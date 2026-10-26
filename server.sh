#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
# Loopback by default; set DEV_HOST=0.0.0.0 only to deliberately expose the dev servers.
DEV_HOST="${DEV_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
# Authentication mode is read from backend/.env by the application. Override
# it explicitly for a local demo with: AUTH_MODE=mock ./server.sh

# Reclaim the fixed development ports before starting. This supports restarting
# the project with one command instead of leaving stale Uvicorn/Vite processes.
stop_listener() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "Stopping existing listener(s) on port $port..."
    kill $pids 2>/dev/null || true
    sleep 1
  fi
}

stop_listener 8000
stop_listener "$FRONTEND_PORT"
configured_origins="${CORS_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}"
export CORS_ORIGINS="$configured_origins,http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"

cleanup() {
  echo "Stopping development servers..."
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  python3 -m venv "$BACKEND_DIR/.venv"
fi
"$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
if ! (
  cd "$BACKEND_DIR"
  "$BACKEND_DIR/.venv/bin/alembic" upgrade head
); then
  cat >&2 <<'EOF'
Database migration failed. Verify that the database configured in backend/.env
is running and reachable, then rerun ./server.sh. This project does not start
or manage Docker/database services.
EOF
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  (cd "$FRONTEND_DIR" && npm install)
fi

# `exec` makes each tracked PID the actual development-server process, so the
# cleanup trap can reliably stop both servers instead of only a wrapper shell.
(cd "$BACKEND_DIR"; exec "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --host "$DEV_HOST" --port 8000) &
BACKEND_PID=$!
(cd "$FRONTEND_DIR"; exec "$FRONTEND_DIR/node_modules/.bin/vite" --host "$DEV_HOST" --port "$FRONTEND_PORT" --strictPort) &
FRONTEND_PID=$!

echo "Backend:  http://localhost:8000/docs"
echo "Frontend: http://localhost:$FRONTEND_PORT"
# Stop everything if either server exits (for example, a port already in use).
# Polling keeps this compatible with macOS's bash 3.2, which has no `wait -n`.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
echo "A development server exited unexpectedly; see the output above." >&2
exit 1
