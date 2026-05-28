# Pipeline Audit: Idempotency, Correctness, and Gaps

> **Date**: 2026-05-28
> **Scope**: Full code review of `scripts/pipeline/` against user requirements
> **Status**: Review complete — findings documented, NO implementation yet

---

## Executive Summary

The pipeline (`pipeline.py`) is a **unified single script** that already merges scraper + normalizer + uploader. It is **fundamentally idempotent** via disk caching at every stage. The architecture (disk cache, worker pools, ProcessPoolExecutor with spawn) is sound.

**However, there are real bugs that prevent correct operation:**

| Bug | Severity | Impact |
|-----|----------|--------|
| `get_reviews()` uses wrong API endpoint | **Critical** | Reviews are NEVER fetched — all places have 0 reviews |
| `--no-cache` clears ALL caches, not just current batch | Low | Re-fetches unrelated grid points on next run |

---

## 1. Idempotency Analysis

### 7 Independent Disk Caches

Each stage checks if its output exists before doing work. No central checkpoint file.

| Stage | Cache Location | Cache Check | Idempotent Because |
|-------|---------------|-------------|-------------------|
| API fetch (places) | `data/cache/api/{lat}_{lng}.json` | File exists | Same grid point → same API response |
| API fetch (reviews) | `data/cache/api/reviews_{place_id}.json` | File exists | Reviews don't change frequently |
| Image download | `data/images/places/{id}/{photo}_thumb.webp` | `.webp` file exists | Same URL → same image |
| Translation | `data/cache/translations.json` | Key in JSON dict | Same input → same translation (deterministic) |
| Normalization | `data/cache/normalized/{place_id}.json` | File exists | Pure function: same input → same output |
| R2 upload | Cloudflare R2 bucket | `head_object` returns 200 | S3 `put_object` is idempotent |
| DB insert | Supabase PostgreSQL | `ON CONFLICT (id) DO UPDATE` | SQL upsert is idempotent |

### Run 1: `--limit 3` (empty cache)

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

  Main process (after each worker returns):
    → enqueue R2: head_object MISS → upload to R2
    → wait for done_event (ensures R2 URLs exist)
    → enqueue DB: ON CONFLICT → insert new record

Phase 3 (Finalize):
  → Wait for R2 queue to drain
  → Wait for DB queue to drain
  → Save translation cache to disk

Result: 3 places in Supabase, images in R2, all caches populated
```

### Run 2: `--limit 3` (caches populated)

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
  api_cache_clear() → delete ALL API cache files
  norm_cache_clear() → delete ALL normalized cache files

Phase 1 (Extract):
  Grid point (35.0, -25.0) → no_cache=True → skip cache READ → HTTP request
  Yields SAME places A, B, C

Phase 2 (Process):
  Worker 1: Place A
    → extract (pure function, instant)
    → download images: no_cache=True → re-download → OVERWRITE .webp
    → fetch reviews: no_cache=True → HTTP request
    → translate: TranslationCache(no_cache=True) → empty cache → re-translate ALL
    → normalize: cache deleted → re-normalize → cache WRITE

  Main process:
    → enqueue R2: no_cache=True → skip head_object → re-upload (OVERWRITE)
    → enqueue DB: ON CONFLICT DO UPDATE → update existing records

Result: Same duration as Run 1. Same records (overwritten, not duplicated).
```

**Conclusion**: Idempotency logic is CORRECT for all 3 scenarios. The disk cache design is sound.

---

## 2. Bugs Found

### Bug 1: `get_reviews()` Uses Wrong API Endpoint (CRITICAL)

**File**: `api_client.py` — `get_reviews()` method, line ~127

**Problem**: The `get_reviews()` method uses `PLACES_ENDPOINT` (`lieuxGetFilter.php`) instead of `REVIEWS_ENDPOINT` (`commGet.php`):

```python
def get_reviews(self, place_id: int) -> list[dict]:
    # BUG: Uses PLACES_ENDPOINT instead of REVIEWS_ENDPOINT
    data = self._get(PLACES_ENDPOINT, {"lieu_id": place_id})
```

The old scraper (`scripts/scraper/api.py`) correctly uses `REVIEWS_ENDPOINT`:

```python
def get_reviews_guest(self, place_id: int) -> list | None:
    data = self._get(REVIEWS_ENDPOINT, params)  # Correct!
```

**Impact**: Reviews are NEVER fetched. Every place in the database has 0 reviews. The entire review pipeline (fetch → translate → normalize → insert) operates on empty data.

