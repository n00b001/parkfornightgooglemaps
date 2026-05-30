"""Shared diskcache instance for the pipeline.

All caching uses diskcache (library) — no custom cache code.
Uses FanoutCache for process-safe high-concurrency access across
multiple worker processes (ProcessPoolExecutor with spawn method).

Import this module to get the shared cache:
    from cache_config import disk_cache, no_disk_cache
"""

from __future__ import annotations

import os

import diskcache as dc

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "cache",
    "diskcache",
)

# Process-safe FanoutCache: 8 sub-databases for concurrent write performance.
disk_cache = dc.FanoutCache(_CACHE_DIR)

# Global flag: set True by --no-disk-cache to bypass all cache reads/writes.
no_disk_cache: bool = False
