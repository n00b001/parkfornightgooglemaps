const fs = require("fs");
const path = require("path");

// Path to scraped data files
const DATA_DIR = path.join(__dirname, "..", "..", "..", "scripts", "data");

let places = null;
let reviewsByPlace = null;
let loaded = false;

/**
 * Load scraped data from JSON files.
 * Called once on startup.
 */
function loadData() {
	if (loaded) return;

	console.log("Loading local scraped data...");

	// Load places
	const placesFile = path.join(DATA_DIR, "places_export.json");
	if (fs.existsSync(placesFile)) {
		const raw = fs.readFileSync(placesFile, "utf-8");
		places = JSON.parse(raw);
		console.log(`Loaded ${places.length} places from local data`);
	} else {
		console.warn(`Places file not found: ${placesFile}`);
		places = [];
	}

	// Load reviews and index by place_id
	const reviewsFile = path.join(DATA_DIR, "reviews_export.json");
	if (fs.existsSync(reviewsFile)) {
		const raw = fs.readFileSync(reviewsFile, "utf-8");
		const allReviews = JSON.parse(raw);
		console.log(`Loaded ${allReviews.length} reviews from local data`);

		// Index reviews by place_id for fast lookup
		reviewsByPlace = new Map();
		for (const review of allReviews) {
			const pid = review.place_id;
			if (!reviewsByPlace.has(pid)) {
				reviewsByPlace.set(pid, []);
			}
			reviewsByPlace.get(pid).push(review);
		}
		console.log(`Reviews indexed for ${reviewsByPlace.size} places`);
	} else {
		console.warn(`Reviews file not found: ${reviewsFile}`);
		reviewsByPlace = new Map();
	}

	loaded = true;
}

/**
 * Get all places (with optional filtering).
 */
function getAllPlaces(options = {}) {
	if (!loaded) loadData();

	let result = places || [];

	// Filter by type
	if (options.type) {
		result = result.filter(
			(p) => p.type?.code === options.type || p.type === options.type,
		);
	}

	// Filter by minimum rating
	if (options.minRating) {
		result = result.filter(
			(p) => (p.rating || 0) >= parseFloat(options.minRating),
		);
	}

	// Filter by bounding box
	if (options.lat && options.lng) {
		const lat = parseFloat(options.lat);
		const lng = parseFloat(options.lng);
		const range = options.range || 0.5;
		result = result.filter(
			(p) =>
				p.latitude >= lat - range &&
				p.latitude <= lat + range &&
				p.longitude >= lng - range &&
				p.longitude <= lng + range,
		);
	}

	// Sort by rating
	if (options.sortBy === "rating") {
		result = [...result].sort((a, b) => (b.rating || 0) - (a.rating || 0));
	}

	// Sort by distance
	if (options.sortBy === "distance" && options.lat && options.lng) {
		const lat = parseFloat(options.lat);
		const lng = parseFloat(options.lng);
		result = [...result].sort((a, b) => {
			const distA =
				Math.pow(a.latitude - lat, 2) + Math.pow(a.longitude - lng, 2);
			const distB =
				Math.pow(b.latitude - lat, 2) + Math.pow(b.longitude - lng, 2);
			return distA - distB;
		});
	}

	return result;
}

/**
 * Get a single place by ID.
 */
function getPlaceById(id) {
	if (!loaded) loadData();
	const numId = typeof id === "string" ? parseInt(id, 10) : id;
	return places?.find((p) => p.id === numId) || null;
}

/**
 * Get reviews for a place.
 */
function getPlaceReviews(placeId) {
	if (!loaded) loadData();
	const numId = typeof placeId === "string" ? parseInt(placeId, 10) : placeId;
	return reviewsByPlace?.get(numId) || [];
}

/**
 * Get total statistics.
 */
function getStats() {
	if (!loaded) loadData();
	return {
		totalPlaces: places?.length || 0,
		totalReviews: reviewsByPlace
			? [...reviewsByPlace.values()].reduce((sum, r) => sum + r.length, 0)
			: 0,
		placesWithReviews: reviewsByPlace?.size || 0,
	};
}

module.exports = {
	loadData,
	getAllPlaces,
	getPlaceById,
	getPlaceReviews,
	getStats,
};