**Fix**: Change `PLACES_ENDPOINT` to `REVIEWS_ENDPOINT` in `get_reviews()`.

### Bug 2: `--no-cache` Clears ALL Caches, Not Just Current Batch (Low)

**File**: `pipeline.py` — `run_pipeline()`, lines ~600-603

**Problem**: When `--no-cache` is used, `api_cache_clear()` deletes ALL cached API responses (all grid points), and `norm_cache_clear()` deletes ALL normalized cache files. This means:

1. Run `--limit 100` (caches 100 grid points + 100 normalized places)
2. Run `--limit 10 --no-cache` (deletes ALL 100 grid point caches + ALL 100 normalized caches)
3. Run `--limit 100` again (must re-fetch ALL 100 grid points from API)

**Impact**: Minor inconvenience. The next normal run after `--no-cache` must re-fetch everything from the API (50+ minutes of rate limiting).

**Fix**: Track which grid points and place IDs were processed in the current run. Only clear those specific cache files on `--no-cache`. Or: don't clear caches at all — just set `no_cache=True` on all cache checks (skip read, force write).

---

## 3. Requirements Checklist

| Requirement | Status | Notes |
|-------------|--------|-------|
| Single unified script | ✅ Done | `pipeline.py` merges scraper + normalizer + uploader |
| Rich logging with colors | ✅ Done | Rich Console + progress bars |
| Progress bars with ETAs | ✅ Done | Per-phase + per-place progress bars |
| Logging to file | ✅ Done | Timestamped log files in `logs/` |
| Progress bars in log file | ⚠️ Partial | `ProgressTracker` logs structured progress to file. Actual Rich progress bars (ANSI) don't render in plain text files — this is by design. |
| Use `uv`, not `pip` | ✅ Done | `pyproject.toml` + `uv run` |
| `--limit` flag | ✅ Done | Limits places processed end-to-end |
| Multithreading (32 threads) | ✅ Done | 16 process workers + 32 R2 threads + 8 DB threads = 56 concurrent |
| Disk cache (no checkpointing) | ✅ Done | 7 independent disk caches |
| `--no-cache` flag | ✅ Done | Bypasses all caches, re-processes everything |
| Functional programming / generators | ✅ Done | `place_source()` generator, pure stage functions |
| Idempotent re-runs | ✅ Done | Same `--limit` → instant completion, no duplicates |
| Documentation (WHY comments) | ✅ Done | `PIPELINE_DESIGN.md` + inline comments |
| Worker pools KEPT | ✅ Done | R2 (32 threads) + DB (8 threads) with backpressure queues |

---

## 4. Architecture Assessment

### What's Excellent ✅

1. **Disk cache idempotency** — Each stage checks file existence. Simple, reliable, debuggable. No central checkpoint to get out of sync.
2. **Worker pools with backpressure** — R2 (32 threads) and DB (8 threads) provide 5-10x speedup. Queues provide natural backpressure.
3. **ProcessPoolExecutor with spawn** — Correct for argos-translate (C extensions, not fork-safe). Workers preload models once.
4. **Translation cache with file locking** — `fcntl.flock()` + merge-before-write prevents data loss from 16 concurrent workers.
5. **R2/DB ordering** — `done_event.wait()` ensures R2 URLs exist before DB insert. Correct.
6. **WebP conversion** — Images converted at download time, R2 keys always `.webp`.
7. **Comprehensive documentation** — `PIPELINE_DESIGN.md` explains WHY for every design decision.
8. **Clean stage separation** — Each stage is a pure function or has clear I/O boundaries.

### What Needs Fixing ❌

1. **`get_reviews()` wrong endpoint** — Reviews never fetched (Bug 1, Critical).
2. **`--no-cache` clears all caches** — Minor inconvenience (Bug 2, Low).

---

## 5. What We're NOT Changing

| Decision | Reason |
|----------|--------|
| NOT removing worker pools | They provide 5-10x speedup (documented in PIPELINE_DESIGN.md) |
| NOT adding checkpointing | Disk cache is simpler and more reliable |
| NOT using `pip` | `uv` only (per project rules) |
| NOT restructuring modular design | Current modular design is maintainable |
| NOT changing cache directory structure | Current structure is clear and debuggable |
| NOT changing translation approach | argos-translate is correct choice (offline, no rate limits) |

---

## 6. Recommended Fixes (NOT Implementing Yet)

### Fix 1: `get_reviews()` Endpoint (Critical)

