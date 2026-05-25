"""
Checkpoint / Resume System

Tracks which grid points have been processed and which places
have been fetched, allowing the scraper to resume after interruption.
"""

import json
import logging
import os
from datetime import UTC, datetime

from config import CHECKPOINT_FILE

logger = logging.getLogger(__name__)


class Checkpoint:
    """Manages scraper progress for resume capability."""

    def __init__(self, checkpoint_file: str = CHECKPOINT_FILE):
        self.file = checkpoint_file
        self.data = self._load()

    def _load(self) -> dict:
        """Load checkpoint from file, or create new one."""
        if os.path.exists(self.file):
            try:
                with open(self.file, encoding="utf-8") as f:
                    data = json.load(f)
                # Convert lists back to sets (JSON serializes sets as lists)
                data["places_fetched"] = set(data.get("places_fetched", []))
                data["reviews_fetched"] = set(data.get("reviews_fetched", []))
                return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load checkpoint: {e}, starting fresh")
                return self._new_checkpoint()
        return self._new_checkpoint()

    @staticmethod
    def _new_checkpoint() -> dict:
        """Create a new checkpoint structure."""
        return {
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "last_updated": datetime.now(UTC).isoformat(),
            "grid_points_completed": [],  # list of "lat,lng" strings
            "places_fetched": set(),  # set of place IDs (stored as list for JSON)
            "reviews_fetched": set(),  # set of place IDs with reviews fetched
            "total_places": 0,
            "total_reviews": 0,
            "errors": [],
        }

    def _save(self):
        """Save checkpoint to file."""
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        # Convert sets to lists for JSON serialization
        save_data = {
            **self.data,
            "places_fetched": list(self.data["places_fetched"]),
            "reviews_fetched": list(self.data["reviews_fetched"]),
            "last_updated": datetime.now(UTC).isoformat(),
        }
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2)

    def mark_grid_point_done(self, lat: float, lng: float):
        """Mark a grid point as completed."""
        key = f"{lat},{lng}"
        if key not in self.data["grid_points_completed"]:
            self.data["grid_points_completed"].append(key)
            self._save()

    def is_grid_point_done(self, lat: float, lng: float) -> bool:
        """Check if a grid point was already processed."""
        return f"{lat},{lng}" in self.data["grid_points_completed"]

    def get_remaining_grid_points(
        self, all_points: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Get grid points that haven't been processed yet."""
        return [(lat, lng) for lat, lng in all_points if not self.is_grid_point_done(lat, lng)]

    def mark_place_fetched(self, place_id: int):
        """Mark a place as fetched."""
        self.data["places_fetched"].add(str(place_id))
        self.data["total_places"] = len(self.data["places_fetched"])

    def is_place_fetched(self, place_id: int) -> bool:
        """Check if a place was already fetched."""
        return str(place_id) in self.data["places_fetched"]

    def mark_reviews_fetched(self, place_id: int):
        """Mark reviews for a place as fetched (does NOT save — caller saves periodically)."""
        self.data["reviews_fetched"].add(str(place_id))

    def is_reviews_fetched(self, place_id: int) -> bool:
        """Check if reviews were already fetched for a place."""
        return str(place_id) in self.data["reviews_fetched"]

    def get_places_needing_reviews(self, place_ids: list[int]) -> list[int]:
        """Get place IDs that need reviews fetched."""
        return [pid for pid in place_ids if not self.is_reviews_fetched(pid)]

    def add_error(self, message: str):
        """Record an error."""
        self.data["errors"].append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "message": message,
            }
        )
        # Keep only last 100 errors
        self.data["errors"] = self.data["errors"][-100:]
        self._save()

    def get_summary(self) -> dict:
        """Get a summary of scraper progress."""
        return {
            "grid_points_completed": len(self.data["grid_points_completed"]),
            "places_fetched": len(self.data["places_fetched"]),
            "reviews_fetched": len(self.data["reviews_fetched"]),
            "total_places": self.data["total_places"],
            "total_reviews": self.data["total_reviews"],
            "errors": len(self.data["errors"]),
            "created_at": self.data["created_at"],
            "last_updated": self.data["last_updated"],
        }

    def reset(self):
        """Reset checkpoint (start fresh)."""
        self.data = self._new_checkpoint()
        self._save()
        logger.info("Checkpoint reset")
