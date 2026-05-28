# Pipeline Idempotency Review & Improvement Plan

> **Date**: 2026-05-28
> **Scope**: Full code review of `scripts/pipeline/` — idempotency, correctness, performance, progress tracking
> **Status**: Review complete, fixes planned but NOT implemented (awaiting approval)

---

## Executive Summary

The pipeline **is fundamentally idempotent** for the same `--limit` value. Re-running with `--limit 3` processes the same 3 places, and all 7 disk caches cause each stage to skip immediately. The `--no-cache` flag correctly forces re-processing.

**However, there are real bugs that break expected behavior:**

| Bug | Severity | Impact |
|-----|----------|--------|
| `--no-cache` doesn't work for API/images in workers | **Critical** | Re-run with `--no-cache` still uses cached API responses and images |
| DB insert races ahead of R2 upload | **High** | Photos in DB may have local paths instead of R2 URLs |
| `_stats` uses `threading.Lock` across processes | **Medium** | Stats display is wrong (but pipeline logic is correct) |
| R2 progress bar shows places, not images | **Low** | Progress bar label is misleading |

---

## 1. Idempotency Verification (All 7 Caches)

### Cache Chain

| Stage | Cache Mechanism | Cache Check | Idempotent Because |
|-------|----------------|-------------|-------------------|
| API fetch (places) | `cache/api/{lat}_{lng}.json` | File exists + `_no_cache` flag | Same grid point → same API response |
| API fetch (reviews) | `cache/api/reviews_{place_id}.json` | File exists + `_no_cache` flag | Reviews don't change frequently |
| Image download | `data/images/places/{id}/{photo}_thumb.webp` | `.webp` file exists + `_no_cache` flag | Same URL → same image |
| Translation | `cache/translations.json` | Key in dict + `no_cache` flag | Same input → same translation |
| Normalization | `cache/normalized/{place_id}.json` | File exists | Pure function: same input → same output |
| R2 upload | Cloudflare R2 bucket | `head_object` returns 200 (skipped if `no_cache`) | S3 `put_object` is idempotent |
| DB insert | Supabase PostgreSQL | `ON CONFLICT (id) DO UPDATE` | SQL upsert is idempotent |

### Run 1: `--limit 3` (first run, empty cache)

```
Phase 1 (Extract):
  Grid point (35.0, -25.0) → API cache MISS → HTTP request → cache WRITE
  Yields places A, B, C (3 unique places)

Phase 2 (Process, 16 workers):
  Worker 1: Place A
    → extract (pure function, instant)
    → download images: .webp doesn't exist → DOWNLOAD → save .webp
    → fetch reviews: API cache MISS → HTTP request → cache WRITE
    → translate: translation cache MISS → translate → cache WRITE
    → normalize: norm cache MISS → normalize → cache WRITE
  Worker 2: Place B (same pipeline)
  Worker 3: Place C (same pipeline)

  Main process (after each worker returns):
    → enqueue R2: head_object MISS → upload to R2
    → enqueue DB: ON CONFLICT → insert new record

Phase 3 (Finalize):
  → Wait for R2 queue to drain (all images uploaded)
  → Wait for DB queue to drain (all records inserted)
  → Save translation cache to disk

Result: 3 places in Supabase, images in R2, all caches populated
```

### Run 2: `--limit 3` (same limit, caches populated)

```
Phase 1 (Extract):
  Grid point (35.0, -25.0) → API cache HIT → return immediately (NO HTTP)
  Yields SAME places A, B, C

Phase 2 (Process, 16 workers):
  Worker 1: Place A
    → extract (pure function, instant)
    → download images: .webp EXISTS → SKIP (no download)
    → fetch reviews: API cache HIT → return immediately (NO HTTP)
    → translate: all strings in cache → SKIP (no translation)
    → normalize: norm cache HIT → return immediately
  Worker 2: Place B — all cached, instant
  Worker 3: Place C — all cached, instant

  Main process:
    → enqueue R2: head_object HIT → SKIP (no upload)
    → enqueue DB: ON CONFLICT DO UPDATE → fast upsert

Phase 3 (Finalize):
  → R2 queue drains instantly (all skipped)
  → DB queue drains instantly (fast upserts)

Result: Completes in seconds. No new records in R2 or DB.
```

### Run 3: `--limit 3 --no-cache`

