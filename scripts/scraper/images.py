#!/usr/bin/env python3
"""
Image Download Utility for Park4Night Scraper

Downloads place photos (thumbnails + large) and vehicle type icons
from Park4Night CDN, saving them locally with relative path tracking.

Directory structure:
    scripts/data/images/
    ├── places/
    │   └── {place_id}/
    │       ├── {photo_id}_thumb.jpg
    │       └── {photo_id}_large.jpg
    └── icons/
        ├── vehicule_nc.png
        ├── vehicule_gv.png
        └── ...
"""

import logging
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    ICON_IMAGES_DIR,
    IMAGE_MAX_RETRIES,
    IMAGE_MIN_SIZE,
    IMAGE_REQUEST_DELAY,
    IMAGE_REQUEST_TIMEOUT,
    IMAGE_RETRY_DELAY,
    PLACE_IMAGES_DIR,
)

logger = logging.getLogger(__name__)


class ImageDownloader:
    """Downloads images from Park4Night CDN with retry and rate limiting."""

    # Vehicle type icon mapping (vehicle_type_code -> filename)
    VEHICLE_ICONS = {
        "NC": "vehicule_nc.png",  # Caravan
        "GV": "vehicule_gv.png",  # Motorhome / Camping-car
        "UL": "vehicule_ul.png",  # Ultralight
        "V": "vehicule_v.png",  # Vehicle
        "M": "vehicule_m.png",  # Motorcycle
        "T": "vehicule_t.png",  # Tent
        "P": "vehicule_p.png",  # Car / Parking
        "I": "vehicule_i.png",  # Unknown / Other
    }

    CDN_BASE = "https://cdn6.park4night.com/images/bitmap/vehicules"
    CDN_VERSION = "2bf1e1a"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Park4Night-Scraper/1.0 (research purposes)",
                "Accept": "image/*",
            }
        )

        # Configure retry strategy
        retry = Retry(
            total=IMAGE_MAX_RETRIES,
            backoff_factor=IMAGE_RETRY_DELAY,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self._last_request_time = 0
        self._stats = {
            "downloaded": 0,
            "skipped_exists": 0,
            "skipped_small": 0,
            "failed": 0,
            "total_bytes": 0,
        }

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < IMAGE_REQUEST_DELAY:
            time.sleep(IMAGE_REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    def _download_file(self, url: str, save_path: Path) -> bool:
        """Download a single file with rate limiting and size check."""
        if save_path.exists():
            self._stats["skipped_exists"] += 1
            return True  # Already downloaded

        self._rate_limit()
        try:
            response = self.session.get(url, timeout=IMAGE_REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()

            # Check content length before saving
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) < IMAGE_MIN_SIZE:
                self._stats["skipped_small"] += 1
                logger.debug(f"Skipping small file: {url} ({content_length} bytes)")
                return False

            # Save file
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify minimum size after download
            actual_size = save_path.stat().st_size
            if actual_size < IMAGE_MIN_SIZE:
                save_path.unlink()
                self._stats["skipped_small"] += 1
                logger.debug(f"Downloaded file too small: {url} ({actual_size} bytes)")
                return False

            self._stats["downloaded"] += 1
            self._stats["total_bytes"] += actual_size
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {url}: {e}")
            self._stats["failed"] += 1
            return False
        except OSError as e:
            logger.error(f"Failed to save {save_path}: {e}")
            self._stats["failed"] += 1
            return False

    def download_place_photo(
        self, place_id: int, photo_id: str, url_large: str, url_thumb: str
    ) -> dict:
        """
        Download both thumbnail and large versions of a place photo.

        Returns a dict with relative paths for storage in JSON:
        {
            "id": photo_id,
            "path_thumb": f"images/places/{place_id}/{photo_id}_thumb.jpg",
            "path_large": f"images/places/{place_id}/{photo_id}_large.jpg",
            "url_thumb": url_thumb,  # Original URL (fallback)
            "url_large": url_large,  # Original URL (fallback)
        }
        """
        place_dir = Path(PLACE_IMAGES_DIR) / str(place_id)

        thumb_path = place_dir / f"{photo_id}_thumb.jpg"
        large_path = place_dir / f"{photo_id}_large.jpg"

        thumb_ok = self._download_file(url_thumb, thumb_path)
        large_ok = self._download_file(url_large, large_path)

        result = {
            "id": photo_id,
            "url_thumb": url_thumb,
            "url_large": url_large,
        }

        if thumb_ok:
            result["path_thumb"] = f"images/places/{place_id}/{photo_id}_thumb.jpg"
        if large_ok:
            result["path_large"] = f"images/places/{place_id}/{photo_id}_large.jpg"

        return result

    def download_place_photos(self, place_id: int, photos: list[dict]) -> list[dict]:
        """
        Download all photos for a place.

        Args:
            place_id: Place ID
            photos: List of photo dicts from the API (with link_large, link_thumb)

        Returns:
            List of photo dicts with relative paths added
        """
        results = []
        for photo in photos:
            photo_id = str(photo.get("id", ""))
            url_large = photo.get("link_large") or photo.get("url_large", "")
            url_thumb = photo.get("link_thumb") or photo.get("url_thumb", "")

            if not url_large and not url_thumb:
                results.append({"id": photo_id})
                continue

            result = self.download_place_photo(place_id, photo_id, url_large, url_thumb)
            result["numero"] = photo.get("numero")
            results.append(result)

        return results

    def download_vehicle_icons(self) -> dict[str, str]:
        """
        Download all vehicle type icons.

        Returns:
            Dict mapping vehicle_type_code to relative path
        """
        os.makedirs(ICON_IMAGES_DIR, exist_ok=True)
        result = {}

        for code, filename in self.VEHICLE_ICONS.items():
            url = f"{self.CDN_BASE}/{filename}?v={self.CDN_VERSION}"
            save_path = Path(ICON_IMAGES_DIR) / filename

            if self._download_file(url, save_path):
                result[code] = f"images/icons/{filename}"
                logger.info(f"Downloaded vehicle icon: {code} -> {filename}")
            else:
                logger.warning(f"Failed to download vehicle icon: {code}")

        return result

    def get_stats(self) -> dict:
        """Return download statistics."""
        stats = self._stats.copy()
        if stats["total_bytes"] > 1024 * 1024:
            stats["total_size"] = f"{stats['total_bytes'] / (1024 * 1024):.1f} MB"
        elif stats["total_bytes"] > 1024:
            stats["total_size"] = f"{stats['total_bytes'] / 1024:.1f} KB"
        else:
            stats["total_size"] = f"{stats['total_bytes']} bytes"
        return stats

    def reset_stats(self) -> None:
        """Reset download statistics."""
        self._stats = {
            "downloaded": 0,
            "skipped_exists": 0,
            "skipped_small": 0,
            "failed": 0,
            "total_bytes": 0,
        }


def create_image_downloader() -> ImageDownloader:
    """Factory function for creating image downloaders."""
    return ImageDownloader()
