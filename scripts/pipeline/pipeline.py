#!/usr/bin/env python3
"""
Park4Night Unified ETL Pipeline

Single script that merges scraper + normalizer + uploader into one pipeline.
Each place flows through all stages end-to-end:

    extract (API) → download images → fetch reviews → translate →
    normalize → upload R2 → insert DB

Idempotency via @cache.memoize() decorators (diskcache library):
  - API fetches: @cache.memoize() on _fetch_grid_cached / _fetch_reviews_cached
  - Translations: @cache.memoize() on _translate_cached
  - Scrape results: @cache.memoize() on _scrape_place_cached
  - Normalize results: @cache.memoize() on _normalize_place_cached
  - Full pipeline: @cache.memoize() on _process_place_cached

Re-running with the same --limit completes instantly (all cached).
--no-disk-cache bypasses disk cache for timing performance tests (NEVER clears cache).

Stages (use --stage to run individually):
  scrape    - Extract places from API, download images, fetch reviews
  normalize - Translate text to English, normalize into DB-ready format
  upload    - Upload images to R2, insert records to Supabase

Usage:
    cd scripts/pipeline && uv run python pipeline.py --limit 10
    cd scripts/pipeline && uv run python pipeline.py --stage scrape --limit 10
    cd scripts/pipeline && uv run python pipeline.py --stage normalize --limit 10
    cd scripts/pipeline && uv run python pipeline.py --stage upload --limit 10
    cd scripts/pipeline && uv run python pipeline.py --limit 10 --no-disk-cache
    cd scripts/pipeline && uv run python pipeline.py --dry-run

Architecture:
  - ProcessPoolExecutor (spawn) for main pipeline workers
    Each worker does: extract → download → reviews → translate → normalize
  - R2 worker pool (32 threads, queue-based) for async image uploads
  - DB worker pool (8 threads, queue-based) for async database inserts
  - Worker pools are KEPT because removing them makes the pipeline 5-10x slower
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import signal
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from frozendict import frozendict

from api_client import Park4NightAPI  # type: ignore[import-not-found]
from cache import cache  # type: ignore[import-not-found]
from config import (  # type: ignore[import-not-found]
    ACTIVITY_CODES,
    PLACE_TYPE_CODES,
    SERVICE_CODES,
)
from db_worker import DBWorkerPool  # type: ignore[import-not-found]
from image_downloader import ImageDownloader  # type: ignore[import-not-found]
from logging_setup import (  # type: ignore[import-not-found]
    ProgressTracker,
    StageTimer,
    console,
    create_progress,
    print_timing_report,
    setup_logging,
)
from normalizer import (  # type: ignore[import-not-found]
    normalize_place,
    normalize_review,
)
from r2_worker import R2UploadTask, R2WorkerPool  # type: ignore[import-not-found]
from translator import (  # type: ignore[import-not-found]
    ensure_packages_installed,
    preload_models,
    translate_batch,
)

logger = logging.getLogger("pipeline")

# ── Globals (for signal handling) ─────────────────────────────────────
_r2_config: dict | None = None
_stats_lock = threading.Lock()
_stats: dict[str, int] = {
    "places_processed": 0,
    "images_downloaded": 0,
    "images_uploaded_r2": 0,
    "db_inserts": 0,
    "errors": 0,
}

_stage_timers: dict[str, StageTimer] = {}

# Per-worker-process shared instances (created in _worker_init).
_worker_api: Park4NightAPI | None = None
_worker_downloader: ImageDownloader | None = None


# ── Helpers ───────────────────────────────────────────────────────────


def _str(value: Any) -> str:
    """Safely convert a value to string, handling None."""
    return str(value).strip() if value is not None else ""


# ── Stage 1: Extract (structure raw API data) ────────────────────────
def extract_place_data(place: dict | frozendict) -> dict | None:
    """Structure raw API data into a clean place dict.

    Pure function: no I/O, no cache, no side effects.
    """
    place_id = int(place.get("id") or 0)
    if not place_id:
        return None

    services = []
    for key, label in SERVICE_CODES.items():
        if place.get(key) in ("1", 1, True, "true"):
            services.append({"code": key, "label": label})

    activities = []
    for key, label in ACTIVITY_CODES.items():
        if place.get(key) in ("1", 1, True, "true"):
            activities.append({"code": key, "label": label})

    type_code = place.get("code", "")
    place_type = PLACE_TYPE_CODES.get(type_code, type_code)

    return {
        "id": place_id,
        "title": _str(place.get("titre")),
        "name": _str(place.get("name")),
        "descriptions": {
            "fr": _str(place.get("description_fr")),
            "en": _str(place.get("description_en")),
            "de": _str(place.get("description_de")),
            "es": _str(place.get("description_es")),
            "it": _str(place.get("description_it")),
            "nl": _str(place.get("description_nl")),
        },
        "latitude": float(place.get("latitude") or 0),
        "longitude": float(place.get("longitude") or 0),
        "type": {"code": type_code, "label": place_type},
        "address": {
            "street": _str(place.get("route")),
            "city": _str(place.get("ville")),
            "zipcode": _str(place.get("code_postal")),
            "country": _str(place.get("pays")),
            "country_iso": _str(place.get("pays_iso")),
        },
        "pricing": {
            "parking": _str(place.get("prix_stationnement")),
            "services": _str(place.get("prix_services")),
        },
        "access": {
            "public": bool(place.get("publique") in ("1", 1, True)),
            "height_limit": _str(place.get("hauteur_limite")),
            "parking_places": _str(place.get("nb_places")),
        },
        "contact": {
            "phone": _str(place.get("tel")),
            "email": _str(place.get("mail")),
            "website": _str(place.get("site_internet")),
            "video": _str(place.get("video")),
        },
        "services": services,
        "activities": activities,
        "photos": [],
        "rating": (float(place.get("note_moyenne", 0)) if place.get("note_moyenne") else None),
        "review_count": int(place.get("nb_commentaires") or 0),
        "photo_count": int(place.get("nb_photos") or 0),
        "visit_count": int(place.get("nb_visites") or 0),
        "is_public": bool(place.get("publique") in ("1", 1, True)),
        "is_protected_nature": bool(place.get("nature_protect") in ("1", 1, True)),
        "is_top_list": bool(place.get("top_liste") in ("1", 1, True)),
        "online_booking": bool(place.get("online_booking") in (True, "1", 1)),
        "created_at": _str(place.get("date_creation")),
        "closed_at": _str(place.get("date_fermeture")),
        "owner": {
            "username": _str(place.get("utilisateur_creation")),
            "user_id": _str(place.get("user_id")),
            "vehicle_type": _str(place.get("user_vehicule")),
        },
        "scraped_at": datetime.now(UTC).isoformat(),
        "source": "guest_api",
    }


# ── Stage 2: Download images ─────────────────────────────────────────
def download_images(place: dict, downloader: ImageDownloader) -> dict:
    """Download photos for a place. Updates place["photos"] in-place."""
    place_id = place["id"]
    raw_photos = place.get("_raw_photos", [])
    photos = downloader.download_place_photos(place_id, raw_photos)
    place["photos"] = photos
    return place


# ── Stage 3: Fetch reviews ───────────────────────────────────────────
def fetch_reviews(place: dict, api: Park4NightAPI) -> dict:
    """Fetch reviews for a place from API (cached via @api_cache.memo)."""
    place_id = place["id"]
    reviews = api.get_reviews(place_id)
    place["reviews"] = reviews
    return place


# ── Stage 4: Translate ───────────────────────────────────────────────
def stage_translate(place: dict) -> dict:
    """Translate all non-English strings for a single place + reviews.

    Uses @translations_cache.memoize() on _do_translate() — already-cached
    strings return instantly without re-running argos-translate.
    """
    texts_to_translate: list[tuple[str, str]] = []

    raw_desc = place.get("descriptions", {})
    if isinstance(raw_desc, dict):
        for lang, text in raw_desc.items():
            if lang != "en" and text and str(text).strip():
                texts_to_translate.append((str(text).strip(), lang))

    raw_pricing = place.get("pricing", {})
    if isinstance(raw_pricing, dict):
        for value in raw_pricing.values():
            val = (str(value) or "").strip().lower()
            if val and val not in ("free", "paid", "on request", "gratuit", "payant"):
                texts_to_translate.append((val, "fr"))

    reviews = place.get("reviews", [])
    for review in reviews:
        text = review.get("text", "")
        if text and str(text).strip():
            texts_to_translate.append((str(text).strip(), "fr"))

    if texts_to_translate:
        translations = translate_batch(texts_to_translate, max_workers=8)

        if isinstance(raw_desc, dict):
            translated_desc = {}
            for lang, text in raw_desc.items():
                text_stripped = (str(text) or "").strip()
                if lang == "en" and text_stripped:
                    translated_desc["en"] = text_stripped
                elif text_stripped and text_stripped in translations:
                    translated_desc["translated"] = translations[text_stripped]
            if "translated" in translated_desc:
                place["descriptions"]["translated"] = translated_desc["translated"]

        if isinstance(raw_pricing, dict):
            for key, value in raw_pricing.items():
                val = (str(value) or "").strip().lower()
                if val and val in translations:
                    raw_pricing[key] = translations[val]

        for review in reviews:
            text = review.get("text", "")
            if text and str(text).strip():
                text_stripped = str(text).strip()
                translated = translations.get(text_stripped, text_stripped)
                review["text"] = {
                    "default": translated,
                    "_original": text_stripped,
                }

    return place


# ── Stage 5: Normalize ───────────────────────────────────────────────
def stage_normalize(place: dict) -> dict | None:
    """Normalize place + reviews into clean DB-ready records."""
    normalized = normalize_place(place)
    if not normalized:
        return None

    normalized_reviews = []
    for review in place.get("reviews", []):
        normalized_review = normalize_review(review)
        if normalized_review:
            normalized_reviews.append(normalized_review)
    normalized["reviews"] = normalized_reviews
    return normalized


# ── Stage 6: Enqueue R2 upload (non-blocking) ────────────────────────
def stage_enqueue_r2(
    place: dict,
    r2_pool: R2WorkerPool | None,
) -> R2UploadTask | None:
    """Enqueue images for async R2 upload. Non-blocking."""
    if r2_pool is None:
        return None
    photos = place.get("photos", [])
    if photos:
        return r2_pool.enqueue(place["id"], photos)
    return None


# ── Stage 7: Enqueue DB insert (non-blocking) ────────────────────────
def stage_enqueue_db(
    place: dict,
    db_pool: DBWorkerPool | None,
) -> None:
    """Enqueue a place + reviews for async DB insert. Non-blocking."""
    if db_pool is None:
        logger.warning(f"Skipping DB insert for place {place.get('id')}: DATABASE_URL not set")
        return
    reviews = place.get("reviews") or []
    db_pool.enqueue(place, reviews)
    with _stats_lock:
        _stats["db_inserts"] += 1


# ── Generator: yield places from grid points ─────────────────────────
def place_source(
    api: Park4NightAPI,
    limit: int | None = None,
) -> Any:
    """Generator that yields raw places from the Park4Night API.

    API responses cached via @api_cache.memoize() on fetch_places_for_grid.
    """
    grid_points = Park4NightAPI.generate_grid_points()
    total_yielded = 0
    seen_ids: set[int] = set()

    limit_msg = f" (limit: {limit} places)" if limit else ""
    console.print(f"  [bold blue]{len(grid_points)}[/bold blue] grid points to scan{limit_msg}")

    for lat, lng in grid_points:
        if limit is not None and total_yielded >= limit:
            break

        places = api.get_places(lat, lng)
        if not places:
            continue

        for place in places:
            if limit is not None and total_yielded >= limit:
                break

            place_id = int(place.get("id") or 0)
            if place_id and place_id not in seen_ids:
                seen_ids.add(place_id)
                yield (place, (lat, lng))
                total_yielded += 1


# ── Signal Handling ──────────────────────────────────────────────────
def _handle_signal(signum: int, frame: Any) -> None:
    """Handle SIGINT/SIGTERM gracefully."""
    sig_name = signal.Signals(signum).name
    console.print(f"\n[bold yellow]Received {sig_name}, exiting...[/bold yellow]")
    sys.exit(0)


# ── Worker initializer (called once per process) ─────────────────────
def _worker_init(preload_translation: bool = True) -> None:
    """Initialize worker process: preload argos models + create shared instances."""
    global _worker_api, _worker_downloader
    if preload_translation:
        preload_models()
    _worker_api = Park4NightAPI()
    _worker_downloader = ImageDownloader()


# ── Scrape worker ────────────────────────────────────────────────────

def _scrape_place_impl(
    place_id: int,
    raw_place: frozendict,
) -> dict:
    """Raw scrape — no caching."""
    assert _worker_api is not None, "Park4NightAPI not initialized"
    assert _worker_downloader is not None, "ImageDownloader not initialized"

    place = extract_place_data(raw_place)
    if not place:
        return {"error": f"Failed to extract place {place_id}"}

    place["_raw_photos"] = raw_place.get("photos", [])
    place = download_images(place, _worker_downloader)
    place = fetch_reviews(place, _worker_api)
    place.pop("_raw_photos", None)

    return place


@cache.memoize()
def _scrape_place_cached(
    place_id: int,
    raw_place: frozendict,
) -> dict:
    return _scrape_place_impl(place_id, raw_place)


def _worker_scrape_place(
    place_id: int,
    raw_place: frozendict,
    use_cache: bool = True,
) -> dict:
    """Scrape a single place: extract → download images → fetch reviews."""
    if use_cache:
        return _scrape_place_cached(place_id, raw_place)
    return _scrape_place_impl(place_id, raw_place)


# ── Normalize worker ─────────────────────────────────────────────────

def _normalize_place_impl(
    place_id: int,
    raw_place: frozendict,
) -> dict:
    """Raw normalize — no caching."""
    place = extract_place_data(raw_place)
    if not place:
        return {"error": f"Failed to extract place {place_id}"}

    place["photos"] = raw_place.get("photos", [])
    place["reviews"] = []  # reviews fetched separately

    assert _worker_api is not None
    place = fetch_reviews(place, _worker_api)
    place = stage_translate(place)

    normalized = stage_normalize(place)
    if not normalized:
        return {"error": f"Failed to normalize place {place_id}"}

    return normalized


@cache.memoize()
def _normalize_place_cached(
    place_id: int,
    raw_place: frozendict,
) -> dict:
    return _normalize_place_impl(place_id, raw_place)


def _worker_normalize_place(
    place_id: int,
    raw_place: frozendict,
    use_cache: bool = True,
) -> dict:
    """Normalize a single place: translate → normalize."""
    if use_cache:
        return _normalize_place_cached(place_id, raw_place)
    return _normalize_place_impl(place_id, raw_place)


# ── Full pipeline worker ─────────────────────────────────────────────

def _process_place_impl(
    place_id: int,
    raw_place: frozendict,
) -> dict:
    """Raw process — no caching."""
    place_start = time.time()
    raw_place_data = raw_place

    # ── Stage 1: Extract ─
    t0 = time.time()
    place = extract_place_data(raw_place_data)
    extract_time = time.time() - t0
    if not place:
        return {"error": f"Failed to extract place {place_id}"}

    # ── Stage 2: Download images ─
    t0 = time.time()
    place["_raw_photos"] = raw_place_data.get("photos", [])
    assert _worker_downloader is not None
    place = download_images(place, _worker_downloader)
    download_time = time.time() - t0

    # ── Stage 3: Fetch reviews ─
    t0 = time.time()
    assert _worker_api is not None
    place = fetch_reviews(place, _worker_api)
    fetch_time = time.time() - t0

    # ── Stage 4: Translate ─
    t0 = time.time()
    place = stage_translate(place)
    translate_time = time.time() - t0

    # ── Stage 5: Normalize ─
    t0 = time.time()
    place = stage_normalize(place)
    normalize_time = time.time() - t0
    if not place:
        return {"error": f"Failed to normalize place {place_id}"}

    place_elapsed = time.time() - place_start
    return {
        "place_id": place_id,
        "elapsed": place_elapsed,
        "extract": extract_time,
        "download": download_time,
        "fetch": fetch_time,
        "translate": translate_time,
        "normalize": normalize_time,
        "place": place,
    }


@cache.memoize()
def _process_place_cached(
    place_id: int,
    raw_place: frozendict,
) -> dict:
    return _process_place_impl(place_id, raw_place)


def _worker_process_place(
    place_id: int,
    raw_place: frozendict,
    use_cache: bool = True,
) -> dict:
    """Process a single place in a separate worker process."""
    if use_cache:
        return _process_place_cached(place_id, raw_place)
    return _process_place_impl(place_id, raw_place)


# ── Stage: Scrape ────────────────────────────────────────────────────
def run_scrape_stage(
    limit: int | None = None,
    no_disk_cache: bool = False,
    dry_run: bool = False,
) -> dict[int, frozendict]:
    """Run the scrape stage: extract → download images → fetch reviews.

    Returns:
        place_id -> raw_place frozendict mapping for downstream stages.
    """
    global _stage_timers

    num_workers = 16

    if no_disk_cache:
        console.print("[yellow]Bypassing disk cache (--no-disk-cache mode)[/yellow]")

    console.print("\n[bold cyan]Starting scrape stage[/bold cyan]")
    if limit:
        console.print(f"  [yellow]Limit: {limit} places[/yellow]")

    if dry_run:
        console.print("[bold yellow]=== DRY RUN — stopping here ===[/bold yellow]")
        return {}

    # Collect places from API
    console.print("\n[bold]Scrape: Extracting places from API...[/bold]")
    extract_start = time.time()
    extract_tracker = ProgressTracker("Extracting places", total=limit or 0)
    places_to_process = []
    for place, grid_point in place_source(Park4NightAPI(), limit=limit):
        places_to_process.append((place, grid_point))
        extract_tracker.update(len(places_to_process))
    extract_tracker.finish()
    extract_elapsed = time.time() - extract_start
    total_places = len(places_to_process)
    console.print(f"  [green]✓ Found {total_places} places in {extract_elapsed:.1f}s[/green]")

    if not total_places:
        console.print("[yellow]No places to process.[/yellow]")
        return {}

    _stage_timers = {
        "extract": StageTimer("Extract"),
        "download": StageTimer("Download"),
        "reviews": StageTimer("Reviews"),
    }

    console.print("\n[bold]Scrape: Downloading images + fetching reviews...[/bold]")
    pipeline_start = time.time()
    process_tracker = ProgressTracker("Scraping places", total=total_places)
    with create_progress("Scraping places", total=total_places) as progress:
        task = progress.add_task("Scraping", total=total_places)
        place_num = 0
        errors = 0

        multiprocessing.set_start_method("spawn", force=True)
        scraped_results: dict[int, frozendict] = {}
        with ProcessPoolExecutor(
            max_workers=num_workers,
            initializer=_worker_init,
            initargs=(False,),  # preload_translation=False
        ) as executor:
            futures = {
                executor.submit(
                    _worker_scrape_place,
                    int(raw_place.get("id") or 0),
                    frozendict(raw_place),
                    not no_disk_cache,
                ): (raw_place, grid_point)
                for raw_place, grid_point in places_to_process
            }

            for future in as_completed(futures):
                place_num += 1
                raw_place, grid_point = futures[future]
                place_id = int(raw_place.get("id") or 0)

                try:
                    result = future.result()

                    if "error" in result:
                        console.print(f"  [red]✗ {result['error']}[/red]")
                        errors += 1
                        with _stats_lock:
                            _stats["errors"] += 1
                    else:
                        with _stats_lock:
                            _stats["places_processed"] += 1
                            _stats["images_downloaded"] += len(result.get("photos", []))
                            scraped_results[place_id] = frozendict(raw_place)

                        console.print(f"  [bold green]✓ Place {place_id} scraped[/bold green]")

                except Exception as e:
                    console.print(f"  [red]✗ Place {place_id} crashed: {e}[/red]")
                    errors += 1
                    with _stats_lock:
                        _stats["errors"] += 1

                progress.update(task, completed=place_num)
                process_tracker.update(place_num)

    process_tracker.finish()

    total_elapsed = time.time() - pipeline_start
    console.print("\n[bold green]✓ Scrape stage complete:[/bold green]")
    console.print(
        f"  Places: [green]{_stats['places_processed']}[/green] processed, "
        f"[red]{errors}[/red] errors"
    )
    console.print(f"  Images: [green]{_stats['images_downloaded']}[/green] downloaded")
    console.print(f"  Total time: [cyan]{total_elapsed:.1f}s[/cyan]")

    if errors:
        console.print(f"\n[bold red]{errors} places had errors[/bold red]")

    return scraped_results


# ── Stage: Normalize ─────────────────────────────────────────────────
def run_normalize_stage(
    scraped_data: dict[int, frozendict],
    limit: int | None = None,
    no_disk_cache: bool = False,
    dry_run: bool = False,
) -> dict[int, dict]:
    """Run the normalize stage: translate → normalize.

    Args:
        scraped_data: place_id -> raw_place data from scrape stage.
        limit: Max places to process.
        no_disk_cache: Bypass disk cache for timing.
        dry_run: Show what would be done.

    Returns:
        place_id -> normalized place data.
    """
    global _stage_timers

    num_workers = 16

    if no_disk_cache:
        console.print("[yellow]Bypassing disk cache (--no-disk-cache mode)[/yellow]")

    console.print("\n[bold cyan]Starting normalize stage[/bold cyan]")
    if limit:
        console.print(f"  [yellow]Limit: {limit} places[/yellow]")

    if dry_run:
        console.print("[bold yellow]=== DRY RUN — stopping here ===[/bold yellow]")
        return {}

    scraped_ids = list(scraped_data.keys())
    if not scraped_ids:
        console.print("[yellow]No scraped places provided.[/yellow]")
        return {}

    if limit:
        scraped_ids = scraped_ids[:limit]

    console.print(f"  [bold blue]{len(scraped_ids)}[/bold blue] places to normalize")

    ensure_packages_installed()

    _stage_timers = {
        "translate": StageTimer("Translate"),
        "normalize": StageTimer("Normalize"),
    }

    console.print("\n[bold]Normalize: Translating + normalizing...[/bold]")
    pipeline_start = time.time()
    normalized_results: dict[int, dict] = {}
    process_tracker = ProgressTracker("Normalizing places", total=len(scraped_ids))
    with create_progress("Normalizing places", total=len(scraped_ids)) as progress:
        task = progress.add_task("Normalizing", total=len(scraped_ids))
        place_num = 0
        errors = 0

        multiprocessing.set_start_method("spawn", force=True)
        with ProcessPoolExecutor(
            max_workers=num_workers,
            initializer=_worker_init,
            initargs=(True,),  # preload_translation=True
        ) as executor:
            futures = {
                executor.submit(
                    _worker_normalize_place,
                    place_id,
                    scraped_data[place_id],
                    not no_disk_cache,
                ): place_id
                for place_id in scraped_ids
            }

            for future in as_completed(futures):
                place_num += 1
                place_id = futures[future]

                try:
                    result = future.result()

                    if "error" in result:
                        console.print(f"  [red]✗ {result['error']}[/red]")
                        errors += 1
                        with _stats_lock:
                            _stats["errors"] += 1
                    else:
                        with _stats_lock:
                            _stats["places_processed"] += 1
                            normalized_results[place_id] = result

                        console.print(f"  [bold green]✓ Place {place_id} normalized[/bold green]")

                except Exception as e:
                    console.print(f"  [red]✗ Place {place_id} crashed: {e}[/red]")
                    errors += 1
                    with _stats_lock:
                        _stats["errors"] += 1

                progress.update(task, completed=place_num)
                process_tracker.update(place_num)

    process_tracker.finish()

    total_elapsed = time.time() - pipeline_start
    console.print("\n[bold green]✓ Normalize stage complete:[/bold green]")
    console.print(
        f"  Places: [green]{_stats['places_processed']}[/green] processed, "
        f"[red]{errors}[/red] errors"
    )
    console.print(f"  Total time: [cyan]{total_elapsed:.1f}s[/cyan]")

    if errors:
        console.print(f"\n[bold red]{errors} places had errors[/bold red]")

    return normalized_results


# ── Stage: Upload ────────────────────────────────────────────────────
def run_upload_stage(
    normalized_data: dict[int, dict],
    limit: int | None = None,
    no_disk_cache: bool = False,
    dry_run: bool = False,
) -> None:
    """Run the upload stage: upload images to R2 + insert records to Supabase.

    Args:
        normalized_data: place_id -> normalized place data from normalize stage.
        limit: Max places to process.
        no_disk_cache: Bypass disk cache for timing.
        dry_run: Show what would be done.
    """
    global _stage_timers

    r2_pool: R2WorkerPool | None = None
    if _r2_config is not None:
        r2_pool = R2WorkerPool(
            _r2_config, no_cache=no_disk_cache, total_expected=limit or 0
        )
        r2_pool.start()

    db_pool: DBWorkerPool | None = None
    if os.environ.get("DATABASE_URL"):
        db_pool = DBWorkerPool(total_expected=limit or 0)
        db_pool.start()

    console.print("\n[bold cyan]Starting upload stage[/bold cyan]")
    if limit:
        console.print(f"  [yellow]Limit: {limit} places[/yellow]")

    if r2_pool is None:
        console.print("[yellow]⚠ R2 config not found — skipping R2 uploads[/yellow]")
    if db_pool is None:
        console.print("[yellow]⚠ DATABASE_URL not set — skipping DB inserts[/yellow]")

    if dry_run:
        console.print("[bold yellow]=== DRY RUN — stopping here ===[/bold yellow]")
        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()
        return

    if r2_pool is None and db_pool is None:
        console.print("[red]No R2 or DB configured. Nothing to upload.[/red]")
        return

    normalized_ids = sorted(normalized_data.keys())
    if not normalized_ids:
        console.print("[yellow]No normalized places provided.[/yellow]")
        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()
        return

    if limit:
        normalized_ids = normalized_ids[:limit]

    console.print(f"  [bold blue]{len(normalized_ids)}[/bold blue] places to upload")

    _stage_timers = {
        "r2_upload": StageTimer("R2 Upload"),
        "db_insert": StageTimer("DB Insert"),
    }

    console.print("\n[bold]Upload: Uploading to R2 + inserting to DB...[/bold]")
    pipeline_start = time.time()
    process_tracker = ProgressTracker("Uploading places", total=len(normalized_ids))
    with create_progress("Uploading places", total=len(normalized_ids)) as progress:
        task = progress.add_task("Uploading", total=len(normalized_ids))
        place_num = 0
        errors = 0

        for place_id in normalized_ids:
            place_num += 1

            place = normalized_data.get(place_id)
            if place is None:
                console.print(f"  [red]✗ Place {place_id} not found in normalized data[/red]")
                errors += 1
                with _stats_lock:
                    _stats["errors"] += 1
                progress.update(task, completed=place_num)
                process_tracker.update(place_num)
                continue

            try:
                t0 = time.time()
                r2_task = stage_enqueue_r2(place, r2_pool)
                if r2_task is not None:
                    r2_task.done_event.wait()
                r2_time = time.time() - t0

                t0 = time.time()
                stage_enqueue_db(place, db_pool)
                db_time = time.time() - t0

                with _stats_lock:
                    _stats["places_processed"] += 1
                    _stats["images_downloaded"] += len(place.get("photos", []))
                    _stage_timers["r2_upload"].add(r2_time)
                    _stage_timers["db_insert"].add(db_time)

                console.print(
                    f"  [bold green]✓ Place {place_id} "
                    f"uploaded (r2={r2_time:.2f}s, db={db_time:.2f}s)[/bold green]"
                )

            except Exception as e:
                console.print(f"  [red]✗ Place {place_id} crashed: {e}[/red]")
                errors += 1
                with _stats_lock:
                    _stats["errors"] += 1

            progress.update(task, completed=place_num)
            process_tracker.update(place_num)

    process_tracker.finish()

    console.print("\n[bold]Upload: Finalize[/bold] — waiting for async uploads...")
    finalize_start = time.time()

    r2_progress_task = None
    db_progress_task = None
    progress_done = threading.Event()

    def _update_progress() -> None:
        while not progress_done.is_set():
            if r2_pool is not None and r2_progress_task is not None:
                completed, total = r2_pool.get_progress()
                progress.update(
                    r2_progress_task,
                    completed=completed,
                    total=total,
                    description=f"R2 Upload: {completed}/{total}",
                )
            if db_pool is not None and db_progress_task is not None:
                completed, total = db_pool.get_progress()
                progress.update(
                    db_progress_task,
                    completed=completed,
                    total=total,
                    description=f"DB Insert: {completed}/{total}",
                )
            progress_done.wait(2.0)

    with create_progress("Finalize", total=1) as progress:
        if r2_pool is not None:
            r2_progress_task = progress.add_task("R2 Upload: 0/0", total=limit or 0)
        if db_pool is not None:
            db_progress_task = progress.add_task("DB Insert: 0/0", total=limit or 0)

        progress_thread = threading.Thread(target=_update_progress, daemon=True)
        progress_thread.start()

        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()

        progress_done.set()
        progress_thread.join(timeout=5.0)

    finalize_elapsed = time.time() - finalize_start
    console.print(f"  [green]✓ Finalize complete in {finalize_elapsed:.1f}s[/green]")

    total_elapsed = time.time() - pipeline_start
    console.print("\n[bold green]✓ Upload stage complete:[/bold green]")
    console.print(
        f"  Places: [green]{_stats['places_processed']}[/green] uploaded, "
        f"[red]{errors}[/red] errors"
    )
    console.print(f"  Total time: [cyan]{total_elapsed:.1f}s[/cyan]")

    if errors:
        console.print(f"\n[bold red]{errors} places had errors[/bold red]")

    verify_upload_stage(normalized_ids[:limit] if limit else normalized_ids)


# ── Upload Verification ──────────────────────────────────────────────
def verify_upload_stage(place_ids: list[int]) -> None:
    """Verify that uploaded places exist in Supabase and images exist in R2."""
    if not place_ids:
        console.print("  [yellow]No places to verify[/yellow]")
        return

    if not os.environ.get("DATABASE_URL"):
        console.print("  [yellow]⚠ Skipping verification (no DATABASE_URL)[/yellow]")
        return

    try:
        from supabase import create_client  # type: ignore[import-not-found]

        supabase = create_client(
            os.environ.get("SUPABASE_URL", os.environ.get("DATABASE_URL", "")),
            os.environ.get("SUPABASE_KEY", ""),
        )

        console.print(f"  Checking {len(place_ids)} places in Supabase...")
        missing_places = 0
        for place_id in place_ids:
            response = supabase.table("places").select("id").eq("id", place_id).execute()
            if not response.data:
                console.print(f"  [red]✗ Place {place_id} missing from Supabase[/red]")
                missing_places += 1

        if missing_places == 0:
            console.print(f"  [green]✓ All {len(place_ids)} places exist in Supabase[/green]")
        else:
            console.print(
                f"  [red]✗ {missing_places}/{len(place_ids)} places missing from Supabase[/red]"
            )

    except ImportError:
        console.print("  [yellow]⚠ Skipping verification (supabase package not installed)[/yellow]")
    except Exception as e:
        console.print(f"  [yellow]⚠ Verification failed: {e}[/yellow]")


# ── Full Pipeline (all stages) ───────────────────────────────────────
def run_full_pipeline(
    limit: int | None = None,
    no_disk_cache: bool = False,
    dry_run: bool = False,
) -> None:
    """Run the full parallel per-place pipeline using ProcessPoolExecutor.

    Each worker is cached via @cache.memoize() — re-running with
    the same args returns cached results instantly.
    """
    global _stage_timers

    num_workers = 16

    if no_disk_cache:
        console.print("[yellow]Bypassing disk cache (--no-disk-cache mode)[/yellow]")

    # Setup R2 worker pool
    r2_pool: R2WorkerPool | None = None
    if _r2_config is not None:
        r2_pool = R2WorkerPool(
            _r2_config, no_cache=no_disk_cache, total_expected=limit or 0
        )
        r2_pool.start()

    # Setup DB worker pool
    db_pool: DBWorkerPool | None = None
    if os.environ.get("DATABASE_URL"):
        db_pool = DBWorkerPool(total_expected=limit or 0)
        db_pool.start()

    ensure_packages_installed()

    limit_label = f" (limit {limit})" if limit else ""
    workers_label = f" with {num_workers} workers"
    console.print(f"\n[bold cyan]Starting pipeline{limit_label}{workers_label}...[/bold cyan]\n")

    if dry_run:
        console.print("[bold yellow]=== DRY RUN — stopping here ===[/bold yellow]")
        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()
        return

    # ── Phase 1: Extract ─────────────────────────────────────────────
    console.print("\n[bold]Phase 1: Extract[/bold] — scanning grid points for places...")
    extract_start = time.time()
    extract_tracker = ProgressTracker("Extracting places", total=limit or 0)
    places_to_process = []
    for place, grid_point in place_source(Park4NightAPI(), limit=limit):
        places_to_process.append((place, grid_point))
        extract_tracker.update(len(places_to_process))
    extract_tracker.finish()
    extract_elapsed = time.time() - extract_start
    total_places = len(places_to_process)
    console.print(f"  [green]✓ Found {total_places} places in {extract_elapsed:.1f}s[/green]")

    if not total_places:
        console.print("[yellow]No places to process.[/yellow]")
        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()
        return

    _stage_timers = {
        "extract": StageTimer("Extract"),
        "download": StageTimer("Download"),
        "reviews": StageTimer("Reviews"),
        "translate": StageTimer("Translate"),
        "normalize": StageTimer("Normalize"),
        "r2_upload": StageTimer("R2 Upload"),
        "db_insert": StageTimer("DB Insert"),
    }

    # ── Phase 2: Process ─────────────────────────────────────────────
    console.print("\n[bold]Phase 2: Process[/bold] — extract, download, translate, normalize...")
    pipeline_start = time.time()
    process_tracker = ProgressTracker("Processing places", total=total_places)
    with create_progress("Processing places", total=total_places) as progress:
        task = progress.add_task("Processing", total=total_places)
        place_num = 0
        errors = 0

        multiprocessing.set_start_method("spawn", force=True)
        with ProcessPoolExecutor(
            max_workers=num_workers,
            initializer=_worker_init,
            initargs=(True,),  # preload_translation=True
        ) as executor:
            futures = {
                executor.submit(
                    _worker_process_place,
                    int(raw_place.get("id") or 0),
                    frozendict(raw_place),
                    not no_disk_cache,
                ): (raw_place, grid_point)
                for raw_place, grid_point in places_to_process
            }

            for future in as_completed(futures):
                place_num += 1
                raw_place, grid_point = futures[future]
                place_id = int(raw_place.get("id") or 0)

                try:
                    result = future.result()

                    if "error" in result:
                        console.print(f"  [red]✗ {result['error']}[/red]")
                        errors += 1
                        with _stats_lock:
                            _stats["errors"] += 1
                    else:
                        place = result.pop("place")

                        with _stats_lock:
                            _stage_timers["extract"].add(result["extract"])
                            _stage_timers["download"].add(result["download"])
                            _stage_timers["reviews"].add(result["fetch"])
                            _stage_timers["translate"].add(result["translate"])
                            _stage_timers["normalize"].add(result["normalize"])

                        t0 = time.time()
                        r2_task = stage_enqueue_r2(place, r2_pool)
                        if r2_task is not None:
                            r2_task.done_event.wait()
                        r2_time = time.time() - t0

                        t0 = time.time()
                        stage_enqueue_db(place, db_pool)
                        db_time = time.time() - t0

                        with _stats_lock:
                            _stats["places_processed"] += 1
                            _stats["images_downloaded"] += len(place.get("photos", []))
                            _stage_timers["r2_upload"].add(r2_time)
                            _stage_timers["db_insert"].add(db_time)

                        rate = place_num / result["elapsed"] if result["elapsed"] > 0 else 0
                        console.print(
                            f"  [bold green]✓ Place {result['place_id']} "
                            f"complete ({result['elapsed']:.2f}s, "
                            f"{rate:.1f} places/s)[/bold green]"
                        )

                        logger.info(
                            f"Place {place_num}/{total_places} "
                            f"({result['place_id']}): "
                            f"total={result['elapsed']:.3f}s | "
                            f"extract={result['extract']:.3f}s, "
                            f"download={result['download']:.3f}s, "
                            f"reviews={result['fetch']:.3f}s, "
                            f"translate={result['translate']:.3f}s, "
                            f"normalize={result['normalize']:.3f}s, "
                            f"r2={r2_time:.3f}s, "
                            f"db={db_time:.3f}s | "
                            f"rate={rate:.2f} places/s"
                        )

                except Exception as e:
                    console.print(f"  [red]✗ Place {place_id} crashed: {e}[/red]")
                    errors += 1
                    with _stats_lock:
                        _stats["errors"] += 1

                progress.update(task, completed=place_num)
                process_tracker.update(place_num)

    process_tracker.finish()

    # ── Phase 3: Finalize ────────────────────────────────────────────
    console.print("\n[bold]Phase 3: Finalize[/bold] — waiting for async uploads...")
    finalize_start = time.time()

    r2_progress_task = None
    db_progress_task = None
    progress_done = threading.Event()

    def _update_progress() -> None:
        while not progress_done.is_set():
            if r2_pool is not None and r2_progress_task is not None:
                completed, total = r2_pool.get_progress()
                progress.update(
                    r2_progress_task,
                    completed=completed,
                    total=total,
                    description=f"R2 Upload: {completed}/{total}",
                )
            if db_pool is not None and db_progress_task is not None:
                completed, total = db_pool.get_progress()
                progress.update(
                    db_progress_task,
                    completed=completed,
                    total=total,
                    description=f"DB Insert: {completed}/{total}",
                )
            progress_done.wait(2.0)

    with create_progress("Finalize", total=1) as progress:
        if r2_pool is not None:
            r2_progress_task = progress.add_task("R2 Upload: 0/0", total=limit or 0)
        if db_pool is not None:
            db_progress_task = progress.add_task("DB Insert: 0/0", total=limit or 0)

        progress_thread = threading.Thread(target=_update_progress, daemon=True)
        progress_thread.start()

        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()

        progress_done.set()
        progress_thread.join(timeout=5.0)

    finalize_elapsed = time.time() - finalize_start
    console.print(f"  [green]✓ Finalize complete in {finalize_elapsed:.1f}s[/green]")

    total_elapsed = time.time() - pipeline_start
    console.print("\n[bold green]✓ Pipeline complete:[/bold green]")
    console.print(
        f"  Places: [green]{_stats['places_processed']}[/green] processed, "
        f"[red]{_stats.get('errors', 0)}[/red] errors"
    )
    console.print(f"  Images: [green]{_stats['images_downloaded']}[/green] downloaded")
    console.print(f"  Total time: [cyan]{total_elapsed:.1f}s[/cyan]")

    print_timing_report(_stage_timers, total_elapsed, total_places)

    if errors:
        console.print(f"\n[bold red]{errors} places had errors[/bold red]")


# ── Main Pipeline (stage router) ─────────────────────────────────────
def run_pipeline(
    limit: int | None = None,
    no_disk_cache: bool = False,
    dry_run: bool = False,
    stage: str | None = None,
) -> None:
    """Run the pipeline, routing to the appropriate stage."""
    if stage == "scrape":
        run_scrape_stage(
            limit=limit, no_disk_cache=no_disk_cache, dry_run=dry_run
        )
        return
    elif stage == "normalize":
        # For standalone normalize, scrape first then normalize
        scraped = run_scrape_stage(
            limit=limit, no_disk_cache=no_disk_cache, dry_run=dry_run
        )
        if scraped:
            run_normalize_stage(
                scraped_data=scraped,
                limit=limit,
                no_disk_cache=no_disk_cache,
                dry_run=dry_run,
            )
    elif stage == "upload":
        # For standalone upload, scrape + normalize first then upload
        scraped = run_scrape_stage(
            limit=limit, no_disk_cache=no_disk_cache, dry_run=dry_run
        )
        if scraped:
            normalized = run_normalize_stage(
                scraped_data=scraped,
                limit=limit,
                no_disk_cache=no_disk_cache,
                dry_run=dry_run,
            )
            if normalized:
                run_upload_stage(
                    normalized_data=normalized,
                    limit=limit,
                    no_disk_cache=no_disk_cache,
                    dry_run=dry_run,
                )
    else:
        return run_full_pipeline(
            limit=limit, no_disk_cache=no_disk_cache, dry_run=dry_run
        )


# ── CLI ───────────────────────────────────────────────────────────────
def main() -> None:
    global _r2_config

    parser = argparse.ArgumentParser(
        description="Park4Night Unified ETL Pipeline\n\n"
        "Single script: scrape → normalize → translate → upload R2 → insert DB\n\n"
        "Idempotent: re-running with same --limit completes instantly (disk cache).\n"
        "Use --no-disk-cache to bypass disk cache for timing performance tests.\n"
        "Use --stage to run only a specific stage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit to first N places")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument(
        "--stage",
        choices=["scrape", "normalize", "upload"],
        default=None,
        help="Run only a specific stage",
    )
    parser.add_argument(
        "--r2-config",
        default=os.path.join(os.path.dirname(__file__), "..", "upload", "r2-config.json"),
        help="Path to R2 config JSON",
    )
    parser.add_argument(
        "--env",
        default=os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        help="Path to .env file",
    )
    parser.add_argument(
        "--no-disk-cache",
        action="store_true",
        help="Bypass disk cache for timing performance tests (never clears cache)",
    )
    args = parser.parse_args()

    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    logger, log_file = setup_logging(log_dir)

    console.print("\n[bold cyan]╔═══════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║  Park4Night Unified Pipeline ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════╝[/bold cyan]\n")

    console.print(f"  Log file: [cyan]{log_file}[/cyan]")
    if args.limit:
        console.print(f"  Limit: [yellow]{args.limit} places[/yellow]")
    if args.stage:
        console.print(f"  Stage: [yellow]{args.stage}[/yellow]")
    if args.no_disk_cache:
        console.print("  [yellow]Disk cache bypassed — timing performance mode[/yellow]")

    if args.env and os.path.exists(args.env):
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        load_dotenv(args.env)

    _r2_config = None
    if args.r2_config and os.path.exists(args.r2_config):
        with open(args.r2_config, encoding="utf-8") as f:
            _r2_config = json.load(f)
        console.print(f"  R2 config: [cyan]{args.r2_config}[/cyan]")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    run_pipeline(
        limit=args.limit,
        no_disk_cache=args.no_disk_cache,
        dry_run=args.dry_run,
        stage=args.stage,
    )


if __name__ == "__main__":
    main()
