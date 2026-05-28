# Pipeline Design — Rationale & Architecture

## Core Principle: Disk Cache > Checkpointing

**Every long-running function is independently idempotent via disk cache.** No central checkpoint tracks "what stage are we at?" — each function checks if its output already exists on disk and skips work if so.

**Why this is better than checkpointing:**
- Checkpointing requires a central state machine that must be kept in sync with actual work done. If the checkpoint says "stage 3 done" but the file doesn't exist, the pipeline breaks.
- Disk caching is self-verifying: if the output file exists, the work is done. No separate state to manage.
- Each function can be tested in isolation — no checkpoint fixture needed.
- Resume after crash is automatic: just re-run, each function skips what's already done.

**The checkpoint file still exists** but only for one purpose: **tracking which grid points have been scraped** (API rate limiting). This is not about idempotency — it's about not re-fetching the same API data.

## Why Queue-Based Worker Pools Exist

**R2WorkerPool and DBWorkerPool are queue-based thread pools for a specific reason: raw I/O is slow.**

- R2 upload: ~100-500ms per image (network + S3 API). A place has 5-20 images. Sequential uploads would add 0.5-10s per place.
- DB insert: ~50-200ms per place (PostgreSQL round-trip + transaction). Sequential inserts would add 0.05-0.2s per place.

**With queue-based pools:**
- Worker threads process places in parallel (extract → download → translate → normalize)
- When a place is ready, it's enqueued to R2/DB pools and the worker moves to the next place
- R2/DB uploads happen in parallel with worker processing
- Total throughput: ~16 places/s (limited by translation CPU) instead of ~2 places/s (limited by I/O)

**This is why the pools exist.** Removing them would make the pipeline 5-10x slower. The pools are NOT being removed.

## Why ProcessPoolExecutor (not ThreadPoolExecutor)

**argos-translate is NOT thread-safe across processes.** It uses global state for model loading. The current design uses ProcessPoolExecutor (spawn) so each worker process gets its own argos-translate instance.

**This is intentional.** The alternative (ThreadPoolExecutor with per-thread model preloading) would require:
- Each thread to load ~30 language models (~500MB RAM per thread)
- 16 threads × 500MB = 8GB RAM just for models
- With spawn, models are loaded once per process and shared across all places in that process

**The trade-off:** ProcessPoolExecutor has pickling overhead (place data must be serialized), but this is negligible compared to translation time (~2s per place).

## Current Architecture

```
Main Process
├── place_source() — generator yielding places from API
│   ├── Phase 1: already-processed places (from checkpoint)
│   └── Phase 2: new places from remaining grid points
├── ProcessPoolExecutor (spawn, 16 workers)
│   └── Each worker process:
│       ├── preload_models() — load argos models once
│       └── _worker_process_place():
│           ├── extract_place_data()      — pure function
│           ├── download_images()         — disk cache (.webp exists → skip)
│           ├── api.get_reviews()         — API call (rate limited)
│           ├── stage_translate()         — CPU (argos, persistent cache)
│           └── stage_normalize()         — pure function
├── R2WorkerPool (32 threads, queue-based)
│   └── head_object check (exists → skip) + put_object
├── DBWorkerPool (8 threads, queue-based)
│   └── ON CONFLICT DO UPDATE (upsert)
└── PipelineCheckpoint — tracks grid points + processed place IDs
```

## Idempotency Via Disk Cache

| Function | Cache Mechanism | Skip Condition |
|----------|----------------|----------------|
| `download_images()` | `.webp` file on disk | File exists (unless `--no-cache`) |
| `translate_batch()` | `data/translation_cache.json` | Text already in cache |
| `stage_normalize()` | Pure function | N/A (always runs, but fast) |
| `R2WorkerPool` | `head_object` API call | Object exists in R2 (unless `--no-cache`) |
| `DBWorkerPool` | `ON CONFLICT DO UPDATE` | Place ID exists in DB |
| `place_source()` | Checkpoint (grid points) | Grid point already scraped |

**Re-running with same `--limit N`:**
- Already-processed places: skipped (checkpoint knows grid points are done)
- No new API calls, no new downloads, no new translations, no new uploads
- Finishes in seconds

