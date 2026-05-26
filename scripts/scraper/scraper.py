#!/usr/bin/env python3
"""
Park4Night Scraper

Scrapes all places and reviews from Park4Night using the guest API.
Supports multiprocessing, checkpoint/resume, and comprehensive data extraction.
Downloads place photos (thumbnails + large) and vehicle type icons locally.

Usage:
    python scraper.py scrape              # Run full scrape (places + reviews + images)
    python scraper.py scrape-places       # Scrape places only (with images)
    python scraper.py scrape-reviews      # Scrape reviews only
    python scraper.py download-images     # Download images for already-scraped places
    python scraper.py status              # Show current progress
    python scraper.py reset               # Reset checkpoint (start fresh)
    python scraper.py export              # Export data to final JSON files
"""

import argparse
import json
import logging
import os
import signal
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
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

# Allow running as script or module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import Park4NightAPI, create_api_client  # pyright: ignore[reportMissingImports]
from checkpoint import Checkpoint  # pyright: ignore[reportMissingImports]
from config import (
    ACTIVITY_CODES,
    DATA_DIR,
    IMAGE_WORKERS,
    PLACE_TYPE_CODES,
    PLACES_FILE,
    REVIEWS_FILE,
    SERVICE_CODES,
    WORKERS,
)
from images import create_image_downloader  # pyright: ignore[reportMissingImports]

# Rich console writes directly to the terminal (not captured by stdout redirect)
console = Console()
logger = logging.getLogger(__name__)

# Global checkpoint reference for signal handlers
_checkpoint: Checkpoint | None = None


