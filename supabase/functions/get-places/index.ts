import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient, transformPlace, haversineDistance } from '../_shared/utils.ts'

const MAX_LIMIT = 200

serve(async (req) => {
  const url = new URL(req.url)
  const lat = parseFloat(url.searchParams.get('lat') ?? '48.8566')
  const lng = parseFloat(url.searchParams.get('lng') ?? '2.3522')
  const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '150'), MAX_LIMIT)
  const type = url.searchParams.get('type') ?? ''
  const minRating = url.searchParams.get('minRating') ?? ''
  const sortBy = url.searchParams.get('sortBy') ?? ''
  const amenities = url.searchParams.get('amenities') ?? ''

  const supabase = getAdminClient()

  let query = supabase
    .from('place')
    .select(
      `
      id, name, latitude, longitude, rating, ratingCount, typeId,
      address, descriptions, photos, google_place_id,
      type (id, englishName, originalCode),
      placeServices (serviceId, service (id, code, label, originalCode))
    `,
    )
    .gte('latitude', lat - 0.5)
    .lte('latitude', lat + 0.5)
    .gte('longitude', lng - 0.5)
    .lte('longitude', lng + 0.5)

  if (type) {
    query = query.eq('typeId', type)
  }
  if (minRating) {
    query = query.gte('rating', parseFloat(minRating))
  }
  if (sortBy === 'rating') {
    query = query.order('rating', { ascending: false })
  }

  const { data: places, error } = await query.limit(limit * 2)

  if (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to fetch places', details: error.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )
  }

  // Filter by amenities
  let filtered = places
  if (amenities) {
    const requested = amenities.split(',')
    filtered = places.filter((place: any) => {
      const serviceCodes = place.placeServices?.map(
        (ps: any) => ps.service?.code,
      ) ?? []
      return requested.every((amenity: string) =>
        serviceCodes.some((code: string | undefined) => code === amenity),
      )
    })
  } else {
    filtered = places
  }

  // Sort by distance
  filtered.sort((a: any, b: any) => {
    const distA = haversineDistance(lat, lng, a.latitude, a.longitude)
    const distB = haversineDistance(lat, lng, b.latitude, b.longitude)
    return distA - distB
  })

  const result = filtered.slice(0, limit).map((place: any) => {
    const transformed = transformPlace(place)
    transformed.distance = haversineDistance(
      lat,
      lng,
      place.latitude,
      place.longitude,
    )
    return transformed
  })

  return new Response(JSON.stringify(result), {
    headers: { 'Content-Type': 'application/json' },
  })
}
