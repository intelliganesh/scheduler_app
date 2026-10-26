#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
# Loopback by default; set DEV_HOST=0.0.0.0 only to deliberately expose the dev servers.
DEV_HOST="${DEV_HOST:-127.0.0.1}"
# Authentication mode is read from backend/.env by the application. Override
# it explicitly for a local demo with: AUTH_MODE=mock ./server.sh

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
(
  cd "$BACKEND_DIR"
  "$BACKEND_DIR/.venv/bin/alembic" upgrade head
)

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  (cd "$FRONTEND_DIR" && npm install)
fi

# `exec` makes each tracked PID the actual development-server process, so the
# cleanup trap can reliably stop both servers instead of only a wrapper shell.
(cd "$BACKEND_DIR"; exec "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app --host "$DEV_HOST" --port 8000) &
BACKEND_PID=$!
(cd "$FRONTEND_DIR"; exec "$FRONTEND_DIR/node_modules/.bin/vite" --host "$DEV_HOST" --port 5173 --strictPort) &
FRONTEND_PID=$!

echo "Backend:  http://localhost:8000/docs"
echo "Frontend: http://localhost:5173"
# Stop everything if either server exits (for example, a port already in use).
# Polling keeps this compatible with macOS's bash 3.2, which has no `wait -n`.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
echo "A development server exited unexpectedly; see the output above." >&2
exit 1
