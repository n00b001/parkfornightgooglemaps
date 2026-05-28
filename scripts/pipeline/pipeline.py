#!/usr/bin/env python3
"""
Park4Night Unified ETL Pipeline

Parallel per-place pipeline:
  Multiple places processed simultaneously by worker threads.
  Each place flows through ALL stages:

    extract → download → fetch reviews → translate → enqueue R2 → normalize → enqueue DB

  Workers share:
    - Translation cache (thread-safe dict with lock)
    - R2 upload pool (async queue-based)
    - DB insert pool (async queue-based)

  --limit N means process N places (in parallel, not serial).
  Checkpoint saved periodically for resume capability.

Parallelism:
  - 16 worker threads (one per CPU core)
  - Each worker runs full pipeline for one place
  - argos-translate uses 2 internal threads per worker = 32 threads total
  - R2 pool: 32 threads for uploads
  - DB pool: 8 threads for inserts
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

# Ensure pipeline package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from api_client import Park4NightAPI  # type: ignore[import-not-found]
from checkpoint import PipelineCheckpoint  # type: ignore[import-not-found]
from config import (  # type: ignore[import-not-found]
    ACTIVITY_CODES,
    PLACE_TYPE_CODES,
    SERVICE_CODES,
)
from db_worker import DBWorkerPool  # type: ignore[import-not-found]
from image_downloader import ImageDownloader  # type: ignore[import-not-found]
from logging_setup import console, create_progress
from normalizer import (  # type: ignore[import-not-found]
    normalize_place,
    normalize_review,
)
from r2_worker import R2WorkerPool  # type: ignore[import-not-found]
from translator import (  # type: ignore[import-not-found]
    ensure_packages_installed,
    get_cache_size,
    preload_models,
    translate_batch,
)

logger = logging.getLogger("pipeline")


# ── Globals (for signal handling) ─────────────────
_checkpoint: PipelineCheckpoint | None = None
_r2_config: dict | None = None
_stats_lock = threading.Lock()
_stats: dict[str, int] = {
    "places_processed": 0,
    "images_downloaded": 0,
    "images_uploaded_r2": 0,
    "translations_cached": 0,
    "db_inserts": 0,
}
_timing: dict[str, float] = {
    "extract": 0.0,
    "translate": 0.0,
    "normalize": 0.0,
    "upload_r2": 0.0,
    "insert_db": 0.0,
    "total": 0.0,
}


# ── Helpers ────────────────────────────────────────


def _str(value) -> str:
    return str(value).strip() if value is not None else ""


# ── Stage 1: Extract (structure raw API data) ─
def extract_place_data(place: dict) -> dict | None:
    """Structure raw API data into a clean place dict.

    Pure function: no I/O, no checkpoint, no side effects.
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


# ── Stage 1b: Download images ─
def download_images(place: dict, downloader: ImageDownloader) -> dict:
    """Download photos for a place. Updates place["photos"] in-place.

    Returns the same place dict with photos populated.
    """
    place_id = place["id"]
    raw_photos = place.get("_raw_photos", [])
    photos = downloader.download_place_photos(place_id, raw_photos)
    place["photos"] = photos
    _stats["images_downloaded"] += len(photos)
    return place


