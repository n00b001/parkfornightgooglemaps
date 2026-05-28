const fs = require("fs");
const path = require("path");

// Path to scraped data files
const DATA_DIR = path.join(__dirname, "..", "..", "..", "scripts", "data");

let places = null;
let reviewsByPlace = null;
let loaded = false;

/**
 * Map Park4Night type codes to English type values.
 */
const TYPE_CODE_MAP = {
	APN: "rvPark", // Aire de camping-car → rvPark
	P: "parking", // Parking area → parking
	PN: "naturalParking", // Parking naturel → naturalParking
	PJ: "campsite", // Aire de jeu → campsite
	C: "campsite", // Camping → campsite
	ACC_G: "freeRvPark", // Aire gratuite → freeRvPark
	DS: "parking", // Dépannage → parking
	AR: "restArea", // Aire de repos → restArea
	PSS: "onSiteParking", // Parking sur site → onSiteParking
	ASS: "serviceArea", // Aire service → serviceArea
	ACC_PR: "private", // Accès privé → private
	ACC_P: "paid", // Accès payant → paid
	F: "closed", // Fermé → closed
	OR: "restArea", // Aire de repos officielle → restArea
	EP: "parking", // Espace de parking → parking
};

/**
 * Map Park4Night service codes to English amenity keys.
 */
const SERVICE_AMENITY_MAP = {
	point_eau: "waterPoint",
	eau: "waterPoint",
	electricite: "electricity",
	"électricité": "electricity",
	poubelle: "trashCan",
	wifi: "wifi",
	vidange_eaux_usees: "wasteWaterDrain",
	vidance_eaux_grises: "wasteWaterDrain",
	vidange_wc: "toiletDrain",
	vidange_chasse: "toiletDrain",
	douche: "shower",
	baignade: "swimming",
	animaux: "pets",
	aire_pique_nique: "picnicArea",
	laverie: "laundry",
	wc_public: "publicToilet",
};

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
};

/**
 * Simple language detection heuristic.
 * Returns true if the text appears to be English.
 */
function isEnglish(text) {
	if (!text || typeof text !== "string") return true;
	// Check for common non-English patterns (accented chars, specific words)
	const nonEnglishPatterns = [
		/[àâäéèêëïîôùûüÿçœæ]/i, // French accented characters
		/\b(les|des|une|dans|pour|avec|sur|sous|entre|vers|chez|sans|parmi)\b/i,
		/\b(est|sont|était|étaient|a|ont|avait|avaient|sera|seront)\b/i,
		/\b(très|même|tout|tous|toute|toutes|bien|mal|plus|moins|très)\b/i,
		/\b(ou|et|mais|donc|car|cependant|toutefois|pourtant)\b/i,
		/\b(dans|sur|sous|devant|derrière|à|de|du|des|au|aux)\b/i,
	];;
	return !nonEnglishPatterns.some((pattern) => pattern.test(text));
}

/**
 * Normalize a review object to use English field names.
 * Non-English text is stored in originalContent for reference.
 * TODO: Integrate with a translation API (Google Translate, DeepL) to produce
 * translated content. Until then, non-English reviews keep their original text
 * as the primary content with a flag indicating translation is needed.
 */
function normalizeReview(review) {
	if (!review) return review;

	const rawText = review.text || review.texte || review.content || "";
	const english = isEnglish(rawText);
	const vehicleType = VEHICLE_TYPE_MAP[review.vehicle_type] || review.vehicle_type || "unknown";

	return {
		id: review.id,
		placeId: review.place_id,
		author: review.author || review.auteur || "anonymous",
		authorId: review.author_id,
		content: rawText, // Primary content (original language if not translated)
		originalContent: english ? null : rawText, // Non-English original preserved
		translatedContent: english ? null : null, // TODO: populate with API translation
		rating: review.rating ?? review.note,
		vehicleType,
		createdAt: review.created_at || review.createdAt,
		needsTranslation: !english,
	};
}

/**
 * Load scraped data from JSON files into memory.
 * Called once on startup (synchronous, non-blocking).
 * Skipped in production — data comes from Prisma DB seeded during build.
 */
function loadData() {
	if (loaded) return;

	// In production, data is served from Prisma DB (seeded during build).
	// Loading 272MB JSON into RAM would OOM on Render free tier.
	if (process.env.NODE_ENV === "production") {
		console.log("Production mode: skipping local data load (using Prisma DB)");
		loaded = true;
		return;
	}

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
				`Failed to parse places file: ${error.message}`,
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
				`Failed to parse reviews file: ${error.message}`,
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
 * Normalize a place object to use English field names and values.
 * Original non-English text is preserved alongside for reference.
 */
function normalizePlace(place) {
	if (!place) return place;

	// Build address string from address object
	const addr = place.address || {};
	const addressStr = [addr.street, addr.city, addr.zipcode, addr.country]
		.filter(Boolean)
		.join(", ");

	// Map type code to English
	const rawTypeCode =
		typeof place.type === "object" ? place.type.code : place.type;
	const type = TYPE_CODE_MAP[rawTypeCode] || "parking";

	// Map services array to English amenity boolean fields
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

	// Map photos with English field names
	const photos = Array.isArray(place.photos)
		? place.photos.map((p) => ({
				...p,
				thumbUrl: p.url_thumb || p.lien_mini || p.thumbUrl,
				largeUrl: p.url_large || p.lien_grand || p.largeUrl,
			}))
		: [];

	return {
		...place,
		// English field names (primary)
		title: place.title || place.titre || place.name,
		address: addressStr || place.address,
		type,
		rating: place.rating ?? place.note_moyenne,
		reviewCount: place.review_count ?? place.nb_comm ?? 0,
		// Original non-English text preserved for reference
		originalTitle: place.titre || place.originalTitle,
		originalAddress: place.adresse || place.originalAddress,
		// Amenity boolean fields (English keys)
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
 * Get reviews for a place (normalized to English field names).
 */
function getPlaceReviews(placeId) {
	if (!loaded) loadData();
	const numId = typeof placeId === "string" ? parseInt(placeId, 10) : placeId;
	const rawReviews = reviewsByPlace?.get(numId) || [];
	return rawReviews.map(normalizeReview);
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
