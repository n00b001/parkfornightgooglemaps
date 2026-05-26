#!/usr/bin/env node
/**
 * One-time seed script: import scraped JSON data into the Prisma database.
 * Run during deployment (render.yaml build step), not on every server start.
 *
 * Usage: node src/services/seedPlaces.js
 */
require("dotenv").config();

const fs = require("fs");
const path = require("path");
const prisma = require("../config/db");

const DATA_DIR = path.join(__dirname, "..", "..", "..", "scripts", "data");

async function seed() {
	const placesFile = path.join(DATA_DIR, "places_export.json");

	if (!fs.existsSync(placesFile)) {
		console.log("No places_export.json found, skipping seed.");
		return;
	}

	let raw;
	try {
		raw = fs.readFileSync(placesFile, "utf-8");
	} catch (err) {
		console.error("Failed to read places file:", err.message);
		process.exit(1);
	}

	let places;
	try {
		places = JSON.parse(raw);
	} catch (err) {
		console.warn(
			`places_export.json is not valid JSON (may be Git LFS pointer): ${err.message}`,
		);
		console.log("Skipping seed.");
		return;
	}

	if (!Array.isArray(places) || !places.length) {
		console.log("No places to seed.");
		return;
	}

	console.log(`Seeding ${places.length} places...`);

	const BATCH = 500;
	for (let i = 0; i < places.length; i += BATCH) {
		const batch = places.slice(i, i + BATCH);
		const upserts = batch.map((p) =>
			prisma.place.upsert({
				where: { id: p.id },
				update: {
					name: p.name || p.title || "",
					latitude: p.latitude,
					longitude: p.longitude,
					type: p.type?.code || p.type || "",
					description: p.description,
					address:
						typeof p.address === "object"
							? [
									p.address.street,
									p.address.city,
									p.address.zipcode,
									p.address.country,
								]
									.filter(Boolean)
									.join(", ")
							: p.address,
					rating: p.rating,
					reviewCount: p.review_count || 0,
					photoCount: p.photo_count || 0,
					photos: p.photos || [],
					rawData: p,
					lastFetched: new Date(),
				},
				create: {
					id: p.id,
					name: p.name || p.title || "",
					latitude: p.latitude,
					longitude: p.longitude,
					type: p.type?.code || p.type || "",
					description: p.description,
					address:
						typeof p.address === "object"
							? [
									p.address.street,
									p.address.city,
									p.address.zipcode,
									p.address.country,
								]
									.filter(Boolean)
									.join(", ")
							: p.address,
					rating: p.rating,
					reviewCount: p.review_count || 0,
					photoCount: p.photo_count || 0,
					photos: p.photos || [],
					rawData: p,
					lastFetched: new Date(),
				},
			}),
		);

		await Promise.allSettled(upserts);
		console.log(`  Seeded ${Math.min(i + BATCH, places.length)}/${places.length}`);
	}

	console.log("Seeding complete.");
}

seed()
	.catch((err) => {
		console.error("Seed failed:", err.message);
		process.exit(1);
	})
	.finally(async () => {
		await prisma.$disconnect();
	});
