# Single-Responsibility Audit Report

## Desired Flow (6 clean stages)

1. **Extract** — structure raw API data + download images
2. **Translate** — translate text to English (retain original)
3. **Enqueue R2** — start image uploads, pipeline moves on
4. **Normalize** — structured data into clean tables, NO translation inside
5. **Build DB payload** — use R2 URLs from step 3, insert into DB payload
6. **Enqueue DB** — upload database payload to database

## Current Violations

### pipeline.py: `stage_extract` — does 4 things
- Structures raw API data into normalized format
- Downloads images via `ImageDownloader`
- Writes to JSONL file (persistence — not a stage concern)
- Marks checkpoint (checkpoint management — not a stage concern)

### pipeline.py: `stage_translate` — broken contract
- Translates strings but doesn't apply them to the place dict
- Results sit in a cache; normalizer pulls from cache later (hidden dependency)
- Should apply translations directly to place dict

### pipeline.py: `stage_normalize` — translation duplication
- Calls `normalize_place()` which calls `translate_text()` INSIDE `pick_or_translate()` and pricing normalization
- Translation happens TWICE: once in stage_translate, again inside normalizer
- Also marks checkpoint (not its job)

### pipeline.py: `stage_enqueue_db` — normalizes reviews inside enqueue
- Calls `normalize_review()` — normalization belongs in normalize stage
- Enqueues to DB — its actual job
- Marks checkpoint — not its job

### pipeline.py: `run_pipeline` — multiple issues
- Calls `stage_insert_db` which no longer exists (renamed to `stage_enqueue_db`)
- Holds `db_conn` that's no longer needed (DB is queue-based)
- Doesn't fetch reviews at all — reviews are missing from the pipeline
- Doesn't wait for R2 completion before proceeding

### normalizer.py: `normalize_place` / `normalize_review` — embedded translation
- Calls `translate_text()` directly inside normalization
- Translation should be a separate upstream stage
- Normalizer should receive pre-translated data

### r2_worker.py: `_process_task` — uploads AND updates DB
- Uploads images to R2 — its job
- Calls `_update_place_photos_in_db()` — DB concern, not R2 concern
- Should only upload and return URLs via photos dict

### db_worker.py: `_process_task` — inserts places, reviews, AND lookup tables
- Too many responsibilities in one worker
- Should be split: lookup upserts, place inserts, review inserts

## Fix Plan

1. Split `stage_extract` → `extract_place_data` + `download_images` (separate stages)
2. Remove JSONL persistence from pipeline (not a pipeline concern)
3. Remove checkpoint marking from all stage functions
4. Fix `stage_translate` to apply translations directly to place dict
5. Remove `translate_text()` calls from `normalizer.py` — receive pre-translated data
6. Remove review normalization from `stage_enqueue_db` — normalize reviews upstream
7. Add review fetching as explicit stage between extract and translate
8. Add review normalization to normalize stage
9. Remove DB update from `r2_worker.py` — only upload, return URLs via photos dict
10. Pipeline waits for R2 done-event, then builds DB payload with R2 URLs, then enqueues DB
11. Remove `db_conn` from `run_pipeline` — DB is fully queue-based
12. Fix `run_pipeline` to call `stage_enqueue_db` instead of `stage_insert_db`
