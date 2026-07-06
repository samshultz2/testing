# EduSyncra marketing site

This folder is the **public marketing homepage** — the page a brand-new school
lands on before it has an account. It is deliberately kept **separate from the
Flask application** so the marketing/sales team can edit copy, pricing and
design and redeploy it **without touching the product codebase**.

It is a single, self-contained `index.html` (all CSS + JS inline, no build
step, no dependencies). Open it in a browser to preview; edit the text and
redeploy.

---

## What it does

- **Hero + features + pricing + FAQ** landing page, light/dark aware, mobile
  responsive.
- **"Start free trial" / "Register"** buttons point at the product's signup
  route. The target URL is set once at the top of the inline `<script>`:

  ```js
  const SIGNUP_URL = "https://signup.edusyncra.site/register";
  ```

  Every `<a class="reg">` on the page is wired to that URL, so changing this
  one line repoints all the CTAs.

- **"Sign in"** box: a school types its subdomain (e.g. `glovic`) and is sent
  to `https://<subdomain>.edusyncra.site/login`. Existing schools therefore
  keep using the same address they already know — nothing to re-learn.

---

## Where to host it (so existing users don't need a new URL)

The product lives on `edusyncra.site` (the owner school is served at the apex,
each tenant at `<subdomain>.edusyncra.site`). Until `edusyncra.com` is bought,
host this page on a subdomain of the domain you already own:

- **`www.edusyncra.site`** — recommended. Marketing homepage.
- **`signup.edusyncra.site`** — reserved subdomain that maps to the app's
  `/register` route (already in `RESERVED_SUBDOMAINS`), so `SIGNUP_URL` above
  resolves to the real signup form inside the app.

Existing schools never see this page — they go straight to their own
subdomain — so their bookmarks keep working unchanged.

### Option A — Cloudflare Pages (recommended, free, marketing edits it directly)

1. Push this `marketing/` folder to its own tiny repo (or a subfolder) that the
   marketing team owns.
2. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
3. Build settings: **no framework**, build command empty, output directory
   `marketing` (or the repo root if you split it out).
4. After the first deploy, **Custom domains → Set up a custom domain →
   `www.edusyncra.site`**. Cloudflare adds the CNAME for you since the zone is
   already on Cloudflare.
5. Marketing now edits `index.html` in that repo; every push redeploys. The
   product codebase is never touched.

### Option B — serve it from the phone/Termux server

If you'd rather not use Pages, drop `index.html` behind the same Cloudflare
tunnel on a path/subdomain of its own (e.g. a static route or a second tiny
static server on another port), then point `www` at it. This keeps everything
on the one box but couples redeploys to the server.

**Recommendation:** Option A. It keeps marketing fully independent, is free, and
survives the phone being offline.

---

## Editing checklist for marketing

- Price / trial length: search the file for `50,000` and `3 days`.
- Signup destination: the `SIGNUP_URL` constant near the bottom.
- Everything else (headlines, features, FAQ) is plain HTML text — edit in place.
- After editing, just commit & push (Pages) or re-copy the file (self-host).
