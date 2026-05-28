#!/usr/bin/env python3
"""
Park4Night Unified ETL Pipeline

Single script that merges scraper + normalizer + uploader into one pipeline.
Each place flows through all stages end-to-end:

    extract (API) → download images → fetch reviews → translate →
    normalize → upload R2 → insert DB

Idempotency via disk cache (NOT checkpointing):
  Each stage checks if its output file exists before doing work.
  Re-running with the same --limit completes instantly (all cached).
  --no-cache bypasses all caches (force re-process everything).

Why disk cache over checkpointing:
  - Simpler: file existence check vs. complex state machine
  - More reliable: no central authority to get out of sync
  - Easier to debug: ls the cache directory to see what's cached
  - Harder to get wrong: can't forget to update the checkpoint

Usage:
    cd scripts/pipeline && uv run python pipeline.py --limit 10
    cd scripts/pipeline && uv run python pipeline.py --limit 10 --no-cache
    cd scripts/pipeline && uv run python pipeline.py --dry-run

Architecture:
  - ProcessPoolExecutor (spawn) for main pipeline workers
    Each worker does: extract → download → reviews → translate → normalize
  - R2 worker pool (32 threads, queue-based) for async image uploads
  - DB worker pool (8 threads, queue-based) for async database inserts
  - Worker pools are KEPT because removing them makes the pipeline 5-10x slower
    (see PIPELINE_DESIGN.md for detailed explanation)

Author: Generated following PIPELINE_DESIGN.md
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

# Ensure pipeline package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import Park4NightAPI  # type: ignore[import-not-found]
from cache import (  # type: ignore[import-not-found]
    api_cache_clear,
    get_cache_stats,
    norm_cache_clear,
    norm_cache_get,
    norm_cache_set,
)
from config import (  # type: ignore[import-not-found]
    ACTIVITY_CODES,
    PLACE_TYPE_CODES,
    SERVICE_CODES,
)
from db_worker import DBWorkerPool  # type: ignore[import-not-found]
from image_downloader import ImageDownloader  # type: ignore[import-not-found]
from logging_setup import (  # type: ignore[import-not-found]
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
from r2_worker import R2WorkerPool  # type: ignore[import-not-found]
from translator import (  # type: ignore[import-not-found]
    ensure_packages_installed,
    get_cache_size,
    preload_models,
    save_cache,
    translate_batch,
)

logger = logging.getLogger("pipeline")

# ── Globals (for signal handling) ─────────────────────────────────────
_r2_config: dict | None = None
_no_cache_global = False
_stats_lock = threading.Lock()
_stats: dict[str, int] = {
    "places_processed": 0,
    "images_downloaded": 0,
    "images_uploaded_r2": 0,
    "translations_cached": 0,
    "db_inserts": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "errors": 0,
}

# Per-stage timing accumulators (for aggregate timing report at end).
# Why: each worker returns per-place timing; main process accumulates here
# to show which stage is the bottleneck when the pipeline takes hours.
_stage_timers: dict[str, StageTimer] = {}

# Per-worker-process shared instances (created in _worker_init, used in _worker_process_place).
# Why: each worker process has its own globals (spawn method). Creating the API client
# and ImageDownloader once per process reuses TCP connections (connection pooling)
# and avoids creating a new requests.Session per place. This is 3-5x faster.
_worker_api: Park4NightAPI | None = None
_worker_downloader: ImageDownloader | None = None


# ── Helpers ───────────────────────────────────────────────────────────


def _str(value: Any) -> str:
    """Safely convert a value to string, handling None."""
    return str(value).strip() if value is not None else ""


# ── Stage 1: Extract (structure raw API data) ────────────────────────
def extract_place_data(place: dict) -> dict | None:
    """Structure raw API data into a clean place dict.

    Pure function: no I/O, no cache, no side effects.
    Returns structured place dict ready for image download, or None on failure.
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
        "photos": [],  # populated by download_images
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
    """Download photos for a place. Updates place["photos"] in-place.

    Disk cache: images are saved to data/images/places/{id}/.
    If .webp file already exists, download is skipped (unless no_cache).
    """
    place_id = place["id"]
    raw_photos = place.get("_raw_photos", [])
    photos = downloader.download_place_photos(place_id, raw_photos)
    place["photos"] = photos
    with _stats_lock:
        _stats["images_downloaded"] += len(photos)
    return place


