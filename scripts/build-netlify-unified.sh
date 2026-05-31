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
BACKEND="${BACKEND_URL:-https://icetea-api-4fjb.onrender.com}"
BACKEND="${BACKEND%/}"
# Call Render directly — Netlify proxy hard-caps at 26s and kills long SSE chat streams.
VITE_BASE="/app/" VITE_BACKEND_BASE="$BACKEND" npm run build
mkdir -p "$DIST/app"
cp -R dist/* "$DIST/app/"

echo ">> terminal API -> ${BACKEND} (direct, bypasses Netlify 26s proxy limit)"

cat > "$DIST/_redirects" <<EOF
/healthz ${BACKEND}/healthz 200!
/v1/* ${BACKEND}/v1/:splat 200!
/app/* /app/index.html 200
/* /index.html 200
EOF

echo ">> done — publish $DIST"
