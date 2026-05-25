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

# ── Geographic Grid ────────────────────────────────────────────────
# Europe bounding box (covers UK, Ireland, France, Spain, Portugal,
# Italy, Germany, Netherlands, Belgium, Scandinavia, etc.)
GRID = {
    "lat_min": 35.0,  # Southern Spain/Portugal
    "lat_max": 71.0,  # Northern Norway
    "lng_min": -25.0,  # Azores / Western Ireland
    "lng_max": 40.0,  # Eastern Europe
    "step": 2.0,  # degrees between query points (~222km)
    "radius": 200,  # km radius per query
}

# ── Output Configuration ───────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PLACES_FILE = os.path.join(DATA_DIR, "places.jsonl")
REVIEWS_FILE = os.path.join(DATA_DIR, "reviews.jsonl")
CHECKPOINT_FILE = os.path.join(DATA_DIR, "checkpoint.json")
LOG_FILE = os.path.join(DATA_DIR, "scraper.log")

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