```
Startup:
  api_cache_clear() → delete API cache files
  norm_cache_clear() → delete normalized cache files

Phase 1 (Extract):
  Grid point (35.0, -25.0) → no_cache=True → skip cache READ → HTTP request → cache WRITE
  Yields SAME places A, B, C

Phase 2 (Process):
  Worker 1: Place A
    → extract (pure function, instant)
    → download images: no_cache=True → re-download → OVERWRITE .webp
    → fetch reviews: no_cache=True → HTTP request → cache WRITE
    → translate: TranslationCache(no_cache=True) → empty cache → re-translate ALL
    → normalize: cache deleted → re-normalize → cache WRITE

  Main process:
    → enqueue R2: no_cache=True → skip head_object → re-upload (OVERWRITE)
    → enqueue DB: ON CONFLICT DO UPDATE → update existing records

Result: Same duration as Run 1. Same records (overwritten, not duplicated).
```

**Conclusion: Idempotency is CORRECT for Runs 1 and 2. Run 3 has a CRITICAL bug (see Bug 1).**

---

## 2. Bugs Found

### Bug 1: `--no-cache` Doesn't Work for API/Images in Worker Processes (CRITICAL)

**File**: `pipeline.py` — `_worker_init()`

**Problem**: The `_no_cache_global` module-level variable is set to `True` in the main process when `--no-cache` is used. But with `multiprocessing.set_start_method("spawn")`, each worker process starts a **fresh Python interpreter** where `_no_cache_global` is `False` (the default).

```python
# Main process: _no_cache_global = True (set by run_pipeline)
# Worker process: _no_cache_global = False (default, spawn starts fresh!)

def _worker_init() -> None:
    global _worker_api, _worker_downloader
    preload_models()
    _worker_api = Park4NightAPI(no_cache=_no_cache_global)       # ← False in worker!
    _worker_downloader = ImageDownloader(no_cache=_no_cache_global)  # ← False in worker!
```

**Impact**: When `--no-cache` is used:
- ✅ Translation respects `--no-cache` (passed as parameter to `stage_translate()`)
- ✅ Normalization respects `--no-cache` (cache files deleted at startup)
- ❌ **API requests DON'T respect `--no-cache`** — workers use cached API responses
- ❌ **Image downloads DON'T respect `--no-cache`** — workers skip re-downloading images

**Result**: `--no-cache` appears to work (translation is re-done) but API and image stages still use cache. The run completes faster than expected because API/images are cached.

**Fix**: Pass `no_cache` to `_worker_init()` via `initargs`:
```python
ProcessPoolExecutor(
    max_workers=num_workers,
    initializer=_worker_init,
    initargs=(no_cache,),  # Pass no_cache to worker init
)
```

And update `_worker_init`:
```python
def _worker_init(no_cache: bool) -> None:
    global _worker_api, _worker_downloader, _no_cache_global
    _no_cache_global = no_cache  # Set correctly in worker process
    preload_models()
    _worker_api = Park4NightAPI(no_cache=no_cache)
    _worker_downloader = ImageDownloader(no_cache=no_cache)
```

### Bug 2: DB Insert Races Ahead of R2 Upload (HIGH)

**File**: `pipeline.py` — `run_pipeline()` Phase 2 loop

**Problem**: The main process enqueues R2 upload and DB insert **both non-blockingly**:

```python
for future in as_completed(futures):
    ...
    place = stage_enqueue_r2(place, r2_pool)  # Non-blocking: enqueue and move on
    stage_enqueue_db(place, db_pool)           # Non-blocking: enqueue and move on
```

The R2 worker updates `photo[r2_url_thumb] = url` in the photos dict (same Python object). But the DB worker might process the place **before** the R2 worker finishes uploading. In that case:

- Photos dict has `path_thumb: "images/places/123/1_thumb.webp"` (local path)
- DB stores this local path instead of the R2 URL
- The web app tries to load `images/places/123/1_thumb.webp` which doesn't exist in production

**Impact**: Some places in the database have local file paths instead of R2 URLs for their photos. The web app shows broken images for these places.

**Why this happens**: The R2 queue (256 tasks) and DB queue (128 tasks) are independent. The DB worker pool (8 threads) might drain its queue faster than the R2 worker pool (32 threads) uploads images — especially when R2 uploads are slow (network-bound, 50-200ms each).

