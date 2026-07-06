# Wildcard DNS + TLS for multi-tenant EduSyncra (`edusyncra.site`)

Each school lives at `<school>.edusyncra.site`. For new subdomains to work
**instantly** (no per-school DNS record or certificate), you need one wildcard
DNS record and one wildcard TLS certificate. Set this up once.

Your existing school keeps the bare apex `edusyncra.site` (see "Bringing your
current school in" below), registration lives at `signup.edusyncra.site`.

---

## 1. DNS

Add these records at your DNS provider (values: `SERVER_IP` = your host):

| Type | Name | Value |
|------|------|-------|
| A | `@` (edusyncra.site) | `SERVER_IP` |
| A | `*` (wildcard) | `SERVER_IP` |
| A | `signup` | `SERVER_IP` |

The `*` record makes `anything.edusyncra.site` resolve to your server with no
further changes — that's what makes new schools instant.

*(Test locally with no DNS at all using `*.lvh.me`, which resolves every
subdomain to 127.0.0.1: set `TENANT_BASE_DOMAIN=lvh.me`.)*

## 2. TLS — pick one

### Option A — Cloudflare (simplest)
1. Put `edusyncra.site` behind Cloudflare (orange-cloud the `@`, `*` and
   `signup` records).
2. SSL/TLS mode **Full (strict)**.
3. Cloudflare's **Universal SSL** covers `edusyncra.site` and `*.edusyncra.site`
   at the edge automatically — no cert work on your box.
4. Generate a Cloudflare **Origin Certificate** (covers `*.edusyncra.site`),
   install it in nginx (below) so the origin is HTTPS too.

### Option B — Let's Encrypt wildcard (certbot, DNS-01)
Wildcard certs require the DNS-01 challenge, so use a DNS plugin for your
provider (Cloudflare shown):
```bash
sudo apt install certbot python3-certbot-dns-cloudflare
# ~/.secrets/cloudflare.ini  -> dns_cloudflare_api_token = <token>   (chmod 600)
sudo certbot certonly \
  --dns-cloudflare --dns-cloudflare-credentials ~/.secrets/cloudflare.ini \
  -d 'edusyncra.site' -d '*.edusyncra.site'
```
Certbot auto-renews via the DNS plugin — no per-school action ever.

## 3. nginx (one server block for every school)

```nginx
server {
    listen 443 ssl;
    server_name edusyncra.site *.edusyncra.site;

    ssl_certificate     /etc/letsencrypt/live/edusyncra.site/fullchain.pem;   # or Cloudflare origin cert
    ssl_certificate_key /etc/letsencrypt/live/edusyncra.site/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;        # gunicorn
        proxy_set_header Host              $host; # the app routes on this
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
    }
}
server {                                          # redirect http -> https
    listen 80;
    server_name edusyncra.site *.edusyncra.site;
    return 301 https://$host$request_uri;
}
```
`Host` is what the app resolves the school from; the app's `ProxyFix` already
trusts `X-Forwarded-*`.

## 4. Turn multi-tenancy on (environment)

```bash
MULTI_TENANT=1
TENANT_BASE_DOMAIN=edusyncra.site
APEX_TENANT=<your-school-subdomain>          # serves your existing school on the apex
RESERVED_SUBDOMAINS=www,signup,app,admin,api
ENABLE_HSTS=1
SESSION_COOKIE_SECURE=1

# Databases
CONTROL_PLANE_DATABASE_URL=postgresql+psycopg://cp_user:pw@host/control_plane
TENANT_DATABASE_URL_TEMPLATE=postgresql+psycopg://app_user:pw@host/{name}
PROVISIONER_DATABASE_URL=postgresql+psycopg://provisioner:pw@host/postgres   # role WITH createdb

# Billing (see docs/BILLING.md)
PLATFORM_PAYSTACK_SECRET_KEY=sk_live_xxx
PLATFORM_PAYSTACK_PUBLIC_KEY=pk_live_xxx
TENANT_PRICE_KOBO=5000000        # ₦50,000 (amount is in kobo)
TENANT_TRIAL_DAYS=3
TENANT_PLAN_DAYS=30
TENANT_BILLING_GRACE_DAYS=7
```

## 5. Bringing your current school in (nothing happens to its data)

Register your existing database as tenant #1 — this only stores a pointer, it
never opens or changes the database:
```bash
DATABASE_URL=<your current DATABASE_URL> \
  python scripts/provision_tenant.py --adopt-current \
  --name "Your School" --subdomain <your-school-subdomain>
```
It is adopted as `plan='owner'` — **free forever, never trial-limited, never
reaped**. Set `APEX_TENANT=<your-school-subdomain>` so `edusyncra.site` keeps
serving it with no URL change for your users.

## 6. Recurring jobs (cron / systemd timer)
```bash
python scripts/migrate_all_tenants.py     # after every deploy with a schema change
python scripts/backup_all_tenants.py      # daily
python scripts/reap_unpaid_tenants.py     # daily (deletes unpaid, past-grace schools)
```
