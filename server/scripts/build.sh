#!/usr/bin/env bash
#
# Build script for Render deployment.
# Each step is logged and errors are handled so critical steps (migrations) always run.
#
set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

log "=== Starting build ==="

# --- Step 1: Git LFS (best-effort, data files may not exist yet) ---
log "Step 1: Git LFS setup..."
git lfs install || true
if git lfs pull 2>/dev/null; then
  log "  Git LFS pull succeeded."
else
  log "  WARNING: Git LFS pull failed or no LFS files. Continuing..."
fi

# --- Step 2: Install dependencies ---
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
  error "DATABASE_URL not set — cannot deploy migrations."; exit 1;
fi
npx prisma migrate deploy || { error "Prisma migrate deploy failed! Tables were NOT created."; exit 1; }
log "  Migrations deployed successfully."

log "=== Build complete ==="
