/**
 * Firebase Admin SDK initialization.
 * Used to store and retrieve place images in Firestore.
 */
const admin = require("firebase-admin");

let db;

function initFirebase() {
	if (db) return db;

	const credentialsPath =
		process.env.FIREBASE_CREDENTIALS || "./firebase-credentials.json";
	const fs = require("fs");
	const path = require("path");

	let credPath = credentialsPath;
	if (!path.isAbsolute(credPath)) {
		credPath = path.join(__dirname, "..", "..", credPath);
	}

	if (!fs.existsSync(credPath)) {
		console.error(`FATAL: Firebase credentials not found: ${credPath}`);
		process.exit(1);
	}

	const serviceAccount = JSON.parse(fs.readFileSync(credPath, "utf-8"));

	admin.initializeApp({
		credential: admin.credential.cert(serviceAccount),
	});

	db = admin.firestore();
	console.log(`Firebase initialized for project: ${serviceAccount.project_id}`);
	return db;
}

function getDb() {
	if (!db) {
		initFirebase();
	}
	return db;
}

module.exports = { initFirebase, getDb };
