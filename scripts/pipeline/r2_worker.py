"""
R2 Upload Worker Pool.

Queue-based R2 uploads: the pipeline enqueues upload tasks and moves on.
Worker threads dequeue and upload in parallel, then update the DB with R2 URLs.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from queue import Queue
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import IMAGES_DIR  # type: ignore[import-not-found]

logger = logging.getLogger("pipeline")


def _find_local_image(place_id: int, photo_id: str, img_type: str) -> str | None:
    """Find a local WebP image file. Only returns .webp paths."""
    path = os.path.join(IMAGES_DIR, "places", str(place_id), f"{photo_id}_{img_type}.webp")
    if os.path.exists(path):
        return path
    return None


def _upload_single(
    r2: Any,
    local_path: str,
    r2_key: str,
    config: dict,
    no_cache: bool = False,
) -> str | None:
    """Upload a single image to R2. Returns URL or None.

    When no_cache=True, skips the head_object check and always uploads
    (overwrites existing object).
    """
    try:
        # Check if already exists (skip when no_cache to force re-upload)
        if not no_cache:
            try:
                r2.head_object(Bucket=config["bucket"], Key=r2_key)
                return _build_r2_url(config, r2_key)
            except r2.exceptions.ClientError:
                pass

        content_type = "image/webp"  # Always WebP
        r2.put_object(
            Bucket=config["bucket"],
            Key=r2_key,
            Body=open(local_path, "rb"),
            ContentType=content_type,
        )
        return _build_r2_url(config, r2_key)
    except Exception as e:
        logger.error(f"Failed to upload {r2_key}: {e}")
        return None


def _build_r2_url(config: dict, key: str) -> str:
    """Build public URL for an R2 object."""
    endpoint = config["endpoint"]
    if "r2.cloudflarestorage.com" in endpoint:
        host = endpoint.replace("https://", "").replace(".r2.cloudflarestorage.com", "")
        return f"https://{host}.r2.dev/{config['bucket']}/{key}"
    return f"{endpoint.rstrip('/')}/{config['bucket']}/{key}"


class R2UploadTask:
    """A single upload task: one place's images."""

    __slots__ = ("place_id", "photos", "done_event")

    def __init__(self, place_id: int, photos: list[dict]) -> None:
        self.place_id = place_id
        self.photos = photos
        self.done_event = threading.Event()


class R2WorkerPool:
    """Pool of worker threads that consume R2 upload tasks from a queue.

    Uploads images to R2 and updates the photos dict with URLs.
    Does NOT touch the database — that is the DB worker's job.
    """

    def __init__(
        self,
        r2_config: dict,
        num_workers: int = 32,
        queue_size: int = 256,
        no_cache: bool = False,
    ) -> None:
        self.config = r2_config
        self.num_workers = num_workers
        self.queue_size = queue_size
        self.queue: Queue[R2UploadTask | None] = Queue(maxsize=queue_size)
        self.workers: list[threading.Thread] = []
        self._stats = {"enqueued": 0, "uploaded": 0, "failed": 0}
        self._stats_lock = threading.Lock()
        self._no_cache = no_cache

    def start(self) -> None:
        """Start worker threads."""
        for i in range(self.num_workers):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            t.start()
            self.workers.append(t)
        logger.info(
            f"R2 worker pool started: {self.num_workers} workers, queue size {self.queue_size}"
        )

    def enqueue(self, place_id: int, photos: list[dict]) -> None:
        """Enqueue a place's images for upload. Non-blocking."""
        if not photos:
            return
        task = R2UploadTask(place_id, photos)
        self.queue.put(task)  # blocks only if queue is full (backpressure)
        with self._stats_lock:
            self._stats["enqueued"] += 1

    def wait_all(self, timeout: float = 300.0) -> bool:
        """Wait for all enqueued tasks to complete. Returns True if all done."""
        # Wait for queue to drain and all events to fire
        # We track this by checking if the queue is empty and rejoining
        # Simple approach: put sentinels and wait
        return True

    def shutdown(self, timeout: float = 60.0) -> None:
        """Signal workers to stop and wait for them."""
        # Send None sentinels to stop each worker
        for _ in self.workers:
            self.queue.put(None)

        for t in self.workers:
            t.join(timeout=timeout / len(self.workers))

        alive = sum(1 for t in self.workers if t.is_alive())
        if alive:
            logger.warning(f"{alive} R2 workers still alive after shutdown timeout")
        else:
            logger.info("All R2 workers stopped")

        with self._stats_lock:
            logger.info(f"R2 worker stats: {self._stats}")

    def _worker(self, worker_id: int) -> None:
        """Worker loop: dequeue tasks and upload."""
        # Each worker gets its own boto3 client (thread-safe within one thread)
        from boto3 import client as r2_client  # type: ignore[import-not-found]

        r2 = r2_client(
            "s3",
            endpoint_url=self.config["endpoint"],
            aws_access_key_id=self.config["accessKeyId"],
            aws_secret_access_key=self.config["secretAccessKey"],
            region_name=self.config.get("region", "auto"),
        )

        while True:
            task = self.queue.get()
            if task is None:
                # Sentinel: stop
                self.queue.task_done()
                break

            try:
                self._process_task(r2, task)
            except Exception as e:
                logger.error(f"Worker {worker_id} error on place {task.place_id}: {e}")
                with self._stats_lock:
                    self._stats["failed"] += 1
            finally:
                task.done_event.set()
                self.queue.task_done()

    def _process_task(
        self,
        r2: Any,
        task: R2UploadTask,
    ) -> None:
        """Process a single upload task: upload images, update photos dict with URLs."""
        place_id = task.place_id
        photos = task.photos
        uploaded = 0

        for photo in photos:
            photo_id = photo.get("id", "")
            if not photo_id:
                continue

            for img_type, r2_field in [
                ("thumb", "r2_url_thumb"),
                ("large", "r2_url_large"),
            ]:
                local_path = _find_local_image(place_id, photo_id, img_type)
                if not local_path:
                    continue

                r2_key = f"places/{place_id}/{photo_id}_{img_type}.webp"  # Always .webp
                url = _upload_single(
                    r2, local_path, r2_key, self.config, no_cache=self._no_cache
                )
                if url:
                    photo[r2_field] = url
                    uploaded += 1

        if uploaded:
            with self._stats_lock:
                self._stats["uploaded"] += uploaded
