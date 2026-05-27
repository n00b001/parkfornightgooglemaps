#!/usr/bin/env python3
"""
Park4Night Data Normaliser

Reads scraped JSONL data (places.jsonl, reviews.jsonl), translates all text
to English as the default language (keeping original text available), deduplicates,
and outputs clean normalised JSONL files ready for upload.

Translation strategy:
  - If an English version exists (e.g. descriptions.en), use it directly
  - If no English version, translate from the source language using deep-translator
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
    uv run normalize.py
    uv run normalize.py --input-dir /path/to/data
    uv run normalize.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

# ── Translation ──────────────────────────────────────────────────────

# Lazy-import translator to avoid startup cost when --dry-run is used
_translator = None
_TRANSLATE_CACHE: dict[str, str] = {}
_TRANSLATE_LOCK: object = object()  # simple lock for single-process safety


def get_translator():
    """Lazy-initialise the translator."""
    global _translator
    if _translator is None:
        from deep_translator import MyMemoryTranslator

        _translator = MyMemoryTranslator(source="auto", target="en")
    return _translator


def translate_text(text: str, max_retries: int = 3) -> str:
    """
    Translate text to English. Uses cache to avoid repeated API calls.
    Returns original text if translation fails.
    """
    if not text or not text.strip():
        return text

    cached_key = text.strip()
    if cached_key in _TRANSLATE_CACHE:
        return _TRANSLATE_CACHE[cached_key]

    translator = get_translator()
    for attempt in range(max_retries):
        try:
            result = translator.translate(cached_key)
            if result and result.strip():
                _TRANSLATE_CACHE[cached_key] = result.strip()
                return result.strip()
            break
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))

    # Fallback: return original
    _TRANSLATE_CACHE[cached_key] = text.strip()
    return text.strip()


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
        # The top-level description is usually already English (scraper picks best)
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
            # Might be a foreign language term — try to translate
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
            place.get("is_public")
            or raw_access.get("public") in (True, "1", 1, "true")
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
        normalised_photos.append({
            "id": str(photo.get("id", "")),
            "numero": photo.get("numero"),
            "path_thumb": photo.get("path_thumb") or photo.get("url_thumb", ""),
            "path_large": photo.get("path_large") or photo.get("url_large", ""),
        })

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
        "rating": float(place["rating"]) if place.get("rating") is not None else None,
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
        # Park4Night reviews can be in any language.
        # We translate to English and keep the original.
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


def build_vehicle_types(
    places: list[dict], reviews: list[dict]
) -> list[dict]:
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


# ── Main pipeline ────────────────────────────────────────────────────

console = Console()


def setup_logging(log_dir: str) -> None:
    """Configure logging with dual output: console + log file."""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "normalize.log")

    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=False,
        markup=False,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler],
        format="%(message)s",
    )


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
                logging.warning(f"Skipping invalid JSON at {filepath}:{line_num}: {e}")
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
    """Write records to a JSONL file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(
    input_dir: str,
    output_dir: str,
    dry_run: bool = False,
) -> None:
    """Run the normalisation pipeline."""
    log_dir = os.path.join(input_dir, "..", "logs")
    setup_logging(log_dir)

    places_file = os.path.join(input_dir, "places.jsonl")
    reviews_file = os.path.join(input_dir, "reviews.jsonl")

    if not os.path.exists(places_file):
        console.print(f"[bold red]ERROR:[/bold red] Places file not found: {places_file}")
        sys.exit(1)

    # ── Load raw data ─────────────────────────────────────────────
    console.print("\n[bold blue]Loading scraped data...[/bold blue]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Loading places...", total=None)
        raw_places = load_jsonl(places_file)
        progress.update(task, completed=len(raw_places))
        logging.info(f"Loaded {len(raw_places)} raw place records")

    if os.path.exists(reviews_file):
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Loading reviews...", total=None)
            raw_reviews = load_jsonl(reviews_file)
            progress.update(task, completed=len(raw_reviews))
            logging.info(f"Loaded {len(raw_reviews)} raw review records")
    else:
        raw_reviews = []
        logging.info("No reviews file found, skipping")

    # ── Deduplicate places ────────────────────────────────────────
    console.print("\n[bold blue]Deduplicating places...[/bold blue]")
    unique_places = deduplicate_places(raw_places)
    logging.info(
        f"Deduplicated: {len(raw_places)} raw → {len(unique_places)} unique places"
    )
    console.print(
        f"  [cyan]{len(raw_places):,}[/cyan] raw records → "
        f"[bold green]{len(unique_places):,}[/bold green] unique places"
    )

    if dry_run:
        console.print("\n[bold yellow]=== DRY RUN — stopping here ===[/bold yellow]")
        return

    # ── Normalise places ──────────────────────────────────────────
    total_places = len(unique_places)

    console.print(f"\n[bold blue]Normalising {total_places:,} places...[/bold blue]")
    normalised_places: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TextColumn("[cyan]{task.fields[translated]} translated[/cyan]"),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Normalising places", total=total_places, translated=0)
        translation_count = 0

        for place in unique_places:
            normalised = normalise_place(place)
            if normalised:
                normalised_places.append(normalised)

            # Count translations (cache misses mean actual API calls)
            current_translations = len(_TRANSLATE_CACHE)
            if current_translations > translation_count:
                translation_count = current_translations
                progress.update(task, translated=translation_count)

            progress.advance(task)

    logging.info(f"Normalised {len(normalised_places)} places")
    logging.info(f"Translation cache: {len(_TRANSLATE_CACHE)} entries")

    # ── Normalise reviews ─────────────────────────────────────────
    total_reviews = len(raw_reviews)
    if total_reviews > 0:
        console.print(
            f"\n[bold blue]Normalising {total_reviews:,} reviews...[/bold blue]"
        )
        normalised_reviews: list[dict] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Normalising reviews", total=total_reviews)

            for review in raw_reviews:
                normalised = normalise_review(review)
                if normalised:
                    normalised_reviews.append(normalised)
                progress.advance(task)

        logging.info(f"Normalised {len(normalised_reviews)} reviews")
    else:
        normalised_reviews = []

    # ── Build lookup tables ───────────────────────────────────────
    console.print("\n[bold blue]Building lookup tables...[/bold blue]")

    place_types = build_place_types(normalised_places)
    services = build_services(normalised_places)
    activities = build_activities(normalised_places)
    vehicle_types = build_vehicle_types(normalised_places, normalised_reviews)

    logging.info(f"Place types: {len(place_types)}")
    logging.info(f"Services: {len(services)}")
    logging.info(f"Activities: {len(activities)}")
    logging.info(f"Vehicle types: {len(vehicle_types)}")

    # ── Write output files ────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)

    console.print(f"\n[bold blue]Writing output to {output_dir}...[/bold blue]")

    write_jsonl(normalised_places, os.path.join(output_dir, "places.jsonl"))
    console.print(f"  ✓ places.jsonl — [bold green]{len(normalised_places):,}[/bold green] records")

    write_jsonl(normalised_reviews, os.path.join(output_dir, "reviews.jsonl"))
    console.print(
        f"  ✓ reviews.jsonl — "
        f"[bold green]{len(normalised_reviews):,}[/bold green] records"
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

    # ── Summary ───────────────────────────────────────────────────
    total_size = sum(
        os.path.getsize(os.path.join(output_dir, f))
        for f in os.listdir(output_dir)
        if f.endswith(".jsonl")
    )

    console.print("\n[bold green]✓ Normalisation complete![/bold green]")
    console.print(f"  Output directory: [cyan]{output_dir}[/cyan]")
    console.print(
        f"  Total output size: [cyan]{total_size / (1024 * 1024):.1f} MB[/cyan]"
    )
    console.print(
        f"  Translation cache: [cyan]{len(_TRANSLATE_CACHE):,}[/cyan] entries"
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
        "--dry-run",
        action="store_true",
        help="Load and deduplicate data without translating or writing output",
    )

    args = parser.parse_args()

    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)

    console.print("\n[bold cyan]╔═══════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║   Park4Night Data Normaliser                      ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════════════════════════╝[/bold cyan]\n")

    console.print(f"  Input:  [cyan]{input_dir}[/cyan]")
    console.print(f"  Output: [cyan]{output_dir}[/cyan]")

    run(input_dir, output_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
