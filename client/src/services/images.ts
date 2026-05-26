/**
 * Image URL utilities for Park4Night app.
 *
 * All images are served from Firestore via the API server.
 * NO CDN fallback — this project supercedes Park4Night entirely.
 */

const API_URL = import.meta.env.VITE_API_URL || "";

/**
 * Photo object from the Place.photos array.
 * Contains local paths (path_thumb, path_large) set by the scraper.
 * These are converted to Firestore URLs at runtime.
 */
export interface Photo {
	id?: string;
	numero?: string;
	path_thumb: string;
	path_large: string;
}

/**
 * Parse a local image path into Firestore route params.
 * e.g., "images/places/514700/1582655_thumb.jpg" -> { placeId: "514700", filename: "1582655_thumb.jpg" }
 */
function parseImagePath(
	localPath: string,
): { placeId: string; filename: string } | null {
	const match = localPath.match(/images\/places\/(\d+)\/(.+)$/);
	if (!match) return null;
	return { placeId: match[1], filename: match[2] };
}

/**
 * Get the thumbnail URL for a photo (served from Firestore).
 * Returns undefined if no local path exists — this is a fatal error.
 */
export function getPhotoThumbUrl(photo: Photo | undefined): string | undefined {
	if (!photo || !photo.path_thumb) return undefined;
	const parsed = parseImagePath(photo.path_thumb);
	if (!parsed) return undefined;
	return `${API_URL}/images/${parsed.placeId}/${parsed.filename}`;
}

/**
 * Get the large URL for a photo (served from Firestore).
 * Returns undefined if no local path exists — this is a fatal error.
 */
export function getPhotoLargeUrl(photo: Photo | undefined): string | undefined {
	if (!photo || !photo.path_large) return undefined;
	const parsed = parseImagePath(photo.path_large);
	if (!parsed) return undefined;
	return `${API_URL}/images/${parsed.placeId}/${parsed.filename}`;
}

/**
 * Vehicle type icon mapping.
 * Maps Park4Night vehicle type codes to Firestore-served icon URLs.
 */
const VEHICLE_ICONS: Record<string, string> = {
	NC: "vehicule_nc.png",
	GV: "vehicule_gv.png",
	UL: "vehicule_ul.png",
	V: "vehicule_v.png",
	M: "vehicule_m.png",
	T: "vehicule_t.png",
	P: "vehicule_p.png",
	I: "vehicule_i.png",
};

/**
 * Get the avatar URL for a review author based on their vehicle type.
 * Served from Firestore via /images/icons/:filename
 * Returns undefined if no icon exists — this is a fatal error.
 */
export function getVehicleIconUrl(
	vehicleType: string | undefined,
): string | undefined {
	if (!vehicleType) return undefined;
	const filename = VEHICLE_ICONS[vehicleType];
	if (!filename) return undefined;
	return `${API_URL}/images/icons/${filename}`;
}
