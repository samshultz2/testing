/* Offline write queue.
 * Any <form data-offline> submits via fetch. If the network/server is
 * unreachable, the submission is saved on the device and replayed automatically
 * when the connection returns, with a small "waiting to sync" indicator. This
 * makes attendance/score entry survive a dropped or very poor connection.
 */
(function () {
  var KEY = 'posyhub_outbox';

  function load() { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; } }
  function save(q) { try { localStorage.setItem(KEY, JSON.stringify(q)); } catch (e) {} updateBadge(); }

  function formBody(form) {
    var fd = new FormData(form), p = new URLSearchParams();
    fd.forEach(function (v, k) { if (typeof v === 'string') p.append(k, v); });
    return p.toString();
  }

  // ---- the "waiting to sync" badge -----------------------------------------
  var badgeEl = null;
  function badge() {
    if (badgeEl) return badgeEl;
    badgeEl = document.createElement('div');
    badgeEl.id = 'offlineBadge';
    badgeEl.style.cssText = 'position:fixed;bottom:14px;left:14px;z-index:9999;'
      + 'background:#b45309;color:#fff;padding:.5rem .8rem;border-radius:10px;'
      + 'font-size:.82rem;box-shadow:0 2px 10px rgba(0,0,0,.25);display:none;cursor:pointer;';
    badgeEl.title = 'Tap to retry now';
    badgeEl.addEventListener('click', flush);
    document.body.appendChild(badgeEl);
    return badgeEl;
  }
  function updateBadge() {
    var n = load().length, b = badge();
    if (!n) { b.style.display = 'none'; return; }
    b.textContent = '↻ ' + n + ' change' + (n > 1 ? 's' : '') + ' waiting to sync';
    b.style.display = 'block';
  }

  function toast(msg) {
    var t = document.createElement('div');
    t.style.cssText = 'position:fixed;bottom:60px;left:14px;z-index:9999;max-width:80%;'
      + 'background:#1f2937;color:#fff;padding:.6rem .9rem;border-radius:10px;'
      + 'font-size:.85rem;box-shadow:0 2px 10px rgba(0,0,0,.3);';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 4500);
  }

  // ---- submit interception --------------------------------------------------
  // Online: let the browser submit normally (real navigation + flash message —
  // zero behaviour change). Only when the device is genuinely offline do we
  // queue the submission and replay it on reconnect.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.matches || !form.matches('form[data-offline]')) return;
    if (navigator.onLine !== false) return;        // online → don't interfere
    e.preventDefault();
    var url = form.getAttribute('action') || location.href;
    var label = form.getAttribute('data-offline-label') || 'Your changes';
    var q = load(); q.push({ url: url, body: formBody(form), label: label, ts: Date.now() }); save(q);
    toast(label + ' saved on this device — it will sync automatically when you’re back online.');
  }, true);

  // ---- replay ---------------------------------------------------------------
  var flushing = false;
  function freshBody(body) {
    // Queued items may be days old; the session CSRF token they captured can be
    // stale. Swap in the current page's token so the replay isn't rejected.
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta) return body;
    var p = new URLSearchParams(body);
    if (p.has('_csrf_token')) p.set('_csrf_token', meta.content);
    return p.toString();
  }
  function flush() {
    if (flushing) return;
    var q = load();
    if (!q.length) return;
    flushing = true;
    var item = q[0];
    fetch(item.url, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                      body: freshBody(item.body), redirect: 'follow' })
      .then(function (res) {
        // Session expired → the POST bounces to the login page. KEEP the item:
        // it syncs after the user logs back in (we retry on every page load).
        if (res.redirected && res.url.indexOf('/login') !== -1) {
          flushing = false;
          toast('Please log in to sync your saved changes.');
          return;
        }
        if (res.status >= 400) throw new Error('http ' + res.status);
        var rest = load(); rest.shift(); save(rest);
        flushing = false;
        if (rest.length) flush(); else toast('All offline changes have been synced.');
      })
      .catch(function () { flushing = false; /* still offline / rejected; retry later */ });
  }

  window.addEventListener('online', flush);
  document.addEventListener('DOMContentLoaded', function () { updateBadge(); if (load().length) flush(); });
})();
