/* EduSyncra service worker.
   - Static assets: cache-first (fast repeat loads, installability).
   - Page navigations: network-first with an offline fallback to the last
     cached copy of that page, then a generic offline page. This lets pages you
     have already visited stay viewable with no connection.
   Note: cached pages live on the device; suitable for a single-user, phone-
   hosted install. Mutations (POST/etc.) always require the network. */
// CACHE_VERSION is stamped automatically by frontend/build.mjs from a content
// hash of the built bundles + CSS (format 'b-<hash>'), so it changes on every
// deploy that changes an asset — no manual bump needed. Static assets also use
// stale-while-revalidate below, so they self-heal on the next load regardless.
const CACHE_VERSION = 'b-97792af8813c';
// Cap the runtime cache (visited pages + section JSON) so it can't grow without
// bound on a long-lived install; oldest entries are evicted first.
const RUNTIME_MAX_ENTRIES = 80;
const STATIC_CACHE = `posyhub-static-${CACHE_VERSION}`;
const RUNTIME_CACHE = `posyhub-runtime-${CACHE_VERSION}`;
const CDN_CACHE = `posyhub-cdn-${CACHE_VERSION}`;
const OFFLINE_URL = '/static/offline.html';
// Third-party libraries loaded from CDNs — cached so the app stays fast and works
// under poor/no network instead of re-downloading them on every page load.
const CDN_HOSTS = ['cdn.jsdelivr.net', 'cdnjs.cloudflare.com',
                   'fonts.googleapis.com', 'fonts.gstatic.com'];
const ASSETS = [
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/js/command-palette.js',
  '/static/img/logo-mark.svg',
  '/static/img/favicon.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-192-maskable.png',
  '/static/icons/icon-512-maskable.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon-32.png',
  // Self-hosted icon font + chart libs (no CDN dependency for core UI).
  '/static/vendor/fontawesome/css/all.min.css',
  '/static/vendor/fontawesome/webfonts/fa-solid-900.woff2',
  '/static/vendor/fontawesome/webfonts/fa-regular-400.woff2',
  '/static/vendor/chart.umd.min.js',
  '/static/vendor/react.production.min.js',
  '/static/vendor/react-dom.production.min.js',
  '/static/js/react/spike.js',
  '/static/js/react/attendance.js',
  '/static/js/react/attendance-app.js',
  '/static/js/react/dashboard-app.js',
  '/static/js/react/students-app.js',
  '/static/js/react/student-view-app.js',
  '/static/js/react/student-form-app.js',
  '/static/js/react/student-trash-app.js',
  '/static/js/react/sales-app.js',
  '/static/js/react/library-app.js',
  '/static/js/react/events-app.js',
  '/static/js/react/admissions-app.js',
  '/static/js/react/reports-app.js',
  '/static/js/react/promotion-app.js',
  '/static/js/react/mock-jamb-app.js',
  '/static/js/react/comms-app.js',
  '/static/js/react/hr-app.js',
  '/static/js/react/finance-app.js',
  '/static/js/react/subjects-app.js',
  '/static/js/react/results-app.js',
  '/static/js/react/cbt-app.js',
  '/static/js/react/academics-app.js',
  '/static/js/react/settings-app.js',
  '/static/js/react/users-app.js',
  '/static/js/react/contributions-app.js',
  '/static/js/react/timetable-app.js',
  '/static/js/react/scratchcards-app.js',
  '/static/js/react/parent-app.js',
  '/static/js/spa-nav.js',
  // Self-hosted MathJax so exam maths renders with no CDN (fonts load on demand
  // via stale-while-revalidate and are then available offline too).
  '/static/js/mathjax-setup.js',
  '/static/js/mathjax-setup-cbt.js',
  '/static/vendor/mathjax/tex-mml-chtml.js',
  '/static/manifest.webmanifest',
  OFFLINE_URL
];

