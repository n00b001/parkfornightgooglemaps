# AGENTS.md — Instructions for AI Coding Agents

## Mandatory Workflow

**Every code change MUST follow this workflow without being asked:**

1. **Make the change** — implement the feature, fix, or refactor
2. **Run CI locally** — `npm run lint`, `npm test`, `npm run build` — all must pass (0 errors; pre-existing warnings are acceptable)
3. **Create a feature branch** — `git checkout -b feature/<short-description>`
4. **Commit** — use conventional commit format (`feat:`, `fix:`, `chore:`, etc.)
5. **Push** — `git push -u origin <branch>`
6. **Create a PR** — `gh pr create` with a clear title and body describing changes, fallback behavior, and CI status
7. **Verify CI passes in the PR** — check that GitHub Actions green-light the PR

## Git Signing

The repo has `commit.gpgsign = true` configured globally using 1Password SSH signer (`hades-ubuntu-key`). If the key is unavailable:

```bash
git commit --no-gpg-sign -m "message"
```

## PR Body Template

```
## Summary
[What changed and why]

## Changes
- [bullet points of modifications]

## Fallback / Edge Cases
[What happens when things go wrong]

## CI
- Lint: [status]
- Tests: [status]
- Build: [status]
```

## Project Commands

| Command | Description |
|---------|-------------|
| `npm run lint` | Lint server + client |
| `npm test` | Run server tests (Jest) |
| `npm run build` | Build server (Prisma) + client (Vite) |
| `npm run dev` | Start both servers |

## Branch Naming

- `feature/<description>` — new features
- `fix/<description>` — bug fixes
- `chore/<description>` — maintenance, deps, config

## Budget Constraint

**NO PAID SERVICES.** Every data store, CDN, and infrastructure component must use a free tier.

| Service | Free Tier | Usage |
|---------|-----------|-------|
| Firebase Firestore | 1GB storage, 50K reads/day | Place metadata + image base64 (thumbnails) |
| Render PostgreSQL | 1GB storage | Structured data: places, reviews, services, descriptions |
| Firebase Storage | 5GB storage | Image files (WebP compressed) — ~$0.03/mo at current size, monitor closely |

**Image compression**: Always convert JPEG → WebP before upload. Typical 50-75% size reduction.

## Critical Project Rules

### NO Park4Night CDN / External Resources
This project is designed to **supercede** Park4Night. The original Park4Night CDN, API endpoints, and all external resources will be turned off at some point.

- **NEVER** use Park4Night CDN URLs (`cdn*.park4night.com`) as fallbacks
- **NEVER** implement fallback logic that reaches back to Park4Night
- **ALL images must come from local paths only** (`/images/places/...`, `/images/icons/...`)
- If a local image does not exist, the app is broken — this is a **fatal error**, not a graceful degradation scenario
- The scraper downloads all needed assets; if they're missing, something went wrong with the scrape

### Image Policy
- Place photos: `scripts/data/images/places/{place_id}/{photo_id}_thumb.jpg` and `{photo_id}_large.jpg`
- Vehicle icons: `scripts/data/images/icons/vehicule_*.png`
- Served via Express static at `/images/` on the API server
- Client constructs URLs as `${API_URL}/<relative-path>` — no CDN fallback, no default avatars, no `onError` handlers pointing elsewhere
- If images directory is missing, the server must **fail to start** (not log a warning and continue)

## DATA SAFETY — ABSOLUTE RULES

### NEVER DELETE DATA FILES. EVER.
- **NEVER** run `rm`, `truncate`, or any command that deletes/empties data files in `scripts/data/`
- **NEVER** run `scraper.py reset` — it resets the checkpoint (which is fine) but was historically dangerous
- **NEVER** clear, wipe, or reset accumulated scraped data (`places.jsonl`, `reviews.jsonl`, images)
- The entire pipeline is designed around **append-only JSONL with checkpoint-based resume** — each run picks up where the last left off
- If you need to re-process data (e.g., normalise again), just re-run the script — it skips already-processed items via checkpoints
- Data files (`places.jsonl`, `reviews.jsonl`, `images/`) are **accumulated over days of scraping** — deleting them destroys irreplaceable work
- If you accidentally delete data, restore from the export files (`places_export.json`, `reviews_export.json`) which are kept as backups
- **This rule overrides everything else.** No feature, refactor, or "clean start" justifies deleting data.

### Pipeline Design — Skip What Exists
- **Scraper**: Uses `checkpoint.json` to skip already-scraped grid points. Appends new places/reviews to JSONL files.
- **Normaliser**: Uses `normalize_checkpoint.json` to skip already-normalised place IDs. Reads from `places.jsonl`, writes to `normalized/`.
- **Uploader**: Skips images that already exist on disk (`_download_file` checks `save_path.exists()`). Database uses upserts — existing records are skipped.
- **Images**: Downloaded during normal scrape (`scrape_places_worker` calls `normalize_place(place, downloader)` which downloads photos inline)

### Running the Pipeline
```bash
# Full pipeline (safe to run multiple times — skips already-processed data):
cd scripts/scraper && uv run scraper.py scrape          # places + reviews + images
cd scripts/normalize && uv run normalize.py              # translate & clean
cd scripts/upload && uv run upload.py                    # R2 images + Supabase DB

# With limits (for testing):
uv run scraper.py scrape --limit 100
uv run normalize.py --limit 100
uv run upload.py --places 100
```

### PR Merge Rule — NEVER merge broken code
- **NEVER merge a PR that breaks the app.** If the feature requires data (scraped places, reviews, images) to function, that data MUST exist before merging.
- Code that introduces new functionality requiring local assets (images, data files) is incomplete until those assets are actually downloaded and committed.
- Always verify the app works end-to-end with the actual data before considering a PR ready.
