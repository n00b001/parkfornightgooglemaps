const prisma = require("../config/db");
const LRUCache = require("../services/lruCache");
const park4night = require("../services/park4night");
const localData = require("../services/localData");

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

	// Check memory cache first
	const key = cacheKey(lat, lng, type, minRating, sortBy, maxLimit);
	const cached = placesCache.get(key);
	if (cached !== undefined) {
		return res.json(cached);
	}

	try {
		// 1. Initial check: Do we have recent data for this bounding box in Prisma?
		const boundingBox = {
			latitude: { gte: lat - 0.5, lte: lat + 0.5 },
			longitude: { gte: lng - 0.5, lte: lng + 0.5 },
		};

		const recentSpots = await prisma.place.findMany({
			where: {
				...boundingBox,
				lastFetched: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) },
			},
			take: 10,
		});

		// 2. Fallback to Live API if data is sparse or stale
		if (recentSpots.length < 10) {
			try {
				const livePlaces = await park4night.getPlaces(lat, lng);
				if (livePlaces && livePlaces.length > 0) {
					// Upsert results to Prisma cache
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
								photoCount: p.rawData?.nb_photos || 0,
								photos: p.rawData?.photos || [],
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
								photoCount: p.rawData?.nb_photos || 0,
								photos: p.rawData?.photos || [],
								rawData: p.rawData,
								lastFetched: new Date(),
							},
						}),
					);
					await Promise.allSettled(upserts);
				}
			} catch (apiError) {
				console.warn("Live API fetch failed, falling back to localData:", apiError.message);
				// 3. Final fallback: Seed/Local data if API is down
				const localSpots = localData.getAllPlaces({ lat, lng, range: 0.5 });
				if (localSpots.length > 0 && recentSpots.length === 0) {
					// Only use local data if we have absolutely nothing in DB
					return res.json(localSpots.slice(0, maxLimit));
				}
			}
		}

		// 4. Final Query: Retrieve from Prisma using user's filters
		const where = { ...boundingBox };
		if (type) where.type = type;
		if (minRating) where.rating = { gte: parseFloat(minRating) };

		const orderBy = {};
		if (sortBy === "rating") orderBy.rating = "desc";

		let places = await prisma.place.findMany({
			where,
			orderBy: Object.keys(orderBy).length > 0 ? orderBy : undefined,
		});

		// Sort by distance from query point (closest first)
		places.sort(
			(a, b) =>
				distance(lat, lng, a.latitude, a.longitude) -
				distance(lat, lng, b.latitude, b.longitude),
		);

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
