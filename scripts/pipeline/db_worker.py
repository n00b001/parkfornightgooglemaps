"""
DB Upload Worker Pool.

Queue-based Supabase inserts: the pipeline enqueues DB tasks and moves on.
Worker threads dequeue and insert in parallel, each with its own connection.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import uuid
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger("pipeline")


def _get_db_url() -> str:
    """Get database URL from environment."""
    database_url = os.environ.get("DATABASE_URL", "")
    if "?" in database_url:
        database_url = database_url.split("?")[0]
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")
    return database_url


def _get_connection() -> psycopg2.extensions.connection:
    """Get a new DB connection (one per worker thread)."""
    conn = psycopg2.connect(_get_db_url())
    conn.autocommit = False
    return conn


def _ensure_lookup_entry(
    conn: psycopg2.extensions.connection,
    table: str,
    code_field: str,
    label_field: str,
    code: str,
    label: str,
) -> None:
    """Insert a lookup entry if it doesn't exist (upsert)."""
    cur = conn.cursor()
    try:
        if table == "PlaceType":
            cur.execute(
                f"""
                INSERT INTO "{table}" ({label_field}, {code_field})
                VALUES (%s, %s)
                ON CONFLICT ({code_field}) DO UPDATE SET {label_field} = EXCLUDED.{label_field}
                """,
                (label or code, code),
            )
        elif table == "VehicleType":
            cur.execute(
                f"""
                INSERT INTO "{table}" (code, {code_field})
                VALUES (%s, %s)
                ON CONFLICT ({code_field}) DO NOTHING
                """,
                (code, code),
            )
        else:
            cur.execute(
                f"""
                INSERT INTO "{table}" (code, label, {code_field})
                VALUES (%s, %s, %s)
                ON CONFLICT ({code_field}) DO UPDATE SET label = EXCLUDED.label
                """,
                (code, label or code, code),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to upsert {table} {code}: {e}")
        raise  # propagate — caller must handle missing lookup entry
    finally:
        cur.close()


def _get_lookup_maps(
    conn: psycopg2.extensions.connection,
) -> tuple[dict, dict, dict]:
    """Get lookup maps for place type, service, and activity."""
    cur = conn.cursor()
    try:
        cur.execute('SELECT id, "originalCode" FROM "PlaceType"')
        type_map = {row[1]: row[0] for row in cur.fetchall()}

        cur.execute('SELECT id, "originalCode" FROM "Service"')
        service_map = {row[1]: row[0] for row in cur.fetchall()}

        cur.execute('SELECT id, "originalCode" FROM "Activity"')
        activity_map = {row[1]: row[0] for row in cur.fetchall()}
    finally:
        cur.close()
    return type_map, service_map, activity_map


def _get_vehicle_map(conn: psycopg2.extensions.connection) -> dict:
    """Get vehicle type mapping."""
    cur = conn.cursor()
    try:
        cur.execute('SELECT id, "originalCode" FROM "VehicleType"')
        return {row[1]: row[0] for row in cur.fetchall()}
    finally:
        cur.close()


def _get_system_user_id(conn: psycopg2.extensions.connection) -> str:
    """Get or create system user for scraped reviews."""
    cur = conn.cursor()
    system_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "scraped-import-system-user"))
    try:
        cur.execute(
            """
            INSERT INTO "User" (id, "googleId", email, "updatedAt")
            VALUES (%s, 'scraped-import', 'scraped@import.local', NOW())
            ON CONFLICT ("googleId") DO UPDATE SET id = EXCLUDED.id, "updatedAt" = NOW()
            RETURNING id
            """,
            (system_user_id,),
        )
        conn.commit()
        row = cur.fetchone()
        return row[0] if row else system_user_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to create system user: {e}")
        return system_user_id
    finally:
        cur.close()


class DBUploadTask:
    """A single DB insert task: one place + its reviews."""

    __slots__ = ("place", "reviews", "done_event")

    def __init__(self, place: dict, reviews: list[dict] | None = None) -> None:
        self.place = place
        self.reviews = reviews or []
        self.done_event = threading.Event()


