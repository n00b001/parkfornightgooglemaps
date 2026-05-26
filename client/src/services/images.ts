/**
 * Image URL utilities for Park4Night app.
 *
 * ALL images come from local paths served by the API server.
 * NO CDN fallback — this project supercedes Park4Night entirely.
 */

const API_URL = import.meta.env.VITE_API_URL || "";

/**
 * Photo object from the Place.photos array.
 * Must have local paths (path_thumb, path_large) set by the scraper.
 */
export interface Photo {
	id?: string;
	numero?: string;
	path_thumb: string;
	path_large: string;
}

/**
 * Get the thumbnail URL for a photo.
 * Returns undefined if no local path exists — this is a fatal error.
 */
export function getPhotoThumbUrl(photo: Photo | undefined): string | undefined {
	if (!photo || !photo.path_thumb) return undefined;
	return `${API_URL}/${photo.path_thumb}`;
}

/**
 * Get the large URL for a photo.
 * Returns undefined if no local path exists — this is a fatal error.
 */
export function getPhotoLargeUrl(photo: Photo | undefined): string | undefined {
	if (!photo || !photo.path_large) return undefined;
	return `${API_URL}/${photo.path_large}`;
}

/**
 * Vehicle type icon mapping.
 * Maps Park4Night vehicle type codes to local icon paths.
 */
const VEHICLE_ICONS: Record<string, string> = {
	NC: "images/icons/vehicule_nc.png",
	GV: "images/icons/vehicule_gv.png",
	UL: "images/icons/vehicule_ul.png",
	V: "images/icons/vehicule_v.png",
	M: "images/icons/vehicule_m.png",
	T: "images/icons/vehicule_t.png",
	P: "images/icons/vehicule_p.png",
	I: "images/icons/vehicule_i.png",
};

/**
 * Get the avatar URL for a review author based on their vehicle type.
 * Returns undefined if no icon exists — this is a fatal error.
 */
export function getVehicleIconUrl(
	vehicleType: string | undefined,
): string | undefined {
	if (!vehicleType) return undefined;
	const localPath = VEHICLE_ICONS[vehicleType];
	if (!localPath) return undefined;
	return `${API_URL}/${localPath}`;
}
