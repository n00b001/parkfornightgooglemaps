"""
R2 Uploader module.

Uploads images for a single place to Cloudflare R2.
Returns updated photo records with R2 URLs.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import IMAGES_DIR  # type: ignore[import-not-found]

logger = logging.getLogger("pipeline")


def create_r2_client(config: dict) -> Any:
    """Create an R2-compatible S3 client."""
    from boto3 import client as r2_client  # type: ignore[import-not-found]

    return r2_client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["accessKeyId"],
        aws_secret_access_key=config["secretAccessKey"],
        region_name=config.get("region", "auto"),
    )


def build_r2_url(config: dict, key: str) -> str:
    """Build public URL for an R2 object."""
    endpoint = config["endpoint"]
    if "r2.cloudflarestorage.com" in endpoint:
        host = endpoint.replace("https://", "").replace(".r2.cloudflarestorage.com", "")
        return f"https://{host}.r2.dev/{config['bucket']}/{key}"
    return f"{endpoint.rstrip('/')}/{config['bucket']}/{key}"


def _find_local_image(place_id: int, photo_id: str, img_type: str) -> str | None:
    """Find a local WebP image file. Only returns .webp paths."""
    path = os.path.join(IMAGES_DIR, "places", str(place_id), f"{photo_id}_{img_type}.webp")
    if os.path.exists(path):
        return path
    return None


def _upload_single(r2: Any, local_path: str, r2_key: str, config: dict) -> str | None:
    """Upload a single image to R2. Returns URL or None."""
    try:
        # Check if already exists
        try:
            r2.head_object(Bucket=config["bucket"], Key=r2_key)
            return build_r2_url(config, r2_key)
        except r2.exceptions.ClientError:
            pass

        content_type = "image/webp"  # Always WebP
        r2.put_object(
            Bucket=config["bucket"],
            Key=r2_key,
            Body=open(local_path, "rb"),
            ContentType=content_type,
        )
        return build_r2_url(config, r2_key)
    except Exception as e:
        logger.error(f"Failed to upload {r2_key}: {e}")
        return None


def upload_place_images(
    r2: Any,
    place: dict,
    config: dict,
) -> dict:
    """Upload all images for a single place to R2.

    Updates the place's photos in-place with r2_url_thumb / r2_url_large.
    Returns the updated place dict.
    """
    place_id = place["id"]
    photos = place.get("photos", [])
    if not photos:
        return place

    uploaded = 0
    for photo in photos:
        photo_id = photo.get("id", "")
        if not photo_id:
            continue

        for img_type, r2_field in [
            ("thumb", "r2_url_thumb"),
            ("large", "r2_url_large"),
        ]:
            local_path = _find_local_image(place_id, photo_id, img_type)
            if not local_path:
                continue

            r2_key = f"places/{place_id}/{photo_id}_{img_type}.webp"  # Always .webp
            url = _upload_single(r2, local_path, r2_key, config)
            if url:
                photo[r2_field] = url
                uploaded += 1

    if uploaded:
        logger.debug(f"Place {place_id}: uploaded {uploaded} images to R2")
    return place
