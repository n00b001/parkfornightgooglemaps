"""Park4Night API Client.

Handles all HTTP requests to Park4Night APIs with retry logic,
rate limiting, error handling, and disk-based response caching.

API responses are cached via @cache.memoize() decorators.
The --no-disk-cache flag bypasses the cache for timing tests.
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

from cache import cache  # type: ignore[import-not-found]
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


def _create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    session.headers.update(
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
    session.mount("https://", adapter)
    return session


# ── Fetch places ──────────────────────────────────────────────────────


def _fetch_places_impl(lat: float, lng: float) -> list[dict]:
    """Raw implementation — no caching."""
    session = _create_session()
    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(
            PLACES_ENDPOINT,
            params={"latitude": lat, "longitude": lng},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("lieux", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {PLACES_ENDPOINT} - {e}")
        return []
    except ValueError as e:
        logger.error(f"JSON parse error: {PLACES_ENDPOINT} - {e}")
        return []


@cache.memoize()
def _fetch_places_cached(lat: float, lng: float) -> list[dict]:
    return _fetch_places_impl(lat, lng)


def fetch_places_for_grid(
    lat: float,
    lng: float,
    use_cache: bool = True,
) -> list[dict]:
    """Fetch places from the guest API for a grid point.

    Args:
        lat: Grid point latitude.
        lng: Grid point longitude.
        use_cache: If False, bypass disk cache (for --no-disk-cache timing).
    """
    if use_cache:
        return _fetch_places_cached(lat, lng)
    return _fetch_places_impl(lat, lng)


# ── Fetch reviews ─────────────────────────────────────────────────────


def _fetch_reviews_impl(place_id: int) -> list[dict]:
    """Raw implementation — no caching."""
    session = _create_session()
    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(
            REVIEWS_ENDPOINT,
            params={"lieu_id": place_id},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "OK":
            return data.get("commentaires", [])
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {REVIEWS_ENDPOINT} - {e}")
        return []
    except ValueError as e:
        logger.error(f"JSON parse error: {REVIEWS_ENDPOINT} - {e}")
        return []


@cache.memoize()
def _fetch_reviews_cached(place_id: int) -> list[dict]:
    return _fetch_reviews_impl(place_id)


def fetch_reviews_for_place(
    place_id: int,
    use_cache: bool = True,
) -> list[dict]:
    """Fetch reviews for a place from the guest API.

    Args:
        place_id: Park4Night place ID.
        use_cache: If False, bypass disk cache (for --no-disk-cache timing).
    """
    if use_cache:
        return _fetch_reviews_cached(place_id)
    return _fetch_reviews_impl(place_id)


# ── Park4NightAPI client ──────────────────────────────────────────────


class Park4NightAPI:
    """Client for Park4Night APIs with rate limiting."""

    def __init__(self, use_cache: bool = True) -> None:
        self._use_cache = use_cache

    def get_places(self, latitude: float, longitude: float) -> list[dict]:
        """Get places for a grid point."""
        return fetch_places_for_grid(latitude, longitude, use_cache=self._use_cache)

    def get_reviews(self, place_id: int) -> list[dict]:
        """Get reviews for a place."""
        return fetch_reviews_for_place(place_id, use_cache=self._use_cache)

    @staticmethod
    def generate_grid_points() -> list[tuple[float, float]]:
        """Generate all grid points for scraping."""
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
