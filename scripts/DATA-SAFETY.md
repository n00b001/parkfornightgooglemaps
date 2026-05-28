# DATA SAFETY — READ BEFORE RUNNING ANY SCRIPT

## ABSOLUTE RULE: NEVER DELETE DATA

The data in `scripts/data/` is accumulated over days of scraping. **It is never deleted.**

## Which Script to Use

| Script | Status | Use For |
|--------|--------|---------|
| **`scripts/pipeline/pipeline.py`** | ✅ **ACTIVE** | All ETL operations — unified per-place pipeline |
| `scripts/normalize/normalize.py` | ❌ **DEPRECATED** | Do not use — old batch-mode normalizer |
| `scripts/upload/upload.py` | ❌ **DEPRECATED** | Do not use — old batch-mode uploader |

**Always use `scripts/pipeline/pipeline.py`.** The deprecated scripts exist only for historical reference.

### What the pipeline does (per-place, end-to-end)

| Stage | Reads | Writes | Skips Already-Processed? |
|-------|-------|--------|--------------------------|
| Extract | Park4Night API | `places.jsonl` (append) | ✅ Yes — checkpoint tracks grid points + place stages |
| Translate | Place descriptions | In-memory cache | ✅ Yes — translation cache in RAM |
| Normalize | Extracted place | Final normalized record | ✅ Yes — checkpoint tracks stages |
| Upload R2 | Local images | Cloudflare R2 | ✅ Yes — checks existing uploads |
| Insert DB | Normalized place + reviews | Supabase PostgreSQL | ✅ Yes — DB upserts + checkpoint |

### Commands that are SAFE to run
- `cd scripts/pipeline && uv run python pipeline.py` — full pipeline run
- `cd scripts/pipeline && uv run python pipeline.py --limit 100` — limited to 100 places
- `cd scripts/pipeline && uv run python pipeline.py --dry-run` — preview without changes

### Pipeline Architecture (for agents)
- Uses `ProcessPoolExecutor` with **spawn** (not fork) to avoid inheriting argos-translate locks.
- Each worker starts fresh — no shared state with the main process.
- **Translation packages** are installed **once in the main process** before workers spawn. Workers only preload models.
- **Stanza MWT warnings** (e.g. `Language et package default expects mwt`) are **expected and harmless** — do NOT suppress them.

### Commands that are DANGEROUS (NEVER run without explicit user approval)
| Command | Why | Safe Alternative |
|---------|-----|----------------|
| `scraper.py reset` | Resets checkpoint (OK) but historically deleted JSONL files | Just re-run `scrape` — it resumes automatically |
| `rm scripts/data/places.jsonl` | Deletes all scraped places | Don't do this |
| `rm -rf scripts/data/images/` | Deletes all downloaded images | Don't do this |
| `truncate` on any data file | Destroys accumulated data | Don't do this |

### If you need to re-process everything
Just re-run the pipeline. The checkpoint system handles it:
- Pipeline: skips grid points already done + place stages already completed
- Translation: in-memory cache deduplicates strings across places
- R2: skips images that already exist
- DB: uses upserts — existing records updated, new records inserted

### Data file locations

| File | Purpose | Format |
|------|---------|--------|
| `data/places.jsonl` | Raw scraped places (append-only) | JSON Lines |
| `data/reviews.jsonl` | Raw scraped reviews (append-only) | JSON Lines |
| `data/checkpoint.json` | Scraper progress tracking | JSON |
| `data/images/places/{id}/` | Downloaded photos (thumb + large) | JPEG files |
| `data/images/icons/` | Vehicle type icons | PNG files |
| `data/places_export.json` | Backup of all places (from export command) | JSON array |
| `data/reviews_export.json` | Backup of all reviews (from export command) | JSON array |
| `data/normalized/places.jsonl` | Cleaned & translated places | JSON Lines |
| `data/normalized/reviews.jsonl` | Cleaned & translated reviews | JSON Lines |
| `data/normalized/normalize_checkpoint.json` | Normaliser progress | JSON |

### Recovery
If data files are accidentally deleted, restore from export backups:
```bash
# Convert places_export.json back to places.jsonl
python3 -c "import json; places = json.load(open('data/places_export.json')); \
  open('data/places.jsonl', 'w').write('\n'.join(json.dumps(p) for p in places))"

# Convert reviews_export.json back to reviews.jsonl
python3 -c "import json; reviews = json.load(open('data/reviews_export.json')); \
  open('data/reviews.jsonl', 'w').write('\n'.join(json.dumps(r) for r in reviews))"
```