class DBWorkerPool:
    """Pool of worker threads that consume DB insert tasks from a queue."""

    def __init__(
        self,
        num_workers: int = 8,
        queue_size: int = 128,
    ) -> None:
        self.num_workers = num_workers
        self.queue_size = queue_size
        self.queue: Queue[DBUploadTask | None] = Queue(maxsize=queue_size)
        self.workers: list[threading.Thread] = []
        self._stats = {"enqueued": 0, "inserted": 0, "failed": 0}
        self._stats_lock = threading.Lock()

    def start(self) -> None:
        """Start worker threads."""
        for i in range(self.num_workers):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            t.start()
            self.workers.append(t)
        logger.info(
            f"DB worker pool started: {self.num_workers} workers, queue size {self.queue_size}"
        )

    def enqueue(self, place: dict, reviews: list[dict] | None = None) -> None:
        """Enqueue a place for DB insert. Non-blocking."""
        task = DBUploadTask(place, reviews)
        self.queue.put(task)  # blocks only if queue is full (backpressure)
        with self._stats_lock:
            self._stats["enqueued"] += 1

    def shutdown(self, timeout: float = 60.0) -> None:
        """Signal workers to stop and wait for them."""
        for _ in self.workers:
            self.queue.put(None)

        for t in self.workers:
            t.join(timeout=timeout / len(self.workers))

        alive = sum(1 for t in self.workers if t.is_alive())
        if alive:
            logger.warning(f"{alive} DB workers still alive after shutdown timeout")
        else:
            logger.info("All DB workers stopped")

        with self._stats_lock:
            logger.info(f"DB worker stats: {self._stats}")

    def _worker(self, worker_id: int) -> None:
        """Worker loop: dequeue tasks and insert into DB."""
        conn = _get_connection()

        # Initialize system user on this connection
        system_user_id = _get_system_user_id(conn)

        while True:
            task = self.queue.get()
            if task is None:
                self.queue.task_done()
                break

            try:
                self._process_task(conn, system_user_id, task)
            except Exception as e:
                logger.error(f"Worker {worker_id} error on place {task.place.get('id')}: {e}")
                with self._stats_lock:
                    self._stats["failed"] += 1
            finally:
                task.done_event.set()
                self.queue.task_done()

        conn.close()

    def _process_task(
        self,
        conn: psycopg2.extensions.connection,
        system_user_id: str,
        task: DBUploadTask,
    ) -> None:
        """Process a single DB insert task: place + reviews."""
        place = task.place

        # Upsert lookup entries
        self._upsert_lookups(conn, place)

        # Get fresh lookup maps
        type_map, service_map, activity_map = _get_lookup_maps(conn)

        # Insert place
        self._insert_place(conn, place, type_map, service_map, activity_map)

        # Insert reviews
        if task.reviews:
            vehicle_map = _get_vehicle_map(conn)
            self._insert_reviews(conn, task.reviews, system_user_id, vehicle_map)

        with self._stats_lock:
            self._stats["inserted"] += 1

    def _upsert_lookups(
        self,
        conn: psycopg2.extensions.connection,
        place: dict,
    ) -> None:
        """Upsert lookup table entries for this place."""
        # Place type (normalized data uses flat keys: type_code, type_label)
        type_code = place.get("type_code", "")
        type_label = place.get("type_label", "")
        if type_code:
            _ensure_lookup_entry(
                conn,
                "PlaceType",
                '"originalCode"',
                '"englishName"',
                type_code,
                type_label,
            )

        # Services
        for svc in place.get("services", []):
            if isinstance(svc, dict):
                _ensure_lookup_entry(
                    conn,
                    "Service",
                    '"originalCode"',
                    "label",
                    svc.get("code", ""),
                    svc.get("label", ""),
                )

        # Activities
        for act in place.get("activities", []):
            if isinstance(act, dict):
                _ensure_lookup_entry(
                    conn,
                    "Activity",
                    '"originalCode"',
                    "label",
                    act.get("code", ""),
                    act.get("label", ""),
                )

        # Vehicle type
        owner = place.get("owner", {})
        if isinstance(owner, dict):
            vt = owner.get("vehicle_type", "")
            if vt:
                _ensure_lookup_entry(
                    conn,
                    "VehicleType",
                    '"originalCode"',
                    "code",
                    vt,
                    "",
                )

    def _insert_place(
        self,
        conn: psycopg2.extensions.connection,
        place: dict,
        type_map: dict,
        service_map: dict,
        activity_map: dict,
    ) -> None:
        """Insert a single place into the database.

        Supports partial records (e.g., just photos update from convert-existing mode).
        If type_code is missing, only updates the photos column.
        """
        cur = conn.cursor()
        try:
            type_code = place.get("type_code", "")
            type_id = type_map.get(type_code)

            # Partial record (no type_code) — just update photos
            if type_id is None and not type_code:
                cur.execute(
                    """
                    UPDATE "Place"
                    SET photos = %s, "photoCount" = %s
                    WHERE id = %s
                    """,
                    (
                        json.dumps(place.get("photos", [])),
                        place.get("photo_count", 0),
                        place["id"],
                    ),
                )
                conn.commit()
                return

            if type_id is None:
                raise KeyError(
                    f"Place {place.get('id')}: type_code '{type_code}' "
                    f"not in PlaceType table — upsert may have failed"
                )

            execute_values(
                cur,
                """
                INSERT INTO "Place" (
                    id, name, latitude, longitude, "typeId", address,
                    rating, "reviewCount", "photoCount", photos, pricing,
                    access, contact, descriptions, "isPublic", "onlineBooking",
                    "lastFetched"
                ) VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    photos = EXCLUDED.photos,
                    rating = EXCLUDED.rating,
                    "reviewCount" = EXCLUDED."reviewCount",
                    "photoCount" = EXCLUDED."photoCount",
                    pricing = EXCLUDED.pricing,
                    access = EXCLUDED.access,
                    contact = EXCLUDED.contact,
                    descriptions = EXCLUDED.descriptions,
                    "lastFetched" = EXCLUDED."lastFetched"
                """,
                [
                    (
                        place["id"],
                        place.get("name") or place.get("title") or "",
                        place["latitude"],
                        place["longitude"],
                        type_id,
                        json.dumps(place.get("address", {})),
                        place.get("rating"),
                        place.get("review_count", 0),
                        place.get("photo_count", 0),
                        json.dumps(place.get("photos", [])),
                        json.dumps(place.get("pricing", {})),
                        json.dumps(place.get("access", {})),
                        json.dumps(place.get("contact", {})),
                        json.dumps(place.get("descriptions", {})),
                        place.get("is_public", True),
                        place.get("online_booking", False),
                        place.get("scraped_at") or None,
                    )
                ],
            )

            # PlaceService junctions
            for svc in place.get("services", []):
                if isinstance(svc, dict):
                    svc_id = service_map.get(svc.get("code", ""))
                    if svc_id:
                        cur.execute(
                            """
                            INSERT INTO "PlaceService" ("placeId", "serviceId")
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (place["id"], svc_id),
                        )

            # PlaceActivity junctions
            for act in place.get("activities", []):
                if isinstance(act, dict):
                    act_id = activity_map.get(act.get("code", ""))
                    if act_id:
                        cur.execute(
                            """
                            INSERT INTO "PlaceActivity" ("placeId", "activityId")
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (place["id"], act_id),
                        )

            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to insert place {place.get('id')}: {e}")
            raise  # propagate to _worker for proper stats tracking
        finally:
            cur.close()

    def _insert_reviews(
        self,
        conn: psycopg2.extensions.connection,
        reviews: list[dict],
        system_user_id: str,
        vehicle_map: dict,
    ) -> None:
        """Insert reviews for a place."""
        if not reviews:
            return

        cur = conn.cursor()
        try:
            execute_values(
                cur,
                """
                INSERT INTO "Review" (
                    id, content, rating, "vehicleTypeId", "authorName",
                    "authorId", "userId", "placeId", "createdAt"
                ) VALUES %s
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        str(uuid.uuid5(uuid.NAMESPACE_DNS, f"review-{r['id']}")),
                        r.get("text", {}).get("default", "")
                        if isinstance(r.get("text"), dict)
                        else (r.get("text") or ""),
                        r.get("rating", 0),
                        vehicle_map.get(
                            r.get("author", {}).get("vehicle_type", "")
                            if isinstance(r.get("author"), dict)
                            else "",
                        ),
                        r.get("author", {}).get("name", "")
                        if isinstance(r.get("author"), dict)
                        else "",
                        r.get("author", {}).get("id", "")
                        if isinstance(r.get("author"), dict)
                        else "",
                        system_user_id,
                        r["place_id"],
                        r.get("created_at") or None,
                    )
                    for r in reviews
                ],
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to insert reviews: {e}")
            raise  # propagate to _worker for proper stats tracking
        finally:
            cur.close()
