"""
Image Downloader.

Downloads place photos (thumbnails + large) from Park4Night CDN
to local disk. All images are saved as WebP (not JPG) for 50-60%
size reduction. See config.py WEBP_QUALITY and WEBP_METHOD settings.

WHY WebP:
  - 50-60% smaller than JPG at equivalent quality
  - Universal browser support (all modern browsers since 2020)
  - Supported by Cloudflare R2 (correct Content-Type: image/webp)
  - Pillow (PIL) has native WebP support via libwebp

WHY convert on download:
  - Images are downloaded as JPG from Park4Night CDN
  - Converted to WebP immediately after download
  - Original JPG is deleted (temporary file)
  - This ensures all images on disk are WebP
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image
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
    WEBP_METHOD,
    WEBP_QUALITY,
)

logger = logging.getLogger("pipeline")


def get_total_webp_size() -> int:
    """Get total size of all WebP images on disk.

    WHY: Monitor total image size to ensure we stay under the 10GB target.
    Called periodically during the pipeline to warn if approaching the limit.

    Returns:
        Total size in bytes of all .webp files in PLACE_IMAGES_DIR.
    """
    total = 0
    if not os.path.exists(PLACE_IMAGES_DIR):
        return 0

    for webp_path in Path(PLACE_IMAGES_DIR).rglob("*.webp"):
        try:
            total += webp_path.stat().st_size
        except OSError:
            pass

    return total


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.2f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} bytes"


class ImageDownloader:
    """Downloads images from Park4Night CDN with retry and rate limiting.

    All images are saved as WebP (not JPG). See module docstring.
    """

    def __init__(self, no_cache: bool = False) -> None:
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
        self._no_cache = no_cache
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

    @staticmethod
    def _convert_jpg_to_webp(jpg_path: Path, webp_path: Path) -> bool:
        """Convert an existing .jpg file to .webp in place.

        WHY configurable quality: Different quality settings produce different
        file sizes. WEBP_QUALITY=60 gives ~45% of original JPG size.
        See config.py for testing results.

        Returns True if conversion succeeded and .jpg was deleted.
        """
        try:
            with Image.open(jpg_path) as img:
                # Handle different color modes
                # WHY: Some images have alpha channel (RGBA) or palette mode (P).
                # WebP lossy encoding requires RGB mode. We composite RGBA onto
                # a white background to preserve transparency as white.
                if img.mode in ("RGBA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[3])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Save as WebP with configured quality
                # WHY quality=WEBP_QUALITY: See config.py for testing results.
                # WHY method=WEBP_METHOD: Best compression ratio (slowest but smallest).
                img.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)

            # Delete original JPG after successful conversion
            # WHY: JPG files are temporary. WebP is the final format.
            jpg_path.unlink()
            return True

        except Exception as e:
            logger.error(f"Failed to convert {jpg_path} to WebP: {e}")
            return False

    def _download_file(self, url: str, save_path: Path, webp_path: Path) -> bool:
        """Download a single file, convert to WebP, and save.

        Flow:
          1. If .webp exists → skip (unless no_cache)
          2. If .jpg exists → convert to .webp (no re-download, unless no_cache)
          3. Download as .jpg (temporary) → convert to .webp → delete .jpg

        Returns True if .webp file exists at end.
        """
        # Skip if .webp already exists (unless no_cache)
        if webp_path.exists() and not self._no_cache:
            self._stats["skipped_exists"] += 1
            if save_path.exists():
                save_path.unlink()
            return True

        # Convert existing .jpg to .webp (no re-download needed, unless no_cache)
        if save_path.exists() and not self._no_cache:
            if self._convert_jpg_to_webp(save_path, webp_path):
                self._stats["downloaded"] += 1
                return True
            else:
                self._stats["failed"] += 1
                return False

        # Download fresh from URL
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

            # Convert to WebP
            if not self._convert_jpg_to_webp(save_path, webp_path):
                self._stats["failed"] += 1
                return False

            self._stats["downloaded"] += 1
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {url}: {e}")
            self._stats["failed"] += 1
            if save_path.exists():
                save_path.unlink()
            return False
        except OSError as e:
            logger.error(f"Failed to save {save_path}: {e}")
            self._stats["failed"] += 1
            if save_path.exists():
                save_path.unlink()
            return False

    def download_place_photos(self, place_id: int, photos: list[dict]) -> list[dict]:
        """Download all photos for a place. Returns photo dicts with local paths.

        All paths are .webp (not .jpg). See module docstring.
        """
        results: list[dict] = []
        for photo in photos:
            photo_id = str(photo.get("id", ""))
            url_large = photo.get("link_large") or photo.get("url_large", "")
            url_thumb = photo.get("link_thumb") or photo.get("url_thumb", "")

            if not url_large and not url_thumb:
                results.append({"id": photo_id})
                continue

            place_dir = Path(PLACE_IMAGES_DIR) / str(place_id)
            thumb_jpg = place_dir / f"{photo_id}_thumb.jpg"
            thumb_webp = place_dir / f"{photo_id}_thumb.webp"
            large_jpg = place_dir / f"{photo_id}_large.jpg"
            large_webp = place_dir / f"{photo_id}_large.webp"

            thumb_ok = self._download_file(url_thumb, thumb_jpg, thumb_webp)
            large_ok = self._download_file(url_large, large_jpg, large_webp)

            result: dict = {
                "id": photo_id,
                "numero": photo.get("numero"),
            }
            if thumb_ok:
                result["path_thumb"] = f"images/places/{place_id}/{photo_id}_thumb.webp"
            if large_ok:
                result["path_large"] = f"images/places/{place_id}/{photo_id}_large.webp"

            results.append(result)

        return results

    def get_stats(self) -> dict:
        return self._stats.copy()
