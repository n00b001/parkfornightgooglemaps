#!/usr/bin/env python3
"""
Upload all images to Firebase Storage and update places_export.json with URLs.

This script:
  1. Reads each image from scripts/data/images/places/{place_id}/
  2. Uploads to Firebase Storage: places/{place_id}/{filename}
  3. Gets the public download URL
  4. Stores image metadata in Firestore (placeId, filename, storageUrl, size, type)
  5. Updates places_export.json photos[] with firebaseStorageUrl field
  6. Saves updated places_export.json

Run locally (where images exist), NOT during CI/CD.
After running, commit the updated places_export.json via Git LFS.

Usage:
    python scripts/upload-images-and-update-exports.py

Requires:
    pip install firebase-admin
    server/firebase-credentials.json
"""

from __future__ import annotations

import json
import os
import sys
import time

import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Add scraper to path for config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scraper"))
from config import DATA_DIR

IMAGES_DIR = os.path.join(DATA_DIR, "images")
PLACES_IMAGES_DIR = os.path.join(IMAGES_DIR, "places")
ICONS_DIR = os.path.join(IMAGES_DIR, "icons")
PLACES_EXPORT = os.path.join(DATA_DIR, "places_export.json")

CREDENTIALS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "server", "firebase-credentials.json"
)

BUCKET_NAME = "park4night-ff117.appspot.com"

# Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def ts():
    return time.strftime("%H:%M:%S")


def log(msg: str, color: str = ""):
    print(f"{color}{ts()} {msg}{RESET}", flush=True)


def progress_bar(current: int, total: int, width: int = 30) -> str:
    pct = min(current / total, 1.0) if total > 0 else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {current:>8}/{total} ({pct * 100:5.1f}%)"


def init_firebase():
    """Initialize Firebase Admin SDK."""
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", CREDENTIALS_PATH)
    cred = credentials.Certificate(cred_path)

    options = {"projectId": "park4night-ff117", "storageBucket": BUCKET_NAME}
    firebase_admin.initialize_app(cred, options)

    db = firestore.client()
    bucket = storage.bucket()
    return db, bucket


def upload_image(bucket, filepath: str, storage_path: str) -> str:
    """Upload a file to Firebase Storage. Returns public URL."""
    blob = bucket.blob(storage_path)

    content_type = "image/jpeg" if filepath.endswith(".jpg") else "image/png"
    blob.content_type = content_type

    blob.upload_from_filename(filepath)
    blob.make_public()

    return blob.public_url


def get_existing_image_ids(db) -> set[str]:
    """Get existing image document IDs from Firestore."""
    log("Checking existing images in Firestore...", DIM)
    existing = set()
    for doc in db.collection("images").stream():
        existing.add(doc.id)
    log(f"  Found {len(existing):,} existing image records.", GREEN)
    return existing


