# Launching PosyHub Publicly From Your Phone (Pilot)

Goal: serve PosyHub from your Android phone (Termux + proot Ubuntu) on **your own
domain over HTTPS**, so teachers and parents can reach it from anywhere — before
you commit to a VPS.

**Why a tunnel instead of pointing DNS at the phone:** Nigerian mobile networks
use carrier-grade NAT — your phone has no public inbound IP address, so an
A-record/port-forward can never reach it. A Cloudflare Tunnel solves this: the
phone makes an *outbound* connection to Cloudflare, and Cloudflare routes your
domain's traffic down that connection. Free, includes automatic HTTPS, and no
router/firewall config.

---

## 1. One-time setup

### a) Put your domain on Cloudflare (free plan)

1. Create an account at dash.cloudflare.com → **Add a site** → enter your domain.
2. At your registrar, change the domain's **nameservers** to the two Cloudflare
   gives you. (Propagation: minutes to a few hours.)

### b) Install cloudflared (inside proot Ubuntu)

```bash
# inside the same Ubuntu proot where PosyHub runs
curl -fsSL -o /tmp/cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
dpkg -i /tmp/cloudflared.deb
cloudflared --version
```

### c) Create the tunnel and route your domain

```bash
cloudflared tunnel login                 # opens a browser → authorize your domain
cloudflared tunnel create edusyncra        # prints a Tunnel ID, writes a credentials .json
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml <<EOF
tunnel: edusyncra
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: edusyncra.site      # or yourdomain.com
    service: http://localhost:8000       # gunicorn port (PORT in .env)
  - service: http_status:404
EOF
cloudflared tunnel route dns edusyncra edusyncra.site
```

### d) Production settings in `.env`

Because the app is now internet-facing:

```bash
APP_ENV=production
PORT=8000
SECRET_KEY=<long random string>
ADMIN_PASSWORD=<strong password>         # or ENABLE_LEGACY_LOGIN=0
TRUST_PROXY=1                            # cloudflared is a reverse proxy
SESSION_COOKIE_SECURE=1                  # cookies only over HTTPS
ENABLE_HSTS=1
FIELD_ENCRYPTION_KEY=<base64 key>        # see docs/SECURITY.md
```

Then run the portal-password encryption once:
`python scripts/encrypt_portal_passwords.py`

### e) Keep the phone alive

- In Termux (outside proot): `termux-wake-lock`
- Android Settings → Battery → Termux → **Unrestricted / Don't optimize**
- Optional: install **Termux:Boot** so everything starts after a reboot.

---

## 2. Daily start — one command

```bash
python app_production.py     # app + Cloudflare tunnel, prints the demo URL
```

It serves the app and starts the tunnel, prints the public URL in a banner, and
restarts the tunnel if it drops. Stop everything with Ctrl-C.

To run **without** Cloudflare (local / same-Wi-Fi only):

```bash
python app.py                # just the app on http://<phone-ip>:5000
```

> If you use PostgreSQL, start it first (e.g. `./scripts/start.sh` brings up
> Postgres) or set `DATABASE_URL`. With neither, the app falls back to its local
> database — fine for a quick demo, but use your real DB for teacher testing.

### Short URL vs instant URL

`app_production.py` picks the mode automatically:

| Mode | You get | Setup |
|------|---------|-------|
| **Instant** (default) | `https://<random-words>.trycloudflare.com` — longer, changes each run | none — works immediately, no account or domain |
| **Short + stable** | `https://edusyncra.site` (your domain, your choice of subdomain) | the one-time named-tunnel setup in section 1, then set `CLOUDFLARE_TUNNEL` + `CLOUDFLARE_HOSTNAME` in `.env` |

For the shortest possible link, route a short subdomain (or the apex) of your
domain in section 1c (`cloudflared tunnel route dns edusyncra edusyncra.site`)
and set `CLOUDFLARE_HOSTNAME=edusyncra.site`.

Verify from another device on mobile data: open the printed URL, or hit
`<that-url>/healthz` → `ok`.

---

## 3. Operating notes & limits

| Topic | Note |
|---|---|
| Data usage | All traffic flows through the phone's connection. A pilot with a handful of teachers is light (tens of MB/day); watch your data plan. |
| Reliability | If the phone sleeps, loses signal, or Termux is killed, the site goes down. Fine for a pilot — not for an exam day. |
| Capacity | A phone handles a few dozen concurrent users comfortably. **Do not run whole-school CBT exams on the phone** — that's what the VPS is for. |
| Backups | The daily Postgres backup still runs on the phone. Periodically copy `instance/backups/` off the device (e.g. `rclone`/Drive). |
| Security | The rate limiting, security headers, and HTTPS all apply. Keep `.env` permissions `600`. |
| Moving to a VPS later | Take a manual backup (`scripts/backup_db.sh`), restore it on the server (`scripts/restore_db.sh`), point the tunnel — or plain DNS — at the VPS. Parents' links don't change. |
