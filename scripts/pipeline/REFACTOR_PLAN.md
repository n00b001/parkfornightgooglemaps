# Pipeline Refactor Plan — Clean Stage Functions with diskcache + lru_cache

## Current Problems

1. **Custom caching code everywhere** — `cache.py` has 300+ lines of manual JSON file I/O with `fcntl` locks, merge logic, periodic saves
2. **Convert (JPG→WebP) is duplicated** — lives in both `image_downloader.py` AND `r2_worker.py` with identical code
3. **No aggregate "place is done" cache** — to skip a place, must check norm_cache, then R2 head_object, then DB query separately
4. **No lru_cache** — translation cache is disk-only (TranslationCache class); repeated translations of the same string in the same run still hit disk
5. **upload_db has no disk checkpoint** — relies only on DB upsert; no way to know "place_id was uploaded to DB" without querying Supabase

## Complete Pipeline Stages

```
extract (pure) → download → fetch_reviews → convert → translate → normalize → upload_r2 → upload_db
```

| # | Stage | Input | Output | Disk Cache | lru_cache |
|---|-------|-------|--------|------------|-----------|
| 1 | extract | raw API dict | structured place dict | N/A (pure) | N/A |
| 2 | download | photo URL | local .webp file | file exists | N/A |
| 3 | fetch_reviews | place_id | reviews list | `cache/api/reviews_{id}.json` | N/A |
| 4 | convert | local .jpg | local .webp | .webp file exists | N/A |
| 5 | translate | text + lang | English text | `cache/translations.json` via diskcache | yes (hot strings) |
| 6 | normalize | scraped place | DB-ready dict | `cache/normalized/{id}.json` via diskcache | N/A |
| 7 | upload_r2 | local .webp | R2 URL | `cache/r2/{place_id}/{photo_id}_{type}.done` | N/A |
| 8 | upload_db | normalized place + R2 URLs | DB record | `cache/db/{place_id}.done` | N/A |

**Aggregate cache**: `cache/done/{place_id}.done` — set when ALL stages complete. If exists, skip entire place.

## Architecture

### diskcache Strategy

Replace all manual JSON file I/O in `cache.py` with the `diskcache` library:

```python
import diskcache as dc

# Single cache instance, shared across all stages
CACHE = dc.Cache("scripts/data/cache")  # SQLite-backed, thread+process safe

# Usage:
CACHE[("translate", "fr", "bonjour")] = "hello"   # set
result = CACHE.get(("translate", "fr", "bonjour")) # get
```

Why diskcache:
- **SQLite-backed**: ACID transactions, no file locks needed
- **Process-safe**: multiple workers can read/write simultaneously
- **Decorator support**: `@CACHE.memoize()` for automatic caching
- **Eviction**: optional size limits (important for 10GB R2 constraint tracking)
- **Single cache**: one `Cache` instance for all stages, keyed by namespace

### lru_cache Strategy

For translation specifically (hot path, same strings repeated within a run):

```python
from functools import lru_cache

@lru_cache(maxsize=8192)
def _translate_in_memory(text: str, lang: str) -> str:
    """In-memory cache for repeated translations within a run."""
    result = CACHE.get(("translate", lang, text))
    if result is not None:
        return result
    translated = _do_translate(text, lang)
    CACHE[("translate", lang, text)] = translated
    return translated
```

### Stage Function Pattern

Each stage is a **standalone function** with its own cache key namespace:

```python
def stage_download(photo_url: str, save_path: Path) -> bool:
    """Download photo, convert to WebP. Returns True if .webp exists."""
    key = ("download", str(save_path))
    if CACHE.get(key) is not None:
        return True  # already done
    
    # ... download logic ...
    
    CACHE[key] = True
    return True
```

### Aggregate "Place Done" Cache

```python
def mark_place_done(place_id: int) -> None:
    """Mark a place as fully processed (all stages complete)."""
    CACHE[("done", place_id)] = {
        "stages": ["download", "convert", "translate", "normalize", "upload_r2", "upload_db"],
        "timestamp": datetime.now(UTC).isoformat(),
    }

def is_place_done(place_id: int) -> bool:
    """Check if a place has completed all stages."""
    return CACHE.get(("done", place_id)) is not None
```

## Implementation Plan

