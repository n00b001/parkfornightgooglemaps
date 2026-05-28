# Pipeline Idempotency — Scientific Analysis & Fix Plan

## 1. OBSERVATION (Problem Statement)

Running `--limit 3` twice produces **different results** each time:
- Run 1: processes 3 places from grid points A, B
- Run 2: processes 3 **different** places from grid points C, D

Running `--limit 3 --no-cache` does **not** re-upload to R2 (head_object skip) and does **not** re-process the same places.

## 2. HYPOTHESES (Root Causes)

### H1: Place-level stages are never marked in the checkpoint

**Evidence:**
- `checkpoint.mark_place_stage_done()` is defined in `checkpoint.py:102` but **never called** in `pipeline.py` (grep confirms 0 calls)
- `checkpoint.is_place_fully_processed()` checks 4 stages: `extracted`, `normalized`, `images_uploaded_r2`, `db_inserted` — **none are ever marked**
- `place_source()` calls `checkpoint.is_place_fully_processed(place_id)` at line 356 — always returns `False`
- `checkpoint._save()` at line 536 saves the file, but no stages were added

**Impact:** The pipeline has no memory of which places it has processed. Every run treats all places as new.

### H2: Grid points are marked done after API fetch, not after full processing

**Evidence:**
- `checkpoint.mark_grid_point_done(lat, lng)` at `pipeline.py:349` (empty grid) and `:361` (after yielding places)
- Called inside `place_source()` generator — immediately after `api.get_places(lat, lng)` returns
- The places from that grid point may not have completed the full pipeline (R2 upload, DB insert) yet

**Impact on Run 2:** `get_remaining_grid_points()` skips all grid points from Run 1. The pipeline fetches from NEW grid points → processes DIFFERENT places.

### H3: `--no-cache` does not propagate to R2 worker

**Evidence:**
- `no_cache` passed to `ImageDownloader(no_cache=no_cache)` at `pipeline.py:411` ✓
- `no_cache` stored globally via `globals()["_no_cache"]` at `pipeline.py:649` — but **never read** by any worker
- `R2WorkerPool.__init__()` accepts `(r2_config, num_workers, queue_size)` — **no `no_cache` parameter**
- `_upload_single()` at `r2_worker.py:37` always does `r2.head_object()` → skips existing objects regardless of `--no-cache`

**Impact:** Even with `--no-cache`, R2 uploads are skipped for existing objects. The flag has no effect on R2.

### H4: `--no-cache` does not propagate to DB worker

**Evidence:**
- `DBWorkerPool.__init__()` accepts `(num_workers, queue_size)` — **no `no_cache` parameter**
- DB uses `ON CONFLICT DO UPDATE` / `ON CONFLICT DO NOTHING` — always idempotent

**Impact:** DB behavior is correct (upsert is idempotent). No change needed for DB.

### H5: Image downloader IS correct

**Evidence:**
- `image_downloader.py:101`: `if webp_path.exists() and not self._no_cache: return True` — skips when cached ✓
- `image_downloader.py:108`: `if save_path.exists() and not self._no_cache:` — skips jpg→webp conversion when cached ✓
- With `--no-cache`: re-downloads and overwrites ✓

**Impact:** Image downloader behavior is correct. No change needed.

## 3. EXPERIMENT (Execution Trace)

### Run 1: `--limit 3`

```
1. PipelineCheckpoint() → loads empty checkpoint
2. place_source():
   - generate_grid_points() → ~500 points
   - get_remaining_grid_points() → all 500 (none done)
   - Grid point (35.0, -25.0): api.get_places() → [place_A, place_B, ...]
     - is_place_fully_processed(A) → False (H1)
     - yield place_A
     - is_place_fully_processed(B) → False
     - yield place_B
     - mark_grid_point_done(35.0, -25.0)  ← marked after fetch (H2)
   - Grid point (35.0, -23.0): api.get_places() → [place_C, ...]
     - yield place_C
     - mark_grid_point_done(35.0, -23.0)
   - total_yielded = 3 → stop
3. Process: A → extract → download → reviews → translate → normalize → R2 → DB → checkpoint._save()
   Process: B → same pipeline
   Process: C → same pipeline
4. Checkpoint saved:
   - grid_points_done: ["35.0,-25.0", "35.0,-23.0"]
   - places: {} (no stages marked! H1)
```

### Run 2: `--limit 3`