def setup_logging() -> None:
    """Configure logging with dual output: console + log files.

    stdout  → scraper.log
    stderr  → scraper_error.log
    logger  → both console (rich) and scraper.log
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    log_file = os.path.join(DATA_DIR, "scraper.log")
    error_log_file = os.path.join(DATA_DIR, "scraper_error.log")

    # Redirect stdout → scraper.log
    stdout_log = open(log_file, "a", encoding="utf-8")
    sys.stdout = stdout_log

    # Redirect stderr → scraper_error.log
    stderr_log = open(error_log_file, "a", encoding="utf-8")
    sys.stderr = stderr_log

    # Console handler with rich formatting (writes to terminal, not stdout)
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=False,
        markup=False,
    )

    # File handler for detailed logging
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler],
        format="%(message)s",
    )


def _str(value: Any) -> str:
    """Safely convert a value to string, handling None."""
    return str(value).strip() if value is not None else ""


def download_place_photos(place_id: int, photos: list[dict], downloader=None) -> list[dict]:
    """
    Download photos for a place and return normalized photo dicts with relative paths.

    Each photo dict gets:
      - id, numero (metadata)
      - url_thumb, url_large (original CDN URLs as fallback)
      - path_thumb, path_large (relative paths to local files, if downloaded)
    """
    if downloader is None:
        downloader = create_image_downloader()
    return downloader.download_place_photos(place_id, photos)


def normalize_place(place: dict, downloader=None) -> dict:
    """
    Normalize a place from the guest API into a clean, consistent format.
    Extracts all available fields including services, activities, photos, etc.

    Args:
        place: Raw place dict from the API
        downloader: Optional ImageDownloader instance (creates new one if not provided)
    """
    place_id = int(place.get("id") or 0)

    # Determine which description to use (prefer English, fallback to French)
    description = (
        place.get("description_en")
        or place.get("description_fr")
        or place.get("description_de")
        or ""
    ).strip()

    # Extract services (boolean flags -> list of service names)
    services = []
    for key, label in SERVICE_CODES.items():
        if place.get(key) in ("1", 1, True, "true"):
            services.append({"code": key, "label": label})

    # Extract activities
    activities = []
    for key, label in ACTIVITY_CODES.items():
        if place.get(key) in ("1", 1, True, "true"):
            activities.append({"code": key, "label": label})

    # Place type
    type_code = place.get("code", "")
    place_type = PLACE_TYPE_CODES.get(type_code, type_code)

    # Photos (downloaded locally with relative paths)
    photos = download_place_photos(place_id, place.get("photos", []), downloader)

    # Contact details
    contact = {
        "phone": _str(place.get("tel")),
        "email": _str(place.get("mail")),
        "website": _str(place.get("site_internet")),
        "video": _str(place.get("video")),
    }

    # Address
    address = {
        "street": _str(place.get("route")),
        "city": _str(place.get("ville")),
        "zipcode": _str(place.get("code_postal")),
        "country": _str(place.get("pays")),
        "country_iso": _str(place.get("pays_iso")),
    }

    # Pricing
    pricing = {
        "parking": _str(place.get("prix_stationnement")),
        "services": _str(place.get("prix_services")),
    }

    # Access info
    access = {
        "public": bool(place.get("publique") in ("1", 1, True)),
        "height_limit": _str(place.get("hauteur_limite")),
        "parking_places": _str(place.get("nb_places")),
    }

    normalized = {
        "id": place_id,
        "title": _str(place.get("titre")),
        "name": _str(place.get("name")),
        "description": description,
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
        "type": {
            "code": type_code,
            "label": place_type,
        },
        "address": address,
        "pricing": pricing,
        "access": access,
        "contact": contact,
        "services": services,
        "activities": activities,
        "photos": photos,
        "rating": float(place.get("note_moyenne", 0)) if place.get("note_moyenne") else None,
        "review_count": int(place.get("nb_commentaires") or 0),
        "photo_count": int(place.get("nb_photos") or 0),
        "visit_count": int(place.get("nb_visites") or 0),
        "is_public": bool(place.get("publique") in ("1", 1, True)),
        "is_protected_nature": bool(place.get("nature_protect") in ("1", 1, True)),
        "is_top_list": bool(place.get("top_liste") in ("1", 1, True)),
        "contact_visible": bool(place.get("contact_visible") in ("1", 1, True)),
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

    return normalized


def fetch_place_reviews(api: Park4NightAPI, place_id: int) -> list[dict]:
    """Fetch reviews for a single place."""
    reviews = api.get_reviews_guest(place_id)
    if not reviews:
        return []

    normalized = []
    for review in reviews:
        normalized.append(
            {
                "id": review.get("id"),
                "place_id": place_id,
                "rating": int(review.get("note", 0)),
                "text": _str(review.get("commentaire")),
                "author": _str(review.get("uuid")),
                "author_id": _str(review.get("user_id")),
                "vehicle_type": _str(review.get("type_vehicule")),
                "created_at": _str(review.get("date_creation")),
                "social": {
                    "website": _str(review.get("url_web")),
                    "facebook": _str(review.get("url_facebook")),
                    "twitter": _str(review.get("url_twitter")),
                    "instagram": _str(review.get("url_instagram")),
                    "youtube": _str(review.get("url_youtube")),
                },
                "scraped_at": datetime.now(UTC).isoformat(),
            }
        )
    return normalized


def scrape_places_worker(args: tuple) -> tuple[str, int, int]:
    """
    Worker function for multiprocessing place scraping.
    Args: (lat, lng, worker_id)
    Returns: (grid_key, places_count, new_places_count)
    """
    lat, lng, worker_id = args
    grid_key = f"{lat},{lng}"

    try:
        api = create_api_client()
        downloader = create_image_downloader()
        places = api.get_places_guest(lat, lng)

        if not places:
            logger.info(f"[Worker {worker_id}] {grid_key}: No places found")
            return grid_key, 0, 0

        new_count = 0
        for place in places:
            try:
                normalized = normalize_place(place, downloader)
                with open(PLACES_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(normalized) + "\n")
                new_count += 1
            except Exception as e:
                logger.error(f"[Worker {worker_id}] Failed to normalize place: {e}")

        logger.info(
            f"[Worker {worker_id}] {grid_key}: Found {len(places)} places, wrote {new_count} new"
        )
        return grid_key, len(places), new_count
    except Exception as e:
        logger.error(f"[Worker {worker_id}] {grid_key}: Worker crashed: {e}")
        return grid_key, 0, 0


def scrape_reviews_worker(args: tuple) -> tuple[int, int]:
    """
    Worker function for multiprocessing review scraping.
    Args: (place_id, worker_id)
    Returns: (place_id, review_count)
    """
    place_id, worker_id = args

    try:
        api = create_api_client()
        reviews = fetch_place_reviews(api, place_id)

        if reviews:
            with open(REVIEWS_FILE, "a", encoding="utf-8") as f:
                for review in reviews:
                    f.write(json.dumps(review) + "\n")

        logger.info(f"[Worker {worker_id}] Place {place_id}: Fetched {len(reviews)} reviews")
        return place_id, len(reviews)
    except Exception as e:
        logger.error(f"[Worker {worker_id}] Place {place_id}: Worker crashed: {e}")
        return place_id, 0


def scrape_places(checkpoint: Checkpoint) -> None:
    """Scrape all places using multiprocessing with rich progress bar."""
    grid_points = Park4NightAPI.generate_grid_points()
    remaining = checkpoint.get_remaining_grid_points(grid_points)

    if not remaining:
        logger.info("All grid points already processed. Use 'reset' to start fresh.")
        return

    console.print(
        f"\n[bold blue]Starting place scrape:[/bold blue] "
        f"{len(remaining)} grid points remaining (of {len(grid_points)} total)"
    )

    worker_args = [(lat, lng, i % WORKERS) for i, (lat, lng) in enumerate(remaining)]

    total_places = 0
    completed = 0
    total_to_scrape = len(remaining)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TextColumn("[cyan]{task.fields[places]} places[/cyan]"),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scraping places", total=total_to_scrape, places=0)

        with ProcessPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(scrape_places_worker, args): args for args in worker_args}

            for future in as_completed(futures):
                grid_key, count, new_count = future.result()
                checkpoint.mark_grid_point_done(
                    float(grid_key.split(",")[0]),
                    float(grid_key.split(",")[1]),
                )
                total_places += new_count
                completed += 1
                progress.update(task, completed=completed, places=total_places)

    console.print(
        f"[bold green]✓ Place scrape complete:[/bold green] "
        f"{total_places} total places from {completed} grid points"
    )


def scrape_reviews(checkpoint: Checkpoint) -> None:
    """Scrape reviews for all known places using multiprocessing."""
    # Load all unique place IDs from places file
    place_ids = set()
    if os.path.exists(PLACES_FILE):
        with open(PLACES_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    place = json.loads(line)
                    place_ids.add(place["id"])
                except (json.JSONDecodeError, KeyError):
                    continue

    # Also load place IDs that already have reviews in the reviews file
    # This ensures we don't re-fetch reviews after a crash
    # Use regex for speed instead of full JSON parsing
    if os.path.exists(REVIEWS_FILE):
        import re

        place_id_pattern = re.compile(r'"place_id":\s*(\d+)')
        found_ids = set()
        with open(REVIEWS_FILE, encoding="utf-8") as f:
            for line in f:
                match = place_id_pattern.search(line)
                if match:
                    found_ids.add(int(match.group(1)))
        # Mark all found place IDs as having reviews fetched
        for pid in found_ids:
            checkpoint.mark_reviews_fetched(pid)
        logger.info(f"Loaded {len(found_ids)} existing place IDs from reviews file")

    # Filter to places needing reviews
    ids_needing_reviews = checkpoint.get_places_needing_reviews(list(place_ids))

    if not ids_needing_reviews:
        console.print(
            "[bold yellow]All reviews already fetched.[/bold yellow] Use 'reset' to start fresh."
        )
        return

    console.print(
        f"\n[bold blue]Starting review scrape:[/bold blue] "
        f"{len(ids_needing_reviews)} places need reviews (of {len(place_ids)} total)"
    )

    worker_args = [(pid, i % WORKERS) for i, pid in enumerate(ids_needing_reviews)]

    total_reviews = 0
    completed = 0
    total_to_scrape = len(ids_needing_reviews)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TextColumn("[cyan]{task.fields[reviews]} reviews[/cyan]"),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scraping reviews", total=total_to_scrape, reviews=0)

        with ProcessPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(scrape_reviews_worker, args): args for args in worker_args}

            for future in as_completed(futures):
                place_id, count = future.result()
                checkpoint.mark_reviews_fetched(place_id)
                total_reviews += count
                completed += 1
                progress.update(task, completed=completed, reviews=total_reviews)

                if completed % 500 == 0 or completed == total_to_scrape:
                    checkpoint._save()  # Save checkpoint periodically

    console.print(
        f"[bold green]✓ Review scrape complete:[/bold green] "
        f"{total_reviews} reviews from {completed} places"
    )


def show_status(checkpoint: Checkpoint) -> None:
    """Show current scraper status."""
    summary = checkpoint.get_summary()
    grid_points = Park4NightAPI.generate_grid_points()
    remaining = checkpoint.get_remaining_grid_points(grid_points)

    print("\n=== Park4Night Scraper Status ===\n")
    print(f"  Created:          {summary['created_at']}")
    print(f"  Last updated:     {summary['last_updated']}")
    print()
    print(
        f"  Grid points:      {summary['grid_points_completed']}/{len(grid_points)} "
        f"({len(remaining)} remaining)"
    )
    print(f"  Places fetched:   {summary['places_fetched']}")
    print(f"  Reviews fetched:  {summary['reviews_fetched']}")
    print(f"  Errors:           {summary['errors']}")
    print()

    # Show file sizes
    for fname in ["places.jsonl", "reviews.jsonl", "checkpoint.json"]:
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.exists(fpath):
            size = os.path.getsize(fpath)
            if size > 1024 * 1024:
                print(f"  {fname}: {size / (1024 * 1024):.1f} MB")
            elif size > 1024:
                print(f"  {fname}: {size / 1024:.1f} KB")
            else:
                print(f"  {fname}: {size} bytes")
    print()


def export_data() -> None:
    """Export scraped data to consolidated JSON files."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # Export places
    places = []
    if os.path.exists(PLACES_FILE):
        with open(PLACES_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    places.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Deduplicate by ID (keep latest)
    places_by_id = {}
    for place in places:
        pid = place["id"]
        if pid not in places_by_id or place.get("scraped_at", "") > places_by_id[pid].get(
            "scraped_at", ""
        ):
            places_by_id[pid] = place

    places_list = list(places_by_id.values())
    places_file = os.path.join(DATA_DIR, "places_export.json")
    with open(places_file, "w", encoding="utf-8") as f:
        json.dump(places_list, f, indent=2, ensure_ascii=False)

    # Export reviews
    reviews = []
    if os.path.exists(REVIEWS_FILE):
        with open(REVIEWS_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    reviews.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    reviews_file = os.path.join(DATA_DIR, "reviews_export.json")
    with open(reviews_file, "w", encoding="utf-8") as f:
        json.dump(reviews, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(places_list)} places to {places_file}")
    print(f"Exported {len(reviews)} reviews to {reviews_file}")


def download_images_worker(args: tuple) -> tuple[int, int, int]:
    """
    Worker function for downloading images for already-scraped places.
    Args: (place_id, worker_id)
    Returns: (place_id, photos_downloaded, total_photos)
    """
    place_id, worker_id = args

    try:
        downloader = create_image_downloader()
        # Read place data from places file
        place_data = None
        if os.path.exists(PLACES_FILE):
            with open(PLACES_FILE, encoding="utf-8") as f:
                for line in f:
                    try:
                        place = json.loads(line)
                        if place.get("id") == place_id:
                            place_data = place
                            break
                    except json.JSONDecodeError:
                        continue

        if not place_data:
            logger.warning(f"[Worker {worker_id}] Place {place_id} not found in places file")
            return place_id, 0, 0

        photos = place_data.get("photos", [])
        if not photos:
            return place_id, 0, 0

        # Check if photos already have local paths (already downloaded)
        all_downloaded = all("path_thumb" in photo and "path_large" in photo for photo in photos)
        if all_downloaded:
            logger.info(f"[Worker {worker_id}] Place {place_id}: Images already downloaded")
            return place_id, 0, len(photos)

        # Download photos
        new_photos = downloader.download_place_photos(place_id, photos)

        # Update place data with new photo paths
        place_data["photos"] = new_photos
        with open(PLACES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(place_data) + "\n")

        downloaded_count = sum(
            1 for photo in new_photos if "path_thumb" in photo or "path_large" in photo
        )
        logger.info(
            f"[Worker {worker_id}] Place {place_id}: "
            f"Downloaded {downloaded_count}/{len(photos)} photos"
        )
        return place_id, downloaded_count, len(photos)
    except Exception as e:
        logger.error(f"[Worker {worker_id}] Place {place_id}: Worker crashed: {e}")
        return place_id, 0, 0


def download_images(checkpoint: Checkpoint, place_id_filter: int | None = None) -> None:
    """
    Download images for all already-scraped places.
    Can be run independently of place scraping.
    """
    # Load all unique place IDs from places file
    place_ids = []
    if os.path.exists(PLACES_FILE):
        with open(PLACES_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    place = json.loads(line)
                    pid = place.get("id")
                    if pid and (place_id_filter is None or pid == place_id_filter):
                        place_ids.append(pid)
                except json.JSONDecodeError:
                    continue

    # Deduplicate (keep last occurrence - latest data)
    seen = set()
    unique_ids = []
    for pid in reversed(place_ids):
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    place_ids = list(reversed(unique_ids))

    if not place_ids:
        console.print("[bold yellow]No places found to download images for.[/bold yellow]")
        return

    console.print(f"\n[bold blue]Starting image download:[/bold blue] {len(place_ids)} places")

    worker_args = [(pid, i % IMAGE_WORKERS) for i, pid in enumerate(place_ids)]

    total_downloaded = 0
    total_photos = 0
    completed = 0
    total_to_process = len(place_ids)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TextColumn("[cyan]{task.fields[photos]} photos[/cyan]"),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading images", total=total_to_process, photos=0)

        with ProcessPoolExecutor(max_workers=IMAGE_WORKERS) as executor:
            futures = {executor.submit(download_images_worker, args): args for args in worker_args}

            for future in as_completed(futures):
                place_id, downloaded, photo_count = future.result()
                total_downloaded += downloaded
                total_photos += photo_count
                completed += 1
                progress.update(task, completed=completed, photos=total_downloaded)

    console.print(
        f"[bold green]✓ Image download complete:[/bold green] "
        f"{total_downloaded} photos from {completed} places ({total_photos} total photos)"
    )


def _handle_signal(signum: int, frame: Any) -> None:
    """Handle SIGINT/SIGTERM by saving checkpoint and exiting gracefully."""
    global _checkpoint
    sig_name = signal.Signals(signum).name
    console.print(f"\n[bold yellow]Received {sig_name}, saving checkpoint...[/bold yellow]")
    if _checkpoint is not None:
        _checkpoint._save()
        console.print("[bold green]✓ Checkpoint saved. Resume with 'scrape-reviews'.[/bold green]")
    sys.exit(0)


def main() -> None:
    """Main entry point."""
    global _checkpoint
    setup_logging()

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    parser = argparse.ArgumentParser(description="Park4Night Scraper")
    parser.add_argument(
        "command",
        choices=[
            "scrape",
            "scrape-places",
            "scrape-reviews",
            "download-images",
            "download-icons",
            "status",
            "reset",
            "export",
        ],
        help="Command to run",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=WORKERS,
        help=f"Number of parallel workers (default: {WORKERS})",
    )
    parser.add_argument(
        "--place-id",
        type=int,
        default=None,
        help="Filter to a specific place ID (for download-images)",
    )

    args = parser.parse_args()
    _checkpoint = Checkpoint()

    if args.command == "scrape":
        logger.info("Starting full scrape (places + reviews)")
        scrape_places(_checkpoint)
        scrape_reviews(_checkpoint)
        logger.info("Full scrape complete!")

    elif args.command == "scrape-places":
        scrape_places(_checkpoint)

    elif args.command == "scrape-reviews":
        scrape_reviews(_checkpoint)

    elif args.command == "status":
        show_status(_checkpoint)

    elif args.command == "reset":
        _checkpoint.reset()
        # Also clear data files
        for fname in [PLACES_FILE, REVIEWS_FILE]:
            if os.path.exists(fname):
                os.remove(fname)
                logger.info(f"Removed {fname}")
        print("Checkpoint and data files reset. Ready for fresh scrape.")

    elif args.command == "download-images":
        download_images(_checkpoint, args.place_id)

    elif args.command == "download-icons":
        downloader = create_image_downloader()
        icons = downloader.download_vehicle_icons()
        console.print(f"[bold green]✓ Downloaded {len(icons)} vehicle type icons[/bold green]")

    elif args.command == "export":
        export_data()


if __name__ == "__main__":
    main()
