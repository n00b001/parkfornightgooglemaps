import { createClient } from "@supabase/supabase-js";

interface Env {
	SUPABASE_URL: string;
	SUPABASE_SERVICE_ROLE_KEY: string;
	ASSETS: any; // Cloudflare Workers Assets binding
}

function getAdminClient(env: Env) {
	return createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);
}

function getAuthUser(request: Request): { id: string; email: string } | null {
	const authHeader = request.headers.get("Authorization");
	if (!authHeader) return null;

	const token = authHeader.replace("Bearer ", "");
	if (!token) return null;

	try {
		const parts = token.split(".");
		if (parts.length !== 3) return null;
		const payload = JSON.parse(atob(parts[1]));
		if (!payload || !payload.sub) return null;
		return { id: payload.sub, email: payload.email || "" };
	} catch {
		return null;
	}
}

// Type code mapping (must match TYPE_NAMES in PlaceDetails.tsx)
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

// Service code mapping (must match AMENITIES in PlaceDetails.tsx)
const SERVICE_AMENITY_MAP: Record<string, string> = {
	point_eau: "waterPoint",
	eau: "waterPoint",
	electricite: "electricity",
	électricité: "electricity",
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
	toilettes_public: "publicToilet",
};

function haversineDistance(
	lat1: number,
	lng1: number,
	lat2: number,
	lng2: number,
): number {
	const R = 6371;
	const dLat = ((lat2 - lat1) * Math.PI) / 180;
	const dLng = ((lng2 - lng1) * Math.PI) / 180;
	const a =
		Math.sin(dLat / 2) * Math.sin(dLat / 2) +
		Math.cos((lat1 * Math.PI) / 180) *
			Math.cos((lat2 * Math.PI) / 180) *
			Math.sin(dLng / 2) *
			Math.sin(dLng / 2);
	const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
	return R * c;
}

function transformPlace(place: any): any {
	if (!place) return place;
	const result = { ...place };

	if (place.type && place.type.originalCode) {
		result.type = TYPE_CODE_MAP[place.type.originalCode];
	}

	if (Array.isArray(place.photos)) {
		result.photos = place.photos.map((photo: any) => ({
			...photo,
			thumbUrl: photo.r2_url_thumb ?? "",
			largeUrl: photo.r2_url_large ?? "",
		}));
	}

	if (Array.isArray(place.placeServices)) {
		for (const ps of place.placeServices) {
			if (ps.service && ps.service.code) {
				const amenityKey = SERVICE_AMENITY_MAP[ps.service.code];
				if (amenityKey) {
					result[amenityKey] = "1";
				}
			}
		}
	}

	if (place.descriptions && typeof place.descriptions === "object") {
		result.description = place.descriptions.en ?? "";
	}

	if (place.address && typeof place.address === "object") {
		const parts = [
			place.address.street,
			place.address.city,
			place.address.zipcode,
			place.address.country,
		].filter(Boolean);
		result.address = parts.join(", ");
	}

	return result;
}

function jsonResponse(data: any, status = 200) {
	return new Response(JSON.stringify(data), {
		status,
		headers: { "Content-Type": "application/json" },
	});
}

async function handleGetPlaces(request: Request, env: Env) {
	const url = new URL(request.url);
	const lat = parseFloat(url.searchParams.get("lat") ?? "48.8566");
	const lng = parseFloat(url.searchParams.get("lng") ?? "2.3522");
	const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "150"), 200);
	const type = url.searchParams.get("type") ?? "";
	const minRating = url.searchParams.get("minRating") ?? "";
	const sortBy = url.searchParams.get("sortBy") ?? "";
	const amenities = url.searchParams.get("amenities") ?? "";

	const supabase = getAdminClient(env);

	let query = supabase
		.from("place")
		.select(
			`id, name, latitude, longitude, rating, ratingCount, typeId, address, descriptions, photos, google_place_id, type (id, englishName, originalCode), placeServices (serviceId, service (id, code, label, originalCode))`,
		)
		.gte("latitude", lat - 0.5)
		.lte("latitude", lat + 0.5)
		.gte("longitude", lng - 0.5)
		.lte("longitude", lng + 0.5);

	if (type) query = query.eq("typeId", type);
	if (minRating) query = query.gte("rating", parseFloat(minRating));
	if (sortBy === "rating") query = query.order("rating", { ascending: false });

	const { data: places, error } = await query.limit(limit * 2);
	if (error) return jsonResponse({ error: error.message }, 500);

	let filtered = places;
	if (amenities) {
		const requested = amenities.split(",");
		filtered = places.filter((place: any) => {
			const serviceCodes =
				place.placeServices?.map((ps: any) => ps.service?.code) ?? [];
			return requested.every((amenity: string) =>
				serviceCodes.some((code: string | undefined) => code === amenity),
			);
		});
	}

	filtered.sort((a: any, b: any) => {
		const distA = haversineDistance(lat, lng, a.latitude, a.longitude);
		const distB = haversineDistance(lat, lng, b.latitude, b.longitude);
		return distA - distB;
	});

	const result = filtered.slice(0, limit).map((place: any) => {
		const transformed = transformPlace(place);
		transformed.distance = haversineDistance(
			lat,
			lng,
			place.latitude,
			place.longitude,
		);
		return transformed;
	});

	return jsonResponse(result);
}

