/*
 * MathJax loader for CBT question/option LaTeX — SPA-safe, idempotent.
 *
 * Same double-load guard as static/js/mathjax-setup.js (see that file), but with
 * the CBT delimiter set: teachers may write inline math as \( … \) OR $ … $ and
 * display math as \[ … \] OR $$ … $$.
 *
 * External 'self' script (no inline nonce) so the admin's soft-navigation SPA can
 * re-run it after a .page-content swap without CSP blocking it, and so the heavy
 * library is appended programmatically (never as a static <script> that would
 * re-execute — and re-initialise MathJax — on every soft navigation).
 */
(function () {
  'use strict';

  if (!window.MathJax) {
    window.MathJax = {
      tex: {
        inlineMath: [['\\(', '\\)'], ['$', '$']],
        displayMath: [['\\[', '\\]'], ['$$', '$$']]
      },
      options: { skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'] },
      chtml: { fontURL: '/static/vendor/mathjax/output/chtml/fonts/woff-v2' }
    };
  }

  window.renderMath = window.renderMath || function (el) {
    if (window.MathJax && window.MathJax.typesetPromise) {
      try { window.MathJax.typesetPromise(el ? [el] : undefined).catch(function () {}); }
      catch (e) { /* ignore */ }
    }
  };

  // Load once — guard on the runtime + a persistent flag, never on the DOM node
  // (a soft-nav can remove the <script> while the library stays loaded in memory;
  // re-adding it re-runs startup on an initialised instance and throws
  // "Cannot set property Package … has only a getter").
  if (window.MathJax && window.MathJax.startup) {
    window.renderMath();
  } else if (!window.__mjLoading) {
    window.__mjLoading = true;
    var s = document.createElement('script');
    s.id = 'MathJax-script';
    s.async = true;
    s.src = '/static/vendor/mathjax/tex-mml-chtml.js';
    document.head.appendChild(s);
  }

  if (!window.__mjSpaHook) {
    window.__mjSpaHook = true;
    window.addEventListener('spa:loaded', function () { window.renderMath(); });
  }
})();
