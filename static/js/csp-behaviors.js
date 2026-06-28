/*
 * CSP-safe declarative behaviours.
 *
 * The app's Content-Security-Policy drops 'unsafe-inline', which disables inline
 * on* handlers (onclick/onchange/onsubmit). These were replaced by data-attributes
 * wired here through event delegation, so they also work for elements inserted
 * later by the React/SPA layers. Keep this dependency-free and defensive.
 */
(function () {
  'use strict';

  // ---- generic call dispatcher --------------------------------------------
  // Replaces inline `onclick="fn(args)"` / `onchange="fn(args)"` calls to global
  // page functions. Usage: data-call="fn" [data-args="a|b|..."] [data-on="change"].
  // Args are pipe-separated; tokens map the way the original inline JS read them:
  //   this -> the element, this.checked -> its checkbox state, 'x'/"x" -> string,
  //   true/false/null -> literal, 12 -> number, otherwise the raw string.
  function parseArgs(raw, el) {
    if (raw == null || raw === '') return [];
    return raw.split('|').map(function (a) {
      a = a.trim();
      if (a === 'this') return el;
      if (a === 'this.checked') return !!el.checked;
      if (a === 'this.value') return el.value;
      if (a === 'true') return true;
      if (a === 'false') return false;
      if (a === 'null') return null;
      if (/^-?\d+(\.\d+)?$/.test(a)) return Number(a);
      return a.replace(/^['"]([\s\S]*)['"]$/, '$1');
    });
  }
  function runCall(el) {
    var fn = window[el.getAttribute('data-call')];
    if (typeof fn !== 'function') return false;
    fn.apply(el, parseArgs(el.getAttribute('data-args'), el));
    return true;
  }

  // change: [data-autosubmit] submits its owning form (was onchange="this.form.submit()")
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (t && t.matches && t.matches('[data-autosubmit]') && t.form) {
      t.form.submit();
      return;
    }
    var c = e.target.closest && e.target.closest('[data-call][data-on="change"]');
    if (c) runCall(c);
  });

  // submit: a form with [data-confirm] asks before submitting (was onsubmit="return confirm(...)")
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (f && f.matches && f.matches('form[data-confirm]')) {
      if (!window.confirm(f.getAttribute('data-confirm'))) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
  }, true);

  // click: a small set of declarative actions.
  document.addEventListener('click', function (e) {
    // generic call dispatch first (default event is click)
    var caller = e.target.closest('[data-call]');
    if (caller && (caller.getAttribute('data-on') || 'click') === 'click') {
      if (runCall(caller)) { e.preventDefault(); return; }
    }

    var el = e.target.closest(
      '[data-print],[data-copy],[data-confirm]:not(form),[data-remove-closest],' +
      '[data-remove-target],[data-remove-parent],[data-select]');
    if (!el) return;

    // remove the element's parent (was onclick="this.parentElement.remove()")
    if (el.hasAttribute('data-remove-parent')) {
      e.preventDefault();
      if (el.parentElement) el.parentElement.remove();
      return;
    }

    // print the page (was onclick="window.print()")
    if (el.hasAttribute('data-print')) {
      e.preventDefault();
      window.print();
      return;
    }

    // confirm before following a link / running the default (non-form elements)
    if (el.hasAttribute('data-confirm')) {
      if (!window.confirm(el.getAttribute('data-confirm'))) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
    }

    // copy the innerText of #id to the clipboard, with brief "Copied" feedback
    if (el.hasAttribute('data-copy')) {
      e.preventDefault();
      var src = document.getElementById(el.getAttribute('data-copy'));
      if (src && navigator.clipboard) {
        navigator.clipboard.writeText(src.innerText).then(function () {
          var done = el.getAttribute('data-copied') || 'Copied';
          el.innerHTML = '<i class="fas fa-check"></i> ' + done;
        });
      }
      return;
    }

    // remove the nearest matching ancestor, or an element by id
    if (el.hasAttribute('data-remove-closest')) {
      e.preventDefault();
      var anc = el.closest(el.getAttribute('data-remove-closest'));
      if (anc) anc.remove();
      return;
    }
    if (el.hasAttribute('data-remove-target')) {
      e.preventDefault();
      var tgt = document.getElementById(el.getAttribute('data-remove-target'));
      if (tgt) tgt.remove();
      return;
    }

    // select the field's text (was onclick="this.select()")
    if (el.hasAttribute('data-select') && el.select) {
      el.select();
      return;
    }
  });
})();
