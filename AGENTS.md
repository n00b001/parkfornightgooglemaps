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

### PR Merge Rule — NEVER merge broken code
- **NEVER merge a PR that breaks the app.** If the feature requires data (scraped places, reviews, images) to function, that data MUST exist before merging.
- Code that introduces new functionality requiring local assets (images, data files) is incomplete until those assets are actually downloaded and committed.
- Always verify the app works end-to-end with the actual data before considering a PR ready.
