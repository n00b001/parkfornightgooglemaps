import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient } from '../_shared/utils.ts'
import { getAuthUser } from '../_shared/auth.ts'

serve(async (req) => {
  if (req.method !== 'DELETE') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const user = getAuthUser(req)
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

  const { error } = await supabase
    .from('favorite')
    .delete()
    .eq('userId', user.id)
    .eq('placeId', placeId)

  if (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to remove favorite', details: error.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )
  }

  return new Response(JSON.stringify({ success: true }), {
    headers: { 'Content-Type': 'application/json' },
  })
}