**Fix**: Wait for R2 `done_event` before enqueuing DB task:
```python
task = R2UploadTask(place_id, photos)
r2_pool.queue.put(task)  # Enqueue R2
task.done_event.wait()   # Wait for R2 to finish THIS place
stage_enqueue_db(place, db_pool)  # Now photos have R2 URLs
```

This maintains parallelism (different places are processed in parallel) while ensuring correctness (R2 URLs exist before DB insert).

### Bug 3: `_stats` Uses `threading.Lock` Across Process Boundaries (MEDIUM)

**File**: `pipeline.py` — `_stats` global

**Problem**: `_stats` is a module-level dict protected by `threading.Lock()`. The `download_images()` function (running in a worker PROCESS) updates `_stats["images_downloaded"]`:

```python
def download_images(place: dict, downloader: ImageDownloader) -> dict:
    ...
    with _stats_lock:  # threading.Lock — doesn't work across processes!
        _stats["images_downloaded"] += len(photos)
    return place
```

With `spawn`, each worker process has its OWN copy of `_stats` and `_stats_lock`. The lock provides no synchronization across processes, and the main process's `_stats` dict is never updated by workers.

**Impact**: The end-of-run summary shows incorrect stats:
- `images_downloaded`: Always 0 (workers update their own copy, main process sees 0)
- `translations_cached`: Always 0 (same reason)
- `cache_hits`/`cache_misses`: Always 0 (same reason)

**Why this doesn't break the pipeline**: The stats are only used for display. The actual pipeline logic (caching, uploading, inserting) is correct.

**Fix**: Remove `_stats` updates from worker functions. The main process already tracks stats from worker results:
```python
# In run_pipeline(), after getting worker result:
with _stats_lock:
    _stats["places_processed"] += 1
    # Worker returns timing data; main process tracks stats
```

### Bug 4: R2 Progress Bar Shows Places, Not Images (LOW)

**File**: `pipeline.py` — Phase 3 Finalize

**Problem**: The R2 progress bar is initialized with `total=limit or 0` (number of places). But R2 uploads individual images, not places. A place with 5 photos generates 10 R2 uploads (thumb + large each).

The progress bar shows "R2 Upload: 3/10" meaning 3 places done, not 3 images. This is confusing.

**Impact**: User sees "R2 Upload: 3/10" and thinks only 3 images were uploaded. Actually, 3 places worth of images (maybe 30-60 images) were uploaded.

**Fix**: Track actual image count instead of place count:
```python
# In R2WorkerPool:
self._completed_images: int = 0  # Instead of _completed_places

# In _process_task():
self._completed_images += uploaded  # Count actual images

# In get_progress():
return self._completed_images, self._total_expected_images
```

---

## 3. Architecture Assessment

### What's Good ✅

1. **Disk cache idempotency** — Each stage checks file existence. Simple, reliable, debuggable.
2. **Worker pools kept** — R2 (32 threads) and DB (8 threads) provide 5-10x speedup vs. sequential.
3. **ProcessPoolExecutor with spawn** — Correct for argos-translate (C extensions, not fork-safe).
4. **WebP conversion** — Images converted at download time, R2 keys always `.webp`.
5. **Translation cache** — Persistent, thread-safe, process-safe (file lock + merge).
6. **Clean stage separation** — Each stage is a pure function or has clear I/O boundaries.
7. **Dead code cleaned up** — `checkpoint.py`, `r2_uploader.py`, `supabase_uploader.py` already deleted.
8. **Comprehensive documentation** — `PIPELINE_DESIGN.md` explains WHY for every design decision.

### What Needs Fixing ❌

1. **`--no-cache` in workers** — Spawn inherits default globals (Bug 1, Critical).
2. **R2/DB race condition** — DB may insert before R2 finishes (Bug 2, High).
3. **Stats across processes** — `threading.Lock` doesn't work across processes (Bug 3, Medium).
4. **R2 progress bar** — Shows places, not images (Bug 4, Low).

---

## 4. Improvement Plan

### Phase 1: Fix Critical Bugs (Must Do)

**Bug 1: `--no-cache` in workers**
- File: `pipeline.py`
- Change: Pass `no_cache` via `initargs` to `_worker_init()`
- Effort: 5 lines of code

**Bug 2: R2/DB race condition**
- File: `pipeline.py`
- Change: Wait for R2 `done_event` before enqueuing DB task
- Effort: 2 lines of code

### Phase 2: Fix Medium Bugs (Should Do)

