const axios = require("axios");
const cloudscraper = require("cloudscraper");
const cld = require("cld");
const { URL } = require("url");

const PARK4NIGHT_BASE_URL = "https://guest.park4night.com/services/V4.1";
const PARK4NIGHT_API_URL = "https://park4night.com/api";

// Create a shared cookie jar for cloudscraper requests
const jar = cloudscraper.jar();
jar.setCookie("PHPSESSID=269hsvp3b5i5eoo4tvulf03gkv", "https://park4night.com");

/**
 * Detect the language of a text string using cld (Compact Language Detector).
 * Returns an object with { iso639_1, iso639_2, name } or null if detection fails.
 */
function detectLanguage(text) {
	if (!text || typeof text !== "string" || text.length < 10) {
		return null;
	}

	return new Promise((resolve) => {
		cld.detect(text, (err, result) => {
			if (
				err ||
				!result ||
				!result.languages ||
				result.languages.length === 0
			) {
				resolve(null);
				return;
			}

			const lang = result.languages[0];
			// Only return if confidence is reasonable (> 75%)
			if (lang.percent < 75) {
				resolve(null);
				return;
			}

			resolve({
				iso639_1: lang.code,
				iso639_2: lang.name, // cld uses name for ISO 639-2
				name: lang.name,
				confidence: lang.percent,
			});
		});
	});
}

/**
 * Build a URL with query parameters.
 */
function buildUrl(baseUrl, params) {
	const url = new URL(baseUrl);
	Object.entries(params).forEach(([key, value]) => {
		if (value !== undefined && value !== null) {
			url.searchParams.append(key, String(value));
		}
	});
	return url.toString();
}

/**
 * Fetch places from Park4Night guest API.
 * Returns up to 100 places with rich data including photos, services, pricing.
 */
const getPlaces = async (latitude, longitude) => {
	try {
		const response = await axios.get(
			`${PARK4NIGHT_BASE_URL}/lieuxGetFilter.php`,
			{
				params: { latitude, longitude },
				timeout: 10000,
			},
		);
		const places = (response.data.lieux || []).map((p) => ({
			id: parseInt(p.id, 10),
			name: p.titre || "",
			latitude: parseFloat(p.latitude),
			longitude: parseFloat(p.longitude),
			type: p.code || "",
			description: p.description_en,
			address: [p.route, p.ville, p.code_postal, p.pays]
				.filter(Boolean)
				.join(", "),
			rating: p.note_moyenne ? parseFloat(p.note_moyenne) : 0,
			rawData: {
				// Core fields
				id: p.id,
				titre: p.titre,
				name: p.name,
				latitude: p.latitude,
				longitude: p.longitude,
				code: p.code,

				// Multi-language descriptions
				description_fr: p.description_fr || "",
				description_en: p.description_en || "",
				description_de: p.description_de || "",
				description_es: p.description_es || "",
				description_it: p.description_it || "",
				description_nl: p.description_nl || "",

				// Address
				route: p.route || "",
				ville: p.ville || "",
				code_postal: p.code_postal || "",
				pays: p.pays || "",
				pays_iso: p.pays_iso || "",

				// Pricing
				prix_stationnement: p.prix_stationnement || "",
				prix_services: p.prix_services || "",

				// Access
				hauteur_limite: p.hauteur_limite || "",
				nb_places: p.nb_places || "",
				publique: p.publique,

				// Contact
				tel: p.tel || "",
				mail: p.mail || "",
				site_internet: p.site_internet || "",

				// Services (boolean flags)
				animaux: p.animaux,
				point_eau: p.point_eau,
				eau_noire: p.eau_noire,
				eau_usee: p.eau_usee,
				wc_public: p.wc_public,
				poubelle: p.poubelle,
				douche: p.douche,
				boulangerie: p.boulangerie,
				electricite: p.electricite,
				wifi: p.wifi,
				piscine: p.piscine,
				laverie: p.laverie,

				// Activities
				rando: p.rando,
				vtt: p.vtt,
				escalade: p.escalade,
				peche: p.peche,
				baignade: p.baignade,

				// Stats
				note_moyenne: p.note_moyenne,
				nb_commentaires: p.nb_commentaires,
				nb_photos: p.nb_photos,
				nb_visites: p.nb_visites,

				// Photos
				photos: p.photos || [],

				// Metadata
				date_creation: p.date_creation || "",
				online_booking: p.online_booking || false,
			},
		}));
		return places;
	} catch (error) {
		console.error("Error fetching from Park4Night guest API:", error.message);
		throw error;
	}
};

/**
 * Fetch places from Park4Night new API using cloudscraper.
 * Returns up to 200 places.
 */