**Re-running with `--limit N --no-cache`:**
- Re-fetch from API (same places, fresh data)
- Re-download images (overwrite existing .webp)
- Re-translate (bypass cache)
- Re-upload to R2 (overwrite existing objects)
- Re-insert to DB (ON CONFLICT DO UPDATE)

## Issues Found & Fixes

### Issue 1: Race Condition — Checkpoint Before R2/DB Complete

**Problem:** Places are marked as processed in the checkpoint AFTER enqueuing R2/DB tasks, but BEFORE those tasks complete. If the pipeline is interrupted (SIGINT) between enqueuing and completing:

1. Worker completes place → main process enqueues R2/DB → marks place as processed → saves checkpoint
2. SIGINT received → checkpoint saved → R2/DB workers killed
3. On resume: place is skipped (checkpoint says done) → R2/DB uploads for this place are LOST

**Why this matters:** The place exists in the checkpoint as "done" but images are missing from R2 and data is missing from DB. On resume, the place is skipped entirely.

**Fix:** Wait for R2/DB tasks to complete (via `done_event.wait()`) BEFORE marking the place as processed. This ensures the checkpoint only marks a place as done when ALL work is actually complete.

**Why not remove the pools?** The pools exist for performance (see above). The fix is to wait for completion, not to remove the pools.

### Issue 2: No Persistent Translation Cache (FIXED)

**Problem:** Translation cache was in-memory only. On restart, all translations were re-computed.

**Fix:** Added `data/translation_cache.json` — loaded on first use, saved after each batch. Thread-safe via lock.

### Issue 3: Grid Points Not Tracked

**Problem:** `mark_grid_point_done()` exists but is never called. The pipeline tracks processed places but not completed grid points. If the pipeline is interrupted during Phase 2, it re-scrapes the same grid points (but skips known places within them).

**Why this matters:** Unnecessary API calls on resume. The API has rate limits — re-scraping the same grid points wastes time and risks hitting rate limits.

**Fix:** Call `mark_grid_point_done()` after all places in a grid point are processed.

## Implementation Plan

### Phase 1: Fix Race Condition (Critical)

**File:** `pipeline.py`

**Change:** After enqueuing R2/DB tasks, wait for `done_event.wait()` before marking the place as processed.

**Why:** Ensures checkpoint only marks a place as done when ALL work is complete. Prevents data loss on interrupt.

**Before:**
```python
# Enqueue R2 (non-blocking)
place = stage_enqueue_r2(place, r2_pool)
# Enqueue DB (non-blocking)
stage_enqueue_db(place, db_pool)
# Mark done (RACE: R2/DB may not be complete!)
checkpoint.mark_place_processed(place_id, lat, lng)
```

**After:**
```python
# Enqueue R2 (blocking — waits for completion)
place = stage_enqueue_r2(place, r2_pool, checkpoint)
# Enqueue DB (blocking — waits for completion)
stage_enqueue_db(place, db_pool, checkpoint)
# Mark done (safe: R2/DB are complete)
checkpoint.mark_place_processed(place_id, lat, lng)
```

**Why keep the pools?** The pools still exist and still process in parallel. The difference is that the main process waits for THIS place's tasks to complete before moving on. Other places' tasks are still processed in parallel by the pools.

### Phase 2: Track Grid Points

**File:** `pipeline.py`

**Change:** After processing all places from a grid point, call `mark_grid_point_done()`.

**Why:** Prevents re-scraping the same grid points on resume.

### Phase 3: Documentation

**File:** `PIPELINE_DESIGN.md` (this file)

**Change:** Document all design decisions with rationale.

**Why:** Prevents future agents from re-implementing the same things without understanding why.

## Files Modified

| File | Change | Why |
|------|--------|-----|
| `translator.py` | Added persistent cache (load/save from disk) | Translation cache survives restart |
| `pipeline.py` | Wait for R2/DB completion before marking done | Fix race condition on interrupt |
| `pipeline.py` | Track grid points in checkpoint | Prevent re-scraping on resume |
| `PIPELINE_DESIGN.md` | Document all design decisions | Prevent future re-implementation |
