#!/usr/bin/env bash
# Build landing + terminal into one dist/, for root netlify.toml publish.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"

rm -rf "$DIST"
mkdir -p "$DIST"

echo ">> landing (/)"
cd "$ROOT/Landing-site"
npm ci --no-audit --no-fund
# Terminal link is same site in prod (/app/)
VITE_TERMINAL_URL="${VITE_TERMINAL_URL:-/app/}" npm run build
cp -R dist/* "$DIST/"

echo ">> terminal (/app)"
cd "$ROOT/frontend"
npm ci --no-audit --no-fund
# Empty base = same-origin API in sseClient.ts; path prefix for assets
VITE_BASE="/app/" VITE_BACKEND_BASE="" npm run build
mkdir -p "$DIST/app"
cp -R dist/* "$DIST/app/"

echo ">> done — publish $DIST"
