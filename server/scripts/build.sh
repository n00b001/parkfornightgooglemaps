#!/usr/bin/env bash
#
# Build script for Render deployment.
# All steps are critical — failures stop the build.
#
set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

log "=== Starting build ==="

# --- Step 1: Install dependencies ---
log "Step 1: Installing root dependencies..."
npm install || { error "Root npm install failed."; exit 1; }

log "Step 2: Installing server dependencies..."
cd "$(dirname "$0")/../" || cd server
npm install || { error "Server npm install failed."; exit 1; }

# --- Step 3: Generate Prisma client (required before migrations) ---
log "Step 3: Generating Prisma client..."
npx prisma generate || { error "Prisma generate failed."; exit 1; }

# --- Step 4: Deploy database migrations (critical — must succeed) ---
log "Step 4: Deploying Prisma migrations..."
if [ -z "${DATABASE_URL:-}" ]; then
  error "DATABASE_URL is required. Set it in Render dashboard."
  exit 1
fi
npx prisma migrate deploy || { error "Prisma migrate deploy failed! Tables were NOT created."; exit 1; }
log "  Migrations deployed successfully."

log "=== Build complete ==="
