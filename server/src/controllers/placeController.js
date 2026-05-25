const localData = require("../services/localData");

const getPlaces = async (req, res) => {
	const { lat, lng, type, minRating, sortBy } = req.query;
	if (!lat || !lng) return res.status(400).json({ error: "Lat/lng required" });

	try {
		const places = localData.getAllPlaces({
			lat: parseFloat(lat),
			lng: parseFloat(lng),
			type,
			minRating,
			sortBy,
		});

		console.log(
			`Serving ${places.length} places from local data for (${lat}, ${lng})`,
		);
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
		const stats = localData.getStats();
		res.json(stats);
	} catch (error) {
		console.error("Unexpected error in getStats:", error.message, error.stack);
		res
			.status(500)
			.json({ error: "Failed to fetch stats", details: error.message });
	}
};

const getPlaceDetail = async (req, res) => {
	try {
		const place = localData.getPlaceById(req.params.id);
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
		const reviews = localData.getPlaceReviews(req.params.id);
		res.json(reviews);
	} catch (error) {
		console.error("Error fetching reviews:", error.message);
		res
			.status(500)
			.json({ error: "Failed to fetch reviews", details: error.message });
	}
};

module.exports = { getPlaces, getPlaceDetail, getPlaceReviews, getStats };
