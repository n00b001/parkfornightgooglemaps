# Unified Pipeline Design

## Why This Exists

Previous agents implemented, unimplemented, and re-implemented the same pipeline patterns multiple times because design decisions were not documented. This file is the **single source of truth** for the pipeline's architecture. Read it before making changes.

## Core Philosophy: Disk Cache, Not Checkpointing

### Why NOT checkpointing

Checkpointing requires a central authority that tracks the state of every place through every stage. This is:
- **Fragile**: If the checkpoint file gets corrupted or out of sync with reality, you get duplicate work or missed places
- **Complex**: The old `PipelineCheckpoint` tracked grid points, place IDs, grid point mappings, AND per-place stage flags — 5 different data structures that must stay consistent
- **Hard to debug**: When something goes wrong, you need to cross-reference the checkpoint file against disk files, R2 bucket contents, and database records

### Why disk cache

Each long-running function checks if its **output file exists** before doing work:

| Stage | Output | Cache Check | Idempotent Because |
|-------|--------|-------------|--------------------|
| API fetch (places) | `cache/api/{lat}_{lng}.json` | File exists | Park4Night API returns same data for same grid point |
| API fetch (reviews) | `cache/api/reviews_{place_id}.json` | File exists | Reviews don't change frequently enough to matter |
| Image download | `data/images/places/{id}/{photo}_thumb.webp` | File exists | Same URL → same image |
| Translation | `cache/translations.json` (JSON dict) | Key in dict | Same input → same translation |
| Normalization | `cache/normalized/{place_id}.json` | File exists | Pure function: same input → same output |
| R2 upload | Cloudflare R2 bucket | `head_object` returns 200 | S3 put_object is idempotent |
| DB insert | Supabase PostgreSQL | `ON CONFLICT (id) DO UPDATE` | SQL upsert is idempotent |

**Result**: Re-running the pipeline with the same `--limit` completes instantly because every stage finds its output already on disk. No checkpoint file needed.

### How `--no-cache` works

Every cache check has a `bypass` flag. When `--no-cache` is set:
- API cache: Delete the file before fetching (re-download from Park4Night)
- Image cache: Delete the file before downloading (re-download from CDN)
- Translation cache: Clear the in-memory dict (re-translate everything)
- Normalization cache: Delete the file before normalizing (re-run pure function)
- R2 upload: Skip `head_object` check (force re-upload, overwrites existing)
- DB insert: Uses `ON CONFLICT DO UPDATE` (always updates, never creates duplicates)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Main Process                             │
│                                                                 │
│  ┌──────────┐    ┌───────────┐    ┌──────────────────────────┐  │
│  │ Grid     │───▶│ Place     │───▶│ ProcessPoolExecutor      │  │
│  │ Iterator │    │ Generator │    │ (spawn, N workers)       │  │
│  └──────────┘    └───────────┘    └──────────┬───────────────┘  │
│                                              │                   │
│                              Each worker does per place:         │
│                              ┌───────────────▼───────────────┐   │
│                              │ 1. Extract (API cache)         │   │
│                              │ 2. Download images (disk cache)│   │
│                              │ 3. Fetch reviews (API cache)   │   │
│                              │ 4. Translate (disk cache)      │   │
│                              │ 5. Normalize (disk cache)      │   │
│                              └───────────────┬───────────────┘   │
│                                              │                   │
│                              Main process collects results:      │
│                              ┌───────────────▼───────────────┐   │
│                              │ 6. Enqueue R2 upload (async)   │   │
│                              │ 7. Enqueue DB insert (async)   │   │
│                              └───────────────┬───────────────┘   │
│                                              │                   │
│  ┌──────────────────────┐  ┌────────────────▼───────────────┐   │
│  │ R2 Worker Pool       │  │ DB Worker Pool                 │   │
│  │ (32 threads, queue)  │  │ (8 threads, queue)             │   │
│  └──────────────────────┘  └────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Why Worker Pools Are KEPT (Not Removed)

The R2 upload pool (32 threads) and DB insert pool (8 threads) were added because **the script was very slow without them**. Here's why:

### R2 Upload Pool (32 threads)
- Each image upload is a network round-trip to Cloudflare (~50-200ms)
- A place has 2-10 photos, each with thumb + large = 4-20 uploads per place
- With 100 places: 400-2000 sequential uploads = 20-400 seconds
- With 32 parallel uploads: 12-62 seconds (5-8x faster)
- **The queue provides backpressure**: if uploads slow down, the pipeline waits instead of overwhelming R2

### DB Insert Pool (8 threads)
- Each place insert involves: upsert lookups + insert place + insert junctions + insert reviews
- Multiple SQL round-trips per place (~10-50ms each)
- With 8 parallel connections: 4-8x faster than sequential
- **Each worker has its own psycopg2 connection** (connections are not thread-safe)
- **The queue provides backpressure**: if DB is slow, the pipeline waits

### Why NOT remove them
Removing worker pools and going sequential would make the pipeline 5-10x slower. The queues are the RIGHT abstraction — they decouple the fast stages (extract, normalize) from the slow stages (upload, insert). If you remove them, you're trading correctness for speed without gaining anything.

## File Structure

```
scripts/pipeline/
├── PIPELINE_DESIGN.md      # This file — read before making changes
├── pipeline.py             # Unified entry point (merged scraper+normalizer+uploader)
├── config.py               # Configuration (API endpoints, rate limits, grid)
├── cache.py                # Disk cache primitives (API, translation, normalization)
├── api_client.py           # Park4Night API client with disk cache
├── image_downloader.py     # Image downloader with WebP conversion + disk cache
├── translator.py           # Argos-translate wrapper with persistent disk cache
├── normalizer.py           # Pure normalization functions (no I/O)
├── r2_worker.py            # R2 upload worker pool (32 threads, queue-based)
├── db_worker.py            # DB insert worker pool (8 threads, queue-based)
├── logging_setup.py        # Rich console + file logging with progress bars
└── pyproject.toml          # Dependencies (managed by uv)
```

