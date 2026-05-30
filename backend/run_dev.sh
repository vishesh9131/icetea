#!/usr/bin/env bash
# Start the icetea backend (safety -> classifier -> agents -> SSE pipeline).
# Run from anywhere; the script cd's into its own directory so PYTHONPATH
# resolves the `icetea` package no matter where you invoke it from.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
exec uvicorn icetea.api.app:app --host 127.0.0.1 --port 8000 "$@"
