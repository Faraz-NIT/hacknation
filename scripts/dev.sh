#!/usr/bin/env bash
# Start API (:8000) and web (:3000) together. Ctrl-C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -d "$ROOT/api/.venv" ]; then
  python3 -m venv "$ROOT/api/.venv"
  "$ROOT/api/.venv/bin/pip" install -q -r "$ROOT/api/requirements.txt"
fi
if [ ! -d "$ROOT/web/node_modules" ]; then
  (cd "$ROOT/web" && npm install)
fi

(cd "$ROOT/api" && .venv/bin/uvicorn app.main:app --reload --port 8000) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
cd "$ROOT/web" && npm run dev
