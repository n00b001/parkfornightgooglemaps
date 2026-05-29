const prisma = require("../config/db");
const LRUCache = require("../services/lruCache");
const park4night = require("../services/park4night");

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
		const where = {
			latitude: { gte: lat - 0.5, lte: lat + 0.5 },
			longitude: { gte: lng - 0.5, lte: lng + 0.5 },
		};

		// Fetch from DB
		let places = await prisma.place.findMany({ where });

		// If fewer than 10 spots found, try live API fallback
		if (places.length < 10) {
			try {
				const livePlaces = await park4night.getPlaces(lat, lng);
				if (livePlaces && livePlaces.length > 0) {
					// Upsert results to database
					const upserts = livePlaces.map((p) =>
						prisma.place.upsert({
							where: { id: p.id },
							update: {
								name: p.name,
								latitude: p.latitude,
								longitude: p.longitude,
								type: p.type,
								description: p.description,
								address: p.address,
								rating: p.rating,
								rawData: p.rawData,
								lastFetched: new Date(),
							},
							create: {
								id: p.id,
								name: p.name,
								latitude: p.latitude,
								longitude: p.longitude,
								type: p.type,
								description: p.description,
								address: p.address,
								rating: p.rating,
								rawData: p.rawData,
								lastFetched: new Date(),
							},
						}),
					);
					await Promise.allSettled(upserts);

					// Re-query database to ensure consistency with user filters
					places = await prisma.place.findMany({ where });
				}
			} catch (fallbackError) {
				console.error("Park4Night fallback failed:", fallbackError.message);
			}
		}

		// Apply server-side filters if provided
		if (type) {
			places = places.filter((p) => p.type === type);
		}
		if (minRating) {
			const min = parseFloat(minRating);
			places = places.filter((p) => (p.rating || 0) >= min);
		}

		// Sort by distance from query point (closest first)
		places.sort(
			(a, b) =>
				distance(lat, lng, a.latitude, a.longitude) -
				distance(lat, lng, b.latitude, b.longitude),
		);

		// If sorting by rating, do it after distance (or instead of?)
		// To match memory "sorting (by rating) when querying the Prisma database"
		if (sortBy === "rating") {
			places.sort((a, b) => (b.rating || 0) - (a.rating || 0));
		}

		// Return only the closest N
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
		// Fetch original Park4Night reviews from guest API
		const reviews = await park4night.getReviews(placeId);
		res.json({ reviews });
	} catch (error) {
		console.error("Error fetching P4N reviews:", error.message);
		// Return empty array on failure to avoid breaking UI
		res.json({ reviews: [] });
	}
};

module.exports = { getPlaces, getPlaceDetail, getPlaceReviews, getStats };
