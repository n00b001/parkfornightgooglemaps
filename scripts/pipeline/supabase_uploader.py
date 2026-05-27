"""
Supabase uploader module.

Uploads normalized data to Supabase PostgreSQL database.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid

import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DB_BATCH_SIZE  # type: ignore[import-not-found]
from logging_setup import create_progress, log_progress

logger = logging.getLogger("pipeline")


def get_connection() -> psycopg2.extensions.connection:
    """Get Supabase PostgreSQL connection."""
    database_url = os.environ.get("DATABASE_URL", "")
    if "?" in database_url:
        database_url = database_url.split("?")[0]

    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    return conn


def ensure_schema(conn: psycopg2.extensions.connection) -> None:
    """Ensure database tables exist."""
    cur = conn.cursor()
    cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'Place')")
    row = cur.fetchone()
    cur.close()
    if not row or not row[0]:
        raise RuntimeError(
            "Database tables don't exist. Run migrations first: "
            "npx prisma migrate deploy --schema=server/prisma/schema.prisma"
        )


def create_system_user(conn: psycopg2.extensions.connection) -> str:
    """Create a system user for scraped review foreign keys."""
    cur = conn.cursor()
    system_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "scraped-import-system-user"))

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
    user_id = row[0] if row else system_user_id
    cur.close()
    return user_id


def upload_lookup_tables(conn: psycopg2.extensions.connection, data: dict[str, list[dict]]) -> None:
    """Upload lookup tables (PlaceType, Service, Activity, VehicleType)."""
    cur = conn.cursor()

    for pt in data.get("place_types", []):
        try:
            cur.execute(
                """
                INSERT INTO "PlaceType" ("englishName", "originalCode")
                VALUES (%s, %s)
                ON CONFLICT ("originalCode") DO UPDATE SET "englishName" = EXCLUDED."englishName"
                """,
                (pt.get("english_name", pt.get("code", "")), pt.get("code", "")),
            )
        except Exception as e:
            logger.error(f"Failed to insert PlaceType {pt}: {e}")

    for svc in data.get("services", []):
        try:
            cur.execute(
                """
                INSERT INTO "Service" (code, label, "originalCode")
                VALUES (%s, %s, %s)
                ON CONFLICT ("originalCode") DO UPDATE SET label = EXCLUDED.label
                """,
                (svc.get("code", ""), svc.get("label", ""), svc.get("original_code", "")),
            )
        except Exception as e:
            logger.error(f"Failed to insert Service {svc}: {e}")

    for act in data.get("activities", []):
        try:
            cur.execute(
                """
                INSERT INTO "Activity" (code, label, "originalCode")
                VALUES (%s, %s, %s)
                ON CONFLICT ("originalCode") DO UPDATE SET label = EXCLUDED.label
                """,
                (act.get("code", ""), act.get("label", ""), act.get("original_code", "")),
            )
        except Exception as e:
            logger.error(f"Failed to insert Activity {act}: {e}")

    for vt in data.get("vehicle_types", []):
        try:
            cur.execute(
                """
                INSERT INTO "VehicleType" (code, "originalCode")
                VALUES (%s, %s)
                ON CONFLICT ("originalCode") DO NOTHING
                """,
                (vt.get("code", ""), vt.get("original_code", "")),
            )
        except Exception as e:
            logger.error(f"Failed to insert VehicleType {vt}: {e}")

    conn.commit()
    cur.close()
    logger.info(
        f"Lookup tables: {len(data.get('place_types', []))} place types, "
        f"{len(data.get('services', []))} services, "
        f"{len(data.get('activities', []))} activities, "
        f"{len(data.get('vehicle_types', []))} vehicle types"
    )


def _get_lookup_maps(
    conn: psycopg2.extensions.connection,
) -> tuple[dict, dict, dict]:
    """Get lookup maps for place type, service, and activity."""
    cur = conn.cursor()

    cur.execute('SELECT id, "originalCode" FROM "PlaceType"')
    type_map = {row[1]: row[0] for row in cur.fetchall()}

    cur.execute('SELECT id, "originalCode" FROM "Service"')
    service_map = {row[1]: row[0] for row in cur.fetchall()}

    cur.execute('SELECT id, "originalCode" FROM "Activity"')
    activity_map = {row[1]: row[0] for row in cur.fetchall()}

    cur.close()
    return type_map, service_map, activity_map


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
    cur.close()


def insert_place(
    conn: psycopg2.extensions.connection,
    place: dict,
) -> None:
    """Insert a single place into Supabase.

    Handles lookup table upserts for this place's type, services, activities,
    and vehicle type. Uses ON CONFLICT to skip duplicates.
    """
    cur = conn.cursor()

    # Upsert place type
    type_code = place.get("type", {}).get("code", "")
    type_label = place.get("type", {}).get("label", "")
    if isinstance(place.get("type"), dict):
        _ensure_lookup_entry(
            conn,
            "PlaceType",
            '"originalCode"',
            '"englishName"',
            type_code,
            type_label,
        )
    elif type_code:
        _ensure_lookup_entry(
            conn,
            "PlaceType",
            '"originalCode"',
            '"englishName"',
            type_code,
            place.get("type", ""),
        )

    # Upsert services
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

    # Upsert activities
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

    # Upsert vehicle type
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

    # Get fresh lookup maps
    type_map, service_map, activity_map = _get_lookup_maps(conn)

    # Insert place (skip if exists)
    try:
        execute_values(
            cur,
            """
            INSERT INTO "Place" (
                id, name, latitude, longitude, "typeId", address,
                rating, "reviewCount", "photoCount", photos, pricing,
                access, contact, descriptions, "isPublic", "onlineBooking",
                "lastFetched"
            ) VALUES %s
            ON CONFLICT (id) DO NOTHING
            """,
            [
                (
                    place["id"],
                    place.get("name") or place.get("title") or "",
                    place["latitude"],
                    place["longitude"],
                    type_map.get(type_code, 1),
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

        # Insert PlaceService junctions
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

        # Insert PlaceActivity junctions
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

    cur.close()


def insert_reviews_for_place(
    conn: psycopg2.extensions.connection,
    reviews: list[dict],
    system_user_id: str | None = None,
) -> int:
    """Insert reviews for a single place into Supabase.

    Returns the number of reviews inserted.
    """
    if not reviews:
        return 0

    cur = conn.cursor()

    # Get system user
    if not system_user_id:
        system_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "scraped-import-system-user"))

    # Get vehicle type mapping
    cur.execute('SELECT id, "originalCode" FROM "VehicleType"')
    vehicle_map = {row[1]: row[0] for row in cur.fetchall()}

    inserted = 0
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
                    r.get("author", {}).get("id", "") if isinstance(r.get("author"), dict) else "",
                    system_user_id,
                    r["place_id"],
                    r.get("created_at") or None,
                )
                for r in reviews
            ],
        )
        conn.commit()
        inserted = len(reviews)
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to insert reviews: {e}")

    cur.close()
    return inserted


def upload_places(conn: psycopg2.extensions.connection, places: list[dict]) -> None:
    """Upload places to Supabase."""
    total = len(places)
    if not total:
        return

    cur = conn.cursor()

    # Get existing place IDs
    cur.execute('SELECT id FROM "Place"')
    existing_ids = {row[0] for row in cur.fetchall()}
    new_places = [p for p in places if p["id"] not in existing_ids]
    skipped = total - len(new_places)

    if skipped:
        logger.info(f"Skipping {skipped} existing places")

    if not new_places:
        logger.info("All places already in database.")
        cur.close()
        return

    # Build type code -> ID mapping
    cur.execute('SELECT id, "originalCode" FROM "PlaceType"')
    type_map = {row[1]: row[0] for row in cur.fetchall()}
    cur.execute('SELECT id, "originalCode" FROM "Service"')
    service_map = {row[1]: row[0] for row in cur.fetchall()}
    cur.execute('SELECT id, "originalCode" FROM "Activity"')
    activity_map = {row[1]: row[0] for row in cur.fetchall()}

    uploaded = 0
    errors = 0

    with create_progress("Uploading places", total=len(new_places)) as progress:
        task = progress.add_task("Uploading places", total=len(new_places))

        for i in range(0, len(new_places), DB_BATCH_SIZE):
            batch = new_places[i : i + DB_BATCH_SIZE]
            try:
                execute_values(
                    cur,
                    """
                    INSERT INTO "Place" (
                        id, name, latitude, longitude, "typeId", address,
                        rating, "reviewCount", "photoCount", photos, pricing,
                        access, contact, descriptions, "isPublic", "onlineBooking",
                        "lastFetched"
                    ) VALUES %s
                    ON CONFLICT (id) DO NOTHING
                    """,
                    [
                        (
                            p["id"],
                            p.get("name") or p.get("title") or "",
                            p["latitude"],
                            p["longitude"],
                            type_map.get(p.get("type_code", ""), 1),
                            json.dumps(p.get("address", {})),
                            p.get("rating"),
                            p.get("review_count", 0),
                            p.get("photo_count", 0),
                            json.dumps(p.get("photos", [])),
                            json.dumps(p.get("pricing", {})),
                            json.dumps(p.get("access", {})),
                            json.dumps(p.get("contact", {})),
                            json.dumps(p.get("descriptions", {})),
                            p.get("is_public", True),
                            p.get("online_booking", False),
                            p.get("scraped_at") or None,
                        )
                        for p in batch
                    ],
                )

                # Insert PlaceService junctions
                for p in batch:
                    for svc in p.get("services", []):
                        if isinstance(svc, dict):
                            svc_id = service_map.get(svc.get("code", ""))
                            if svc_id:
                                cur.execute(
                                    """
                                    INSERT INTO "PlaceService" ("placeId", "serviceId")
                                    VALUES (%s, %s)
                                    ON CONFLICT DO NOTHING
                                    """,
                                    (p["id"], svc_id),
                                )

                # Insert PlaceActivity junctions
                for p in batch:
                    for act in p.get("activities", []):
                        if isinstance(act, dict):
                            act_id = activity_map.get(act.get("code", ""))
                            if act_id:
                                cur.execute(
                                    """
                                    INSERT INTO "PlaceActivity" ("placeId", "activityId")
                                    VALUES (%s, %s)
                                    ON CONFLICT DO NOTHING
                                    """,
                                    (p["id"], act_id),
                                )

                conn.commit()
                uploaded += len(batch)
                progress.update(task, completed=uploaded)
                log_progress("Place upload", uploaded, len(new_places))

            except Exception as e:
                conn.rollback()
                errors += len(batch)
                logger.error(f"Batch error at index {i}: {e}")
                if errors > 5:
                    logger.error("Too many errors, stopping place uploads")
                    break

    cur.close()
    logger.info(f"Places: {uploaded} uploaded, {errors} errors")


def upload_reviews(
    conn: psycopg2.extensions.connection,
    reviews: list[dict],
    system_user_id: str,
) -> None:
    """Upload reviews to Supabase."""
    total = len(reviews)
    if not total:
        return

    cur = conn.cursor()

    # Get vehicle type mapping
    cur.execute('SELECT id, "originalCode" FROM "VehicleType"')
    vehicle_map = {row[1]: row[0] for row in cur.fetchall()}

    uploaded = 0
    errors = 0

    with create_progress("Uploading reviews", total=total) as progress:
        task = progress.add_task("Uploading reviews", total=total)

        for i in range(0, total, DB_BATCH_SIZE):
            batch = reviews[i : i + DB_BATCH_SIZE]
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
                        for r in batch
                    ],
                )
                conn.commit()
                uploaded += len(batch)
                progress.update(task, completed=uploaded)
                log_progress("Review upload", uploaded, total)

            except psycopg2.errors.ForeignKeyViolation:
                conn.rollback()
                logger.warning(f"Skipping batch at {i}: place doesn't exist yet")
            except Exception as e:
                conn.rollback()
                errors += len(batch)
                logger.error(f"Batch error at index {i}: {e}")
                if errors > 5:
                    logger.error("Too many errors, stopping review uploads")
                    break

    cur.close()
    logger.info(f"Reviews: {uploaded} uploaded, {errors} errors")
