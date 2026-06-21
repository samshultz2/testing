/*
 * App-wide soft navigation ("no reload" feel).
 *
 * The app is a set of per-section React islands rendered into `.page-content`,
 * each loading its own bundle. Within a section, navigation is already
 * reload-free (the React router). This layer makes navigation BETWEEN sections
 * — and any plain link in the menu or page — reload-free too: it fetches the
 * destination, swaps only the page body (and breadcrumb / flashes / sidebar
 * active state / title), and re-runs the new section's script so its React app
 * mounts. Anything it can't handle cleanly falls back to a real navigation, so
 * behaviour never regresses.
 *
 * Safety:
 *  - It ignores clicks a React handler already took (`defaultPrevented`), so the
 *    per-section routers keep working untouched.
 *  - Before swapping it fires `spa:swapping`; the shared `useSection` hook bumps
 *    a generation counter so a section detached by a swap stops reacting to
 *    history events (no leaks, no double-handling).
 *  - Only same-origin GET navigations from the menu or page content are taken.
 */
(function () {
  'use strict';
  // Only run inside the authenticated app layout (it has a sidebar + page body).
  if (!document.getElementById('sidebar') || !document.querySelector('.page-content')) return;
  if (window.__spaNavReady) return;
  window.__spaNavReady = true;

  var bar = document.getElementById('navProgress');
  function progress(on) {
    if (!bar) return;
    if (on) { bar.style.opacity = '1'; bar.style.width = '70%'; }
    else { bar.style.width = '100%'; setTimeout(function () { bar.style.opacity = '0'; bar.style.width = '0'; }, 200); }
  }

  function reexec(container) {
    // Scripts inserted via innerHTML don't execute; recreate executable ones so
    // the section's bundle runs and mounts. Non-JS scripts (the JSON data block)
    // are left in place.
    var scripts = container.querySelectorAll('script');
    for (var i = 0; i < scripts.length; i++) {
      var old = scripts[i];
      var type = (old.getAttribute('type') || '').toLowerCase();
      if (type && type !== 'text/javascript' && type !== 'application/javascript' && type !== 'module') continue;
      var s = document.createElement('script');
      if (old.src) s.src = old.src; else s.textContent = old.textContent;
      if (old.type) s.type = old.type;
      old.parentNode.replaceChild(s, old);
    }
  }

  function syncActive(doc, selector) {
    var fresh = doc.querySelector(selector);
    if (!fresh) return;
    var map = {};
    fresh.querySelectorAll('a').forEach(function (a) { map[a.getAttribute('href')] = a.className; });
    var live = document.querySelector(selector);
    if (!live) return;
    live.querySelectorAll('a').forEach(function (a) {
      var c = map[a.getAttribute('href')];
      if (c !== undefined) a.className = c;
    });
  }

  // Everything in <head> after the marker is the current page's {% block extra_css %}.
  function pageHeadNodes(d) {
    var marker = d.querySelector('head meta[name="spa-css-marker"]');
    var out = [];
    if (marker) { var n = marker.nextElementSibling; while (n) { out.push(n); n = n.nextElementSibling; } }
    return out;
  }

  function syncHead(doc) {
    // Swap the page-specific styles so the new body is styled immediately,
    // instead of looking broken until a manual reload.
    pageHeadNodes(document).forEach(function (n) { n.remove(); });   // drop current page's CSS
    pageHeadNodes(doc).forEach(function (node) {                     // add destination's CSS
      document.head.appendChild(document.importNode(node, true));
    });
  }

  function syncBodyScripts(doc) {
    // Page-specific scripts from {% block extra_js %} live in <body> outside
    // .page-content; re-run the destination's so per-page JS works after a swap.
    // NOTE: these scripts re-execute in the global scope on every navigation, so
    // page-level extra_js must NOT use top-level `const`/`let` (their lexical
    // bindings persist across swaps and throw "already declared" on re-run) —
    // use `var`/`function` at top level, which redeclare harmlessly.
    document.querySelectorAll('script[data-spa-extra]').forEach(function (n) { n.remove(); });
    var live = {};
    Array.prototype.forEach.call(document.body.querySelectorAll('script'),
      function (s) { if (!s.closest('.page-content')) live[s.outerHTML] = 1; });
    doc.body.querySelectorAll('script').forEach(function (node) {
      if (node.closest('.page-content')) return;   // section bundle — handled by reexec()
      if (live[node.outerHTML]) return;            // a base script, already running
      var s = document.createElement('script');
      if (node.src) s.src = node.src; else s.textContent = node.textContent;
      if (node.type) s.type = node.type;
      s.setAttribute('data-spa-extra', '1');
      document.body.appendChild(s);
    });
  }

  function swap(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var fresh = doc.querySelector('.page-content');
    if (!fresh) return false;                       // not an app page → caller falls back

    // Tell every loaded section it's being detached (stops stale history handlers).
    window.dispatchEvent(new Event('spa:swapping'));

    syncHead(doc);                                  // page CSS first, so no flash of unstyled body
    var cur = document.querySelector('.page-content');
    var imported = document.importNode(fresh, true);
    cur.parentNode.replaceChild(imported, cur);
    reexec(imported);
    syncBodyScripts(doc);                           // page-specific extra_js

    // Breadcrumb, title, flashes, and sidebar/bottom-nav active state.
    var nb = doc.querySelector('.breadcrumb'), cb = document.querySelector('.breadcrumb');
    if (nb && cb) cb.innerHTML = nb.innerHTML;
    if (doc.title) document.title = doc.title;
    var oldFlash = document.querySelector('.flash-messages');
    if (oldFlash) oldFlash.remove();
    var newFlash = doc.querySelector('.flash-messages');
    if (newFlash) imported.parentNode.insertBefore(document.importNode(newFlash, true), imported);
    syncActive(doc, '.sidebar-nav');
    syncActive(doc, '.bottom-nav');
    return true;
  }

  var navToken = 0;
  function softLoad(url, push) {
    var token = ++navToken;
    progress(true);
    fetch(url, { headers: { 'X-Requested-With': 'spa-nav' }, credentials: 'same-origin' })
      .then(function (r) {
        var ct = r.headers.get('content-type') || '';
        if (!r.ok || ct.indexOf('text/html') < 0) throw new Error('non-html');
        return r.text().then(function (html) { return { html: html, finalUrl: r.url }; });
      })
      .then(function (o) {
        if (token !== navToken) return;             // superseded by a newer click
        if (!swap(o.html)) { window.location = url; return; }
        if (push) history.pushState({ sn: 1 }, '', o.finalUrl || url);
        window.scrollTo(0, 0);
        progress(false);
        window.dispatchEvent(new Event('spa:loaded'));
      })
      .catch(function () { window.location = url; });   // never leave the user stuck
  }

  // Intercept menu + in-page link clicks only (not header controls).
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a');
    if (!a) return;
    if (!a.closest('.sidebar-nav, .bottom-nav, .page-content')) return;   // scope
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || a.target === '_blank' || a.hasAttribute('download')
        || a.hasAttribute('data-no-spa')) return;
    var url;
    try { url = new URL(a.href); } catch (_) { return; }
    if (url.origin !== location.origin) return;
    e.preventDefault();
    softLoad(a.href, true);
  });

  // Back / forward: re-render the destination in place (the per-section routers
  // for the previously-live section are already neutralised by spa:swapping).
  window.addEventListener('popstate', function () { softLoad(location.href, false); });
})();