```
1. PipelineCheckpoint() → loads checkpoint with 2 grid points done
2. place_source():
   - generate_grid_points() → ~500 points
   - get_remaining_grid_points() → 498 points (skips 35.0,-25.0 and 35.0,-23.0) ← H2
   - Grid point (35.0, -21.0): api.get_places() → [place_D, place_E, ...]
     - yield place_D (DIFFERENT from Run 1!)
     - yield place_E
     - mark_grid_point_done(35.0, -21.0)
   - Grid point (35.0, -19.0): api.get_places() → [place_F, ...]
     - yield place_F
     - mark_grid_point_done(35.0, -19.0)
   - total_yielded = 3 → stop
3. Process: D, E, F → NEW images downloaded, NEW R2 uploads, NEW DB inserts
```

**Result:** Run 2 processes places D, E, F — completely different from Run 1's A, B, C. **NOT idempotent.**

### Run 3: `--limit 3 --no-cache`

Same as Run 2 (different places) PLUS:
- Images: re-downloaded (ImageDownloader handles no_cache ✓)
- R2: still skipped (head_object check, no_cache not propagated — H3)
- DB: upsert (idempotent, no change needed)

**Result:** Different places than Run 1, R2 not re-uploaded. **NOT idempotent.**

## 4. CONCLUSION (Required Changes)

### Change 1: Track processed place IDs in checkpoint

**File:** `checkpoint.py`

Add:
- `processed_place_ids`: `list[int]` — place IDs that completed the full pipeline
- `place_grid_points`: `dict[str, str]` — maps `str(place_id)` → `"lat,lng"` (for re-fetch on --no-cache)
- `is_place_processed(place_id)`: check if place ID is in `processed_place_ids`
- `mark_place_processed(place_id, lat, lng)`: add to list + store grid point
- `get_processed_place_ids(limit)`: return up to `limit` processed IDs

Keep existing `mark_place_stage_done` / `is_place_fully_processed` for backward compatibility (they track partial progress for resume).

### Change 2: Yield processed places first in place_source

**File:** `pipeline.py` — `place_source()` function

New logic:
```
Phase 1: Already-processed places (from checkpoint)
  For each processed place ID (up to limit):
    If no_cache:
      Look up grid point → re-fetch from API → yield place
    Else (cache mode):
      Yield cached marker: {"id": place_id, "_cached": True}
    Count toward limit

Phase 2: New places from grid points (existing logic)
  For each remaining grid point:
    Fetch places from API
    Skip already-processed places
    Yield new places
    Count toward limit
```

### Change 3: Handle cached markers in run_pipeline

**File:** `pipeline.py` — `run_pipeline()` function

For each yielded item:
- If `_cached` marker: skip pipeline entirely, count toward limit, print "[dim]✓ Place {id} cached[/dim]"
- If raw place: run full pipeline as before

After full pipeline completes:
- Call `checkpoint.mark_place_processed(place_id, lat, lng)`
- This replaces the bare `checkpoint._save()` at line 536

### Change 4: Pass no_cache to R2 worker

**File:** `r2_worker.py`

Changes:
- `R2WorkerPool.__init__()`: add `no_cache: bool = False` parameter
- Store `self._no_cache = no_cache`
- `_upload_single()`: skip `head_object` check when `self._no_cache` is True
- Pass `no_cache` through `_process_task()` → `_upload_single()`

**File:** `pipeline.py`

- `R2WorkerPool(_r2_config, no_cache=no_cache)` — pass flag at construction

### Change 5: Track grid point per place

**File:** `pipeline.py` — `place_source()` function

- Yield `(place_data, lat, lng)` tuples instead of raw place dicts
- `run_pipeline` extracts place data and grid point from tuple
- On pipeline completion, store grid point in checkpoint via `mark_place_processed(place_id, lat, lng)`

### Change 6: Move grid point marking to after full processing

**File:** `pipeline.py`

- Remove `checkpoint.mark_grid_point_done(lat, lng)` from `place_source()` generator
- Track which grid points have all places processed in `run_pipeline()`
- Mark grid point done after ALL places from that grid point complete the pipeline

**Rationale:** Currently grid points are marked done after API fetch (line 361), before places complete the pipeline. This causes Run 2 to skip those grid points and fetch from new ones.

## 5. IMPLEMENTATION PLAN (Ordered by Dependency)

### Phase 1: Checkpoint Extensions (no dependencies)

