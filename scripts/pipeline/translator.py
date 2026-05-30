"""Translation client module.

Calls the HTTP translation server (translation_server.py) to translate
batches of texts. Falls back to direct argos-translate if the server
is unavailable.

The server runs argostranslate with ThreadPoolExecutor(32) in a single
process — ctranslate2 releases the GIL during inference, so threads
actually utilize multiple cores.

Caching is handled by pipeline.py via diskcache. This module is a
pure translation engine with no cache management.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

import argostranslate.package as argos_package
import argostranslate.translate as argos_translate
import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline")

# ── Configuration ─────────────────────────────────────────────────────
SERVER_URL = os.environ.get(
    "TRANSLATION_SERVER_URL",
    "http://127.0.0.1:8765",
)
HTTP_TIMEOUT = float(os.environ.get("TRANSLATION_HTTP_TIMEOUT", "120"))

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

# ── Shared state ──────────────────────────────────────────────────────
_PACKAGES_INITIALIZED = False
_PACKAGES_LOCK = threading.Lock()

# HTTP client reused across calls
_http_client: httpx.Client | None = None
_http_lock = threading.Lock()


def _get_http_client() -> httpx.Client:
    global _http_client
    with _http_lock:
        if _http_client is None:
            _http_client = httpx.Client(timeout=HTTP_TIMEOUT)
        return _http_client


# ── Package management ────────────────────────────────────────────────


def _ensure_packages_installed() -> None:
    """Ensure all required language packages are installed (for fallback)."""
    global _PACKAGES_INITIALIZED

    with _PACKAGES_LOCK:
        if _PACKAGES_INITIALIZED:
            return

        logger.info("Checking argos-translate language packages...")
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
            logger.info(
                "Installing %d translation packages...",
                len(packages_to_install),
            )
            for lang_code, pkg in packages_to_install:
                logger.info("Installing %s → en...", lang_code)
                download_path = pkg.download()
                argos_package.install_from_path(download_path)
                download_path.unlink(missing_ok=True)
        else:
            logger.info("All translation packages already installed")

        _PACKAGES_INITIALIZED = True


def ensure_packages_installed() -> None:
    """Ensure all required language packages are installed.

    Call this ONCE in the main process BEFORE spawning workers.
    """
    _ensure_packages_installed()


def preload_models() -> None:
    """Preload translation models (no-op when using HTTP server).

    The server preloads its own models. This exists for backward
    compatibility and fallback mode.
    """
    # Check if server is available — if so, no need to preload locally
    try:
        client = _get_http_client()
        resp = client.get(f"{SERVER_URL}/health", timeout=5)
        if resp.status_code == 200:
            logger.info(
                "Translation server available at %s — skipping local model preload",
                SERVER_URL,
            )
            return
    except Exception:
        pass

    # Fallback: preload locally
    logger.info("Translation server unavailable — preloading models locally...")
    for lang_code in REQUIRED_SOURCE_LANGUAGES:
        try:
            argos_translate.translate(
                "test sentence for preloading",
                from_code=lang_code,
                to_code="en",
            )
        except Exception:
            logger.warning("Failed to preload model for %s", lang_code)
    logger.info("All translation models preloaded")


# ── Translation ───────────────────────────────────────────────────────


def _translate_single(text: str, src_lang: str) -> tuple[str, str]:
    """Translate a single text to English using argos-translate (fallback)."""
    if not text or not text.strip():
        return (text, text)

    stripped = text.strip()
    if src_lang == "en":
        return (text, stripped)

    installed = argos_package.get_installed_packages()
    has_model = any(
        pkg.from_code == src_lang and pkg.to_code == "en"
        for pkg in installed
        if hasattr(pkg, "from_code")
    )
    if not has_model:
        logger.warning(
            "No translation model for %s→en, skipping: %s...",
            src_lang,
            stripped[:80],
        )
        return (text, stripped)

    translated = argos_translate.translate(stripped, from_code=src_lang, to_code="en")
    if not translated or not translated.strip():
        raise RuntimeError(f"Translation returned empty result ({src_lang}→en): {stripped[:80]}...")
    return (text, translated.strip())


def translate_batch(
    texts: list[tuple[str, str]],
    max_workers: int | None = None,
) -> dict[str, str]:
    """Translate a batch of texts to English.

    Tries the HTTP translation server first. Falls back to direct
    argos-translate if the server is unavailable.

    Args:
        texts: List of (text, source_language) tuples.
        max_workers: Unused (kept for backward compatibility).

    Returns:
        {original_text: translated_text} for all inputs.
    """
    _ensure_packages_installed()
    if not texts:
        return {}

    # Filter out empty texts and English texts
    to_translate = [(t, lang) for t, lang in texts if t and t.strip() and lang != "en"]
    skip_results = {
        t: (t.strip() if t.strip() else t)
        for t, lang in texts
        if not to_translate or (t, lang) not in to_translate
    }

    if not to_translate:
        return skip_results

    # Try HTTP server first
    try:
        client = _get_http_client()
        items = [{"text": t, "lang": lang} for t, lang in to_translate]
        resp = client.post(
            f"{SERVER_URL}/translate",
            json={"items": items},
        )
        if resp.status_code == 200:
            server_results = resp.json()["results"]
            # Merge with skip results
            all_results = dict(skip_results)
            all_results.update(server_results)
            return all_results
    except httpx.ConnectError:
        logger.info(
            "Translation server unavailable at %s — using local fallback",
            SERVER_URL,
        )
    except Exception as e:
        logger.warning("Translation server error: %s — using local fallback", e)

    # Fallback: direct argos-translate
    logger.info("Translating %d texts locally...", len(to_translate))
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = dict(skip_results)
    worker_count = max_workers or 8
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_translate_single, text, lang): (text, lang)
            for text, lang in to_translate
        }
        for future in as_completed(futures):
            original, translated = future.result()
            results[original] = translated

    return results
