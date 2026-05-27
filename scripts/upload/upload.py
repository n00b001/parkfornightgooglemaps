#!/usr/bin/env python3
"""
Park4Night Data Uploader

Uploads normalised Park4Night data to Cloudflare R2 (images) and Supabase
(PostgreSQL database).

Two-phase process:
  Phase 1 — Upload images to Cloudflare R2, collect URLs
  Phase 2 — Upload database records to Supabase with correct image URLs

Features:
  - Multithreaded image uploads with progress bars
  - Timestamped log files
  - CLI arguments for limiting scope
  - Resume capability (skips already-uploaded images)
  - Bulk inserts to PostgreSQL

Usage:
    # Upload everything:
    uv run upload.py

    # Upload first 10 places only:
    uv run upload.py --places 10

    # Custom config paths:
    uv run upload.py --env /path/to/.env --config /path/to/config.json

    # Dry run (list without uploading):
    uv run upload.py --dry-run

    # Upload only images or only database:
    uv run upload.py --section images
    uv run upload.py --section database

Requires:
    .env file with: SUPABASE_URL, SUPABASE_SERVICE_KEY
    config.json with R2 credentials (accessKeyId, secretAccessKey, endpoint, bucket)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

import psycopg2
from boto3 import client as r2_client
from dotenv import load_dotenv
from psycopg2.extras import execute_values
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)

# ── Globals ──────────────────────────────────────────────────────────

console = Console()
logger: logging.Logger | None = None

# R2 URL template (public bucket URL)
R2_PUBLIC_URL_TEMPLATE = "https://p4n-images.{bucket_hash}.cdn.cloudflare.com"


# ── Configuration ────────────────────────────────────────────────────


def load_config(config_path: str) -> dict:
    """Load R2 configuration from JSON file."""
    if not os.path.exists(config_path):
        console.print(f"[bold red]ERROR:[/bold red] Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    required_keys = ["accessKeyId", "secretAccessKey", "endpoint", "bucket"]
    for key in required_keys:
        if key not in config:
            console.print(f"[bold red]ERROR:[/bold red] Missing key in config: {key}")
            sys.exit(1)

    return config


def load_env(env_path: str) -> dict[str, str]:
    """Load environment variables from .env file."""
    if not os.path.exists(env_path):
        console.print(f"[bold red]ERROR:[/bold red] .env file not found: {env_path}")
        sys.exit(1)

    load_dotenv(env_path)
    return {
        "SUPABASE_URL": os.environ.get("SUPABASE_URL", ""),
        "SUPABASE_SERVICE_KEY": os.environ.get("SUPABASE_SERVICE_KEY", ""),
    }


# ── Logging ──────────────────────────────────────────────────────────


def setup_logging(log_dir: str) -> None:
    """Configure logging with dual output: console + timestamped log file."""
    global logger

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"upload_{timestamp}.log")

    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=False,
        markup=False,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )

    logger = logging.getLogger("upload")
    logger.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    console.print(f"  Log file: [cyan]{log_file}[/cyan]")


# ── Data Loading ─────────────────────────────────────────────────────


def load_jsonl(filepath: str) -> list[dict]:
    """Load a JSONL file."""
    records = []
    if not os.path.exists(filepath):
        return records

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def load_normalized_data(data_dir: str) -> dict[str, list[dict]]:
    """Load all normalised data files."""
    normalized_dir = os.path.join(data_dir, "normalized")

    if not os.path.exists(normalized_dir):
        console.print(
            f"[bold red]ERROR:[/bold red] Normalised data not found: {normalized_dir}\n"
            f"Run the normalise script first: uv run scripts/normalize/normalize.py"
        )
        sys.exit(1)

    return {
        "places": load_jsonl(os.path.join(normalized_dir, "places.jsonl")),
        "reviews": load_jsonl(os.path.join(normalized_dir, "reviews.jsonl")),
        "place_types": load_jsonl(os.path.join(normalized_dir, "place_types.jsonl")),
        "services": load_jsonl(os.path.join(normalized_dir, "services.jsonl")),
        "activities": load_jsonl(os.path.join(normalized_dir, "activities.jsonl")),
        "vehicle_types": load_jsonl(os.path.join(normalized_dir, "vehicle_types.jsonl")),
    }


# ── Image Collection ─────────────────────────────────────────────────


def collect_images(places: list[dict], images_base_dir: str) -> list[dict]:
    """
    Collect all image files that need to be uploaded.

    Returns list of dicts:
      {
        "place_id": int,
        "photo_id": str,
        "local_path": str,  # path to local file
        "r2_key": str,      # key in R2 bucket
        "size": int,
        "type": "thumb" | "large",
      }
    """
    images: list[dict] = []

    for place in places:
        place_id = place["id"]
        for photo in place.get("photos", []):
            photo_id = photo.get("id", "")
            if not photo_id:
                continue

            for img_type, path_key in [("thumb", "path_thumb"), ("large", "path_large")]:
                relative_path = photo.get(path_key, "")
                if not relative_path:
                    continue

                # The path could be a local path or a CDN URL
                # For local paths, construct the full path
                if relative_path.startswith("http"):
                    # Already a URL — skip (shouldn't happen with normalised data)
                    continue

                # Try to find the file in images directory
                # Path format: images/places/{place_id}/{photo_id}_thumb.jpg
                local_path = os.path.join(
                    images_base_dir, "places", str(place_id), f"{photo_id}_{img_type}.jpg"
                )

                # Also try .webp
                if not os.path.exists(local_path):
                    local_path_webp = local_path.replace(".jpg", ".webp")
                    if os.path.exists(local_path_webp):
                        local_path = local_path_webp

                if not os.path.exists(local_path):
                    continue

                # Build R2 key
                ext = os.path.splitext(local_path)[1] or ".jpg"
                r2_key = f"places/{place_id}/{photo_id}_{img_type}{ext}"

                images.append({
                    "place_id": place_id,
                    "photo_id": photo_id,
                    "local_path": local_path,
                    "r2_key": r2_key,
                    "size": os.path.getsize(local_path),
                    "type": img_type,
                })

    return images


# ── R2 Upload ────────────────────────────────────────────────────────


def create_r2_client(config: dict) -> Any:
    """Create an R2-compatible S3 client."""
    return r2_client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["accessKeyId"],
        aws_secret_access_key=config["secretAccessKey"],
        region_name=config.get("region", "auto"),
    )


def upload_image_to_r2(r2, image: dict, bucket: str) -> str | None:
    """Upload a single image to R2. Returns public URL or None on failure."""
    r2_key = image["r2_key"]
    local_path = image["local_path"]

    try:
        # Check if already exists
        try:
            r2.head_object(Bucket=bucket, Key=r2_key)
            return build_r2_url(config_get_bucket(), r2_key)
        except r2.exceptions.ClientError:
            pass  # Object doesn't exist, proceed with upload

        content_type = "image/webp" if local_path.endswith(".webp") else "image/jpeg"

        r2.put_object(
            Bucket=bucket,
            Key=r2_key,
            Body=open(local_path, "rb"),
            ContentType=content_type,
        )

        return build_r2_url(bucket, r2_key)

    except Exception as e:
        if logger:
            logger.error(f"Failed to upload {r2_key}: {e}")
        return None


def config_get_bucket() -> str:
    """Get bucket from global config."""
    return _global_config["bucket"]


def build_r2_url(bucket: str, key: str) -> str:
    """Build public URL for an R2 object.

    Cloudflare R2 public URLs follow the pattern:
    https://{account_id}.r2.dev/{bucket}/{key}
    or if a custom domain is configured, that domain is used.

    For now, we construct from the endpoint URL.
    """
    endpoint = _global_config["endpoint"]
    # Endpoint looks like: https://cc878f6279e2f7efcb86549a41ceeb53.r2.cloudflarestorage.com
    # Public URL: https://cc878f6279e2f7efcb86549a41ceeb53.r2.dev/{bucket}/{key}
    # Extract the account hash from endpoint
    if "r2.cloudflarestorage.com" in endpoint:
        host = endpoint.replace("https://", "").replace(".r2.cloudflarestorage.com", "")
        return f"https://{host}.r2.dev/{bucket}/{key}"
    else:
        # Fallback: use endpoint directly
        return f"{endpoint.rstrip('/')}/{bucket}/{key}"


# Global config reference (set during main())
_global_config: dict = {}


def upload_images_phase(
    r2: Any,
    images: list[dict],
    bucket: str,
    max_workers: int = 16,
) -> dict[int, dict[str, dict[str, str]]]:
    """
    Upload all images to R2. Returns mapping of:
      place_id -> {photo_id -> {"thumb": url, "large": url}}
    """
    total = len(images)
    if not total:
        console.print("  [yellow]No images to upload.[/yellow]")
        return {}

    if logger:
        logger.info(f"Uploading {total:,} images to R2 bucket '{bucket}'")

    # Track results
    url_map: dict[int, dict[str, dict[str, str]]] = {}
    uploaded = 0
    skipped = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TransferSpeedColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Uploading to R2", total=total)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(upload_image_to_r2, r2, img, bucket): img
                for img in images
            }

            total_bytes = 0
            for future in as_completed(futures):
                image = futures[future]
                try:
                    url = future.result()
                    if url:
                        place_id = image["place_id"]
                        photo_id = image["photo_id"]
                        img_type = image["type"]

                        if place_id not in url_map:
                            url_map[place_id] = {}
                        if photo_id not in url_map[place_id]:
                            url_map[place_id][photo_id] = {}
                        url_map[place_id][photo_id][img_type] = url

                        uploaded += 1
                        total_bytes += image["size"]
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    if logger:
                        logger.error(f"Unexpected error for {image['r2_key']}: {e}")

                progress.update(
                    task,
                    completed=uploaded + skipped + failed,
                    visible=True,
                )

    if logger:
        logger.info(
            f"R2 upload complete: {uploaded:,} uploaded, "
            f"{skipped:,} skipped, {failed:,} failed"
        )

    return url_map


# ── Update Place Records with R2 URLs ────────────────────────────────


def update_place_photo_urls(
    places: list[dict],
    url_map: dict[int, dict[str, dict[str, str]]],
) -> None:
    """Update place photo records with R2 URLs (in-place)."""
    updated = 0

    for place in places:
        place_id = place["id"]
        photo_urls = url_map.get(place_id, {})

        for photo in place.get("photos", []):
            photo_id = photo.get("id", "")
            urls = photo_urls.get(photo_id, {})

            if "thumb" in urls:
                photo["r2_url_thumb"] = urls["thumb"]
                updated += 1
            if "large" in urls:
                photo["r2_url_large"] = urls["large"]
                updated += 1

    if logger:
        logger.info(f"Updated {updated} photo URLs across {len(places)} places")


# ── Supabase Upload ──────────────────────────────────────────────────


def get_supabase_connection(env_vars: dict) -> psycopg2.extensions.connection:
    """Get Supabase PostgreSQL connection."""
    supabase_url = env_vars.get("SUPABASE_URL", "")

    if not supabase_url:
        console.print("[bold red]ERROR:[/bold red] SUPABASE_URL not set in .env file")
        sys.exit(1)

    # Supabase URL is like: https://xyz.supabase.co
    # We need the PostgreSQL connection string
    # The DATABASE_URL format for Supabase is typically provided separately
    # Try to construct from SUPABASE_URL or use DATABASE_URL directly
    database_url = os.environ.get("DATABASE_URL", "")

    if not database_url:
        # Try to construct from SUPABASE_URL
        # Format: postgresql://postgres.{project_ref}:{password}@{host}:5432/postgres
        console.print(
            "[bold yellow]WARNING:[/bold yellow] DATABASE_URL not set. "
            "Set it in your .env file for Supabase PostgreSQL connection."
        )
        console.print(
            "[bold yellow]   Format:[/bold yellow] "
            "postgresql://postgres.{project_ref}:{password}@db.{project_ref}.supabase.co:5432/postgres"
        )
        sys.exit(1)

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        return conn
    except psycopg2.OperationalError as e:
        console.print(f"[bold red]ERROR:[/bold red] Failed to connect to database: {e}")
        sys.exit(1)


def ensure_schema(conn: psycopg2.extensions.connection) -> None:
    """Ensure the database schema exists."""
    cur = conn.cursor()
    cur.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'Place')"
    )
    row = cur.fetchone()
    if not row or not row[0]:
        console.print(
            "[bold red]ERROR:[/bold red] Database tables don't exist.\n"
            "Run migrations first: npx prisma migrate deploy --schema=server/prisma/schema.prisma"
        )
        conn.close()
        sys.exit(1)
    cur.close()


def create_system_user(conn: psycopg2.extensions.connection) -> str:
    """Create a system user for scraped review foreign keys."""
    cur = conn.cursor()
    system_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "scraped-import-system-user"))

    cur.execute(
        """
        INSERT INTO "User" (id, googleId, email)
        VALUES (%s, 'scraped-import', 'scraped@import.local')
        ON CONFLICT (googleId) DO UPDATE SET id = EXCLUDED.id
        RETURNING id
        """,
        (system_user_id,),
    )
    conn.commit()
    row = cur.fetchone()
    user_id = row[0] if row else system_user_id
    cur.close()
    return user_id


def upload_lookup_tables(
    conn: psycopg2.extensions.connection,
    data: dict[str, list[dict]],
) -> None:
    """Upload lookup tables (PlaceType, Service, Activity, VehicleType)."""
    cur = conn.cursor()

    # ── PlaceType ─────────────────────────────────────────────────
    for pt in data["place_types"]:
        try:
            cur.execute(
                """
                INSERT INTO "PlaceType" (englishName, originalCode)
                VALUES (%s, %s)
                ON CONFLICT (originalCode) DO UPDATE SET englishName = EXCLUDED.englishName
                """,
                (pt.get("english_name", pt.get("code", "")), pt.get("code", "")),
            )
        except Exception as e:
            if logger:
                logger.error(f"Failed to insert PlaceType {pt}: {e}")

    # ── Service ───────────────────────────────────────────────────
    for svc in data["services"]:
        try:
            cur.execute(
                """
                INSERT INTO "Service" (code, label, originalCode)
                VALUES (%s, %s, %s)
                ON CONFLICT (originalCode) DO UPDATE SET label = EXCLUDED.label
                """,
                (
                    svc.get("code", ""),
                    svc.get("label", ""),
                    svc.get("original_code", ""),
                ),
            )
        except Exception as e:
            if logger:
                logger.error(f"Failed to insert Service {svc}: {e}")

    # ── Activity ──────────────────────────────────────────────────
    for act in data["activities"]:
        try:
            cur.execute(
                """
                INSERT INTO "Activity" (code, label, originalCode)
                VALUES (%s, %s, %s)
                ON CONFLICT (originalCode) DO UPDATE SET label = EXCLUDED.label
                """,
                (
                    act.get("code", ""),
                    act.get("label", ""),
                    act.get("original_code", ""),
                ),
            )
        except Exception as e:
            if logger:
                logger.error(f"Failed to insert Activity {act}: {e}")

    # ── VehicleType ───────────────────────────────────────────────
    for vt in data["vehicle_types"]:
        try:
            cur.execute(
                """
                INSERT INTO "VehicleType" (code, originalCode)
                VALUES (%s, %s)
                ON CONFLICT (originalCode) DO NOTHING
                """,
                (vt.get("code", ""), vt.get("original_code", "")),
            )
        except Exception as e:
            if logger:
                logger.error(f"Failed to insert VehicleType {vt}: {e}")

    conn.commit()
    cur.close()

    if logger:
        logger.info(
            f"Lookup tables: {len(data['place_types'])} place types, "
            f"{len(data['services'])} services, "
            f"{len(data['activities'])} activities, "
            f"{len(data['vehicle_types'])} vehicle types"
        )


def upload_places(
    conn: psycopg2.extensions.connection,
    places: list[dict],
) -> None:
    """Upload places to Supabase."""
    total = len(places)
    if not total:
        return

    if logger:
        logger.info(f"Uploading {total:,} places to Supabase")

    cur = conn.cursor()

    # Get existing place IDs
    cur.execute('SELECT id FROM "Place"')
    existing_ids = {row[0] for row in cur.fetchall()}
    new_places = [p for p in places if p["id"] not in existing_ids]
    skipped = total - len(new_places)

    if skipped and logger:
        logger.info(f"Skipping {skipped:,} existing places")

    if not new_places:
        console.print("  [yellow]All places already in database.[/yellow]")
        cur.close()
        return

    # Build type code -> ID mapping
    cur.execute('SELECT id, originalCode FROM "PlaceType"')
    type_map = {row[1]: row[0] for row in cur.fetchall()}
    cur.execute('SELECT id, originalCode FROM "Service"')
    service_map = {row[1]: row[0] for row in cur.fetchall()}
    cur.execute('SELECT id, originalCode FROM "Activity"')
    activity_map = {row[1]: row[0] for row in cur.fetchall()}

    batch_size = 500
    uploaded = 0
    errors = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Uploading places", total=len(new_places))

        for i in range(0, len(new_places), batch_size):
            batch = new_places[i : i + batch_size]
            try:
                # Insert places
                execute_values(
                    cur,
                    """
                    INSERT INTO "Place" (
                        id, name, latitude, longitude, typeId, address,
                        rating, reviewCount, photoCount, photos, pricing,
                        access, contact, descriptions, isPublic, onlineBooking,
                        lastFetched
                    ) VALUES %s
                    ON CONFLICT (id) DO NOTHING
                    """,
                    [
                        (
                            p["id"],
                            p.get("name") or p.get("title") or "",
                            p["latitude"],
                            p["longitude"],
                            type_map.get(p.get("type_code", ""), 1),
                            json.dumps(p.get("address", {})),
                            p.get("rating"),
                            p.get("review_count", 0),
                            p.get("photo_count", 0),
                            json.dumps(p.get("photos", [])),
                            json.dumps(p.get("pricing", {})),
                            json.dumps(p.get("access", {})),
                            json.dumps(p.get("contact", {})),
                            json.dumps(p.get("descriptions", {})),
                            p.get("is_public", True),
                            p.get("online_booking", False),
                            p.get("scraped_at") or None,
                        )
                        for p in batch
                    ],
                )

                # Insert PlaceService junctions
                for p in batch:
                    for svc in p.get("services", []):
                        if isinstance(svc, dict):
                            svc_code = svc.get("code", "")
                            svc_id = service_map.get(svc_code)
                            if svc_id:
                                cur.execute(
                                    """
                                    INSERT INTO "PlaceService" (placeId, serviceId)
                                    VALUES (%s, %s)
                                    ON CONFLICT DO NOTHING
                                    """,
                                    (p["id"], svc_id),
                                )

                # Insert PlaceActivity junctions
                for p in batch:
                    for act in p.get("activities", []):
                        if isinstance(act, dict):
                            act_code = act.get("code", "")
                            act_id = activity_map.get(act_code)
                            if act_id:
                                cur.execute(
                                    """
                                    INSERT INTO "PlaceActivity" (placeId, activityId)
                                    VALUES (%s, %s)
                                    ON CONFLICT DO NOTHING
                                    """,
                                    (p["id"], act_id),
                                )

                conn.commit()
                uploaded += len(batch)
                progress.update(task, completed=uploaded)

            except Exception as e:
                conn.rollback()
                errors += len(batch)
                if logger:
                    logger.error(f"Batch error at index {i}: {e}")
                if errors > 5:
                    if logger:
                        logger.error("Too many errors, stopping place uploads")
                    break

    cur.close()

    if logger:
        logger.info(f"Places: {uploaded:,} uploaded, {errors} errors")


def upload_reviews(
    conn: psycopg2.extensions.connection,
    reviews: list[dict],
    system_user_id: str,
) -> None:
    """Upload reviews to Supabase."""
    total = len(reviews)
    if not total:
        return

    if logger:
        logger.info(f"Uploading {total:,} reviews to Supabase")

    cur = conn.cursor()

    # Get vehicle type mapping
    cur.execute('SELECT id, originalCode FROM "VehicleType"')
    vehicle_map = {row[1]: row[0] for row in cur.fetchall()}

    batch_size = 1000
    uploaded = 0
    errors = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Uploading reviews", total=total)

        for i in range(0, total, batch_size):
            batch = reviews[i : i + batch_size]
            try:
                execute_values(
                    cur,
                    """
                    INSERT INTO "Review" (
                        id, content, rating, vehicleTypeId, authorName,
                        authorId, userId, placeId, createdAt
                    ) VALUES %s
                    ON CONFLICT DO NOTHING
                    """,
                    [
                        (
                            str(uuid.uuid5(uuid.NAMESPACE_DNS, f"review-{r['id']}")),
                            r.get("text", {}).get("default", "")
                            if isinstance(r.get("text"), dict)
                            else (r.get("text") or ""),
                            r.get("rating", 0),
                            vehicle_map.get(
                                r.get("author", {}).get("vehicle_type", "")
                                if isinstance(r.get("author"), dict)
                                else "",
                            ),
                            r.get("author", {}).get("name", "")
                            if isinstance(r.get("author"), dict)
                            else "",
                            r.get("author", {}).get("id", "")
                            if isinstance(r.get("author"), dict)
                            else "",
                            system_user_id,
                            r["place_id"],
                            r.get("created_at") or None,
                        )
                        for r in batch
                    ],
                )
                conn.commit()
                uploaded += len(batch)
                progress.update(task, completed=uploaded)

            except psycopg2.errors.ForeignKeyViolation:
                conn.rollback()
                if logger:
                    logger.warning(f"Skipping batch at {i}: place doesn't exist yet")
            except Exception as e:
                conn.rollback()
                errors += len(batch)
                if logger:
                    logger.error(f"Batch error at index {i}: {e}")
                if errors > 5:
                    if logger:
                        logger.error("Too many errors, stopping review uploads")
                    break

    cur.close()

    if logger:
        logger.info(f"Reviews: {uploaded:,} uploaded, {errors} errors")


# ── Main Pipeline ────────────────────────────────────────────────────


def run(
    data_dir: str,
    config: dict,
    env_vars: dict,
    places_limit: int | None,
    dry_run: bool,
    section: str,
) -> None:
    """Run the upload pipeline."""
    global _global_config
    _global_config = config

    # ── Load data ─────────────────────────────────────────────────
    console.print("\n[bold blue]Loading normalised data...[/bold blue]")
    all_data = load_normalized_data(data_dir)

    places = all_data["places"]
    reviews = all_data["reviews"]

    # Apply limit
    if places_limit and places_limit > 0:
        places = places[:places_limit]
        # Filter reviews to match limited places
        place_ids = {p["id"] for p in places}
        reviews = [r for r in reviews if r.get("place_id") in place_ids]
        console.print(f"  Limited to [bold]{places_limit}[/bold] places")

    console.print(f"  Places: [cyan]{len(places):,}[/cyan]")
    console.print(f"  Reviews: [cyan]{len(reviews):,}[/cyan]")

    if dry_run:
        console.print("\n[bold yellow]=== DRY RUN — stopping here ===[/bold yellow]")
        return

    # ── Phase 1: Upload images to R2 ──────────────────────────────
    if section in ("images", "all"):
        console.print("\n[bold cyan]═══ Phase 1: Upload images to Cloudflare R2 ═══[/bold cyan]")

        images_base_dir = os.path.join(data_dir, "images")
        images = collect_images(places, images_base_dir)
        console.print(f"  Found [cyan]{len(images):,}[/cyan] images to upload")

        if images:
            r2 = create_r2_client(config)
            url_map = upload_images_phase(r2, images, config["bucket"])
            update_place_photo_urls(places, url_map)
            console.print(
                f"  [bold green]✓[/bold green] Uploaded images for "
                f"[bold]{len(url_map):,}[/bold] places"
            )

    # ── Phase 2: Upload to Supabase ───────────────────────────────
    if section in ("database", "all"):
        console.print("\n[bold cyan]═══ Phase 2: Upload to Supabase ═══[/bold cyan]")

        conn = get_supabase_connection(env_vars)
        ensure_schema(conn)
        console.print("  [bold green]✓[/bold green] Connected to Supabase")

        # Upload lookup tables first
        upload_lookup_tables(conn, all_data)
        console.print("  [bold green]✓[/bold green] Lookup tables uploaded")

        # Create system user for review FK
        system_user_id = create_system_user(conn)

        # Upload places
        upload_places(conn, places)
        console.print("  [bold green]✓[/bold green] Places uploaded")

        # Upload reviews
        upload_reviews(conn, reviews, system_user_id)
        console.print("  [bold green]✓[/bold green] Reviews uploaded")

        conn.close()

    # ── Summary ───────────────────────────────────────────────────
    console.print("\n[bold green]╔═══════════════════════════════════════════╗[/bold green]")
    console.print("[bold green]║   Upload complete!                        ║[/bold green]")
    console.print("[bold green]╚═══════════════════════════════════════════╝[/bold green]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload normalised Park4Night data to R2 and Supabase",
    )
    parser.add_argument(
        "--data-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "data"),
        help="Directory containing scraped + normalised data (default: ../data)",
    )
    parser.add_argument(
        "--places",
        type=int,
        default=None,
        help="Limit to first N places (and their reviews)",
    )
    parser.add_argument(
        "--env",
        default=os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        help="Path to .env file (default: ../../.env)",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "..", "r2-config.json"),
        help="Path to R2 config JSON (default: ../r2-config.json)",
    )
    parser.add_argument(
        "--log-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "..", "logs"),
        help="Directory for log files (default: ../../logs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load data and list files without uploading",
    )
    parser.add_argument(
        "--section",
        choices=["images", "database", "all"],
        default="all",
        help="Which section to upload (default: all)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Number of parallel upload workers (default: 16)",
    )

    args = parser.parse_args()

    console.print("\n[bold cyan]╔═══════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║   Park4Night Data Uploader                        ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════════════════════════╝[/bold cyan]\n")

    data_dir = os.path.abspath(args.data_dir)
    console.print(f"  Data dir: [cyan]{data_dir}[/cyan]")
    console.print(f"  Config:   [cyan]{args.config}[/cyan]")
    console.print(f"  Env:      [cyan]{args.env}[/cyan]")

    # Setup logging
    setup_logging(args.log_dir)

    # Load configuration
    config = load_config(args.config)
    env_vars = load_env(args.env)

    run(
        data_dir=data_dir,
        config=config,
        env_vars=env_vars,
        places_limit=args.places,
        dry_run=args.dry_run,
        section=args.section,
    )


if __name__ == "__main__":
    main()
