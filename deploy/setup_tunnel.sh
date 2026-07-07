#!/usr/bin/env bash
# Install cloudflared, create a named tunnel to this box, and run it as a
# systemd service. One interactive step: a browser login to authorise the tunnel.
#
#   bash deploy/setup_tunnel.sh            # reads deploy/setup.env for the domain
#
# After it runs, add ONE wildcard DNS record it prints (Cloudflare can't create a
# wildcare route from the CLI). Everything else — apex + www/signup/api — is
# routed for you.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
CONF="${1:-$HERE/setup.env}"
[ -f "$CONF" ] && { set -a; . "$CONF"; set +a; }
DOMAIN="${TENANT_BASE_DOMAIN:?set TENANT_BASE_DOMAIN in setup.env}"
NAME="${TUNNEL_NAME:-edusyncra}"
PORT="${APP_PORT:-5000}"
log() { printf '\n\033[1;32m▸ %s\033[0m\n' "$*"; }

# 1. install cloudflared (Debian/Ubuntu apt repo)
if ! command -v cloudflared >/dev/null 2>&1; then
  log "installing cloudflared"
  sudo mkdir -p --mode=0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
    | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
  sudo apt-get update -y && sudo apt-get install -y cloudflared
fi

# 2. authorise (interactive, once) — opens a URL to pick your zone
if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
  log "authorise cloudflared (a login URL will appear — open it and pick ${DOMAIN})"
  cloudflared tunnel login
fi

# 3. create the tunnel (idempotent)
if ! cloudflared tunnel list 2>/dev/null | awk '{print $2}' | grep -qx "$NAME"; then
  log "creating tunnel ${NAME}"
  cloudflared tunnel create "$NAME"
fi
UUID=$(cloudflared tunnel list | awk -v n="$NAME" '$2==n{print $1; exit}')
[ -n "$UUID" ] || { echo "could not determine tunnel id"; exit 1; }

# 4. ingress config — wildcard + apex -> the local app
log "writing ~/.cloudflared/config.yml"
mkdir -p "$HOME/.cloudflared"
cat > "$HOME/.cloudflared/config.yml" <<CFG
tunnel: ${UUID}
credentials-file: ${HOME}/.cloudflared/${UUID}.json
ingress:
  - hostname: "*.${DOMAIN}"
    service: http://127.0.0.1:${PORT}
  - hostname: "${DOMAIN}"
    service: http://127.0.0.1:${PORT}
  - service: http_status:404
CFG

# 5. DNS routes for the apex + reserved hosts (wildcard is manual, see below)
log "routing DNS for apex + reserved subdomains"
cloudflared tunnel route dns "$NAME" "$DOMAIN" 2>/dev/null || true
for s in www signup api; do
  cloudflared tunnel route dns "$NAME" "${s}.${DOMAIN}" 2>/dev/null || true
done

# 6. run as a systemd service (starts on boot)
log "installing cloudflared as a service"
sudo cloudflared --config "$HOME/.cloudflared/config.yml" service install 2>/dev/null || sudo cloudflared service install || true
sudo systemctl enable --now cloudflared 2>/dev/null || true

cat <<DONE

$(printf '\033[1;33m')ONE MANUAL STEP$(printf '\033[0m') — add the wildcard so every school subdomain resolves:
  Cloudflare dashboard -> DNS -> Add record
    Type: CNAME   Name: *   Target: ${UUID}.cfargotunnel.com   Proxy: ON

Tunnel ${NAME} (${UUID}) is live. Check it:  sudo systemctl status cloudflared
DONE
