/* WAEC / NECO exam timetable — one-page sheet: layout, options and export.
 *
 * Layout: the days are split, in order, into 1-3 real column boxes (a
 * contiguous partition that keeps the longest column as short as possible),
 * then the largest text size that still fits the page is found by binary
 * search for each column count; the count that allows the biggest text wins
 * (fewer columns on a tie). Real boxes — not CSS columns — so html2canvas
 * captures exactly what is on screen.
 *
 * Export: PDF / PNG from an off-screen clone at natural size (no transform),
 * in the chosen paper size and orientation; Print uses @page with the same.
 */
(function () {
  'use strict';
  var PAPER = { a4: [794, 1123], letter: [816, 1056] };

  function px(el, name) { return parseFloat(getComputedStyle(el)[name]) || 0; }

  function Sheet(el) {
    this.el = el;
    this.body = el.querySelector('.xts-body');
    this.days = [].slice.call(el.querySelectorAll('.xts-day'));
    this.days.forEach(function (d, i) { d.classList.add('t' + (i % 4)); });
  }

  Sheet.prototype.place = function (n) {
    var body = this.body, days = this.days, gap;
    body.innerHTML = '';
    var cols = [];
    for (var i = 0; i < n; i++) { var c = document.createElement('div'); c.className = 'xts-col'; body.appendChild(c); cols.push(c); }
    this.el.setAttribute('data-cols', n);
    // measure every day at this column width
    days.forEach(function (d) { cols[0].appendChild(d); });
    gap = px(cols[0], 'rowGap');
    var h = days.map(function (d) { return d.getBoundingClientRect().height / scaleOf(d); });
    // contiguous partition minimising the tallest column
    var m = days.length, pre = [0];
    for (i = 0; i < m; i++) pre.push(pre[i] + h[i]);
    function cost(a, b) { return b > a ? pre[b] - pre[a] + gap * (b - a - 1) : 0; }
    var best = [], cut = [];
    for (var k = 0; k <= n; k++) { best.push([]); cut.push([]); for (var j = 0; j <= m; j++) { best[k].push(Infinity); cut[k].push(0); } }
    best[0][0] = 0;
    for (k = 1; k <= n; k++) for (j = 0; j <= m; j++) for (var s = 0; s <= j; s++) {
      var v = Math.max(best[k - 1][s], cost(s, j));
      if (v < best[k][j]) { best[k][j] = v; cut[k][j] = s; }
    }
    var ends = [], e = m;
    for (k = n; k >= 1; k--) { ends.unshift([cut[k][e], e]); e = cut[k][e]; }
    ends.forEach(function (r, ci) { for (var q = r[0]; q < r[1]; q++) cols[ci].appendChild(days[q]); });
    return best[n][m];
  };

  Sheet.prototype.fits = function () {
    var avail = this.body.getBoundingClientRect().height / scaleOf(this.body) + 0.5;
    var over = this.el.scrollHeight > this.el.clientHeight + 1;
    var tall = [].slice.call(this.body.children).some(function (c) { return c.scrollHeight > avail; });
    return !over && !tall;
  };

  Sheet.prototype.layout = function () {
    var el = this.el, land = el.getAttribute('data-orient') === 'landscape';
    var tries = land ? (this.days.length < 3 ? [1, 2] : [2, 3]) : (this.days.length < 4 ? [1] : [1, 2, 3]);
    var self = this, result = null;
    tries.forEach(function (n) {
      var lo = 6.5, hi = land ? 22 : 24, ok = null;
      for (var it = 0; it < 11; it++) {
        var mid = (lo + hi) / 2;
        el.style.setProperty('--fs', mid + 'px'); self.place(n);
        if (self.fits()) { ok = mid; lo = mid; } else { hi = mid; }
      }
      if (ok == null) ok = 6.5;
      if (!result || ok > result.fs * 1.04) result = { n: n, fs: ok };
    });
    el.style.setProperty('--fs', result.fs.toFixed(2) + 'px');
    this.place(result.n);
    // rounding can tip it over — step down until it really fits
    var f = result.fs;
    while (!this.fits() && f > 6) { f -= 0.25; el.style.setProperty('--fs', f + 'px'); this.place(result.n); }
    return { cols: result.n, fs: f };
  };

  function scaleOf(node) {
    var host = node.closest('[data-xts-scale]');
    if (!host) return 1;
    var m = /scale\(([\d.]+)/.exec(host.style.transform || '');
    return m ? parseFloat(m[1]) : 1;
  }

  /* ------------------------------------------------------------ controller */
  function Panel(root, cfg) {
    this.root = root; this.cfg = cfg || {};
    this.el = root.querySelector('.xts');
    this.sheet = new Sheet(this.el);
    this.scaleBox = root.querySelector('[data-xts-scale]');
    this.stage = root.querySelector('[data-xts-stage]');
    this.key = 'xtsExport';
    try { this.prefs = JSON.parse(localStorage.getItem(this.key) || '{}'); } catch (e) { this.prefs = {}; }
    this.bind();
  }
  Panel.prototype.save = function () { try { localStorage.setItem(this.key, JSON.stringify(this.prefs)); } catch (e) {} };
  Panel.prototype.bind = function () {
    var self = this, r = this.root, p = this.prefs;
    r.querySelectorAll('[data-xts-theme]').forEach(function (b) {
      b.addEventListener('click', function () { self.set('theme', b.getAttribute('data-xts-theme')); });
    });
    r.querySelectorAll('[data-xts-set]').forEach(function (b) {
      b.addEventListener('click', function () { self.set(b.getAttribute('data-xts-set'), b.getAttribute('data-v')); });
    });
    r.querySelectorAll('[data-xts-opt]').forEach(function (c) {
      var k = c.getAttribute('data-xts-opt');
      if (!c.disabled && typeof p[k] === 'boolean') c.checked = p[k];
      c.addEventListener('change', function () { p[k] = c.checked; self.save(); self.apply(); });
    });
    r.querySelectorAll('[data-xts-do]').forEach(function (b) {
      b.addEventListener('click', function () { self.run(b.getAttribute('data-xts-do'), b); });
    });
    window.addEventListener('resize', function () { self.fitStage(); });
    // The sheet's web fonts only start loading once it is shown (e.g. when the
    // modal opens), and text measured with a fallback font gives a wrong
    // layout — so lay out again whenever fonts finish loading.
    var again = null;
    function relayout() { clearTimeout(again); again = setTimeout(function () { if (self.el.offsetParent !== null || self.el.closest('[data-xts-panel]').offsetParent !== null) self.apply(); }, 60); }
    if (document.fonts) {
      if (document.fonts.ready) document.fonts.ready.then(relayout);
      if (document.fonts.addEventListener) document.fonts.addEventListener('loadingdone', relayout);
    }
    this.relayout = relayout;
    var img = this.el.querySelector('.xts-logo'); if (img && !img.complete) img.addEventListener('load', function () { self.apply(); });
    this.apply();
  };
  Panel.prototype.set = function (k, v) { this.prefs[k] = v; this.save(); this.apply(); };
  Panel.prototype.apply = function () {
    var p = this.prefs, el = this.el, r = this.root, d = this.cfg.defaults || {};
    var theme = this.cfg.theme || p.theme || d.theme || 'timeline';
    el.setAttribute('data-theme', theme);
    el.setAttribute('data-orient', p.orient || 'portrait');
    el.setAttribute('data-paper', p.paper || 'a4');
    r.querySelectorAll('[data-xts-theme]').forEach(function (b) {
      var on = b.getAttribute('data-xts-theme') === theme; b.classList.toggle('on', on); b.setAttribute('aria-checked', on);
    });
    r.querySelectorAll('[data-xts-set]').forEach(function (b) {
      var k = b.getAttribute('data-xts-set'), cur = p[k] || (k === 'orient' ? 'portrait' : 'a4');
      var on = b.getAttribute('data-v') === cur; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on);
    });
    r.querySelectorAll('[data-xts-opt]').forEach(function (c) { el.classList.toggle('no-' + c.getAttribute('data-xts-opt'), !c.checked || c.disabled); });
    this.cfg.theme = null;                       // a ?theme= only seeds the first paint
    this.fitStage(true);
    var res = this.sheet.layout();
    var note = r.querySelector('[data-xts-note]');
    if (note) note.textContent = (p.orient === 'landscape' ? 'Landscape' : 'Portrait') + ' · ' + (res.cols === 1 ? 'one column' : res.cols + ' columns') +
      (res.fs < 9 ? ' · small text — try landscape or hide some details' : '');
    this.fitStage();
  };
  Panel.prototype.fitStage = function (natural) {
    if (!this.scaleBox || !this.stage) return;
    var o = this.el.getAttribute('data-orient') === 'landscape', paper = PAPER[this.el.getAttribute('data-paper')] || PAPER.a4;
    var W = o ? paper[1] : paper[0], H = o ? paper[0] : paper[1];
    if (natural) { this.scaleBox.style.transform = 'none'; return; }
    var avail = this.stage.clientWidth - 24, maxH = this.stage.getAttribute('data-max-h');
    var k = Math.min(1, avail / W, maxH ? (parseFloat(maxH) / H) : 1);
    this.scaleBox.style.transform = 'scale(' + k + ')';
    this.scaleBox.style.width = W + 'px';
    this.scaleBox.style.height = H + 'px';
    this.scaleBox.parentNode.style.width = (W * k) + 'px';
    this.scaleBox.parentNode.style.height = (H * k) + 'px';
  };
  Panel.prototype.clone = function () {
    var host = document.createElement('div');
    host.style.cssText = 'position:fixed;left:-20000px;top:0;pointer-events:none';
    var c = this.el.cloneNode(true);
    host.appendChild(c); document.body.appendChild(host);
    return { host: host, el: c };
  };
  Panel.prototype.run = function (what, btn) {
    var self = this, name = (this.cfg.filename || 'exam_timetable');
    var land = this.el.getAttribute('data-orient') === 'landscape', paper = this.el.getAttribute('data-paper') || 'a4';
    if (what === 'print') {
      var css = document.getElementById('xts-page') || document.head.appendChild(Object.assign(document.createElement('style'), { id: 'xts-page' }));
      css.textContent = '@page{size:' + (paper === 'letter' ? 'letter' : 'A4') + ' ' + (land ? 'landscape' : 'portrait') + ';margin:0}' +
        '@media print{body>*:not(.xts-print-host){display:none!important}.xts-print-host{display:block!important;position:static!important;left:auto!important}}';
      var cl = this.clone(); cl.host.className = 'xts-print-host';
      setTimeout(function () { window.print(); cl.host.remove(); }, 50);
      return;
    }
    if (!window.html2canvas) { alert('The download tools are still loading — try again in a moment.'); return; }
    var label = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Preparing…';
    var cl2 = this.clone();
    var size = PAPER[paper] || PAPER.a4, W = land ? size[1] : size[0], H = land ? size[0] : size[1];
    window.html2canvas(cl2.el, { scale: 2.5, useCORS: true, backgroundColor: null, width: W, height: H, windowWidth: W + 40 })
      .then(function (canvas) {
        if (what === 'png') {
          var a = document.createElement('a'); a.href = canvas.toDataURL('image/png'); a.download = name + '.png'; a.click();
        } else {
          var JsPDF = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
          var pdf = new JsPDF({ orientation: land ? 'landscape' : 'portrait', unit: 'pt', format: paper === 'letter' ? 'letter' : 'a4' });
          pdf.addImage(canvas.toDataURL('image/jpeg', 0.94), 'JPEG', 0, 0, pdf.internal.pageSize.getWidth(), pdf.internal.pageSize.getHeight());
          pdf.save(name + '.pdf');
        }
      })
      .catch(function () { alert('Could not make the file — try Print instead.'); })
      .then(function () { cl2.host.remove(); btn.disabled = false; btn.innerHTML = label; });
  };

  window.XTSheet = { Panel: Panel, Sheet: Sheet };
})();
