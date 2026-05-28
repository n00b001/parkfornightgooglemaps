# Pipeline Architecture — WHY Every Decision Was Made

> **Purpose**: This document explains WHY every architectural decision was made.
> Read this BEFORE modifying the pipeline. If you change something, update this
> document to explain the new reasoning. This prevents the cycle of
> implement → unimplement → reimplement that has plagued this project.

---

## Table of Contents

1. [High-Level Data Flow](#1-high-level-data-flow)
2. [Why Disk Cache, Not Checkpointing](#2-why-disk-cache-not-checkpointing)
3. [Why Worker Pools Are KEPT (R2: 32 threads, DB: 8 threads)](#3-why-worker-pools-are-kept)
4. [Why ProcessPoolExecutor with spawn](#4-why-processpoolexecutor-with-spawn)
5. [Why Functional Programming + Generators](#5-why-functional-programming--generators)
6. [The Seven Caches](#6-the-seven-caches)
7. [Idempotency Guarantees](#7-idempotency-guarantees)
8. [Stage Design (scrape / normalize / upload)](#8-stage-design)
9. [Why Rich Logging + File Logging](#9-why-rich-logging--file-logging)
10. [Why `uv`, Not `pip`](#10-why-uv-not-pip)
11. [File Structure](#11-file-structure)
12. [Configuration](#12-configuration)
13. [Testing Strategy](#13-testing-strategy)

---

## 1. High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FULL PIPELINE (--limit N)                    │
│                                                                     │
│  Phase 1: Extract                                                   │
│    API (grid points) → disk cache (api/) → unique places            │
│                                                                     │
│  Phase 2: Process (16 parallel workers via ProcessPoolExecutor)     │
│    Worker: extract → download images → fetch reviews →              │
│            translate (argos) → normalize → save to norm cache       │
│    Main:   enqueue R2 (wait) → enqueue DB (fire-and-forget)         │
│                                                                     │
│  Phase 3: Finalize                                                  │
│    Wait for R2 queue (32 threads) + DB queue (8 threads) to drain   │
│    Save translation cache to disk                                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     STAGE-BY-STAGE (--stage X)                      │
│                                                                     │
│  --stage scrape:  API → download images → fetch reviews →           │
│                   save to cache/scraped/{place_id}.json             │
│                                                                     │
│  --stage normalize: read cache/scraped/ → translate → normalize →   │
│                     save to cache/normalized/{place_id}.json        │
│                                                                     │
│  --stage upload:   read cache/normalized/ → upload R2 → insert DB   │
└─────────────────────────────────────────────────────────────────────┘
```

**Why two modes?**
- Full pipeline: maximum throughput — each place flows through all stages end-to-end
- Stage-by-stage: flexibility — test scraping without R2/DB credentials, re-normalize after fixing the normalizer, re-upload after fixing R2 config

---

## 2. Why Disk Cache, Not Checkpointing

**Decision**: Every long-running I/O operation is backed by a disk cache. File existence (`os.path.exists()`) determines if work is skipped.

**Rejected alternative**: Central checkpoint file tracking "what we've done" (e.g., `pipeline_checkpoint.json` with arrays of processed place IDs).

### Why disk cache wins

| Criterion | Disk Cache | Checkpoint |
|-----------|-----------|------------|
| **Simplicity** | `if os.path.exists(path): return cached` | Must read JSON, parse, check array, update, write back |
| **Reliability** | File either exists or doesn't — no ambiguity | Checkpoint can get out of sync (crash mid-write, partial update) |
| **Debuggability** | `ls data/cache/` shows exactly what's cached | Must parse JSON to understand state |
| **Crash resilience** | Next run processes what's missing automatically | Must handle partial checkpoint (which entries are valid?) |
| **Concurrency** | Each cache is independent — no contention | Single checkpoint file = bottleneck + race conditions |
| **Forget-to-update** | Impossible — the output FILE IS the cache | Easy to forget to add the place ID to the checkpoint |

### How it works

```
API response cached?     → Yes: return cached.  No: fetch → cache → return.
Image .webp exists?      → Yes: skip download.  No: download → convert → save.
Translation cached?      → Yes: return cached.  No: translate → cache → return.
Normalized cached?       → Yes: return cached.  No: normalize → cache → return.
R2 object exists?        → Yes: skip upload.    No: head_object → upload.
DB record exists?        → Yes: ON CONFLICT UPDATE. No: INSERT.
```

### The seven independent caches

1. **API cache** (`data/cache/api/`) — Park4Night API responses per grid point
2. **Scrape cache** (`data/cache/scraped/`) — Complete scraped place data (for stage-by-stage mode)
3. **Normalization cache** (`data/cache/normalized/`) — Normalized place data ready for DB
4. **Translation cache** (`data/cache/translations.json`) — {original: translated} dict
5. **Image cache** (`data/images/places/{id}/`) — Downloaded images as .webp files
6. **R2 cache** (implicit — `head_object` check before upload)
7. **DB cache** (implicit — `ON CONFLICT DO UPDATE` in Supabase)

Caches 1-4 are explicit disk files. Caches 5-7 are implicit (file existence or database upserts).

**Why 7 caches, not 1?**
- Each cache has different semantics (API responses expire differently from translations)
- Independent caches can be cleared independently (`--no-cache` clears API + norm, not images)
- Debugging is easier — you can see which stage is the bottleneck by checking which cache is cold

---

## 3. Why Worker Pools Are KEPT

**Decision**: R2 uploads use 32 parallel threads. DB inserts use 8 parallel threads. Both are queue-based with backpressure.

**Rejected alternative**: Sequential uploads/inserts (one at a time).

### Benchmarks (from PIPELINE_DESIGN.md)

| Operation | Sequential | Parallel | Speedup |
|-----------|-----------|----------|---------|
| R2 upload (100 places) | 20-400s | 12-62s | **5-8x** |
| DB insert (100 places) | ~100s | ~25s | **4x** |

### Why 32 threads for R2

- Each R2 upload is a network round-trip (50-200ms per image)
- On a 10Gbps connection, 32 parallel uploads saturate the bandwidth
- Cloudflare R2 has generous rate limits — 32 threads don't trigger throttling
- Each image is independent — no ordering required

### Why 8 threads for DB

- Each thread maintains its own `psycopg2` connection (connections are NOT thread-safe)
- Supabase free tier: 10k connections/day — 8 concurrent connections is well within limits
- 8 threads provides 3-5x throughput over sequential without overwhelming the database
- Too many threads would cause connection pool exhaustion on the Supabase side

### Why queue-based with backpressure

```
Pipeline (fast)  →  [Queue: max 256]  →  R2 Workers (32 threads)
                        ↑
                   blocks when full
```

- The pipeline enqueues tasks and moves on immediately
- If uploads slow down, the queue fills up and blocks (backpressure)
- This prevents the pipeline from overwhelming R2/Supabase
- Without backpressure, the pipeline would create thousands of pending tasks and run out of memory

### Why the main process waits for R2 before enqueuing DB

```python
r2_task = stage_enqueue_r2(place, r2_pool)
if r2_task is not None:
    r2_task.done_event.wait()  # Wait for THIS place's R2 upload
stage_enqueue_db(place, db_pool)  # Then enqueue DB
```

- The R2 worker updates the photos dict with R2 URLs (`photo["r2_url_thumb"]`)
- If the DB worker processes the place before R2 finishes, the photos in the database will have local file paths instead of R2 URLs
- Waiting for the `done_event` ensures R2 URLs exist before DB insert
- This still maintains parallelism: different places are processed in parallel; we only wait for THIS place's R2 upload

**DO NOT REMOVE THIS WAIT.** Removing it results in broken image URLs in the database.

---

## 4. Why ProcessPoolExecutor with spawn

**Decision**: Main pipeline workers use `ProcessPoolExecutor` with `spawn` start method (not `fork`).

**Rejected alternatives**:
- `fork` start method — inherits parent's memory including locked mutexes → deadlocks with argos-translate
- `ThreadPoolExecutor` — GIL prevents true parallelism for CPU-bound translation

### Why spawn, not fork

- `argos-translate` uses C extensions (C++ neural network models) that are NOT fork-safe
- `fork()` inherits the parent's memory space, including locked mutexes → child process deadlocks immediately
- `spawn` starts a fresh Python interpreter → no inherited state → no deadlocks
- Each worker preloads translation models once at startup (via `_worker_init()`)

### Why 16 workers

- Machine has 32 cores — 16 workers leaves room for I/O (R2/DB worker pools)
- Translation (argos-translate) is CPU-bound — saturating all cores leaves no room for network I/O
- 16 workers provides good throughput without starving the system

### Why workers preload models

```python
def _worker_init(no_cache: bool, preload_translation: bool = True):
    if preload_translation:
        preload_models()  # Load all 30+ language models into memory
    _worker_api = Park4NightAPI(no_cache=no_cache)
    _worker_downloader = ImageDownloader(no_cache=no_cache)
```

- Each worker process takes ~100 seconds to spawn (loading 30+ argos-translate models)
- Models are loaded ONCE per process (in `_worker_init`) and reused for all places
- Without preloading, each place would trigger model loading → pipeline would be 100x slower
- The scrape stage uses `preload_translation=False` (no translation needed) → spawns instantly

### Why check norm cache BEFORE submitting to executor

```python
for raw_place, grid_point in places_to_process:
    place_id = int(raw_place.get("id") or 0)
    if not no_cache:
        cached_data = norm_cache_get(place_id)
        if cached_data is not None:
            # Skip worker entirely — enqueue R2 + DB directly
```

- Each worker takes ~100 seconds to spawn (loading argos models)
- If we submit all places to the executor and check the cache INSIDE the worker, we waste 100s per worker just to find out the place is already cached
- Checking in the main process means cached places are handled instantly with zero spawn cost
- On a re-run with the same `--limit`, ALL places are cached → zero workers spawned → completes in seconds

---

## 5. Why Functional Programming + Generators

**Decision**: Pure functions for transformation, generators for data flow.

### Why generators for place sourcing

```python
def place_source(api: Park4NightAPI, limit: int | None = None):
    """Yields (place_dict, grid_point) tuples from the API."""
    for lat, lng in grid_points:
        places = api.get_places(lat, lng)
        for place in places:
            if place_id not in seen_ids:
                yield (place, (lat, lng))
```

- Memory-efficient: doesn't load all places into RAM
- Lazy evaluation: places are yielded one at a time as grid points are scanned
- Deduplication: `seen_ids` set ensures each place is yielded only once
- With `--limit N`, the generator stops after N places — no wasted API calls

### Why pure functions for transformation

```python
def extract_place_data(place: dict) -> dict | None:
    """Pure function: no I/O, no cache, no side effects."""

def normalize_place(place: dict) -> dict | None:
    """Pure function: no I/O, no cache, no side effects."""
```

- Easy to test: no mocks needed, just pass input and check output
- Easy to reason about: same input → same output, always
- Composable: `normalize(extract(raw_place))` works without hidden state
- Parallelizable: pure functions can run in any order, any number of times

---

## 6. The Seven Caches

### Cache 1: API Response Cache

**Location**: `data/cache/api/{lat}_{lng}.json` and `data/cache/api/reviews_{place_id}.json`

**Purpose**: Cache Park4Night API responses to avoid re-fetching on every run.

**Why**: Park4Night API has rate limiting (0.3s between requests). 10,000 grid points = 50 minutes of rate limiting on every run. With cache: re-run completes in seconds.

**Key**: Grid point coordinates (same coords → same response) or place ID (for reviews).

**Lifecycle**: Written after API fetch. Read before API fetch. Cleared on `--no-cache`.

### Cache 2: Scrape Cache

**Location**: `data/cache/scraped/{place_id}.json`

**Purpose**: Store complete scraped place data (with downloaded photos and reviews) between scrape and normalize stages.

**Why**: Allows running the pipeline in separate stages (`--stage scrape` then `--stage normalize`). The scrape stage writes here; the normalize stage reads here.

**Key**: Place ID.

**Lifecycle**: Written after scrape stage. Read by normalize stage. Cleared on `--no-cache` (scrape stage only).

**Note**: The full pipeline does NOT use this cache — it goes directly from extract → download → translate → normalize → norm cache. The scrape cache is only used by `--stage scrape` and `--stage normalize`.

### Cache 3: Normalization Cache

**Location**: `data/cache/normalized/{place_id}.json`

**Purpose**: Store normalized place data (translated, structured, DB-ready) to avoid re-normalizing on every run.

**Why**: Normalization involves translation (slow — ~100ms per string with argos-translate). Re-running the pipeline should not re-translate already-translated strings.

**Key**: Place ID.

**Lifecycle**: Written after normalize stage. Read before normalize stage (to skip worker). Read by upload stage. Cleared on `--no-cache`.

### Cache 4: Translation Cache

**Location**: `data/cache/translations.json`

**Purpose**: Persistent {original_text: translated_text} dict. Loaded from disk at startup, saved periodically.

**Why**: argos-translate is slow (~100ms per string). 10,000 unique strings = ~17 minutes on every run without cache. Re-running the pipeline should be instant, not re-translate everything.

**Key**: Original text (exact string match).

**Lifecycle**: Loaded at worker startup. Updated during translation. Saved every 1000 translations and on shutdown. Thread-safe (file lock + merge strategy for concurrent writers).

**Why file lock + merge**: Multiple worker processes (spawn via ProcessPoolExecutor) each load the cache from disk at startup, translate different strings, then save periodically. Without merging, the last writer wins and other workers' translations are silently lost.

### Cache 5: Image Cache

**Location**: `data/images/places/{place_id}/{photo_id}_thumb.webp` and `{photo_id}_large.webp`

**Purpose**: Downloaded images in WebP format.

**Why**: Images are large (100KB-2MB each). Re-downloading on every run wastes bandwidth and time. WebP format is 50-75% smaller than JPEG.

**Key**: File existence (`os.path.exists()`).

**Lifecycle**: Downloaded as .jpg (temporary), converted to .webp, .jpg deleted. On re-run, .webp exists → skip download. On `--no-cache`, .webp is overwritten.

### Cache 6: R2 Cache (Implicit)

**Mechanism**: `head_object` check before upload.

**Purpose**: Skip uploading images that already exist in R2.

**Why**: R2 uploads are network-bound (50-200ms per image). If the image already exists, skip the upload entirely.

**Lifecycle**: Checked before each upload. On `--no-cache`, the check is skipped (force re-upload).

### Cache 7: DB Cache (Implicit)

**Mechanism**: `ON CONFLICT DO UPDATE` in Supabase.

**Purpose**: Idempotent database inserts — re-running doesn't create duplicate records.

**Why**: PostgreSQL upserts are atomic and fast. If the record exists, it's updated. If it doesn't, it's inserted. No separate "check if exists" step needed.

**Lifecycle**: Every DB insert uses upsert. On re-run, existing records are updated (no duplicates).

---

## 7. Idempotency Guarantees

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
    → Norm cache check BEFORE executor: HIT → skip worker entirely
    → R2: head_object HIT → skip upload
    → DB: ON CONFLICT DO UPDATE → fast upsert (no new data)

Result: Run 2 completes in seconds. No new records. ✅
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

Result: Same duration as Run 1. Same records (overwritten, not duplicated). ✅
```

### Scenario 3: `--limit 3` then `--limit 5` (incremental)

```
Run 1: Process places A, B, C (3 places)
Run 2:
  → Places A, B, C: All cached → skip instantly
  → Places D, E: Process normally

Result: 5 total records in DB. No duplicate work for A, B, C. ✅
```

### Scenario 4: Pipeline crash mid-way

```
Pipeline crashes after processing 5 of 10 places:
  → Norm cache has 5 entries (places A-E)
  → Translation cache has translations for places A-E (saved periodically)
  → R2 has images for places A-E (uploaded before crash)
  → DB has records for places A-E (inserted before crash)

Next run:
  → Places A-E: All cached → skip instantly
  → Places F-J: Process normally

Result: 10 total records in DB. No duplicate work for A-E. ✅
```

---

## 8. Stage Design

### Why three stages (scrape, normalize, upload)?

1. **Test scraping without R2/DB credentials** — `--stage scrape` doesn't need `.env` or `r2-config.json`
2. **Re-normalize after fixing the normalizer** — `--stage normalize` reads from scrape cache, doesn't re-scrape
3. **Re-upload after fixing R2/DB config** — `--stage upload` reads from norm cache, doesn't re-scrape or re-normalize

### Stage dependencies

```
scrape → normalize → upload
   ↓          ↓          ↓
scraped/   normalized/  R2 + DB
```

- `--stage scrape`: Writes to `cache/scraped/`. No prerequisites.
- `--stage normalize`: Reads from `cache/scraped/`, writes to `cache/normalized/`. Requires scrape stage first.
- `--stage upload`: Reads from `cache/normalized/`. Requires normalize stage first.

### Full pipeline vs. stage-by-stage

| Aspect | Full Pipeline | Stage-by-Stage |
|--------|--------------|----------------|
| Speed | Faster (no intermediate disk I/O) | Slower (writes/read between stages) |
| Flexibility | All-or-nothing | Run individual stages |
| Use case | Production runs | Debugging, testing, partial re-runs |

---

## 9. Why Rich Logging + File Logging

**Decision**: All output goes to BOTH console (Rich formatting) AND log file (plain text with timestamps).

### Why Rich for console

- Colored output makes it easy to distinguish stages, errors, warnings
- Progress bars with ETAs show real-time progress
- Timing report table at the end shows bottleneck stages

### Why file logging

- When running in the background (tmux, cron, CI), you can't see the console
- `tail -f logs/pipeline_*.log` shows progress in real-time
- Log files are timestamped (`pipeline_20240101_120000.log`) — easy to find the right run
- Every `logger.info()` goes to both console and file automatically

### Why progress bars must be in the log file too

- `ProgressTracker` class logs progress to file at regular intervals (every 5 seconds)
- Without this, the log file would have no progress information during long-running stages
- The console shows Rich progress bars; the log file shows plain text progress updates

### Why all log messages have timestamps

- File handler uses `logging.Formatter` with `%(asctime)s`
- Console handler uses Rich's `RichHandler` with `show_time=True`
- Every log entry is timestamped — easy to correlate events across runs

---

## 10. Why `uv`, Not `pip`

**Decision**: All Python package management uses `uv` (astral-sh/uv). `pip` is forbidden.

### Why `uv`

| Criterion | `uv` | `pip` |
|-----------|------|-------|
| Speed | 10-100x faster | Slow (resolves dependencies one at a time) |
| Virtual environments | Automatic | Manual (`python -m venv`) |
| Reproducibility | `uv.lock` ensures exact versions | `requirements.txt` is often outdated |
| Single source of truth | `pyproject.toml` | `requirements.txt` + `pyproject.toml` (confusion) |

### Commands

| Operation | Correct | Forbidden |
|-----------|---------|-----------|
| Add dependency | `uv add <package>` | `pip install <package>` |
| Run script | `uv run python pipeline.py` | `python pipeline.py` |
| Add dev dependency | `uv add --dev <package>` | `pip install <package>` |

---

## 11. File Structure

```
scripts/pipeline/
├── pipeline.py              # Unified entry point (CLI + all stages)
├── config.py                # Configuration (API endpoints, rate limits, grid, codes)
├── cache.py                 # Disk cache primitives (7 caches)
├── api_client.py            # Park4Night API client (retry, rate limiting, cache)
├── image_downloader.py      # Image downloader (download → convert to WebP → save)
├── translator.py            # Argos-translate wrapper (offline, parallel, cached)
├── normalizer.py            # Pure normalization functions (no I/O, no cache)
├── r2_worker.py             # R2 upload worker pool (32 threads, queue-based)
├── db_worker.py             # DB insert worker pool (8 threads, queue-based)
├── logging_setup.py         # Rich console + file logging + progress tracking
├── pyproject.toml           # Dependencies (managed by uv)
├── PIPELINE_ARCHITECTURE.md # This file — WHY every decision was made
├── PIPELINE_DESIGN.md       # Original design document (kept for reference)
├── PIPELINE_DESIGN_V2.md    # Improvement plan (V2)
├── REVIEW_FINDINGS_V2.md    # Review findings (V2)
└── cleanup_r2.py            # One-time utility (delete non-WebP from R2)
```

### Module responsibilities

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `pipeline.py` | CLI, stage routing, main loop, progress tracking | All modules |
| `config.py` | Constants, API endpoints, rate limits, grid, codes | None |
| `cache.py` | Disk cache read/write/clear | None |
| `api_client.py` | HTTP requests, retry, rate limiting, cache | `cache.py`, `config.py` |
| `image_downloader.py` | Download images, convert to WebP | `config.py` |
| `translator.py` | Argos-translate wrapper, parallel translation, cache | `cache.py` |
| `normalizer.py` | Pure normalization functions | None |
| `r2_worker.py` | R2 upload worker pool | `config.py` |
| `db_worker.py` | DB insert worker pool | `config.py` |
| `logging_setup.py` | Rich console + file logging | None |

---

## 12. Configuration

### Required files

| File | Purpose | Required for |
|------|---------|-------------|
| `.env` | `DATABASE_URL` (Supabase connection string) | `--stage upload`, full pipeline |
| `scripts/upload/r2-config.json` | R2 credentials (endpoint, keys, bucket) | `--stage upload`, full pipeline |

### Template files

| File | Purpose |
|------|---------|
| `.env.example` | Template for `.env` with placeholder values |
| `scripts/upload/r2-config.json.example` | Template for R2 config with placeholder values |

### What happens without config

- Without `.env`: DB worker pool is not started. DB inserts are skipped (warning logged). Pipeline continues.
- Without `r2-config.json`: R2 worker pool is not started. R2 uploads are skipped (warning logged). Pipeline continues.
- This allows testing the scrape and normalize stages without cloud credentials.

---

## 13. Testing Strategy

### Test 1: Scrape stage

```bash
cd scripts/pipeline && uv run python pipeline.py --stage scrape --limit 10
```

**Verify**:
- 10 places in `data/cache/scraped/`
- Images in `data/images/places/` (as .webp files)
- Reviews fetched (check log for "reviews" entries)
- Log file has timestamped entries

### Test 2: Scrape idempotency

```bash
cd scripts/pipeline && uv run python pipeline.py --stage scrape --limit 10
```

**Verify**:
- Completes in seconds (all cached)
- No new HTTP requests (check log)
- No new files created

### Test 3: Normalize stage

```bash
cd scripts/pipeline && uv run python pipeline.py --stage normalize --limit 10
```

**Verify**:
- 10 places in `data/cache/normalized/`
- Translations cached (`data/cache/translations.json`)
- Reviews normalized

### Test 4: Normalize idempotency

```bash
cd scripts/pipeline && uv run python pipeline.py --stage normalize --limit 10
```

**Verify**:
- Completes in seconds (all cached)
- No new translations

### Test 5: Upload stage

```bash
cd scripts/pipeline && uv run python pipeline.py --stage upload --limit 10
```

**Verify**:
- Images in R2 (check Cloudflare dashboard)
- Records in Supabase (check Supabase dashboard)
- Verification step passes

### Test 6: Upload idempotency

```bash
cd scripts/pipeline && uv run python pipeline.py --stage upload --limit 10
```

**Verify**:
- R2 head_object skips uploads
- DB upsert is fast
- No duplicate records

### Test 7: Full pipeline

```bash
cd scripts/pipeline && uv run python pipeline.py --limit 10
```

**Verify**:
- All stages complete
- Timing report shows bottleneck stages
- Cache stats show hits/misses

### Test 8: Full pipeline idempotency

```bash
cd scripts/pipeline && uv run python pipeline.py --limit 10
```

**Verify**:
- Completes in seconds (all cached)
- No new HTTP requests
- No new files created
- No new R2 uploads
- No new DB records

---

## Rules for Future Modifications

1. **DO NOT remove worker pools** — they exist for performance (5-10x speedup). Document WHY if you change the thread counts.
2. **DO NOT use checkpointing** — disk cache is simpler and more reliable. Document WHY if you add a checkpoint.
3. **DO NOT use `pip`** — use `uv add` and `uv run` exclusively.
4. **DO NOT delete data files** — the pipeline is append-only with cache-based skip logic.
5. **DO NOT implement without documentation** — write WHY in comments and this file.
6. **DO NOT run tests with more than 10 places** until the user reviews.
7. **DO NOT merge a PR that breaks the app** — verify end-to-end before considering a PR ready.
8. **DO NOT use Park4Night CDN** — all images must come from local paths only.

---

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 2026-05-28 | Initial document | Prevent implement → unimplement → reimplement cycle |
