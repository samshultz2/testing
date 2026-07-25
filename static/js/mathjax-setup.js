/*
 * MathJax loader for Mock JAMB question text, options and passages — SPA-safe.
 *
 * The admin runs a soft-navigation SPA (static/js/spa-nav.js) that swaps
 * `.page-content` via innerHTML. Two consequences this file handles:
 *   1. An inline <script nonce> re-added after a swap loses its nonce and is
 *      CSP-blocked — so the config/loader must live in THIS external 'self'
 *      script (allowed by script-src without a nonce), which spa-nav re-runs
 *      cleanly on each navigation.
 *   2. MathJax auto-typesets only once at startup, so freshly-swapped content
 *      would stay as raw LaTeX. We re-typeset after every `spa:loaded`, and once
 *      immediately whenever the library is already loaded.
 *
 * Delimiters are \( … \) and \[ … \] only (never $ … $), so a currency amount in
 * a stem is not mistaken for maths. Loaded from jsdelivr (allowed by CSP).
 */
(function () {
  'use strict';

  if (!window.MathJax) {
    window.MathJax = {
      tex: { inlineMath: [['\\(', '\\)']], displayMath: [['\\[', '\\]']] },
      options: { skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'] },
      // Self-hosted fonts (see /static/vendor/mathjax) so the exam never depends
      // on a CDN — works offline and on networks that block jsdelivr.
      chtml: { fontURL: '/static/vendor/mathjax/output/chtml/fonts/woff-v2' }
    };
  }

  // Re-typeset a node (or the whole page) after client-side DOM changes.
  window.renderMath = function (el) {
    if (window.MathJax && window.MathJax.typesetPromise) {
      try { window.MathJax.typesetPromise(el ? [el] : undefined).catch(function () {}); }
      catch (e) { /* ignore */ }
    }
  };

  // (Question-table styling lives in static/css/style.css so it applies even if
  // this script hasn't run.)

  // Load the library at most once per page. Guard on the actual MathJax runtime
  // (window.MathJax.startup) and a persistent "loading" flag — NOT just the DOM
  // <script> node. A soft-navigation can remove a #MathJax-script that lived in
  // .page-content (e.g. a CBT page's) while the library stays loaded in memory;
  // re-adding it then re-runs MathJax's startup against an already-initialised
  // instance and throws "Cannot set property Package … has only a getter".
  if (window.MathJax && window.MathJax.startup) {
    // Fully loaded already → just typeset the freshly-swapped content.
    window.renderMath();
  } else if (!window.__mjLoading) {
    // First time (or the in-flight load hasn't finished): load it once. Into
    // <head> so it survives .page-content swaps. It auto-typesets on startup.
    window.__mjLoading = true;
    var s = document.createElement('script');
    s.id = 'MathJax-script';
    s.async = true;
    s.src = '/static/vendor/mathjax/tex-mml-chtml.js';
    document.head.appendChild(s);
  }
  // else: a load kicked off by an earlier navigation is still in flight; it will
  // auto-typeset when it finishes — do nothing (adding it again would double-load).

  // After any soft navigation, re-typeset (installed once).
  if (!window.__mjSpaHook) {
    window.__mjSpaHook = true;
    window.addEventListener('spa:loaded', function () { window.renderMath(); });
  }
})();
