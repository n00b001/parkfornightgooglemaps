#!/usr/bin/env python3
"""
Upload scraped images to Google Firestore.

Each image is stored as a base64-encoded string in a Firestore document:
  Collection: images
  Document ID: {place_id}__{filename}
  Fields: data (base64), contentType, size

Usage:
    # Upload all images:
    python scripts/upload-images-to-firestore.py

    # Upload just 10 for testing:
    python scripts/upload-images-to-firestore.py --limit 10

    # Dry run (list files without uploading):
    python scripts/upload-images-to-firestore.py --dry-run

Requires:
    pip install firebase-admin
    server/firebase-credentials.json (service account key)
"""
import argparse
import base64
import os
import sys
import time

# Add scraper to path for config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scraper"))
from config import DATA_DIR
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

IMAGES_DIR = os.path.join(DATA_DIR, "images")
PLACES_IMAGES_DIR = os.path.join(IMAGES_DIR, "places")
ICONS_DIR = os.path.join(IMAGES_DIR, "icons")

CREDENTIALS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "server", "firebase-credentials.json"
)


def init_firestore():
    """Initialize Firebase Admin SDK and return Firestore client."""
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", CREDENTIALS_PATH)
    if not os.path.exists(cred_path):
        print(f"ERROR: Credentials file not found: {cred_path}")
        sys.exit(1)

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    return firestore.client()


def collect_image_files(thumbnails_only=False, large_only=False):
    """Collect all image files to upload."""
    files = []

    # Place photos
    if os.path.exists(PLACES_IMAGES_DIR):
        for root, _, filenames in os.walk(PLACES_IMAGES_DIR):
            for filename in filenames:
                if thumbnails_only and "_large." in filename:
                    continue
                if large_only and "_thumb." in filename:
                    continue

                filepath = os.path.join(root, filename)
                place_id = os.path.basename(root)
                doc_id = f"{place_id}__{filename}"
                content_type = "image/jpeg" if filename.endswith(".jpg") else "image/png"
                files.append((filepath, doc_id, content_type))

    # Vehicle icons
    if os.path.exists(ICONS_DIR):
        for filename in os.listdir(ICONS_DIR):
            if filename.endswith((".png", ".jpg", ".jpeg")):
                filepath = os.path.join(ICONS_DIR, filename)
                doc_id = f"icons__{filename}"
                content_type = "image/png" if filename.endswith(".png") else "image/jpeg"
                files.append((filepath, doc_id, content_type))

    return files


def main():
    parser = argparse.ArgumentParser(description="Upload images to Firestore")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max files to upload (0=all)")
    args = parser.parse_args()

    # Collect files
    print(f"Collecting image files from {IMAGES_DIR}...")
    files = collect_image_files()
    print(f"Found {len(files)} files")

    if args.limit > 0:
        files = files[: args.limit]
        print(f"Limited to {len(files)} files")

    if not files:
        print("No files to upload.")
        return

    total_size = sum(os.path.getsize(fp) for fp, _, _ in files)
    print(f"Total size: {total_size / (1024**2):.1f} MB")

    if args.dry_run:
        print("\nFiles to upload:")
        for fp, doc_id, _ in files:
            size = os.path.getsize(fp)
            print(f"  {doc_id} ({size/1024:.1f} KB)")
        return

    # Initialize Firestore
    print("\nInitializing Firebase...")
    db = init_firestore()

    print("\nUploading to Firestore collection 'images'...")

    uploaded = 0
    errors = 0
    start_time = time.time()

    for i, (filepath, doc_id, content_type) in enumerate(files, 1):
        try:
            size = os.path.getsize(filepath)

            if size > 1_000_000:
                print(f"  SKIP (too large): {doc_id}")
                continue

            with open(filepath, "rb") as f:
                data = f.read()

            base64_data = base64.b64encode(data).decode("ascii")

            db.collection("images").document(doc_id).set({
                "data": base64_data,
                "contentType": content_type,
                "size": size,
                "uploadedAt": SERVER_TIMESTAMP,
            })
            uploaded += 1

        except Exception as e:
            errors += 1
            print(f"  ERROR {doc_id}: {e}")

        if i % 1000 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(files) - i) / rate if rate > 0 else 0
            print(f"  Progress: {i}/{len(files)} ({rate:.0f}/sec, ETA: {eta/60:.1f} min)")

    elapsed = time.time() - start_time
    print(f"\nDone: {uploaded} uploaded, {errors} errors in {elapsed:.0f}s")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
