"""Translation module using Argos Translate (offline).

Replaces Google Translate with local neural machine translation.
Supports all common European languages -> EN.
No API rate limits. No internet required after initial package download.

All source languages are known from data structure:
  - Descriptions: keys are language codes (fr, de, es, etc.)
  - Pricing: always French
  - Reviews: always French (Park4Night is a French site)

Workers call the translation server via HTTP. The server runs argos-translate
in a ThreadPoolExecutor(32) to saturate all CPU cores without GIL contention.
If the server is unreachable, a clear exception is raised — there is no fallback.

Translation caching is handled by pipeline.py via diskcache.
This module is a pure translation engine with no cache management.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

import argostranslate.package as argos_package
import argostranslate.translate as argos_translate

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline")

# ── HTTP server configuration ─────────────────────────────────────────
_DEFAULT_SERVER_URL = os.environ.get("TRANSLATION_SERVER_URL", "http://127.0.0.1:8765")
_HTTP_TIMEOUT = 120  # seconds — large batches can take a while

# Source languages to install translation packages for (→ English).
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


# ── Package management ────────────────────────────────────────────────


def _ensure_packages_installed() -> None:
    """Ensure all required language packages are installed."""
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
                f"No translation packages available for: {', '.join(missing_languages)}. "
                f"Run 'uv run pipeline.py --setup' to install packages."
            )

        if packages_to_install:
            logger.info(
                f"Installing {len(packages_to_install)} translation packages "
                f"(one-time, offline after download)..."
            )
            for lang_code, pkg in packages_to_install:
                logger.info(f"Installing {lang_code} → en...")
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
    """Preload all translation models into memory.

    Call this in each worker process (spawn method).
    Uses realistic text to fully warm stanza splitters + ctranslate2 pipeline.
    """
    warmup_text = (
        "C'est un bel endroit pour camper avec beaucoup d'espace et des installations propres "
        "et un accès facile à la mer pour les caravanes et les camping-cars. "
        "Nous avons passé une excellente nuit ici et nous reviendrons certainement."
    )
    logger.info("Preloading translation models...")
    for lang_code in REQUIRED_SOURCE_LANGUAGES:
        try:
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
        except Exception:
            logger.warning("Failed to preload model for %s", lang_code)
    logger.info("All translation models preloaded")


# ── Translation ───────────────────────────────────────────────────────


def _translate_single(text: str, src_lang: str) -> tuple[str, str]:
    """Translate a single text to English using argos-translate.

    Pure translation — no caching. Caching handled by stages.translate_text().
    English source text is returned immediately without any processing.
    """
    if not text or not text.strip():
        return (text, text)

    stripped = text.strip()

    if src_lang == "en":
        # English source → no translation needed, return immediately
        return (text, stripped)

    installed = argos_package.get_installed_packages()
    has_model = any(pkg.from_code == src_lang and pkg.to_code == "en" for pkg in installed)
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
    max_workers: int = 8,
) -> dict[str, str]:
    """Translate a batch of texts to English using argos-translate.

    Pure translation — no caching. Caching handled by stages.translate_text().

    Returns {original_text: translated_text} for all inputs.

    Note: Runs sequentially because argos-translate is not thread-safe
    (CPU-bound neural translation holds GIL + internal model locks).
    Parallelism is provided by the worker processes (16 workers).
    """
    if not texts:
        return {}

    results: dict[str, str] = {}
    for text, lang in texts:
        original, translated = _translate_single(text, lang)
        results[original] = translated

    return results


# ── HTTP Client ───────────────────────────────────────────────────────


def translate_batch_http(
    texts: list[tuple[str, str]],
    server_url: str | None = None,
) -> dict[str, str]:
    """Translate a batch of texts via the HTTP translation server.

    Sends all texts to the translation server in a single HTTP request.
    The server uses ThreadPoolExecutor(32) to parallelize across CPU cores,
    bypassing the GIL limitation of per-worker argos-translate.

    Args:
        texts: List of (text, source_language) tuples.
        server_url: URL of the translation server. Defaults to
            TRANSLATION_SERVER_URL env var or http://127.0.0.1:8765.

    Returns:
        Dict mapping original text → translated text.

    Raises:
        RuntimeError: If the server is unreachable.
    """
    if not texts:
        return {}

    url = (server_url or _DEFAULT_SERVER_URL).rstrip("/")

    import httpx

    # Filter out English source texts — no translation needed
    non_en_texts = [(text, lang) for text, lang in texts if lang != "en"]
    en_texts = {text: text.strip() for text, lang in texts if lang == "en"}

    # Convert [(text, lang), ...] to [[text, lang], ...] for JSON
    payload = {"texts": [[text, lang] for text, lang in non_en_texts]}

    try:
        response = httpx.post(
            f"{url}/translate",
            json=payload,
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Translation server unreachable at {url}. "
            f"Is the server running? Start it with: "
            f"cd scripts/pipeline && uv run python translation_server.py"
        )
    except httpx.TimeoutException:
        raise RuntimeError(
            f"Translation request timed out after {_HTTP_TIMEOUT}s "
            f"(batch size: {len(texts)} texts). "
            f"Server may be overloaded."
        )
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Translation server error: {e.response.status_code}") from e

    result = response.json()
    translations = result.get("translations", {})
    # Merge English texts back (no translation needed)
    translations.update(en_texts)
    return translations
