import { serve } from 'https://deno.land/std@0.208.0/http/server.ts'
import { getAdminClient } from '../_shared/utils.ts'
import { getAuthUser } from '../_shared/auth.ts'

serve(async (req) => {
  const authUser = getAuthUser(req)

  const supabase = getAdminClient()

  // Look up the app User record by auth_user_id
  const { data: user, error } = await supabase
    .from('user')
    .select('id, email, name, avatar, createdAt, updatedAt')
    .eq('authUserId', authUser.id)
    .single()

  if (error || !user) {
    // User exists in auth but not in app User table yet
    // Return basic info from auth
    return new Response(
      JSON.stringify({
        id: authUser.id,
        email: authUser.email,
        name: null,
        avatar: null,
      }),
      { headers: { 'Content-Type': 'application/json' } },
    )
  }

  return new Response(JSON.stringify(user), {
    headers: { 'Content-Type': 'application/json' },
  })
})
