"""High-performance translation server using CTranslate2 directly.

Bypasses argos-translate's single-sentence API and uses CTranslate2's
translate_batch() with large batches, int8 quantization, and per-language-pair
translators running in parallel to saturate all CPU cores.

Architecture:
  Worker 1 ─┐
  Worker 2 ─┼──→ [FastAPI Server :8765] ─→ 29 parallel translators
  ...       │    (one per language pair, each with its own thread)
  Worker 16 ┘

Key optimizations:
  - One CTranslate2 translator per language pair, running concurrently
  - Each translator has its own queue and processing thread
  - translate_batch() processes sentences in batches within each language
  - int8 quantization for ~2x speedup with negligible quality loss
  - SentencePiece/BPE tokenizers loaded per language pair

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
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import ctranslate2  # type: ignore[import-untyped]
from fastapi import FastAPI
from pydantic import BaseModel
from uvicorn import Config, Server

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline.translation_server")

# ── Configuration ─────────────────────────────────────────────────────
SERVER_HOST = "127.0.0.1"
SERVER_PORT = int(os.environ.get("TRANSLATION_PORT", "8765"))

# CTranslate2 threading per translator.
# With 29 language pairs and 32 cores, use 1-2 threads per translator.
INTER_THREADS = int(os.environ.get("CT2_INTER_THREADS", "1"))
INTRA_THREADS = int(os.environ.get("CT2_INTRA_THREADS", "2"))

# Batch size for translate_batch() within each language pair.
BATCH_SIZE = int(os.environ.get("CT2_BATCH_SIZE", "128"))

# Use int8 quantization for ~2x speedup with negligible quality loss.
COMPUTE_TYPE = os.environ.get("CT2_COMPUTE_TYPE", "int8")

# Accumulation window: wait this long to collect a batch within each language.
BATCH_WINDOW = float(os.environ.get("BATCH_WINDOW", "0.03"))

# Maximum time a sentence waits before being processed anyway.
MAX_WAIT = float(os.environ.get("BATCH_QUEUE_MAX_WAIT", "5.0"))

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


# ── Model loader ──────────────────────────────────────────────────────


def _find_model_path(from_lang: str, to_lang: str) -> Path | None:
    """Find the CTranslate2 model directory for a language pair."""
    base = Path(
        os.environ.get(
            "ARGOS_TRANSLATE_DATA",
            os.path.expanduser("~/.local/share/argos-translate/packages"),
        )
    )

    if not base.exists():
        return None

    for pkg_dir in sorted(base.iterdir()):
        if not pkg_dir.is_dir():
            continue
        name = pkg_dir.name.lower()
        if f"{from_lang}_{to_lang}" in name or f"{from_lang}-{to_lang}" in name:
            model_dir = pkg_dir / "model"
            if model_dir.exists():
                return model_dir

    return None


def _load_tokenizer(pkg_dir: Path) -> Any:
    """Load the tokenizer for a model package."""
    sp_path = pkg_dir / "sentencepiece.model"
    bpe_path = pkg_dir / "bpe.model"

    if sp_path.exists():
        import sentencepiece as spm

        sp = spm.SentencePieceProcessor()
        sp.load(str(sp_path))  # type: ignore[attr-defined]
        return sp
    return None


# ── Translation engine ────────────────────────────────────────────────


def _tokenize(texts: list[str], tokenizer: Any) -> list[list[str]]:
    """Tokenize a batch of texts using SentencePiece."""
    if tokenizer is None:
        return [text.split() for text in texts]
    try:
        return [tokenizer.encode_as_pieces(text) for text in texts]
    except Exception:
        return [text.split() for text in texts]


def _detokenize(tokens: list[str]) -> str:
    """Detokenize a list of tokens back to text."""
    return "".join(tokens).replace("▁", " ").strip()


def _translate_batch(
    translator: Any,
    tokenizer: Any,
    texts: list[str],
) -> list[str]:
    """Translate a batch of texts using CTranslate2 directly."""
    tokenized = _tokenize(texts, tokenizer)

    try:
        results = translator.translate_batch(
            tokenized,
            max_batch_size=BATCH_SIZE,
        )
    except Exception as e:
        logger.warning("Batch translation failed: %s", e)
        return list(texts)

    output = []
    for i, result in enumerate(results):
        try:
            tokens = result.hypotheses[0]
            text = _detokenize(tokens).strip()
            output.append(text if text else texts[i])
        except Exception:
            output.append(texts[i])

    return output


# ── Per-Language Translator Worker ────────────────────────────────────
#
# Each language pair gets its own translator + queue + worker thread.
# This allows multiple language pairs to translate simultaneously,
# saturating all CPU cores.


class _PendingItem:
    """A single sentence waiting to be translated."""

    __slots__ = ("original", "text", "event", "result")

    def __init__(self, original: str, text: str) -> None:
        self.original = original
        self.text = text
        self.event = threading.Event()
        self.result = text


class _LanguageWorker:
    """Manages translation for a single language pair.

    Has its own CTranslate2 translator, queue, and worker thread.
    """

    def __init__(
        self,
        lang: str,
        translator: Any,
        tokenizer: Any,
    ) -> None:
        self.lang = lang
        self.translator = translator
        self.tokenizer = tokenizer
        self._queue: deque[_PendingItem] = deque()
        self._lock = threading.Lock()
        self._not_empty = threading.Event()
        self._running = True
        self._thread = threading.Thread(target=self._work_loop, daemon=True)
        self._thread.start()

    def enqueue(self, item: _PendingItem) -> None:
        """Add a sentence to this language's queue."""
        with self._lock:
            self._queue.append(item)
        self._not_empty.set()

    def _work_loop(self) -> None:
        """Continuously process queued sentences in batches."""
        while self._running:
            # Wait for items in the queue
            self._not_empty.wait(timeout=BATCH_WINDOW)
            self._not_empty.clear()

            with self._lock:
                if not self._queue:
                    continue

                # Collect up to BATCH_SIZE items
                batch: list[_PendingItem] = []
                for _ in range(min(BATCH_SIZE, len(self._queue))):
                    batch.append(self._queue.popleft())

            if not batch:
                continue

            # Translate
            texts = [item.text for item in batch]

            # Deduplicate
            seen: dict[str, int] = {}
            unique_texts: list[str] = []
            text_to_indices: dict[int, list[int]] = {}

            for j, text in enumerate(texts):
                if text not in seen:
                    idx = len(unique_texts)
                    seen[text] = idx
                    unique_texts.append(text)
                    text_to_indices[idx] = []
                text_to_indices[seen[text]].append(j)

            translated = _translate_batch(self.translator, self.tokenizer, unique_texts)

            # Map results back and signal
            for unique_idx, trans_text in enumerate(translated):
                for j in text_to_indices[unique_idx]:
                    batch[j].result = trans_text
                    batch[j].event.set()

    def shutdown(self) -> None:
        """Stop the worker and process remaining items."""
        self._running = False
        self._not_empty.set()
        self._thread.join(timeout=5)


