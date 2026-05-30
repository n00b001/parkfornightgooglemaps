#!/usr/bin/env python3
"""
Park4Night Unified ETL Pipeline

Single script: scrape → normalize → translate → upload R2 → insert DB

Each place flows through all stages end-to-end:
    extract (API) → download images → fetch reviews → translate →
    normalize → upload R2 → insert DB

Idempotent: re-running with same --limit completes instantly (disk cache).
Use --no-disk-cache to bypass all caches for performance metrics.

Usage:
    cd scripts/pipeline && uv run python pipeline.py --limit 10
    cd scripts/pipeline && uv run python pipeline.py --limit 10 --no-disk-cache
    cd scripts/pipeline && uv run python pipeline.py --dry-run

Architecture:
  - ProcessPoolExecutor (spawn) for main pipeline workers
  - R2 worker pool (32 threads, queue-based) for async image uploads
  - DB worker pool (8 threads, queue-based) for async database inserts
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

import diskcache as dc

# Ensure pipeline package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import Park4NightAPI  # type: ignore[import-not-found]
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
    translate_batch_http,
)

logger = logging.getLogger("pipeline")

# ── Disk cache (process-safe FanoutCache) ────────────────────────────
_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "cache",
    "diskcache",
)
disk_cache = dc.FanoutCache(_CACHE_DIR)

# ── Globals ──────────────────────────────────────────────────────────
_r2_config: dict | None = None
NO_DISK_CACHE = False  # set True by --no-disk-cache
_translation_server_url: str = ""  # set by run_pipeline()
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
_stage_timers: dict[str, StageTimer] = {}


# ── Helpers ───────────────────────────────────────────────────────────


def _str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def get_cache_stats() -> dict[str, Any]:
    """Get statistics about the diskcache."""
    stats: dict[str, Any] = {
        "diskcache_size": 0,
        "diskcache_size_str": "0 bytes",
    }
    try:
        size = disk_cache.size
        stats["diskcache_size"] = size
        if size > 1024 * 1024:
            stats["diskcache_size_str"] = f"{size / (1024 * 1024):.1f} MB"
        elif size > 1024:
            stats["diskcache_size_str"] = f"{size / 1024:.1f} KB"
        else:
            stats["diskcache_size_str"] = f"{size} bytes"
    except Exception:
        pass
    return stats


# ── Cache helpers (simple get/set by key) ────────────────────────────


def _cache_get(key: str) -> Any:
    """Get from disk cache. Returns None on miss."""
    if NO_DISK_CACHE:
        return None
    try:
        return disk_cache[key]
    except KeyError:
        return None


def _cache_set(key: str, value: Any) -> None:
    """Set in disk cache. No-op when --no-disk-cache."""
    if NO_DISK_CACHE:
        return
    disk_cache[key] = value


# ── Stage: extract place data ────────────────────────────────────────


def extract_place_data(place: dict) -> dict | None:
    """Structure raw API data into a clean place dict. Pure function."""
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


# ── Stage: scrape place (extract + download + reviews) ───────────────


def scrape_place(raw_place: dict, api: Park4NightAPI, downloader: ImageDownloader) -> dict | None:
    """Scrape a single place: extract data, download images, fetch reviews."""
    place_id = int(raw_place.get("id") or 0)
    if not place_id:
        return None

    # Check cache
    cache_key = f"scrape:{place_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        with _stats_lock:
            _stats["cache_hits"] += 1
        return cached

    # Extract
    place = extract_place_data(raw_place)
    if not place:
        return None

    # Download images
    raw_photos = raw_place.get("photos", [])
    photos = downloader.download_place_photos(place_id, raw_photos)
    place["photos"] = photos

    # Fetch reviews
    reviews = api.get_reviews(place_id)
    place["reviews"] = reviews

    # Cache result
    _cache_set(cache_key, place)
    with _stats_lock:
        _stats["cache_misses"] += 1

    return place


# ── Stage: translate place ───────────────────────────────────────────


def translate_place(place: dict) -> dict:
    """Translate all non-English strings for a single place + reviews."""
    place_id = place.get("id", 0)

    # Check cache
    cache_key = f"translate:{place_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        with _stats_lock:
            _stats["cache_hits"] += 1
        return cached

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
        translations = translate_batch_http(
            texts_to_translate, server_url=_translation_server_url
        )

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

    # Cache result
    _cache_set(cache_key, place)
    with _stats_lock:
        _stats["cache_misses"] += 1

    return place


# ── Stage: normalize place ───────────────────────────────────────────


def normalize_place_stage(place: dict) -> dict | None:
    """Normalize place + reviews into clean DB-ready records."""
    place_id = place.get("id", 0)

    # Check cache
    cache_key = f"normalize:{place_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        with _stats_lock:
            _stats["cache_hits"] += 1
        return cached

    normalized = normalize_place(place)
    if not normalized:
        return None

    normalized_reviews = []
    for review in place.get("reviews", []):
        nr = normalize_review(review)
        if nr:
            normalized_reviews.append(nr)
    normalized["reviews"] = normalized_reviews

    # Cache result
    _cache_set(cache_key, normalized)
    with _stats_lock:
        _stats["cache_misses"] += 1

    return normalized


# ── Stage: enqueue R2 upload (non-blocking) ──────────────────────────


def enqueue_r2(
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


# ── Stage: enqueue DB insert (non-blocking) ──────────────────────────


def enqueue_db(
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


def place_source(api: Park4NightAPI, limit: int | None = None) -> Any:
    """Generator that yields raw places from the Park4Night API."""
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
    console.print(f"\n[bold yellow]Received {sig_name}, shutting down...[/bold yellow]")
    console.print("[bold green]✓ Shutting down.[/bold green]")
    sys.exit(0)


# ── Worker initializer (called once per process) ─────────────────────


def _worker_init(no_disk_cache: bool, translation_server_url: str) -> None:
    """Initialize worker process: set global flags.

    Models are NOT loaded in workers — they use the HTTP translation server.
    """
    global NO_DISK_CACHE, _translation_server_url
    NO_DISK_CACHE = no_disk_cache
    _translation_server_url = translation_server_url


# ── Worker function (must be top-level for pickling) ─────────────────


def _worker_process_place(raw_place: dict) -> dict:
    """Process a single place in a separate worker process.

    Does: scrape → translate → normalize.
    R2/DB enqueueing done by main process.
    """
    place_id = int(raw_place.get("id") or 0)
    place_start = time.time()

    api = Park4NightAPI()
    downloader = ImageDownloader()

    # ── Scrape (extract + download + reviews) ─
    t0 = time.time()
    scraped = scrape_place(raw_place, api, downloader)
    scrape_time = time.time() - t0
    if not scraped:
        return {"error": f"Failed to scrape place {place_id}"}

    # ── Translate ─
    t0 = time.time()
    translated = translate_place(scraped)
    translate_time = time.time() - t0

    # ── Normalize ─
    t0 = time.time()
    normalized = normalize_place_stage(translated)
    normalize_time = time.time() - t0
    if not normalized:
        return {"error": f"Failed to normalize place {place_id}"}

    place_elapsed = time.time() - place_start
    return {
        "place_id": place_id,
        "elapsed": place_elapsed,
        "scrape": scrape_time,
        "translate": translate_time,
        "normalize": normalize_time,
        "place": normalized,
    }


# ── Main Pipeline ────────────────────────────────────────────────────


def run_pipeline(
    limit: int | None = None,
    no_disk_cache: bool = False,
    dry_run: bool = False,
    no_translation_server: bool = False,
) -> None:
    """Run the full pipeline: extract → scrape → translate → normalize → upload."""
    global NO_DISK_CACHE, _stage_timers, _translation_server_url
    NO_DISK_CACHE = no_disk_cache

    num_workers = 16

    # Initialize R2 and DB worker pools
    r2_pool: R2WorkerPool | None = None
    if _r2_config is not None:
        r2_pool = R2WorkerPool(_r2_config, no_disk_cache=no_disk_cache, total_expected=limit or 0)
        r2_pool.start()

    db_pool: DBWorkerPool | None = None
    if os.environ.get("DATABASE_URL"):
        db_pool = DBWorkerPool(total_expected=limit or 0)
        db_pool.start()

    # Start translation server (single process, ThreadPoolExecutor for parallelism)
    if no_translation_server:
        console.print("[yellow]Translation server disabled — using local argos-translate[/yellow]")
        _translation_server_url = ""
    else:
        from translation_server import (  # type: ignore[import-not-found]
            get_server_url,
            start_server,
        )

        console.print("[bold cyan]Starting translation server...[/bold cyan]")
        start_server(install_packages=True, preload=True)
        _translation_server_url = get_server_url()
        console.print(f"  [green]✓ Translation server ready at {_translation_server_url}[/green]")

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

    # ── Phase 1: Extract ────────────────────────────────────────────
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
    logger.info(f"Extract phase: {total_places} places found in {extract_elapsed:.1f}s")

    if not total_places:
        console.print("[yellow]No places to process.[/yellow]")
        if r2_pool is not None:
            r2_pool.shutdown()
        if db_pool is not None:
            db_pool.shutdown()
        return

    _stage_timers = {
        "extract": StageTimer("Extract"),
        "scrape": StageTimer("Scrape"),
        "translate": StageTimer("Translate"),
        "normalize": StageTimer("Normalize"),
        "r2_upload": StageTimer("R2 Upload"),
        "db_insert": StageTimer("DB Insert"),
    }

    # ── Phase 2: Process ────────────────────────────────────────────
    console.print("\n[bold]Phase 2: Process[/bold] — scrape, translate, normalize...")
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
            initargs=(no_disk_cache, _translation_server_url),
        ) as executor:
            futures = {
                executor.submit(_worker_process_place, raw_place): (raw_place, grid_point)
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
                            _stage_timers["scrape"].add(result.get("scrape", 0))
                            _stage_timers["translate"].add(result.get("translate", 0))
                            _stage_timers["normalize"].add(result.get("normalize", 0))

                        # Enqueue R2 upload
                        t0 = time.time()
                        r2_task = enqueue_r2(place, r2_pool)
                        if r2_task is not None:
                            r2_task.done_event.wait()
                        r2_time = time.time() - t0

                        # Enqueue DB insert
                        t0 = time.time()
                        enqueue_db(place, db_pool)
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
                            f"scrape={result.get('scrape', 0):.3f}s, "
                            f"translate={result.get('translate', 0):.3f}s, "
                            f"normalize={result.get('normalize', 0):.3f}s, "
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

    # ── Phase 3: Finalize ───────────────────────────────────────────
    console.print("\n[bold]Phase 3: Finalize[/bold] — waiting for async uploads...")
    finalize_start = time.time()

    r2_progress_task: Any = None
    db_progress_task: Any = None
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
    logger.info(f"Finalize phase: {finalize_elapsed:.1f}s")

    # Shutdown translation server
    if _translation_server_url:
        from translation_server import stop_server  # type: ignore[import-not-found]

        stop_server()

    # ── Summary Report ──────────────────────────────────────────────
    total_elapsed = time.time() - pipeline_start
    console.print("\n[bold green]✓ Pipeline complete:[/bold green]")
    console.print(
        f"  Places: [green]{_stats['places_processed']}[/green] processed, "
        f"[red]{_stats.get('errors', 0)}[/red] errors"
    )
    console.print(f"  Images: [green]{_stats['images_downloaded']}[/green] downloaded")
    console.print(f"  Cache hits: [cyan]{_stats['cache_hits']}[/cyan]")
    console.print(f"  Cache misses: [cyan]{_stats['cache_misses']}[/cyan]")
    console.print(f"  Total time: [cyan]{total_elapsed:.1f}s[/cyan]")

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
        "Use --no-disk-cache to bypass all caches for performance metrics.",
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
        "--no-disk-cache",
        action="store_true",
        help="Bypass all disk caches — re-download, re-translate, re-upload",
    )
    parser.add_argument(
        "--no-translation-server",
        action="store_true",
        help="Skip HTTP translation server — use local argos-translate per worker (slower)",
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
    if args.no_disk_cache:
        console.print("  [yellow]Cache bypassed — all data will be re-processed[/yellow]")

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

    cache_stats = get_cache_stats()
    console.print(f"  Cache: [cyan]{cache_stats}[/cyan]")

    run_pipeline(
        limit=args.limit,
        no_disk_cache=args.no_disk_cache,
        dry_run=args.dry_run,
        no_translation_server=args.no_translation_server,
    )


if __name__ == "__main__":
    main()
