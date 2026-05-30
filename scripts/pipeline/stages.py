"""Pipeline stage functions with automatic disk caching via diskcache.

Each function is decorated with @disk_cache.memoize() for persistent disk caching.
Re-running the pipeline skips already-cached computations automatically.

Uses diskcache.FanoutCache for process-safe high-concurrency caching across
multiple worker processes (ProcessPoolExecutor with spawn method).

Stages:
  fetch_places(lat, lng)          - API: fetch places for grid point
  fetch_reviews(place_id)          - API: fetch reviews for place
  download_image(url, path)        - Download single image file
  convert_to_webp(jpg, webp)       - Convert JPG to WebP
  upload_to_r2(key, webp_path)     - Upload WebP to R2
  translate_text(text, lang)       - Translate to English (disk + lru)
  normalize_place(place_id, data)  - Normalize into DB-ready format
  upload_to_supabase(id, data, reviews) - Upsert place+reviews to Supabase

Usage:
  from stages import (
      fetch_places, fetch_reviews, download_image,
      convert_to_webp, upload_to_r2, translate_text,
      normalize_place, upload_to_supabase,
      init_stages, shutdown_stages,
  )
  init_stages(r2_config, no_disk_cache=False)
  # ... call stage functions (caching is automatic)
  shutdown_stages()
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from frozendict import frozendict  # type: ignore[import-not-found]

from cache_config import disk_cache  # type: ignore[import-not-found]

logger = logging.getLogger("pipeline.stages")

# ── Module-level singletons (per worker process) ─────────────────────
_api_client: Any = None
_downloader: Any = None
_r2_client: Any = None
_r2_config: dict | None = None


def init_stages(r2_config: dict | None = None, no_disk_cache: bool = False) -> None:
    """Initialize worker process singletons and cache.

    Call once when each worker process starts (spawn method).
    Creates shared API client, image downloader, and R2 client.
    Does NOT clear cache — cache clearing is forbidden (see CACHE_POLICY.md).
    """
    global _api_client, _downloader, _r2_client, _r2_config

    from api_client import Park4NightAPI  # type: ignore[import-not-found]
    from image_downloader import ImageDownloader  # type: ignore[import-not-found]

    _api_client = Park4NightAPI()
    _downloader = ImageDownloader()

    _r2_config = r2_config
    if r2_config:
        import boto3  # type: ignore[import-not-found]

        _r2_client = boto3.client(
            "s3",
            endpoint_url=r2_config["endpoint"],
            aws_access_key_id=r2_config["accessKeyId"],
            aws_secret_access_key=r2_config["secretAccessKey"],
            region_name=r2_config.get("region", "auto"),
        )


# ── Helper: lazy singleton getters ───────────────────────────────────
def _get_api():
    global _api_client
    if _api_client is None:
        from api_client import Park4NightAPI  # type: ignore[import-not-found]

        _api_client = Park4NightAPI()
    return _api_client


def _get_downloader():
    global _downloader
    if _downloader is None:
        from image_downloader import ImageDownloader  # type: ignore[import-not-found]

        _downloader = ImageDownloader()
    return _downloader


# ── Stage: fetch_places ──────────────────────────────────────────────
@disk_cache.memoize()
def fetch_places(latitude: float, longitude: float) -> list[dict]:
    """Fetch places from Park4Night API for a grid point.

    Disk cached: same coordinates always return the same places.
    Re-running the pipeline skips HTTP requests for cached grid points.
    """
    return _get_api().get_places(latitude, longitude)


# ── Stage: fetch_reviews ─────────────────────────────────────────────
@disk_cache.memoize()
def fetch_reviews(place_id: int) -> list[dict]:
    """Fetch reviews for a place from Park4Night API.

    Disk cached: same place_id always returns the same reviews.
    """
    return _get_api().get_reviews(place_id)


# ── Stage: download_image ────────────────────────────────────────────
@disk_cache.memoize()
def download_image(url: str, save_path: str) -> str | None:
    """Download a single image file from URL to local path.

    Disk cached: same URL + path combination returns cached path.
    Side effect: writes the file to disk on first call.
    Returns None if download fails.
    """
    downloader = _get_downloader()
    result = downloader._download_single(url, Path(save_path))
    return str(result) if result else None


# ── Stage: convert_to_webp ───────────────────────────────────────────
@disk_cache.memoize()
def convert_to_webp(jpg_path: str, webp_path: str) -> str | None:
    """Convert a JPG image to WebP format.

    Disk cached: same input/output paths return cached result.
    Side effect: writes WebP file on first call.
    Returns None if conversion fails.
    """
    from PIL import Image

    jpg = Path(jpg_path)
    webp = Path(webp_path)

    if not jpg.exists():
        return None

    try:
        with Image.open(jpg) as img:
            if img.mode in ("RGBA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.save(webp, "WEBP", quality=50, method=6)
        return str(webp)
    except Exception as e:
        logger.error(f"Failed to convert {jpg_path} to WebP: {e}")
        return None


# ── Stage: upload_to_r2 ──────────────────────────────────────────────
@disk_cache.memoize()
def upload_to_r2(r2_key: str, webp_path: str) -> str | None:
    """Upload a WebP image to Cloudflare R2.

    Disk cached: same key + path returns cached URL.
    Side effect: uploads file to R2 on first call.
    Returns None if upload fails.
    """
    global _r2_client, _r2_config
    if _r2_client is None or _r2_config is None:
        return None

    try:
        # Check if already exists
        try:
            _r2_client.head_object(Bucket=_r2_config["bucket"], Key=r2_key)
            return _build_r2_url(_r2_config, r2_key)
        except _r2_client.exceptions.ClientError:
            pass

        _r2_client.put_object(
            Bucket=_r2_config["bucket"],
            Key=r2_key,
            Body=open(webp_path, "rb"),
            ContentType="image/webp",
        )
        return _build_r2_url(_r2_config, r2_key)
    except Exception as e:
        logger.error(f"Failed to upload {r2_key}: {e}")
        return None


def _build_r2_url(config: dict, key: str) -> str:
    """Build public URL for an R2 object."""
    endpoint = config["endpoint"]
    if "r2.cloudflarestorage.com" in endpoint:
        host = endpoint.replace("https://", "").replace(".r2.cloudflarestorage.com", "")
        return f"https://{host}.r2.dev/{config['bucket']}/{key}"
    return f"{endpoint.rstrip('/')}/{config['bucket']}/{key}"


# ── Stage: translate_text ────────────────────────────────────────────
# Two-level cache: lru_cache (in-memory) wraps disk_cache.memoize (disk)
@lru_cache(maxsize=131072)
@disk_cache.memoize()
def translate_text(text: str, src_lang: str) -> str:
    """Translate a single text to English.

    Two-level cache:
      1. lru_cache (in-memory, 131072 entries): instant within process
      2. disk_cache.memoize (disk): persists across process restarts
    """
    if not text or not text.strip():
        return text

    if src_lang == "en":
        return text.strip()

    from translator import (  # type: ignore[import-not-found]
        ensure_packages_installed,
        translate_text,
    )

    ensure_packages_installed()
    return translate_text(text.strip(), src_lang)


# ── Stage: normalize_place ───────────────────────────────────────────
@disk_cache.memoize()
def normalize_place(place_id: int, place_data: frozendict) -> dict | None:
    """Normalize a place record into DB-ready format.

    Disk cached: same place_id + data returns cached normalized data.
    Pure function: no side effects, no I/O.
    Caller must wrap place_data in frozendict() for hashability.
    """
    from normalizer import normalize_place as _do_normalize  # type: ignore[import-not-found]

    return _do_normalize(dict(place_data))


# ── Stage: upload_to_supabase ────────────────────────────────────────
@disk_cache.memoize()
def upload_to_supabase(
    place_id: int, place_data: frozendict, reviews: frozendict
) -> bool:
    """Upload a normalized place + reviews to Supabase.

    Disk cached: same place_id + data returns cached result.
    Side effect: upserts place and reviews to Supabase on first call.
    Returns True if upload succeeded, False otherwise.
    Caller must wrap place_data and reviews in frozendict() for hashability.
    """
    import json
    import uuid

    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        logger.error("psycopg2 not installed")
        return False

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        logger.warning("DATABASE_URL not set, skipping Supabase upload")
        return False

    # Strip query params
    if "?" in database_url:
        database_url = database_url.split("?")[0]

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        cur = conn.cursor()

        try:
            # Get lookup maps
            cur.execute('SELECT id, "originalCode" FROM "PlaceType"')
            type_map = {row[1]: row[0] for row in cur.fetchall()}

            cur.execute('SELECT id, "originalCode" FROM "Service"')
            service_map = {row[1]: row[0] for row in cur.fetchall()}

            cur.execute('SELECT id, "originalCode" FROM "Activity"')
            activity_map = {row[1]: row[0] for row in cur.fetchall()}

            cur.execute('SELECT id, "originalCode" FROM "VehicleType"')
            vehicle_map = {row[1]: row[0] for row in cur.fetchall()}

            # Get or create system user
            system_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "scraped-import-system-user"))
            cur.execute(
                """
                INSERT INTO "User" (id, "googleId", email, "updatedAt")
                VALUES (%s, 'scraped-import', 'scraped@import.local', NOW())
                ON CONFLICT ("googleId") DO UPDATE SET id = EXCLUDED.id, "updatedAt" = NOW()
                RETURNING id
                """,
                (system_user_id,),
            )
            row = cur.fetchone()
            system_user_id = row[0] if row else system_user_id

            # Insert place
            type_code = place_data.get("type_code", "")
            type_id = type_map.get(type_code)
            if type_id is None:
                logger.warning(f"Place {place_id}: type_code '{type_code}' not in PlaceType table")
                conn.rollback()
                return False

            execute_values(
                cur,
                """
                INSERT INTO "Place" (
                    id, name, latitude, longitude, "typeId", address,
                    rating, "reviewCount", "photoCount", photos, pricing,
                    access, contact, descriptions, "isPublic", "onlineBooking",
                    "lastFetched"
                ) VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    photos = EXCLUDED.photos,
                    rating = EXCLUDED.rating,
                    "reviewCount" = EXCLUDED."reviewCount",
                    "photoCount" = EXCLUDED."photoCount",
                    pricing = EXCLUDED.pricing,
                    access = EXCLUDED.access,
                    contact = EXCLUDED.contact,
                    descriptions = EXCLUDED.descriptions,
                    "lastFetched" = EXCLUDED."lastFetched"
                """,
                [
                    (
                        place_data["id"],
                        place_data.get("name") or place_data.get("title") or "",
                        place_data["latitude"],
                        place_data["longitude"],
                        type_id,
                        json.dumps(place_data.get("address", {})),
                        place_data.get("rating"),
                        place_data.get("review_count", 0),
                        place_data.get("photo_count", 0),
                        json.dumps(place_data.get("photos", [])),
                        json.dumps(place_data.get("pricing", {})),
                        json.dumps(place_data.get("access", {})),
                        json.dumps(place_data.get("contact", {})),
                        json.dumps(place_data.get("descriptions", {})),
                        place_data.get("is_public", True),
                        place_data.get("online_booking", False),
                        place_data.get("scraped_at") or None,
                    )
                ],
            )

            # PlaceService junctions
            for svc in place_data.get("services", []):
                if isinstance(svc, dict):
                    svc_id = service_map.get(svc.get("code", ""))
                    if svc_id:
                        cur.execute(
                            """
                            INSERT INTO "PlaceService" ("placeId", "serviceId")
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (place_data["id"], svc_id),
                        )

            # PlaceActivity junctions
            for act in place_data.get("activities", []):
                if isinstance(act, dict):
                    act_id = activity_map.get(act.get("code", ""))
                    if act_id:
                        cur.execute(
                            """
                            INSERT INTO "PlaceActivity" ("placeId", "activityId")
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (place_data["id"], act_id),
                        )

            # Insert reviews
            if reviews:
                execute_values(
                    cur,
                    """
                    INSERT INTO "Review" (
                        id, content, rating, "vehicleTypeId", "authorName",
                        "authorId", "userId", "placeId", "createdAt"
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
                        for r in reviews
                    ],
                )

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to upload place {place_id} to Supabase: {e}")
            return False

        finally:
            cur.close()
            conn.close()

    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        return False
