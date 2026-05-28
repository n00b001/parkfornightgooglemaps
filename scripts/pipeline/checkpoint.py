"""
Unified checkpoint system for the pipeline.

Tracks which grid points have been scraped and which places
have completed each stage (extract, normalize, images, R2, DB).
Allows resuming from any point after interruption.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CHECKPOINT_FILE  # type: ignore[import-not-found]

logger = logging.getLogger("pipeline")


class PipelineCheckpoint:
    """Manages pipeline progress for resume capability.

    Tracks:
    - Grid points completed (scraped)
    - Per-place stage completion (extract, normalize, images, R2, DB)
    - Overall statistics
    """

    def __init__(self, checkpoint_file: str = CHECKPOINT_FILE):
        self.file = checkpoint_file
        self.data = self._load()

    def _load(self) -> dict:
        """Load checkpoint from file, or create new one."""
        if os.path.exists(self.file):
            try:
                with open(self.file, encoding="utf-8") as f:
                    data = json.load(f)
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
            "grid_points_done": [],
            "places": {},
            "processed_place_ids": [],
            "place_grid_points": {},
            "stats": {
                "total_places_processed": 0,
                "total_reviews_processed": 0,
                "total_images_downloaded": 0,
                "total_images_uploaded_r2": 0,
                "errors": [],
            },
        }

    def _save(self) -> None:
        """Save checkpoint to file."""
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        self.data["last_updated"] = datetime.now(UTC).isoformat()
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    # ── Grid Points ───────────────────────────────
    def mark_grid_point_done(self, lat: float, lng: float) -> None:
        """Mark a grid point as completed."""
        key = f"{lat},{lng}"
        if key not in self.data["grid_points_done"]:
            self.data["grid_points_done"].append(key)
            self._save()

    def is_grid_point_done(self, lat: float, lng: float) -> bool:
        """Check if a grid point was already processed."""
        return f"{lat},{lng}" in self.data["grid_points_done"]

    def get_remaining_grid_points(
        self, all_points: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Get grid points that haven't been processed yet."""
        return [(lat, lng) for lat, lng in all_points if not self.is_grid_point_done(lat, lng)]

    # ── Place Stages ──────────────────────────────
    def _get_place_record(self, place_id: int) -> dict:
        """Get or create a place record."""
        pid = str(place_id)
        if pid not in self.data["places"]:
            self.data["places"][pid] = {
                "stages": {},
            }
        return self.data["places"][pid]

    def mark_place_stage_done(self, place_id: int, stage: str) -> None:
        """Mark a stage as completed for a place."""
        record = self._get_place_record(place_id)
        record["stages"][stage] = True
        self._save()

    def is_place_stage_done(self, place_id: int, stage: str) -> bool:
        """Check if a stage was completed for a place."""
        pid = str(place_id)
        place_record = self.data["places"].get(pid, {})
        return place_record.get("stages", {}).get(stage, False)

    def get_place_stages(self, place_id: int) -> dict[str, bool]:
        """Get all stage completion status for a place."""
        pid = str(place_id)
        place_record = self.data["places"].get(pid, {})
        return place_record.get("stages", {})

    def is_place_fully_processed(self, place_id: int) -> bool:
        """Check if a place has completed all stages.

        Checks both the new processed_place_ids list AND the legacy stage tracking.
        """
        if self.is_place_processed(place_id):
            return True
        required_stages = [
            "extracted",
            "normalized",
            "images_uploaded_r2",
            "db_inserted",
        ]
        return all(self.is_place_stage_done(place_id, stage) for stage in required_stages)

    # ── Statistics ────────────────────────────────
    def increment_stat(self, key: str, amount: int = 1) -> None:
        """Increment a statistic."""
        self.data["stats"][key] = self.data["stats"].get(key, 0) + amount

    def add_error(self, message: str) -> None:
        """Record an error."""
        self.data["stats"]["errors"].append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "message": message,
            }
        )
        # Keep only last 100 errors
        self.data["stats"]["errors"] = self.data["stats"]["errors"][-100:]
        self._save()

    def get_summary(self) -> dict:
        """Get a summary of pipeline progress."""
        total_places = len(self.data["places"])
        fully_processed = sum(
            1 for pid in self.data["places"] if self.is_place_fully_processed(int(pid))
        )

        return {
            "grid_points_done": len(self.data["grid_points_done"]),
            "total_places": total_places,
            "fully_processed": fully_processed,
            **self.data["stats"],
        }

    # ── Processed Places ─────────────────────────
    def is_place_processed(self, place_id: int) -> bool:
        """Check if a place has been fully processed (end-to-end)."""
        return str(place_id) in self.data.get("processed_place_ids", [])

    def mark_place_processed(self, place_id: int, lat: float, lng: float) -> None:
        """Mark a place as fully processed and record its grid point."""
        pid = str(place_id)
        processed = self.data.setdefault("processed_place_ids", [])
        if pid not in processed:
            processed.append(pid)
        self.data.setdefault("place_grid_points", {})[pid] = f"{lat},{lng}"
        self._save()

    def get_processed_place_ids(self, limit: int | None = None) -> list[int]:
        """Return processed place IDs, optionally limited."""
        ids = [
            int(pid) for pid in self.data.get("processed_place_ids", [])
            if pid.isdigit()
        ]
        if limit is not None:
            return ids[:limit]
        return ids

    def get_place_grid_point(self, place_id: int) -> tuple[float, float] | None:
        """Look up the grid point for a processed place. Returns (lat, lng) or None."""
        key = self.data.get("place_grid_points", {}).get(str(place_id))
        if key:
            parts = key.split(",")
            return float(parts[0]), float(parts[1])
        return None

    def reset(self) -> None:
        """Reset checkpoint (start fresh)."""
        self.data = self._new_checkpoint()
        self._save()
        logger.info("Checkpoint reset")
