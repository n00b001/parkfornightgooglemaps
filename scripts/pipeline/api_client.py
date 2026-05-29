"""
Park4Night API Client.

Handles all HTTP requests to Park4Night APIs with retry logic,
rate limiting, error handling, and disk-based response caching.

Disk cache: API responses are cached to scripts/data/cache/api/ to avoid
re-fetching on every run. This is the primary idempotency mechanism —
re-running the pipeline finds cached responses and skips HTTP requests.

Why cache API responses:
  - Park4Night API has rate limiting (0.3s between requests)
  - 10,000 grid points = 50 minutes of rate limiting on every run
  - With cache: re-run completes in seconds (no HTTP requests)
  - Cache key is grid point coordinates (same coords → same response)
"""

from __future__ import annotations

import logging
import os
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cache import api_cache  # type: ignore[import-not-found]
from config import (  # type: ignore[import-not-found]
    MAX_RETRIES,
    PLACES_ENDPOINT,
    REGIONS,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    RETRY_DELAY,
    REVIEWS_ENDPOINT,
)

logger = logging.getLogger("pipeline")


class Park4NightAPI:
    """Client for Park4Night APIs with retry and rate limiting."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Park4Night-Scraper/1.0 (research purposes)",
                "Accept": "application/json",
            }
        )

        retry = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_DELAY,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, params: dict) -> dict | None:
        self._rate_limit()
        try:
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {url} - {e}")
            return None
        except ValueError as e:
            logger.error(f"JSON parse error: {url} - {e}")
            return None

    def get_places(
        self,
        latitude: float,
        longitude: float,
    ) -> list[dict]:
        """Get places from the guest API for a grid point.

        Disk cached: same (lat, lng) → same response, no HTTP request.

        Args:
            latitude: Grid point latitude.
            longitude: Grid point longitude.

        Returns:
            List of place dicts from the API, or empty list on failure.
        """
        # Disk cache: check if this grid point was already fetched
        cache_key = f"places:{latitude}:{longitude}"
        cached: list[dict] | None = api_cache.get(cache_key, None)  # type: ignore[assignment]
        if cached is not None:
            return cached

        data = self._get(
            PLACES_ENDPOINT,
            {
                "latitude": latitude,
                "longitude": longitude,
            },
        )
        if data and "lieux" in data:
            result = data["lieux"]
        else:
            result = []
        api_cache.set(cache_key, result)
        return result

    def get_reviews(self, place_id: int) -> list[dict]:
        """Get reviews for a place from the guest API.

        Disk cached: same place_id → same response, no HTTP request.

        Args:
            place_id: Park4Night place ID.

        Returns:
            List of review dicts from the API, or empty list on failure.
        """
        # Disk cache: check if reviews for this place were already fetched
        cache_key = f"reviews:{place_id}"
        cached: list[dict] | None = api_cache.get(cache_key, None)  # type: ignore[assignment]
        if cached is not None:
            return cached

        # Why REVIEWS_ENDPOINT (commGet.php): this is the dedicated reviews endpoint.
        # PLACES_ENDPOINT (lieuxGetFilter.php) returns place data, not reviews.
        # Using the wrong endpoint means reviews are never fetched.
        data = self._get(REVIEWS_ENDPOINT, {"lieu_id": place_id})
        if data and data.get("status") == "OK":
            result = data.get("commentaires", [])
        else:
            result = []
        api_cache.set(cache_key, result)
        return result

    @staticmethod
    def generate_grid_points() -> list[tuple[float, float]]:
        """Generate all grid points for scraping.

        Returns list of (latitude, longitude) tuples covering all regions
        defined in config.REGIONS.
        """
        points: list[tuple[float, float]] = []
        for region in REGIONS:
            lat_min, lat_max = region["lat_min"], region["lat_max"]
            lng_min, lng_max = region["lng_min"], region["lng_max"]
            step = region["step"]

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
