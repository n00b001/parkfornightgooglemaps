"""
Image Downloader.

Downloads place photos (thumbnails + large) from Park4Night CDN
to local disk.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (  # type: ignore[import-not-found]
    IMAGE_MAX_RETRIES,
    IMAGE_MIN_SIZE,
    IMAGE_REQUEST_DELAY,
    IMAGE_REQUEST_TIMEOUT,
    IMAGE_RETRY_DELAY,
    PLACE_IMAGES_DIR,
)

logger = logging.getLogger("pipeline")


class ImageDownloader:
    """Downloads images from Park4Night CDN with retry and rate limiting."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Park4Night-Scraper/1.0 (research purposes)",
                "Accept": "image/*",
            }
        )

        retry = Retry(
            total=IMAGE_MAX_RETRIES,
            backoff_factor=IMAGE_RETRY_DELAY,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self._last_request_time = 0.0
        self._stats = {
            "downloaded": 0,
            "skipped_exists": 0,
            "skipped_small": 0,
            "failed": 0,
        }

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < IMAGE_REQUEST_DELAY:
            time.sleep(IMAGE_REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    def _download_file(self, url: str, save_path: Path) -> bool:
        """Download a single file with rate limiting and size check."""
        if save_path.exists():
            self._stats["skipped_exists"] += 1
            return True

        self._rate_limit()
        try:
            response = self.session.get(url, timeout=IMAGE_REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) < IMAGE_MIN_SIZE:
                self._stats["skipped_small"] += 1
                return False

            for attempt in range(5):
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    break
                except FileNotFoundError:
                    if attempt == 4:
                        raise
                    time.sleep(0.1 * (attempt + 1))

            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            actual_size = save_path.stat().st_size
            if actual_size < IMAGE_MIN_SIZE:
                save_path.unlink()
                self._stats["skipped_small"] += 1
                return False

            self._stats["downloaded"] += 1
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {url}: {e}")
            self._stats["failed"] += 1
            return False
        except OSError as e:
            logger.error(f"Failed to save {save_path}: {e}")
            self._stats["failed"] += 1
            return False

    def download_place_photos(self, place_id: int, photos: list[dict]) -> list[dict]:
        """Download all photos for a place. Returns photo dicts with local paths."""
        results: list[dict] = []
        for photo in photos:
            photo_id = str(photo.get("id", ""))
            url_large = photo.get("link_large") or photo.get("url_large", "")
            url_thumb = photo.get("link_thumb") or photo.get("url_thumb", "")

            if not url_large and not url_thumb:
                results.append({"id": photo_id})
                continue

            place_dir = Path(PLACE_IMAGES_DIR) / str(place_id)
            thumb_path = place_dir / f"{photo_id}_thumb.jpg"
            large_path = place_dir / f"{photo_id}_large.jpg"

            thumb_ok = self._download_file(url_thumb, thumb_path)
            large_ok = self._download_file(url_large, large_path)

            result: dict = {
                "id": photo_id,
                "numero": photo.get("numero"),
            }
            if thumb_ok:
                result["path_thumb"] = f"images/places/{place_id}/{photo_id}_thumb.jpg"
            if large_ok:
                result["path_large"] = f"images/places/{place_id}/{photo_id}_large.jpg"

            results.append(result)

        return results

    def get_stats(self) -> dict:
        return self._stats.copy()
