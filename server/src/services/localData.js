const fs = require("fs");
const path = require("path");

// Path to scraped data files
const DATA_DIR = path.join(__dirname, "..", "..", "..", "scripts", "data");

let places = null;
let reviewsByPlace = null;
let loaded = false;

/**
 * Map Park4Night type codes to client-expected code_type values.
 */
const TYPE_CODE_MAP = {
	APN: "cc", // Aire de camping-car → cc
	P: "p", // Parking area → p
	PN: "nature", // Parking naturel → nature
	PJ: "cp", // Aire de jeu → cp (camping place)
	C: "cp", // Camping → cp
	ACC_G: "cc", // Aire gratuite → cc
	DS: "p", // Dépannage → p
	AR: "p", // Aire de repos → p
	PSS: "p", // Parking sur site → p
	ASS: "p", // Aire service → p
	ACC_PR: "p_prive", // Accès privé → p_prive
	ACC_P: "p", // Accès payant → p
	F: "ferme", // Fermé → ferme
	OR: "p", // Aire de repos officielle → p
	EP: "p", // Espace de parking → p
};

/**
 * Map Park4Night service codes to client amenity keys.
 */
const SERVICE_AMENITY_MAP = {
	point_eau: "point_eau",
	eau: "point_eau",
	electricite: "electricite",
	électricité: "electricite",
	poubelle: "poubelle",
	wifi: "wifi",
	vidange_eaux_usees: "vidange_eaux_usees",
	vidance_eaux_grises: "vidange_eaux_usees",
	vidange_wc: "vidange_wc",
	vidange_chasse: "vidange_wc",
	douche: "douche",
	baignade: "baignade",
};

/**
 * Load scraped data from JSON files into memory.
 * Called once on startup (synchronous, non-blocking).
 */
function loadData() {
	if (loaded) return;

	console.log("Loading local scraped data...");

	// Load places
	const placesFile = path.join(DATA_DIR, "places_export.json");
	if (fs.existsSync(placesFile)) {
		try {
			const raw = fs.readFileSync(placesFile, "utf-8");
			places = JSON.parse(raw);
			console.log(`Loaded ${places.length} places from local data`);
		} catch (error) {
			console.warn(
				`Failed to parse places file (may be Git LFS pointer): ${error.message}`,
			);
			places = [];
		}
	} else {
		console.warn(`Places file not found: ${placesFile}`);
		places = [];
	}

	// Load reviews and index by place_id
	const reviewsFile = path.join(DATA_DIR, "reviews_export.json");
	if (fs.existsSync(reviewsFile)) {
		try {
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
		} catch (error) {
			console.warn(
				`Failed to parse reviews file (may be Git LFS pointer): ${error.message}`,
			);
			reviewsByPlace = new Map();
		}
	} else {
		console.warn(`Reviews file not found: ${reviewsFile}`);
		reviewsByPlace = new Map();
	}

	loaded = true;
}

/**
 * Normalize a place object to match client-expected field names.
 */
function normalizePlace(place) {
	if (!place) return place;

	// Build address string from address object
	const addr = place.address || {};
	const adresse = [addr.street, addr.city, addr.zipcode, addr.country]
		.filter(Boolean)
		.join(", ");

	// Map type code
	const rawTypeCode =
		typeof place.type === "object" ? place.type.code : place.type;
	const code_type = TYPE_CODE_MAP[rawTypeCode] || "p";

	// Map services array to amenity boolean fields
	const amenities = {};
	if (Array.isArray(place.services)) {
		for (const service of place.services) {
			const code = service.code || service;
			const mappedKey = SERVICE_AMENITY_MAP[code];
			if (mappedKey) {
				amenities[mappedKey] = "1";
			}
		}
	}

	// Map photos
	const photos = Array.isArray(place.photos)
		? place.photos.map((p) => ({
				...p,
				lien_mini: p.url_thumb || p.lien_mini,
				lien_grand: p.url_large || p.lien_grand,
			}))
		: [];

	return {
		...place,
		// Client-expected field aliases
		titre: place.title || place.titre,
		adresse: adresse || place.adresse,
		type: code_type, // overwrite object with mapped string for client compat
		code_type,
		note_moyenne:
			place.rating != null ? String(place.rating) : place.note_moyenne,
		nb_comm: place.review_count ?? place.nb_comm ?? 0,
		// Amenity boolean fields
		...amenities,
		// Normalized photos
		photos,
	};
}

/**
 * Get all places (with optional filtering).
 */
function getAllPlaces(options = {}) {
	if (!loaded) loadData();

	let result = places || [];

	// Filter by type (check both raw and normalized)
	if (options.type) {
		result = result.filter((p) => {
			const rawCode = p.type?.code || p.type;
			const normalized = TYPE_CODE_MAP[rawCode] || rawCode;
			return normalized === options.type || rawCode === options.type;
		});
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

	// Normalize all places before returning
	return result.map(normalizePlace);
}

/**
 * Get a single place by ID.
 */
function getPlaceById(id) {
	if (!loaded) loadData();
	const numId = typeof id === "string" ? parseInt(id, 10) : id;
	const place = places?.find((p) => p.id === numId) || null;
	return place ? normalizePlace(place) : null;
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
