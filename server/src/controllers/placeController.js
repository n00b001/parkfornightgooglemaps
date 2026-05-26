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

	// Check cache first
	const key = cacheKey(lat, lng, type, minRating, sortBy, maxLimit);
	const cached = placesCache.get(key);
	if (cached !== undefined) {
		return res.json(cached);
	}

	try {
		// 1. Try fetching from DB first (within 0.5 degree bounding box)
		const boxSize = 0.5;
		const where = {
			latitude: { gte: lat - boxSize, lte: lat + boxSize },
			longitude: { gte: lng - boxSize, lte: lng + boxSize },
		};

		let dbPlaces = await prisma.place.findMany({ where });

		// Filter for "recent" spots (updated in the last 24 hours)
		const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
		const recentPlaces = dbPlaces.filter((p) => p.lastFetched > oneDayAgo);

		// 2. If fewer than 10 recent spots, fetch from Park4Night API
		if (recentPlaces.length < 10) {
			console.log(`Only ${recentPlaces.length} recent spots in DB for (${lat}, ${lng}). Fetching from P4N API...`);
			try {
				let apiPlaces = await park4night.getPlaces(lat, lng);

				// 3. Fallback to localData if API returns nothing
				if (!apiPlaces || apiPlaces.length === 0) {
					console.log("P4N API returned no results. Falling back to localData...");
					apiPlaces = localData.getAllPlaces({ lat, lng, range: boxSize });
				}

				if (apiPlaces && apiPlaces.length > 0) {
					// Upsert to DB to refresh cache
					const upserts = apiPlaces.map((p) =>
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

					// Re-fetch from DB to get the most up-to-date list
					dbPlaces = await prisma.place.findMany({ where });
				}
			} catch (apiError) {
				console.error("Park4Night API error:", apiError.message);
				// If API fails, we still have whatever was in DB or we could try localData
				if (dbPlaces.length === 0) {
					console.log("API failed and DB empty. Trying localData...");
					const localPlaces = localData.getAllPlaces({ lat, lng, range: boxSize });
					if (localPlaces.length > 0) {
						// Upsert local data too
						const upserts = localPlaces.map((p) =>
							prisma.place.upsert({
								where: { id: p.id },
								update: {
									name: p.name || p.title,
									latitude: p.latitude,
									longitude: p.longitude,
									type: p.type,
									description: p.description,
									address: p.address,
									rating: p.rating,
									rawData: p,
									lastFetched: new Date(),
								},
								create: {
									id: p.id,
									name: p.name || p.title,
									latitude: p.latitude,
									longitude: p.longitude,
									type: p.type,
									description: p.description,
									address: p.address,
									rating: p.rating,
									rawData: p,
									lastFetched: new Date(),
								},
							}),
						);
						await Promise.allSettled(upserts);
						dbPlaces = await prisma.place.findMany({ where });
					}
				}
			}
		}

		// 4. Apply filters and sorting on the resulting set
		let filteredPlaces = dbPlaces;

		if (type) {
			filteredPlaces = filteredPlaces.filter((p) => p.type === type);
		}

		if (minRating) {
			const minR = parseFloat(minRating);
			filteredPlaces = filteredPlaces.filter((p) => (p.rating || 0) >= minR);
		}

		// Sort by distance from query point (closest first)
		filteredPlaces.sort(
			(a, b) =>
				distance(lat, lng, a.latitude, a.longitude) -
				distance(lat, lng, b.latitude, b.longitude),
		);

		if (sortBy === "rating") {
			filteredPlaces.sort((a, b) => (b.rating || 0) - (a.rating || 0));
		}

		// Return only the closest N
		const result = filteredPlaces.slice(0, maxLimit);
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
		// Fetch original Park4Night reviews
		const p4nReviews = await park4night.getReviews(placeId);
		res.json({ reviews: p4nReviews });
	} catch (error) {
		console.error("Error fetching P4N reviews:", error.message);
		res
			.status(500)
			.json({ error: "Failed to fetch P4N reviews", details: error.message });
	}
};

module.exports = { getPlaces, getPlaceDetail, getPlaceReviews, getStats };
