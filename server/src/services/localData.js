const fs = require("fs");
const path = require("path");
const prisma = require("../config/db");

// Path to scraped data files
const DATA_DIR = path.join(__dirname, "..", "..", "..", "scripts", "scraper", "data");

let loaded = false;

/**
 * Seed database from scraped JSON files if they exist.
 * Called on startup.
 */
async function loadData() {
	if (loaded) return;

	console.log("Checking for local scraped data to seed...");

	const placesFile = path.join(DATA_DIR, "places_export.json");
	if (fs.existsSync(placesFile)) {
		try {
			const raw = fs.readFileSync(placesFile, "utf-8");
			const places = JSON.parse(raw);
			console.log(`Found ${places.length} places in local data. Seeding...`);

			const upsertPromises = places.map(p => {
				const data = {
					id: p.id,
					name: p.name || p.title || "",
					latitude: p.latitude,
					longitude: p.longitude,
					type: p.type?.code || p.type || "",
					description: p.description,
					address: typeof p.address === 'object' ?
						[p.address.street, p.address.city, p.address.zipcode, p.address.country].filter(Boolean).join(", ") :
						p.address,
					rating: p.rating,
					reviewCount: p.review_count || 0,
					photoCount: p.photo_count || 0,
					photos: p.photos || [],
					rawData: p,
					lastFetched: new Date()
				};
				return prisma.place.upsert({
					where: { id: p.id },
					update: data,
					create: data
				});
			});

			await Promise.allSettled(upsertPromises);
			console.log("Seeding complete.");
		} catch (err) {
			console.error("Failed to seed places:", err.message);
		}
	} else {
		console.log("No local places_export.json found for seeding.");
	}

	loaded = true;
}

module.exports = {
	loadData
};
