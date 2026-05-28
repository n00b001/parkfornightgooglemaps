"""
Unified pipeline configuration.

All settings in one place: API endpoints, rate limits, geographic grid,
output paths, service/activity codes.
"""

import os

# ── Paths ─────────────────────────────────────────────────
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SCRIPTS_DIR, "data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
PLACE_IMAGES_DIR = os.path.join(IMAGES_DIR, "places")
ICON_IMAGES_DIR = os.path.join(IMAGES_DIR, "icons")
LOG_DIR = os.path.join(SCRIPTS_DIR, "..", "logs")

# Checkpoint
CHECKPOINT_FILE = os.path.join(DATA_DIR, "pipeline_checkpoint.json")

# ── API Configuration ─────────────────────────────
GUEST_API_BASE = "https://guest.park4night.com/services/V4.1"
PLACES_ENDPOINT = f"{GUEST_API_BASE}/lieuxGetFilter.php"
REVIEWS_ENDPOINT = f"{GUEST_API_BASE}/commGet.php"

# Rate Limiting
REQUEST_DELAY = 0.3  # seconds between requests
REQUEST_TIMEOUT = 30  # seconds per request
MAX_RETRIES = 3
RETRY_DELAY = 2

# ── Image Download ────────────────────────────────
IMAGE_REQUEST_DELAY = 0.1
IMAGE_REQUEST_TIMEOUT = 30
IMAGE_MAX_RETRIES = 3
IMAGE_RETRY_DELAY = 2
IMAGE_WORKERS = 32
IMAGE_MIN_SIZE = 1024

# ── Translation ───────────────────────────────────
TRANSLATION_WORKERS = 64
TRANSLATION_BATCH_SIZE = 500

# ── R2 Upload ─────────────────────────────────────
R2_WORKERS = 16

# ── Database ──────────────────────────────────────
DB_BATCH_SIZE = 500

# ── Geographic Grid ───────────────────────────────
REGIONS = [
    {
        "name": "Europe",
        "lat_min": 35.0,
        "lat_max": 71.0,
        "lng_min": -25.0,
        "lng_max": 40.0,
        "step": 2.0,
    },
    {
        "name": "North America",
        "lat_min": 25.0,
        "lat_max": 72.0,
        "lng_min": -170.0,
        "lng_max": -50.0,
        "step": 3.0,
    },
    {
        "name": "South America",
        "lat_min": 10.0,
        "lat_max": -56.0,
        "lng_min": -82.0,
        "lng_max": -34.0,
        "step": 3.0,
    },
    {
        "name": "Africa",
        "lat_min": 38.0,
        "lat_max": -35.0,
        "lng_min": -20.0,
        "lng_max": 52.0,
        "step": 3.0,
    },
    {
        "name": "Middle East",
        "lat_min": 12.0,
        "lat_max": 42.0,
        "lng_min": 35.0,
        "lng_max": 75.0,
        "step": 3.0,
    },
    {
        "name": "East Asia",
        "lat_min": 20.0,
        "lat_max": 50.0,
        "lng_min": 110.0,
        "lng_max": 150.0,
        "step": 3.0,
    },
    {
        "name": "Southeast Asia",
        "lat_min": 15.0,
        "lat_max": -12.0,
        "lng_min": 95.0,
        "lng_max": 140.0,
        "step": 3.0,
    },
    {
        "name": "Oceania",
        "lat_min": -45.0,
        "lat_max": -10.0,
        "lng_min": 135.0,
        "lng_max": 180.0,
        "step": 3.0,
    },
]

# ── Service/Amenity Codes ─────────────────────────
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
