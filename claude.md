# Park4Night Google Maps PWA - Project Instructions

## Tech Stack
- **Client**: React 18 + TypeScript + Vite + Tailwind CSS + @react-google-maps/api + TanStack Query + PWA (vite-plugin-pwa)
- **Server**: Node.js + Express + Prisma (PostgreSQL) + Passport (Google OAuth)
- **Deployment**: Render (server + static client + PostgreSQL database)

## Project Structure
```
├── client/          # React PWA frontend
│   ├── src/
│   │   ├── components/   # MapContainer, ListView, PlaceDetails, etc.
│   │   ├── hooks/        # useGpsTracking
│   │   ├── services/     # IndexedDB caching (db.ts)
│   │   ├── App.tsx       # Main app with map/list views
│   │   └── axiosConfig.ts
│   └── package.json
├── server/          # Express API backend
│   ├── src/
│   │   ├── controllers/  # place, review, favorite, visit
│   │   ├── routes/       # Express routers
│   │   ├── config/       # Prisma DB, Passport
│   │   └── services/     # Park4Night API integration
│   └── prisma/schema.prisma
├── render.yaml      # Render deployment config
└── package.json     # Root (concurrently for dev)
```

## Development Workflow
1. **Always use git worktrees** for feature branches
2. **Always create a PR** — never push directly to main
3. **Ensure CI passes locally** before pushing (`npm test`)
4. **Ensure CI passes in PR** before merging — **ALWAYS monitor PR CI status and fix failures before declaring done**
5. **NEVER commit secrets** (API keys, tokens, passwords) to git — GitGuardian scans all commits and will fail CI. Use environment variables exclusively.

## Key Commands
```bash
# Install all dependencies
npm run install:all

# Dev server (client + server concurrently)
npm run dev

# Build both
npm run build

# Run tests (server Jest + client if any)
npm test

# Lint
npm run lint
```

## Environment Variables
### Server (.env)
- `DATABASE_URL` — PostgreSQL connection string
- `NODE_ENV` — development/production
- `SESSION_SECRET` — Session encryption secret
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — Google OAuth
- `CLIENT_URL` — Frontend URL for CORS
- `SERVER_URL` — Server origin for OAuth callback URL (auto-set by Render)

### Client (Vite env)
- `VITE_API_URL` — Backend API URL (auto-set by Render)
- `VITE_GOOGLE_MAPS_API_KEY` — Google Maps JavaScript API key (MUST be a real key with billing, NOT the demo key)

## Google Cloud Console Configuration
The OAuth 2.0 client must have:
- **Authorized redirect URIs**: `https://park4night-server.onrender.com/auth/google/callback`
- **Authorized JavaScript origins**: `https://park4night-client.onrender.com`

## Known Issues & Gotchas
- **Google Maps demo key**: The Google Maps demo key has a tiny daily quota. Always use a real API key with billing enabled. When quota is exceeded, `map.getBounds()` returns undefined causing TypeErrors. **NEVER commit API keys or secrets to git** — GitGuardian will fail CI.
- **Park4Night API**: The external API (`guest.park4night.com`) can be slow or rate-limit. Always handle failures gracefully with caching.
- **Prisma**: Run `npx prisma generate` after any schema change. Use `npx prisma db push` to sync schema to DB.
- **Session table**: The `Session` model in Prisma is used by `connect-pg-simple` for session storage. Must exist before server starts.

## API Endpoints
- `GET /health` — Health check
- `GET /auth/me` — Current user (requires auth)
- `GET /api/places?lat=&lng=&type=&minRating=&sortBy=` — Get places near coords
- `GET /api/places/:id/reviews` — Get reviews for a place
- `POST /api/favorites` / `DELETE /api/favorites/:placeId` — Toggle favorite
- `POST /api/visits` — Record a visit
- `POST /api/reviews` — Submit a review
