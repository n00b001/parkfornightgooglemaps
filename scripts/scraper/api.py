"""
Park4Night API Client

Handles all HTTP requests to Park4Night APIs with retry logic,
rate limiting, and error handling.
"""

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    MAX_RETRIES,
    NEW_PLACE_DETAIL,
    NEW_PLACE_REVIEWS,
    NEW_PLACES_ENDPOINT,
    PLACES_ENDPOINT,
    REGIONS,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    RETRY_DELAY,
    REVIEWS_ENDPOINT,
)

logger = logging.getLogger(__name__)


class Park4NightAPI:
    """Client for Park4Night APIs with retry and rate limiting."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Park4Night-Scraper/1.0 (research purposes)",
                "Accept": "application/json",
            }
        )

        # Configure retry strategy
        retry = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_DELAY,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, params: dict, use_json: bool = True) -> dict | None:
        """Make a GET request with rate limiting and error handling."""
        self._rate_limit()
        try:
            logger.debug(f"GET {url} {params}")
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            if use_json:
                return response.json()
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {url} - {e}")
            return None
        except ValueError as e:
            logger.error(f"JSON parse error: {url} - {e}")
            return None

    # ── Guest API (legacy, richest data) ───────────────────────────

    def get_places_guest(self, latitude: float, longitude: float) -> list | None:
        """
        Get places from the guest API.
        Returns up to 100 places with rich data including photos, services, pricing.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
        }
        data = self._get(PLACES_ENDPOINT, params)
        if data and "lieux" in data:
            return data["lieux"]
        return []

    def get_reviews_guest(self, place_id: int) -> list | None:
        """
        Get reviews for a place from the guest API.
        Returns list of review objects with rating and text.
        """
        params = {"lieu_id": place_id}
        data = self._get(REVIEWS_ENDPOINT, params)
        if data and data.get("status") == "OK":
            return data.get("commentaires", [])
        return []

    # ── New API ────────────────────────────────────────────────────

    def get_places_new(
        self, latitude: float, longitude: float, radius: int = 200, lang: str = "en"
    ) -> list | None:
        """Get places from the new API. Returns up to 200 places."""
        params = {
            "lat": latitude,
            "lng": longitude,
            "radius": radius,
            "filter": "{}",
            "lang": lang,
        }
        data = self._get(NEW_PLACES_ENDPOINT, params)
        if isinstance(data, list):
            return data
        return []

    def get_place_detail_new(self, place_id: int, lang: str = "en") -> dict | None:
        """Get detailed place info from the new API."""
        url = NEW_PLACE_DETAIL.format(id=place_id)
        params = {"lang": lang}
        return self._get(url, params)

    def get_place_reviews_new(self, place_id: int, lang: str = "en") -> list | None:
        """Get reviews from the new API."""
        url = NEW_PLACE_REVIEWS.format(id=place_id)
        params = {"lang": lang}
        data = self._get(url, params)
        if isinstance(data, list):
            return data
        return []

    # ── Grid generation ────────────────────────────────────────────

    @staticmethod
    def _generate_region_points(region: dict) -> list[tuple[float, float]]:
        """Generate grid points for a single region."""
        points = []
        lat_min, lat_max = region["lat_min"], region["lat_max"]
        lng_min, lng_max = region["lng_min"], region["lng_max"]
        step = region["step"]

        # Handle both north-to-south and south-to-north ranges
        lat_step = step if lat_min <= lat_max else -step
        lng_step = step if lng_min <= lng_max else -step

        lat = lat_min
        while (lat_step > 0 and lat <= lat_max) or (lat_step < 0 and lat >= lat_max):
            lng = lng_min
            while (lng_step > 0 and lng <= lng_max) or (lng_step < 0 and lng >= lng_max):
                points.append((round(lat, 4), round(lng, 4)))
                lng += lng_step
            lat += lat_step
        return points

    @staticmethod
    def generate_grid_points() -> list[tuple[float, float]]:
        """Generate all grid points for scraping the entire globe."""
        points = []
        for region in REGIONS:
            points.extend(Park4NightAPI._generate_region_points(region))
        return points

    @staticmethod
    def generate_grid_points_for_region(region_name: str) -> list[tuple[float, float]]:
        """Generate grid points for a specific region by name."""
        for region in REGIONS:
            if region["name"] == region_name:
                return Park4NightAPI._generate_region_points(region)
        return []


def create_api_client() -> Park4NightAPI:
    """Factory function for creating API clients."""
    return Park4NightAPI()