# ── Stage 3: Fetch reviews ───────────────────────────────────────────
def fetch_reviews(place: dict, api: Park4NightAPI) -> dict:
    """Fetch reviews for a place from API (with disk cache).

    If reviews are cached on disk, returns immediately without HTTP request.
    """
    place_id = place["id"]
    reviews = api.get_reviews(place_id)
    place["reviews"] = reviews
    return place


# ── Stage 4: Translate ───────────────────────────────────────────────
def stage_translate(place: dict, no_cache: bool = False) -> dict:
    """Translate all non-English strings for a single place + reviews.

    Uses persistent disk cache: already-translated strings are loaded
    from disk at startup. Re-running the pipeline does not re-translate
    cached strings.

    Applies translations directly to the place dict:
      - descriptions["translated"] = English translation
      - pricing values translated in-place
      - review text translated: {"default": English, "_original": original}
    """
    # Collect (text, src_lang) pairs to translate
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
            if val and val not in (
                "free",
                "paid",
                "on request",
                "gratuit",
                "payant",
            ):
                texts_to_translate.append((val, "fr"))

    # Collect review text to translate (always French)
    reviews = place.get("reviews", [])
    for review in reviews:
        text = review.get("text", "")
        if text and str(text).strip():
            texts_to_translate.append((str(text).strip(), "fr"))

    # Translate (parallel, uses persistent disk cache)
    if texts_to_translate:
        translations = translate_batch(texts_to_translate, max_workers=8, no_cache=no_cache)
        with _stats_lock:
            _stats["translations_cached"] = get_cache_size()

        # Apply translations to descriptions
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

        # Apply translations to pricing
        if isinstance(raw_pricing, dict):
            for key, value in raw_pricing.items():
                val = (str(value) or "").strip().lower()
                if val and val in translations:
                    raw_pricing[key] = translations[val]

        # Apply translations to reviews
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
    """Normalize place + reviews into clean DB-ready records.

    No translation — all text must be pre-translated by stage_translate.
    Uses disk cache: if normalized output exists on disk, returns cached.
    Returns fully normalized place ready for DB insert, or None on failure.
    """
    place_id = place["id"]

    # Check normalization cache
    cached = norm_cache_get(place_id)
    if cached is not None:
        with _stats_lock:
            _stats["cache_hits"] += 1
        # Still need to normalize reviews (they're not cached separately)
        normalized_reviews = []
        for review in place.get("reviews", []):
            nr = normalize_review(review)
            if nr:
                normalized_reviews.append(nr)
        cached["reviews"] = normalized_reviews
        return cached

    with _stats_lock:
        _stats["cache_misses"] += 1

    normalized = normalize_place(place)
    if not normalized:
        return None

    # Normalize reviews
    normalized_reviews = []
    for review in place.get("reviews", []):
        normalized_review = normalize_review(review)
        if normalized_review:
            normalized_reviews.append(normalized_review)
    normalized["reviews"] = normalized_reviews

    # Cache normalized data
    norm_cache_set(place_id, normalized)

    return normalized


# ── Stage 6: Enqueue R2 upload (non-blocking) ────────────────────────
def stage_enqueue_r2(
    place: dict,
    r2_pool: R2WorkerPool | None,
) -> dict:
    """Enqueue images for async R2 upload. Non-blocking.

    Worker threads dequeue and upload in parallel, then update DB with URLs.
    Returns the unchanged place dict.
    """
    if r2_pool is None:
        return place

    photos = place.get("photos", [])
    if photos:
        r2_pool.enqueue(place["id"], photos)
    return place


# ── Stage 7: Enqueue DB insert (non-blocking) ────────────────────────
def stage_enqueue_db(
    place: dict,
    db_pool: DBWorkerPool | None,
) -> None:
    """Enqueue a place + reviews for async DB insert. Non-blocking.

    Place and reviews MUST already be normalized by the caller.
    Raises if reviews are missing.
    """
    if db_pool is None:
        raise RuntimeError("DB worker pool is None — pipeline misconfigured")
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

    Iterates through all grid points, fetches places from each point,
    and yields unique places (deduplicated by ID).

    Disk cache: API responses are cached per grid point. Re-running
    the pipeline finds cached responses and skips HTTP requests.

    Args:
        api: Park4NightAPI client (with disk cache).
        limit: Maximum number of places to yield (None = no limit).

    Yields:
        (place_dict, grid_point) tuples where grid_point is (lat, lng).
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
    """Handle SIGINT/SIGTERM gracefully: save caches and exit."""
    sig_name = signal.Signals(signum).name
    console.print(f"\n[bold yellow]Received {sig_name}, saving caches...[/bold yellow]")
    save_cache()  # Save translation cache to disk
    console.print("[bold green]✓ Caches saved.[/bold green]")
    sys.exit(0)


