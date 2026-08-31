#!/usr/bin/env bash
#
# Serve PosyHub publicly from the phone via Cloudflare Tunnel.
# One-time setup: see docs/PHONE_PILOT.md. Then just run:
#   ./scripts/phone_serve.sh
#
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TUNNEL_NAME="${TUNNEL_NAME:-posyhub}"

command -v cloudflared >/dev/null 2>&1 || {
  echo "cloudflared is not installed — see docs/PHONE_PILOT.md (section 1b)." >&2
  exit 1
}
[ -f "$HOME/.cloudflared/config.yml" ] || {
  echo "No tunnel config at ~/.cloudflared/config.yml — see docs/PHONE_PILOT.md (section 1c)." >&2
  exit 1
}

# 1. Start Postgres + gunicorn in the background (start.sh is idempotent).
echo "[phone-serve] starting app (postgres + gunicorn)..."
./scripts/start.sh &
APP_PID=$!

cleanup() {
  echo "[phone-serve] shutting down..."
  kill "$APP_PID" 2>/dev/null || true
  pkill -f "cloudflared tunnel run" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 2. Wait for the app to answer locally before exposing it.
PORT="$(grep -E '^PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2)"
PORT="${PORT:-8000}"
echo "[phone-serve] waiting for http://localhost:${PORT}/healthz ..."
for i in $(seq 1 60); do
  if curl -fsS "http://localhost:${PORT}/healthz" >/dev/null 2>&1; then
    echo "[phone-serve] app is up."
    break
  fi
  [ "$i" = 60 ] && { echo "app did not come up in 60s" >&2; exit 1; }
  sleep 1
done

# 3. Run the tunnel in the foreground; restart it if it drops (mobile networks).
while true; do
  echo "[phone-serve] starting Cloudflare tunnel '${TUNNEL_NAME}'..."
  cloudflared tunnel run "$TUNNEL_NAME" || true
  echo "[phone-serve] tunnel exited — restarting in 5s (Ctrl-C to stop)"
  sleep 5
done
