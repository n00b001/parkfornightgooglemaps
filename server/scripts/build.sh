#!/usr/bin/env bash
#
# Build script for Render deployment.
# Each step is logged and errors are handled so critical steps (migrations) always run.
#
set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

log "=== Starting build ==="

# --- Step 1: Install dependencies ---
log "Step 2: Installing root dependencies..."
npm install || { error "Root npm install failed."; exit 1; }

log "Step 3: Installing server dependencies..."
cd "$(dirname "$0")/../" || cd server
npm install || { error "Server npm install failed."; exit 1; }

# --- Step 4: Generate Prisma client (required before migrations) ---
log "Step 4: Generating Prisma client..."
npx prisma generate || { error "Prisma generate failed."; exit 1; }

# --- Step 5: Deploy database migrations (critical — must succeed) ---
log "Step 5: Deploying Prisma migrations..."
if [ -z "${DATABASE_URL:-}" ]; then
  log "  WARNING: DATABASE_URL not set — skipping migrate deploy."
else
  npx prisma migrate deploy || { error "Prisma migrate deploy failed! Tables were NOT created."; exit 1; }
  log "  Migrations deployed successfully."
fi

# --- Step 6: Seed places (best-effort — don't fail build if data missing) ---
log "Step 6: Seeding places..."
if [ -z "${DATABASE_URL:-}" ]; then
  log "  WARNING: DATABASE_URL not set — skipping seed."
else
  node src/services/seedPlaces.js || log "  WARNING: Seed script failed, continuing anyway."
fi

log "=== Build complete ==="
