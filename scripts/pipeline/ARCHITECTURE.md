# Unified Pipeline Architecture

> **THIS IS THE ACTIVE SCRIPT.** Use `scripts/pipeline/` for all ETL operations.
> The old `scripts/normalize/` directory is **deprecated** — do not use it.

## Overview

Single script `pipeline.py` that merges the three existing scripts (scraper, normalizer, uploader) into one generator-based ETL pipeline. Each place flows through all stages sequentially:

```
Grid Point → Scrape Places → (for each place:)
  1. EXTRACT:    API call → raw place dict
  2. TRANSFORM:  Normalize + translate to English
  3. IMAGES-LOCAL: Download photos to disk
  4. IMAGES-R2:   Upload photos to Cloudflare R2
     (R2 URLs injected into place data)
  5. LOAD-DB:    Insert place + reviews into Supabase PostgreSQL
```

## Directory Structure

```
scripts/pipeline/
├── __init__.py          # package marker
├── pipeline.py          # main entry point (CLI, orchestrator)
├── config.py            # all configuration (API endpoints, rate limits, paths)
├── checkpoint.py        # unified checkpoint system (JSON-based)
├── api_client.py        # Park4Night API client (rate-limited, retry)
├── image_downloader.py  # download images from CDN to local disk
├── translator.py        # Argos Translate (offline) with caching
├── normalizer.py        # normalize place/review data + translate
├── r2_uploader.py       # upload images to Cloudflare R2
├── supabase_uploader.py  # insert records into Supabase PostgreSQL
└── logging_setup.py     # dual-output logging (console + file)
```

## Checkpoint System

Single checkpoint file `scripts/data/pipeline_checkpoint.json` tracks progress per place:

```json
{
  "version": 1,
  "grid_points_done": ["35.0,-25.0", ...],
  "places": {
    "123456": {
      "scraped_at": "2024-01-01T00:00:00Z",
      "stages": {
        "extracted": true,
        "normalized": true,
        "images_downloaded": true,
        "images_uploaded_r2": true,
        "reviews_fetched": true,
        "db_inserted_place": true,
        "db_inserted_reviews": true
      }
    }
  },
  "stats": {
    "total_places_processed": 0,
    "total_reviews_processed": 0,
    "total_images_downloaded": 0,
    "total_images_uploaded_r2": 0,
    "errors": []
  }
}
```

On re-run, the pipeline:
1. Loads checkpoint
2. Skips grid points already done
3. For each place, skips stages already completed

## Multithreading Strategy

All I/O-bound operations use `ThreadPoolExecutor` (not ProcessPoolExecutor) since Python's GIL doesn't block during I/O:

| Stage | Workers | Reasoning |
|-------|---------|-----------|
| API scraping (grid points) | 8 | Rate-limited by API, too many = ban risk |
| Image download (per place) | 32 images/worker, 4 workers for places in parallel | Disk + network bound, high bandwidth available |
| Translation (batch) | 64 threads to Argos Translate (offline) | CPU-bound (neural net inference), no rate limits, fully offline |
| R2 upload (images) | 16 workers | Network-bound, Cloudflare handles high concurrency well |
| DB insert (places) | Sequential with batch inserts of 500-1000 at a time for efficiency.

## Progress Bar Design

**Console**: Rich `Progress` with spinner, bar, completion count, elapsed time
**Log file**: Plain text progress updates written every N items via `logger.info()`

```python
# Console shows:
# ⠋ Processing places ━━━━━━━━━━━━━━━━ 100/1000 • 00:32

# Log file shows (every 50 items):
# [Pipeline] 50,498,765,432,123 (items)
```

## Configuration

All config in `config.py`:
- API endpoints + rate limits
- Geographic grid regions
- Output paths (data dir, images dir)
- Service/activity codes

## CLI Interface

```bash
cd scripts/pipeline
uv run python pipeline.py [options]

Options:
  --limit N          Process only first N places end-to-end (default: no limit)
  --dry-run          Show what would be done without making changes
  --r2-config PATH   Path to R2 config JSON (default: ../upload/r2-config.json)
  --env PATH         Path to .env file (default: ../../.env)
```

## Running the Pipeline

```bash
# Full run (no limit):
cd scripts/pipeline && uv run python pipeline.py

# Limited run (10 places end-to-end):
cd scripts/pipeline && uv run python pipeline.py --limit 10

# Dry run:
cd scripts/pipeline && uv run python pipeline.py --dry-run
```

## Translation

Uses **Argos Translate** (offline neural machine translation) — no API keys, no rate limits, no internet required after initial package download.

- 24 source languages → English (fr, de, es, it, nl, pt, pl, ru, sv, da, nb, fi, cs, el, hu, ro, bg, sk, sl, et, lt, lv, uk, tr, sq, ca, gl, eu, ga)
- Packages auto-installed on first run (~10-50MB each, cached in `~/.local/share/argos-translate/packages/`)
- Thread-safe: `langdetect` serialized with lock, translation parallel with 64 workers
- **All errors fail loudly** — no silent fallbacks; any translation failure crashes the pipeline

## Deprecated Scripts

| Script | Status | Why |
|--------|--------|-----|
| `scripts/normalize/normalize.py` | **DEPRECATED** | Old batch-mode normalizer — processes all places at once, not per-place. Uses same argos-translate but lacks unified pipeline flow. |
| `scripts/upload/upload.py` | **DEPRECATED** | Old batch-mode uploader — replaced by pipeline's R2 + Supabase stages. |

**Always use `scripts/pipeline/pipeline.py` for ETL operations.**

## Data Flow

### Phase 0: Setup
- Load checkpoint
- Initialize logging (console + file)

### Phase 1: Extract (Scrape)
For each grid point not in checkpoint:
1. API call → list of raw places
2. For each new place, write to `places.jsonl` (append-only, dedup by ID later)

### Phase 2: Transform (Normalize + Translate)
Load all unique places from `places.jsonl`:
1. Collect all strings needing translation
2. Batch translate with 64 threads
3. Normalize each place (flatten, clean, translate text)

### Phase 3: Load Images (Download + Upload)
For each place with photos:
1. Download photos to `scripts/data/images/places/{place_id}/`
2. Upload to R2, get public URLs

### Phase 4: Load DB (Supabase)
1. Insert lookup tables (PlaceType, Service, Activity, VehicleType)
2. Insert places with R2 image URLs
3. Insert reviews

## Error Handling
- Each stage logs errors but continues processing other items
- Checkpoint saves after each successful stage completion
- If a place fails at any stage, it's retried on next run
