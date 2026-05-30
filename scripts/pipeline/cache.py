"""Single global diskcache instance shared across all pipeline modules.

All caching uses @cache.memoize() decorators. The --no-disk-cache flag
bypasses the cache for timing tests — it never clears stored data.
"""

from __future__ import annotations

import os

from diskcache import Cache

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "cache",
)
os.makedirs(_CACHE_DIR, exist_ok=True)

cache = Cache(_CACHE_DIR)
