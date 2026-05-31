const prisma = require("../config/db");
const LRUCache = require("../services/lruCache");
const p4n = require("../services/park4night");
const {
	transformPlaces,
	transformPlace,
} = require("../services/placeTransform");

const MAX_PLACES_LIMIT = 200;

// LRU cache: 100 entries, 5-minute TTL
const placesCache = new LRUCache(100, 5 * 60 * 1000);

// Build a cache key from query params
const cacheKey = (lat, lng, type, minRating, sortBy, limit) =>
	`${lat},${lng}|${type}|${minRating}|${sortBy}|${limit}`;

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
		const boundingBox = {
			latMin: lat - 0.5,
			latMax: lat + 0.5,
			lngMin: lng - 0.5,
			lngMax: lng + 0.5,
		};

		// 1. Check local database first (spots updated in the last 24h)
		const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
		let dbPlaces = await prisma.place.findMany({
			where: {
				latitude: { gte: boundingBox.latMin, lte: boundingBox.latMax },
				longitude: { gte: boundingBox.lngMin, lte: boundingBox.lngMax },
				lastFetched: { gte: oneDayAgo },
			},
			include: {
				type: true,
				placeServices: { include: { service: true } },
			},
		});

		// 2. Hybrid Fallback: If < 10 spots, fetch live from Park4Night
		if (dbPlaces.length < 10) {
			console.log(`Only ${dbPlaces.length} spots in DB. Fetching live data...`);
			try {
				const livePlaces = await p4n.getPlaces(lat, lng);

				// Upsert live results to DB in parallel
				await Promise.allSettled(
					livePlaces.map((p) =>
						prisma.place.upsert({
							where: { id: p.id },
							update: {
								name: p.name,
								latitude: p.latitude,
								longitude: p.longitude,
								rating: p.rating,
								lastFetched: new Date(),
								// We don't update complex relations here for speed
							},
							create: {
								id: p.id,
								name: p.name,
								latitude: p.latitude,
								longitude: p.longitude,
								rating: p.rating,
								lastFetched: new Date(),
							},
						}),
					),
				);

				// Re-query DB to get consistent results with filters and relations
				const where = {
					latitude: { gte: boundingBox.latMin, lte: boundingBox.latMax },
					longitude: { gte: boundingBox.lngMin, lte: boundingBox.lngMax },
				};
				if (type) where.type = { originalCode: type }; // Adjust if type is code
				if (minRating) where.rating = { gte: parseFloat(minRating) };

				dbPlaces = await prisma.place.findMany({
					where,
					include: {
						type: true,
						placeServices: { include: { service: true } },
					},
				});
			} catch (apiError) {
				console.warn("Park4Night API failed, using available DB data:", apiError.message);
			}
		}

		// 3. Sorting & Response
		dbPlaces.sort(
			(a, b) =>
				distance(lat, lng, a.latitude, a.longitude) -
				distance(lat, lng, b.latitude, b.longitude),
		);

		const result = transformPlaces(dbPlaces.slice(0, maxLimit));
		placesCache.set(key, result);
		res.json(result);
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
		const place = await prisma.place.findUnique({
			where: { id },
			include: {
				type: true,
				placeServices: { include: { service: true } },
				placeActivities: { include: { activity: true } },
			},
		});
		if (!place) return res.status(404).json({ error: "Place not found" });
		res.json(transformPlace(place));
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
		const reviews = await prisma.review.findMany({
			where: { placeId },
			orderBy: { createdAt: "desc" },
		});
		res.json({ reviews });
	} catch (error) {
		console.error("Error fetching reviews:", error.message);
		res
			.status(500)
			.json({ error: "Failed to fetch reviews", details: error.message });
	}
};

module.exports = { getPlaces, getPlaceDetail, getPlaceReviews, getStats };
