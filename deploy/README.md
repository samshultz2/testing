# One-shot VPS setup + database migration

Move EduSyncra to a real VPS and bring your current school's data with it — in a
few commands. Cloudflare only ever does DNS; everything else is set up here.

## What you get after running it
- Postgres role + your **owner** database + the **control-plane** (tenant registry)
- a Python venv with dependencies
- a complete `.env` (with freshly generated `SECRET_KEY` / `FIELD_ENCRYPTION_KEY`)
- your existing school registered as the **free-forever apex school**
- the daily **billing cron** (renewal reminders + purge) installed
- new schools able to self-register, provision, bill, and be managed at `/platform`

The setup is **idempotent** — re-running never drops data or rotates your secrets.

---

## Step 1 — Dump your current database (on your CURRENT machine)

On the phone/Termux box you run today:

```bash
cd ~/your-app
bash deploy/migrate_db.sh export "postgresql://posyhub:posyhub@localhost:5432/posyhub" edusyncra_dump.sql
```

The dump includes your data **and** the schema revision, so nothing drifts.
Copy it to the VPS:

```bash
scp edusyncra_dump.sql user@your-vps:~/edusyncra/
```

> Starting fresh with no existing data? Skip this step and leave `OWNER_DB_DUMP`
> blank — the installer creates an empty owner school and prints a first-login
> admin password.

## Step 2 — Configure (on the VPS)

```bash
git clone <your repo> ~/edusyncra && cd ~/edusyncra
cp deploy/setup.env.example deploy/setup.env
nano deploy/setup.env          # fill in domain, DB password, dump path, Paystack/SMTP
```

Point `OWNER_DB_DUMP` at the file you copied (e.g. `/home/user/edusyncra/edusyncra_dump.sql`).

## Step 3 — Run the installer (once)

```bash
bash deploy/setup_vps.sh
```

That's it. It installs packages (Debian/Ubuntu), creates the databases, restores
your dump, writes `.env`, brings the schema to head, adopts your school as the
apex owner, and installs the cron. When it finishes it prints your start command
and URLs.

## Step 4 — Start the app + DNS

```bash
cd ~/edusyncra && .venv/bin/python app_production.py     # waitress on :5000
```

In Cloudflare (DNS only):
- wildcard `*.your-domain` **and** the apex → your tunnel (→ `http://127.0.0.1:5000`)
- Paystack dashboard → **Webhook URL**: `https://api.your-domain/billing/webhook`
  (leave the dashboard *Callback URL* blank — the app sets it per payment)

Your existing school stays at `https://your-domain`, new schools register at
`https://signup.your-domain/register`, and you manage everything at
`https://your-domain/platform`.

---

## Handy follow-ups
- **Test the billing lifecycle** without waiting: `.venv/bin/python scripts/billing_devtools.py show` and `... paid <school> -3` etc. (see the billing docs).
- **Run the daily job by hand**: `.venv/bin/python scripts/billing_cron.py --dry-run`.
- **Re-run setup** any time (e.g. after `git pull`) — it applies new migrations to the owner DB and leaves your data and secrets untouched.

## Notes
- The app role owns the tenant databases (it has `CREATEDB`), so new schools are
  provisioned with no cross-role permission juggling.
- `.env` is written `chmod 600` and is gitignored — your secrets never leave the box.
- `BILLING_TEST_MODE` is intentionally **not** written to `.env`; production forces
  it off so no one can self-extend for free.