**Bug 3: Stats across processes**
- File: `pipeline.py`
- Change: Remove `_stats` updates from worker functions; track in main process only
- Effort: 10 lines of code

### Phase 3: Fix Low Bugs (Nice to Have)

**Bug 4: R2 progress bar**
- Files: `pipeline.py`, `r2_worker.py`
- Change: Track image count instead of place count
- Effort: 15 lines of code

---

## 5. What We're NOT Changing

| Decision | Reason |
|----------|--------|
| NOT removing worker pools | They provide 5-10x speedup (documented in PIPELINE_DESIGN.md) |
| NOT adding checkpointing | Disk cache is simpler and more reliable |
| NOT using `pip` | `uv` only (per project rules) |
| NOT merging into single file | Modular design is better for maintainability |
| NOT changing cache directory structure | Current structure is clear and debuggable |
| NOT changing translation approach | argos-translate is correct choice (offline, no rate limits) |

---

## 6. Testing Plan

After fixes are implemented:

```bash
# Test 1: Basic idempotency
cd scripts/pipeline && uv run python pipeline.py --limit 10
# Verify: 10 places in Supabase, images in R2, progress bars visible

cd scripts/pipeline && uv run python pipeline.py --limit 10
# Verify: Completes in < 10 seconds (all cached), no new records
# Verify: Progress bars show 100% instantly (all cached)

# Test 2: No-cache re-processing
cd scripts/pipeline && uv run python pipeline.py --limit 10 --no-cache
# Verify: Same duration as Test 1, same record count (overwritten, not duplicated)
# Verify: Progress bars show real-time progress
# Verify: API requests are made (not cached) — check log file for HTTP requests
# Verify: Images are re-downloaded (not skipped) — check log file for download stats

# Test 3: Incremental processing
cd scripts/pipeline && uv run python pipeline.py --limit 20
# Verify: First 10 cached (fast), next 10 processed (slower), total 20 records

# Test 4: Log file verification
# Verify: Log file has timestamped progress updates for all phases
# Verify: R2/DB progress visible in log file
```

---

## 7. Answers to User's Specific Questions

### "It should be idempotent"
✅ **Already is** for normal runs (same `--limit`). Re-running processes same places, all cached → instant completion. Verified by tracing all 7 cache mechanisms.

### "I don't really like checkpointing, prefer disk cache"
✅ **Already implemented.** Each stage checks file existence. No checkpoint file used. Documented in PIPELINE_DESIGN.md.

### "Remove queue/threadpool for uploads — stupid idea"
✅ **Worker pools are KEPT.** They provide 5-10x speedup. Documented in PIPELINE_DESIGN.md with concrete numbers (32 threads for R2: 12-62s vs 20-400s sequential).

### "Write in comments and md files why you are doing things"
✅ **Comprehensive.** PIPELINE_DESIGN.md explains every design decision. Worker pools have "why" comments. Cache modules explain rationale.

### "All scripts should have progress bars with rich, timestamps, file logging"
✅ **Implemented.** Main pipeline has progress bar. R2/DB worker pools have progress bars (Phase 3 Finalize). Log file has timestamps. Progress logged to file via `log_progress()` and `ProgressTracker`.

### "Merge scraper, normalizer, uploader into one script"
✅ **Already done.** `pipeline.py` is the unified script. Old scripts are deprecated.

### "Use functional programming and Python generators"
✅ **Already done.** `place_source()` is a generator. Each stage is a pure function.

### "Use multithreading (32 threads, 64GB RAM, 10Gbps)"
✅ **Already done.** 16 ProcessPoolExecutor workers + 32 R2 threads + 8 DB threads = 56 concurrent workers.

### "Save progress, no duplicate work on re-run"
✅ **Already done.** Disk cache at every stage.

---

## 8. Recommendation

**The pipeline is fundamentally sound.** The idempotency design (disk cache) is correct and working. The bugs found are:

1. **`--no-cache` in workers** (Critical) — Easy fix: pass via `initargs`
2. **R2/DB race condition** (High) — Easy fix: wait for `done_event`
3. **Stats across processes** (Medium) — Easy fix: track in main process only
4. **R2 progress bar** (Low) — Easy fix: track image count

**Total effort**: ~30 lines of code changes across 2 files.

**Do NOT**: Remove worker pools, add checkpointing, restructure modular design, or use pip.
