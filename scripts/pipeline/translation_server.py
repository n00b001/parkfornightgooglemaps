"""HTTP translation server for the pipeline.

Runs argostranslate in a single process with ThreadPoolExecutor so that
multiple worker processes can translate concurrently via HTTP without
each loading their own copy of the models.

Architecture:
  Worker 1 ─┐
  Worker 2 ─┼──→ [FastAPI Server :8765] ─→ ThreadPoolExecutor(32)
  ...       │    (1 set of models, 32 threads, GIL released by ctranslate2)
  Worker 16 ┘

cttranslate2 releases the Python GIL during inference, so 32 threads
actually utilize 32 cores for the neural network computation.

Usage:
    # Start server manually:
    cd scripts/pipeline && uv run python -m translation_server

    # Or let pipeline.py start it automatically (default behavior).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import argostranslate.package as argos_package
import argostranslate.translate as argos_translate
from fastapi import FastAPI
from pydantic import BaseModel
from uvicorn import Config, Server

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline.translation_server")

# ── Configuration ─────────────────────────────────────────────────────
SERVER_HOST = "127.0.0.1"
SERVER_PORT = int(os.environ.get("TRANSLATION_PORT", "8765"))
TRANSLATION_THREADS = int(os.environ.get("TRANSLATION_THREADS", "32"))

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

# ── Request/Response schemas ──────────────────────────────────────────


class TranslationItem(BaseModel):
    text: str
    lang: str


class TranslationRequest(BaseModel):
    items: list[TranslationItem]


class TranslationResponse(BaseModel):
    results: dict[str, str]  # original_text -> translated_text


# ── Model lifecycle ───────────────────────────────────────────────────
_models_ready = False
_models_lock = threading.Lock()


def _ensure_models_loaded() -> None:
    """Install packages and preload all translation models (once)."""
    global _models_ready
    with _models_lock:
        if _models_ready:
            return

        logger.info("Loading argos-translate packages...")
        argos_package.update_package_index()

        installed_pairs = {
            (pkg.from_code, pkg.to_code)
            for pkg in argos_package.get_installed_packages()
            if hasattr(pkg, "from_code")
        }

        available = argos_package.get_available_packages()
        for lang in REQUIRED_SOURCE_LANGUAGES:
            if (lang, "en") not in installed_pairs:
                match = next(
                    (p for p in available if p.from_code == lang and p.to_code == "en"),
                    None,
                )
                if match:
                    path = match.download()
                    argos_package.install_from_path(path)
                    path.unlink(missing_ok=True)
                    logger.info("Installed %s → en", lang)

        # Preload all models into memory
        logger.info("Preloading %d translation models...", len(REQUIRED_SOURCE_LANGUAGES))
        for lang in REQUIRED_SOURCE_LANGUAGES:
            try:
                argos_translate.translate("preload test", from_code=lang, to_code="en")
            except Exception as e:
                logger.warning("Failed to preload %s: %s", lang, e)

        _models_ready = True
        logger.info(
            "Translation server ready — %d threads, port %d",
            TRANSLATION_THREADS,
            SERVER_PORT,
        )


def _translate_one(item: TranslationItem) -> tuple[str, str]:
    """Translate a single text. Called from thread pool."""
    text = item.text.strip()
    lang = item.lang

    if not text or lang == "en":
        return (item.text, text)

    installed = argos_package.get_installed_packages()
    has_model = any(
        pkg.from_code == lang and pkg.to_code == "en"
        for pkg in installed
        if hasattr(pkg, "from_code")
    )
    if not has_model:
        return (item.text, text)

    try:
        translated = argos_translate.translate(text, from_code=lang, to_code="en")
        result = translated.strip() if translated else text
        return (item.text, result)
    except Exception as e:
        logger.warning("Translation failed (%s→en): %s", lang, e)
        return (item.text, text)


# ── FastAPI app ───────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_models_loaded()
    yield


app = FastAPI(title="Translation Server", lifespan=lifespan)


@app.post("/translate", response_model=TranslationResponse)
def translate_endpoint(request: TranslationRequest) -> TranslationResponse:
    """Translate a batch of texts to English.

    Deduplicates identical texts before translating.
    """
    if not request.items:
        return TranslationResponse(results={})

    # Deduplicate by (text, lang) — same text+lang only translated once
    seen: dict[tuple[str, str], str] = {}  # (original_text, lang) -> original_text
    unique: list[TranslationItem] = []
    for item in request.items:
        key = (item.text, item.lang)
        if key not in seen:
            seen[key] = item.text
            unique.append(item)

    # Translate in parallel threads
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=TRANSLATION_THREADS) as pool:
        for original, translated in pool.map(_translate_one, unique):
            results[original] = translated

    return TranslationResponse(results=results)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "threads": str(TRANSLATION_THREADS)}


# ── Server runner ─────────────────────────────────────────────────────


def run_server(host: str = SERVER_HOST, port: int = SERVER_PORT) -> None:
    """Run the translation server (blocking)."""
    config = Config(app, host=host, port=port, log_level="info")
    server = Server(config)
    server.run()


class TranslationServer:
    """Manage the translation server as a background process.

    Used by pipeline.py to start/stop the server automatically.
    """

    def __init__(self, host: str = SERVER_HOST, port: int = SERVER_PORT) -> None:
        self.host = host
        self.port = port
        self._server: Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the server in a background thread."""
        _ensure_models_loaded()
        config = Config(app, host=self.host, port=self.port, log_level="warning")
        self._server = Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        # Wait for server to be ready
        import httpx as httpx_lib

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                resp = httpx_lib.get(f"http://{self.host}:{self.port}/health", timeout=2)
                if resp.status_code == 200:
                    logger.info("Translation server started on %s:%d", self.host, self.port)
                    return
            except Exception:
                pass
            time.sleep(0.5)
        logger.error("Translation server failed to start within 30s")
        raise RuntimeError("Translation server failed to start")

    def shutdown(self) -> None:
        """Shutdown the server."""
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Translation server shut down")

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


# ── CLI entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Translation Server")
    parser.add_argument("--host", default=SERVER_HOST)
    parser.add_argument("--port", type=int, default=SERVER_PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_server(host=args.host, port=args.port)
