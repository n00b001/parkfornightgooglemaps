# Cache Policy

## ABSOLUTE RULE: NEVER CLEAR THE DISK CACHE VIA CLI

The `--no-disk-cache` flag **bypasses** disk cache reads — it does NOT clear, delete, or reset any cache data.

### Why

It takes **days** to download and process the full dataset. Clearing the cache destroys irreplaceable accumulated work. The entire pipeline is designed around **append-only caching with skip-existing logic** — each run picks up where the last left off.

### What `--no-disk-cache` Does

- Skips reading from `diskcache.FanoutCache` (stages.py memoized functions)
- Forces fresh API requests, image downloads, translations, etc. for the current batch
- **Still writes results to cache** — new data is preserved for future runs

### What `--no-disk-cache` Does NOT Do

- ~~Clears `scripts/data/cache/diskcache/`~~ — **NEVER**
- ~~Clears `scripts/data/cache/api/`~~ — **NEVER**
- ~~Clears `scripts/data/cache/scraped/`~~ — **NEVER**
- ~~Clears `scripts/data/cache/normalized/`~~ — **NEVER**
- ~~Clears `scripts/data/cache/translations.json`~~ — **NEVER**

### Code Rule

Any code that calls `disk_cache.clear()`, `api_cache_clear()`, `scrape_cache_clear()`, `norm_cache_clear()`, or `TranslationCache.clear()` triggered by a CLI flag is **broken** and must be removed.

Cache clearing should only happen manually by deleting files on disk — never automated via a CLI flag.
