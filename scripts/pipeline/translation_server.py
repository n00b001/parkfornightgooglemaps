"""Translation HTTP server using FastAPI + argostranslate.

Runs as a separate process that worker processes call via HTTP.
This bypasses the GIL — each worker process makes independent HTTP
requests, and the server uses a thread pool for ctranslate2.

Architecture:
  Worker 1 ──→ [HTTP] ──→ Translation Server (FastAPI + ThreadPool)
  Worker 2 ──→ [HTTP] ──→   ↓ argostranslate (ctranslate2)
  ...        ──→ [HTTP] ──→   ↓ ThreadPoolExecutor(16)
  Worker 32 ──→ [HTTP] ──→   → responses

Start standalone:
    cd scripts/pipeline && uv run python translation_server.py

Start from pipeline:
    server = TranslationServer(port=8900)
    server.start()
    # ... workers use HTTP client on port 8900 ...
    server.shutdown()
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import argostranslate.package as argos_package
import argostranslate.translate as argos_translate
from fastapi import FastAPI
from pydantic import BaseModel
from uvicorn import Config, Server

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline.translation_server")

# Thread pool size: ctranslate2 releases GIL between batches,
# so multiple threads can translate in parallel.
# Benchmark: 16 threads saturate a 32-core machine well.
TRANSLATION_THREADS = 16

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

# ── FastAPI app ──────────────────────────────────────────────────────

app = FastAPI(title="Translation Server", version="1.0.0")

# Session cache: text|lang -> translation (in-memory, per-session)
_session_cache: dict[str, str] = {}
_session_cache_lock = threading.Lock()

# Thread pool for translation
_executor = ThreadPoolExecutor(
    max_workers=TRANSLATION_THREADS,
    thread_name_prefix="translate",
)


class TranslationRequest(BaseModel):
    """Request body for /translate endpoint."""

    texts: list[list[str]]  # [[text, lang], ...]


class TranslationResponse(BaseModel):
    """Response from /translate endpoint."""

    translations: dict[str, str]  # {original_text: translated_text}


def _ensure_packages() -> None:
    """Ensure all translation packages are installed."""
    argos_package.update_package_index()

    available = argos_package.get_available_packages()
    installed = argos_package.get_installed_packages()
    installed_pairs = {
        (pkg.from_code, pkg.to_code) for pkg in installed if hasattr(pkg, "from_code")
    }

    for lang_code in REQUIRED_SOURCE_LANGUAGES:
        if (lang_code, "en") not in installed_pairs:
            match = next(
                (pkg for pkg in available if pkg.from_code == lang_code and pkg.to_code == "en"),
                None,
            )
            if match:
                download_path = match.download()
                argos_package.install_from_path(download_path)
                download_path.unlink(missing_ok=True)
                logger.info(f"Installed {lang_code} → en")


def _preload_models() -> None:
    """Preload all translation models into memory."""
    logger.info("Preloading translation models...")
    for lang_code in REQUIRED_SOURCE_LANGUAGES:
        try:
            argos_translate.translate(
                "test sentence for preloading",
                from_code=lang_code,
                to_code="en",
            )
            logger.info(f"  Preloaded {lang_code} → en")
        except Exception as e:
            logger.warning(f"Failed to preload {lang_code}: {e}")
    logger.info("All models preloaded")


def _translate_one(text: str, lang: str) -> tuple[str, str]:
    """Translate a single text. Called from thread pool."""
    if not text or not text.strip():
        return (text, text)

    stripped = text.strip()
    if lang == "en":
        return (text, stripped)

    # Check session cache
    key = f"{stripped}|{lang}"
    with _session_cache_lock:
        if key in _session_cache:
            return (text, _session_cache[key])

    installed = argos_package.get_installed_packages()
    has_model = any(pkg.from_code == lang and pkg.to_code == "en" for pkg in installed)
    if not has_model:
        logger.warning(f"No model for {lang}→en, returning original: {stripped[:60]}")
        return (text, stripped)

    try:
        translated = argos_translate.translate(stripped, from_code=lang, to_code="en")
        if not translated or not translated.strip():
            raise RuntimeError(f"Empty translation ({lang}→en): {stripped[:60]}")
        result = translated.strip()
        with _session_cache_lock:
            _session_cache[key] = result
        return (text, result)
    except Exception as e:
        logger.warning(f"Translation failed ({lang}): {e}")
        return (text, stripped)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "threads": str(TRANSLATION_THREADS)}


@app.post("/translate")
def translate(request: TranslationRequest) -> TranslationResponse:
    """Translate a batch of texts to English.

    Request: {"texts": [["C'est la vie", "fr"], ["Hello", "en"]]}
    Response: {"translations": {"C'est la vie": "That's life", "Hello": "Hello"}}
    """
    if not request.texts:
        return TranslationResponse(translations={})

    # Deduplicate
    unique: dict[str, tuple[str, str]] = {}
    for text, lang in request.texts:
        key = text.strip()
        if key and key not in unique:
            unique[key] = (text, lang)

    # Submit to thread pool
    futures = [_executor.submit(_translate_one, text, lang) for text, lang in unique.values()]

    translations: dict[str, str] = {}
    for future in futures:
        original, translated = future.result()
        translations[original] = translated

    return TranslationResponse(translations=translations)


# ── Server management ────────────────────────────────────────────────


class TranslationServer:
    """Manages the translation server process.

    Usage:
        server = TranslationServer(port=8900)
        server.start()
        # Workers call http://localhost:8900/translate
        server.shutdown()
    """

    def __init__(self, port: int = 8900) -> None:
        self.port = port
        self._server: Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the translation server in a background thread."""
        # Ensure packages and preload models in the main thread first
        _ensure_packages()
        _preload_models()

        config = Config(
            app=app,
            host="127.0.0.1",
            port=self.port,
            log_level="info",
            access_log=False,
        )
        self._server = Server(config)

        self._thread = threading.Thread(
            target=self._server.run,
            name="translation-server",
            daemon=True,
        )
        self._thread.start()

        # Wait for server to be ready
        import time

        for _ in range(30):  # 3 second timeout
            time.sleep(0.1)
            if self._server.started:
                break
        else:
            raise RuntimeError("Translation server failed to start")

        logger.info(f"Translation server started on port {self.port}")

    def shutdown(self) -> None:
        """Shutdown the translation server."""
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Translation server shut down")

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


# ── CLI entry point ──────────────────────────────────────────────────


def main() -> None:
    """Run the translation server as a standalone process."""
    import argparse
    import signal

    parser = argparse.ArgumentParser(description="Translation Server")
    parser.add_argument("--port", type=int, default=8900, help="Port to listen on")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    server = TranslationServer(port=args.port)

    def _handle_signal(signum: int, frame: Any) -> None:
        print(f"\nReceived {signal.Signals(signum).name}, shutting down...")
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    server.start()
    print(f"Translation server running on {server.url}")

    # Keep main thread alive
    try:
        while server.is_running:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
