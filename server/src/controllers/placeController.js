const prisma = require("../config/db");
const park4night = require("../services/park4night");
const localData = require("../services/localData");

const upsertPlaces = async (places) => {
	const results = [];
	for (const p of places) {
		try {
			const saved = await prisma.place.upsert({
				where: { id: p.id },
				update: {
					name: p.name || "",
					latitude: p.latitude,
					longitude: p.longitude,
					type: p.type || "",
					description: p.description,
					address: p.address,
					rating: p.rating,
					rawData: p.rawData,
					lastFetched: new Date(),
				},
				create: {
					id: p.id,
					name: p.name || "",
					latitude: p.latitude,
					longitude: p.longitude,
					type: p.type || "",
					description: p.description,
					address: p.address,
					rating: p.rating,
					rawData: p.rawData,
				},
			});
			results.push(saved);
		} catch (err) {
			console.error(`Failed to upsert place ${p.id}:`, err.message);
			// Fallback to the original object if upsert fails
			results.push(p);
		}
	}
	return results;
};

const getPlaces = async (req, res) => {
	const { lat: qLat, lng: qLng, type, minRating, sortBy } = req.query;
	if (!qLat || !qLng) return res.status(400).json({ error: "Lat/lng required" });

	const lat = parseFloat(qLat);
	const lng = parseFloat(qLng);

	try {
		// Build Prisma query
		const where = {
			latitude: { gte: lat - 0.5, lte: lat + 0.5 },
			longitude: { gte: lng - 0.5, lte: lng + 0.5 },
		};

		if (type) {
			where.type = type;
		}

		if (minRating) {
			where.rating = { gte: parseFloat(minRating) };
		}

		const orderBy = {};
		if (sortBy === "rating") {
			orderBy.rating = "desc";
		}

		// 1. Try Prisma Database
		let places = await prisma.place.findMany({
			where,
			orderBy: Object.keys(orderBy).length > 0 ? orderBy : undefined,
		});

		// 2. If no results or few results, try live API
		if (places.length < 10) {
			try {
				const livePlaces = await park4night.getPlaces(lat, lng);
				if (livePlaces && livePlaces.length > 0) {
					console.log(`Serving ${livePlaces.length} places from Live API`);
					places = await upsertPlaces(livePlaces);
					return res.json(places);
				}
			} catch (apiErr) {
				console.error("API Fetch failed:", apiErr.message);
			}
		}

		// 3. Fallback to Local Data if DB/API yielded nothing
		if (places.length === 0) {
			places = localData.getAllPlaces({
				lat,
				lng,
				type,
				minRating,
				sortBy,
			});
			console.log(`Serving ${places.length} places from local data`);
		} else {
			console.log(`Serving ${places.length} places from Prisma DB`);
		}

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
			where: { reviews: { some: {} } }
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
		let place = await prisma.place.findUnique({ where: { id } });

		if (!place) {
			try {
				const liveDetail = await park4night.getPlaceDetail(id);
				if (liveDetail) {
					const saved = await upsertPlaces([liveDetail]);
					return res.json(saved[0]);
				}
			} catch (apiErr) {
				console.error("API Detail Fetch failed:", apiErr.message);
			}
			place = localData.getPlaceById(id);
		}

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
		const reviews = await park4night.getReviews(placeId);
		res.json({ reviews });
	} catch (error) {
		console.error("Error fetching reviews:", error.message);
		res
			.status(500)
			.json({ error: "Failed to fetch reviews", details: error.message });
	}
};

module.exports = { getPlaces, getPlaceDetail, getPlaceReviews, getStats };
