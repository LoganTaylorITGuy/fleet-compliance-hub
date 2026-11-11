#!/usr/bin/env bash
# Share a live demo over HTTPS with a free Cloudflare quick tunnel.
#
#   scripts/demo-tunnel.sh            # serve current data
#   scripts/demo-tunnel.sh --reset    # reload fresh demo data first
#   scripts/demo-tunnel.sh --port 8090
#
# What it does:
#   1. Serves the app with waitress (a production WSGI server, not the Flask
#      dev server), bound to 127.0.0.1 only: nothing is exposed on the LAN.
#   2. Opens a Cloudflare quick tunnel (no account; a new random
#      https://*.trycloudflare.com address each run).
#   3. Prints the public URL and a QR code to scan with a phone.
#   4. Ctrl+C closes the tunnel and stops the server.
#
# The URL is public while this runs, and demo mode's one-click logins are on.
# All data is fictional. Run it only for the length of a demo, then reset:
#   python seed.py --reset

set -euo pipefail

PORT=8080
RESET=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset) RESET=true; shift ;;
    --port) PORT="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
PY=.venv/bin/python
[[ -x "$PY" ]] || { echo "No .venv found. See README: Quick start." >&2; exit 1; }
command -v cloudflared >/dev/null || { echo "cloudflared is not installed: brew install cloudflared" >&2; exit 1; }
[[ -x .venv/bin/waitress-serve ]] || { echo "waitress missing: pip install -e .[dev]" >&2; exit 1; }

# Settings for this run only (the .env file is not read by waitress).
export APP_ENV=demo
export DEMO_MODE=true
export SESSION_COOKIE_SECURE=true   # the public URL is HTTPS
export TRUST_PROXY=true             # Cloudflare is in front; trust its X-Forwarded headers
SECRET_KEY="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
export SECRET_KEY

if $RESET; then
  echo "Reloading fresh demo data..."
  "$PY" seed.py --reset | tail -5
fi

LOG_DIR="$(mktemp -d)"
SERVER_PID=""
TUNNEL_PID=""
WATCHDOG_PID=""
cleanup() {
  trap - EXIT INT TERM HUP
  echo
  [[ -n "$TUNNEL_PID" ]] && kill "$TUNNEL_PID" 2>/dev/null || true
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
  [[ -n "$WATCHDOG_PID" ]] && kill "$WATCHDOG_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  rm -rf "$LOG_DIR"
  echo "Tunnel closed and server stopped. The public URL no longer works."
  echo "Restore demo data any time with: python seed.py --reset"
}
trap cleanup EXIT INT TERM HUP   # HUP: the terminal window was closed

# Watchdog: if this script dies for any reason (even kill -9, which no trap can
# catch), stop the tunnel and the server so the public URL never outlives it.
start_watchdog() {
  local parent=$$
  (
    trap '' INT HUP
    while kill -0 "$parent" 2>/dev/null; do sleep 2; done
    kill "$@" 2>/dev/null || true
  ) &
  WATCHDOG_PID=$!
}

echo "Starting the app on 127.0.0.1:$PORT (waitress)..."
.venv/bin/waitress-serve --listen="127.0.0.1:$PORT" --threads=8 --ident=fleet-compliance-hub \
  --call app:create_app >"$LOG_DIR/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 50); do
  curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break
  kill -0 "$SERVER_PID" 2>/dev/null || { cat "$LOG_DIR/server.log" >&2; exit 1; }
  sleep 0.2
done

echo "Opening a Cloudflare quick tunnel..."
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$LOG_DIR/tunnel.log" 2>&1 &
TUNNEL_PID=$!
start_watchdog "$SERVER_PID" "$TUNNEL_PID"
URL=""
for _ in $(seq 1 90); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/tunnel.log" | head -1 || true)"
  [[ -n "$URL" ]] && break
  kill -0 "$TUNNEL_PID" 2>/dev/null || { cat "$LOG_DIR/tunnel.log" >&2; exit 1; }
  sleep 0.5
done
[[ -n "$URL" ]] || { echo "No tunnel URL after 45s:" >&2; tail -20 "$LOG_DIR/tunnel.log" >&2; exit 1; }

# A brand-new tunnel hostname can take a minute to reach this Mac's DNS (and
# macOS caches the early "not found"). Check through Cloudflare's resolver too,
# so we know the tunnel itself works.
HOST="${URL#https://}"
VERIFIED=""
printf "Checking the public URL"
for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 "$URL/healthz" >/dev/null 2>&1; then VERIFIED="yes"; break; fi
  IP="$(dig +short @1.1.1.1 "$HOST" 2>/dev/null | head -1 || true)"
  if [[ -n "$IP" ]] && curl -fsS --max-time 5 --resolve "$HOST:443:$IP" "$URL/healthz" >/dev/null 2>&1; then
    VERIFIED="via Cloudflare DNS"; break
  fi
  printf "."; sleep 1
done
echo
case "$VERIFIED" in
  yes) echo "Public URL verified." ;;
  "via Cloudflare DNS")
    echo "Public URL verified. If this laptop's browser can't open it yet, give its DNS a minute;"
    echo "phones on cellular usually open it right away." ;;
  *) echo "Warning: couldn't confirm the public URL yet. It may need another minute." >&2 ;;
esac

cat <<EOF

  Fleet Compliance Hub is live:

      $URL/login

  Demo password: fleet-demo-2026  (or use the one-click demo logins)
  Fictional data only. Press Ctrl+C to close the tunnel when the demo ends.

EOF
if command -v qrencode >/dev/null; then
  qrencode -t ANSIUTF8 -m 2 "$URL/login"
  echo "  Scan to open on a phone."
fi

wait "$TUNNEL_PID"
