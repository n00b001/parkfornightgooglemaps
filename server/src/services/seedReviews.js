#!/usr/bin/env node
/**
 * One-time seed script: import scraped reviews into the Prisma database.
 * Run during deployment (render.yaml build step), after seedPlaces.js.
 *
 * Usage: node src/services/seedReviews.js
 */
require("dotenv").config();

const fs = require("fs");
const path = require("path");
const prisma = require("../config/db");

const DATA_DIR = path.join(__dirname, "..", "..", "..", "scripts", "data");

/**
 * Map Park4Night vehicle type codes to English.
 */
const VEHICLE_TYPE_MAP = {
	NC: "caravan", // Caravane
	GV: "motorhome", // Grand véhicule / Camping-car
	UL: "ultralight", // Ultraléger
	V: "vehicle", // Véhicule standard
	M: "motorcycle", // Moto
	T: "tent", // Tente
	P: "car", // Voiture
	I: "unknown", // Inconnu
};

async function seed() {
	const reviewsFile = path.join(DATA_DIR, "reviews_export.json");

	if (!fs.existsSync(reviewsFile)) {
		console.log("No reviews_export.json found, skipping seed.");
		return;
	}

	// Quick check: is this a Git LFS pointer?
	const firstBytes = fs
		.readFileSync(reviewsFile, {
			encoding: "utf-8",
			flag: "r",
		})
		.slice(0, 100);
	if (firstBytes.startsWith("version https://git-lfs")) {
		console.warn(
			"reviews_export.json is a Git LFS pointer — run `git lfs pull` before seeding.",
		);
		console.log("Skipping seed.");
		return;
	}

	let reviews;
	try {
		const raw = fs.readFileSync(reviewsFile, "utf-8");
		reviews = JSON.parse(raw);
	} catch (err) {
		console.error("Failed to parse reviews file:", err.message);
		process.exit(1);
	}

	if (!Array.isArray(reviews) || !reviews.length) {
		console.log("No reviews to seed.");
		return;
	}

	console.log(`Seeding ${reviews.length} reviews...`);

	// Create a system "scraper" user for imported reviews
	let scraperUser;
	try {
		scraperUser = await prisma.user.upsert({
			where: { googleId: "scraper-import" },
			update: {},
			create: {
				googleId: "scraper-import",
				email: "scraper@park4night-import.local",
				name: "Park4Night Import",
			},
		});
	} catch (err) {
		console.error("Failed to create scraper user:", err.message);
		process.exit(1);
	}

	const BATCH = 500;
	let totalCreated = 0;
	let totalSkipped = 0;

	for (let i = 0; i < reviews.length; i += BATCH) {
		const batch = reviews.slice(i, i + BATCH);

		for (const review of batch) {
			try {
				// Normalize vehicle type
				const rawVehicleType =
					review.vehicle_type || review.vehicleType || "unknown";
				const vehicleType = VEHICLE_TYPE_MAP[rawVehicleType] || rawVehicleType;

				// Get content from various field names
				const content = review.text || review.texte || review.content || "";

				// Skip empty reviews
				if (!content.trim()) {
					totalSkipped++;
					continue;
				}

				await prisma.review.create({
					data: {
						content,
						rating: parseInt(review.rating || review.note || "0"),
						vehicleType,
						authorName: review.author || review.auteur || null,
						authorId: String(review.author_id || review.authorId || ""),
						userId: scraperUser.id, // All imported reviews belong to scraper user
						placeId: parseInt(review.place_id || review.placeId || "0"),
						createdAt: review.created_at
							? new Date(review.created_at)
							: new Date(),
					},
				});
				totalCreated++;
			} catch (err) {
				// Skip reviews for places that don't exist in DB
				if (!err.message.includes("Foreign key constraint")) {
					console.error(`Failed to seed review ${review.id}:`, err.message);
				}
				totalSkipped++;
			}
		}

		console.log(
			`  Seeded ${Math.min(i + BATCH, reviews.length)}/${reviews.length} ` +
				`(${totalCreated} created, ${totalSkipped} skipped)`,
		);
	}

	console.log(
		`Seeding complete: ${totalCreated} reviews created, ${totalSkipped} skipped.`,
	);
}

seed()
	.catch((err) => {
		console.error("Seed failed:", err.message);
		process.exit(1);
	})
	.finally(async () => {
		await prisma.$disconnect();
	});
