import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient } from '../_shared/utils.ts'
import { getAuthUser } from '../_shared/auth.ts'

serve(async (req) => {
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const user = getAuthUser(req)
  const body = await req.json()
  const placeId = parseInt(body.placeId)

  if (isNaN(placeId)) {
    return new Response(JSON.stringify({ error: 'Invalid place ID' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const supabase = getAdminClient()

  const { data, error } = await supabase
    .from('visit')
    .upsert(
      { userId: user.id, placeId, visitedAt: new Date().toISOString() },
      { onConflict: 'userId_placeId' },
    )
    .select()
    .single()

  if (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to record visit', details: error.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )
  }

  return new Response(JSON.stringify(data), {
    headers: { 'Content-Type': 'application/json' },
  })
})
