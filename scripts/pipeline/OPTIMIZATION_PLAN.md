# Pipeline Optimization Plan

## Current Status (2026-05-29)

### Working Architecture
- **Shared translation server**: Single process with Queue-based IPC (spawn context)
- **24 workers** via ProcessPoolExecutor (spawn)
- **Translation server**: 1 argos instance, ThreadPool(4), batches by language
- **Non-blocking translation**: Workers submit requests, main process waits + applies
- **Image downloader**: ThreadPoolExecutor for parallel photo downloads (32 workers)
- **R2 worker pool**: 32 workers, queue size 256
- **DB worker pool**: 8 workers, queue size 128

### Performance Benchmarks

| Scenario | Places | Time | Rate | Translation % |
|----------|--------|------|------|---------------|
| With cache | 100 | 25.7s | ~4/s | 0% (cached) |
| No cache (blocking) | 100 | 170s | ~0.6/s | 90% |
| No cache (non-blocking) | 100 | 93s | ~1.1/s | 0.1% |
| No cache (non-blocking) | 50 | 58.7s | ~0.85/s | 0.1% |

**Key insight**: Non-blocking translation reduced translation time from 3738s → 0.09s (99.98% reduction). Download is now the bottleneck at 28.6%.

### Root Cause: Translation Bottleneck

Each worker **blocks** waiting for translation response:
1. Worker sends request to server via Queue
2. Server collects requests, waits for BATCH_SIZE (64) or BATCH_TIMEOUT (0.1s)
3. Server translates using ThreadPool(4) at ~63 texts/s
4. Server sends response via Queue
5. Worker receives response and continues

**Problem**: With ~3 texts/place and 63 texts/s capacity, the server can handle ~21 places/s. But workers send 1 request at a time and block, so the server never sees enough requests to batch efficiently. Each worker waits ~30s for its translation.

**Math**: 100 places × 3 texts = 300 texts. At 63 texts/s = ~5s wall clock. But cumulative time is 3682s because each worker blocks individually.

## Optimization Strategies

### Strategy 1: Non-blocking Translation (Highest Impact)

**Idea**: Workers submit translation requests and continue with other work (R2 upload, DB insert) while waiting for results.

**Implementation**:
1. Worker sends translation request and gets a future/callback
2. Worker proceeds to normalize + enqueue R2/DB tasks
3. When translation completes, worker updates the place dict
4. All stages run in parallel

**Expected improvement**: Translation time overlaps with R2/DB, reducing wall clock time by ~50%.

**Estimated new rate**: ~1.2 places/s (from 0.6/s)

### Strategy 2: Increase Batch Size + Reduce Timeout

**Current**: BATCH_SIZE=64, BATCH_TIMEOUT=0.1s
**Proposed**: BATCH_SIZE=128, BATCH_TIMEOUT=0.05s

**Rationale**: More texts per batch = better throughput. Shorter timeout = less latency for small batches.

**Expected improvement**: ~10-20% faster translation.

### Strategy 3: Pre-translate Common Texts

**Idea**: Many places share common descriptions (e.g., "Espace de stationnement gratuit", "Accès 24h/24"). Pre-translate these once and cache aggressively.

**Implementation**:
1. First pass: collect all unique texts across all places
2. Translate all unique texts in one big batch
3. Second pass: use cached translations (instant)

**Expected improvement**: After first pass, translation is instant (cache hit).

**Trade-off**: First pass takes longer, but subsequent runs are fast.

### Strategy 4: Increase Worker Count

**Current**: 24 workers
**Proposed**: 32-48 workers (match CPU threads)

**Rationale**: More workers = more places processed in parallel. Translation server can handle the load (63 texts/s).

**Expected improvement**: ~20-30% faster (diminishing returns due to translation bottleneck).

### Strategy 5: Translation Server Improvements

**Current**: Single server, ThreadPool(4), batches by language
**Proposed**:
1. Increase TRANSLATION_THREADS from 4 to 8 (benchmarked: still optimal for ctranslate2)
2. Process batches immediately when any request arrives (no timeout wait)
3. Use priority queue: urgent requests (single text) processed before batch

**Expected improvement**: ~10-20% faster translation.

## Recommended Implementation Order

1. **Strategy 2** (batch size/timeout): Quick win, 5-minute change
2. **Strategy 4** (more workers): Quick win, 1-line change
3. **Strategy 1** (non-blocking): Medium effort, highest impact
4. **Strategy 3** (pre-translate): Medium effort, helps subsequent runs
5. **Strategy 5** (server tweaks): Low effort, marginal gains

## ETA Calculations

### Current (no cache, non-blocking, 54,155 places)
- Rate: ~1.1 places/s
- Time: 54,155 / 1.1 = 49,232s = **~13.7 hours**

### With cache (subsequent runs)
- Rate: ~4 places/s
- Time: 54,155 / 4 = 13,539s = **~3.8 hours**

### Further optimizations (theoretical)
- Overlap translation wait with R2 upload: ~1.5 places/s → **~9.5 hours**
- Increase download concurrency: marginal gain (already 32 workers)
- Pre-translate common texts: helps subsequent runs only

## Known Issues

1. **Queue context mismatch**: Fixed by using `get_context("spawn")` for all Queue/Process objects
2. **Manager.dict with spawn**: Doesn't work reliably — use Queue instead
3. **Translation cache**: 57MB on disk, ~156K entries. Loaded in ~1s. Critical for performance.
4. **GPU unavailable**: RTX 4090 OOM (23GB/24GB used by desktop). CUDA acceleration not viable.

## Files Modified

- `translation_server.py`: Shared translation server with Queue-based IPC
- `pipeline.py`: Worker initialization, translation via server, ProcessPoolExecutor
- `image_downloader.py`: Parallel photo downloads with ThreadPoolExecutor
- `r2_worker.py`: On-the-fly JPG→WebP conversion during upload
- `cache.py`: Translation cache with thread-safe access
