import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient } from '../_shared/utils.ts'
import { getAuthUser } from '../_shared/auth.ts'

serve(async (req) => {
  const user = getAuthUser(req)

  const supabase = getAdminClient()

  const { data: reviews, error } = await supabase
    .from('review')
    .select('*')
    .eq('userId', user.id)
    .order('createdAt', { ascending: false })

  if (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to fetch reviews', details: error.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )
  }

  return new Response(JSON.stringify(reviews), {
    headers: { 'Content-Type': 'application/json' },
  })
}
