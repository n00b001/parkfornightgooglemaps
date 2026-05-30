"""Translation module using Argos Translate (offline).

Replaces Google Translate with local neural machine translation.
Supports all common European languages -> EN.
No API rate limits. No internet required after initial package download.

All source languages are known from data structure:
  - Descriptions: keys are language codes (fr, de, es, etc.)
  - Pricing: always French
  - Reviews: always French (Park4Night is a French site)

Translation caching is handled by stages.translate_text() via
@disk_cache.memoize() + @lru_cache decorators. This module is a
pure translation engine with no cache management.

HTTP client: TranslationClient calls the translation server via HTTP,
bypassing the GIL. Falls back to local translation if server is down.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

import argostranslate.package as argos_package
import argostranslate.translate as argos_translate
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline")

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
    """
    logger.info("Preloading translation models...")
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
    """Translate a single text to English using argos-translate.

    Pure translation — no caching. Caching handled by stages.translate_text().
    """
    if not text or not text.strip():
        return (text, text)

    stripped = text.strip()

    if src_lang == "en":
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


class TranslationClient:
    """HTTP client for the translation server.

    Calls the translation server via HTTP, bypassing the GIL.
    Falls back to local translation if the server is down.

    Usage:
        client = TranslationClient(server_url="http://127.0.0.1:8900")
        results = client.translate_batch(texts)
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8900",
        timeout: float = 30.0,
        fallback_to_local: bool = True,
    ) -> None:
        self.server_url = server_url
        self.timeout = timeout
        self.fallback_to_local = fallback_to_local
        self._server_available = True

    def translate_batch(
        self,
        texts: list[tuple[str, str]],
    ) -> dict[str, str]:
        """Translate a batch of texts via HTTP.

        Falls back to local translation if the server is down.
        """
        if not texts:
            return {}

        # Filter out English texts (no translation needed)
        to_translate: list[tuple[str, str]] = []
        english: dict[str, str] = {}
        for text, lang in texts:
            stripped = text.strip()
            if lang == "en" or not stripped:
                english[text] = stripped
            else:
                to_translate.append((text, lang))

        if not to_translate:
            return english

        # Try HTTP server
        if self._server_available:
            try:
                results = self._translate_via_http(to_translate)
                results.update(english)
                return results
            except Exception as e:
                logger.warning(f"Translation server unavailable: {e}")
                if self.fallback_to_local:
                    self._server_available = False
                else:
                    raise

        # Fallback to local translation
        logger.info("Falling back to local translation")
        results = translate_batch(to_translate)
        results.update(english)
        return results

    def _translate_via_http(
        self,
        texts: list[tuple[str, str]],
    ) -> dict[str, str]:
        """Translate via HTTP server."""
        response = requests.post(
            f"{self.server_url}/translate",
            json={"texts": [[text, lang] for text, lang in texts]},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("translations", {})


# ── Global client (for backward compatibility) ────────────────────────

_default_client: TranslationClient | None = None


def get_translation_client(
    server_url: str | None = None,
    timeout: float = 30.0,
    fallback_to_local: bool = True,
) -> TranslationClient:
    """Get or create the default translation client.

    If server_url is None, uses local translation only.
    """
    global _default_client
    if _default_client is None:
        if server_url:
            _default_client = TranslationClient(
                server_url=server_url,
                timeout=timeout,
                fallback_to_local=fallback_to_local,
            )
        else:
            # No server URL — use local translation
            _default_client = TranslationClient(
                server_url="http://invalid",
                fallback_to_local=True,
            )
    return _default_client


def reset_translation_client() -> None:
    """Reset the default translation client."""
    global _default_client
    _default_client = None
