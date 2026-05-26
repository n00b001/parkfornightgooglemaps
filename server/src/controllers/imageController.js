/**
 * Image controller: serve images from Firestore.
 *
 * Routes:
 *   GET /images/:placeId/:filename  - Place photos (thumb or large)
 *   GET /images/icons/:filename     - Vehicle type icons
 */
const { getDb } = require("../config/firebase");

/**
 * Build the Firestore document ID from route params.
 * e.g., placeId=346250, filename=1010320_thumb.jpg -> "346250__1010320_thumb.jpg"
 */
function buildDocId(placeId, filename) {
	return `${placeId}__${filename}`;
}

/**
 * Serve a place image from Firestore.
 * GET /images/:placeId/:filename
 */
async function getPlaceImage(req, res) {
	const { placeId, filename } = req.params;

	if (!placeId || !filename) {
		return res.status(400).json({ error: "Missing placeId or filename" });
	}

	try {
		const db = getDb();
		const docId = buildDocId(placeId, filename);
		const doc = await db.collection("images").doc(docId).get();

		if (!doc.exists) {
			return res.status(404).json({ error: "Image not found" });
		}

		const data = doc.data();
		const base64Data = data.data;
		const contentType = data.contentType || "image/jpeg";

		if (!base64Data) {
			return res.status(500).json({ error: "Image data missing" });
		}

		// Convert base64 to binary
		const buffer = Buffer.from(base64Data, "base64");

		res.setHeader("Content-Type", contentType);
		res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
		res.setHeader("Content-Length", buffer.length);
		res.send(buffer);
	} catch (error) {
		console.error(
			`Error fetching image ${placeId}/${filename}:`,
			error.message,
		);
		res.status(500).json({ error: "Failed to fetch image" });
	}
}

/**
 * Serve a vehicle icon from Firestore.
 * GET /images/icons/:filename
 */
async function getIcon(req, res) {
	const { filename } = req.params;

	if (!filename) {
		return res.status(400).json({ error: "Missing filename" });
	}

	try {
		const db = getDb();
		const docId = `icons__${filename}`;
		const doc = await db.collection("images").doc(docId).get();

		if (!doc.exists) {
			return res.status(404).json({ error: "Icon not found" });
		}

		const data = doc.data();
		const base64Data = data.data;
		const contentType = data.contentType || "image/png";

		if (!base64Data) {
			return res.status(500).json({ error: "Icon data missing" });
		}

		const buffer = Buffer.from(base64Data, "base64");

		res.setHeader("Content-Type", contentType);
		res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
		res.setHeader("Content-Length", buffer.length);
		res.send(buffer);
	} catch (error) {
		console.error(`Error fetching icon ${filename}:`, error.message);
		res.status(500).json({ error: "Failed to fetch icon" });
	}
}

module.exports = { getPlaceImage, getIcon };
