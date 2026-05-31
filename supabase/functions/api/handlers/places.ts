import type { Handler } from "hono";
import { getSupabase } from "../utils/db.ts";

// Map type codes to client-friendly keys (must match client TYPE_NAMES)
const TYPE_CODE_MAP: Record<string, string> = {
	APN: "rvPark",
	P: "parking",
	PN: "naturalParking",
	PJ: "campsite",
	C: "campsite",
	ACC_G: "freeRvPark",
	DS: "parking",
	AR: "restArea",
	PSS: "onSiteParking",
	ASS: "serviceArea",
	ACC_PR: "private",
	ACC_P: "paid",
	F: "closed",
	OR: "restArea",
	EP: "parking",
	CAR: "campsite",
	H: "campsite",
	HP: "campsite",
	A: "serviceArea",
	CS: "campsite",
	CL: "naturalParking",
	AL: "rvPark",
	S: "serviceArea",
	EC: "campsite",
	FM: "campsite",
	G: "campsite",
	M: "campsite",
	R: "campsite",
	RH: "campsite",
	T: "campsite",
};

// Map service codes to amenity keys (must match client AMENITIES)
const SERVICE_AMENITY_MAP: Record<string, string> = {
	point_eau: "waterPoint",
	eau: "waterPoint",
	electricite: "electricity",
	électricite: "electricity",
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

const MAX_PLACES_LIMIT = 200;

/**
 * Transform a place row from the database to the flat format expected by the client.
 */
function transformPlace(
	place: Record<string, unknown>,
): Record<string, unknown> {
	const result = { ...place };

	// Map type code
	const typeRow = place.type as Record<string, unknown> | undefined;
	if (typeRow?.originalCode) {
		result.type = TYPE_CODE_MAP[typeRow.originalCode as string];
	}

	// Photos — R2 URLs only
	const photos = place.photos as Array<Record<string, unknown>> | undefined;
	if (Array.isArray(photos)) {
		result.photos = photos.map((photo) => ({
			...photo,
			thumbUrl: photo.r2_url_thumb ?? "",
			largeUrl: photo.r2_url_large ?? "",
		}));
	}

	// Build amenity fields from placeServices
	const placeServices = place.placeServices as
		| Array<{ service: { code: string } }>
		| undefined;
	if (Array.isArray(placeServices)) {
		for (const ps of placeServices) {
			const code = ps.service?.code;
			if (code) {
				const amenityKey = SERVICE_AMENITY_MAP[code];
				if (amenityKey) {
					result[amenityKey] = "1";
				}
			}
		}
	}

	// Description from JSON
	const descriptions = place.descriptions as Record<string, string> | undefined;
	if (descriptions && typeof descriptions === "object") {
		result.description = descriptions.en ?? "";
	}

	// Address from JSON
	const address = place.address as Record<string, string> | undefined;
	if (address && typeof address === "object") {
		const parts = [
			address.street,
			address.city,
			address.zipcode,
			address.country,
		].filter(Boolean);
		result.address = parts.join(", ");
	}

	return result;
}

/**
 * GET /api/places
 * Fetch places near a coordinate, sorted by distance.
 */
export const getPlaces: Handler = async (c) => {
	const url = new URL(c.req.url);
	const qLat = url.searchParams.get("lat");
	const qLng = url.searchParams.get("lng");
	const type = url.searchParams.get("type");
	const minRating = url.searchParams.get("minRating");
	const sortBy = url.searchParams.get("sortBy");
	const limitParam = url.searchParams.get("limit");

	if (!qLat || !qLng) {
		return c.json({ error: "Lat/lng required" }, 400);
	}

	const lat = parseFloat(qLat);
	const lng = parseFloat(qLng);
	const maxLimit = Math.min(
		limitParam ? parseInt(limitParam, 10) : MAX_PLACES_LIMIT,
		MAX_PLACES_LIMIT,
	);

	const supabase = getSupabase();

	// Build PostgREST query
	let query = supabase
		.from("place")
		.select(`
      *,
      type (id, englishName, originalCode),
      placeServices (placeId, serviceId, service (id, code, label, originalCode)),
      placeActivities (placeId, activityId, activity (id, code, label, originalCode))
    `)
		.gte("latitude", lat - 0.5)
		.lte("latitude", lat + 0.5)
		.gte("longitude", lng - 0.5)
		.lte("longitude", lng + 0.5)
		.limit(maxLimit * 3); // fetch extra to filter by distance after

	if (type) {
		query = query.eq("type", type);
	}
	if (minRating) {
		query = query.gte("rating", parseFloat(minRating));
	}
	if (sortBy === "rating") {
		query = query.order("rating", { ascending: false });
	}

	const { data: places, error } = await query;
	if (error) {
		console.error("Error fetching places:", error.message);
		return c.json(
			{ error: "Failed to fetch places", details: error.message },
			500,
		);
	}

	// Sort by distance (closest first) and take top N
	const sorted = (places || []).sort((a, b) => {
		const distA = Math.sqrt((a.latitude - lat) ** 2 + (a.longitude - lng) ** 2);
		const distB = Math.sqrt((b.latitude - lat) ** 2 + (b.longitude - lng) ** 2);
		return distA - distB;
	});

	const result = sorted.slice(0, maxLimit).map(transformPlace);
	return c.json(result);
};

/**
 * GET /api/places/stats
 */
export const getStats: Handler = async (c) => {
	const supabase = getSupabase();

	const { count: totalPlaces, error: err1 } = await supabase
		.from("place")
		.select("*", { count: "exact", head: true });
	if (err1) {
		console.error("Error fetching total places:", err1.message);
		return c.json(
			{ error: "Failed to fetch stats", details: err1.message },
			500,
		);
	}

	const { count: totalReviews, error: err2 } = await supabase
		.from("review")
		.select("*", { count: "exact", head: true });
	if (err2) {
		console.error("Error fetching total reviews:", err2.message);
		return c.json(
			{ error: "Failed to fetch stats", details: err2.message },
			500,
		);
	}

	const { count: placesWithReviews, error: err3 } = await supabase
		.from("place")
		.select("id", { count: "exact", head: true })
		.in(
			"id",
			(
				await supabase
					.from("review")
					.select("placeId", { head: false })
					.limit(100000)
			).data?.map((r) => r.placeId) ?? [],
		);
	if (err3) {
		console.error("Error fetching places with reviews:", err3.message);
		return c.json(
			{ error: "Failed to fetch stats", details: err3.message },
			500,
		);
	}

	return c.json({
		totalPlaces: totalPlaces ?? 0,
		totalReviews: totalReviews ?? 0,
		placesWithReviews: placesWithReviews ?? 0,
	});
};

/**
 * GET /api/places/:id
 */
export const getPlaceDetail: Handler = async (c) => {
	const id = parseInt(c.req.param("id"));
	const supabase = getSupabase();

	const { data: place, error } = await supabase
		.from("place")
		.select(`
      *,
      type (id, englishName, originalCode),
      placeServices (placeId, serviceId, service (id, code, label, originalCode)),
      placeActivities (placeId, activityId, activity (id, code, label, originalCode))
    `)
		.eq("id", id)
		.single();

	if (error || !place) {
		return c.json({ error: "Place not found" }, 404);
	}

	return c.json(transformPlace(place));
};

/**
 * GET /api/places/:id/reviews
 */
export const getPlaceReviews: Handler = async (c) => {
	const placeId = parseInt(c.req.param("id"));
	const supabase = getSupabase();

	const { data: reviews, error } = await supabase
		.from("review")
		.select("*")
		.eq("placeId", placeId)
		.order("createdAt", { ascending: false });

	if (error) {
		console.error("Error fetching reviews:", error.message);
		return c.json(
			{ error: "Failed to fetch reviews", details: error.message },
			500,
		);
	}

	return c.json({ reviews: reviews ?? [] });
};
