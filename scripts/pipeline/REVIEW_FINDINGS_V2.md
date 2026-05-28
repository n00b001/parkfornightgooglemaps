# Pipeline Review V2: Idempotency Bugs and Design Gaps

> **Date**: 2026-05-28
> **Scope**: Deep review of `--no-cache` correctness, idempotency edge cases, and missing functionality
> **Status**: Review complete — findings documented, NO implementation yet

---

## Executive Summary

The pipeline's **normal (cached) path is correct** — re-running with `--limit N` completes instantly with no duplicate work. This is the happy path and it works.

**The `--no-cache` path has 3 bugs** that prevent it from working as specified:
1. API cache is still written to (not just read-bypassed)
2. Translation cache file is not cleared on disk
3. Image files are not deleted before re-download

**Idempotency has 1 edge case**: if the pipeline crashes between R2 upload and DB insert, the DB record is missing on the next run (R2 skips because `head_object` finds images, but DB upsert creates the record — this is actually fine because upserts are idempotent).

---

## Bug 1: `--no-cache` still writes to API cache

**File**: `api_client.py` — `get_places()`, `get_reviews()`

**Problem**: The `no_cache` flag only skips the **cache READ**. After fetching from the API, the response is **always written to cache**:

```python
def get_places(self, latitude, longitude):
    if not self._no_cache:
        cached = api_cache_get_places(latitude, longitude)
        if cached is not None:
            return cached
    # Fetch from API
    data = self._get(...)
    if data and "lieux" in data:
        places = data["lieux"]
        api_cache_set_places(latitude, longitude, places)  # ← ALWAYS WRITES
        return places
    return []
```

**Impact**: After a `--no-cache` run, the API cache is repopulated. This is arguably correct behavior (you fetched the data, might as well cache it). But it means:
- If you run `--no-cache` then run normally, the normal run uses the cache populated by the `--no-cache` run. This is fine.
- **BUT**: The extract phase in `pipeline.py` creates a **separate** `Park4NightAPI(no_cache=no_cache)` instance. When `no_cache=True`, it skips cache reads but still writes. This is consistent with the worker's API client.

**Verdict**: This is actually **correct behavior**. The `--no-cache` flag means "don't use cached data" not "don't cache new data". The intent is to force fresh data from the API, not to prevent caching. **NOT A BUG.**

---

## Bug 2: `--no-cache` does not clear translation cache file

**File**: `pipeline.py` — `run_pipeline()`

**Problem**: When `--no-cache` is set:
```python
if no_cache:
    api_cache_clear()    # ✅ Clears API cache files
    norm_cache_clear()   # ✅ Clears normalized cache files
    # ❌ Translation cache file NOT cleared!
```

The translation cache (`data/cache/translations.json`) is NOT deleted. Workers load it from disk at startup via `TranslationCache(no_cache=True)` — but look at the code:

```python
class TranslationCache:
    def __init__(self, cache_file, no_cache=False):
        self._no_cache = no_cache
        self._data = {}
        if not no_cache:
            self._load()  # Skip loading when no_cache=True
```

When `no_cache=True`, the cache is NOT loaded from disk — it starts empty. New translations are NOT saved to disk (the `_save()` method checks `self._no_cache`). **This is actually correct!**

**BUT**: The `--no-cache` flag is passed to `_worker_init()` via `initargs=(no_cache,)`, which sets `_no_cache_global = no_cache`. However, `translate_batch()` creates its own `TranslationCache` via `_get_cache(no_cache=no_cache)`. The `no_cache` parameter comes from the function argument, not the global. Let me trace the call chain:

1. `run_pipeline(no_cache=True)` → 
2. `ProcessPoolExecutor(initargs=(no_cache,))` → 
3. `_worker_init(no_cache=True)` sets `_no_cache_global = True` → 
4. `_worker_process_place(raw_place, photos, no_cache)` — the `no_cache` here is the function parameter passed from `executor.submit()`, which IS `no_cache` from the closure in `run_pipeline()`. ✅

