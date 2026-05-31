/**
 * Map PlaceType.originalCode to client-friendly type keys.
 * Must match TYPE_NAMES in PlaceDetails.tsx.
 */
const TYPE_CODE_MAP = {
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

/**
 * Map Service.code to client amenity key.
 * Must match AMENITIES in PlaceDetails.tsx.
 */
const SERVICE_AMENITY_MAP = {
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
	wc_public: "publicToilet",
};

/**
 * Transform a place from the normalized DB schema to the flat format
 * expected by the client. Handles:
 * - typeId → type string (e.g., 'rvPark')
 * - R2 URL priority for photos
 * - Service codes → amenity boolean fields
 */
function transformPlace(place) {
	if (!place) return place;

	const result = { ...place };

	// Map type code to client-friendly type string
	if (place.type && place.type.originalCode) {
		result.type = TYPE_CODE_MAP[place.type.originalCode];
	} else if (place.rawData && place.rawData.code) {
		result.type = TYPE_CODE_MAP[place.rawData.code];
	}

	// Photos use R2 URLs only, with fallback to rawData photos for live results
	if (Array.isArray(place.photos)) {
		result.photos = place.photos.map((photo) => ({
			...photo,
			thumbUrl: photo.r2_url_thumb ?? photo.path_thumb ?? "",
			largeUrl: photo.r2_url_large ?? photo.path_large ?? "",
		}));
	} else if (place.rawData && Array.isArray(place.rawData.photos)) {
		result.photos = place.rawData.photos.map((photo) => ({
			...photo,
			thumbUrl: photo.path_thumb ?? "",
			largeUrl: photo.path_large ?? "",
		}));
	}

	// Build amenity fields from services JSON (if present)
	if (Array.isArray(place.services)) {
		for (const service of place.services) {
			const code = typeof service === "string" ? service : service.code;
			const amenityKey = SERVICE_AMENITY_MAP[code];
			if (amenityKey) {
				result[amenityKey] = "1";
			}
		}
	}

	// Build amenity fields from placeServices relation (if loaded)
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

	// Extract description from descriptions JSON or rawData
	if (place.descriptions && typeof place.descriptions === "object") {
		result.description = place.descriptions.en ?? "";
	} else if (place.rawData && place.rawData.description_en) {
		result.description = place.rawData.description_en;
	}

	// Extract address string from address JSON or rawData
	if (place.address && typeof place.address === "object") {
		const parts = [
			place.address.street,
			place.address.city,
			place.address.zipcode,
			place.address.country,
		].filter(Boolean);
		result.address = parts.join(", ");
	} else if (place.rawData && typeof place.rawData === "object") {
		// Park4night guest API format
		const parts = [
			place.rawData.route,
			place.rawData.ville,
			place.rawData.code_postal,
			place.rawData.pays,
		].filter(Boolean);
		if (parts.length > 0) {
			result.address = parts.join(", ");
		}
	}

	// Build amenity fields from rawData boolean flags
	if (place.rawData && typeof place.rawData === "object") {
		Object.keys(SERVICE_AMENITY_MAP).forEach((code) => {
			if (place.rawData[code] === "1" || place.rawData[code] === 1 || place.rawData[code] === true) {
				const amenityKey = SERVICE_AMENITY_MAP[code];
				if (amenityKey) {
					result[amenityKey] = "1";
				}
			}
		});
	}

	return result;
}

/**
 * Transform an array of places.
 */
function transformPlaces(places) {
	return places.map(transformPlace);
}

module.exports = { transformPlace, transformPlaces, TYPE_CODE_MAP };
