"""HTTP translation server for the pipeline.

Replaces per-worker argos-translate instances with a single server process
that handles translation requests from all workers over HTTP.

Architecture:
  Worker 1 ─┐
  Worker 2 ─┼──→ [FastAPI Server] ─→ ThreadPoolExecutor(32) ─→ argos-translate
  ...       │    (models loaded once, no GIL contention across workers)
  Worker 16 ┘

Each worker calls POST /translate with a JSON body:
  {"texts": [["C'est un beau jour", "fr"], ["Bonjour", "fr"]]}
Response:
  {"translations": {"C'est un beau jour": "It's a beautiful day", ...}}

Benefits over per-worker argos:
  - Models loaded ONCE (29 languages × ~50MB each = ~1.5GB, not ×16 workers)
  - ThreadPoolExecutor(32) saturates all CPU cores for ctranslate2
  - Workers are unblocked — they continue scraping while translation happens
  - No GIL contention — workers are separate processes, server handles threading

Usage:
  # Start server standalone:
  cd scripts/pipeline && uv run python translation_server.py

  # Or let pipeline.py start it automatically (default behavior)
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import argostranslate.package as argos_package
import argostranslate.translate as argos_translate

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline.translation_server")

# Suppress verbose argostranslate/stanza logging
logging.getLogger("argostranslate").setLevel(logging.WARNING)
logging.getLogger("stanza").setLevel(logging.WARNING)

# ── Server Configuration ─────────────────────────────────────────────
SERVER_HOST = "127.0.0.1"
SERVER_PORT = int(os.environ.get("TRANSLATION_SERVER_PORT", "8765"))
TRANSLATION_THREADS = int(os.environ.get("TRANSLATION_THREADS", "32"))

# Source languages (same as translator.py)
REQUIRED_SOURCE_LANGUAGES = [
    "fr",
    "de",
    "es",
    "it",
    "nl",
    "pt",
    "pl",
    "ru",
    "sv",
    "da",
    "nb",
    "fi",
    "cs",
    "el",
    "hu",
    "ro",
    "bg",
    "sk",
    "sl",
    "et",
    "lt",
    "lv",
    "uk",
    "tr",
    "sq",
    "ca",
    "gl",
    "eu",
    "ga",
]

# ── Global State ─────────────────────────────────────────────────────
_server_thread: threading.Thread | None = None
_server_ready = threading.Event()


# ── Translation Engine ───────────────────────────────────────────────


class TranslationEngine:
    """Thread-safe translation engine with model preloading and caching."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session_cache: dict[str, str] = {}
        self._models_loaded = False

    def install_packages(self) -> None:
        """Install all required language packages."""
        logger.info("Installing argos-translate language packages...")
        argos_package.update_package_index()

        available_packages = argos_package.get_available_packages()
        installed_packages = argos_package.get_installed_packages()

        installed_pairs = {
            (pkg.from_code, pkg.to_code) for pkg in installed_packages if hasattr(pkg, "from_code")
        }

        packages_to_install = []
        missing_languages = []

        for lang_code in REQUIRED_SOURCE_LANGUAGES:
            if (lang_code, "en") not in installed_pairs:
                match = next(
                    (
                        pkg
                        for pkg in available_packages
                        if pkg.from_code == lang_code and pkg.to_code == "en"
                    ),
                    None,
                )
                if match:
                    packages_to_install.append((lang_code, match))
                else:
                    missing_languages.append(lang_code)

        if missing_languages:
            raise RuntimeError(
                f"No translation packages available for: {', '.join(missing_languages)}"
            )

        if packages_to_install:
            logger.info(f"Installing {len(packages_to_install)} translation packages...")
            for lang_code, pkg in packages_to_install:
                logger.info(f"  Installing {lang_code} → en...")
                download_path = pkg.download()
                argos_package.install_from_path(download_path)
                download_path.unlink(missing_ok=True)
        else:
            logger.info("All translation packages already installed")

    def preload_models(self) -> None:
        """Preload all translation models into memory.

        Uses realistic French text (long review-style sentence) to fully warm
        stanza sentence splitters, ctranslate2 models, and torch LSTM layers.
        A simple "test" sentence only loads the model but doesn't initialize
        the inference pipeline — first real requests would still be slow.
        """
        # Realistic text that exercises stanza segmentation + ctranslate2 inference
        warmup_text = (
            "C'est un bel endroit pour camper avec beaucoup d'espace et des installations propres "
            "et un accès facile à la mer pour les caravanes et les camping-cars. "
            "Nous avons passé une excellente nuit ici et nous reviendrons certainement."
        )
        logger.info("Preloading %d translation models...", len(REQUIRED_SOURCE_LANGUAGES))
        for lang_code in REQUIRED_SOURCE_LANGUAGES:
            try:
                # First pass: load the model
                argos_translate.translate(
                    "test sentence for preloading",
                    from_code=lang_code,
                    to_code="en",
                )
                # Second pass: warm stanza splitters + ctranslate2 inference pipeline
                argos_translate.translate(
                    warmup_text,
                    from_code=lang_code,
                    to_code="en",
                )
                logger.debug("  Preloaded %s → en", lang_code)
            except Exception as e:
                logger.warning("Failed to preload model for %s: %s", lang_code, e)
        self._models_loaded = True
        logger.info("All translation models preloaded")

    def translate_single(self, text: str, src_lang: str) -> str:
        """Translate a single text to English."""
        if not text or not text.strip():
            return text

        stripped = text.strip()

        if src_lang == "en":
            return stripped

        # Check session cache (thread-safe via lock)
        cache_key = f"{stripped}|{src_lang}"
        with self._lock:
            if cache_key in self._session_cache:
                return self._session_cache[cache_key]

        # Check if model exists
        installed = argos_package.get_installed_packages()
        has_model = any(pkg.from_code == src_lang and pkg.to_code == "en" for pkg in installed)
        if not has_model:
            logger.warning("No model for %s→en, returning original", src_lang)
            return stripped

        # Translate
        try:
            translated = argos_translate.translate(stripped, from_code=src_lang, to_code="en")
            result = translated.strip() if translated else stripped
        except Exception as e:
            logger.warning("Translation failed (%s→en): %s", src_lang, e)
            result = stripped

        # Store in session cache
        with self._lock:
            self._session_cache[cache_key] = result

        return result

    def translate_batch(self, texts: list[tuple[str, str]]) -> dict[str, str]:
        """Translate a batch of texts using thread pool.

        Args:
            texts: List of (text, source_language) tuples.

        Returns:
            Dict mapping original text → translated text.
        """
        if not texts:
            return {}

        # Deduplicate by (text, lang) and skip English-to-English
        unique_items: dict[str, tuple[str, str]] = {}
        for text, lang in texts:
            stripped = text.strip()
            if lang == "en":
                # English source → no translation needed
                continue
            key = f"{stripped}|{lang}"
            if key not in unique_items:
                unique_items[key] = (stripped, lang)

        # Check session cache first
        cached_results: dict[str, str] = {}
        to_translate: list[tuple[str, str]] = []

        with self._lock:
            for key, (text, lang) in unique_items.items():
                if key in self._session_cache:
                    cached_results[text] = self._session_cache[key]
                else:
                    to_translate.append((text, lang))

        if not to_translate:
            return {text: cached_results.get(text, text) for text, _ in texts}

        # Translate remaining using thread pool
        def _do_translate(item: tuple[str, str]) -> tuple[str, str]:
            text, lang = item
            translated = self.translate_single(text, lang)
            return (text, translated)

        with ThreadPoolExecutor(max_workers=TRANSLATION_THREADS) as executor:
            for original, translated in executor.map(_do_translate, to_translate):
                cached_results[original] = translated

        # Build final result (map each input to its translation)
        results: dict[str, str] = {}
        for text, lang in texts:
            stripped = text.strip()
            if lang == "en":
                results[text] = stripped
            elif stripped in cached_results:
                results[text] = cached_results[stripped]
            else:
                results[text] = stripped

        return results


