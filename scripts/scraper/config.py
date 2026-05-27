"""
Park4Night Scraper Configuration

Defines the geographic grid to scrape, API endpoints, rate limits,
and output settings.
"""

import os

# ── API Configuration ──────────────────────────────────────────────
GUEST_API_BASE = "https://guest.park4night.com/services/V4.1"
PLACES_ENDPOINT = f"{GUEST_API_BASE}/lieuxGetFilter.php"
REVIEWS_ENDPOINT = f"{GUEST_API_BASE}/commGet.php"

# New API endpoints (for cross-referencing)
NEW_API_BASE = "https://park4night.com/api"
NEW_PLACES_ENDPOINT = f"{NEW_API_BASE}/places/around"
NEW_PLACE_DETAIL = f"{NEW_API_BASE}/places/{{id}}"
NEW_PLACE_REVIEWS = f"{NEW_API_BASE}/places/{{id}}/reviews"

# ── Rate Limiting ──────────────────────────────────────────────────
REQUEST_DELAY = 0.3  # seconds between requests (politeness)
REQUEST_TIMEOUT = 30  # seconds per request
MAX_RETRIES = 3  # retries on failure
RETRY_DELAY = 2  # seconds between retries

# ── Geographic Grid (Global) ───────────────────────────────────────
# Regional grids with appropriate step sizes for landmass coverage.
# Each region: lat_min, lat_max, lng_min, lng_max, step (degrees)
# Step ~2.0° ≈ 222km; 200km radius per query ensures overlap.
REGIONS = [
    # Europe (existing - already scraped, will be skipped by checkpoint)
    {
        "name": "Europe",
        "lat_min": 35.0,
        "lat_max": 71.0,
        "lng_min": -25.0,
        "lng_max": 40.0,
        "step": 2.0,
    },
    # North America (Canada, USA, Mexico)
    {
        "name": "North America",
        "lat_min": 25.0,
        "lat_max": 72.0,
        "lng_min": -170.0,
        "lng_max": -50.0,
        "step": 3.0,  # Larger area, coarser step
    },
    # South America
    {
        "name": "South America",
        "lat_min": 10.0,
        "lat_max": -56.0,
        "lng_min": -82.0,
        "lng_max": -34.0,
        "step": 3.0,
    },
    # Africa
    {
        "name": "Africa",
        "lat_min": 38.0,
        "lat_max": -35.0,
        "lng_min": -20.0,
        "lng_max": 52.0,
        "step": 3.0,
    },
    # Middle East / Central Asia
    {
        "name": "Middle East",
        "lat_min": 12.0,
        "lat_max": 42.0,
        "lng_min": 35.0,
        "lng_max": 75.0,
        "step": 3.0,
    },
    # East Asia (Japan, Korea, China coastal)
    {
        "name": "East Asia",
        "lat_min": 20.0,
        "lat_max": 50.0,
        "lng_min": 110.0,
        "lng_max": 150.0,
        "step": 3.0,
    },
    # Southeast Asia
    {
        "name": "Southeast Asia",
        "lat_min": 15.0,
        "lat_max": -12.0,
        "lng_min": 95.0,
        "lng_max": 140.0,
        "step": 3.0,
    },
    # Oceania (Australia, NZ)
    {
        "name": "Oceania",
        "lat_min": -45.0,
        "lat_max": -10.0,
        "lng_min": 135.0,
        "lng_max": 180.0,
        "step": 3.0,
    },
]

# Legacy single-grid config (for backward compatibility)
GRID = REGIONS[0]  # Europe as default
GRID["radius"] = 200

# ── Output Configuration ───────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PLACES_FILE = os.path.join(DATA_DIR, "places.jsonl")
REVIEWS_FILE = os.path.join(DATA_DIR, "reviews.jsonl")
CHECKPOINT_FILE = os.path.join(DATA_DIR, "checkpoint.json")
LOG_FILE = os.path.join(DATA_DIR, "scraper.log")

# ── Image Download Configuration ───────────────────────────────────
IMAGES_DIR = os.path.join(DATA_DIR, "images")
PLACE_IMAGES_DIR = os.path.join(IMAGES_DIR, "places")
ICON_IMAGES_DIR = os.path.join(IMAGES_DIR, "icons")
IMAGE_REQUEST_DELAY = 0.1  # seconds between image downloads per worker
IMAGE_REQUEST_TIMEOUT = 30  # seconds per image download
IMAGE_MAX_RETRIES = 3  # retries on failure
IMAGE_RETRY_DELAY = 2  # seconds between retries
IMAGE_WORKERS = 32  # parallel image download workers
IMAGE_MIN_SIZE = 1024  # minimum file size in bytes (skip tiny/broken images)

# ── Multiprocessing ────────────────────────────────────────────────
WORKERS = 4  # number of parallel workers
BATCH_SIZE = 50  # places per batch for review fetching

# ── Service/Amenity Codes ──────────────────────────────────────────
SERVICE_CODES = {
    "animaux": "Pets allowed",
    "point_eau": "Fresh water point",
    "eau_noire": "Black water disposal",
    "eau_usee": "Grey water disposal",
    "wc_public": "Public toilets",
    "poubelle": "Trash bins",
    "douche": "Showers",
    "boulangerie": "Bakery nearby",
    "electricite": "Electricity",
    "wifi": "WiFi",
    "piscine": "Swimming pool",
    "laverie": "Laundry",
    "gaz": "Gas",
    "gpl": "LPG",
    "donnees_mobile": "Mobile data",
    "lavage": "Vehicle wash",
}

ACTIVITY_CODES = {
    "visites": "Sightseeing",
    "windsurf": "Windsurfing",
    "vtt": "Mountain biking",
    "rando": "Hiking",
    "escalade": "Climbing",
    "eaux_vives": "White water",
    "peche": "Fishing (boat)",
    "peche_pied": "Fishing (shore)",
    "moto": "Motorcycle",
    "point_de_vue": "Viewpoint",
    "baignade": "Swimming",
    "jeux_enfants": "Children's playground",
}

# Place type codes
PLACE_TYPE_CODES = {
    "PN": "Surrounded by nature",
    "C": "Camping",
    "CAR": "Caravan park",
    "H": "Hotel",
    "HP": "Holiday park",
    "A": "Aire de service",
    "PJ": "Parking",
    "CS": "Campsite",
    "CL": "Clearing",
    "AL": "Aire de camping-car",
    "P": "Parking area",
    "S": "Service area",
    "EC": "Eco-camping",
    "FM": "Farm stay",
    "G": "Gite",
    "M": "Motel",
    "R": "Rural tourism",
    "RH": "Rural house",
    "T": "Tourist farm",
}
