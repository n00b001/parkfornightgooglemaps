"""
Centralized diskcache configuration for the Park4Night pipeline.

Provides pre-configured diskcache.Cache instances for each pipeline stage.
All caches use SQLite-backed storage (diskcache) for process-safe persistence
across the ProcessPoolExecutor (spawn) worker pool.

Cache directories live under scripts/data/cache/diskcache/ — separate from
the existing file-based caches (api/, normalized/, scraped/).

Why separate caches per stage:
  - Independent size limits and TTLs per concern
  - Easy to clear one stage without invalidating others
  - Clearer debugging (which cache is growing?)

Why diskcache (not functools.lru_cache):
  - Persists to disk — survives process restarts
  - Process-safe (SQLite with WAL mode) — works with spawn workers
  - Thread-safe — works with R2/DB worker pools
  - Supports eviction (LRU/LFU), TTL, tag-based bulk eviction
"""

from __future__ import annotations

import os
from typing import Any

import diskcache as dc

# ── Cache directory ──────────────────────────────────────────────────
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(SCRIPTS_DIR, "data", "cache", "diskcache")

# ── Cache instances ──────────────────────────────────────────────────
# Each cache is a separate SQLite database for independent management.

# API responses: get_places(lat, lng) and get_reviews(place_id)
# Stores raw JSON responses from Park4Night API.
# Size limit: 500 MB (API responses are small JSON, ~100KB per grid point)
# TTL: None (API data changes slowly; manual cache clear to refresh)
api_cache: dc.Cache = dc.Cache(
    directory=os.path.join(CACHE_DIR, "api"),
    size_limit=500 * 1024 * 1024,  # 500 MB
)

# Translation results: _translate_single(text, src_lang)
# Stores translated text strings.
# Size limit: 2 GB (text is small but accumulates over thousands of places)
# TTL: None (translations are deterministic for the same input)
translation_cache: dc.Cache = dc.Cache(
    directory=os.path.join(CACHE_DIR, "translation"),
    size_limit=2 * 1024 * 1024 * 1024,  # 2 GB
)

# Normalized places: normalize_place(place_id)
# Stores the normalized place dict keyed by place_id.
# Size limit: 5 GB (normalized places are ~3-5KB each, ~1M places = ~5GB)
# TTL: None (normalized data is deterministic given the same input)
normalize_cache: dc.Cache = dc.Cache(
    directory=os.path.join(CACHE_DIR, "normalized"),
    size_limit=5 * 1024 * 1024 * 1024,  # 5 GB
)

# Image download results: _download_file(url, save_path, webp_path)
# Stores boolean success/failure per URL.
# Size limit: 100 MB (just URLs and booleans)
# TTL: None (if a URL failed, it likely will again; manual clear to retry)
image_cache: dc.Cache = dc.Cache(
    directory=os.path.join(CACHE_DIR, "images"),
    size_limit=100 * 1024 * 1024,  # 100 MB
)

# R2 upload results: _upload_single(r2_key, local_path)
# Stores R2 URL or None per key.
# Size limit: 500 MB (URLs are small strings)
# TTL: None (once uploaded, the object persists in R2)
r2_cache: dc.Cache = dc.Cache(
    directory=os.path.join(CACHE_DIR, "r2"),
    size_limit=500 * 1024 * 1024,  # 500 MB
)

# DB insert results: _insert_place(place_id), _insert_reviews(place_id)
# Stores success/failure per place_id.
# Size limit: 100 MB (just place IDs and booleans)
# TTL: None (once inserted, the record persists in DB)
db_cache: dc.Cache = dc.Cache(
    directory=os.path.join(CACHE_DIR, "db"),
    size_limit=100 * 1024 * 1024,  # 100 MB
)

# All cache instances (for bulk operations like clear/close)
all_caches: list[dc.Cache] = [
    api_cache,
    translation_cache,
    normalize_cache,
    image_cache,
    r2_cache,
    db_cache,
]


# ── Utility functions ────────────────────────────────────────────────


def get_cache_stats() -> dict[str, Any]:
    """Get statistics for all cache instances.

    Returns dict mapping cache name to {size, numbers, garbage_collected}.
    """
    stats: dict[str, Any] = {}
    cache_map = {
        "api": api_cache,
        "translation": translation_cache,
        "normalized": normalize_cache,
        "images": image_cache,
        "r2": r2_cache,
        "db": db_cache,
    }
    for name, cache in cache_map.items():
        stats[name] = {
            "size": cache.size,  # type: ignore[attr-defined]
            "hits": cache.hits,  # type: ignore[attr-defined]
            "misses": cache.misses,  # type: ignore[attr-defined]
        }
    return stats


def clear_all_caches() -> None:
    """Clear all cache instances. Use with --no-disk-cache."""
    for cache in all_caches:
        cache.clear()


def close_all_caches() -> None:
    """Close all cache connections. Call on shutdown."""
    for cache in all_caches:
        cache.close()


def ensure_cache_dirs() -> None:
    """Ensure all cache directories exist."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    for cache in all_caches:
        os.makedirs(cache.directory, exist_ok=True)