self.addEventListener('install', (e) => {
  // Resilient precache: cache each asset independently so a single missing/404
  // file can't reject the whole install and leave the SW stuck (which would
  // break offline for everyone). addAll is all-or-nothing; allSettled is not.
  e.waitUntil(
    caches.open(STATIC_CACHE)
      // cache:'reload' bypasses the browser's HTTP cache so a fresh install
      // stores truly current bytes, not a stale copy the browser held onto.
      .then((c) => Promise.allSettled(
        ASSETS.map((u) => c.add(new Request(u, { cache: 'reload' })))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  const keep = [STATIC_CACHE, RUNTIME_CACHE, CDN_CACHE];
  e.waitUntil(
    (async () => {
      // Faster network-first navigations: let the browser start the request
      // while the SW is still spinning up.
      if (self.registration.navigationPreload) {
        try { await self.registration.navigationPreload.enable(); } catch (_) { /* unsupported */ }
      }
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => !keep.includes(k)).map((k) => caches.delete(k)));
      await self.clients.claim();
    })()
  );
});

// Keep a cache from growing without bound: trim to the newest `max` entries
// (cache.keys() preserves insertion order, so the front is the oldest).
async function trimCache(name, max) {
  try {
    const cache = await caches.open(name);
    const keys = await cache.keys();
    for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
  } catch (_) { /* best-effort */ }
}

self.addEventListener('message', (e) => {
  // Allow the app to clear cached pages (e.g. on logout).
  if (e.data === 'clear-runtime') {
    caches.delete(RUNTIME_CACHE);
  }
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                    // never cache mutations
  const url = new URL(req.url);

  // Remaining third-party CDN assets (Google Fonts, MathJax): cache-first with
  // background refresh. Only successful (or opaque cross-origin) responses are
  // cached — caching an error response here is what used to permanently blank
  // the icons until users manually cleared the cache.
  if (CDN_HOSTS.includes(url.hostname)) {
    e.respondWith(
      caches.open(CDN_CACHE).then((cache) =>
        cache.match(req).then((hit) => {
          const network = fetch(req).then((res) => {
            if (res && (res.ok || res.type === 'opaque')) cache.put(req, res.clone());
            return res;
          }).catch(() => hit);
          return hit || network;
        })
      )
    );
    return;
  }

  if (url.origin !== self.location.origin) return;     // only same-origin beyond this

  // Static assets: stale-while-revalidate. Serve the cached copy instantly for
  // speed, but always fetch a fresh copy in the background and update the cache,
  // so replaced icons/CSS/JS appear on the next load without a manual clear.
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.match(req).then((hit) => {
          const network = fetch(req).then((res) => {
            if (res && res.status === 200) cache.put(req, res.clone());
            return res;
          }).catch(() => hit);
          return hit || network;
        })
      )
    );
    return;
  }

  // Page requests: full-page navigations AND in-app SPA soft-navigations (which
  // arrive as fetch() with the X-Requested-With: spa-nav header, NOT mode
  // 'navigate'). Both must be cached, or pages reached only via the in-app menu
  // are never stored and won't open offline. Network-first so online always wins;
  // the HTML is cached under the bare URL so navigate and SPA requests share one
  // entry and a visited page opens offline.
  const isPage = req.mode === 'navigate'
    || req.headers.get('X-Requested-With') === 'spa-nav';
  if (isPage) {
    e.respondWith(
      // Prefer the navigation-preload response (started by the browser before the
      // SW woke up) when present, else a normal fetch.
      Promise.resolve(e.preloadResponse).then((pre) => pre || fetch(req)).then((res) => {
        // Only cache genuine HTML pages — never files served inline as
        // navigations (PDF previews, downloads), or stale copies get served back.
        const ct = res.headers.get('Content-Type') || '';
        const disp = res.headers.get('Content-Disposition') || '';
        if (res.ok && ct.indexOf('text/html') !== -1 && disp.indexOf('attachment') === -1) {
          const copy = res.clone();
          caches.open(RUNTIME_CACHE).then((c) =>
            c.put(req.url, copy).then(() => trimCache(RUNTIME_CACHE, RUNTIME_MAX_ENTRIES)));
        }
        return res;
      }).catch(() =>
        // Offline: serve the cached page (ignoreVary so a page cached under a
        // different header set — e.g. Vary: Cookie — still matches), else the
        // generic offline page.
        caches.match(req.url, { ignoreVary: true })
          .then((hit) => hit || caches.match(OFFLINE_URL))
          .then((resp) => resp || new Response(
            '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            + '<body style="font-family:system-ui;text-align:center;padding:3rem 1rem;color:#334">'
            + '<h1>You are offline</h1><p>This page hasn\'t been saved for offline use yet. '
            + 'Reconnect, open it once, and it will be available offline next time.</p>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' }, status: 200 }))
      )
    );
    return;
  }

  // In-app data requests: section JSON payloads (fetchPage) and apiGet calls,
  // marked by the headers the app sends (X-Requested-With: fetch / Accept: json).
  // Network-first so online is always fresh; the JSON is cached so dynamic
  // screens still render their last-known data offline.
  const wantsData = req.headers.get('X-Requested-With') === 'fetch'
    || (req.headers.get('Accept') || '').indexOf('application/json') !== -1;
  if (wantsData) {
    e.respondWith(
      fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(RUNTIME_CACHE).then((c) =>
            c.put(req.url, copy).then(() => trimCache(RUNTIME_CACHE, RUNTIME_MAX_ENTRIES)));
        }
        return res;
      }).catch(() => caches.match(req.url, { ignoreVary: true }))
    );
    return;
  }
});
