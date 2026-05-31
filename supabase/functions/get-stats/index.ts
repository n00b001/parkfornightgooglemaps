import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient } from '../_shared/utils.ts'

serve(async (_req) => {
  const supabase = getAdminClient()

  const { count: totalPlaces } = await supabase
    .from('place')
    .select('*', { count: 'exact', head: true })

  const { count: totalReviews } = await supabase
    .from('review')
    .select('*', { count: 'exact', head: true })

  const { count: placesWithReviews } = await supabase
    .from('place')
    .select('*', { count: 'exact', head: true })
    .is('reviews', null)
    .neq('reviews', null)

  return new Response(
    JSON.stringify({
      totalPlaces: totalPlaces ?? 0,
      totalReviews: totalReviews ?? 0,
      placesWithReviews: placesWithReviews ?? 0,
    }),
    { headers: { 'Content-Type': 'application/json' } },
  )
})