## Cache Directory Structure

```
scripts/data/cache/
├── api/
│   ├── 48.8566_2.3522.json      # Grid point → places list
│   ├── reviews_12345.json        # Place ID → reviews list
│   └── ...
├── normalized/
│   ├── 12345.json                # Place ID → normalized place dict
│   └── ...
└── translations.json             # {original_text: translated_text} dict
```

## Logging Design

### Console Output (Rich)
- Colored output with progress bars, spinners, and ETA
- Progress bars for each major phase (extract, download, translate, normalize, upload, insert)
- Per-place progress bar showing overall completion

### Log File
- Plain text with timestamps: `2024-01-15 14:30:22 [INFO    ] Processing place 12345`
- Progress updates written periodically (every N places or every 5 seconds)
- Log file path printed at startup

### Why progress bars must be in the log file too
When running the pipeline in the background (e.g., via tmux or cron), you can't see the Rich progress bars. The log file is the only way to monitor progress. Every `logger.info()` call goes to both console and file.

## Translation Cache Design

### Why persistent (not in-memory)
The old pipeline kept translations in RAM only. This meant:
- Re-running the pipeline always re-translated everything (argos-translate is slow: ~100ms per string)
- With 10,000 unique strings: ~17 minutes of translation time on every run
- The translation cache could grow to 50-100MB in RAM

### New design
- `translations.json` file in cache directory
- Loaded at startup into an in-memory dict (fast lookups)
- Saved to disk every 1000 new translations (or on shutdown)
- Thread-safe: `threading.Lock` protects writes
- Process-safe: only one process writes at a time (main process handles saves)

### Why argos-translate (not Google Translate)
- **Offline**: No internet required after initial package download
- **No rate limits**: Can use 64 parallel threads
- **Free**: No API keys, no costs
- **Deterministic**: Same input → same output (important for idempotency)

## Multiprocessing Design

### Why `spawn` (not `fork`)
- argos-translate uses C extensions that are NOT fork-safe
- `fork()` inherits parent's memory including locked mutexes → deadlocks
- `spawn` starts fresh Python interpreters → no inherited state

### Why ProcessPoolExecutor (not ThreadPoolExecutor) for main pipeline
- argos-translate releases the GIL during translation → benefits from true parallelism
- Each worker process gets its own argos models → no contention
- Workers are CPU-bound (translation) + I/O-bound (API, images) → processes are better

### Why ThreadPoolExecutor for R2/DB pools
- R2 uploads and DB inserts are purely I/O-bound
- Threads share memory → no need to serialize data between processes
- Each thread has its own boto3 client / psycopg2 connection → no contention

## Idempotency Guarantees

### Running with `--limit N` twice
1. First run: Downloads N places, processes them, uploads to R2 + DB
2. Second run: All cache files exist → every stage skips → completes in seconds
3. **No duplicate records** in R2 or DB (upserts + head_object checks)

### Running with `--limit N --no-cache`
1. Bypasses all disk caches
2. Re-downloads from Park4Night API
3. Re-downloads images from CDN
4. Re-translates all text
5. Re-uploads to R2 (overwrites existing objects)
6. Re-inserts to DB (upserts update existing records)
7. **No duplicate records** — same number of records as first run

### Running with `--limit N` then `--limit M` (M > N)
1. First N places: All cached → skip instantly
2. Next M-N places: Process normally
3. **No duplicate work** for first N places

## Testing Strategy

### Small-scale testing (required before any PR)
```bash
# First run: should process 10 places end-to-end
cd scripts/pipeline && uv run python pipeline.py --limit 10

# Second run: should complete instantly (all cached)
cd scripts/pipeline && uv run python pipeline.py --limit 10

# No-cache run: should take same time as first run
cd scripts/pipeline && uv run python pipeline.py --limit 10 --no-cache
```

### Verification checklist
- [ ] 10 places appear in Supabase (`SELECT COUNT(*) FROM "Place"`)
- [ ] Images appear in R2 bucket (check via Cloudflare dashboard)
- [ ] Re-run completes in < 5 seconds (all cached)
- [ ] No duplicate records after re-run
- [ ] `--no-cache` run produces same record count (not double)

## Anti-Patterns (DO NOT DO)

1. **DO NOT use checkpoint files** — disk cache is simpler and more reliable
2. **DO NOT remove worker pools** — they exist for performance, removing them makes the pipeline 5-10x slower
3. **DO NOT use `pip`** — use `uv add` and `uv run` exclusively
4. **DO NOT delete data files** — the entire pipeline is append-only with cache-based skip logic
5. **DO NOT use Park4Night CDN URLs** — all images must come from local paths only
6. **DO NOT suppress stanza MWT warnings** — they are expected and harmless (argostranslate issue)
7. **DO NOT implement without documentation** — write WHY in comments and markdown files

## Dependencies

Managed by `uv` via `pyproject.toml`:
- `requests` — HTTP client for Park4Night API
- `rich` — Console output with progress bars and colors
- `argostranslate` — Offline neural machine translation
- `boto3` — Cloudflare R2 (S3-compatible) client
- `psycopg2-binary` — PostgreSQL client for Supabase
- `python-dotenv` — Environment variable loading
- `Pillow` — Image format conversion (JPEG → WebP)
