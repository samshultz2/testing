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

  function activeNonce() {
    // The current document's CSP nonce, stable for this page's lifetime. Inline
    // scripts we recreate on a soft-nav must carry it or the nonce-based CSP
    // (script-src 'self' 'nonce-…', no 'unsafe-inline') blocks them — which is
    // what left inline-initialised content (e.g. Chart.js pages) blank until a
    // full reload. Prefer the <meta name="csp-nonce"> value: a <meta> is not
    // subject to the nonce-hiding that blanks a <script>'s nonce after load
    // (some mobile WebViews then return '' from the .nonce IDL too). Fall back
    // to a nonce-bearing script for older pages that predate the meta tag.
    var m = document.querySelector('meta[name="csp-nonce"]');
    if (m && m.content) return m.content;
    var el = document.querySelector('script[nonce]');
    return (el && (el.nonce || el.getAttribute('nonce'))) || '';
  }

  function inlineBody(text) {
    // Run re-executed inline scripts in their OWN function scope. A classic inline
    // script runs in global scope, and removing its <script> element does NOT undo
    // its top-level `const`/`let`/`class` declarations — so re-running the same page
    // on a later soft navigation threw "Identifier already declared", which aborted
    // that page's script and left its buttons dead until a hard refresh. Wrapping
    // makes every re-run independent. (Module scripts already have their own scope,
    // so those are left untouched by the caller.)
    return '(function(){\n' + text + '\n})();';
  }

  function buildScript(old, nonce) {
    // Recreate one <script> so it actually executes (scripts inserted via
    // innerHTML/DOMParser never run). Returns the fresh element, or null for a
    // non-JS block (e.g. the inline JSON data island) that must be left as-is.
    var type = (old.getAttribute('type') || '').toLowerCase();
    if (type && type !== 'text/javascript' && type !== 'application/javascript' && type !== 'module') return null;
    var s = document.createElement('script');
    if (old.src) s.src = old.src;
    else if (type === 'module') s.textContent = old.textContent;   // module = own scope
    else s.textContent = inlineBody(old.textContent);              // scope per re-run
    if (old.type) s.type = old.type;
    // Inline scripts need this document's nonce or the CSP blocks them.
    if (!old.src && nonce) s.setAttribute('nonce', nonce);
    // Ordered execution: a dynamically-inserted external script is async by
    // default, so it would run whenever it happens to finish loading. async=false
    // (plus the awaited onload in runInOrder) makes externals run in insertion
    // order — exactly like the HTML parser does on a hard load.
    s.async = false;
    return s;
  }

  function insertAndSettle(s, insert) {
    // insert() places the node, which triggers its execution. An inline script
    // runs synchronously on insertion, so it's already done. An external one
    // executes when it finishes loading, so we resolve on load/error — the NEXT
    // script (which may depend on this one, e.g. a Chart.js init after chart.js)
    // waits for it. THIS is the fix for charts/buttons that were blank or dead
    // after a soft navigation until a hard refresh: on a hard load the parser
    // guarantees a dependency runs before the code that uses it, but naive
    // re-insertion made the dependency async, so the dependent inline code ran
    // first, threw, and aborted — killing that page's charts and click handlers.
    if (s.src) {
      return new Promise(function (resolve) {
        s.onload = s.onerror = function () { resolve(); };
        insert(s);
      });
    }
    insert(s);
    return Promise.resolve();
  }

  function runInOrder(olds, nonce, insertFor, tokenAtStart) {
    // Execute a list of parsed <script> nodes strictly in order, awaiting each
    // external script before running the next. Returns a Promise. Bails if a
    // newer navigation superseded this one (tokenAtStart !== navToken), so
    // in-flight scripts from an abandoned page can't mount into the live one.
    return olds.reduce(function (p, old) {
      return p.then(function () {
        if (tokenAtStart !== navToken) return;         // superseded — stop
        var s = buildScript(old, nonce);
        if (!s) return;                                 // leave JSON/data blocks
        return insertAndSettle(s, function (el) { insertFor(old, el); });
      });
    }, Promise.resolve());
  }

  function reexec(container, token) {
    // Re-run the section bundle + any inline scripts inside .page-content, in
    // order. Non-JS scripts (the JSON data block) are left in place by buildScript.
    var nonce = activeNonce();
    var scripts = Array.prototype.slice.call(container.querySelectorAll('script'));
    return runInOrder(scripts, nonce, function (old, el) {
      old.parentNode.replaceChild(el, old);
    }, token);
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

  function syncBodyScripts(doc, token) {
    // Page-specific scripts from {% block extra_js %} live in <body> outside
    // .page-content; re-run the destination's so per-page JS works after a swap.
    // Ordered + dependency-aware (runInOrder), so a lib like chart.umd.min.js is
    // fully loaded before the inline `new Chart(...)` init that follows it.
    // NOTE: these scripts re-execute in the global scope on every navigation, so
    // page-level extra_js must NOT use top-level `const`/`let` (their lexical
    // bindings persist across swaps and throw "already declared" on re-run) —
    // use `var`/`function` at top level, which redeclare harmlessly.
    document.querySelectorAll('script[data-spa-extra]').forEach(function (n) { n.remove(); });
    var nonce = activeNonce();
    var live = {};
    Array.prototype.forEach.call(document.body.querySelectorAll('script'),
      function (s) { if (!s.closest('.page-content')) live[s.outerHTML] = 1; });
    var pending = [];
    doc.body.querySelectorAll('script').forEach(function (node) {
      if (node.closest('.page-content')) return;   // section bundle — handled by reexec()
      if (live[node.outerHTML]) return;            // a base script, already running
      pending.push(node);
    });
    return runInOrder(pending, nonce, function (old, el) {
      el.setAttribute('data-spa-extra', '1');
      document.body.appendChild(el);
    }, token);
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
    // Run the section's scripts, then the page's extra_js — in order, awaiting
    // external deps at each step (see runInOrder). Content scripts run before
    // extra_js, matching document order on a hard load. Fire-and-forget: the DOM
    // is already live, so breadcrumb/title updates below need not wait on JS.
    var tok = navToken;
    reexec(imported, tok).then(function () { return syncBodyScripts(doc, tok); });

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

  // Links that return a file (PDF/Excel/CSV…) or a standalone print page must be
  // handled natively by the browser — soft-loading them fetches the file as if it
  // were a page and dumps the user into the app shell instead of downloading.
  function isFileLink(u) {
    return /\.(pdf|xlsx?|csv|docx?|pptx?|zip|png|jpe?g|svg|txt)$/i.test(u.pathname)
        || /(^|\/)(export|download|print)(\/|$|_)/i.test(u.pathname)
        || /[?&](format|export)=(pdf|xlsx?|csv|excel|word|docx?)/i.test(u.search);
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
    if (isFileLink(url)) return;                 // let the browser download/open it
    e.preventDefault();
    softLoad(a.href, true);
  });

  // Back / forward: re-render the destination in place (the per-section routers
  // for the previously-live section are already neutralised by spa:swapping).
  window.addEventListener('popstate', function () { softLoad(location.href, false); });
})();
