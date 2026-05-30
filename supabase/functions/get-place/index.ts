import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient, transformPlace } from '../_shared/utils.ts'

serve(async (req) => {
  const url = new URL(req.url)
  const id = parseInt(url.searchParams.get('id') ?? url.pathname.split('/').pop() ?? '')

  if (isNaN(id)) {
    return new Response(JSON.stringify({ error: 'Invalid place ID' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const supabase = getAdminClient()

  const { data: place, error } = await supabase
    .from('place')
    .select(
      `
      id, name, latitude, longitude, rating, ratingCount, typeId,
      address, descriptions, photos, google_place_id,
      type (id, englishName, originalCode),
      placeServices (serviceId, service (id, code, label, originalCode)),
      placeActivities (activityId, activity (id, code, label, originalCode))
    `,
    )
    .eq('id', id)
    .single()

  if (error || !place) {
    return new Response(JSON.stringify({ error: 'Place not found' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  return new Response(JSON.stringify(transformPlace(place)), {
    headers: { 'Content-Type': 'application/json' },
  })
}