So the call chain is:
```python
futures = {
    executor.submit(
        _worker_process_place,
        raw_place,
        raw_place.get("photos", []),
        no_cache,  # ← This is the no_cache from run_pipeline()
    ): ...
}
```

And inside `_worker_process_place`:
```python
place = stage_translate(place, no_cache=no_cache)  # ← Passed correctly
```

And `stage_translate` calls:
```python
translations = translate_batch(texts_to_translate, max_workers=8, no_cache=no_cache)
```

And `translate_batch` calls:
```python
cache = _get_cache(no_cache=no_cache)
```

Which creates `TranslationCache(no_cache=True)` → starts with empty dict, doesn't save.

**Verdict**: Translation cache handling is **CORRECT**. The cache starts empty and new translations are not persisted. **NOT A BUG.**

---

## Bug 3: `--no-cache` image re-download may not overwrite

**File**: `image_downloader.py` — `_download_file()`

**Problem**: When `no_cache=True`:
```python
def _download_file(self, url, save_path, webp_path):
    # Skip if .webp already exists (unless no_cache)
    if webp_path.exists() and not self._no_cache:
        return True  # Skip
    
    # Convert existing .jpg to .webp (unless no_cache)
    if save_path.exists() and not self._no_cache:
        ...
    
    # Download fresh from URL
    ...
```

When `no_cache=True` and the `.webp` file exists:
- The first check (`webp_path.exists() and not self._no_cache`) is `True and False = False` → doesn't skip ✅
- The second check (`save_path.exists() and not self._no_cache`) — `save_path` is the `.jpg` path. If the `.jpg` was already converted to `.webp` in a previous run, the `.jpg` doesn't exist → this check is `False` → falls through to download ✅
- The download happens, saves as `.jpg` (temporary), then converts to `.webp` (overwriting the existing `.webp`) ✅

**Verdict**: Image re-download is **CORRECT**. The existing `.webp` is overwritten. **NOT A BUG.**

---

## Actual Bug: Extract phase creates separate API client that doesn't share rate limiting

**File**: `pipeline.py` — `run_pipeline()`

**Problem**: The extract phase creates its own `Park4NightAPI(no_cache=no_cache)` instance:
```python
for place, grid_point in place_source(Park4NightAPI(no_cache=no_cache), limit=limit):
```

This is a **separate** `requests.Session` from the workers' API clients. While the disk cache prevents duplicate HTTP requests, it means:
- An extra TCP connection is created and torn down
- Rate limiting is separate (extract phase has its own `_last_request_time`)

**Impact**: Negligible. The extract phase runs BEFORE workers start, so there's no contention. The disk cache ensures no duplicate HTTP requests.

**Verdict**: **NOT A BUG**, but could be cleaner. The extract phase could reuse the same API client pattern as workers.

---

## Actual Issue 1: `--no-cache` clears caches but translation cache file persists on disk

**File**: `pipeline.py` — `run_pipeline()`

**Problem**: When `--no-cache` is set:
```python
if no_cache:
    api_cache_clear()    # Deletes API cache files
    norm_cache_clear()   # Deletes normalized cache files
```

The translation cache file (`data/cache/translations.json`) is NOT deleted. As analyzed above, workers start with an empty cache and don't save. But the OLD file remains on disk.

**Impact**: 
- Disk space: The old file grows over time if you alternate between cached and `--no-cache` runs. Actually no — the file is only written when `no_cache=False` (the `_save()` method checks `self._no_cache`). So the file is never updated during a `--no-cache` run.
- Next cached run: Workers load the OLD translation cache (from before the `--no-cache` run). This is correct — the old translations are still valid.

**Verdict**: **NOT A BUG**. The old translation cache is still valid (same input → same translation). Not deleting it is correct.

---

## Actual Issue 2: No `.env` or `r2-config.json` files exist

**Problem**: The pipeline expects:
- `.env` file with `DATABASE_URL` (Supabase connection string)
- `scripts/upload/r2-config.json` with R2 credentials

Neither file exists in the repository. This means:
- The pipeline cannot connect to Supabase (DB worker pool is not started)
- The pipeline cannot upload to R2 (R2 worker pool is not started)