# ── FastAPI Application ──────────────────────────────────────────────

engine = TranslationEngine()


def create_app() -> Any:
    """Create and configure the FastAPI application."""

    from fastapi import FastAPI

    def _lifespan(app_ref: Any) -> Any:
        """Lifespan context manager for startup/shutdown events."""
        logger.info("Translation server starting on %s:%d", SERVER_HOST, SERVER_PORT)
        logger.info("Thread pool size: %d", TRANSLATION_THREADS)
        yield
        logger.info("Translation server shutting down")

    app = FastAPI(
        title="Translation Server",
        docs_url=None,
        redoc_url=None,
        lifespan=_lifespan,
    )

    @app.post("/translate")
    def translate_endpoint(request: dict[str, Any]) -> dict[str, Any]:
        """Translate a batch of texts.

        Request body:
          {"texts": [["text1", "fr"], ["text2", "de"], ...]}

        Response:
          {"translations": {"text1": "translation1", ...}}
        """
        texts = request.get("texts", [])
        if not texts:
            return {"translations": {}}

        # Convert from [[text, lang], ...] to [(text, lang), ...]
        text_tuples = [(str(t[0]), str(t[1])) for t in texts if len(t) >= 2]

        start_time = time.time()
        translations = engine.translate_batch(text_tuples)
        elapsed = time.time() - start_time

        logger.debug("Translated %d texts in %.3fs", len(text_tuples), elapsed)

        return {"translations": translations}

    @app.get("/health")
    def health_check() -> dict[str, Any]:
        """Health check endpoint."""
        return {
            "status": "ok",
            "models_loaded": engine._models_loaded,
            "cache_size": len(engine._session_cache),
            "threads": TRANSLATION_THREADS,
        }

    return app


