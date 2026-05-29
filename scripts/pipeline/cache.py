"""
Disk-based caching for the unified pipeline.

Every long-running I/O operation is backed by a disk cache. This replaces
the old checkpoint system: instead of tracking "what we've done", each
function checks "does the output file exist?" before doing work.

Why disk cache over checkpointing:
  - Simpler: file existence check vs. complex state machine
  - More reliable: no central authority to get out of sync
  - Easier to debug: ls the cache directory to see what's cached
  - Harder to get wrong: can't forget to update the checkpoint

Cache directory: scripts/data/cache/
  ├── api/                    # API responses (grid points + reviews)
  │   ├── 48.8566_2.3522.json  # Grid point → places list
  │   └── reviews_12345.json    # Place ID → reviews list
  ├── scraped/                # Complete scraped place data (photos + reviews)
  │   └── 12345.json            # Place ID → scraped place dict
  ├── normalized/             # Normalized place data
  │   └── 12345.json            # Place ID → normalized dict
  └── translations.json       # {original_text: translated_text} dict

All caches support --no-disk-cache bypass (skip read, skip write).
All caches are thread-safe (file locks for concurrent access).
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger("pipeline")

# ── Cache directory ──────────────────────────────────────────────────
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(SCRIPTS_DIR, "data", "cache")
API_CACHE_DIR = os.path.join(CACHE_DIR, "api")
SCRAPED_CACHE_DIR = os.path.join(CACHE_DIR, "scraped")
NORM_CACHE_DIR = os.path.join(CACHE_DIR, "normalized")
TRANSLATION_CACHE_FILE = os.path.join(CACHE_DIR, "translations.json")


def _ensure_dirs() -> None:
    """Create cache directories if they don't exist."""
    os.makedirs(API_CACHE_DIR, exist_ok=True)
    os.makedirs(SCRAPED_CACHE_DIR, exist_ok=True)
    os.makedirs(NORM_CACHE_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)


# ── API Response Cache ───────────────────────────────────────────────
# Caches Park4Night API responses to avoid re-fetching on every run.
# Key: grid point coordinates or place ID.
# Value: raw JSON response from API.


def _api_grid_key(lat: float, lng: float) -> str:
    """Generate cache filename for a grid point."""
    return f"{lat}_{lng}.json"


def _api_reviews_key(place_id: int) -> str:
    """Generate cache filename for place reviews."""
    return f"reviews_{place_id}.json"


def api_cache_get_places(lat: float, lng: float) -> list[dict] | None:
    """Get cached places for a grid point. Returns None if not cached."""
    _ensure_dirs()
    path = os.path.join(API_CACHE_DIR, _api_grid_key(lat, lng))
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "lieux" in data:
            return data["lieux"]
        return data if isinstance(data, list) else None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read API cache {path}: {e}")
        return None


def api_cache_set_places(lat: float, lng: float, places: list[dict]) -> None:
    """Cache places for a grid point."""
    _ensure_dirs()
    path = os.path.join(API_CACHE_DIR, _api_grid_key(lat, lng))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"lieux": places}, f, ensure_ascii=False)
    except OSError as e:
        logger.error(f"Failed to write API cache {path}: {e}")


def api_cache_get_reviews(place_id: int) -> list[dict] | None:
    """Get cached reviews for a place. Returns None if not cached."""
    _ensure_dirs()
    path = os.path.join(API_CACHE_DIR, _api_reviews_key(place_id))
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("status") == "OK":
            return data.get("commentaires", [])
        return data if isinstance(data, list) else None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read API cache {path}: {e}")
        return None


def api_cache_set_reviews(place_id: int, reviews: list[dict]) -> None:
    """Cache reviews for a place."""
    _ensure_dirs()
    path = os.path.join(API_CACHE_DIR, _api_reviews_key(place_id))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"status": "OK", "commentaires": reviews}, f, ensure_ascii=False)
    except OSError as e:
        logger.error(f"Failed to write API cache {path}: {e}")


def api_cache_clear() -> int:
    """Clear all API cache files. Returns number of files deleted."""
    count = 0
    if os.path.exists(API_CACHE_DIR):
        for filename in os.listdir(API_CACHE_DIR):
            path = os.path.join(API_CACHE_DIR, filename)
            if os.path.isfile(path):
                os.unlink(path)
                count += 1
    logger.info(f"Cleared {count} API cache files")
    return count


# ── Scrape Cache ─────────────────────────────────────────────────────
# Caches complete scraped place data (with photos and reviews) between
# the scrape and normalize stages. This allows running the pipeline in
# separate stages: --stage scrape saves here, --stage normalize reads here.
#
# Key: place ID.
# Value: complete place dict with photos (local paths) and reviews.


def scrape_cache_get(place_id: int) -> dict | None:
    """Get cached scraped place data. Returns None if not cached.

    This is the output of the scrape stage: complete place data with
    downloaded photos (local paths) and fetched reviews. Used by the
    normalize stage to read pre-scraped data.
    """
    _ensure_dirs()
    path = os.path.join(SCRAPED_CACHE_DIR, f"{place_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read scrape cache {path}: {e}")
        return None


