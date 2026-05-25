# Park4Night Scraper

Comprehensive scraping tool for Park4Night.com that extracts all place data, reviews, services, and amenities.

## Features

- **Complete data extraction**: Places, reviews, services, amenities, photos, pricing, contact details
- **Multiprocessing**: Parallel workers for fast scraping
- **Checkpoint/Resume**: Interrupt and resume without re-downloading data
- **Deduplication**: Same place scraped multiple times? Only the latest copy is kept
- **JSONL output**: Stream-friendly format for large datasets

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Run from the scraper directory
cd scripts/scraper

# Full scrape (places + reviews)
python scraper.py scrape

# Scrape places only
python scraper.py scrape-places

# Scrape reviews only
python scraper.py scrape-reviews

# Check progress
python scraper.py status

# Export to consolidated JSON
python scraper.py export

# Reset and start fresh
python scraper.py reset
```

## Output Files

All data is saved to `scripts/scraper/data/`:

| File | Format | Description |
|------|--------|-------------|
| `places.jsonl` | JSON Lines | One place per line, append-only |
| `reviews.jsonl` | JSON Lines | One review per line, append-only |
| `checkpoint.json` | JSON | Progress tracking for resume |
| `scraper.log` | Text | Detailed log of all operations |
| `places_export.json` | JSON | Consolidated places (after `export`) |
| `reviews_export.json` | JSON | Consolidated reviews (after `export`) |

## Data Schema

### Place Object

```json
{
  "id": 619478,
  "title": "(YO41 5PF) Old York Forest Caravan Park",
  "name": "Old York Forest Caravan Park",
  "description": "Campsite surrounded by nature...",
  "descriptions": {
    "fr": "...",
    "en": "...",
    "de": "...",
    "es": "",
    "it": "",
    "nl": ""
  },
  "latitude": 53.918748,
  "longitude": -0.866529,
  "type": { "code": "C", "label": "Camping" },
  "address": {
    "street": "The Street",
    "city": "Thornton",
    "zipcode": "YO41 5PF",
    "country": "United Kingdom",
    "country_iso": "gb"
  },
  "pricing": {
    "parking": "payant",
    "services": ""
  },
  "access": {
    "public": true,
    "height_limit": "",
    "parking_places": "20"
  },
  "contact": {
    "phone": "",
    "email": "",
    "website": "",
    "video": ""
  },
  "services": [
    { "code": "point_eau", "label": "Fresh water point" },
    { "code": "eau_noire", "label": "Black water disposal" }
  ],
  "activities": [
    { "code": "rando", "label": "Hiking" }
  ],
  "photos": [
    {
      "id": "1928605",
      "url_large": "https://cdn3.park4night.com/...",
      "url_thumb": "https://cdn3.park4night.com/...",
      "numero": "1"
    }
  ],
  "rating": 4.5,
  "review_count": 12,
  "photo_count": 5,
  "created_at": "2025-08-03 12:00:00",
  "scraped_at": "2026-05-25T19:00:00+00:00",
  "source": "guest_api"
}
```

### Review Object

```json
{
  "id": "5256163",
  "place_id": 619478,
  "rating": 5,
  "text": "Payed £60 for 2 nights, EHU...",
  "author": "T4Nut",
  "author_id": "4761855",
  "vehicle_type": "V",
  "created_at": "2025-08-30 12:25:09",
  "social": {
    "website": "",
    "facebook": "",
    "twitter": "",
    "instagram": "",
    "youtube": ""
  },
  "scraped_at": "2026-05-25T19:00:00+00:00"
}
```

## Configuration

Edit `config.py` to adjust:

- **GRID**: Geographic coverage area and step size
- **WORKERS**: Number of parallel workers
- **REQUEST_DELAY**: Politeness delay between requests
- **MAX_RETRIES**: Retry attempts on failure

## API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `guest.park4night.com/services/V4.1/lieuxGetFilter.php` | Place listing (up to 100 per query) |
| `guest.park4night.com/services/V4.1/commGet.php` | Place reviews |
| `park4night.com/api/places/around` | Alternative place listing (up to 200) |
| `park4night.com/api/places/{id}` | Place detail |
| `park4night.com/api/places/{id}/reviews` | Place reviews (alternative) |