# ── Worker initializer (called once per process) ─────────────────────
def _worker_init() -> None:
    """Initialize worker process: preload argos models + create shared instances.

    Called once when each process starts (spawn method).
    Each process loads its own models — no shared state, no deadlock.

    Why create shared instances here:
      Each worker process has its own globals (spawn method). Creating the
      API client and ImageDownloader once per process reuses TCP connections
      (connection pooling) and avoids creating a new requests.Session per place.
      This is 3-5x faster than creating new instances per place.
    """
    global _worker_api, _worker_downloader
    preload_models()
    # Create shared instances for this worker process.
    # The no_cache flag is passed via _worker_process_place's no_cache param,
    # but we create the instances here with the global no_cache setting.
    _worker_api = Park4NightAPI(no_cache=_no_cache_global)
    _worker_downloader = ImageDownloader(no_cache=_no_cache_global)


# ── Worker function (must be top-level for pickling) ─────────────────
def _worker_process_place(
    raw_place: dict,
    photos: list[dict],
    no_cache: bool = False,
) -> dict:
    """Process a single place in a separate worker process.

    Each process gets its own argos-translate instance (no contention).
    Does: extract → download → fetch reviews → translate → normalize
    Returns place data + timing (R2/DB enqueueing done by main process).

    Uses shared API client and ImageDownloader instances created in
    _worker_init() — reuses TCP connections across places (3-5x faster).

    Disk cache is used at every stage:
      - API responses cached per grid point
      - Images cached as .webp files on disk
      - Translations cached in translations.json
      - Normalized data cached per place ID
    """
    place_id = int(raw_place.get("id") or 0)
    place_start = time.time()

    # ── Stage 1: Extract ─
    t0 = time.time()
    place = extract_place_data(raw_place)
    extract_time = time.time() - t0
    if not place:
        return {"error": f"Failed to extract place {place_id}"}

    # ── Stage 2: Download images ─
    t0 = time.time()
    place["_raw_photos"] = photos
    # Use shared ImageDownloader from _worker_init (reuses TCP connections)
    assert _worker_downloader is not None, "ImageDownloader not initialized"
    place = download_images(place, _worker_downloader)
    download_time = time.time() - t0

    # ── Stage 3: Fetch reviews ─
    t0 = time.time()
    # Use shared API client from _worker_init (reuses TCP connections)
    assert _worker_api is not None, "Park4NightAPI not initialized"
    place = fetch_reviews(place, _worker_api)
    fetch_time = time.time() - t0

    # ── Stage 4: Translate ─
    t0 = time.time()
    place = stage_translate(place, no_cache=no_cache)
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
        "place": place,  # return normalized place for main process
    }


