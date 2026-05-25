# Park4Night Google Maps - Repository Instructions

## Project Overview
A Progressive Web App (PWA) that replicates Park4Night functionality with Google Maps integration. Built with React + TypeScript (frontend) and Node.js + Express + Prisma (backend).

## Tech Stack
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Google Maps API, IndexedDB (offline)
- **Backend**: Node.js, Express, Prisma ORM, PostgreSQL, Passport.js (Google OAuth)
- **Deployment**: Render.com (web service + static site + managed database)

## Quick Start

```bash
# Install all dependencies
npm run install:all

# Copy environment files
cp server/.env.example server/.env
cp client/.env.example client/.env
# Edit .env files with your credentials

# Run development servers (concurrent)
npm run dev

# Build for production
npm run build
```

## Development Commands

| Command | Description |
|---------|-------------|
| `npm run install:all` | Install deps for root, server, and client |
| `npm run dev` | Start both server (port 5000) and client (port 5173) |
| `npm run build` | Build server (Prisma generate) and client (Vite) |
| `npm run test` | Run server tests (Jest) |
| `npm run lint` | Lint server (ESLint) and client (ESLint + TypeScript) |

## Project Structure

```
.
├── client/                 # React + TypeScript frontend
│   ├── src/
│   │   ├── components/     # React components (MapContainer, ListView, etc.)
│   │   ├── hooks/          # Custom hooks (useGpsTracking)
│   │   ├── services/       # IndexedDB service (db.ts)
│   │   ├── App.tsx         # Main app component
│   │   └── main.tsx        # Entry point
│   ├── public/             # Static assets & PWA icons
│   ├── vite.config.ts      # Vite + PWA plugin config
│   └── eslint.config.js    # ESLint flat config
├── server/                 # Node.js + Express backend
│   ├── src/
│   │   ├── config/         # Passport (Google OAuth) & Prisma config
│   │   ├── controllers/    # Route handlers (places, reviews, favorites, visits)
│   │   ├── routes/         # Express routers
│   │   ├── services/       # Park4Night API integration
│   │   └── index.js        # Express app entry point
│   ├── prisma/
│   │   └── schema.prisma   # Database schema
│   ├── tests/              # Jest test suite
│   └── eslint.config.mjs   # ESLint flat config
├── .github/workflows/ci.yml # GitHub Actions CI
├── render.yaml             # Render.com deployment config
└── package.json            # Root scripts (dev, build, test, lint)
```

## Database Schema
- **User**: Google OAuth authentication (googleId, email, name, avatar)
- **Place**: Cached Park4Night locations (id, name, lat/lng, type, rating, rawData)
- **Review**: User reviews for places (userId, placeId, content, rating)
- **Favorite**: User's bookmarked places (userId, placeId - composite key)
- **Visit**: User's visited places (userId, placeId, visitedAt)

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | No | Health check |
| GET | `/auth/google` | No | Google OAuth login |
| GET | `/auth/google/callback` | No | OAuth callback |
| GET | `/auth/me` | Yes | Current user |
| GET | `/auth/logout` | Yes | Logout |
| GET | `/api/places?lat=&lng=&type=&minRating=&sortBy=` | No | Get places |
| GET | `/api/places/:id/reviews` | No | Get Park4Night reviews |
| GET | `/api/reviews/:placeId` | Yes | Get local reviews |
| POST | `/api/reviews` | Yes | Add review |
| GET | `/api/favorites` | Yes | Get favorites |
| POST | `/api/favorites` | Yes | Add favorite |
| DELETE | `/api/favorites/:id` | Yes | Remove favorite |
| GET | `/api/visits` | Yes | Get visits |
| POST | `/api/visits` | Yes | Record visit |

## Testing
- Tests use Jest with supertest for HTTP endpoints
- Controller tests mock Prisma client and external services
- Run: `npm test` (root) or `npm test` (server/)

## Linting
- Server: ESLint flat config with Node.js globals
- Client: ESLint flat config with TypeScript + React hooks + browser globals
- Run: `npm run lint`

## Deployment
- Uses `render.yaml` for multi-service deployment on Render.com
- Server: Web service with PostgreSQL database
- Client: Static site with Vite build output
- Environment variables configured via Render dashboard

## Key Dependencies
- `@react-google-maps/api` - Google Maps React wrapper
- `@prisma/client` - Database ORM
- `passport-google-oauth20` - Google OAuth
- `vite-plugin-pwa` - PWA service worker generation
- `idb` - IndexedDB wrapper for offline storage
