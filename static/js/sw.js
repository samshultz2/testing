/* EduSyncra service worker.
   - Static assets: cache-first (fast repeat loads, installability).
   - Page navigations: network-first with an offline fallback to the last
     cached copy of that page, then a generic offline page. This lets pages you
     have already visited stay viewable with no connection.
   Note: cached pages live on the device; suitable for a single-user, phone-
   hosted install. Mutations (POST/etc.) always require the network. */
// Bump CACHE_VERSION whenever static assets (icons/CSS/JS) change so clients
// pick them up promptly. Static assets also use stale-while-revalidate below,
// so they self-heal on the next load even without a bump.
const CACHE_VERSION = 'v10';
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
  '/static/manifest.webmanifest',
  OFFLINE_URL
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(STATIC_CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  const keep = [STATIC_CACHE, RUNTIME_CACHE, CDN_CACHE];
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !keep.includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

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

  // Page navigations: network-first, fall back to cached page, then offline page.
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(RUNTIME_CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() =>
        caches.match(req).then((hit) => hit || caches.match(OFFLINE_URL))
      )
    );
  }
});
