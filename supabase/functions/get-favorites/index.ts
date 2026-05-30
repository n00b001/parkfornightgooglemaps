import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient, transformPlace } from '../_shared/utils.ts'
import { getAuthUser } from '../_shared/auth.ts'

serve(async (req) => {
  const user = getAuthUser(req)

  const supabase = getAdminClient()

  const { data: favorites, error } = await supabase
    .from('favorite')
    .select(
      `
      placeId,
      place (
        id, name, latitude, longitude, rating, ratingCount, typeId,
        address, descriptions, photos, google_place_id,
        type (id, englishName, originalCode),
        placeServices (serviceId, service (id, code, label, originalCode))
      )
    `,
    )
    .eq('userId', user.id)

  if (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to fetch favorites', details: error.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )
  }

  const places = favorites
    .map((f: any) => transformPlace(f.place))
    .filter(Boolean)

  return new Response(JSON.stringify(places), {
    headers: { 'Content-Type': 'application/json' },
  })
})
