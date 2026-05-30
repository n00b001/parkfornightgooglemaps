import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient, transformPlace } from '../_shared/utils.ts'
import { getAuthUser } from '../_shared/auth.ts'

serve(async (req) => {
  const user = getAuthUser(req)

  const supabase = getAdminClient()

  const { data: visits, error } = await supabase
    .from('visit')
    .select(
      `
      placeId, visitedAt,
      place (
        id, name, latitude, longitude, rating, ratingCount, typeId,
        address, descriptions, photos, google_place_id,
        type (id, englishName, originalCode),
        placeServices (serviceId, service (id, code, label, originalCode))
      )
    `,
    )
    .eq('userId', user.id)
    .order('visitedAt', { ascending: false })

  if (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to fetch visits', details: error.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )
  }

  const result = visits.map((v: any) => ({
    ...v,
    place: transformPlace(v.place),
  }))

  return new Response(JSON.stringify(result), {
    headers: { 'Content-Type': 'application/json' },
  })
})
