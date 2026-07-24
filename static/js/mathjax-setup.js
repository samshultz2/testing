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
      options: { skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'] }
    };
  }

  // Re-typeset a node (or the whole page) after client-side DOM changes.
  window.renderMath = function (el) {
    if (window.MathJax && window.MathJax.typesetPromise) {
      try { window.MathJax.typesetPromise(el ? [el] : undefined).catch(function () {}); }
      catch (e) { /* ignore */ }
    }
  };

  // Table styling for questions rendered from a scraped [table: …] marker
  // (see utils.mathtext.question_html). Injected once; style-src allows this.
  if (!document.getElementById('mjq-style')) {
    var st = document.createElement('style');
    st.id = 'mjq-style';
    st.textContent =
      '.mjq-table{border-collapse:collapse;margin:.5rem 0;font-size:.9em;max-width:100%}' +
      '.mjq-table th,.mjq-table td{border:1px solid var(--border-color,#cbd5e1);padding:.28rem .6rem;text-align:left}' +
      '.mjq-table th{background:var(--gray-50,#f1f5f9);font-weight:700}';
    document.head.appendChild(st);
  }

  if (!document.getElementById('MathJax-script')) {
    // First time on a maths page: load the library (it auto-typesets on startup).
    var s = document.createElement('script');
    s.id = 'MathJax-script';
    s.async = true;
    s.src = 'https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js';
    document.head.appendChild(s);
  } else {
    // Already loaded on a previous page → typeset the just-swapped content now.
    window.renderMath();
  }

  // After any soft navigation, re-typeset (installed once).
  if (!window.__mjSpaHook) {
    window.__mjSpaHook = true;
    window.addEventListener('spa:loaded', function () { window.renderMath(); });
  }
})();
