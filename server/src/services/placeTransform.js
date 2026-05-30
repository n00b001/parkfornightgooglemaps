/**
 * Map PlaceType.originalCode to client-friendly type keys.
 * Must match the TYPE_CODE_MAP in localData.js and TYPE_NAMES in PlaceDetails.tsx.
 */
const TYPE_CODE_MAP = {
  APN: 'rvPark',
  P: 'parking',
  PN: 'naturalParking',
  PJ: 'campsite',
  C: 'campsite',
  ACC_G: 'freeRvPark',
  DS: 'parking',
  AR: 'restArea',
  PSS: 'onSiteParking',
  ASS: 'serviceArea',
  ACC_PR: 'private',
  ACC_P: 'paid',
  F: 'closed',
  OR: 'restArea',
  EP: 'parking',
  CAR: 'campsite',
  H: 'campsite',
  HP: 'campsite',
  A: 'serviceArea',
  CS: 'campsite',
  CL: 'naturalParking',
  AL: 'rvPark',
  S: 'serviceArea',
  EC: 'campsite',
  FM: 'campsite',
  G: 'campsite',
  M: 'campsite',
  R: 'campsite',
  RH: 'campsite',
  T: 'campsite',
};

/**
 * Map Service.code to client amenity key.
 * Must match SERVICE_AMENITY_MAP in localData.js and AMENITIES in PlaceDetails.tsx.
 */
const SERVICE_AMENITY_MAP = {
  point_eau: 'waterPoint',
  eau: 'waterPoint',
  electricite: 'electricity',
  électricité: 'electricity',
  poubelle: 'trashCan',
  wifi: 'wifi',
  vidange_eaux_usees: 'wasteWaterDrain',
  vidance_eaux_grises: 'wasteWaterDrain',
  vidange_wc: 'toiletDrain',
  vidange_chasse: 'toiletDrain',
  douche: 'shower',
  baignade: 'swimming',
  animaux: 'pets',
  aire_pique_nique: 'picnicArea',
  laverie: 'laundry',
  wc_public: 'publicToilet',
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
    result.type = TYPE_CODE_MAP[place.type.originalCode] || place.type.englishName || 'parking';
  }

  // Ensure photos use R2 URLs
  if (Array.isArray(place.photos)) {
    result.photos = place.photos.map((photo) => ({
      ...photo,
      thumbUrl: photo.r2_url_thumb || photo.path_thumb || photo.thumbUrl || '',
      largeUrl: photo.r2_url_large || photo.path_large || photo.largeUrl || '',
    }));
  }

  // Build amenity fields from services JSON (if present)
  if (Array.isArray(place.services)) {
    for (const service of place.services) {
      const code = typeof service === 'string' ? service : service.code;
      const amenityKey = SERVICE_AMENITY_MAP[code];
      if (amenityKey) {
        result[amenityKey] = '1';
      }
    }
  }

  // Build amenity fields from placeServices relation (if loaded)
  if (Array.isArray(place.placeServices)) {
    for (const ps of place.placeServices) {
      if (ps.service && ps.service.code) {
        const amenityKey = SERVICE_AMENITY_MAP[ps.service.code];
        if (amenityKey) {
          result[amenityKey] = '1';
        }
      }
    }
  }

  // Extract description from descriptions JSON
  if (place.descriptions && typeof place.descriptions === 'object') {
    result.description =
      place.descriptions.default || place.descriptions.en || '';
  }

  // Extract address string from address JSON
  if (place.address && typeof place.address === 'object') {
    const parts = [place.address.street, place.address.city, place.address.zipcode, place.address.country].filter(Boolean);
    result.address = parts.join(', ');
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
