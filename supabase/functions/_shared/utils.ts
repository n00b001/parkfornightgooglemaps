import { createClient } from 'npm:@supabase/supabase-js'

export const supabaseUrl = Deno.env.get('SUPABASE_URL')!
export const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!

export function getAdminClient() {
  return createClient(supabaseUrl, serviceKey)
}

// Map PlaceType.originalCode to client-friendly type keys.
// Must match TYPE_NAMES in PlaceDetails.tsx.
export const TYPE_CODE_MAP: Record<string, string> = {
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
}

// Map Service.code to client amenity key.
// Must match AMENITIES in PlaceDetails.tsx.
export const SERVICE_AMENITY_MAP: Record<string, string> = {
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
  toilettes_public: 'publicToilet',
}

function haversineDistance(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLng = ((lng2 - lng1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) *
      Math.sin(dLng / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return R * c
}

export function transformPlace(place: any): any {
  if (!place) return place

  const result = { ...place }

  // Map type code to client-friendly type string
  if (place.type && place.type.originalCode) {
    result.type = TYPE_CODE_MAP[place.type.originalCode]
  }

  // Photos use R2 URLs only
  if (Array.isArray(place.photos)) {
    result.photos = place.photos.map((photo: any) => ({
      ...photo,
      thumbUrl: photo.r2_url_thumb ?? '',
      largeUrl: photo.r2_url_large ?? '',
    }))
  }

  // Build amenity fields from placeServices relation
  if (Array.isArray(place.placeServices)) {
    for (const ps of place.placeServices) {
      if (ps.service && ps.service.code) {
        const amenityKey = SERVICE_AMENITY_MAP[ps.service.code]
        if (amenityKey) {
          result[amenityKey] = '1'
        }
      }
    }
  }

  // Extract description from descriptions JSON
  if (place.descriptions && typeof place.descriptions === 'object') {
    result.description = place.descriptions.en ?? ''
  }

  // Extract address string from address JSON
  if (place.address && typeof place.address === 'object') {
    const parts = [
      place.address.street,
      place.address.city,
      place.address.zipcode,
      place.address.country,
    ].filter(Boolean)
    result.address = parts.join(', ')
  }

  return result
}

export { haversineDistance }
