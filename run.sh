#!/usr/bin/env bash
# Boots backend (FastAPI :8077) + frontend (Vite :5173).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Free the ports first — kill any stale backend/frontend from a previous run, so we never
# hit "Address already in use" (which silently leaves an old backend serving stale code).
lsof -ti tcp:8077 | xargs kill -9 2>/dev/null || true
lsof -ti tcp:5173 | xargs kill -9 2>/dev/null || true
sleep 1

cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi
./.venv/bin/uvicorn app.main:app --port 8077 --reload &
BACK=$!

cd "$ROOT/frontend"
[ -d node_modules ] || npm install
npm run dev &
FRONT=$!

echo ""
echo "  Backend : http://localhost:8077  (docs /docs)"
echo "  Studio  : http://localhost:5173"
echo ""
trap "kill $BACK $FRONT 2>/dev/null" EXIT
wait
