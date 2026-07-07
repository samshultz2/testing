# Go-live checklist — moving EduSyncra to a VPS

Follow top to bottom. Copy-paste the commands. Nothing here touches your current
phone setup until you choose to switch DNS at the end.
Reference details: `deploy/README.md`.

---

## Phase 0 — Prepare (can do now, no VPS needed)
- [ ] Get a VPS (Ubuntu 22.04/24.04). Note its IP and an SSH user.
- [ ] Domain already on Cloudflare (nameservers pointed at Cloudflare).
- [ ] Paystack account → copy your **TEST** keys (`sk_test_…`, `pk_test_…`).
- [ ] SMTP credentials ready (host, port, user, password, from-address).

Nothing to run yet. Your phone keeps serving the school as-is.

---

## Phase 1 — Dump your current database (on the PHONE/Termux)
```bash
cd ~/your-app
bash deploy/migrate_db.sh export "postgresql://posyhub:posyhub@localhost:5432/posyhub" edusyncra_dump.sql
```
- [ ] `edusyncra_dump.sql` created.
- [ ] Copy it to the VPS:
```bash
scp edusyncra_dump.sql USER@VPS_IP:~/
```

---

## Phase 2 — Install on the VPS (one script)
```bash
ssh USER@VPS_IP
git clone <your-repo-url> ~/edusyncra && cd ~/edusyncra
mv ~/edusyncra_dump.sql ~/edusyncra/
cp deploy/setup.env.example deploy/setup.env
nano deploy/setup.env
```
Fill in `deploy/setup.env`:
- [ ] `TENANT_BASE_DOMAIN`, `APEX_TENANT`, `OWNER_SCHOOL_NAME`, `OWNER_ADMIN_EMAIL`
- [ ] `DB_APP_PASSWORD` (a strong password)
- [ ] `OWNER_DB_DUMP=/home/USER/edusyncra/edusyncra_dump.sql`
- [ ] `PLATFORM_PAYSTACK_SECRET_KEY` / `PUBLIC_KEY` (test keys) + `TENANT_PRICE_KOBO`
- [ ] `SMTP_*`
- [ ] `INSTALL_SERVICE=yes`, and `SETUP_TUNNEL=yes` if you want the tunnel set up now

Then run it:
```bash
bash deploy/setup_vps.sh
```
- [ ] Finishes with "SETUP COMPLETE" and prints your URLs.
- [ ] `sudo systemctl status edusyncra` shows **active (running)**.

---

## Phase 3 — Cloudflare tunnel + DNS
(Skip the install command if you set `SETUP_TUNNEL=yes` above.)
```bash
bash deploy/setup_tunnel.sh
```
- [ ] Complete the one-time browser login when prompted.
- [ ] Add the **wildcard** record it prints — Cloudflare → DNS → Add record:
      `CNAME  *  →  <tunnel-id>.cfargotunnel.com`  (Proxy: ON)
- [ ] `sudo systemctl status cloudflared` shows **active (running)**.

---

## Phase 4 — Paystack webhook
- [ ] Paystack dashboard → Settings → API Keys & Webhooks → **Webhook URL**:
      `https://api.YOUR-DOMAIN/billing/webhook`
- [ ] Leave the dashboard **Callback URL** blank (the app sets it per payment).

---

## Phase 5 — Verify it works
- [ ] `https://YOUR-DOMAIN` → your existing school's login; sign in as owner.
- [ ] `https://YOUR-DOMAIN/platform` → super-admin console loads.
- [ ] `https://signup.YOUR-DOMAIN/register` → register a throwaway test school;
      confirm the email link, then log in at `https://<sub>.YOUR-DOMAIN`.
- [ ] Billing lifecycle (test): `.venv/bin/python scripts/billing_devtools.py show`
      then `... paid <testschool> -3` → visit a page → redirected to /billing.
- [ ] Test payment with card `4084 0840 8408 4081` (exp any future, CVV `408`) →
      access restored, receipt email received.
- [ ] Delete the test school from `/platform`.

---

## Phase 6 — Go live
- [ ] Swap the two Paystack keys in `.env` to **live** (`sk_live_…`, `pk_live_…`):
      `nano .env` then `sudo systemctl restart edusyncra`.
- [ ] Point production traffic at the VPS: the wildcard + apex now resolve to the
      new tunnel. Once confirmed, decommission the phone.

---

## If something's off
- App logs: `sudo journalctl -u edusyncra -f`
- Tunnel logs: `sudo journalctl -u cloudflared -f`
- Re-run `bash deploy/setup_vps.sh` any time — it's idempotent (won't drop data
  or change your secrets), and applies any new migrations to the owner DB.
- Your original phone setup is untouched until you switch DNS, so you can always
  fall back to it.