# ── Stage 2: Translate (translate strings for this place) ─
def stage_translate(place: dict) -> dict:
    """Translate all non-English strings for a single place + reviews.

    Applies translations directly to the place dict:
      - descriptions["translated"] = English translation
      - pricing values translated in-place
      - review text translated: {"default": English, "_original": original}
    Uses in-memory cache — repeated strings across places are instant.
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
            if val and val not in ("free", "paid", "on request", "gratuit", "payant"):
                texts_to_translate.append((val, "fr"))  # pricing is always French

    # Collect review text to translate (always French)
    reviews = place.get("reviews", [])
    for review in reviews:
        text = review.get("text", "")
        if text and str(text).strip():
            texts_to_translate.append((str(text).strip(), "fr"))

    # Translate (parallel, uses cache for already-seen strings)
    if texts_to_translate:
        translations = translate_batch(texts_to_translate, max_workers=8)
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


# ── Stage 4: Normalize (clean tables, no translation) ─
def stage_normalize(place: dict) -> dict | None:
    """Normalize place + reviews into clean DB-ready records.

    No translation — all text must be pre-translated by stage_translate.
    Returns fully normalized place ready for DB insert, or None on failure.
    """
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

    return normalized


# ── Stage 4: Enqueue R2 upload (blocking — waits for completion) ─
# WHY blocking: The R2 worker pool exists for performance (parallel uploads
# across multiple places). But we MUST wait for THIS place's uploads to
# complete before marking it as processed in the checkpoint. Otherwise,
# if the pipeline is interrupted between enqueuing and completing, the
# checkpoint says "done" but the images are missing from R2. On resume,
# the place is skipped entirely, and images are lost.
# The pool still processes other places' uploads in parallel — we only
# block on THIS place's done_event.
def stage_enqueue_r2(
    place: dict,
    r2_pool: R2WorkerPool | None,
    checkpoint: PipelineCheckpoint,
) -> dict:
    """Enqueue images for R2 upload and wait for completion.

    Blocks until all images for this place are uploaded (or skipped).
    Marks the r2_uploaded stage in the checkpoint.
    Returns the place dict with R2 URLs populated.
    """
    if r2_pool is None:
        return place

    photos = place.get("photos", [])
    if photos:
        task = r2_pool.enqueue(place["id"], photos)
        # Wait for R2 upload to complete before proceeding.
        # This ensures the checkpoint only marks the place as done
        # when ALL work is actually complete (fixes race condition).
        task.done_event.wait(timeout=300)
        checkpoint.mark_place_stage_done(place["id"], "r2_uploaded")
    return place


# ── Stage 5: Insert DB (place + reviews into Supabase) ─
# WHY blocking: Same rationale as R2. The DB worker pool exists for
# performance (parallel inserts across multiple places). But we MUST
# wait for THIS place's insert to complete before marking it as
# processed. Otherwise, on interrupt, the checkpoint says "done" but
# the data is missing from the database.
def stage_enqueue_db(
    place: dict,
    db_pool: DBWorkerPool | None,
    checkpoint: PipelineCheckpoint,
) -> None:
    """Enqueue a place + reviews for DB insert and wait for completion.

    Blocks until the DB insert is complete.
    Marks the db_inserted stage in the checkpoint.
    Place and reviews MUST already be normalized by the caller.
    Raises if reviews are missing.
    """
    if db_pool is None:
        raise RuntimeError("DB worker pool is None — pipeline misconfigured")
    reviews = place.get("reviews") or []  # empty list is valid (no reviews for this place)

    # Enqueue place + pre-normalized reviews for DB insert
    task = db_pool.enqueue(place, reviews)
    # Wait for DB insert to complete before proceeding.
    # This ensures the checkpoint only marks the place as done
    # when ALL work is actually complete (fixes race condition).
    task.done_event.wait(timeout=300)
    checkpoint.mark_place_stage_done(place["id"], "db_inserted")
    _stats["db_inserts"] += 1


# ── Generator: yield raw places from API ──────────
def place_source(
    api: Park4NightAPI,
    checkpoint: PipelineCheckpoint,
    limit: int | None = None,
    no_cache: bool = False,
):
    """Generator that yields place tuples from the Park4Night API.

    Yields (place_or_marker, grid_point, is_cached) tuples:
      - place_or_marker: raw place dict, or {"id": ..., "_cached": True} for cached
      - grid_point: (lat, lng) tuple, or None for cached markers
      - is_cached: True if this is a cached marker (skip pipeline)

    Two phases:
      Phase 1: Already-processed places (from checkpoint)
        - Cache mode: yield cached markers (skip pipeline)
        - no-cache mode: re-fetch from API, yield raw place
      Phase 2: New places from remaining grid points
        - Skip already-processed places
        - Yield raw places

    Respects `limit` across both phases.
    """
    total_yielded = 0

    # ── Phase 1: Already-processed places ──────────────────────
    processed_ids = checkpoint.get_processed_place_ids(limit)
    if processed_ids:
        cache_label = "[dim]cached[/dim]" if not no_cache else "[yellow]re-fetching[/yellow]"
        console.print(
            f"  [bold blue]{len(processed_ids)}[/bold blue] processed places ({cache_label})"
        )

    for place_id in processed_ids:
        if limit is not None and total_yielded >= limit:
            break

        if no_cache:
            # Re-fetch from API using stored grid point
            grid_point = checkpoint.get_place_grid_point(place_id)
            if grid_point:
                lat, lng = grid_point
                place = api.get_place_by_grid_point(place_id, lat, lng)
                if place:
                    yield (place, (lat, lng), False)
                    total_yielded += 1
                    continue
            console.print(f"  [yellow]⚠ Place {place_id} not found in API, skipping[/yellow]")
        else:
            # Cache mode: yield marker to skip pipeline
            yield ({"id": place_id, "_cached": True}, None, True)
            total_yielded += 1

    # ── Phase 2: New places from grid points ───────────────────
    grid_points = Park4NightAPI.generate_grid_points()
    remaining = checkpoint.get_remaining_grid_points(grid_points)

    if not remaining:
        if not processed_ids:
            console.print("  [yellow]All grid points already processed.[/yellow]")
        return

    limit_msg = f" (limit: {limit} places)" if limit else ""
    already = total_yielded
    new_limit = (limit - already) if (limit is not None and limit > already) else None
    if new_limit:
        limit_msg = f" (limit: {new_limit} new places)"
    console.print(f"  [bold blue]{len(remaining)}[/bold blue] grid points remaining{limit_msg}")

    for lat, lng in remaining:
        if new_limit is not None and (total_yielded - already) >= new_limit:
            break

        places = api.get_places(lat, lng)
        if not places:
            # Mark grid point as done even if no places (it was scraped)
            checkpoint.mark_grid_point_done(lat, lng)
            continue

        for place in places:
            if new_limit is not None and (total_yielded - already) >= new_limit:
                break

            place_id = int(place.get("id") or 0)

            # Skip already-processed places
            if checkpoint.is_place_processed(place_id):
                continue

            yield (place, (lat, lng), False)
            total_yielded += 1

        # Mark grid point as done after yielding all places from it.
        # WHY: This prevents re-scraping the same grid point on resume.
        # Even if some places from this grid point fail to process (R2/DB
        # errors), the grid point itself was scraped successfully — we
        # don't need to re-scrape it. On resume, the checkpoint will skip
        # this grid point, but it will re-process any places that failed
        # (because they're not in processed_place_ids).
        checkpoint.mark_grid_point_done(lat, lng)


# ── Convert existing mode ──────────────────────────
# ── Signal Handling ────────────────────────────────
def _handle_signal(signum, frame) -> None:
    """Handle SIGINT/SIGTERM gracefully."""
    sig_name = signal.Signals(signum).name
    console.print(f"\n[bold yellow]Received {sig_name}, saving checkpoint...[/bold yellow]")
    if _checkpoint is not None:
        _checkpoint._save()
        console.print("[bold green]✓ Checkpoint saved.[/bold green]")
    sys.exit(0)


# ── Worker initializer (called once per process) ──
def _worker_init() -> None:
    """Initialize worker process: preload argos models.

    Called once when each process starts (spawn method).
    Each process loads its own models — no shared state, no deadlock.
    """
    preload_models()


# ── Worker function (must be top-level for pickling) ──
def _worker_process_place(
    raw_place: dict,
    photos: list[dict],
    no_cache: bool = False,
) -> dict:
    """Process a single place in a separate worker process.

    Each process gets its own argos-translate instance (no contention).
    Does: extract → download → fetch reviews → translate → normalize
    Returns place data + timing (R2/DB enqueueing done by main process).
    """
    place_id = int(raw_place.get("id") or 0)
    place_start = time.time()

    # ── Stage 1: Extract ─
    t0 = time.time()
    place = extract_place_data(raw_place)
    extract_time = time.time() - t0
    if not place:
        return {"error": f"Failed to extract place {place_id}"}

    # ── Stage 1b: Download images ─
    t0 = time.time()
    place["_raw_photos"] = photos
    downloader = ImageDownloader(no_cache=no_cache)
    place = download_images(place, downloader)
    download_time = time.time() - t0

    # ── Stage 1c: Fetch reviews ─
    t0 = time.time()
    api = Park4NightAPI()
    place["reviews"] = api.get_reviews(place_id)
    fetch_time = time.time() - t0

    # ── Stage 2: Translate ─
    t0 = time.time()
    place = stage_translate(place)
    translate_time = time.time() - t0

    # ── Stage 3: Normalize ─
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


def run_pipeline(
    api: Park4NightAPI,
    checkpoint: PipelineCheckpoint,
    limit: int | None = None,
    num_workers: int = 16,
    no_cache: bool = False,
) -> None:
    """Run the parallel per-place pipeline using ProcessPoolExecutor.

    Each worker process gets its own argos-translate instance (no contention).
    Workers: extract → download → fetch reviews → translate → normalize
    Main process: enqueue R2 → enqueue DB → checkpoint
    """
    # Setup R2 worker pool (async queue-based uploads)
    r2_pool: R2WorkerPool | None = None
    if _r2_config is not None:
        r2_pool = R2WorkerPool(_r2_config, no_cache=no_cache)
        r2_pool.start()

    # Setup DB worker pool (async queue-based inserts)
    db_pool: DBWorkerPool | None = None
    if os.environ.get("DATABASE_URL"):
        db_pool = DBWorkerPool()
        if db_pool is not None:
            db_pool.start()

    # Install translation packages once in main process before spawning workers.
    # With spawn, each worker starts fresh — packages are installed globally
    # (shared across processes), so this only needs to happen once.
    ensure_packages_installed()

    # Progress tracking
    limit_label = f" (limit {limit})" if limit else ""
    workers_label = f" with {num_workers} workers"
    console.print(f"\n[bold cyan]Starting pipeline{limit_label}{workers_label}...[/bold cyan]\n")

    # Collect all places to process (pre-fetch from generator)
    # Each item is: (place_or_marker, grid_point, is_cached)
    places_to_process = list(place_source(api, checkpoint, limit, no_cache))
    total_places = len(places_to_process)

    if not total_places:
        return

    with create_progress("Pipeline", total=total_places) as progress:
        task = progress.add_task("Processing", total=total_places)
        place_num = 0
        errors = 0

        # Separate cached markers from real work
        cached_count = sum(1 for _, _, is_cached in places_to_process if is_cached)
        real_places = [
            (place_or_marker, grid_point)
            for place_or_marker, grid_point, is_cached in places_to_process
            if not is_cached
        ]

        # Print cached summary
        if cached_count:
            console.print(f"  [dim]✓ {cached_count} place(s) cached, skipping pipeline[/dim]")
            place_num += cached_count
            with _stats_lock:
                _stats["places_processed"] += cached_count
            progress.update(task, completed=place_num)

        # Process real places
        if real_places:
            # Use spawn (not fork) to avoid inheriting argos locks
            # Each worker preloads models once via initializer
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
                    for raw_place, grid_point in real_places
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
                        else:
                            place = result.pop("place")

                            # Main process: enqueue R2 (blocking — waits for completion)
                            # WHY blocking: See stage_enqueue_r2 docstring.
                            # The R2 pool still processes other places in parallel;
                            # we only block on THIS place's done_event.
                            t0 = time.time()
                            place = stage_enqueue_r2(place, r2_pool, checkpoint)
                            r2_time = time.time() - t0

                            # Main process: enqueue DB (blocking — waits for completion)
                            # WHY blocking: See stage_enqueue_db docstring.
                            # The DB pool still processes other places in parallel;
                            # we only block on THIS place's done_event.
                            t0 = time.time()
                            stage_enqueue_db(place, db_pool, checkpoint)
                            db_time = time.time() - t0

                            # Main process: mark place processed + save checkpoint
                            # This is safe now because R2/DB are complete (we waited).
                            # If the pipeline is interrupted here, the place is NOT
                            # marked as processed, so it will be re-processed on resume.
                            # Each stage is independently idempotent via disk cache:
                            # - Images: .webp exists → skip (image_downloader.py)
                            # - Translations: in cache → skip (translator.py)
                            # - R2: head_object exists → skip (r2_worker.py)
                            # - DB: ON CONFLICT DO UPDATE (db_worker.py)
                            if grid_point:
                                checkpoint.mark_place_processed(
                                    place_id, grid_point[0], grid_point[1]
                                )
                            with _stats_lock:
                                _stats["places_processed"] += 1

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

                            logger.info(
                                f"Place {place_num} ({result['place_id']}): "
                                f"total={result['elapsed']:.3f}s | "
                                f"extract={result['extract']:.3f}s, "
                                f"download={result['download']:.3f}s, "
                                f"translate={result['translate']:.3f}s, "
                                f"r2={r2_time:.3f}s, "
                                f"normalize={result['normalize']:.3f}s, "
                                f"db={db_time:.3f}s | "
                                f"rate={rate:.2f} places/s"
                            )

                    except Exception as e:
                        console.print(
                            f"  [red]✗ Place {place_id} crashed: {e}[/red]"
                        )
                        errors += 1

                    progress.update(task, completed=place_num)

    # Cleanup: wait for all uploads/inserts to finish, then shut down workers
    if r2_pool is not None:
        console.print("\n[dim]Waiting for R2 uploads to complete...[/dim]")
        r2_pool.shutdown()

    if db_pool is not None:
        console.print("[dim]Waiting for DB inserts to complete...[/dim]")
        db_pool.shutdown()

    if errors:
        console.print(f"\n[bold red]{errors} places had errors[/bold red]")


# ── CLI ────────────────────────────────────────────
def main() -> None:
    global _checkpoint, logger, _r2_config

    parser = argparse.ArgumentParser(description="Park4Night Unified ETL Pipeline")
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
        "--workers",
        type=int,
        default=8,
        help="Number of parallel worker threads (default: 8)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache — re-download all images (useful for testing speed)",
    )
    args = parser.parse_args()

    # Setup logging
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    from logging_setup import setup_logging

    logger, log_file = setup_logging(log_dir)
    _checkpoint = PipelineCheckpoint()

    console.print("\n[bold cyan]╔═══════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║  Park4Night Unified Pipeline ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════╝[/bold cyan]\n")

    console.print(f"  Log file: [cyan]{log_file}[/cyan]")
    if args.limit:
        console.print(f"  Limit: [yellow]{args.limit} places[/yellow]")

    # Load environment
    if args.env and os.path.exists(args.env):
        from dotenv import load_dotenv

        load_dotenv(args.env)

    # Load R2 config
    _r2_config = None
    if args.r2_config and os.path.exists(args.r2_config):
        with open(args.r2_config, encoding="utf-8") as f:
            _r2_config = json.load(f)

    # Signal handling
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Store no_cache globally for worker access
    globals()["_no_cache"] = args.no_cache
    if args.no_cache:
        console.print("  [yellow]Cache disabled — all images will be re-downloaded[/yellow]")

    start_time = time.time()

    # ── Run pipeline ───────────────────────
    api = Park4NightAPI()
    run_pipeline(
        api, _checkpoint, limit=args.limit, num_workers=args.workers, no_cache=args.no_cache
    )

    elapsed = time.time() - start_time

    # ── Summary ───────────────────────────
    summary = _checkpoint.get_summary()
    total_places = _stats["places_processed"]
    rate = total_places / elapsed if elapsed > 0 else 0

    console.print("\n[bold green]╔═══════════════════════╗[/bold green]")
    console.print("[bold green]║  Pipeline complete!  ║[/bold green]")
    console.print("[bold green]╚═══════════════════════╝[/bold green]")
    console.print(f"  Time: [cyan]{elapsed:.1f}s[/cyan]")
    console.print(f"  Grid points: [cyan]{summary['grid_points_done']}[/cyan]")
    console.print(f"  Places processed: [cyan]{total_places}[/cyan] ({rate:.1f} places/s)")
    console.print(f"  Stats: {_stats}")

    # Extrapolation for 200,000 places
    eta_hours = 0.0
    if rate > 0:
        eta_seconds = 200_000 / rate
        eta_hours = eta_seconds / 3600
        console.print("\n[yellow]Extrapolation for 200,000 places:[/yellow]")
        console.print(
            f"  At {rate:.1f} places/s → ~{eta_hours:.1f} hours ({eta_seconds / 60:.0f} minutes)"
        )

    logger.info(f"Pipeline complete in {elapsed:.1f}s")
    logger.info(f"Rate: {rate:.2f} places/s")
    logger.info(f"Extrapolation 200k places: ~{eta_hours:.1f} hours at {rate:.1f} places/s")


if __name__ == "__main__":
    main()