### Phase 1: Add diskcache dependency + new cache module

1. `uv add diskcache` in `scripts/pipeline/`
2. Rewrite `cache.py` as thin wrapper around diskcache:
   - Single `Cache` instance
   - Namespace convention: `("stage", place_id, detail)`
   - `is_place_done()`, `mark_place_done()`
   - `get_cache_stats()` using diskcache stats
3. Test: `uv run python -c "from cache import CACHE; CACHE[('test', 1)] = 'hello'; print(CACHE.get(('test', 1)))"`

### Phase 2: Extract convert as standalone stage

1. Create `convert.py` with `stage_convert(photo_id, place_id)` function
   - Input: place_id + photo_id
   - Check: does .webp exist? → skip
   - Action: convert .jpg → .webp, delete .jpg
   - Cache: `CACHE[("convert", place_id, photo_id, type)] = True`
2. Remove duplicate convert code from `image_downloader.py` and `r2_worker.py`
3. Test: convert 10 photos, verify .webp files, verify cache

### Phase 3: Rewrite each stage function with diskcache

For each stage, create a clean function following the pattern:

```python
def stage_X(place_id: int, ...) -> Result:
    key = ("X", place_id, ...)
    cached = CACHE.get(key)
    if cached is not None:
        return cached  # cache hit
    
    result = _do_work(...)
    CACHE[key] = result
    return result
```

Stages to refactor (in order):
1. `stage_fetch_reviews` — cache key: `("reviews", place_id)`
2. `stage_translate` — cache key: `("translate", lang, text)` + lru_cache
3. `stage_normalize` — cache key: `("normalize", place_id)`
4. `stage_upload_r2` — cache key: `("r2", place_id, photo_id, type)`
5. `stage_upload_db` — cache key: `("db", place_id)`

### Phase 4: Add aggregate "place done" tracking

1. After all stages complete for a place, call `mark_place_done(place_id)`
2. Before processing a place, check `is_place_done(place_id)` — skip entirely if done
3. This replaces the current norm_cache check + R2 head_object + DB query cascade

### Phase 5: Update pipeline.py to use new stage functions

1. Replace `stage_translate`, `stage_normalize`, etc. with new diskcache-backed versions
2. Update worker functions to use new stage functions
3. Add `mark_place_done()` call after R2 + DB complete
4. Add `is_place_done()` check before submitting to executor

### Phase 6: Clean up + remove old code

1. Remove `TranslationCache` class from `cache.py` (replaced by diskcache)
2. Remove `fcntl` lock logic (diskcache handles concurrency)
3. Remove periodic save logic (diskcache commits on every write)
4. Remove duplicate convert code from `image_downloader.py` and `r2_worker.py`
5. Update `pyproject.toml` ruff known-first-party

## Data Flow (with R2 URLs in DB)

```
Worker process:
  extract → download → fetch_reviews → convert → translate → normalize
  (returns normalized place with local .webp paths)

Main process:
  wait_for_translation()  # apply translations
  upload_r2()             # upload .webp → R2, update photos with R2 URLs
  upload_db()             # insert normalized place (photos contain R2 URLs)
  mark_place_done()       # aggregate cache
```

**Critical**: `upload_db` MUST happen AFTER `upload_r2` completes for that place.
The photos dict must contain `r2_url_thumb` and `r2_url_large` before DB insert.

## Key Design Decisions

1. **diskcache over manual JSON**: SQLite-backed, process-safe, no file locks, decorator support
2. **Single Cache instance**: All stages share one `Cache("scripts/data/cache")`, namespaced by key prefix
3. **lru_cache only for translation**: Hot path where same strings repeat within a run
4. **Aggregate "done" cache**: One check to skip entire place, not cascade of norm_cache + R2 + DB checks
5. **Convert is standalone stage**: No more duplicated code between downloader and R2 worker
6. **upload_db has disk checkpoint**: `("db", place_id)` key — no need to query Supabase to check

## Testing Strategy

Each phase tested independently:
- Phase 1: `--limit 10` with new cache module
- Phase 2: convert 10 photos, verify cache
- Phase 3: each stage function tested with `--limit 5`
- Phase 4: verify `is_place_done()` skips correctly
- Phase 5: full pipeline `--limit 50`, compare output with old pipeline
- Phase 6: lint + test + build pass