async function handleGetPlace(request: Request, env: Env) {
	const url = new URL(request.url);
	const id = url.searchParams.get("id");
	if (!id) return jsonResponse({ error: "Missing id" }, 400);

	const supabase = getAdminClient(env);
	const { data, error } = await supabase
		.from("place")
		.select(
			`id, name, latitude, longitude, rating, ratingCount, typeId, address, descriptions, photos, google_place_id, type (id, englishName, originalCode), placeServices (serviceId, service (id, code, label, originalCode))`,
		)
		.eq("id", id)
		.single();

	if (error) return jsonResponse({ error: error.message }, 500);
	return jsonResponse(transformPlace(data));
}

async function handleGetPlaceReviews(request: Request, env: Env) {
	const url = new URL(request.url);
	const placeId = url.searchParams.get("placeId");
	if (!placeId) return jsonResponse({ error: "Missing placeId" }, 400);

	const supabase = getAdminClient(env);
	const { data, error } = await supabase
		.from("review")
		.select("*")
		.eq("placeId", placeId)
		.order("createdAt", { ascending: false });

	if (error) return jsonResponse({ error: error.message }, 500);
	return jsonResponse(data);
}

async function handleGetStats(_req: Request, env: Env) {
	const supabase = getAdminClient(env);
	const { count, error } = await supabase
		.from("place")
		.select("*", { count: "exact", head: true });

	if (error) return jsonResponse({ error: error.message }, 500);
	return jsonResponse({ totalPlaces: count ?? 0 });
}

async function handleGetUser(request: Request, env: Env) {
	const user = getAuthUser(request);
	if (!user) return jsonResponse({ error: "Unauthorized" }, 401);

	const supabase = getAdminClient(env);
	const { data, error } = await supabase
		.from("User")
		.select("*")
		.eq("authUserId", user.id)
		.single();

	if (error && error.code !== "PGRST116") {
		return jsonResponse({ error: error.message }, 500);
	}
	return jsonResponse(data);
}

async function handleGetFavorites(request: Request, env: Env) {
	const user = getAuthUser(request);
	if (!user) return jsonResponse({ error: "Unauthorized" }, 401);

	const supabase = getAdminClient(env);
	const { data, error } = await supabase
		.from("favorite")
		.select(
			`placeId, place (id, name, latitude, longitude, rating, typeId, address, descriptions, photos, type (id, englishName, originalCode), placeServices (serviceId, service (id, code, label, originalCode)))`,
		)
		.eq("userId", user.id);

	if (error) return jsonResponse({ error: error.message }, 500);

	const places = (data ?? []).map((f: any) => transformPlace(f.place));
	return jsonResponse(places);
}

async function handleAddFavorite(request: Request, env: Env) {
	const user = getAuthUser(request);
	if (!user) return jsonResponse({ error: "Unauthorized" }, 401);

	const body = await request.json();
	const { placeId } = body;
	if (!placeId) return jsonResponse({ error: "Missing placeId" }, 400);

	const supabase = getAdminClient(env);
	const { error } = await supabase.from("favorite").insert({
		userId: user.id,
		placeId,
	});

	if (error) return jsonResponse({ error: error.message }, 500);
	return jsonResponse({ success: true });
}

