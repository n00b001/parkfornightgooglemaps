"""Shared translation server for the pipeline.

Replaces per-worker argos-translate instances with a single server process
that batches translations from all workers.

Architecture:
  Worker 1 ─┐
  Worker 2 ─┼──→ [Translation Server] ─→ response Queue
  ...       │    (1 model, ThreadPool(4) = 63 texts/s)
  Worker 24 ┘

Workers send requests via request Queue, poll response Queue for their results.
Each response has a request_id so workers can match responses to requests.

Caching: uses joblib.Memory for disk persistence across restarts.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context
from typing import Any

from joblib import Memory

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline.translation_server")

# Batch size: collect this many strings before translating.
BATCH_SIZE = 128
# Batch timeout: don't wait longer than this for a full batch.
BATCH_TIMEOUT = 0.05  # seconds
# Thread pool for translation (benchmarked: 4 = optimal for ctranslate2)
TRANSLATION_THREADS = 4

# Use spawn context explicitly to match ProcessPoolExecutor
_mp_ctx = get_context("spawn")

# Cache directory for translation results
_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "cache",
    "joblib",
)


class TranslationServer:
    """Translation server running in a separate process.

    Workers submit via request_queue, poll response_queue for results.
    All multiprocessing objects use 'spawn' context to avoid fork/spawn conflicts.
    """

    def __init__(self) -> None:
        self._process: Any = None
        self._request_queue: Any = _mp_ctx.Queue()
        self._response_queue: Any = _mp_ctx.Queue()
        # Shared dict for non-blocking results: request_id -> {text: translation}
        self._results: Any = _mp_ctx.Manager().dict()

    def start(self) -> None:
        """Start the translation server process."""
        self._process = _mp_ctx.Process(
            target=_server_main,
            args=(self._request_queue, self._response_queue, self._results),
            daemon=True,
            name="translation-server",
        )
        self._process.start()
        logger.info(f"Translation server started (pid={self._process.pid})")

    def shutdown(self) -> None:
        """Shutdown the translation server."""
        try:
            self._request_queue.put_nowait(("shutdown", []))
        except Exception:
            pass
        if self._process and self._process.is_alive():
            self._process.join(timeout=10)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=5)
        logger.info("Translation server shut down")

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.is_alive()


def _server_main(
    request_queue: Any,
    response_queue: Any,
    results_dict: Any,
) -> None:
    """Main loop for the translation server process."""
    import argostranslate.package as argos_package
    import argostranslate.translate as argos_translate

    logger.info("Translation server: installing packages...")
    argos_package.update_package_index()

    # joblib.Memory for disk-persistent translation cache
    memory = Memory(_CACHE_DIR, verbose=0)

    @memory.cache
    def _cached_translate(text: str, lang: str) -> str:
        """Translate a single text — cached on disk via joblib."""
        translated = argos_translate.translate(text, from_code=lang, to_code="en")
        return translated.strip()

    logger.info("Translation server: preloading French model...")
    argos_translate.translate("test", from_code="fr", to_code="en")
    logger.info("Translation server: ready")

    # In-memory cache for current session (fast hits)
    _session_cache: dict[str, str] = {}

    # Buffer: request_id -> [(text, lang), ...]
    buffer: dict[str, list[tuple[str, str]]] = {}

    def _get_translation(text: str, lang: str) -> str:
        """Get translation from session cache, disk cache, or compute."""
        key = f"{text}|{lang}"
        if key in _session_cache:
            return _session_cache[key]
        result = _cached_translate(text, lang)
        _session_cache[key] = result
        return result

    def _process_batch() -> None:
        if not buffer:
            return

        # Group by language, deduplicate
        by_lang: dict[str, set[str]] = {}
        for texts in buffer.values():
            for text, lang in texts:
                by_lang.setdefault(lang, set()).add(text.strip())

        # Translate
        all_results: dict[str, str] = {}
        for lang, lang_texts in by_lang.items():
            lang_texts_list = list(lang_texts)

            def _translate_one(text: str) -> tuple[str, str]:
                try:
                    translated = _get_translation(text, lang)
                    return (text, translated)
                except Exception as e:
                    logger.warning(f"Translation failed ({lang}): {e}")
                    return (text, text)

            with ThreadPoolExecutor(max_workers=TRANSLATION_THREADS) as executor:
                for original, translated in executor.map(_translate_one, lang_texts_list):
                    all_results[original] = translated

        # Send responses for each request
        for req_id, texts in buffer.items():
            response: dict[str, str] = {}
            for text, lang in texts:
                stripped = text.strip()
                if lang == "en":
                    response[text] = stripped
                elif stripped in all_results:
                    response[text] = all_results[stripped]
                else:
                    response[text] = stripped
            response_queue.put((req_id, response))
            # Also store in shared dict for non-blocking access
            response["_done"] = "yes"
            results_dict[req_id] = response

        buffer.clear()

    # Main loop
    batch_timer = time.time()

    while True:
        try:
            try:
                item = request_queue.get(timeout=0.05)
            except Exception:
                item = None

            if item is None:
                if time.time() - batch_timer >= BATCH_TIMEOUT and buffer:
                    _process_batch()
                    batch_timer = time.time()
                continue

            req_id, texts = item

            if req_id == "shutdown":
                if buffer:
                    _process_batch()
                logger.info("Translation server: shutting down")
                break

            buffer[req_id] = texts

            total_texts = sum(len(t) for t in buffer.values())
            if total_texts >= BATCH_SIZE or time.time() - batch_timer >= BATCH_TIMEOUT:
                _process_batch()
                batch_timer = time.time()

        except KeyboardInterrupt:
            if buffer:
                _process_batch()
            break
        except Exception as e:
            logger.error(f"Translation server error: {e}", exc_info=True)