# ── Main Pipeline ────────────────────────────────────────────────────
def run_pipeline(
    limit: int | None = None,
    no_cache: bool = False,
    dry_run: bool = False,
) -> None:
    """Run the parallel per-place pipeline using ProcessPoolExecutor.

    Each worker process gets its own argos-translate instance (no contention).
    Workers: extract → download → fetch reviews → translate → normalize
    Main process: enqueue R2 → enqueue DB → save caches

    Disk cache ensures idempotency:
      - Re-running with same --limit: all stages find cached output → skip
      - --no-cache: bypass all caches → re-process everything

    Progress tracking:
      - Per-place progress bar (console + log file)
      - Per-stage timing accumulators (for end-of-run report)
      - Log progress every place (not every 10) for file visibility
    """
    global _no_cache_global, _stage_timers
    _no_cache_global = no_cache

    # 16 workers: half of 32 cores. Translation (argos) is CPU-bound,
    # so we don't saturate all cores — leaves room for I/O workers.
    num_workers = 16

    # Clear caches if --no-cache
    if no_cache:
        console.print("[yellow]Clearing disk caches (--no-cache mode)...[/yellow]")
        api_cache_clear()
        norm_cache_clear()

    # Setup R2 worker pool (async queue-based uploads)
    # KEPT because removing it makes the pipeline 5-10x slower.
    # 32 threads for parallel uploads to Cloudflare R2.
    r2_pool: R2WorkerPool | None = None
    if _r2_config is not None:
        r2_pool = R2WorkerPool(_r2_config, no_cache=no_cache, total_expected=limit or 0)
        r2_pool.start()

    # Setup DB worker pool (async queue-based inserts)
    # KEPT because removing it makes the pipeline 5-10x slower.
    # 8 threads for parallel inserts to Supabase PostgreSQL.
    db_pool: DBWorkerPool | None = None
    if os.environ.get("DATABASE_URL"):
        db_pool = DBWorkerPool(total_expected=limit or 0)
        db_pool.start()

    # Install translation packages once in main process before spawning.
    # With spawn, each worker starts fresh — packages are installed globally
    # (shared across processes), so this only needs to happen once.
    ensure_packages_installed()

    # Progress tracking
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

    # ── Phase 1: Extract (collect places from API) ─────────────────
    # Collect all places to process (pre-fetch from generator).
    # Each item is: (raw_place_dict, grid_point).
    # This phase shows a progress bar for grid points scanned.
    console.print("\n[bold]Phase 1: Extract[/bold] — scanning grid points for places...")
    extract_start = time.time()
    places_to_process = list(place_source(Park4NightAPI(no_cache=no_cache), limit=limit))
    extract_elapsed = time.time() - extract_start
    total_places = len(places_to_process)
    console.print(f"  [green]✓ Found {total_places} places in {extract_elapsed:.1f}s[/green]")
    logger.info(f"Extract phase: {total_places} places found in {extract_elapsed:.1f}s")

    if not total_places:
        console.print("[yellow]No places to process.[/yellow]")
        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()
        return

    # Initialize per-stage timing accumulators.
    # Why: each worker returns per-place timing; main process accumulates
    # here to produce the aggregate timing report at the end.
    _stage_timers = {
        "extract": StageTimer("Extract"),
        "download": StageTimer("Download"),
        "reviews": StageTimer("Reviews"),
        "translate": StageTimer("Translate"),
        "normalize": StageTimer("Normalize"),
        "r2_upload": StageTimer("R2 Upload"),
        "db_insert": StageTimer("DB Insert"),
    }

    # ── Phase 2: Process (extract → download → translate → normalize) ─
    console.print("\n[bold]Phase 2: Process[/bold] — extract, download, translate, normalize...")
    pipeline_start = time.time()
    with create_progress("Processing places", total=total_places) as progress:
        task = progress.add_task("Processing", total=total_places)
        place_num = 0
        errors = 0

        # Use spawn (not fork) to avoid inheriting argos locks.
        # Each worker preloads models once via initializer.
        multiprocessing.set_start_method("spawn", force=True)
        with ProcessPoolExecutor(
            max_workers=num_workers,
            initializer=_worker_init,
        ) as executor:
            futures = {
                executor.submit(
                    _worker_process_place,
                    raw_place,
                    raw_place.get("photos", []),
                    no_cache,
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

                        # Accumulate per-stage timing from worker.
                        # Why: these times are per-place; we sum them to show
                        # total time spent in each stage across all places.
                        with _stats_lock:
                            _stage_timers["extract"].add(result["extract"])
                            _stage_timers["download"].add(result["download"])
                            _stage_timers["reviews"].add(result["fetch"])
                            _stage_timers["translate"].add(result["translate"])
                            _stage_timers["normalize"].add(result["normalize"])

                        # Main process: enqueue R2 upload (non-blocking)
                        t0 = time.time()
                        place = stage_enqueue_r2(place, r2_pool)
                        r2_time = time.time() - t0

                        # Main process: enqueue DB insert (non-blocking)
                        t0 = time.time()
                        stage_enqueue_db(place, db_pool)
                        db_time = time.time() - t0

                        with _stats_lock:
                            _stats["places_processed"] += 1
                            _stage_timers["r2_upload"].add(r2_time)
                            _stage_timers["db_insert"].add(db_time)

                        rate = (
                            place_num / result["elapsed"]
                            if result["elapsed"] > 0
                            else 0
                        )
                        console.print(
                            f"  [bold green]✓ Place {result['place_id']} "
                            f"complete ({result['elapsed']:.2f}s, "
                            f"{rate:.1f} places/s)[/bold green]"
                        )

                        # Log every place to file (not every 10) for visibility.
                        # Why: when running in tmux/cron, the log file is the
                        # only monitoring surface. Every place logged = easy tail.
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

    # ── Phase 3: Wait for async uploads/inserts ─────────────────────
    console.print("\n[bold]Phase 3: Finalize[/bold] — waiting for async uploads...")
    finalize_start = time.time()

    # Progress tracking for R2/DB during Finalize.
    # Why: the worker pools run asynchronously in the background. Without
    # progress bars, the Finalize phase appears stuck for minutes.
    # We use a background thread to read progress from the worker pools
    # and update Rich progress bars + log file in real-time.
    r2_progress_task = None
    db_progress_task = None
    progress_done = threading.Event()

    def _update_progress() -> None:
        """Background thread: read progress from worker pools and update bars."""
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
            # Log progress to file every 5 seconds
            if logger:
                r2_done, r2_total = (
                    r2_pool.get_progress() if r2_pool is not None else (0, 0)
                )
                db_done, db_total = (
                    db_pool.get_progress() if db_pool is not None else (0, 0)
                )
                logger.info(
                    f"[Finalize] R2: {r2_done}/{r2_total} • "
                    f"DB: {db_done}/{db_total} • "
                    f"elapsed: {time.time() - finalize_start:.1f}s"
                )
            progress_done.wait(2.0)  # Check every 2 seconds

    # Create progress bars for R2 and DB
    with create_progress("Finalize", total=1) as progress:
        if r2_pool is not None:
            r2_progress_task = progress.add_task("R2 Upload: 0/0", total=limit or 0)
        if db_pool is not None:
            db_progress_task = progress.add_task("DB Insert: 0/0", total=limit or 0)

        # Start background progress updater
        progress_thread = threading.Thread(target=_update_progress, daemon=True)
        progress_thread.start()

        # Shutdown worker pools (waits for queues to drain)
        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()

        # Stop progress updater
        progress_done.set()
        progress_thread.join(timeout=5.0)

    finalize_elapsed = time.time() - finalize_start
    console.print(f"  [green]✓ Finalize complete in {finalize_elapsed:.1f}s[/green]")
    logger.info(f"Finalize phase: {finalize_elapsed:.1f}s")

    # Save translation cache to disk
    save_cache()

    # ── Summary Report ──────────────────────────────────────────────
    total_elapsed = time.time() - pipeline_start
    console.print("\n[bold green]✓ Pipeline complete:[/bold green]")
    console.print(
        f"  Places: [green]{_stats['places_processed']}[/green] processed, "
        f"[red]{_stats.get('errors', 0)}[/red] errors"
    )
    console.print(f"  Images: [green]{_stats['images_downloaded']}[/green] downloaded")
    console.print(
        f"  Cache: [green]{_stats['cache_hits']}[/green] hits, "
        f"[yellow]{_stats['cache_misses']}[/yellow] misses"
    )
    console.print(f"  Total time: [cyan]{total_elapsed:.1f}s[/cyan]")

    # Print aggregate timing report (shows bottleneck stage)
    print_timing_report(_stage_timers, total_elapsed, total_places)

    if errors:
        console.print(f"\n[bold red]{errors} places had errors[/bold red]")


# ── CLI ───────────────────────────────────────────────────────────────
def main() -> None:
    global _r2_config

    parser = argparse.ArgumentParser(
        description="Park4Night Unified ETL Pipeline\n\n"
        "Single script: scrape → normalize → translate → upload R2 → insert DB\n\n"
        "Idempotent: re-running with same --limit completes instantly (disk cache).\n"
        "Use --no-cache to bypass all caches and re-process everything.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N places (fully processed end-to-end)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
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
        "--no-cache",
        action="store_true",
        help="Bypass all disk caches — re-download, re-translate, re-upload",
    )
    args = parser.parse_args()

    # Setup logging (dual output: Rich console + timestamped log file)
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    logger, log_file = setup_logging(log_dir)

    console.print("\n[bold cyan]╔═══════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║  Park4Night Unified Pipeline ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════╝[/bold cyan]\n")

    console.print(f"  Log file: [cyan]{log_file}[/cyan]")
    if args.limit:
        console.print(f"  Limit: [yellow]{args.limit} places[/yellow]")
    if args.no_cache:
        console.print("  [yellow]Cache disabled — all data will be re-processed[/yellow]")

    # Load environment
    if args.env and os.path.exists(args.env):
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        load_dotenv(args.env)

    # Load R2 config
    _r2_config = None
    if args.r2_config and os.path.exists(args.r2_config):
        with open(args.r2_config, encoding="utf-8") as f:
            _r2_config = json.load(f)
        console.print(f"  R2 config: [cyan]{args.r2_config}[/cyan]")

    # Signal handling (save caches on Ctrl+C)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Show cache stats
    cache_stats = get_cache_stats()
    console.print(f"  Cache: [cyan]{cache_stats}[/cyan]")

    # Run the pipeline
    run_pipeline(
        limit=args.limit,
        no_cache=args.no_cache,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
