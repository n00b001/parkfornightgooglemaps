import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient } from '../_shared/utils.ts'

serve(async (req) => {
  const url = new URL(req.url)
  const placeId = parseInt(
    url.searchParams.get('placeId') ?? url.pathname.split('/').pop() ?? '',
  )

  if (isNaN(placeId)) {
    return new Response(JSON.stringify({ error: 'Invalid place ID' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const supabase = getAdminClient()

  const { data: reviews, error } = await supabase
    .from('review')
    .select('*')
    .eq('placeId', placeId)
    .order('createdAt', { ascending: false })

  if (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to fetch reviews', details: error.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )
  }

  return new Response(JSON.stringify({ reviews }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