# ── Server Lifecycle ─────────────────────────────────────────────────


def start_server(
    host: str = SERVER_HOST,
    port: int = SERVER_PORT,
    install_packages: bool = True,
    preload: bool = True,
) -> None:
    """Start the translation server in a background thread.

    Blocks until the server is ready to accept connections.

    Args:
        host: Host to bind to.
        port: Port to bind to.
        install_packages: Install argos packages if missing.
        preload: Preload all models into memory.
    """
    global _server_thread

    if _server_thread and _server_thread.is_alive():
        logger.info("Translation server already running")
        return

    # Install packages and preload models BEFORE starting the server
    if install_packages:
        engine.install_packages()
    if preload:
        engine.preload_models()

    app = create_app()

    def _run_server() -> None:
        import uvicorn

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning",  # Suppress uvicorn logs during normal operation
            access_log=False,
        )

    _server_thread = threading.Thread(target=_run_server, daemon=True, name="translation-server")
    _server_thread.start()

    # Wait for server to be ready
    import httpx

    deadline = time.time() + 30  # 30 second timeout
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://{host}:{port}/health", timeout=1.0)
            if response.status_code == 200:
                logger.info(
                    "Translation server ready on %s:%d (threads=%d)",
                    host,
                    port,
                    TRANSLATION_THREADS,
                )
                return
        except (httpx.ConnectError, httpx.TimeoutException):
            time.sleep(0.2)

    logger.error("Translation server failed to start within 30 seconds")
    raise RuntimeError("Translation server failed to start")


def stop_server() -> None:
    """Stop the translation server."""
    global _server_thread
    if _server_thread and _server_thread.is_alive():
        logger.info("Stopping translation server...")
        # uvicorn in a thread can't be gracefully stopped easily,
        # but since it's a daemon thread it will exit with the process
        logger.info("Translation server thread will exit with process")


def get_server_url() -> str:
    """Get the URL of the running translation server."""
    return f"http://{SERVER_HOST}:{SERVER_PORT}"


# ── Standalone Execution ─────────────────────────────────────────────


def main() -> None:
    """Run the translation server as a standalone process."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    print(f"Starting translation server on {SERVER_HOST}:{SERVER_PORT}")
    print(f"Thread pool: {TRANSLATION_THREADS} threads")

    engine.install_packages()
    engine.preload_models()

    app = create_app()

    print(f"Server ready on http://{SERVER_HOST}:{SERVER_PORT}")
    print("Endpoints:")
    print("  POST /translate  - Translate texts")
    print("  GET  /health     - Health check")

    uvicorn.run(
        app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
