# Pipeline Design V2 — Improvement Plan

> **Date**: 2026-05-28
> **Status**: Plan only — NO implementation yet
> **Prerequisites**: Read REVIEW_FINDINGS_V2.md first

---

## What's Already Working (Do Not Change)

| Feature | Status | Why It Works |
|---------|--------|--------------|
| Disk cache idempotency | ✅ | 7 independent caches, file-existence checks |
| `--limit N` then `--limit N` | ✅ | All caches hit → instant completion, no duplicates |
| `--no-cache` API fetch | ✅ | Skips cache read, fetches fresh, writes cache |
| `--no-cache` translation | ✅ | Empty cache, doesn't save |
| `--no-cache` images | ✅ | Re-downloads, overwrites .webp |
| `--no-cache` R2 upload | ✅ | Skips head_object, force re-upload |
| `--no-cache` DB insert | ✅ | ON CONFLICT DO UPDATE |
| Worker pools (R2: 32, DB: 8) | ✅ | 5-10x speedup, backpressure queues |
| ProcessPoolExecutor (spawn) | ✅ | argos-translate is not fork-safe |
| Rich logging + progress bars | ✅ | Console + file output |
| Translation cache (file lock + merge) | ✅ | 16 concurrent writers, no data loss |

---

## Issues To Fix

### Issue 1: Stale `isort` config (Low Priority)

**File**: `pyproject.toml`

The `isort` config references 3 deleted modules:
- `checkpoint` — replaced by disk cache
- `r2_uploader` — replaced by `r2_worker`
- `supabase_uploader` — replaced by `db_worker`

**Fix**: Update `known-first-party` list to match actual modules.

### Issue 2: Missing `.env` and `r2-config.json` templates (Medium Priority)

**Problem**: The pipeline needs `.env` (with `DATABASE_URL`) and `scripts/upload/r2-config.json` to connect to Supabase and R2. Neither file exists in the repo. Without them, the pipeline runs but silently skips R2 upload and DB insert.

**Fix**: Add `.env.example` and `r2-config.json.example` template files to the repo with instructions.

### Issue 3: No separate stage modes (Medium Priority)

**Problem**: The pipeline is all-or-nothing. You can't run just the scraper, just the normalizer, or just the uploader.

**User's exact words**: "running the scraper for 10 places", "running the normaliser for 10 places", "running the uploader for 10 places"

**Current behavior**: `pipeline.py --limit 10` runs ALL stages (scrape → normalize → upload).

**Requested behavior**:
```bash
# Just scrape (download places + images to local disk)
uv run python pipeline.py --stage scrape --limit 10

# Just normalize (translate + normalize already-scraped data)
uv run python pipeline.py --stage normalize --limit 10

# Just upload (upload already-normalized data to R2 + Supabase)
uv run python pipeline.py --stage upload --limit 10

# All stages (default)
uv run python pipeline.py --limit 10
```

**Why this matters**:
- Test scraping without needing R2/DB credentials
- Re-normalize data after fixing the normalizer (without re-scraping)
- Re-upload to R2/DB without re-scraping

**Design**:
- Each stage reads/writes intermediate data from disk
- Scrape stage: writes raw place data + images to `data/cache/` and `data/images/`
- Normalize stage: reads from `data/cache/` and `data/images/`, writes to `data/cache/normalized/`
- Upload stage: reads from `data/cache/normalized/` and `data/images/`, uploads to R2 + Supabase
- `--limit N` applies to each stage independently (first N places by ID)

---

## Design Decisions

### Why disk cache, not checkpointing

**User's exact words**: "I don't really like the idea of checkpointing. I prefer that you put a cache on each long-running function using a disk cache."

**Rationale**:
1. **Simplicity**: File existence check (`os.path.exists()`) vs. complex state machine with 5+ data structures
2. **Reliability**: No central authority to get out of sync with reality
3. **Debuggability**: `ls data/cache/` shows exactly what's cached — no need to parse JSON checkpoint files
4. **Crash resilience**: If the pipeline crashes mid-place, the next run processes what's missing. No checkpoint to reset.

**How it works**:
```
API response cached? → Yes: return cached. No: fetch → cache → return.
Image .webp exists?  → Yes: skip download.  No: download → convert → save.
Translation cached?  → Yes: return cached.  No: translate → cache → return.
Normalized cached?   → Yes: return cached.  No: normalize → cache → return.
R2 object exists?    → Yes: skip upload.    No: head_object → upload.
DB record exists?    → Yes: ON CONFLICT UPDATE. No: INSERT.
```

### Why worker pools are KEPT

