# Marketing homepage

The public marketing homepage is now **served by the app itself and edited
live** — there is no separate static site and nothing for Cloudflare to host.
Cloudflare only ever handles DNS.

## Where it lives

- **Public page:** `https://www.<your-domain>` (e.g. `https://www.edusyncra.site`)
  — served by the app on any *platform host* (a reserved subdomain such as
  `www`/`signup`, or the apex if no owner school claims it).
  Template: `templates/marketing/home.html`.
- **Register link on the page** → `/register` (the in-app signup form).
- **"Sign in" box** → sends a school to `https://<subdomain>.<your-domain>/`.

## Editing the content (no code, no deploy)

The marketing/sales team edits everything from the platform dashboard:

1. Sign in as a platform admin on the owner host (`https://<your-domain>`).
2. Go to **`/platform`** → click **Edit homepage** (`/platform/homepage`).
3. Change the headline, sub-headline, CTA text, trial note, price, features,
   how-it-works steps, FAQ and footer, then **Save**. Changes are live
   immediately.

Features / steps / FAQ are edited as simple `Title | description` (or
`Question | Answer`) lines — one per line — so no JSON or code is involved.

Content is stored in the **control-plane database**
(`utils/tenancy.py` → `SiteContent`), with sensible defaults in
`utils/site_content.py` used until something is overridden. The price defaults
to the configured subscription amount (`TENANT_PRICE_KOBO`) unless you set an
explicit figure in the editor.

## Making the URLs resolve (DNS only)

Point `www` (and `signup`) at the app the same way your school subdomains
already resolve — the wildcard `*.<domain>` record through your tunnel covers
them, and both are in `RESERVED_SUBDOMAINS` so the app treats them as platform
hosts rather than schools. Nothing else in Cloudflare is involved.
