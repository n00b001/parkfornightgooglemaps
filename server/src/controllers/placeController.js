const prisma = require("../config/db");
const LRUCache = require("../services/lruCache");
const park4night = require("../services/park4night");
const { normalizePlace } = require("../services/normalization");

const MAX_PLACES_LIMIT = 200;

// LRU cache: 100 entries, 5-minute TTL
const placesCache = new LRUCache(100, 5 * 60 * 1000);

// Build a cache key from query params
const cacheKey = (lat, lng, type, minRating, sortBy, limit) =>
	`${lat},${lng}|${type || "*"}|${minRating || "*"}|${sortBy || "*"}|${limit}`;

// Simple Euclidean distance (good enough for sorting nearby places)
const distance = (aLat, aLng, bLat, bLng) =>
	Math.sqrt((aLat - bLat) ** 2 + (aLng - bLng) ** 2);

const getPlaces = async (req, res) => {
	const { lat: qLat, lng: qLng, type, minRating, sortBy, limit } = req.query;
	if (!qLat || !qLng)
		return res.status(400).json({ error: "Lat/lng required" });

	const lat = parseFloat(qLat);
	const lng = parseFloat(qLng);
	const maxLimit = Math.min(
		limit ? parseInt(limit, 10) : MAX_PLACES_LIMIT,
		MAX_PLACES_LIMIT,
	);

	// Check cache first
	const key = cacheKey(lat, lng, type, minRating, sortBy, maxLimit);
	const cached = placesCache.get(key);
	if (cached !== undefined) {
		return res.json(cached);
	}

	try {
		// 1. Check local DB for spots in the area
		const where = {
			latitude: { gte: lat - 0.5, lte: lat + 0.5 },
			longitude: { gte: lng - 0.5, lte: lng + 0.5 },
		};

		if (type) where.type = type;
		if (minRating) where.rating = { gte: parseFloat(minRating) };

		let places = await prisma.place.findMany({ where });

		// 2. Determine if we need to fetch live data (e.g., < 20 spots or data is old)
		const freshThreshold = new Date(Date.now() - 24 * 60 * 60 * 1000);
		const freshPlaces = places.filter(p => p.lastFetched > freshThreshold);

		if (freshPlaces.length < 20 && process.env.NODE_ENV !== 'test') {
			console.log(`Insufficient fresh data (${freshPlaces.length} < 20), fetching from Park4night...`);
			try {
				const liveData = await park4night.getPlaces(lat, lng);
				if (liveData && liveData.length > 0) {
					// Normalize and upsert live data
					const upserts = liveData.map(p => {
						const normalized = normalizePlace(p.rawData || p);
						return prisma.place.upsert({
							where: { id: normalized.id },
							update: normalized,
							create: normalized,
						});
					});
					await Promise.allSettled(upserts);
					// Refetch from DB to get the merged/updated list
					places = await prisma.place.findMany({ where });
				}
			} catch (apiError) {
				console.error("Park4night API fetch failed:", apiError.message);
				// Fallback to whatever we have in DB
			}
		}

		// 3. Sort and limit results
		if (sortBy === "rating") {
			places.sort((a, b) => (b.rating || 0) - (a.rating || 0));
		} else {
			// Default: Sort by distance from query point (closest first)
			places.sort(
				(a, b) =>
					distance(lat, lng, a.latitude, a.longitude) -
					distance(lat, lng, b.latitude, b.longitude),
			);
		}

		places = places.slice(0, maxLimit);
		placesCache.set(key, places);
		res.json(places);
	} catch (error) {
		console.error("Unexpected error in getPlaces:", error.message, error.stack);
		res
			.status(500)
			.json({ error: "Failed to fetch places", details: error.message });
	}
};

const getStats = async (_req, res) => {
	try {
		const totalPlaces = await prisma.place.count();
		const totalReviews = await prisma.review.count();
		const placesWithReviews = await prisma.place.count({
			where: { reviews: { some: {} } },
		});
		res.json({
			totalPlaces,
			totalReviews,
			placesWithReviews,
		});
	} catch (error) {
		console.error("Unexpected error in getStats:", error.message, error.stack);
		res
			.status(500)
			.json({ error: "Failed to fetch stats", details: error.message });
	}
};

const getPlaceDetail = async (req, res) => {
	try {
		const id = parseInt(req.params.id);
		const place = await prisma.place.findUnique({ where: { id } });
		if (!place) return res.status(404).json({ error: "Place not found" });
		res.json(place);
	} catch (error) {
		console.error("Error fetching place detail:", error.message);
		res
			.status(500)
			.json({ error: "Failed to fetch place", details: error.message });
	}
};

const getPlaceReviews = async (req, res) => {
	try {
		const placeId = parseInt(req.params.id);
		const p4nReviews = await park4night.getReviews(placeId);

		// Map P4N reviews to a consistent format for the frontend
		const formattedReviews = p4nReviews.map(r => ({
			author: r.auteur || r.author || "Park4Night User",
			content: r.commentaire || r.text || r.content || "",
			rating: r.note || r.rating || 0,
			date: r.date_creation || r.createdAt,
			needsTranslation: r.language && r.language.iso639_1 !== 'en'
		}));

		res.json({ reviews: formattedReviews });
	} catch (error) {
		console.error("Error fetching reviews from Park4night:", error.message);
		res
			.status(500)
			.json({ error: "Failed to fetch reviews", details: error.message });
	}
};

module.exports = { getPlaces, getPlaceDetail, getPlaceReviews, getStats };
