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
const { normalizePlace } = require("./normalization");

const DATA_DIR = path.join(__dirname, "..", "..", "..", "scripts", "data");

async function seed() {
	const placesFile = path.join(DATA_DIR, "places_export.json");

	if (!fs.existsSync(placesFile)) {
		console.log("No places_export.json found, skipping seed.");
		return;
	}

	// Quick check: is this a Git LFS pointer?
	const firstBytes = fs.readFileSync(placesFile, {
		encoding: "utf-8",
		flag: "r",
	}).slice(0, 100);
	if (firstBytes.startsWith("version https://git-lfs")) {
		console.warn(
			"places_export.json is a Git LFS pointer — run `git lfs pull` before seeding.",
		);
		console.log("Skipping seed.");
		return;
	}

	let places;
	try {
		const raw = fs.readFileSync(placesFile, "utf-8");
		places = JSON.parse(raw);
	} catch (err) {
		console.error("Failed to parse places file:", err.message);
		process.exit(1);
	}

	if (!Array.isArray(places) || !places.length) {
		console.log("No places to seed.");
		return;
	}

	console.log(`Seeding ${places.length} places...`);

	const BATCH = 500;
	for (let i = 0; i < places.length; i += BATCH) {
		const batch = places.slice(i, i + BATCH);
		const upserts = batch.map((p) => {
			const normalized = normalizePlace(p);
			return prisma.place.upsert({
				where: { id: normalized.id },
				update: normalized,
				create: normalized,
			});
		});

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
