#!/usr/bin/env python3
"""
Park4Night Data Normaliser

Reads scraped JSONL data (places.jsonl, reviews.jsonl), translates all text
to English as the default language (keeping original text available), deduplicates,
and outputs clean normalised JSONL files ready for upload.

Translation strategy:
  - If an English version exists (e.g. descriptions.en), use it directly
  - If no English version, translate from the source language using argos-translate (offline)
  - All field names are already English (set by the scraper)
  - Field VALUES that may be in foreign languages: descriptions, review text,
    place titles, address fields, pricing values

Output:
  scripts/data/normalized/places.jsonl
  scripts/data/normalized/reviews.jsonl
  scripts/data/normalized/place_types.jsonl
  scripts/data/normalized/services.jsonl
  scripts/data/normalized/activities.jsonl
  scripts/data/normalized/vehicle_types.jsonl

Usage:
    # Full run:
    uv run normalize.py

    # Test with 10 places only:
    uv run normalize.py --limit 10

    # Custom paths:
    uv run normalize.py --input-dir /path/to/data --output-dir /path/to/output

    # Dry run (load + deduplicate, no translation):
    uv run normalize.py --dry-run

    # Pre-install translation packages (one-time setup):
    uv run normalize.py --setup
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

import argostranslate.package as argos_package
import argostranslate.translate as argos_translate
from langdetect import LangDetectException, detect
from rich.console import Console

# Suppress stanza MWT warnings (benign — stanza auto-adds MWT for languages
# that need it, e.g. Estonian. argostranslate 1.11.0 has a partial fix
# (get_stanza_processors) but doesn't call it in lazy_pipeline().
# See: https://github.com/argosopentech/argos-translate/issues/400
if importlib.util.find_spec("stanza") is not None:
    logging.getLogger("stanza").setLevel(logging.ERROR)
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

# ── Console & Logger ────────────────────────────────────────────────

# Force terminal rendering even when piped, and force unbuffered output
console = Console(force_terminal=True, soft_wrap=False)
logger: logging.Logger | None = None
# Track progress for log file writes
_progress_log_file: str = ""


def setup_logging(log_dir: str) -> str:
    """Configure logging with dual output: console + timestamped log file.

    Returns the path to the log file created.
    """
    global logger, _progress_log_file

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"normalize_{timestamp}.log")
    _progress_log_file = log_file

    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=False,
        markup=False,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger = logging.getLogger("normalize")
    logger.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    console.print(f"  Log file: [cyan]{log_file}[/cyan]")
    return log_file


def log_progress(phase: str, completed: int, total: int) -> None:
    """Write progress update to log file (visible while running)."""
    if logger and _progress_log_file:
        pct = (completed / total * 100) if total else 0
        logger.info(f"[{phase}] {completed:>8,}/{total:,} ({pct:5.1f}%)")


# ── Translation Engine ──────────────────────────────────────────────
# Uses argos-translate: offline, free, no API keys, no rate limits.
# Language model packages are downloaded once on first run and cached locally.


# Shared translation cache
_TRANSLATE_CACHE: dict[str, str] = {}
_PACKAGES_INITIALIZED = False
_PACKAGES_LOCK = threading.Lock()
# langdetect is not thread-safe - serialize all detection calls
_LANG_DETECT_LOCK = threading.Lock()

# Source languages to install translation packages for (→ English).
# Covers all common European languages found in Park4Night data.
# argos-translate code for Norwegian is "nb" (Bokmål).
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
]  # fmt: skip


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

        if logger:
            logger.info("Checking argos-translate language packages...")
        console.print("[bold blue]Checking translation packages...[/bold blue]")

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
                # Find matching package (some languages may use different codes)
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
                f"Run 'uv run normalize.py --setup' to install packages."
            )

        if packages_to_install:
            console.print(
                f"  [yellow]Installing {len(packages_to_install)} translation "
                f"packages (one-time, offline after download)...[/yellow]"
            )
            if logger:
                logger.info(f"Installing {len(packages_to_install)} translation packages")

            for lang_code, pkg in packages_to_install:
                console.print(f"  ⬇ Downloading {lang_code} → en...")
                if logger:
                    logger.info(f"Installing {lang_code} → en")
                download_path = pkg.download()
                argos_package.install_from_path(download_path)
                # Clean up downloaded file
                download_path.unlink(missing_ok=True)
        else:
            console.print("  [green]✓ All translation packages already installed[/green]")

        _PACKAGES_INITIALIZED = True


def _detect_language(text: str) -> str:
    """Detect the language of a text string.

    Returns ISO 639-1 language code (e.g. 'fr', 'de', 'en').
    Raises RuntimeError if detection fails.
    Thread-safe: uses lock since langdetect is not thread-safe.
    """
    with _LANG_DETECT_LOCK:
        try:
            lang = detect(text)
        except (LangDetectException, ValueError) as e:
            raise RuntimeError(f"Language detection failed for text: {text[:80]}... ({e})") from e
    # Normalize Norwegian codes
    if lang in ("no", "nn"):
        return "nb"
    return lang


def _translate_single(text: str) -> tuple[str, str]:
    """Translate a single text to English using argos-translate.

    Returns (original, translated). Fails loudly on any error.
    """
    if not text or not text.strip():
        return (text, text)

    stripped = text.strip()
    src_lang = _detect_language(stripped)

    # No translation needed if already English
    if src_lang == "en":
        return (text, stripped)

    translated = argos_translate.translate(stripped, from_code=src_lang, to_code="en")
    if not translated or not translated.strip():
        raise RuntimeError(f"Translation returned empty result ({src_lang}→en): {stripped[:80]}...")
    return (text, translated.strip())


def translate_batch(
    texts: list[str],
    max_workers: int = 8,
) -> dict[str, str]:
    """Translate a batch of texts to English using parallel argos-translate calls.

    Returns {original_text: translated_text} for all inputs.
    Already-cached entries are returned immediately.
    Offline translation means no rate limits — can use high concurrency.
    """
    # Ensure packages are installed before any translation
    _ensure_packages_installed()

    # Filter out already-cached and empty texts
    to_translate = [t for t in texts if t and t.strip() not in _TRANSLATE_CACHE]

    if not to_translate:
        return {t: _TRANSLATE_CACHE.get(t.strip(), t) for t in texts}

    results: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_translate_single, t): t for t in to_translate}
        for future in as_completed(futures):
            original, translated = future.result()
            key = original.strip() if original else original
            results[key] = translated
            _TRANSLATE_CACHE[key] = translated

    # Merge with cache for all inputs
    all_results: dict[str, str] = {}
    for t in texts:
        if not t or not t.strip():
            all_results[t] = t
        else:
            key = t.strip()
            all_results[t] = _TRANSLATE_CACHE.get(key, key)

    return all_results


def translate_text(text: str) -> str:
    """Translate a single text to English, using the shared cache.

    For fallback when a string wasn't in the batch (shouldn't happen normally).
    """
    if not text or not text.strip():
        return text
    key = text.strip()
    if key in _TRANSLATE_CACHE:
        return _TRANSLATE_CACHE[key]
    # Ensure packages are installed
    _ensure_packages_installed()
    # Cache miss — translate on demand
    _, translated = _translate_single(key)
    _TRANSLATE_CACHE[key] = translated
    return translated


# ── Language detection helpers ───────────────────────────────────────

LANG_PRIORITY = ["en", "fr", "de", "es", "it", "nl"]
"""Order to check for existing translations."""


def pick_or_translate(
    descriptions: dict[str, str],
    field_name: str = "description",
) -> dict[str, Any]:
    """
    Given a dict of {lang: text}, produce:
      {
        "default": "<English text>",
        "_original": {"fr": "...", "en": "...", ...},  # all originals
      }

    Strategy: pick English if available, otherwise translate the best available.
    Fails loudly if no translatable text is found.
    """
    originals = {lang: (text or "").strip() for lang, text in descriptions.items()}

    # Pick English text
    english_text = ""
    for lang in LANG_PRIORITY:
        candidate = originals.get(lang, "")
        if candidate:
            if lang == "en":
                english_text = candidate
                break
            else:
                # Need to translate this one
                english_text = translate_text(candidate)
                break

    if not english_text:
        # Last resort: use the first non-empty value
        for text in originals.values():
            if text:
                english_text = translate_text(text)
                break

    if not english_text:
        raise RuntimeError(f"No translatable text found for {field_name}: {descriptions}")

    return {
        "default": english_text,
        "_original": {k: v for k, v in originals.items() if v},
    }


# ── Normalisation functions ──────────────────────────────────────────


def normalise_place(place: dict) -> dict | None:
    """Normalise a single place record."""
    place_id = int(place.get("id", 0))
    if not place_id:
        return None

    # ── Title / Name ──────────────────────────────────────────────
    title = (place.get("title") or "").strip()
    name = (place.get("name") or "").strip()

    # ── Descriptions ──────────────────────────────────────────────
    raw_descriptions = place.get("descriptions", {})
    if not isinstance(raw_descriptions, dict):
        raw_descriptions = {}

    # Also consider the top-level 'description' field
    top_level_desc = (place.get("description") or "").strip()
    if top_level_desc and "en" not in (raw_descriptions or {}):
        raw_descriptions.setdefault("en", top_level_desc)

    descriptions = pick_or_translate(raw_descriptions, "description")

    # ── Type ──────────────────────────────────────────────────────
    raw_type = place.get("type", {})
    if isinstance(raw_type, dict):
        type_code = raw_type.get("code", "")
        type_label = raw_type.get("label", "")
    else:
        type_code = str(raw_type)
        type_label = ""

    # ── Address ───────────────────────────────────────────────────
    raw_address = place.get("address", {})
    if not isinstance(raw_address, dict):
        raw_address = {}

    address = {
        "street": (raw_address.get("street") or "").strip(),
        "city": (raw_address.get("city") or "").strip(),
        "zipcode": (raw_address.get("zipcode") or raw_address.get("code_postal") or "").strip(),
        "country": (raw_address.get("country") or "").strip(),
        "country_iso": (raw_address.get("country_iso") or "").strip(),
    }

    # ── Pricing ───────────────────────────────────────────────────
    raw_pricing = place.get("pricing", {})
    if not isinstance(raw_pricing, dict):
        raw_pricing = {}

    pricing = {}
    for key in ("parking", "services"):
        value = (raw_pricing.get(key) or "").strip().lower()
        # Translate common French pricing terms
        if value == "gratuit":
            value = "free"
        elif value == "payant":
            value = "paid"
        elif value == "sur demande":
            value = "on request"
        elif value and value not in ("free", "paid", "on request", ""):
            translated = translate_text(value)
            if translated.lower() != value.lower():
                value = translated.lower()
        pricing[key] = value

    # ── Access ────────────────────────────────────────────────────
    raw_access = place.get("access", {})
    if not isinstance(raw_access, dict):
        raw_access = {}

    access = {
        "public": bool(
            place.get("is_public") or raw_access.get("public") in (True, "1", 1, "true")
        ),
        "height_limit": (raw_access.get("height_limit") or "").strip(),
        "parking_places": (raw_access.get("parking_places") or "").strip(),
    }

    # ── Contact ───────────────────────────────────────────────────
    raw_contact = place.get("contact", {})
    if not isinstance(raw_contact, dict):
        raw_contact = {}

    contact = {
        "phone": (raw_contact.get("phone") or "").strip(),
        "email": (raw_contact.get("email") or "").strip(),
        "website": (raw_contact.get("website") or "").strip(),
        "video": (raw_contact.get("video") or "").strip(),
    }

    # ── Services & Activities (already English from scraper) ─────
    services = place.get("services", [])
    if not isinstance(services, list):
        services = []

    activities = place.get("activities", [])
    if not isinstance(activities, list):
        activities = []

    # ── Photos ────────────────────────────────────────────────────
    photos = place.get("photos", [])
    if not isinstance(photos, list):
        photos = []

    normalised_photos = []
    for photo in photos:
        if not isinstance(photo, dict):
            continue
        normalised_photos.append(
            {
                "id": str(photo.get("id", "")),
                "numero": photo.get("numero"),
                "path_thumb": photo.get("path_thumb") or photo.get("url_thumb", ""),
                "path_large": photo.get("path_large") or photo.get("url_large", ""),
            }
        )

    # ── Owner ─────────────────────────────────────────────────────
    raw_owner = place.get("owner", {})
    if not isinstance(raw_owner, dict):
        raw_owner = {}

    # ── Build normalised record ───────────────────────────────────
    return {
        "id": place_id,
        "title": title,
        "name": name,
        "descriptions": descriptions,
        "latitude": float(place.get("latitude") or 0),
        "longitude": float(place.get("longitude") or 0),
        "type_code": type_code,
        "type_label": type_label,
        "address": address,
        "pricing": pricing,
        "access": access,
        "contact": contact,
        "services": services,
        "activities": activities,
        "photos": normalised_photos,
        "rating": (float(place["rating"]) if place.get("rating") is not None else None),
        "review_count": int(place.get("review_count") or 0),
        "photo_count": int(place.get("photo_count") or len(normalised_photos)),
        "visit_count": int(place.get("visit_count") or 0),
        "is_public": access["public"],
        "is_protected_nature": bool(place.get("is_protected_nature")),
        "is_top_list": bool(place.get("is_top_list")),
        "online_booking": bool(place.get("online_booking")),
        "owner_username": (raw_owner.get("username") or "").strip(),
        "owner_user_id": (raw_owner.get("user_id") or "").strip(),
        "owner_vehicle_type": (raw_owner.get("vehicle_type") or "").strip(),
        "created_at": (place.get("created_at") or "").strip(),
        "closed_at": (place.get("closed_at") or "").strip(),
        "scraped_at": (place.get("scraped_at") or "").strip(),
    }


def normalise_review(review: dict) -> dict | None:
    """Normalise a single review record."""
    review_id = review.get("id")
    if not review_id:
        return None

    place_id = int(review.get("place_id", 0))
    if not place_id:
        return None

    # ── Review text — translate if not English ───────────────────
    raw_text = (review.get("text") or "").strip()
    if raw_text:
        translated = translate_text(raw_text)
        review_text = {
            "default": translated,
            "_original": raw_text,
        }
    else:
        review_text = {"default": "", "_original": ""}

    # ── Author ────────────────────────────────────────────────────
    author = {
        "name": (review.get("author") or "").strip(),
        "id": (review.get("author_id") or "").strip(),
        "vehicle_type": (review.get("vehicle_type") or "").strip(),
    }

    # ── Social links ──────────────────────────────────────────────
    social = review.get("social", {})
    if not isinstance(social, dict):
        social = {}

    return {
        "id": str(review_id),
        "place_id": place_id,
        "rating": int(review.get("rating") or 0),
        "text": review_text,
        "author": author,
        "social": {
            "website": (social.get("website") or "").strip(),
            "facebook": (social.get("facebook") or "").strip(),
            "twitter": (social.get("twitter") or "").strip(),
            "instagram": (social.get("instagram") or "").strip(),
            "youtube": (social.get("youtube") or "").strip(),
        },
        "created_at": (review.get("created_at") or "").strip(),
        "scraped_at": (review.get("scraped_at") or "").strip(),
    }


# ── Lookup table builders ────────────────────────────────────────────


def build_place_types(places: list[dict]) -> list[dict]:
    """Extract unique place types from all places."""
    seen: dict[str, dict] = {}
    for place in places:
        code = place.get("type_code", "")
        label = place.get("type_label", "")
        if code and code not in seen:
            seen[code] = {
                "code": code,
                "english_name": label or code,
                "original_code": code,
            }
    return list(seen.values())


def build_services(places: list[dict]) -> list[dict]:
    """Extract unique service codes from all places."""
    seen: dict[str, dict] = {}
    for place in places:
        for svc in place.get("services", []):
            if isinstance(svc, dict):
                code = svc.get("code", "")
                label = svc.get("label", "")
                if code and code not in seen:
                    seen[code] = {
                        "code": code,
                        "label": label or code,
                        "original_code": code,
                    }
    return list(seen.values())


def build_activities(places: list[dict]) -> list[dict]:
    """Extract unique activity codes from all places."""
    seen: dict[str, dict] = {}
    for place in places:
        for act in place.get("activities", []):
            if isinstance(act, dict):
                code = act.get("code", "")
                label = act.get("label", "")
                if code and code not in seen:
                    seen[code] = {
                        "code": code,
                        "label": label or code,
                        "original_code": code,
                    }
    return list(seen.values())


def build_vehicle_types(places: list[dict], reviews: list[dict]) -> list[dict]:
    """Extract unique vehicle type codes from places and reviews."""
    seen: dict[str, dict] = {}

    # From place owners
    for place in places:
        vt = place.get("owner_vehicle_type", "")
        if vt and vt not in seen:
            seen[vt] = {"code": vt, "original_code": vt}

    # From review authors
    for review in reviews:
        author = review.get("author", {})
        if isinstance(author, dict):
            vt = author.get("vehicle_type", "")
            if vt and vt not in seen:
                seen[vt] = {"code": vt, "original_code": vt}

    return list(seen.values())


# ── Checkpoint / Resume ──────────────────────────────────────────────

CHECKPOINT_FILENAME = "normalize_checkpoint.json"


def load_normalize_checkpoint(output_dir: str) -> dict:
    """Load normalisation checkpoint from output directory."""
    checkpoint_path = os.path.join(output_dir, CHECKPOINT_FILENAME)
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"normalised_place_ids": [], "version": 1}


def save_normalize_checkpoint(output_dir: str, place_ids: list[int]) -> None:
    """Save normalisation checkpoint."""
    checkpoint_path = os.path.join(output_dir, CHECKPOINT_FILENAME)
    checkpoint = {
        "normalised_place_ids": sorted(place_ids),
        "version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)


def get_new_places(unique_places: list[dict], output_dir: str) -> tuple[list[dict], list[int]]:
    """
    Determine which places need normalisation (not yet done).

    Returns:
        (new_places, already_normalised_ids)
    """
    checkpoint = load_normalize_checkpoint(output_dir)
    existing_ids = set(checkpoint.get("normalised_place_ids", []))

    if not existing_ids:
        return unique_places, []

    new_places = [p for p in unique_places if p["id"] not in existing_ids]
    skipped = [p["id"] for p in unique_places if p["id"] in existing_ids]

    return new_places, skipped


# ── Data I/O ─────────────────────────────────────────────────────────


def load_jsonl(filepath: str) -> list[dict]:
    """Load a JSONL file, returning list of dicts."""
    records = []
    if not os.path.exists(filepath):
        return records

    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                if logger:
                    logger.warning(f"Skipping invalid JSON at {filepath}:{line_num}: {e}")
    return records


def deduplicate_places(places: list[dict]) -> list[dict]:
    """Deduplicate places by ID, keeping the latest (by scraped_at)."""
    by_id: dict[int, dict] = {}
    for place in places:
        pid = place.get("id")
        if pid is None:
            continue
        if pid not in by_id:
            by_id[pid] = place
        else:
            existing_ts = by_id[pid].get("scraped_at", "")
            new_ts = place.get("scraped_at", "")
            if new_ts > existing_ts:
                by_id[pid] = place
    return list(by_id.values())


def write_jsonl(records: list[dict], filepath: str) -> None:
    """Write records to a JSONL file (overwrite mode)."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_jsonl(records: list[dict], filepath: str) -> None:
    """Append records to a JSONL file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Collect unique strings for batch translation ─────────────────────


def collect_strings_to_translate(places: list[dict], reviews: list[dict]) -> set[str]:
    """Collect all unique non-English strings that need translation."""
    strings: set[str] = set()

    for place in places:
        # Descriptions
        raw_desc = place.get("descriptions", {})
        if isinstance(raw_desc, dict):
            for lang, text in raw_desc.items():
                if lang != "en" and text and str(text).strip():
                    strings.add(str(text).strip())

        # Pricing values
        raw_pricing = place.get("pricing", {})
        if isinstance(raw_pricing, dict):
            for value in raw_pricing.values():
                val = (str(value) or "").strip().lower()
                if val and val not in (
                    "free",
                    "paid",
                    "on request",
                    "gratuit",
                    "payant",
                    "sur demande",
                ):
                    strings.add(val)

    for review in reviews:
        text = (review.get("text") or "").strip()
        if text:
            strings.add(text)

    return strings


# ── Main pipeline ────────────────────────────────────────────────────


def run(
    input_dir: str,
    output_dir: str,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    """Run the normalisation pipeline with resume support.

    On re-run, already-normalised places are skipped and only new places
    are processed. Lookup tables are rebuilt from all data (existing + new).
    """
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    setup_logging(log_dir)

    places_file = os.path.join(input_dir, "places.jsonl")
    reviews_file = os.path.join(input_dir, "reviews.jsonl")

    if not os.path.exists(places_file):
        console.print(f"[bold red]ERROR:[/bold red] Places file not found: {places_file}")
        sys.exit(1)

    # ── Load raw data ─────────────────────────────────────────────
    console.print("\n[bold blue]Loading scraped data...[/bold blue]")
    if logger:
        logger.info("Loading places.jsonl")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading places...", total=None)
        raw_places = load_jsonl(places_file)
        progress.update(task, completed=len(raw_places))
        if logger:
            logger.info(f"Loaded {len(raw_places):,} raw place records")

    if os.path.exists(reviews_file):
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Loading reviews...", total=None)
            raw_reviews = load_jsonl(reviews_file)
            progress.update(task, completed=len(raw_reviews))
            if logger:
                logger.info(f"Loaded {len(raw_reviews):,} raw review records")
    else:
        raw_reviews = []
        if logger:
            logger.info("No reviews file found, skipping")

    # ── Deduplicate places ────────────────────────────────────────
    console.print("\n[bold blue]Deduplicating places...[/bold blue]")
    unique_places = deduplicate_places(raw_places)
    if logger:
        logger.info(f"Deduplicated: {len(raw_places):,} raw → {len(unique_places):,} unique places")
    console.print(
        f"  [cyan]{len(raw_places):,}[/cyan] raw records → "
        f"[bold green]{len(unique_places):,}[/bold green] unique places"
    )

    # ── Resume: check for already-normalised places ───────────────
    existing_normalised_places = []
    existing_normalised_reviews = []

    if os.path.exists(os.path.join(output_dir, "places.jsonl")):
        existing_normalised_places = load_jsonl(os.path.join(output_dir, "places.jsonl"))
        if logger:
            logger.info(f"Found {len(existing_normalised_places):,} previously normalised places")

    if os.path.exists(os.path.join(output_dir, "reviews.jsonl")):
        existing_normalised_reviews = load_jsonl(os.path.join(output_dir, "reviews.jsonl"))
        if logger:
            logger.info(f"Found {len(existing_normalised_reviews):,} previously normalised reviews")

    # Determine which places are new
    existing_place_ids = {p["id"] for p in existing_normalised_places}
    new_places = [p for p in unique_places if p["id"] not in existing_place_ids]
    skipped_count = len(unique_places) - len(new_places)

    if skipped_count > 0:
        console.print(
            f"  [yellow]Skipping {skipped_count:,} already-normalised places "
            f"(resuming with {len(new_places):,} new places)[/yellow]"
        )
        if logger:
            logger.info(f"Resuming: {skipped_count:,} skipped, {len(new_places):,} new")

    # Filter reviews to only those for new places
    new_place_ids = {p["id"] for p in new_places}
    new_reviews = [r for r in raw_reviews if r.get("place_id") in new_place_ids]

    # ── Apply limit ───────────────────────────────────────────────
    if limit and limit > 0:
        # Limit applies to total (existing + new)
        total_target = limit
        remaining_slots = total_target - len(existing_normalised_places)
        if remaining_slots <= 0:
            console.print(f"  [yellow]Limit of {limit} already met by existing data.[/yellow]")
            new_places = []
            new_reviews = []
        else:
            new_places = new_places[:remaining_slots]
            new_place_ids = {p["id"] for p in new_places}
            new_reviews = [r for r in raw_reviews if r.get("place_id") in new_place_ids]
            console.print(
                f"  [yellow]Limited to {limit} total places "
                f"({len(existing_normalised_places)} existing + {len(new_places)} new)[/yellow]"
            )
            if logger:
                logger.info(f"Limit applied: {limit} total places")

    if dry_run:
        console.print("\n[bold yellow]=== DRY RUN — stopping here ===[/bold yellow]")
        return

    # ── Phase 1: Batch collect & translate all unique strings ─────
    if new_places or new_reviews:
        console.print("\n[bold blue]Phase 1: Collecting strings to translate...[/bold blue]")
        strings_to_translate = collect_strings_to_translate(new_places, new_reviews)
        # Remove already-cached
        strings_to_translate -= set(_TRANSLATE_CACHE.keys())

        if strings_to_translate:
            # Convert to sorted list for deterministic batching
            all_strings = sorted(strings_to_translate)
            total_strings = len(all_strings)
            console.print(f"  [cyan]{total_strings:,}[/cyan] unique strings to translate\n")

            # argos-translate is offline: no rate limits, crank up concurrency
            max_workers = 64
            batch_size = 500
            if logger:
                logger.info(
                    f"Batch translating {total_strings:,} unique strings "
                    f"(max_workers={max_workers}, batch_size={batch_size})"
                )
            total_batches = (total_strings + batch_size - 1) // batch_size

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("•"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Translating", total=total_strings)
                translated_count = 0

                for batch_num in range(0, total_batches):
                    start_idx = batch_num * batch_size
                    end_idx = min(start_idx + batch_size, total_strings)
                    batch = all_strings[start_idx:end_idx]

                    translate_batch(batch, max_workers=max_workers)
                    translated_count += len(batch)

                    progress.update(task, completed=translated_count)
                    # Log progress every 10 batches (~every 1000 strings)
                    if batch_num % 10 == 0:
                        log_progress("Translating", translated_count, total_strings)

            if logger:
                logger.info(f"Translation complete: {len(_TRANSLATE_CACHE):,} entries in cache")
        else:
            console.print("  [yellow]No strings to translate (all English or cached)[/yellow]")
    else:
        console.print("\n[yellow]No new places to translate.[/yellow]")

    # ── Phase 2: Normalise new places ────────────────────────────
    total_new_places = len(new_places)
    normalised_new_places: list[dict] = []

    if total_new_places > 0:
        console.print(
            f"\n[bold blue]Phase 2: Normalising {total_new_places:,} new places...[/bold blue]"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Normalising places", total=total_new_places)

            for i, place in enumerate(new_places):
                normalised = normalise_place(place)
                if normalised:
                    normalised_new_places.append(normalised)
                progress.advance(task)
                # Log progress every 5000 places
                if (i + 1) % 5000 == 0:
                    log_progress("Normalising places", i + 1, total_new_places)

        if logger:
            logger.info(f"Normalised {len(normalised_new_places):,} new places")
    else:
        console.print("\n[yellow]Phase 2: No new places to normalise.[/yellow]")

    # ── Phase 3: Normalise new reviews ───────────────────────────
    total_new_reviews = len(new_reviews)
    normalised_new_reviews: list[dict] = []

    if total_new_reviews > 0:
        console.print(
            f"\n[bold blue]Phase 3: Normalising {total_new_reviews:,} new reviews...[/bold blue]"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Normalising reviews", total=total_new_reviews)

            for i, review in enumerate(new_reviews):
                normalised = normalise_review(review)
                if normalised:
                    normalised_new_reviews.append(normalised)
                progress.advance(task)
                # Log progress every 50000 reviews
                if (i + 1) % 50000 == 0:
                    log_progress("Normalising reviews", i + 1, total_new_reviews)

        if logger:
            logger.info(f"Normalised {len(normalised_new_reviews):,} new reviews")
    else:
        console.print("\n[yellow]Phase 3: No new reviews to normalise.[/yellow]")

    # ── Merge existing + new data ────────────────────────────────
    all_normalised_places = existing_normalised_places + normalised_new_places
    all_normalised_reviews = existing_normalised_reviews + normalised_new_reviews

    # ── Phase 4: Build lookup tables (from ALL data) ─────────────
    console.print("\n[bold blue]Phase 4: Building lookup tables...[/bold blue]")

    place_types = build_place_types(all_normalised_places)
    services = build_services(all_normalised_places)
    activities = build_activities(all_normalised_places)
    vehicle_types = build_vehicle_types(all_normalised_places, all_normalised_reviews)

    if logger:
        logger.info(f"Place types: {len(place_types):,}")
        logger.info(f"Services: {len(services):,}")
        logger.info(f"Activities: {len(activities):,}")
        logger.info(f"Vehicle types: {len(vehicle_types):,}")

    # ── Phase 5: Write output files ──────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    console.print(f"\n[bold blue]Phase 5: Writing output to {output_dir}...[/bold blue]")

    write_jsonl(all_normalised_places, os.path.join(output_dir, "places.jsonl"))
    console.print(
        f"  ✓ places.jsonl — [bold green]{len(all_normalised_places):,}[/bold green] records"
    )

    write_jsonl(all_normalised_reviews, os.path.join(output_dir, "reviews.jsonl"))
    console.print(
        f"  ✓ reviews.jsonl — [bold green]{len(all_normalised_reviews):,}[/bold green] records"
    )

    write_jsonl(place_types, os.path.join(output_dir, "place_types.jsonl"))
    console.print(f"  ✓ place_types.jsonl — [bold green]{len(place_types):,}[/bold green] records")

    write_jsonl(services, os.path.join(output_dir, "services.jsonl"))
    console.print(f"  ✓ services.jsonl — [bold green]{len(services):,}[/bold green] records")

    write_jsonl(activities, os.path.join(output_dir, "activities.jsonl"))
    console.print(f"  ✓ activities.jsonl — [bold green]{len(activities):,}[/bold green] records")

    write_jsonl(vehicle_types, os.path.join(output_dir, "vehicle_types.jsonl"))
    console.print(
        f"  ✓ vehicle_types.jsonl — [bold green]{len(vehicle_types):,}[/bold green] records"
    )

    # ── Save checkpoint ──────────────────────────────────────────
    all_place_ids = [p["id"] for p in all_normalised_places]
    save_normalize_checkpoint(output_dir, all_place_ids)
    if logger:
        logger.info(f"Checkpoint saved: {len(all_place_ids):,} normalised place IDs")

    # ── Summary ───────────────────────────────────────────────────
    total_size = sum(
        os.path.getsize(os.path.join(output_dir, f))
        for f in os.listdir(output_dir)
        if f.endswith(".jsonl")
    )

    console.print("\n[bold green]✓ Normalisation complete![/bold green]")
    console.print(f"  Output directory: [cyan]{output_dir}[/cyan]")
    console.print(f"  Total output size: [cyan]{total_size / (1024 * 1024):.1f} MB[/cyan]")
    console.print(f"  Translation cache: [cyan]{len(_TRANSLATE_CACHE):,}[/cyan] entries")

    if logger:
        logger.info(
            f"Output: {total_size / (1024 * 1024):.1f} MB, "
            f"{len(_TRANSLATE_CACHE):,} translations cached"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalise scraped Park4Night data into clean tables"
    )
    parser.add_argument(
        "--input-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data"),
        help="Directory containing scraped places.jsonl and reviews.jsonl (default: ../data)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "normalized"),
        help="Directory for normalised output (default: ../data/normalized)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N places (and their reviews) for testing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and deduplicate data without translating or writing output",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Install translation language packages and exit (no normalisation)",
    )

    args = parser.parse_args()

    # Handle --setup: install packages and exit
    if args.setup:
        console.print("\n[bold cyan]╔═══════════════════════════════════════════╗[/bold cyan]")
        console.print("[bold cyan]║   Park4Night Translation Setup             ║[/bold cyan]")
        console.print("[bold cyan]╚═══════════════════════════════════════════╝[/bold cyan]\n")
        _ensure_packages_installed()
        console.print("\n[bold green]✓ Setup complete![/bold green]")
        return

    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)

    console.print("\n[bold cyan]╔═══════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║   Park4Night Data Normaliser                      ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════════════════════════╝[/bold cyan]\n")

    console.print(f"  Input:  [cyan]{input_dir}[/cyan]")
    console.print(f"  Output: [cyan]{output_dir}[/cyan]")
    if args.limit:
        console.print(f"  Limit:  [yellow]{args.limit} places[/yellow]")

    run(input_dir, output_dir, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