const getPlacesNew = async (latitude, longitude, radius = 200, lang = "en") => {
	try {
		const url = buildUrl(`${PARK4NIGHT_API_URL}/places/around`, {
			lat: latitude,
			lng: longitude,
			radius,
			filter: "{}",
			lang,
		});

		const response = await cloudscraper.get({
			url,
			jar: jar,
			timeout: 15000,
			gs: true, // Enable Cloudflare bypass
		});

		let data;
		try {
			// API responses may be base64 encoded
			let jsonStr = response;
			if (
				!response.startsWith("{") &&
				!response.startsWith("[") &&
				response.length > 10
			) {
				jsonStr = Buffer.from(response, "base64").toString("utf8");
			}
			data = JSON.parse(jsonStr);
		} catch (parseError) {
			console.error(
				"Error parsing Park4Night new API response:",
				parseError.message,
			);
			return [];
		}

		const places = (Array.isArray(data) ? data : []).map((p) => ({
			id: p.id,
			name: p.title_short,
			latitude: p.lat,
			longitude: p.lng,
			type: p.type?.code,
			description: p.description,
			address: p.address
				? (typeof p.address === "string"
						? p.address
						: `${p.address.street}, ${p.address.city}, ${p.address.country}`.trim())
				: [p.route, p.ville, p.code_postal, p.pays].filter(Boolean).join(", "),
			rating: p.rating,
			rawData: p,
		}));
		return places;
	} catch (error) {
		console.error("Error fetching from Park4Night new API:", error.message);
		return []; // Fallback to empty array
	}
};

/**
 * Fetch reviews for a place from the guest API with language detection.
 * Each review object will include a `language` field with detected language info.
 */
const getReviews = async (placeId) => {
	try {
		const response = await axios.get(`${PARK4NIGHT_BASE_URL}/commGet.php`, {
			params: { lieu_id: placeId },
			timeout: 10000,
		});
		if (response.data.status === "OK") {
			const reviews = response.data.commentaires || [];
			// Add language detection to each review (parallel)
			const reviewsWithLanguage = await Promise.all(
				reviews.map(async (review) => ({
					...review,
					language: await detectLanguage(review.commentaire),
				})),
			);
			return reviewsWithLanguage;
		}
		return [];
	} catch (error) {
		console.error("Error fetching reviews from Park4Night:", error.message);
		return [];
	}
};

/**
 * Fetch reviews for a place from the new API using cloudscraper.
 * NOTE: This endpoint requires authentication and may return 404 for unauthenticated requests.
 * Each review object will include a `language` field with detected language info.
 */
const getReviewsNew = async (placeId, lang = "en") => {
	try {
		const url = buildUrl(`${PARK4NIGHT_API_URL}/places/${placeId}/reviews`, {
			lang,
		});

		const response = await cloudscraper.get({
			url,
			jar: jar,
			timeout: 15000,
			gs: true, // Enable Cloudflare bypass
		});

		let data;
		try {
			data = JSON.parse(response);
		} catch (parseError) {
			console.error(
				"Error parsing Park4Night new API reviews response:",
				parseError.message,
			);
			return [];
		}

		const reviews = Array.isArray(data) ? data : [];
		// Add language detection to each review (parallel)
		const reviewsWithLanguage = await Promise.all(
			reviews.map(async (review) => ({
				...review,
				language: await detectLanguage(
					review.commentaire,
				),
			})),
		);
		return reviewsWithLanguage;
	} catch (error) {
		console.error("Error fetching reviews from new API:", error.message);
		return [];
	}
};

/**
 * Fetch detailed place info from the new API using cloudscraper.
 */
const getPlaceDetail = async (placeId, lang = "en") => {
	try {
		const url = buildUrl(`${PARK4NIGHT_API_URL}/places/${placeId}`, {
			lang,
		});

		const response = await cloudscraper.get({
			url,
			jar: jar,
			timeout: 15000,
			gs: true, // Enable Cloudflare bypass
		});

		let data;
		try {
			data = JSON.parse(response);
		} catch (parseError) {
			console.error(
				"Error parsing Park4Night place detail response:",
				parseError.message,
			);
			return null;
		}

		if (data) {
			// Standardize detail output
			return {
				id: data.id,
name: data.title_short,
				latitude: data.lat,
				longitude: data.lng,
				type: data.type?.code,
				description: data.description,
				address: data.address
					? (typeof data.address === "string"
							? data.address
							: `${data.address.street}, ${data.address.city}, ${data.address.country}`.trim())
					: [data.route, data.ville, data.code_postal, data.pays]
							.filter(Boolean)
							.join(", "),
rating: data.rating,
				rawData: data,
			};
		}
		return data;
	} catch (error) {
		console.error("Error fetching place detail:", error.message);
		return null;
	}
};

module.exports = {
	getPlaces,
	getPlacesNew,
	getReviews,
	getReviewsNew,
	getPlaceDetail,
	detectLanguage, // Export for testing
};