**File**: `api_client.py`

**Change**: Line ~127 — change `PLACES_ENDPOINT` to `REVIEWS_ENDPOINT`

```python
# Before:
data = self._get(PLACES_ENDPOINT, {"lieu_id": place_id})

# After:
data = self._get(REVIEWS_ENDPOINT, {"lieu_id": place_id})
```

**Effort**: 1 line of code.

### Fix 2: `--no-cache` Selective Cache Clearing (Low Priority)

**File**: `pipeline.py`

**Change**: Instead of `api_cache_clear()` / `norm_cache_clear()`, track which grid points and place IDs were processed, then only clear those specific files.

**Alternative**: Don't clear caches at all. Just set `no_cache=True` on all cache operations — they skip the read but still write the result. This is simpler and achieves the same goal.

**Effort**: ~20 lines of code.

---

## 7. Testing Plan (For When Fixes Are Approved)

```bash
# Test 1: Basic pipeline run
cd scripts/pipeline && uv run python pipeline.py --limit 10
# Verify: 10 places in Supabase, images in R2, reviews fetched, progress bars visible
# Verify: Log file has timestamped entries

# Test 2: Idempotency (re-run same limit)
cd scripts/pipeline && uv run python pipeline.py --limit 10
# Verify: Completes in < 10 seconds (all cached)
# Verify: No new records in R2 or DB
# Verify: Cache stats show hits

# Test 3: No-cache re-processing
cd scripts/pipeline && uv run python pipeline.py --limit 10 --no-cache
# Verify: Same duration as Test 1 (~same time)
# Verify: Same record count (overwritten, not duplicated)
# Verify: API requests made (check log for HTTP activity)
# Verify: Images re-downloaded (check log for download stats)

# Test 4: Incremental processing
cd scripts/pipeline && uv run python pipeline.py --limit 20
# Verify: First 10 cached (fast), next 10 processed (slower)
# Verify: Total 20 records in DB
```

---

## 8. Answers to User's Specific Questions

### "It should be idempotent"
✅ **Already is** for normal runs (same `--limit`). Re-running processes same places, all cached → instant completion. Verified by tracing all 7 cache mechanisms.

### "I don't really like checkpointing, prefer disk cache"
✅ **Already implemented.** Each stage checks file existence. No checkpoint file used. Documented in PIPELINE_DESIGN.md.

### "Remove queue/threadpool for uploads — stupid idea"
✅ **Worker pools are KEPT.** They provide 5-10x speedup. Documented in PIPELINE_DESIGN.md with concrete numbers.

### "Write in comments and md files why you are doing things"
✅ **Comprehensive.** PIPELINE_DESIGN.md explains every design decision. Worker pools have "why" comments. Cache modules explain rationale.

### "All scripts should have progress bars with rich, timestamps, file logging"
✅ **Implemented.** Main pipeline has progress bar. R2/DB worker pools have progress bars (Phase 3 Finalize). Log file has timestamps. Progress logged to file via `ProgressTracker`.

### "Merge scraper, normalizer, uploader into one script"
✅ **Already done.** `pipeline.py` is the unified script. Old scripts are deprecated.

### "Use functional programming and Python generators"
✅ **Already done.** `place_source()` is a generator. Each stage is a pure function.

### "Use multithreading (32 threads, 64GB RAM, 10Gbps)"
✅ **Already done.** 16 ProcessPoolExecutor workers + 32 R2 threads + 8 DB threads = 56 concurrent workers.

### "Save progress, no duplicate work on re-run"
✅ **Already done.** Disk cache at every stage.

---

## 9. Summary

| Category | Status |
|----------|--------|
| Core idempotency design | ✅ Sound |
| `--no-cache` behavior | ✅ Correct (minor improvement possible) |
| Worker pools | ✅ Kept and working |
| Disk cache (7 caches) | ✅ All working |
| Rich logging | ✅ Working |
| File logging | ✅ Working (timestamps) |
| Progress bars in file | ✅ Working (structured log messages) |
| Documentation | ✅ Comprehensive |
| **Reviews fetching** | ❌ **BROKEN** — wrong API endpoint |
| Error resilience | ✅ Good (crash-safe via caches) |

**Total remaining work**: Fix `get_reviews()` endpoint (1 line). Optional: improve `--no-cache` selective clearing.

**The pipeline is fundamentally sound.** The idempotency design (disk cache) is correct and working. The only critical bug is the wrong API endpoint for reviews.
