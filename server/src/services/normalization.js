/**
 * Map Park4Night type codes to English type values.
 */
const TYPE_CODE_MAP = {
	APN: "rvPark", // Aire de camping-car → rvPark
	P: "parking", // Parking area → parking
	PN: "naturalParking", // Parking naturel → naturalParking
	PJ: "campsite", // Aire de jeu → campsite
	C: "campsite", // Camping → campsite
	ACC_G: "freeRvPark", // Aire gratuite → freeRvPark
	DS: "parking", // Dépannage → parking
	AR: "restArea", // Aire de repos → restArea
	PSS: "onSiteParking", // Parking sur site → onSiteParking
	ASS: "serviceArea", // Aire service → serviceArea
	ACC_PR: "private", // Accès privé → private
	ACC_P: "paid", // Accès payant → paid
	F: "closed", // Fermé → closed
	OR: "restArea", // Aire de repos officielle → restArea
	EP: "parking", // Espace de parking → parking
};

/**
 * Map Park4Night service codes to English amenity keys.
 */
const SERVICE_AMENITY_MAP = {
	point_eau: "waterPoint",
	eau: "waterPoint",
	electricite: "electricity",
	"électricité": "electricity",
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
 * Normalize a place object to the structure expected by the Prisma model and the frontend.
 */
function normalizePlace(p) {
	if (!p) return null;

	// Handle both guest API and new API structures
	const id = parseInt(p.id || p.lieu_id, 10);
	const name = p.name || p.titre || p.title || p.title_short || "";
	const latitude = parseFloat(p.latitude || p.lat);
	const longitude = parseFloat(p.longitude || p.lng);
	const rawTypeCode = p.code || (p.type && p.type.code) || "";
	const type = TYPE_CODE_MAP[rawTypeCode] || "parking";

	let address = "";
	if (typeof p.address === "string") {
		address = p.address;
	} else if (p.address && typeof p.address === "object") {
		address = [p.address.street, p.address.city, p.address.zipcode, p.address.country]
			.filter(Boolean)
			.join(", ");
	} else {
		address = [p.route, p.ville, p.code_postal, p.pays].filter(Boolean).join(", ");
	}

	const rating = p.rating || (p.note_moyenne ? parseFloat(p.note_moyenne) : 0);
	const reviewCount = p.review_count || p.nb_commentaires || p.nb_comm || 0;
	const photoCount = p.photo_count || p.nb_photos || 0;

	// Extract amenities
	const amenities = {};
	// Guest API style (top-level properties)
	Object.keys(SERVICE_AMENITY_MAP).forEach(key => {
		if (p[key] === "1" || p[key] === 1 || p[key] === true) {
			amenities[SERVICE_AMENITY_MAP[key]] = "1";
		}
	});
	// New API style (services array)
	if (Array.isArray(p.services)) {
		p.services.forEach(s => {
			const code = s.code || s;
			const mappedKey = SERVICE_AMENITY_MAP[code];
			if (mappedKey) {
				amenities[mappedKey] = "1";
			}
		});
	}

	// Photos normalization
	let photos = [];
	if (Array.isArray(p.photos)) {
		photos = p.photos.map(photo => ({
			id: photo.id,
			url_large: photo.url_large || photo.lien_grand || photo.largeUrl,
			url_thumb: photo.url_thumb || photo.lien_mini || photo.thumbUrl
		}));
	}

	return {
		id,
		name,
		latitude,
		longitude,
		type,
		description: p.description || p.description_en || p.description_fr || "",
		address,
		rating,
		reviewCount,
		photoCount,
		photos,
		...amenities,
		rawData: p,
		lastFetched: new Date()
	};
}

module.exports = {
	normalizePlace,
	TYPE_CODE_MAP,
	SERVICE_AMENITY_MAP
};
