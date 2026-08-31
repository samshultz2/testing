// Command palette (⌘K / Ctrl-K) — a fast keyboard-driven switcher over every
// destination the user can reach, so navigating doesn't mean hunting a 16-module
// sidebar tree. It indexes the already-rendered sidebar nav, which the server has
// ALREADY permission-gated, so the palette automatically shows only what this
// role may open (single source of truth — no parallel permission list to drift).
// CSP-safe: external script, no inline handlers; all listeners attached in JS.
(function () {
  'use strict';

  var RECENT_KEY = 'cmdk:recent';
  var overlay = null, input = null, listEl = null, emptyEl = null;
  var items = [], filtered = [], active = 0, lastFocus = null, isOpen = false;

  function iconOf(a) {
    var i = a.querySelector('i');
    if (!i) return 'fas fa-arrow-right';
    return i.getAttribute('class').replace(/\bactive\b/g, '').trim() || 'fas fa-arrow-right';
  }

  // Walk the sidebar <ul> in order, tracking the current section header so each
  // link carries its group (e.g. "Finance", "Results") for context + search.
  function buildIndex() {
    var out = [];
    var ul = document.querySelector('.sidebar-nav ul');
    if (ul) {
      var section = '';
      Array.prototype.forEach.call(ul.children, function (li) {
        if (li.classList && li.classList.contains('nav-section')) {
          section = (li.textContent || '').trim(); return;
        }
        var a = li.querySelector && li.querySelector('a.nav-link');
        if (!a) return;
        var span = a.querySelector('span');
        var label = ((span ? span.textContent : a.textContent) || '').trim().replace(/\s+/g, ' ');
        var href = a.getAttribute('href');
        if (!label || !href || href === '#') return;
        out.push({ label: label, href: href, section: section, icon: iconOf(a), kind: 'page' });
      });
    }
    // A couple of global commands for the "command" half of the palette.
    out.push({ label: 'Toggle dark / light theme', icon: 'fas fa-circle-half-stroke', kind: 'command', cmd: 'theme' });
    var logout = document.querySelector('.profile-menu a[href*="logout"], a[href$="/logout"]');
    if (logout) out.push({ label: 'Sign out', href: logout.getAttribute('href'), icon: 'fas fa-right-from-bracket', kind: 'command' });
    return out;
  }

  // Cheap fuzzy ranking: prefix > substring > subsequence.
  function score(q, text) {
    text = text.toLowerCase();
    if (!q) return 1;
    if (text.indexOf(q) === 0) return 1000;
    var idx = text.indexOf(q);
    if (idx > 0) return 600 - idx;
    var ti = 0, qi = 0, gaps = 0;
    for (; ti < text.length && qi < q.length; ti++) {
      if (text.charAt(ti) === q.charAt(qi)) qi++; else gaps++;
    }
    return qi === q.length ? (120 - Math.min(gaps, 119)) : -1;
  }

  function recents() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch (e) { return []; }
  }
  function pushRecent(href) {
    if (!href) return;
    try {
      var r = recents().filter(function (h) { return h !== href; });
      r.unshift(href);
      localStorage.setItem(RECENT_KEY, JSON.stringify(r.slice(0, 6)));
    } catch (e) { /* storage unavailable */ }
  }

  function applyFilter(raw) {
    var q = (raw || '').trim().toLowerCase();
    if (!q) {
      var rec = recents(), byHref = {};
      items.forEach(function (it) { if (it.href) byHref[it.href] = it; });
      var top = rec.map(function (h) { return byHref[h]; }).filter(Boolean);
      filtered = top.concat(items.filter(function (it) { return top.indexOf(it) < 0; }));
    } else {
      filtered = items.map(function (it) {
        return { it: it, s: Math.max(score(q, it.label), score(q, (it.section + ' ' + it.label)) - 60) };
      }).filter(function (x) { return x.s > -1; })
        .sort(function (a, b) { return b.s - a.s; })
        .map(function (x) { return x.it; });
    }
    active = 0;
    render();
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function render() {
    listEl.innerHTML = '';
    if (!filtered.length) { emptyEl.style.display = 'block'; return; }
    emptyEl.style.display = 'none';
    filtered.forEach(function (it, i) {
      var li = document.createElement('li');
      li.className = 'cmdk-item';
      li.setAttribute('role', 'option');
      li.id = 'cmdk-opt-' + i;
      li.innerHTML = '<i class="' + esc(it.icon) + '" aria-hidden="true"></i>'
        + '<span class="cmdk-label">' + esc(it.label) + '</span>'
        + '<span class="cmdk-sec">' + esc(it.kind === 'command' ? 'Command' : (it.section || 'Go to')) + '</span>';
      li.addEventListener('mousemove', function () { if (active !== i) { active = i; paintActive(); } });
      li.addEventListener('click', function () { choose(i); });
      listEl.appendChild(li);
    });
    paintActive();
  }

  function paintActive() {
    var kids = listEl.children;
    for (var i = 0; i < kids.length; i++) {
      var on = i === active;
      kids[i].classList.toggle('active', on);
      kids[i].setAttribute('aria-selected', on ? 'true' : 'false');
    }
    if (kids[active]) {
      kids[active].scrollIntoView({ block: 'nearest' });
      input.setAttribute('aria-activedescendant', kids[active].id);
    }
  }

  function choose(i) {
    var it = filtered[i];
    if (!it) return;
    if (it.cmd === 'theme') {
      var cur = document.documentElement.getAttribute('data-theme') || 'light';
      var next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
      close();
      return;
    }
    if (it.href) { pushRecent(it.href); close(); window.location.assign(it.href); }
  }

  function onKey(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, filtered.length - 1); paintActive(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); paintActive(); }
    else if (e.key === 'Enter') { e.preventDefault(); choose(active); }
    else if (e.key === 'Escape') { e.preventDefault(); close(); }
  }

  function buildUI() {
    overlay = document.createElement('div');
    overlay.className = 'cmdk-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Command palette');
    overlay.innerHTML =
      '<div class="cmdk-panel">'
      + '<div class="cmdk-search"><i class="fas fa-magnifying-glass" aria-hidden="true"></i>'
      + '<input type="text" class="cmdk-input" role="combobox" aria-expanded="true" aria-controls="cmdk-list" '
      + 'aria-autocomplete="list" placeholder="Search pages and actions…" autocomplete="off" aria-label="Search pages and actions" />'
      + '<kbd class="cmdk-esck">Esc</kbd></div>'
      + '<ul class="cmdk-list" id="cmdk-list" role="listbox" aria-label="Results"></ul>'
      + '<div class="cmdk-empty" role="status" style="display:none">No matches — try another word.</div>'
      + '<div class="cmdk-foot"><span><kbd>↑</kbd><kbd>↓</kbd> navigate</span><span><kbd>↵</kbd> open</span><span><kbd>esc</kbd> close</span></div>'
      + '</div>';
    document.body.appendChild(overlay);
    input = overlay.querySelector('.cmdk-input');
    listEl = overlay.querySelector('.cmdk-list');
    emptyEl = overlay.querySelector('.cmdk-empty');
    overlay.addEventListener('mousedown', function (e) { if (e.target === overlay) close(); });
    input.addEventListener('input', function () { applyFilter(input.value); });
    input.addEventListener('keydown', onKey);
  }

  function openPalette() {
    if (isOpen) return;
    if (!overlay) buildUI();
    items = buildIndex();
    lastFocus = document.activeElement;
    overlay.classList.add('show');
    document.body.classList.add('cmdk-lock');
    isOpen = true;
    input.value = '';
    applyFilter('');
    setTimeout(function () { input.focus(); }, 0);
  }

  function close() {
    if (!isOpen) return;
    overlay.classList.remove('show');
    document.body.classList.remove('cmdk-lock');
    isOpen = false;
    if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (e) {} }
  }

  document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      isOpen ? close() : openPalette();
    }
  });

  // Header hint chip + any element opting in via data-command-palette.
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-command-palette], .cmdk-hint');
    if (t) { e.preventDefault(); openPalette(); }
  });

  window.openCommandPalette = openPalette;
})();