**User's exact words**: "you talk about removing queue/threadpool for uploads - that is a stupid idea, read the comments and notes. They were added because this script was very slow."

**Rationale**:
- **R2 uploads**: Each image is a network round-trip (50-200ms). 32 parallel threads = 5-8x throughput.
- **DB inserts**: Each place involves 5+ SQL round-trips (upsert lookups + insert place + junctions + reviews). 8 parallel connections = 4-8x throughput.
- **Backpressure**: Queues block when full, preventing the pipeline from overwhelming R2 or Supabase.

**Benchmarks** (from PIPELINE_DESIGN.md):
- Sequential R2 uploads: 20-400 seconds for 100 places
- Parallel R2 uploads (32 threads): 12-62 seconds
- Sequential DB inserts: ~100 seconds for 100 places
- Parallel DB inserts (8 threads): ~25 seconds

### Why ProcessPoolExecutor with spawn

- **argos-translate** uses C extensions that are NOT fork-safe
- `fork()` inherits parent's memory including locked mutexes → deadlocks
- `spawn` starts fresh Python interpreters → no inherited state
- Each worker preloads translation models once at startup

### Why functional programming + generators

- **`place_source()` generator**: Yields places one at a time from the API. Memory-efficient — doesn't load all places into RAM.
- **Pure stage functions**: `extract_place_data()`, `normalize_place()`, `normalize_review()` have no side effects. Easy to test, easy to reason about.
- **Pipeline as data flow**: Each place flows through stages like a pipe: `extract → download → reviews → translate → normalize → R2 → DB`

---

## File Structure (After Changes)

```
scripts/pipeline/
├── PIPELINE_DESIGN.md      # Original design (kept for reference)
├── PIPELINE_DESIGN_V2.md   # This file — improvement plan
├── REVIEW_FINDINGS_V2.md   # Review findings
├── pipeline.py             # Unified entry point (modified to add --stage flag)
├── config.py               # Configuration
├── cache.py                # Disk cache primitives
├── api_client.py           # Park4Night API client
├── image_downloader.py     # Image downloader
├── translator.py           # Argos-translate wrapper
├── normalizer.py           # Pure normalization functions
├── r2_worker.py            # R2 upload worker pool
├── db_worker.py            # DB insert worker pool
├── logging_setup.py        # Rich console + file logging
├── cleanup_r2.py           # One-time utility
├── pyproject.toml          # Dependencies (fixed isort config)
├── .env.example            # NEW: Template for .env
└── r2-config.json.example  # NEW: Template for R2 config
```

---

## Implementation Plan (Ordered, Small Steps)

### Step 1: Fix `isort` config in `pyproject.toml`
- Remove deleted modules from `known-first-party`
- Add `r2_worker` and `db_worker`
- **Test**: `uv run ruff check` passes

### Step 2: Add `.env.example` and `r2-config.json.example`
- Template files with placeholder values
- Instructions in comments
- **Test**: Files exist and are valid JSON/env format

### Step 3: Add `--stage` flag to `pipeline.py`
- `--stage scrape`: Run extract + download only
- `--stage normalize`: Run translate + normalize only (reads from cache)
- `--stage upload`: Run R2 upload + DB insert only (reads from normalized cache)
- Default (no `--stage`): Run all stages (current behavior)
- **Test**: Each stage works independently with `--limit 10`

### Step 4: Add verification step
- After upload, verify place count in Supabase
- After R2 upload, verify image count
- Report mismatches
- **Test**: Verification passes for 10 places

### Step 5: Test end-to-end
- Run scraper for 10 places → verify 10 places downloaded
- Run normalizer for 10 places → verify 10 normalized + reviews + lookup tables
- Run uploader for 10 places → verify data in Supabase + images in R2
- Re-run each → verify no duplicate work
- **STOP for user review**

---

## What NOT To Do

1. **DO NOT remove worker pools** — they exist for performance (5-10x speedup)
2. **DO NOT use checkpointing** — disk cache is simpler and more reliable
3. **DO NOT use `pip`** — use `uv add` and `uv run` exclusively
4. **DO NOT delete data files** — the pipeline is append-only with cache-based skip logic
5. **DO NOT implement without documentation** — write WHY in comments and markdown files
6. **DO NOT run tests with more than 10 places** until user reviews

---

## Documentation Policy

Every change must include:
1. **Inline comments** explaining WHY (not WHAT) — especially for non-obvious decisions
2. **Markdown files** for architectural decisions (like this one)
3. **Docstrings** for all public functions
4. **Examples** in docstrings showing usage

**Why**: Previous agents implemented → unimplemented → reimplemented the same features because the reasoning wasn't documented. This policy prevents that.
