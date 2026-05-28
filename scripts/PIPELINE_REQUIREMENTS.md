# Pipeline Script Requirements

## Core Goals
A single unified pipeline script that processes Park4Night data end-to-end:
scrape → normalize → download images → convert to WebP → upload to Cloudflare R2 → upload to Supabase

## Technical Requirements

### Logging & Progress
- Rich library for colored output and progress bars with ETAs
- All progress bars and logs must also be written to file
- Each step (extract, transform, load) clearly logged with progress bars

### Execution
- Use `uv` for package management (not raw python, not pip)
- Multithreading: 32 threads, 64GB RAM, 10Gbps internet available
- `--limit` flag to limit number of places processed (for testing)

### Resilience
- Save progress between runs — skip already processed items
- Cache work to disk (no duplicate work)
- Checkpoint-based resume

### Architecture
- Functional programming with Python generators
- Each place processed through the full pipeline:
  1. Download place data
  2. Normalize into clean database structure (no duplication)
  3. Translate text to English
  4. Download images for this place
  5. Convert images to WebP
  6. Upload images to Cloudflare R2
  7. Insert image URLs into DB data
  8. Upload DB data to Supabase

### Testing
- Test with small numbers (10 places max)
- Do not test higher numbers until reviewed
- Stop at test point for review

### Research
- Use online search to understand best approaches for different problems
- Evidence-based decisions

## Image Policy
- **ALL images must be WebP format** — no JPEG, no PNG in R2 bucket
- Convert on-the-fly during upload
- R2 bucket keys always end in `.webp`
- Delete any non-WebP files already in the bucket