- [ ] **1.1** Add `processed_place_ids` and `place_grid_points` to checkpoint structure
- [ ] **1.2** Add `is_place_processed(place_id)` method
- [ ] **1.3** Add `mark_place_processed(place_id, lat, lng)` method
- [ ] **1.4** Add `get_processed_place_ids(limit)` method
- [ ] **1.5** Add `get_place_grid_point(place_id)` method

### Phase 2: R2 Worker no_cache Support (depends on nothing)

- [ ] **2.1** Add `no_cache` parameter to `R2WorkerPool.__init__()`
- [ ] **2.2** Store `self._no_cache` instance variable
- [ ] **2.3** Modify `_upload_single()` to skip `head_object` when `no_cache=True`
- [ ] **2.4** Pass `no_cache` through `_process_task()` → `_upload_single()`

### Phase 3: API Client Enhancement (depends on nothing)

- [ ] **3.1** Add `get_place_by_grid_point(place_id, lat, lng)` method to `Park4NightAPI`
  - Fetches grid point, finds specific place by ID, returns it
  - Returns `None` if place not found in grid point response

### Phase 4: place_source Restructure (depends on Phase 1, 3)

- [ ] **4.1** Change yield format from `place` to `(place_or_marker, lat_lng, is_cached)`
- [ ] **4.2** Phase 1: yield already-processed places from checkpoint
  - Cache mode: yield `({"id": place_id, "_cached": True}, None, True)`
  - no-cache mode: look up grid point, re-fetch from API, yield `(place, (lat, lng), False)`
- [ ] **4.3** Phase 2: yield new places from remaining grid points
  - Skip already-processed places via `is_place_processed()`
  - Yield `(place, (lat, lng), False)`
- [ ] **4.4** Remove `mark_grid_point_done()` calls from `place_source()`

### Phase 5: run_pipeline Updates (depends on Phase 2, 4)

- [ ] **5.1** Handle cached markers: skip pipeline, count toward limit
- [ ] **5.2** Extract `(place, grid_point, is_cached)` from yield tuples
- [ ] **5.3** After full pipeline: call `checkpoint.mark_place_processed(place_id, lat, lng)`
- [ ] **5.4** Pass `no_cache` to `R2WorkerPool()` constructor
- [ ] **5.5** Track grid point completion: mark grid point done after all its places complete
- [ ] **5.6** Update `places_to_process` collection to handle new yield format

### Phase 6: Verification

- [ ] **6.1** Test: Run 1 with `--limit 3` → 3 places processed, checkpoint has 3 processed IDs
- [ ] **6.2** Test: Run 2 with `--limit 3` → same 3 places cached, finishes quickly, no new records
- [ ] **6.3** Test: Run 3 with `--limit 3 --no-cache` → same 3 places re-processed, R2 re-uploaded, comparable duration
- [ ] **6.4** Test: Run 4 with `--limit 10` → 3 cached + 7 new places processed
- [ ] **6.5** Test: Verify checkpoint file structure after each run

## 6. RISK ASSESSMENT

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Checkpoint file grows large (200K places × grid point mapping) | Medium | ~10MB for 200K places — manageable. Consider periodic cleanup of old entries. |
| API returns different places for same grid point (new places added) | Low | `get_place_by_grid_point()` finds by ID — works even if response changes. |
| Place no longer exists in API response (deleted) | Low | `get_place_by_grid_point()` returns None → skip with warning. |
| Backward compatibility with existing checkpoint | Low | New fields are optional — existing checkpoint loads fine (missing keys → defaults). |
| Grid point tracking complexity | Medium | Keep it simple: track in `run_pipeline`, not `place_source`. |

## 7. FILES TO MODIFY

| File | Changes | Lines Affected |
|------|---------|---------------|
| `checkpoint.py` | Add processed place tracking | ~20 new lines |
| `api_client.py` | Add `get_place_by_grid_point()` | ~10 new lines |
| `pipeline.py` | Restructure `place_source()`, update `run_pipeline()` | ~50 lines modified |
| `r2_worker.py` | Add `no_cache` support | ~10 lines modified |

## 8. NOT CHANGING

| Component | Reason |
|-----------|--------|
| `image_downloader.py` | Already handles `no_cache` correctly |
| `db_worker.py` | Upsert is naturally idempotent; no change needed |
| `translator.py` | In-memory cache is per-run; no persistent cache needed |
| `normalizer.py` | Pure function; no state to track |
| `config.py` | No configuration changes needed |
