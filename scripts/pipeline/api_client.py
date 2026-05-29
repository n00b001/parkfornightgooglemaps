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

from cache import (  # type: ignore[import-not-found]
    api_cache_get_places,
    api_cache_get_reviews,
    api_cache_set_places,
    api_cache_set_reviews,
)
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
    """Client for Park4Night APIs with retry, rate limiting, and disk cache.

    All responses are cached to disk. Re-running the pipeline with the same
    grid points skips HTTP requests entirely (cache hit).

    The `no_disk_cache` flag bypasses the cache: skips cache reads before
    fetching, forcing fresh data from the API.
    """

    def __init__(self, no_disk_cache: bool = False) -> None:
        self._no_disk_cache = no_disk_cache
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

    @property
    def no_disk_cache(self) -> bool:
        """Whether cache is bypassed (--no-disk-cache mode)."""
        return self._no_disk_cache

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

        Checks disk cache first. If cached, returns immediately without
        making an HTTP request. If not cached (or no_disk_cache mode), fetches
        from API and caches the response.

        Args:
            latitude: Grid point latitude.
            longitude: Grid point longitude.

        Returns:
            List of place dicts from the API, or empty list on failure.
        """
        # Check cache first
        if not self._no_disk_cache:
            cached = api_cache_get_places(latitude, longitude)
            if cached is not None:
                return cached

        # Fetch from API
        data = self._get(
            PLACES_ENDPOINT,
            {
                "latitude": latitude,
                "longitude": longitude,
            },
        )
        if data and "lieux" in data:
            places = data["lieux"]
            # Cache the response
            api_cache_set_places(latitude, longitude, places)
            return places
        return []

    def get_reviews(self, place_id: int) -> list[dict]:
        """Get reviews for a place from the guest API.

        Checks disk cache first. If cached, returns immediately.
        If not cached (or no_disk_cache mode), fetches from API and caches.

        Args:
            place_id: Park4Night place ID.

        Returns:
            List of review dicts from the API, or empty list on failure.
        """
        # Check cache first
        if not self._no_disk_cache:
            cached = api_cache_get_reviews(place_id)
            if cached is not None:
                return cached

        # Fetch from API
        # Why REVIEWS_ENDPOINT (commGet.php): this is the dedicated reviews endpoint.
        # PLACES_ENDPOINT (lieuxGetFilter.php) returns place data, not reviews.
        # Using the wrong endpoint means reviews are never fetched.
        data = self._get(REVIEWS_ENDPOINT, {"lieu_id": place_id})
        if data and data.get("status") == "OK":
            reviews = data.get("commentaires", [])
            # Cache the response
            api_cache_set_reviews(place_id, reviews)
            return reviews
        return []

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