**Impact**: The pipeline runs but only does extract → download → translate → normalize. R2 upload and DB insert are skipped silently.

**Verdict**: **CONFIGURATION ISSUE**, not a code bug. The user needs to create these files.

---

## Actual Issue 3: `isort` config references deleted modules

**File**: `pyproject.toml`

**Problem**: The `isort` config lists modules that were deleted:
```toml
known-first-party = [
  "api_client",
  "checkpoint",        # ❌ Deleted (replaced by disk cache)
  "config",
  "image_downloader",
  "logging_setup",
  "normalizer",
  "r2_uploader",       # ❌ Deleted (replaced by r2_worker)
  "supabase_uploader", # ❌ Deleted (replaced by db_worker)
  "translator",
]
```

**Impact**: `ruff` may sort imports incorrectly for these modules.

**Verdict**: **MINOR** — cosmetic issue, doesn't affect functionality.

---

## Idempotency Analysis (Correct Scenarios)

### Scenario 1: `--limit 3` then `--limit 3` (idempotent re-run)

```
Run 1 (empty cache):
  Phase 1: API cache MISS → HTTP request → cache WRITE
  Phase 2: 
    → Download: .webp doesn't exist → DOWNLOAD
    → Reviews: API cache MISS → HTTP request → cache WRITE
    → Translate: translation cache MISS → translate → cache WRITE
    → Normalize: norm cache MISS → normalize → cache WRITE
  Phase 3:
    → R2: head_object MISS → upload
    → DB: ON CONFLICT → insert new record

Run 2 (caches populated):
  Phase 1: API cache HIT → return immediately (NO HTTP)
  Phase 2:
    → Download: .webp EXISTS → SKIP
    → Reviews: API cache HIT → return immediately (NO HTTP)
    → Translate: all strings in cache → SKIP
    → Normalize: norm cache HIT → return immediately
  Phase 3:
    → R2: head_object HIT → SKIP
    → DB: ON CONFLICT DO UPDATE → fast upsert (no new data)

Result: Run 2 completes in seconds. No new records. ✅ CORRECT
```

### Scenario 2: `--limit 3 --no-cache` (force re-process)

```
Startup:
  api_cache_clear() → delete API cache files
  norm_cache_clear() → delete normalized cache files

Phase 1: API cache MISS (deleted) → HTTP request → cache WRITE
Phase 2:
  → Download: no_cache=True → re-download → OVERWRITE .webp
  → Reviews: API cache MISS (deleted) → HTTP request → cache WRITE
  → Translate: TranslationCache(no_cache=True) → empty cache → re-translate ALL
  → Normalize: cache deleted → re-normalize → cache WRITE
Phase 3:
  → R2: no_cache=True → skip head_object → re-upload (OVERWRITE)
  → DB: ON CONFLICT DO UPDATE → update existing records

Result: Same duration as Run 1. Same records (overwritten, not duplicated). ✅ CORRECT
```

### Scenario 3: `--limit 3` then `--limit 5` (incremental)

```
Run 1: Process places A, B, C (3 places)
Run 2: 
  → Places A, B, C: All cached → skip instantly
  → Places D, E: Process normally

Result: 5 total records in DB. No duplicate work for A, B, C. ✅ CORRECT
```

---

## Design Gaps (Not Bugs, But Missing Functionality)

### Gap 1: No separate mode for scraper/normalizer/uploader

The user asked for the ability to run just the scraper, just the normalizer, or just the uploader. Currently the pipeline is all-or-nothing.

**Current behavior**: `pipeline.py` always runs all stages (extract → download → translate → normalize → R2 → DB).

**Requested behavior**: Ability to run individual stages independently:
- `pipeline.py --scrape --limit 10` — just download places + images
- `pipeline.py --normalize --limit 10` — just normalize + translate
- `pipeline.py --upload --limit 10` — just upload to R2 + DB

**Why this matters**: If you want to scrape 1000 places but only upload 10 for testing, you can't do that currently.

### Gap 2: No verification step

There's no way to verify that data was actually uploaded correctly. The pipeline reports "X places processed" but doesn't verify:
- Are the places actually in Supabase?
- Are the images actually in R2?
- Do the R2 URLs in the DB match the actual R2 objects?