def upload_all_images(db, bucket):
    """Upload all place images and icons. Returns dict of place_id -> {filename: url}."""
    image_urls = {}  # place_id -> {filename: url}
    existing_ids = get_existing_image_ids(db)

    # Collect all files
    all_files = []

    if os.path.exists(PLACES_IMAGES_DIR):
        for root, _, filenames in os.walk(PLACES_IMAGES_DIR):
            place_id = os.path.basename(root)
            for filename in sorted(filenames):
                filepath = os.path.join(root, filename)
                storage_path = f"places/{place_id}/{filename}"
                doc_id = f"{place_id}__{filename}"
                img_type = "thumb" if "_thumb." in filename else "large"
                all_files.append((filepath, storage_path, doc_id, place_id, filename, img_type))

    if os.path.exists(ICONS_DIR):
        for filename in sorted(os.listdir(ICONS_DIR)):
            if filename.endswith((".png", ".jpg", ".jpeg")):
                filepath = os.path.join(ICONS_DIR, filename)
                storage_path = f"icons/{filename}"
                doc_id = f"icons__{filename}"
                all_files.append((filepath, storage_path, doc_id, "icons", filename, "icon"))

    total = len(all_files)
    to_upload = [(fp, sp, did, pid, fn, it) for fp, sp, did, pid, fn, it in all_files if did not in existing_ids]
    skipped = total - len(to_upload)

    if skipped:
        log(f"  Skipping {skipped:,} already uploaded.", YELLOW)

    if not to_upload:
        log("  All images already uploaded!", GREEN)
        # Still build image_urls from existing
        return image_urls

    log(f"Uploading {BOLD}{len(to_upload):,}{RESET} images to Firebase Storage", GREEN)

    start_time = time.time()
    uploaded = 0
    errors = 0

    for filepath, storage_path, doc_id, place_id, filename, img_type in to_upload:
        try:
            size = os.path.getsize(filepath)

            # Upload to Storage
            public_url = upload_image(bucket, filepath, storage_path)

            # Store metadata in Firestore
            db.collection("images").document(doc_id).set({
                "placeId": int(place_id) if place_id != "icons" else place_id,
                "filename": filename,
                "storageUrl": public_url,
                "size": size,
                "type": img_type,
                "uploadedAt": SERVER_TIMESTAMP,
            })

            # Track URL for places_export update
            if place_id not in image_urls:
                image_urls[place_id] = {}
            image_urls[place_id][filename] = public_url

            uploaded += 1

        except Exception as e:
            errors += 1
            if errors <= 3:
                log(f"  {RED}✗ ERROR {doc_id}: {e}{RESET}", RED)

        processed = uploaded + errors
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (len(to_upload) - processed) / rate if rate > 0 else 0
        eta_str = f"{eta / 3600:.1f}h" if eta > 1800 else f"{eta / 60:.1f}m"

        bar = progress_bar(processed, len(to_upload))
        print(f"\r  {bar} | {rate:.0f}/s ETA {eta_str}", end="", flush=True)

    elapsed = time.time() - start_time
    log(
        f"\n  {GREEN}✓{RESET} {uploaded:,} uploaded, {errors} errors in {elapsed / 60:.1f}m",
        GREEN if errors == 0 else RED,
    )

    return image_urls


def update_places_export(image_urls: dict):
    """Update places_export.json with Firebase Storage URLs."""
    log(f"\nLoading {PLACES_EXPORT}...", DIM)
    with open(PLACES_EXPORT, encoding="utf-8") as f:
        places = json.load(f)

    updated_count = 0
    url_count = 0

    for place in places:
        place_id = str(place["id"])
        photos = place.get("photos", [])
        place_image_urls = image_urls.get(place_id, {})

        for photo in photos:
            photo_id = photo.get("id", "")
            # Find matching image URLs
            if f"{photo_id}_thumb.jpg" in place_image_urls:
                photo["firebaseStorageUrlThumb"] = place_image_urls[f"{photo_id}_thumb.jpg"]
                url_count += 1
            if f"{photo_id}_large.jpg" in place_image_urls:
                photo["firebaseStorageUrlLarge"] = place_image_urls[f"{photo_id}_large.jpg"]
                url_count += 1

        if url_count > 0:
            updated_count += 1

    # Save updated export
    log("Saving updated places_export.json...", DIM)
    with open(PLACES_EXPORT, "w", encoding="utf-8") as f:
        json.dump(places, f, ensure_ascii=False)

    file_size = os.path.getsize(PLACES_EXPORT)
    log(
        f"  Updated {updated_count:,} places with {url_count:,} Firebase Storage URLs "
        f"({file_size / 1024 / 1024:.1f} MB)",
        GREEN,
    )


def main():
    log("Initializing Firebase...", GREEN)
    db, bucket = init_firebase()
    log("Connected to Firebase.", GREEN)

    log("\n=== Uploading images ===", BOLD)
    image_urls = upload_all_images(db, bucket)

    if not image_urls:
        log("No new images uploaded. Checking if export needs updating...", YELLOW)
        # Even if no new uploads, we might need to build URLs from existing Firestore records
        for doc in db.collection("images").stream():
            data = doc.to_dict() or {}
            place_id = str(data.get("placeId", ""))
            filename = data.get("filename", "")
            url = data.get("storageUrl", "")
            if place_id and filename and url:
                if place_id not in image_urls:
                    image_urls[place_id] = {}
                image_urls[place_id][filename] = url

    if image_urls:
        log("\n=== Updating places_export.json ===", BOLD)
        update_places_export(image_urls)
    else:
        log("No image URLs to update.", YELLOW)

    log("\n=== Done! Next steps: ===", BOLD + GREEN)
    log("1. git add -f scripts/data/places_export.json", CYAN)
    log("2. git commit -m 'feat: add Firebase Storage URLs to places'", CYAN)
    log("3. git push (LFS will handle large file)", CYAN)


if __name__ == "__main__":
    main()
