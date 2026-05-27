#!/usr/bin/env node
/**
 * Seed script: upload images to Firebase Storage and store metadata in Firestore.
 * Run during deployment (render.yaml build step), after seedPlaces.js.
 *
 * - Uploads each image to Firebase Storage: places/{place_id}/{filename}
 * - Stores metadata in Firestore 'images' collection (URL, size, type)
 * - Updates photo URLs in places data
 *
 * Usage: node src/services/seedImages.js
 */
require("dotenv").config();

const fs = require("fs");
const path = require("path");
const admin = require("firebase-admin");

const DATA_DIR = path.join(__dirname, "..", "..", "..", "scripts", "data");
const IMAGES_DIR = path.join(DATA_DIR, "images");
const PLACES_IMAGES_DIR = path.join(IMAGES_DIR, "places");
const ICONS_DIR = path.join(IMAGES_DIR, "icons");

// Initialize Firebase Admin
function initFirebase() {
  if (admin.apps.length === 0) {
    const credPath = process.env.FIREBASE_CREDENTIALS
      ? path.resolve(process.cwd(), process.env.FIREBASE_CREDENTIALS)
      : path.join(__dirname, "..", "..", "firebase-credentials.json");

    if (!fs.existsSync(credPath)) {
      console.warn("Firebase credentials not found, skipping image seed.");
      return null;
    }

    admin.initializeApp({
      credential: admin.credential.cert(require(credPath)),
      storageBucket: "park4night-ff117.appspot.com",
    });
  }
  return admin;
}

async function uploadImageToStorage(filepath, storagePath) {
  /** Upload a file to Firebase Storage. Returns the public URL. */
  const bucket = admin.storage().bucket();
  const file = bucket.file(storagePath);

  await file.save(fs.readFileSync(filepath), {
    metadata: {
      contentType: getFileContentType(filepath),
    },
    predefinedAcl: "publicRead",
  });

  // Generate public URL
  const url = `https://storage.googleapis.com/${bucket.name}/${encodeURIComponent(storagePath)}`;
  return url;
}

function getFileContentType(filepath) {
  if (filepath.endsWith(".jpg") || filepath.endsWith(".jpeg")) return "image/jpeg";
  if (filepath.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

async function storeImageMetadataInFirestore(placeId, filename, storageUrl, size, type) {
  /** Store image metadata in Firestore 'images' collection. */
  const db = admin.firestore();
  const docId = `${placeId}__${filename}`;

  await db.collection("images").doc(docId).set({
    placeId: parseInt(placeId) || placeId,
    filename,
    storageUrl,
    size,
    type, // 'thumb' | 'large' | 'icon'
    uploadedAt: admin.firestore.FieldValue.serverTimestamp(),
  });
}

async function seedPlaceImages() {
  /** Upload all place images to Firebase Storage and store metadata in Firestore. */
  if (!fs.existsSync(PLACES_IMAGES_DIR)) {
    console.log("No place images directory found, skipping.");
    return { uploaded: 0, failed: 0 };
  }

  const placeDirs = fs
    .readdirSync(PLACES_IMAGES_DIR)
    .filter((d) =>
      fs.statSync(path.join(PLACES_IMAGES_DIR, d)).isDirectory()
    );

  console.log(`Found ${placeDirs.length} places with images...`);

  let uploaded = 0;
  let failed = 0;
  const BATCH_LOG = 1000;

  for (let i = 0; i < placeDirs.length; i++) {
    const placeId = placeDirs[i];
    const placeImgDir = path.join(PLACES_IMAGES_DIR, placeId);
    const files = fs.readdirSync(placeImgDir);

    for (const filename of files) {
      try {
        const filepath = path.join(placeImgDir, filename);
        const stat = fs.statSync(filepath);

        // Determine type
        let type = "large";
        if (filename.includes("_thumb")) type = "thumb";
        else if (filename.includes("_large")) type = "large";

        // Storage path: places/{place_id}/{filename}
        const storagePath = `places/${placeId}/${filename}`;

        // Upload to Firebase Storage
        const storageUrl = await uploadImageToStorage(filepath, storagePath);

        // Store metadata in Firestore
        await storeImageMetadataInFirestore(
          placeId,
          filename,
          storageUrl,
          stat.size,
          type
        );

        uploaded++;
      } catch (err) {
        failed++;
        if (failed <= 5) {
          console.error(
            `Failed to upload ${placeId}/${filename}:`,
            err.message
          );
        }
      }

      if ((uploaded + failed) % BATCH_LOG === 0) {
        console.log(
          `  Uploaded ${uploaded}, failed ${failed} ` +
            `(${((i / placeDirs.length) * 100).toFixed(1)}% places)`
        );
      }
    }
  }

  console.log(
    `Place images complete: ${uploaded} uploaded, ${failed} failed.`
  );
  return { uploaded, failed };
}

async function seedIcons() {
  /** Upload vehicle icons to Firebase Storage. */
  if (!fs.existsSync(ICONS_DIR)) {
    console.log("No icons directory found, skipping.");
    return { uploaded: 0, failed: 0 };
  }

  const files = fs
    .readdirSync(ICONS_DIR)
    .filter((f) => f.endsWith(".png") || f.endsWith(".jpg"));

  console.log(`Uploading ${files.length} vehicle icons...`);

  let uploaded = 0;
  let failed = 0;

  for (const filename of files) {
    try {
      const filepath = path.join(ICONS_DIR, filename);
      const stat = fs.statSync(filepath);
      const storagePath = `icons/${filename}`;

      const storageUrl = await uploadImageToStorage(filepath, storagePath);

      await storeImageMetadataInFirestore(
        "icons",
        filename,
        storageUrl,
        stat.size,
        "icon"
      );

      uploaded++;
    } catch (err) {
      failed++;
      console.error(`Failed to upload icon ${filename}:`, err.message);
    }
  }

  console.log(`Icons complete: ${uploaded} uploaded, ${failed} failed.`);
  return { uploaded, failed };
}

async function main() {
  console.log("Starting image seed...");

  const firebase = initFirebase();
  if (!firebase) {
    console.log("Firebase not initialized, skipping image seed.");
    return;
  }

  const placeResult = await seedPlaceImages();
  const iconResult = await seedIcons();

  const totalUploaded =
    placeResult.uploaded + iconResult.uploaded;
  const totalFailed = placeResult.failed + iconResult.failed;

  console.log(
    `\nImage seed complete: ${totalUploaded} uploaded, ${totalFailed} failed.`
  );

  if (totalFailed > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Image seed failed:", err);
  process.exit(1);
});
