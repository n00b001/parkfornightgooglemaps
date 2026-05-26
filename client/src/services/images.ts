/**
 * Image URL utilities for Park4Night app.
 *
 * Constructs image URLs preferring local paths (served by the API server)
 * with fallback to CDN URLs.
 */

const API_URL = import.meta.env.VITE_API_URL || '';

/**
 * Photo object from the Place.photos array.
 * May have local paths (path_thumb, path_large) and/or CDN URLs (url_thumb, url_large).
 */
export interface Photo {
  id?: string;
  numero?: string;
  url_thumb?: string;
  url_large?: string;
  path_thumb?: string;
  path_large?: string;
  thumbUrl?: string; // Legacy field from localData normalization
  largeUrl?: string; // Legacy field from localData normalization
  lien_mini?: string; // French API field
  lien_grand?: string; // French API field
}

/**
 * Get the thumbnail URL for a photo, preferring local path over CDN URL.
 */
export function getPhotoThumbUrl(photo: Photo | undefined): string | undefined {
  if (!photo) return undefined;

  // Local path (served by API server)
  if (photo.path_thumb) {
    return `${API_URL}/${photo.path_thumb}`;
  }

  // Legacy normalized field
  if (photo.thumbUrl) {
    return photo.thumbUrl;
  }

  // CDN URL fallback
  if (photo.url_thumb) {
    return photo.url_thumb;
  }

  // French API field
  if (photo.lien_mini) {
    return photo.lien_mini;
  }

  return undefined;
}

/**
 * Get the large URL for a photo, preferring local path over CDN URL.
 */
export function getPhotoLargeUrl(photo: Photo | undefined): string | undefined {
  if (!photo) return undefined;

  // Local path (served by API server)
  if (photo.path_large) {
    return `${API_URL}/${photo.path_large}`;
  }

  // Legacy normalized field
  if (photo.largeUrl) {
    return photo.largeUrl;
  }

  // CDN URL fallback
  if (photo.url_large) {
    return photo.url_large;
  }

  // French API field
  if (photo.lien_grand) {
    return photo.lien_grand;
  }

  return undefined;
}

/**
 * Vehicle type icon mapping.
 * Maps Park4Night vehicle type codes to local icon paths.
 */
const VEHICLE_ICONS: Record<string, string> = {
  NC: 'images/icons/vehicule_nc.png',  // Caravan
  GV: 'images/icons/vehicule_gv.png',  // Motorhome
  UL: 'images/icons/vehicule_ul.png',  // Ultralight
  V:  'images/icons/vehicule_v.png',   // Vehicle
  M:  'images/icons/vehicule_m.png',   // Motorcycle
  T:  'images/icons/vehicule_t.png',   // Tent
  P:  'images/icons/vehicule_p.png',   // Car
  I:  'images/icons/vehicule_i.png',   // Other
};

// CDN fallback URLs for vehicle icons
const CDN_BASE = 'https://cdn6.park4night.com/images/bitmap/vehicules';
const CDN_VERSION = '2bf1e1a';

/**
 * Get the avatar URL for a review author based on their vehicle type.
 * Park4Night uses vehicle type icons as user avatars (not profile pictures).
 */
export function getVehicleIconUrl(vehicleType: string | undefined): string | undefined {
  if (!vehicleType) return undefined;

  const localPath = VEHICLE_ICONS[vehicleType];
  if (localPath) {
    // Return local path - client will try to load it, and if it fails (404),
    // the onError handler can fall back to CDN
    return `${API_URL}/${localPath}`;
  }

  return undefined;
}

/**
 * Get the CDN fallback URL for a vehicle icon.
 */
export function getVehicleIconCdnUrl(vehicleType: string | undefined): string | undefined {
  if (!vehicleType) return undefined;

  const filename = VEHICLE_ICONS[vehicleType];
  if (filename) {
    const basename = filename.split('/').pop();
    return `${CDN_BASE}/${basename}?v=${CDN_VERSION}`;
  }

  return undefined;
}

/**
 * Default avatar placeholder (SVG data URI for a generic user icon).
 */
export const DEFAULT_AVATAR =
  'data:image/svg+xml,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
    'stroke="%239CA3AF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>' +
    '</svg>'
  );
