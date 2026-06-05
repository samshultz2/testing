/* PosyHub service worker.
   - Static assets: cache-first (fast repeat loads, installability).
   - Page navigations: network-first with an offline fallback to the last
     cached copy of that page, then a generic offline page. This lets pages you
     have already visited stay viewable with no connection.
   Note: cached pages live on the device; suitable for a single-user, phone-
   hosted install. Mutations (POST/etc.) always require the network. */
const STATIC_CACHE = 'posyhub-static-v2';
const RUNTIME_CACHE = 'posyhub-runtime-v2';
const OFFLINE_URL = '/static/offline.html';
const ASSETS = [
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/manifest.webmanifest',
  OFFLINE_URL
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(STATIC_CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  const keep = [STATIC_CACHE, RUNTIME_CACHE];
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
  if (url.origin !== self.location.origin) return;     // only same-origin

  // Static assets: cache-first.
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(STATIC_CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => hit))
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
