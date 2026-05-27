"""Translation module using Argos Translate (offline).

Replaces Google Translate with local neural machine translation.
Supports all common European languages -> EN.
No API rate limits. No internet required after initial package download.

All source languages are known from data structure:
  - Descriptions: keys are language codes (fr, de, es, etc.)
  - Pricing: always French
  - Reviews: always French (Park4Night is a French site)
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import argostranslate.package as argos_package
import argostranslate.translate as argos_translate

logger = logging.getLogger("pipeline")

# ── Shared state ──────────────────────────────────────────────────────
_TRANSLATE_CACHE: dict[str, str] = {}
_PACKAGES_INITIALIZED = False
_PACKAGES_LOCK = threading.Lock()

# Source languages to install translation packages for (→ English).
REQUIRED_SOURCE_LANGUAGES = [
    "fr",  # French
    "de",  # German
    "es",  # Spanish
    "it",  # Italian
    "nl",  # Dutch
    "pt",  # Portuguese
    "pl",  # Polish
    "ru",  # Russian
    "sv",  # Swedish
    "da",  # Danish
    "nb",  # Norwegian (Bokmål)
    "fi",  # Finnish
    "cs",  # Czech
    "el",  # Greek
    "hu",  # Hungarian
    "ro",  # Romanian
    "bg",  # Bulgarian
    "sk",  # Slovak
    "sl",  # Slovenian
    "et",  # Estonian
    "lt",  # Lithuanian
    "lv",  # Latvian
    "uk",  # Ukrainian
    "tr",  # Turkish
    "sq",  # Albanian
    "ca",  # Catalan
    "gl",  # Galician
    "eu",  # Basque
    "ga",  # Irish
]


# ── Package management ────────────────────────────────────────────────


def _ensure_packages_installed() -> None:
    """Ensure all required language packages are installed.

    Downloads and installs missing language model packages on first run.
    Packages are cached locally after first download (~10-50MB each).
    Fails loudly if any required package cannot be installed.
    """
    global _PACKAGES_INITIALIZED

    with _PACKAGES_LOCK:
        if _PACKAGES_INITIALIZED:
            return

        logger.info("Checking argos-translate language packages...")

        # Update package index (lightweight JSON file)
        argos_package.update_package_index()

        # Get available and installed packages
        available_packages = argos_package.get_available_packages()
        installed_packages = argos_package.get_installed_packages()

        # Build set of installed source→en translations
        installed_pairs = {
            (pkg.from_code, pkg.to_code) for pkg in installed_packages if hasattr(pkg, "from_code")
        }

        # Install missing packages
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

        # Fail loudly if any required language has no available package
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


# ── Translation ───────────────────────────────────────────────────────


def _translate_single(text: str, src_lang: str) -> tuple[str, str]:
    """Translate a single text to English using argos-translate.

    Args:
        text: Text to translate.
        src_lang: ISO 639-1 source language code (e.g. 'fr', 'de').

    Returns (original, translated). Fails loudly on any error.
    """
    if not text or not text.strip():
        return (text, text)

    stripped = text.strip()

    # No translation needed if already English
    if src_lang == "en":
        return (text, stripped)

    # Check if translation model exists
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
    """Translate a batch of texts to English using parallel argos-translate calls.

    Args:
        texts: List of (text, src_lang) tuples.
        max_workers: Number of parallel threads.

    Returns {original_text: translated_text} for all inputs.
    Already-cached entries are returned immediately.
    Offline translation means no rate limits — can use high concurrency.
    """
    # Ensure packages are installed before any translation
    _ensure_packages_installed()

    # Filter out already-cached texts
    uncached = [(t, lang) for t, lang in texts if t not in _TRANSLATE_CACHE]

    if not uncached:
        return {t: _TRANSLATE_CACHE[t] for t, _ in texts}

    # Translate uncached texts in parallel
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_translate_single, text, lang): (text, lang)
            for text, lang in uncached
        }
        for future in as_completed(futures):
            original, translated = future.result()
            results[original] = translated

    # Update cache
    _TRANSLATE_CACHE.update(results)

    # Return results for all inputs (cached + newly translated)
    return {t: _TRANSLATE_CACHE[t] for t, _ in texts}


def translate_text(text: str, src_lang: str) -> str:
    """Translate a single text to English.

    Args:
        text: Text to translate.
        src_lang: ISO 639-1 source language code.

    Uses in-memory cache for repeated strings.
    Returns the original text if already English or empty.
    """
    if not text or not text.strip():
        return text

    stripped = text.strip()
    if stripped in _TRANSLATE_CACHE:
        return _TRANSLATE_CACHE[stripped]

    _, translated = _translate_single(stripped, src_lang)
    _TRANSLATE_CACHE[stripped] = translated
    return translated


def get_cache_size() -> int:
    """Return the number of entries in the translation cache."""
    return len(_TRANSLATE_CACHE)
