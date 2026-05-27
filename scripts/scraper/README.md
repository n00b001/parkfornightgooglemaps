# Park4Night Scraper

Scrapes all place data, reviews, and images from Park4Night.com and saves them locally.

## Installation

```bash
cd scripts/scraper
uv sync
```

## Usage

```bash
cd scripts/scraper

# Full scrape (places + reviews + images)
uv run scraper.py scrape

# Scrape places only (with images)
uv run scraper.py scrape-places

# Scrape reviews only
uv run scraper.py scrape-reviews

# Download images for already-scraped places
uv run scraper.py download-images

# Download vehicle type icons
uv run scraper.py download-icons

# Check progress
uv run scraper.py status

# Reset checkpoint (start fresh)
uv run scraper.py reset
```

## Output Files

All data is saved to `scripts/data/`:

| File | Format | Description |
|------|--------|-------------|
| `places.jsonl` | JSON Lines | One place per line, append-only |
| `reviews.jsonl` | JSON Lines | One review per line, append-only |
| `checkpoint.json` | JSON | Progress tracking for resume |
| `scraper.log` | Text | Detailed log of all operations |
| `images/places/` | Images | Downloaded place photos (thumb + large) |
| `images/icons/` | Images | Vehicle type icons |

## Pipeline

This is the **first step** in the data pipeline:

1. **Scrape** (`scripts/scraper/`) — Download raw data from Park4Night
2. **Normalise** (`scripts/normalize/`) — Clean data, translate to English, output clean tables
3. **Upload** (`scripts/upload/`) — Upload images to Cloudflare R2, data to Supabase