async function handleRemoveFavorite(request: Request, env: Env) {
	const user = getAuthUser(request);
	if (!user) return jsonResponse({ error: "Unauthorized" }, 401);

	const url = new URL(request.url);
	const placeId = url.searchParams.get("placeId");
	if (!placeId) return jsonResponse({ error: "Missing placeId" }, 400);

	const supabase = getAdminClient(env);
	const { error } = await supabase
		.from("favorite")
		.delete()
		.eq("userId", user.id)
		.eq("placeId", placeId);

	if (error) return jsonResponse({ error: error.message }, 500);
	return jsonResponse({ success: true });
}

async function handleAddReview(request: Request, env: Env) {
	const user = getAuthUser(request);
	if (!user) return jsonResponse({ error: "Unauthorized" }, 401);

	const body = await request.json();
	const { placeId, rating, comment } = body;
	if (!placeId || rating == null) {
		return jsonResponse({ error: "Missing placeId or rating" }, 400);
	}

	const supabase = getAdminClient(env);
	const { error } = await supabase.from("review").insert({
		userId: user.id,
		placeId,
		rating,
		comment,
	});

	if (error) return jsonResponse({ error: error.message }, 500);
	return jsonResponse({ success: true });
}

async function handleGetReviews(request: Request, env: Env) {
	const user = getAuthUser(request);
	if (!user) return jsonResponse({ error: "Unauthorized" }, 401);

	const supabase = getAdminClient(env);
	const { data, error } = await supabase
		.from("review")
		.select("*")
		.eq("userId", user.id)
		.order("createdAt", { ascending: false });

	if (error) return jsonResponse({ error: error.message }, 500);
	return jsonResponse(data);
}

async function handleRecordVisit(request: Request, env: Env) {
	const user = getAuthUser(request);
	if (!user) return jsonResponse({ error: "Unauthorized" }, 401);

	const body = await request.json();
	const { placeId, latitude, longitude } = body;
	if (!placeId) return jsonResponse({ error: "Missing placeId" }, 400);

	const supabase = getAdminClient(env);
	const { error } = await supabase.from("visit").insert({
		userId: user.id,
		placeId,
		latitude,
		longitude,
	});

	if (error) return jsonResponse({ error: error.message }, 500);
	return jsonResponse({ success: true });
}

async function handleGetVisits(request: Request, env: Env) {
	const user = getAuthUser(request);
	if (!user) return jsonResponse({ error: "Unauthorized" }, 401);

	const supabase = getAdminClient(env);
	const { data, error } = await supabase
		.from("visit")
		.select(
			`id, placeId, createdAt, place (id, name, latitude, longitude, rating, typeId, address, descriptions, photos, type (id, englishName, originalCode), placeServices (serviceId, service (id, code, label, originalCode)))`,
		)
		.eq("userId", user.id)
		.order("createdAt", { ascending: false });

	if (error) return jsonResponse({ error: error.message }, 500);

	const visits = (data ?? []).map((v: any) => ({
		...v,
		place: v.place ? transformPlace(v.place) : null,
	}));
	return jsonResponse(visits);
}

// Route handlers
const ROUTES: Record<string, (req: Request, env: Env) => Promise<Response>> = {
	"get-places": handleGetPlaces,
	"get-place": handleGetPlace,
	"get-place-reviews": handleGetPlaceReviews,
	"get-stats": handleGetStats,
	"get-user": handleGetUser,
	"get-favorites": handleGetFavorites,
	"add-favorite": handleAddFavorite,
	"remove-favorite": handleRemoveFavorite,
	"add-review": handleAddReview,
	"get-reviews": handleGetReviews,
	"record-visit": handleRecordVisit,
	"get-visits": handleGetVisits,
};

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		const url = new URL(request.url);
		const path = url.pathname;

		// Handle API routes
		const apiMatch = path.match(/^\/functions\/v1\/(.+)$/);
		if (apiMatch) {
			const functionName = apiMatch[1];
			const handler = ROUTES[functionName];
			if (handler) {
				return handler(request, env);
			}
			return jsonResponse({ error: `Unknown function: ${functionName}` }, 404);
		}

		// Let Workers Assets handle static files and SPA fallback
		return fetch(request);
	},
};
