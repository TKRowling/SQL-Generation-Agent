#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
  echo "Backend virtual environment not found. Create backend/.venv and install requirements-dev.txt first." >&2
  exit 1
fi

if [[ ! -f "$ROOT/backend/.env" ]]; then
  echo "backend/.env is missing. Copy backend/.env.example and configure it." >&2
  exit 1
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "frontend/node_modules is missing. Run npm install inside frontend first." >&2
  exit 1
fi

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd "$ROOT/backend"
  .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

(
  cd "$ROOT/frontend"
  npm run dev
) &
FRONTEND_PID=$!

wait