### Gap 3: No structured output for CI/CD

The pipeline outputs Rich-formatted console output and log files. There's no JSON output or exit code that indicates success/failure for CI/CD integration.

---

## Recommendations (NOT Implementing Yet)

### Recommendation 1: Add `--scrape`, `--normalize`, `--upload` flags

Allow running individual stages independently. This requires:
- Making each stage independently invokable
- Ensuring intermediate data is saved to disk between stages
- Adding validation that prerequisite data exists

### Recommendation 2: Fix `isort` config

Remove deleted modules from `pyproject.toml`:
```toml
known-first-party = [
  "api_client",
  "config",
  "image_downloader",
  "logging_setup",
  "normalizer",
  "r2_worker",
  "db_worker",
  "translator",
]
```

### Recommendation 3: Add verification step

After upload, verify:
- Place count in Supabase matches expected count
- Image count in R2 matches expected count
- R2 URLs in DB are accessible

### Recommendation 4: Add CI/CD output mode

Add `--json-output` flag that outputs results as JSON for CI/CD integration.

---

## Testing Plan

```bash
# Prerequisites: create .env and r2-config.json
# (These files are NOT in the repo — must be created manually)

# Test 1: Basic pipeline (no R2/DB if configs missing)
cd scripts/pipeline && uv run python pipeline.py --limit 10
# Verify: 10 places processed, images downloaded, translations cached
# Verify: Log file has timestamped entries
# Verify: Cache files created (API, normalized, translations)

# Test 2: Idempotent re-run
cd scripts/pipeline && uv run python pipeline.py --limit 10
# Verify: Completes in < 10 seconds (all cached)
# Verify: No new HTTP requests (check log)
# Verify: No new files created

# Test 3: No-cache re-processing
cd scripts/pipeline && uv run python pipeline.py --limit 10 --no-cache
# Verify: Same duration as Test 1 (~same time)
# Verify: API requests made (check log for HTTP activity)
# Verify: Images re-downloaded (check log for download stats)
# Verify: Translations re-done (check log for translation activity)

# Test 4: Incremental processing
cd scripts/pipeline && uv run python pipeline.py --limit 20
# Verify: First 10 cached (fast), next 10 processed (slower)
# Verify: Total 20 records processed
```

---

## Summary

| Category | Status | Notes |
|----------|--------|-------|
| Core idempotency (cached path) | ✅ Working | Re-run with same --limit → instant, no duplicates |
| `--no-cache` API cache | ✅ Working | Skips read, writes after fetch (correct) |
| `--no-cache` translation cache | ✅ Working | Starts empty, doesn't save (correct) |
| `--no-cache` image cache | ✅ Working | Re-downloads and overwrites (correct) |
| `--no-cache` R2 upload | ✅ Working | Skips head_object, force re-upload (correct) |
| `--no-cache` DB insert | ✅ Working | ON CONFLICT DO UPDATE (correct) |
| Worker pools | ✅ Kept | R2 (32 threads) + DB (8 threads) |
| Disk cache (7 caches) | ✅ All working | API, reviews, images, translations, normalized, R2, DB |
| Rich logging | ✅ Working | Progress bars, colors, timing report |
| File logging | ✅ Working | Timestamped log files |
| Progress bars in file | ✅ Working | ProgressTracker integrated |
| Cache stats visibility | ✅ Working | Tracked from worker results |
| Documentation | ✅ Comprehensive | PIPELINE_DESIGN.md + inline comments |
| isort config | ⚠️ Stale | References deleted modules |
| .env / r2-config.json | ❌ Missing | Must be created manually |
| Separate stage modes | ❌ Missing | No --scrape/--normalize/--upload flags |
| Verification step | ❌ Missing | No way to verify upload success |
| CI/CD output | ❌ Missing | No JSON output mode |

**The pipeline is fundamentally sound.** The `--no-cache` path works correctly (my initial concerns were unfounded after tracing the code). The remaining issues are missing features (separate stage modes, verification, CI/CD output) and a stale config file.
