# AGENTS.md — Instructions for AI Coding Agents

## What This Project Is

**This is a Progressive Web App (PWA) deployed to Render that shows camping and parking spaces on Google Maps.** Users browse places, read reviews, see photos, filter by services/activities, favourite places, and write their own reviews — all with Google login.

The Python scripts in `scripts/` are **just data collection** — they scrape, translate, and upload place data to the database. They are a means to an end, not the product itself.

**The product is the web app.** Every decision should serve the end user experience: fast loading, clear information, easy navigation, mobile-first design.

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

## Python Tooling — ALWAYS USE `uv`, NEVER `pip`

This project uses **uv** (astral-sh/uv) as the sole Python package manager and runner. **pip is forbidden.**

| Operation | Correct | Forbidden |
|-----------|---------|-----------|
| Add a dependency | `uv add <package>` | `pip install <package>` |
| Run a script | `uv run script.py` | `python script.py` |
| Run with args | `uv run script.py --arg value` | `python script.py --arg value` |
| Add dev dependency | `uv add --dev <package>` | `pip install <package>` |
| Sync environment | `uv sync` | `pip install -r requirements.txt` |
| Remove dependency | `uv remove <package>` | `pip uninstall <package>` |

**Rules:**
- **NEVER** use `pip install`, `pip uninstall`, `pip freeze`, or any `pip` command
- **NEVER** create or modify `requirements.txt` — dependencies are managed by `pyproject.toml` + `uv.lock`
- **ALWAYS** use `uv add <package>` to install a new dependency (updates `pyproject.toml` and `uv.lock` automatically)
- **ALWAYS** use `uv run <script>` to execute Python scripts (uses the managed virtual environment)
- Each sub-project (`scripts/scraper/`, `scripts/normalize/`, `scripts/upload/`) has its own `pyproject.toml` — run `uv` commands **inside that directory**
- Before using a new Python library, **read its documentation first** (via web search or `ctx_fetch_and_index`) to understand the API

### Why
- `uv` is 10-100x faster than pip
- `uv` manages virtual environments automatically — no manual `venv` activation needed
- `uv.lock` ensures reproducible builds across machines
- `pyproject.toml` is the single source of truth for dependencies

## Pipeline Caching — DECORATOR-ONLY RULE

The pipeline (`scripts/pipeline/`) uses `diskcache` library for persistent disk caching.

**ABSOLUTE RULE: NEVER call `disk_cache.get()`, `disk_cache.set()`, or `disk_cache[key]` directly.**

All caching MUST use `@disk_cache.memoize()` function decorators. Custom cache management code means untested code which means bugs.

### Correct Pattern
```python
from cache_config import disk_cache

@disk_cache.memoize()
def fetch_places(latitude: float, longitude: float) -> list[dict]:
    """Fetch places from API. Automatically cached by decorator."""
    return api_client.get_places(latitude, longitude)
```

### Wrong Pattern (NEVER DO THIS)
```python
# ❌ WRONG — manual cache management
result = disk_cache.get(key)
if result is None:
    result = do_expensive_thing()
    disk_cache.set(key, result)
```

### Key Rules
1. **Decorator-only**: All cached operations must be functions decorated with `@disk_cache.memoize()`
2. **`frozendict` for dict args**: Stage functions taking dicts must receive `frozendict`-wrapped arguments to satisfy decorator hashing requirements
3. **`--no-disk-cache` bypass**: Uses `func.__wrapped__(*args)` to skip the decorator entirely — never deletes cache
4. **No manual cache code**: Zero manual get/set anywhere in the codebase
5. **Shared instance**: Import `disk_cache` from `cache_config` — never instantiate your own

### Why
- `diskcache` decorators are battle-tested and handle edge cases (hash collisions, cache eviction, type serialization)
- Custom cache code is untested and introduces bugs
- Decorator pattern makes caching explicit and auditable at function definition time

### Example
```bash
# Add a new dependency to the scraper:
cd scripts/scraper && uv add httpx

# Run the scraper:
cd scripts/scraper && uv run scraper.py scrape

# Add a dev-only tool:
cd scripts/scraper && uv add --dev ruff
```

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
cd scripts/pipeline && uv run python pipeline.py

# With limits (for testing):
cd scripts/pipeline && uv run python pipeline.py --limit 100

# Dry run (preview without changes):
cd scripts/pipeline && uv run python pipeline.py --dry-run
```

### Pipeline Architecture — IMPORTANT
- **The unified pipeline** (`scripts/pipeline/pipeline.py`) is the **only active ETL script**. The old `scripts/normalize/normalize.py` and `scripts/upload/upload.py` are **DEPRECATED** — do not modify them.
- Uses `ProcessPoolExecutor` with **spawn** (not fork) to avoid inheriting argos-translate locks.
- Each worker process starts fresh — no shared state with the main process.
- **Translation packages** (argostranslate) are installed **once in the main process** (`ensure_packages_installed()`) before workers spawn. Workers only preload models (`preload_models()`) — they do NOT re-check for packages.
- **Stanza MWT warnings** (e.g. `Language et package default expects mwt, which has been added`) are **expected and harmless** — they come from stanza (a dependency of argostranslate) when it auto-adds the MWT processor for certain languages. Do NOT suppress these warnings — they are diagnostic. If they become a problem, it must be fixed upstream in argostranslate, not silenced.

### PR Merge Rule — NEVER merge broken code
- **NEVER merge a PR that breaks the app.** If the feature requires data (scraped places, reviews, images) to function, that data MUST exist before merging.
- Code that introduces new functionality requiring local assets (images, data files) is incomplete until those assets are actually downloaded and committed.
- Always verify the app works end-to-end with the actual data before considering a PR ready.
