#!/usr/bin/env python3
"""
Park4Night Unified ETL Pipeline

True per-place generator pipeline:
  Each place flows through ALL stages before the next begins.
  --limit N means the pipeline iterates N times, each time
  processing one place completely end-to-end.

    extract → translate → normalize → upload R2 → insert DB
    → checkpoint (save progress)
    → next place

Parallelism: within each stage (image downloads, translations, R2 uploads)
Caching: translation cache in RAM, checkpoint on disk for resume
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
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
    get_cache_size,
    translate_batch,
)

logger = logging.getLogger("pipeline")


# ── Globals (for signal handling) ─────────────────
_checkpoint: PipelineCheckpoint | None = None
_r2_config: dict | None = None
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
        translations = translate_batch(texts_to_translate, max_workers=64)
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


# ── Stage 4: Enqueue R2 upload (non-blocking) ─
def stage_enqueue_r2(place: dict, r2_pool: R2WorkerPool | None) -> dict:
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


# ── Stage 5: Insert DB (place + reviews into Supabase) ─
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
    place_id = place["id"]
    reviews = place.get("reviews") or []  # empty list is valid (no reviews for this place)

    # Enqueue place + pre-normalized reviews for async insert
    db_pool.enqueue(place, reviews)
    _stats["db_inserts"] += 1


# ── Generator: yield raw places from API ──────────
def place_source(api: Park4NightAPI, checkpoint: PipelineCheckpoint, limit: int | None = None):
    """Generator that yields raw places from the Park4Night API.

    Respects checkpoint to skip already-processed grid points.
    Yields one raw place dict at a time, up to `limit` places.
    """
    grid_points = Park4NightAPI.generate_grid_points()
    remaining = checkpoint.get_remaining_grid_points(grid_points)

    if not remaining:
        console.print("  [yellow]All grid points already processed.[/yellow]")
        return

    limit_msg = f" (limit: {limit} places)" if limit else ""
    console.print(f"  [bold blue]{len(remaining)}[/bold blue] grid points remaining{limit_msg}")

    total_yielded = 0

    for lat, lng in remaining:
        if limit is not None and total_yielded >= limit:
            break

        places = api.get_places(lat, lng)
        if not places:
            checkpoint.mark_grid_point_done(lat, lng)
            continue

        for place in places:
            if limit is not None and total_yielded >= limit:
                break

            place_id = int(place.get("id") or 0)

            # Skip fully processed places
            if checkpoint.is_place_fully_processed(place_id):
                continue

            yield place
            total_yielded += 1

        checkpoint.mark_grid_point_done(lat, lng)


# ── Signal Handling ────────────────────────────────
def _handle_signal(signum, frame) -> None:
    """Handle SIGINT/SIGTERM gracefully."""
    sig_name = signal.Signals(signum).name
    console.print(f"\n[bold yellow]Received {sig_name}, saving checkpoint...[/bold yellow]")
    if _checkpoint is not None:
        _checkpoint._save()
        console.print("[bold green]✓ Checkpoint saved.[/bold green]")
    sys.exit(0)


# ── Main Pipeline ─────────────────────────────────
def run_pipeline(
    api: Park4NightAPI, checkpoint: PipelineCheckpoint, limit: int | None = None
) -> None:
    """Run the per-place generator pipeline.

    Each place flows through all stages sequentially:
      extract → download images → translate → enqueue R2 → normalize → enqueue DB
    Checkpoint saved after each place for resume capability.
    """
    downloader = ImageDownloader()

    # Setup R2 worker pool (async queue-based uploads)
    r2_pool: R2WorkerPool | None = None
    if _r2_config is not None:
        r2_pool = R2WorkerPool(_r2_config)
        r2_pool.start()

    # Setup DB worker pool (async queue-based inserts)
    db_pool: DBWorkerPool | None = None
    if os.environ.get("DATABASE_URL"):
        db_pool = DBWorkerPool()
        if db_pool is not None:
            db_pool.start()

    # Progress tracking
    limit_label = f" (limit {limit})" if limit else ""
    console.print(f"\n[bold cyan]Starting pipeline{limit_label}...[/bold cyan]\n")

    with create_progress("Pipeline", total=limit) as progress:
        task = progress.add_task("Processing", total=limit or None)
        place_num = 0

        for raw_place in place_source(api, checkpoint, limit):
            place_id = int(raw_place.get("id") or 0)
            place_num += 1
            place_start = time.time()

            console.print(f"\n[bold]Place {place_num}:[/bold] [cyan]{place_id}[/cyan]")
            console.print(f"  Title: {raw_place.get('titre', 'N/A')}")

            # ── Stage 1: Extract (structure raw API data) ─
            t0 = time.time()
            console.print("  [dim]→ extract[/dim]")
            place = extract_place_data(raw_place)
            extract_time = time.time() - t0
            if not place:
                console.print(f"  [red]✗ Failed to extract place {place_id}[/red]")
                continue

            # ── Stage 1b: Download images ─
            t0 = time.time()
            console.print("  [dim]→ download images[/dim]")
            place["_raw_photos"] = raw_place.get("photos", [])
            place = download_images(place, downloader)
            download_time = time.time() - t0

            # ── Stage 1c: Fetch reviews ─
            t0 = time.time()
            console.print("  [dim]→ fetch reviews[/dim]")
            place["reviews"] = api.get_reviews(place_id)
            fetch_time = time.time() - t0

            # ── Stage 2: Translate (place + reviews) ─
            t0 = time.time()
            console.print("  [dim]→ translate[/dim]")
            place = stage_translate(place)
            translate_time = time.time() - t0

            # ── Stage 3: Enqueue R2 upload (non-blocking) ─
            t0 = time.time()
            console.print("  [dim]→ enqueue R2[/dim]")
            place = stage_enqueue_r2(place, r2_pool)
            r2_time = time.time() - t0

            # ── Stage 4: Normalize (clean tables, no translation) ─
            t0 = time.time()
            console.print("  [dim]→ normalize[/dim]")
            place = stage_normalize(place)
            normalize_time = time.time() - t0
            if not place:
                console.print(f"  [red]✗ Failed to normalize place {place_id}[/red]")
                continue

            # ── Stage 5: Enqueue DB insert (non-blocking) ─
            t0 = time.time()
            console.print("  [dim]→ enqueue DB[/dim]")
            stage_enqueue_db(place, db_pool)
            db_time = time.time() - t0

            # ── Checkpoint (save progress after each place) ─
            checkpoint._save()
            _stats["places_processed"] += 1
            place_elapsed = time.time() - place_start

            if limit:
                progress.update(task, completed=place_num)

            # Per-place timing summary
            rate = (
                place_num
                / sum(
                    t
                    for t in [
                        extract_time,
                        download_time,
                        fetch_time,
                        translate_time,
                        r2_time,
                        normalize_time,
                        db_time,
                    ]
                    if t > 0
                )
                if place_elapsed > 0
                else 0
            )
            console.print(
                f"  [bold green]✓ Place {place_id} complete "
                f"({place_elapsed:.2f}s, {rate:.1f} places/s)[/bold green]"
            )

            # Log detailed timing
            logger.info(
                f"Place {place_num} ({place_id}): "
                f"total={place_elapsed:.3f}s | "
                f"extract={extract_time:.3f}s, "
                f"download={download_time:.3f}s, "
                f"translate={translate_time:.3f}s, "
                f"r2={r2_time:.3f}s, "
                f"normalize={normalize_time:.3f}s, "
                f"db={db_time:.3f}s | "
                f"rate={rate:.2f} places/s"
            )

    # Cleanup: wait for all uploads/inserts to finish, then shut down workers
    if r2_pool is not None:
        console.print("\n[dim]Waiting for R2 uploads to complete...[/dim]")
        r2_pool.shutdown()

    if db_pool is not None:
        console.print("[dim]Waiting for DB inserts to complete...[/dim]")
        db_pool.shutdown()


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

    start_time = time.time()

    # ── Run pipeline ───────────────────────
    api = Park4NightAPI()
    run_pipeline(api, _checkpoint, limit=args.limit)

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