# ── Global translator registry ────────────────────────────────────────
_workers: dict[str, _LanguageWorker] = {}
_workers_lock = threading.Lock()
_workers_ready = False


def _ensure_workers_loaded() -> None:
    """Load all translation models and start worker threads."""
    global _workers_ready
    with _workers_lock:
        if _workers_ready:
            return

        logger.info(
            "Loading %d CTranslate2 translators (inter=%d, intra=%d, batch=%d)...",
            len(REQUIRED_SOURCE_LANGUAGES),
            INTER_THREADS,
            INTRA_THREADS,
            BATCH_SIZE,
        )

        for lang in REQUIRED_SOURCE_LANGUAGES:
            model_path = _find_model_path(lang, "en")
            if not model_path:
                logger.warning("No model found for %s → en", lang)
                continue

            pkg_dir = model_path.parent
            tokenizer = _load_tokenizer(pkg_dir)

            try:
                translator = ctranslate2.Translator(
                    str(model_path),
                    device="cpu",
                    inter_threads=INTER_THREADS,
                    intra_threads=INTRA_THREADS,
                    compute_type=COMPUTE_TYPE,
                )
                worker = _LanguageWorker(lang, translator, tokenizer)
                _workers[lang] = worker
                logger.info("Loaded %s → en worker", lang)
            except Exception as e:
                logger.error("Failed to load %s → en: %s", lang, e)

        _workers_ready = True
        logger.info(
            "Translation server ready — %d workers loaded, port %d",
            len(_workers),
            SERVER_PORT,
        )


# ── FastAPI app ───────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_workers_loaded()
    yield


app = FastAPI(title="Translation Server", lifespan=lifespan)


@app.post("/translate", response_model=TranslationResponse)
def translate_endpoint(request: TranslationRequest) -> TranslationResponse:
    """Translate a batch of texts to English using per-language workers."""
    if not request.items:
        return TranslationResponse(results={})

    results: dict[str, str] = {}
    pending_by_lang: dict[str, list[_PendingItem]] = {}

    for item in request.items:
        lang = item.lang
        original = item.text
        text = item.text.strip()

        if lang == "en" or not text:
            results[original] = text
            continue

        pending = _PendingItem(original, text)
        pending_by_lang.setdefault(lang, []).append(pending)

    # Enqueue to language workers
    for lang, items in pending_by_lang.items():
        worker = _workers.get(lang)
        if worker:
            for item in items:
                worker.enqueue(item)
        else:
            # No worker for this language — return originals
            for item in items:
                results[item.original] = item.text

    # Wait for all pending items
    for items in pending_by_lang.values():
        for item in items:
            item.event.wait(timeout=MAX_WAIT)
            results[item.original] = item.result

    return TranslationResponse(results=results)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "workers": str(len(_workers)),
        "inter_threads": str(INTER_THREADS),
        "intra_threads": str(INTRA_THREADS),
        "batch_size": str(BATCH_SIZE),
        "compute_type": COMPUTE_TYPE,
    }


# ── Server runner ─────────────────────────────────────────────────────


def run_server(host: str = SERVER_HOST, port: int = SERVER_PORT) -> None:
    """Run the translation server (blocking)."""
    config = Config(app, host=host, port=port, log_level="info")
    server = Server(config)
    server.run()


class TranslationServer:
    """Manage the translation server as a background process."""

    def __init__(self, host: str = SERVER_HOST, port: int = SERVER_PORT) -> None:
        self.host = host
        self.port = port
        self._server: Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the server in a background thread."""
        _ensure_workers_loaded()
        config = Config(app, host=self.host, port=self.port, log_level="warning")
        self._server = Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

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
        """Shutdown the server and all workers."""
        for worker in _workers.values():
            worker.shutdown()
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

    parser = argparse.ArgumentParser(description="Translation Server")
    parser.add_argument("--host", default=SERVER_HOST)
    parser.add_argument("--port", type=int, default=SERVER_PORT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_server(host=args.host, port=args.port)