def scrape_cache_set(place_id: int, data: dict) -> None:
    """Cache scraped place data.

    Called by the scrape stage after downloading photos and fetching reviews.
    The normalize stage reads this data to translate and normalize.
    """
    _ensure_dirs()
    path = os.path.join(SCRAPED_CACHE_DIR, f"{place_id}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError as e:
        logger.error(f"Failed to write scrape cache {path}: {e}")


def scrape_cache_list() -> list[int]:
    """List all cached scraped place IDs.

    Used by the normalize stage to find places that have been scraped
    but not yet normalized.
    """
    _ensure_dirs()
    place_ids: list[int] = []
    if os.path.exists(SCRAPED_CACHE_DIR):
        for filename in os.listdir(SCRAPED_CACHE_DIR):
            if filename.endswith(".json"):
                try:
                    place_ids.append(int(filename.removesuffix(".json")))
                except ValueError:
                    pass
    return sorted(place_ids)


def scrape_cache_clear() -> int:
    """Clear all scrape cache files. Returns number of files deleted."""
    count = 0
    if os.path.exists(SCRAPED_CACHE_DIR):
        for filename in os.listdir(SCRAPED_CACHE_DIR):
            path = os.path.join(SCRAPED_CACHE_DIR, filename)
            if os.path.isfile(path):
                os.unlink(path)
                count += 1
    logger.info(f"Cleared {count} scrape cache files")
    return count


# ── Normalization Cache ──────────────────────────────────────────────
# Caches normalized place data to avoid re-normalizing on every run.
# Key: place ID.
# Value: normalized place dict.


def norm_cache_get(place_id: int) -> dict | None:
    """Get cached normalized place. Returns None if not cached."""
    _ensure_dirs()
    path = os.path.join(NORM_CACHE_DIR, f"{place_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read norm cache {path}: {e}")
        return None


def norm_cache_set(place_id: int, data: dict) -> None:
    """Cache normalized place data."""
    _ensure_dirs()
    path = os.path.join(NORM_CACHE_DIR, f"{place_id}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError as e:
        logger.error(f"Failed to write norm cache {path}: {e}")


def norm_cache_clear() -> int:
    """Clear all normalization cache files. Returns number of files deleted."""
    count = 0
    if os.path.exists(NORM_CACHE_DIR):
        for filename in os.listdir(NORM_CACHE_DIR):
            path = os.path.join(NORM_CACHE_DIR, filename)
            if os.path.isfile(path):
                os.unlink(path)
                count += 1
    logger.info(f"Cleared {count} normalization cache files")
    return count


# ── Translation Cache ────────────────────────────────────────────────
# Persistent translation cache: {original_text: translated_text}
# Loaded from disk at startup, saved periodically.
# Thread-safe: lock protects all writes.


class TranslationCache:
    """Persistent translation cache with thread-safe access.

    Loads from disk at startup, saves periodically.
    Thread-safe: all writes protected by lock.
    Process-safe: only one process writes at a time.

    Why persistent (not in-memory):
      - argos-translate is slow (~100ms per string)
      - 10,000 unique strings = ~17 minutes on every run without cache
      - Re-running pipeline should be instant, not re-translate everything
    """

    def __init__(self, cache_file: str = TRANSLATION_CACHE_FILE, no_disk_cache: bool = False) -> None:
        self._cache_file = cache_file
        self._no_disk_cache = no_disk_cache
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()
        self._new_entries = 0
        self._save_interval = 1000  # Save every N new translations

        if not no_disk_cache:
            self._load()

    def _load(self) -> None:
        """Load translation cache from disk."""
        _ensure_dirs()
        if not os.path.exists(self._cache_file):
            logger.info("No existing translation cache, starting fresh")
            return
        try:
            with open(self._cache_file, encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info(f"Loaded translation cache: {len(self._data):,} entries")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load translation cache: {e}, starting fresh")
            self._data = {}

    def _save(self) -> None:
        """Save translation cache to disk with file lock + merge.

        Why file lock + merge:
          Multiple worker processes (spawn via ProcessPoolExecutor) each load
          the cache from disk at startup, translate different strings, then
          save periodically. Without merging, the last writer wins and other
          workers' translations are silently lost.

        Strategy:
          1. Acquire exclusive file lock (fcntl.flock) so only one process
             writes at a time.
          2. Read current file from disk (may have been written by another
             worker since we loaded).
          3. Merge: our in-memory entries overwrite disk entries.
          4. Write merged result atomically (tmp file + os.replace).
          5. Release lock.

        This ensures no translations are lost when 16 workers save concurrently.
        """
        _ensure_dirs()
        lock_path = self._cache_file + ".lock"
        tmp_path = self._cache_file + ".tmp"
        lock_fd: int = -1
        try:
            # Acquire exclusive lock (blocks until another writer finishes)
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            # Read current state from disk (may have new entries from other workers)
            disk_data: dict[str, str] = {}
            if os.path.exists(self._cache_file):
                try:
                    with open(self._cache_file, encoding="utf-8") as f:
                        disk_data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    disk_data = {}

            # Merge: our in-memory entries overwrite disk entries
            merged = {**disk_data, **self._data}

            # Atomic write: write to temp file, then rename
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False)
            os.replace(tmp_path, self._cache_file)
            logger.info(f"Saved translation cache: {len(merged):,} entries")
        except OSError as e:
            logger.error(f"Failed to save translation cache: {e}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        finally:
            # Release lock and close file descriptor
            if lock_fd >= 0:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
                except OSError:
                    pass

    def get(self, text: str) -> str | None:
        """Get cached translation. Returns None if not cached."""
        if self._no_disk_cache:
            return None
        with self._lock:
            return self._data.get(text)

    def set(self, text: str, translation: str) -> None:
        """Cache a translation. Saves to disk periodically."""
        with self._lock:
            if text not in self._data:
                self._data[text] = translation
                self._new_entries += 1
                if self._new_entries >= self._save_interval:
                    self._new_entries = 0
                    if not self._no_disk_cache:
                        self._save()

    def get_or_none(self, text: str) -> str | None:
        """Get cached translation, always returns value if cached."""
        with self._lock:
            return self._data.get(text)

    def bulk_set(self, translations: dict[str, str]) -> None:
        """Cache multiple translations at once."""
        with self._lock:
            new_count = 0
            for text, translation in translations.items():
                if text not in self._data:
                    self._data[text] = translation
                    new_count += 1
            self._new_entries += new_count
            if self._new_entries >= self._save_interval:
                self._new_entries = 0
                if not self._no_disk_cache:
                    self._save()

    def save(self) -> None:
        """Force save cache to disk (call on shutdown)."""
        with self._lock:
            if not self._no_disk_cache:
                self._save()

    def clear(self) -> None:
        """Clear cache (for --no-disk-cache mode)."""
        with self._lock:
            self._data.clear()
            self._new_entries = 0
            if os.path.exists(self._cache_file):
                os.unlink(self._cache_file)
        logger.info("Translation cache cleared")

    @property
    def size(self) -> int:
        """Number of cached translations."""
        with self._lock:
            return len(self._data)

    @property
    def new_count(self) -> int:
        """Number of new translations since last save."""
        with self._lock:
            return self._new_entries


# ── Cache Statistics ─────────────────────────────────────────────────


def get_cache_stats() -> dict[str, Any]:
    """Get statistics about all caches."""
    stats: dict[str, Any] = {
        "api_cache_files": 0,
        "scrape_cache_files": 0,
        "norm_cache_files": 0,
        "translation_entries": 0,
        "total_cache_size_bytes": 0,
    }

    # API cache
    if os.path.exists(API_CACHE_DIR):
        api_files = [
            f for f in os.listdir(API_CACHE_DIR) if os.path.isfile(os.path.join(API_CACHE_DIR, f))
        ]
        stats["api_cache_files"] = len(api_files)
        stats["total_cache_size_bytes"] += sum(
            os.path.getsize(os.path.join(API_CACHE_DIR, f)) for f in api_files
        )

    # Scrape cache
    if os.path.exists(SCRAPED_CACHE_DIR):
        scrape_files = [
            f
            for f in os.listdir(SCRAPED_CACHE_DIR)
            if os.path.isfile(os.path.join(SCRAPED_CACHE_DIR, f))
        ]
        stats["scrape_cache_files"] = len(scrape_files)
        stats["total_cache_size_bytes"] += sum(
            os.path.getsize(os.path.join(SCRAPED_CACHE_DIR, f)) for f in scrape_files
        )

    # Normalization cache
    if os.path.exists(NORM_CACHE_DIR):
        norm_files = [
            f for f in os.listdir(NORM_CACHE_DIR) if os.path.isfile(os.path.join(NORM_CACHE_DIR, f))
        ]
        stats["norm_cache_files"] = len(norm_files)
        stats["total_cache_size_bytes"] += sum(
            os.path.getsize(os.path.join(NORM_CACHE_DIR, f)) for f in norm_files
        )

    # Translation cache
    if os.path.exists(TRANSLATION_CACHE_FILE):
        try:
            with open(TRANSLATION_CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            stats["translation_entries"] = len(data) if isinstance(data, dict) else 0
            stats["total_cache_size_bytes"] += os.path.getsize(TRANSLATION_CACHE_FILE)
        except (json.JSONDecodeError, OSError):
            pass

    # Human-readable size
    size = stats["total_cache_size_bytes"]
    if size > 1024 * 1024:
        stats["total_cache_size"] = f"{size / (1024 * 1024):.1f} MB"
    elif size > 1024:
        stats["total_cache_size"] = f"{size / 1024:.1f} KB"
    else:
        stats["total_cache_size"] = f"{size} bytes"

    return stats
