import { Hono } from 'https://deno.land/x/hono@v4.6.3/mod.ts'
import { cors } from 'https://deno.land/x/hono@v4.6.3/middleware/cors.ts'
import { createClient } from 'npm:@supabase/supabase-js@2'
import { authenticateRequest } from './utils/auth.ts'
import { getPlaces, getPlaceDetail, getPlaceReviews, getStats } from './handlers/places.ts'
import { getFavorites, addFavorite, removeFavorite } from './handlers/favorites.ts'
import { addReview, getReviews } from './handlers/reviews.ts'
import { recordVisit, getVisits } from './handlers/visits.ts'

const app = new Hono()

// CORS — allow the client origin
app.use('*', cors({
  origin: (c) => {
    const origin = c.req.header('Origin')
    return origin || '*'
  },
  allowHeaders: ['Authorization', 'Content-Type'],
  allowMethods: ['GET', 'POST', 'DELETE', 'OPTIONS'],
  maxAge: 86400,
  credentials: true,
}))

// Health check
app.get('/health', (c) => c.text('OK'))

// Places (public)
app.get('/api/places/stats', getStats)
app.get('/api/places', getPlaces)
app.get('/api/places/:id/reviews', getPlaceReviews)
app.get('/api/places/:id', getPlaceDetail)

// Authenticated routes
app.get('/api/favorites', authenticateRequest, getFavorites)
app.post('/api/favorites', authenticateRequest, addFavorite)
app.delete('/api/favorites/:id', authenticateRequest, removeFavorite)

app.get('/api/reviews/:placeId', getReviews)
app.post('/api/reviews', authenticateRequest, addReview)

app.get('/api/visits', authenticateRequest, getVisits)
app.post('/api/visits', authenticateRequest, recordVisit)

// Auth endpoints
app.get('/auth/me', async (c) => {
  const token = c.req.header('Authorization')?.replace('Bearer ', '')
  if (!token) return c.json(null, 200)

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  )
  const { data: { user }, error } = await supabase.auth.getUser(token)
  if (error || !user) return c.json(null, 200)
  return c.json({
    id: user.id,
    email: user.email,
    name: user.user_metadata?.full_name || user.user_metadata?.name || null,
    avatar: user.user_metadata?.avatar_url || null,
  }, 200)
})

Deno.serve(app.fetch)
