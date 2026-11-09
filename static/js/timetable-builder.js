/*
 * Timetable designer: the parts that make it feel like an app.
 *   - a tap-to-fill grid builder for the day × period layouts (Saturday
 *     classes, holiday lessons): spreadsheet-style keys on a computer, and a
 *     day-by-day list with a bottom-sheet subject picker on a phone
 *   - "Saved timetables" drawer and a Save button in the header, with the
 *     current timetable's name and saved state
 *   - undo (Ctrl+Z / button) for every builder change
 *
 * It sits on top of timetable-designer.js, which still owns the data
 * (the global `rows`), the printable sheet, paste/quick-add and saving.
 * The builder only edits `rows` and calls renderEditor()/renderSheet().
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var B = $('ttBuilder'), RE = $('rowEditor');
  if (!B || !RE || typeof window.renderSheet !== 'function') return;

  var phone = window.matchMedia('(max-width: 759px)');
  var undoStack = [], sel = { d: 0, p: 0 }, phoneDay = 0, mode = null, M = { days: [], periods: [] }, IDX = {};
  var clip = null, editor = null;

  // ---------------------------------------------------------------- model
  function gridLayout() { return !isBlankGrid() && layout().mode === 'grid'; }
  function sat() { return el('layout').value === 'saturday'; }
  function wk(r) { var w = parseInt(r.week, 10); return w >= 1 ? w : 0; }
  function hasDay(r) { return !!(wk(r) || r.date || r.day); }
  function dayKey(r) {
    var g = (r.group || '').trim();
    return (sat() && wk(r) ? 'w' + wk(r) : 'd' + (r.date ? toISO(r.date) : canonDay(r.day || ''))) + '§' + g;
  }
  function sortVal(d) {
    if (sat() && wk(d)) return 'a' + ('0000' + wk(d)).slice(-4);
    if (d.date) return 'b' + toISO(d.date);
    return 'c' + ('0' + dayRank(canonDay(d.day))).slice(-2);
  }
  function build() {
    var days = [], dm = {}, periods = [], pm = {};
    IDX = {};
    rows.forEach(function (r, i) {
      if (r.time && !isAll(r.group)) {
        var k = periodKey(r);
        if (!pm[k]) { pm[k] = { k: k, time: r.time, dur: r.dur || '' }; periods.push(pm[k]); }
      }
      if (!hasDay(r)) return;
      var dk = dayKey(r);
      if (!dm[dk]) { dm[dk] = { k: dk, week: r.week, date: r.date, day: r.day, group: (r.group || '').trim(), order: i }; days.push(dm[dk]); }
      if (r.time) { var ck = dk + '|' + periodKey(r); if (!(ck in IDX)) IDX[ck] = i; }
    });
    periods.sort(function (a, b) { return a.time.localeCompare(b.time) || (+a.dur || 0) - (+b.dur || 0); });
    days.sort(function (a, b) { var x = sortVal(a), y = sortVal(b); return x < y ? -1 : x > y ? 1 : a.order - b.order; });
    M = { days: days, periods: periods };
    sel.d = Math.max(0, Math.min(sel.d, days.length - 1));
    sel.p = Math.max(0, Math.min(sel.p, periods.length - 1));
    phoneDay = Math.max(0, Math.min(phoneDay, days.length - 1));
  }
  function cellRow(d, p) { var i = IDX[d.k + '|' + p.k]; return i == null ? null : rows[i]; }
  function dayLabel(d) {
    if (sat() && wk(d)) return 'Week ' + wk(d);
    if (d.date) return dayFromDate(d.date) || fmtDate(d.date);
    return d.day || 'Day';
  }
  function daySub(d) {
    var bits = [];
    if (d.date) bits.push(sat() ? fmtDate(d.date) : fmtDate(d.date));
    if (d.group) bits.push(d.group);
    return bits.join(' · ');
  }
  function shortDay(d) {
    if (sat() && wk(d)) return 'Wk ' + wk(d);
    if (d.date) { var n = dayFromDate(d.date) || ''; return n.slice(0, 3) + ' ' + fmtDate(d.date).split('/').slice(0, 2).join('/'); }
    return (d.day || 'Day').slice(0, 3);
  }
  function plabel(p) { return periodLabel({ time: p.time, dur: p.dur }); }
  function newRowFor(d, p) {
    var r = blankRow();
    r.week = d.week || ''; r.date = d.date || ''; r.day = d.day || ''; r.group = d.group || '';
    r.time = p.time; r.dur = p.dur;
    rows.push(r); IDX[d.k + '|' + p.k] = rows.length - 1;
    return r;
  }
  function setCell(d, p, subject, teacher) {
    var r = cellRow(d, p) || newRowFor(d, p);
    r.subject = subject || ''; r.teacher = teacher || '';
  }
  function teacherFor(subject) {
    var s = (subject || '').trim().toLowerCase(); if (!s) return '';
    for (var i = rows.length - 1; i >= 0; i--) if ((rows[i].subject || '').trim().toLowerCase() === s && rows[i].teacher) return rows[i].teacher;
    return '';
  }
  function subjects() {
    var seen = {}, used = [], rest = [];
    rows.forEach(function (r) { var s = (r.subject || '').trim(); if (s && !seen[s.toLowerCase()]) { seen[s.toLowerCase()] = 1; used.push(s); } });
    document.querySelectorAll('#subjectList option').forEach(function (o) {
      var s = (o.value || '').trim(); if (s && !seen[s.toLowerCase()]) { seen[s.toLowerCase()] = 1; rest.push(s); }
    });
    ['Break', 'Lunch', 'Assembly', 'Free period'].forEach(function (s) { if (!seen[s.toLowerCase()]) { seen[s.toLowerCase()] = 1; rest.push(s); } });
    return { used: used, rest: rest };
  }
  function teachers() {
    var seen = {}, out = [];
    rows.forEach(function (r) { var t = (r.teacher || '').trim(); if (t && !seen[t]) { seen[t] = 1; out.push(t); } });
    return out;
  }
  function hue(s) { var h = 0; s = (s || '').toLowerCase(); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360; return h; }
  function breakish(s) { return /^(break|lunch|short break|long break|recess|free|free period|assembly)$/i.test((s || '').trim()); }
  function filled() {
    var n = 0, t = M.days.length * M.periods.length;
    M.days.forEach(function (d) { M.periods.forEach(function (p) { var r = cellRow(d, p); if (r && r.subject) n++; }); });
    return { n: n, t: t };
  }

  // ------------------------------------------------------------- changes
  function snap() { undoStack.push(JSON.stringify(rows)); if (undoStack.length > 60) undoStack.shift(); }
  function undo() {
    if (!undoStack.length) { toast('Nothing to undo'); return; }
    rows = JSON.parse(undoStack.pop());
    refresh(); toast('Undone');
  }
  function refresh() {
    window.renderEditor();             // the list view + this builder
    window.renderSheet();
    if (sat()) renderManageSaturdays();
  }
  function change(fn) { snap(); fn(); refresh(); }
  function nextTimeAfter(p) { return p ? addMinutes(p.time, p.dur || 40) : '08:00'; }
  function addPeriod(time, dur) {
    var p = { time: time || nextTimeAfter(M.periods[M.periods.length - 1]), dur: String(dur || (M.periods.length ? M.periods[M.periods.length - 1].dur : 40) || 40) };
    p.k = p.time + '|' + p.dur;
    M.days.forEach(function (d) { if (!cellRow(d, p)) newRowFor(d, p); });
    M.periods.push(p);
    return p;
  }
  function nextDayFrom(d) {
    var n = { week: '', date: '', day: '', group: d ? d.group : '' };
    if (sat()) { var max = 0; M.days.forEach(function (x) { max = Math.max(max, wk(x)); }); n.week = String(max + 1); return n; }
    var last = null; M.days.forEach(function (x) { if (x.date && (!last || toISO(x.date) > last)) last = toISO(x.date); });
    if (last) {
      var iso = addDaysISO(last, 1), guard = 0;
      while (guard++ < 7 && /Saturday|Sunday/.test(dayFromDate(iso) || '')) iso = addDaysISO(iso, 1);
      n.date = iso; n.day = dayFromDate(iso) || ''; return n;
    }
    var rank = -1; M.days.forEach(function (x) { rank = Math.max(rank, dayRank(canonDay(x.day))); });
    n.day = DAY_ORDER[Math.min(rank + 1, 6)] || 'Monday';
    return n;
  }
  function addDayLike(spec, groups) {
    (groups && groups.length ? groups : ['']).forEach(function (g) {
      var d = { week: spec.week, date: spec.date, day: spec.day, group: g };
      d.k = dayKey(d);
      M.periods.forEach(function (p) { if (!cellRow(d, p)) newRowFor(d, p); });
    });
  }
  function groupsOfBase(d) {
    var base = d.k.split('§')[0], gs = [];
    M.days.forEach(function (x) { if (x.k.split('§')[0] === base) gs.push(x.group); });
    return gs;
  }
  function addDay() {
    var last = M.days[M.days.length - 1];
    change(function () { addDayLike(nextDayFrom(last), last ? groupsOfBase(last) : ['']); });
    build();
    phoneDay = M.days.length - 1; sel.d = M.days.length - 1; sel.p = 0;
    if (M.days.length) render(); focusSel();
  }
  function removeWhere(fn) { rows = rows.filter(function (r) { return !fn(r); }); }
  function inDay(d) { return function (r) { return hasDay(r) && dayKey(r) === d.k; }; }
  function inPeriod(p) { return function (r) { return r.time && periodKey(r) === p.k; }; }

  // --------------------------------------------------------------- render
  function render() {
    var on = gridLayout();
    $('tdModeBuild').hidden = !on;
    if (!on) { if (mode === 'build' || !mode) setMode('list', true); B.innerHTML = ''; return; }
    if (!mode) setMode('build', true);
    if (mode !== 'build') return;
    build();
    closeEditor(true);
    if (!M.days.length || !M.periods.length) { B.innerHTML = wizardHTML(); wireWizard(); return; }
    B.innerHTML = toolbarHTML() + (phone.matches ? phoneHTML() : deskHTML());
    $('tbTeachers') && ($('tbTeachers').innerHTML = teachers().map(function (t) { return '<option value="' + esc(t) + '">'; }).join(''));
    if (!phone.matches) markSel();
  }
  function toolbarHTML() {
    var f = filled(), pct = f.t ? Math.round(f.n / f.t * 100) : 0;
    return '<div class="tb-bar">'
      + '<div class="tb-prog"><b>' + f.n + '</b> of ' + f.t + ' lessons filled<span class="rs-meter ' + (pct >= 100 ? 'good' : 'n') + '"><i style="width:' + pct + '%"></i></span></div>'
      + '<div class="tb-bar-a">'
      + '<button type="button" class="rs-icon-btn" data-tb="undo" title="Undo (Ctrl+Z)" aria-label="Undo"' + (undoStack.length ? '' : ' disabled') + '><i class="fas fa-rotate-left" aria-hidden="true"></i></button>'
      + (phone.matches ? '' : '<button type="button" class="rs-icon-btn" data-tb="wide" title="' + ($('tdWrap').classList.contains('td-wide') ? 'Show the preview' : 'Wider grid (hide the preview)') + '" aria-label="Toggle wide grid"><i class="fas ' + ($('tdWrap').classList.contains('td-wide') ? 'fa-compress' : 'fa-expand') + '" aria-hidden="true"></i></button>')
      + '<button type="button" class="rs-icon-btn" data-tb="restart" title="Start a new grid" aria-label="Start a new grid"><i class="fas fa-table-cells" aria-hidden="true"></i></button>'
      + '</div></div>';
  }
  function cellHTML(r) {
    if (!r || !r.subject) return '<span class="tb-empty">+</span>';
    return '<b>' + esc(r.subject) + '</b>' + (r.teacher ? '<small>' + esc(r.teacher) + '</small>' : '');
  }
  function cellStyle(r) {
    if (!r || !r.subject) return '';
    return ' style="--h:' + hue(r.subject) + '"';
  }
  function deskHTML() {
    var dayWord = sat() ? 'week' : 'day';
    var h = '<div class="tb-scroll"><table class="tb-grid" role="grid" aria-label="Timetable grid"><thead><tr><th class="tb-corner">' + (sat() ? 'Week' : 'Day') + '</th>';
    M.periods.forEach(function (p, pi) {
      h += '<th><button type="button" class="tb-ph" data-tb="period" data-p="' + pi + '" title="Change the time or length"><b>' + esc(plabel(p)) + '</b><small>' + esc(p.dur || '?') + ' min</small></button></th>';
    });
    h += '<th class="tb-addc"><button type="button" class="tb-add" data-tb="addperiod" title="Add a period"><i class="fas fa-plus" aria-hidden="true"></i></button></th></tr></thead><tbody>';
    M.days.forEach(function (d, di) {
      h += '<tr><th class="tb-dh"><button type="button" class="tb-dbtn" data-tb="day" data-d="' + di + '" title="Copy, rename or remove"><b>' + esc(dayLabel(d)) + '</b><small>' + esc(daySub(d)) + '</small></button></th>';
      M.periods.forEach(function (p, pi) {
        var r = cellRow(d, p);
        h += '<td><button type="button" class="tb-cell' + (r && r.subject ? ' on' : '') + (r && breakish(r.subject) ? ' brk' : '') + '" data-d="' + di + '" data-p="' + pi + '" tabindex="-1"' + cellStyle(r) + '>' + cellHTML(r) + '</button></td>';
      });
      h += '<td></td></tr>';
    });
    h += '<tr><th class="tb-dh"><button type="button" class="tb-add wide" data-tb="addday"><i class="fas fa-plus" aria-hidden="true"></i> Add ' + dayWord + '</button></th><td colspan="' + (M.periods.length + 1) + '"></td></tr>';
    h += '</tbody></table></div>';
    h += '<div class="tb-keys"><span><kbd>Enter</kbd> or type to fill</span><span><kbd>Tab</kbd>/<kbd>←↑→↓</kbd> move</span><span><kbd>Del</kbd> clear</span><span><kbd>Ctrl</kbd>+<kbd>C</kbd>/<kbd>V</kbd> copy, paste from Excel</span><span><kbd>Ctrl</kbd>+<kbd>D</kbd> same as above</span><span><kbd>Ctrl</kbd>+<kbd>Z</kbd> undo</span></div>';
    h += paletteHTML('Click a subject to put it in the selected box');
    return h;
  }
  function paletteHTML(title) {
    var s = subjects();
    function chip(x) { return '<button type="button" class="tb-chip" data-tb="pick" data-s="' + esc(x) + '" style="--h:' + hue(x) + '">' + esc(x) + '</button>'; }
    return '<div class="tb-pal"><div class="tb-pal-h">' + title + '</div>'
      + (s.used.length ? '<div class="tb-chips">' + s.used.map(chip).join('') + '</div>' : '')
      + (s.rest.length ? '<div class="tb-chips more">' + s.rest.map(chip).join('') + '</div>' : '') + '</div>';
  }
  function phoneHTML() {
    var d = M.days[phoneDay], dayWord = sat() ? 'week' : 'day';
    var h = '<div class="tb-days" role="tablist" aria-label="' + (sat() ? 'Weeks' : 'Days') + '">';
    M.days.forEach(function (x, di) {
      var full = M.periods.every(function (p) { var r = cellRow(x, p); return r && r.subject; });
      h += '<button type="button" role="tab" class="tb-dchip' + (di === phoneDay ? ' on' : '') + (full ? ' done' : '') + '" data-tb="pday" data-d="' + di + '" aria-selected="' + (di === phoneDay) + '"><b>' + esc(shortDay(x)) + '</b>' + (x.group ? '<small>' + esc(x.group) + '</small>' : '') + (full ? '<i class="fas fa-check" aria-hidden="true"></i>' : '') + '</button>';
    });
    h += '<button type="button" class="tb-dchip add" data-tb="addday" aria-label="Add a ' + dayWord + '"><i class="fas fa-plus" aria-hidden="true"></i></button></div>';
    h += '<div class="tb-dayhd"><div><b>' + esc(dayLabel(d)) + '</b><small>' + esc(daySub(d) || (M.periods.length + ' periods')) + '</small></div>'
      + '<button type="button" class="rs-btn ghost sm" data-tb="copy" data-d="' + phoneDay + '"><i class="fas fa-clone" aria-hidden="true"></i> Copy to…</button>'
      + '<button type="button" class="rs-icon-btn" data-tb="day" data-d="' + phoneDay + '" aria-label="More for this ' + dayWord + '"><i class="fas fa-ellipsis" aria-hidden="true"></i></button></div>';
    h += '<div class="tb-plist">';
    M.periods.forEach(function (p, pi) {
      var r = cellRow(d, p), on = r && r.subject;
      h += '<div class="tb-prow' + (on ? ' on' : '') + (on && breakish(r.subject) ? ' brk' : '') + '"' + cellStyle(r) + '>'
        + '<button type="button" class="tb-pt" data-tb="period" data-p="' + pi + '" aria-label="Change time of period ' + (pi + 1) + '"><b>' + esc(fmtT(p.time)) + '</b><small>' + esc(p.dur || '?') + 'm</small></button>'
        + '<button type="button" class="tb-ps" data-tb="pcell" data-p="' + pi + '">'
        + (on ? '<b>' + esc(r.subject) + '</b>' + (r.teacher ? '<small>' + esc(r.teacher) + '</small>' : '') : '<span class="tb-ph-t">Tap to choose a subject</span>')
        + '</button><i class="fas fa-chevron-right" aria-hidden="true"></i></div>';
    });
    h += '<button type="button" class="tb-addrow" data-tb="addperiod"><i class="fas fa-plus" aria-hidden="true"></i> Add a period <small>starts ' + esc(fmtT(nextTimeAfter(M.periods[M.periods.length - 1]))) + '</small></button></div>';
    return h;
  }

  // --------------------------------------------------------------- wizard
  function nextMonday() {
    var d = new Date(); d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7));
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function nextSaturday() {
    var d = new Date(); d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7 || 7));
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function wizardHTML() {
    var s = sat();
    function lens(name, val, opts) {
      return '<div class="tb-lens" role="group">' + opts.map(function (o) { return '<button type="button" data-lens="' + name + '" data-v="' + o + '" class="' + (String(o) === String(val) ? 'on' : '') + '">' + o + '</button>'; }).join('') + '</div>';
    }
    return '<div class="tb-wiz"><div class="tb-wiz-h"><span class="tb-wiz-ic"><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i></span><div><b>Set up the grid in one go</b><small>Answer four quick questions — then just tap each box to pick a subject.</small></div></div>'
      + '<div class="tb-wiz-g">'
      + (s
        ? '<label class="td-f"><span>First Saturday</span><input type="date" id="tbwFirst" value="' + esc(saturdayPlan.first || nextSaturday()) + '"></label>'
          + '<label class="td-f"><span>How many weeks?</span><input type="number" id="tbwDays" min="1" max="40" value="8" inputmode="numeric"></label>'
        : '<label class="td-f"><span>First day</span><input type="date" id="tbwFirst" value="' + nextMonday() + '"></label>'
          + '<label class="td-f"><span>How many days?</span><input type="number" id="tbwDays" min="1" max="60" value="5" inputmode="numeric"></label>'
          + '<label class="rs-check tb-wiz-full"><input type="checkbox" id="tbwSkip" checked> Skip Saturdays and Sundays</label>')
      + '<label class="td-f"><span>First lesson starts</span><input type="time" id="tbwStart" value="08:00"></label>'
      + '<label class="td-f"><span>Periods each ' + (s ? 'Saturday' : 'day') + '</span><input type="number" id="tbwN" min="1" max="14" value="' + (s ? 4 : 6) + '" inputmode="numeric"></label>'
      + '<div class="td-f tb-wiz-full"><span>Each period lasts (minutes)</span>' + lens('dur', s ? 60 : 40, [30, 35, 40, 45, 60, 80, 90]) + '</div>'
      + '<div class="td-f tb-wiz-full"><span>Break <em>(optional)</em></span><div class="tb-wiz-brk">after period <select id="tbwBrk"><option value="0">no break</option>' + [1, 2, 3, 4, 5, 6].map(function (n) { return '<option value="' + n + '"' + (n === 2 && s ? ' selected' : n === 3 && !s ? ' selected' : '') + '>' + n + '</option>'; }).join('') + '</select> for ' + lens('brk', s ? 30 : 20, [10, 15, 20, 30, 40]) + ' min</div></div>'
      + '<label class="td-f tb-wiz-full"><span>Classes / streams <em>(optional — only if they differ, e.g. Science, Arts)</em></span><input id="tbwGroups" placeholder="Leave blank if everyone has the same timetable"></label>'
      + '</div><button type="button" class="rs-btn primary tb-wiz-go" data-tb="wizgo"><i class="fas fa-table-cells" aria-hidden="true"></i> Create the grid</button>'
      + '<p class="tb-wiz-or">Already have it in Excel, WhatsApp or a photo? <button type="button" class="tb-link" data-td-mode="paste">Paste it instead</button></p></div>';
  }
  function wireWizard() {
    B.querySelectorAll('[data-lens]').forEach(function (b) {
      b.addEventListener('click', function () {
        B.querySelectorAll('[data-lens="' + b.dataset.lens + '"]').forEach(function (x) { x.classList.toggle('on', x === b); });
      });
    });
  }
  function lensVal(name, dflt) { var b = B.querySelector('[data-lens="' + name + '"].on'); return b ? b.dataset.v : dflt; }
  function wizardGo() {
    var first = $('tbwFirst').value, n = Math.max(1, Math.min(60, parseInt($('tbwDays').value, 10) || 1));
    var start = normTime($('tbwStart').value || '08:00') || '08:00', np = Math.max(1, Math.min(14, parseInt($('tbwN').value, 10) || 1));
    var dur = lensVal('dur', '40'), brkAfter = parseInt($('tbwBrk').value, 10) || 0, brkLen = lensVal('brk', '20');
    var groups = ($('tbwGroups').value || '').split(/[,;\n]/).map(function (g) { return g.trim(); }).filter(Boolean);
    if (!groups.length) groups = [''];
    snap();
    // drop the untouched starter rows, keep anything typed
    rows = rows.filter(function (r) { return r.subject || r.time; });
    if (sat() && first) { saturdayPlan.first = first; el('satFirst').value = first; }
    var days = [];
    if (sat()) { for (var w = 1; w <= n; w++) days.push({ week: String(w), date: '', day: '' }); }
    else {
      var iso = first || nextMonday(), guard = 0;
      while (days.length < n && guard++ < 400) {
        var dn = dayFromDate(iso) || '';
        if (!($('tbwSkip').checked && /Saturday|Sunday/.test(dn))) days.push({ week: '', date: iso, day: dn });
        iso = addDaysISO(iso, 1);
      }
    }
    var periods = [], t = start;
    for (var i = 1; i <= np; i++) {
      periods.push({ time: t, dur: dur, brk: false }); t = addMinutes(t, dur);
      if (i === brkAfter && i < np) { periods.push({ time: t, dur: brkLen, brk: true }); t = addMinutes(t, brkLen); }
    }
    days.forEach(function (d) {
      groups.forEach(function (g) {
        periods.forEach(function (p) {
          var r = blankRow(); r.week = d.week; r.date = d.date; r.day = d.day; r.group = g; r.time = p.time; r.dur = p.dur;
          if (p.brk) r.subject = 'Break';
          rows.push(r);
        });
      });
    });
    sel = { d: 0, p: 0 }; phoneDay = 0;
    refresh();
    toast('Grid ready — ' + (phone.matches ? 'tap a period to choose its subject' : 'click a box or just start typing'));
    focusSel();
    if (phone.matches) setTimeout(function () { openPicker(0, 0); }, 250);
  }

  // ------------------------------------------------------------- desktop
  function cellBtn(di, pi) { return B.querySelector('.tb-cell[data-d="' + di + '"][data-p="' + pi + '"]'); }
  function markSel() {
    B.querySelectorAll('.tb-cell.sel').forEach(function (c) { c.classList.remove('sel'); c.tabIndex = -1; });
    var c = cellBtn(sel.d, sel.p); if (c) { c.classList.add('sel'); c.tabIndex = 0; }
  }
  function focusSel() {
    if (phone.matches) return;
    markSel(); var c = cellBtn(sel.d, sel.p);
    if (c) { c.focus({ preventScroll: true }); c.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
  }
  function move(dd, dp, wrap) {
    var nd = sel.d + dd, np = sel.p + dp;
    if (wrap) {
      if (np >= M.periods.length) { np = 0; nd++; }
      if (np < 0) { np = M.periods.length - 1; nd--; }
    }
    if (nd < 0 || nd >= M.days.length || np < 0 || np >= M.periods.length) return false;
    sel.d = nd; sel.p = np; focusSel(); return true;
  }
  function updateCell(di, pi) {
    var c = cellBtn(di, pi); if (!c) return;
    var r = cellRow(M.days[di], M.periods[pi]);
    c.className = 'tb-cell' + (r && r.subject ? ' on' : '') + (r && breakish(r.subject) ? ' brk' : '') + (di === sel.d && pi === sel.p ? ' sel' : '');
    if (r && r.subject) c.style.setProperty('--h', hue(r.subject)); else c.style.removeProperty('--h');
    c.innerHTML = cellHTML(r);
  }
  // A light change (one cell) re-renders only that cell + the sheet: keeps focus snappy.
  function commitCell(di, pi, subject, teacher) {
    var d = M.days[di], p = M.periods[pi]; if (!d || !p) return;
    var r = cellRow(d, p);
    if ((r ? r.subject : '') === subject && (r ? r.teacher : '') === teacher) return;
    snap(); setCell(d, p, subject, teacher);
    window.renderSheet();
    $('rowBody') && (window.__tbQuiet = 1, window.renderEditor(), window.__tbQuiet = 0);
    if (phone.matches) return;
    updateCell(di, pi); refreshBar();
  }
  function refreshBar() {
    var bar = B.querySelector('.tb-bar'); if (!bar) return;
    var tmp = document.createElement('div'); tmp.innerHTML = toolbarHTML();
    bar.replaceWith(tmp.firstChild);
  }
  function openEditor(initial) {
    closeEditor();
    var c = cellBtn(sel.d, sel.p); if (!c) return;
    var r = cellRow(M.days[sel.d], M.periods[sel.p]);
    var ed = document.createElement('div');
    ed.className = 'tb-ed';
    ed.innerHTML = '<input class="tb-ed-s" list="subjectList" placeholder="Subject" aria-label="Subject" autocomplete="off">'
      + '<input class="tb-ed-t" list="tbTeachers" placeholder="Teacher (optional)" aria-label="Teacher" autocomplete="off">'
      + '<small><kbd>Enter</kbd> save &amp; next · <kbd>Tab</kbd> teacher · <kbd>Esc</kbd> cancel</small>';
    B.appendChild(ed);
    var s = ed.querySelector('.tb-ed-s'), t = ed.querySelector('.tb-ed-t'), autoT = !(r && r.teacher);
    s.value = initial != null ? initial : (r ? r.subject : '');
    t.value = r ? r.teacher : '';
    var br = B.getBoundingClientRect(), cr = c.getBoundingClientRect();
    var w = Math.max(cr.width, 230), left = Math.min(cr.left - br.left, B.clientWidth - w - 4);
    ed.style.left = Math.max(0, left) + 'px'; ed.style.top = (cr.top - br.top) + 'px'; ed.style.width = w + 'px';
    editor = { el: ed, di: sel.d, pi: sel.p, s: s, t: t };
    s.addEventListener('input', function () { if (autoT) t.value = teacherFor(s.value); });
    t.addEventListener('input', function () { autoT = false; });
    ed.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); saveEditor(); move(0, 1, true); }
      else if (e.key === 'Escape') { e.preventDefault(); closeEditor(); focusSel(); }
      else if (e.key === 'Tab' && !e.shiftKey && e.target === t) { e.preventDefault(); saveEditor(); move(0, 1, true); }
      else if (e.key === 'Tab' && e.shiftKey && e.target === s) { e.preventDefault(); saveEditor(); move(0, -1, true); }
    });
    ed.addEventListener('focusout', function (e) {
      if (!editor || editor.el !== ed) return;
      if (e.relatedTarget && ed.contains(e.relatedTarget)) return;
      setTimeout(function () { if (editor && editor.el === ed && !ed.contains(document.activeElement)) saveEditor(); }, 0);
    });
    s.focus();
    if (initial != null) { var n = s.value.length; s.setSelectionRange(n, n); if (autoT) t.value = teacherFor(s.value); }
    else s.select();
  }
  function saveEditor() {
    if (!editor) return;
    var e = editor; editor = null;
    commitCell(e.di, e.pi, e.s.value.trim(), e.t.value.trim());
    e.el.remove();
  }
  function closeEditor(silent) { if (editor) { editor.el.remove(); editor = null; } }
  function pasteBlock(text) {
    var lines = text.replace(/\r/g, '').split('\n'); while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
    if (!lines.length) return;
    var grid = lines.map(function (l) { return l.indexOf('\t') >= 0 ? l.split('\t') : [l]; });
    change(function () {
      grid.forEach(function (cells, ri) {
        while (sel.d + ri >= M.days.length) { addDayLike(nextDayFrom(M.days[M.days.length - 1]), ['']); build(); }
        cells.forEach(function (v, ci) {
          while (sel.p + ci >= M.periods.length) addPeriod();
          var sc = parseSubjectCell(v || '');
          setCell(M.days[sel.d + ri], M.periods[sel.p + ci], sc.subject, sc.teacher || (sc.subject ? teacherFor(sc.subject) : ''));
        });
      });
    });
    toast('Pasted ' + grid.length + ' × ' + Math.max.apply(null, grid.map(function (g) { return g.length; })) + ' boxes');
    focusSel();
  }

  B.addEventListener('keydown', function (e) {
    var c = e.target.closest && e.target.closest('.tb-cell'); if (!c || phone.matches) return;
    sel.d = +c.dataset.d; sel.p = +c.dataset.p;
    var k = e.key, mod = e.ctrlKey || e.metaKey;
    if (k === 'ArrowRight') { e.preventDefault(); move(0, 1); }
    else if (k === 'ArrowLeft') { e.preventDefault(); move(0, -1); }
    else if (k === 'ArrowDown') { e.preventDefault(); move(1, 0); }
    else if (k === 'ArrowUp') { e.preventDefault(); move(-1, 0); }
    else if (k === 'Tab') { if (move(0, e.shiftKey ? -1 : 1, true)) e.preventDefault(); }
    else if (k === 'Enter' || k === 'F2' || k === ' ') { e.preventDefault(); openEditor(); }
    else if (k === 'Delete' || k === 'Backspace') { e.preventDefault(); commitCell(sel.d, sel.p, '', ''); }
    else if (mod && (k === 'c' || k === 'C')) {
      var r = cellRow(M.days[sel.d], M.periods[sel.p]);
      clip = r ? { s: r.subject, t: r.teacher } : { s: '', t: '' };
      try { navigator.clipboard && navigator.clipboard.writeText(clip.s + (clip.t ? ' (' + clip.t + ')' : '')); } catch (x) {}
      e.preventDefault(); toast('Copied');
    }
    else if (mod && (k === 'd' || k === 'D')) {
      e.preventDefault(); if (sel.d < 1) return;
      var up = cellRow(M.days[sel.d - 1], M.periods[sel.p]);
      commitCell(sel.d, sel.p, up ? up.subject : '', up ? up.teacher : '');
    }
    else if (k.length === 1 && !mod && !e.altKey) { e.preventDefault(); openEditor(k); }
  });
  document.addEventListener('paste', function (e) {
    var c = document.activeElement && document.activeElement.closest && document.activeElement.closest('#ttBuilder .tb-cell');
    if (!c) return;
    var text = (e.clipboardData || window.clipboardData).getData('text');
    e.preventDefault();
    if (text && (text.indexOf('\t') >= 0 || text.indexOf('\n') >= 0)) pasteBlock(text);
    else if (text) { var sc = parseSubjectCell(text); commitCell(sel.d, sel.p, sc.subject, sc.teacher || teacherFor(sc.subject)); }
    else if (clip) commitCell(sel.d, sel.p, clip.s, clip.t);
  });
  B.addEventListener('dblclick', function (e) { if (e.target.closest('.tb-cell')) openEditor(); });

  // --------------------------------------------------------------- sheets
  var sheetBg = null;
  function openSheet(title, body, foot, cls) {
    closeSheet();
    sheetBg = document.createElement('div');
    sheetBg.className = 'tb-ov no-print';
    sheetBg.innerHTML = '<div class="tb-sheet ' + (cls || '') + '" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">'
      + '<div class="tb-grab" aria-hidden="true"></div>'
      + '<div class="tb-sheet-h"><h3>' + title + '</h3><button type="button" class="rs-icon-btn" data-sheet-x aria-label="Close"><i class="fas fa-xmark" aria-hidden="true"></i></button></div>'
      + '<div class="tb-sheet-b">' + body + '</div>' + (foot ? '<div class="tb-sheet-f">' + foot + '</div>' : '') + '</div>';
    document.body.appendChild(sheetBg);
    document.body.classList.add('tb-lock');
    sheetBg.addEventListener('click', function (e) { if (e.target === sheetBg || e.target.closest('[data-sheet-x]')) closeSheet(); });
    requestAnimationFrame(function () { sheetBg && sheetBg.classList.add('on'); });
    return sheetBg.querySelector('.tb-sheet');
  }
  function closeSheet() {
    if (!sheetBg) return;
    var bg = sheetBg; sheetBg = null;
    var home = $('tdHome');
    bg.querySelectorAll('[data-home]').forEach(function (n) { home.appendChild(n); });
    bg.remove(); document.body.classList.remove('tb-lock');
    if (picker) picker = null;
  }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && sheetBg) { e.preventDefault(); closeSheet(); focusSel(); } });

  // Phone subject picker
  var picker = null;
  function openPicker(di, pi) {
    build();
    if (!M.days[di] || !M.periods[pi]) return;
    var sh = openSheet('Choose a subject', '', '<button type="button" class="rs-btn ghost" data-pk="clear"><i class="fas fa-eraser" aria-hidden="true"></i> Clear</button><button type="button" class="rs-btn primary" data-pk="done">Done</button>', 'tb-pk');
    picker = { di: di, pi: pi, sh: sh, tEdited: false };
    paintPicker();
    sh.addEventListener('click', function (e) {
      var b = e.target.closest('[data-pk]'); if (!b) return;
      var a = b.dataset.pk;
      if (a === 'pick') pickerPick(b.dataset.s);
      else if (a === 'use') pickerPick(sh.querySelector('.tb-pk-q').value.trim());
      else if (a === 'prev') pickerGo(-1);
      else if (a === 'next') pickerGo(1);
      else if (a === 'clear') { commitCell(picker.di, picker.pi, '', ''); renderPhoneOnly(); paintPicker(); }
      else if (a === 'done') { pickerSaveTeacher(); closeSheet(); render(); }
    });
  }
  function pickerSaveTeacher() {
    if (!picker) return;
    var t = picker.sh.querySelector('.tb-pk-t'); if (!t || !picker.tEdited) return;
    var r = cellRow(M.days[picker.di], M.periods[picker.pi]);
    if (r && r.subject && r.teacher !== t.value.trim()) commitCell(picker.di, picker.pi, r.subject, t.value.trim());
  }
  function paintPicker() {
    var d = M.days[picker.di], p = M.periods[picker.pi], r = cellRow(d, p), s = subjects(), cur = r ? r.subject : '';
    function chip(x) { return '<button type="button" class="tb-chip' + (x === cur ? ' on' : '') + '" data-pk="pick" data-s="' + esc(x) + '" style="--h:' + hue(x) + '">' + esc(x) + '</button>'; }
    var b = picker.sh.querySelector('.tb-sheet-b');
    b.innerHTML = '<div class="tb-pk-h"><button type="button" class="rs-icon-btn" data-pk="prev" aria-label="Previous period"><i class="fas fa-chevron-left" aria-hidden="true"></i></button>'
      + '<div><b>' + esc(dayLabel(d)) + (d.group ? ' · ' + esc(d.group) : '') + '</b><small>' + esc(plabel(p)) + ' · period ' + (picker.pi + 1) + ' of ' + M.periods.length + '</small></div>'
      + '<button type="button" class="rs-icon-btn" data-pk="next" aria-label="Next period"><i class="fas fa-chevron-right" aria-hidden="true"></i></button></div>'
      + '<label class="rs-search tb-pk-s"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><input type="search" class="tb-pk-q" placeholder="Search or type a new subject" autocomplete="off" enterkeyhint="done"></label>'
      + '<div class="tb-pk-use" hidden></div>'
      + (s.used.length ? '<div class="tb-pk-l">In this timetable</div><div class="tb-chips">' + s.used.map(chip).join('') + '</div>' : '')
      + '<div class="tb-pk-l">' + (s.used.length ? 'More subjects' : 'Subjects') + '</div><div class="tb-chips more">' + s.rest.map(chip).join('') + '</div>'
      + '<label class="td-f tb-pk-tw"><span>Teacher <em>(optional — remembered for next time)</em></span><input class="tb-pk-t" list="tbTeachers" placeholder="e.g. Mr Bello" value="' + esc(r ? r.teacher : '') + '" autocomplete="off"></label>';
    var q = b.querySelector('.tb-pk-q'), use = b.querySelector('.tb-pk-use'), t = b.querySelector('.tb-pk-t');
    q.addEventListener('input', function () {
      var v = q.value.trim().toLowerCase(), exact = false;
      b.querySelectorAll('.tb-chip').forEach(function (c) {
        var m = !v || c.dataset.s.toLowerCase().indexOf(v) >= 0; c.hidden = !m;
        if (c.dataset.s.toLowerCase() === v) exact = true;
      });
      use.hidden = !v || exact;
      use.innerHTML = v ? '<button type="button" class="tb-chip new" data-pk="use"><i class="fas fa-plus" aria-hidden="true"></i> Use “' + esc(q.value.trim()) + '”</button>' : '';
    });
    q.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return; e.preventDefault();
      var first = b.querySelector('.tb-chip:not([hidden])');
      var v = q.value.trim(); if (!v) return;
      pickerPick(first && first.dataset.s && first.dataset.s.toLowerCase().indexOf(v.toLowerCase()) === 0 ? first.dataset.s : v);
    });
    t.addEventListener('input', function () { picker.tEdited = true; });
    t.addEventListener('change', pickerSaveTeacher);
  }
  function pickerPick(subject) {
    if (!subject || !picker) return;
    var t = picker.sh.querySelector('.tb-pk-t');
    var teacher = picker.tEdited ? t.value.trim() : teacherFor(subject);
    commitCell(picker.di, picker.pi, subject, teacher);
    renderPhoneOnly();
    // auto-advance: next period, then the next day's first period
    if (!pickerGo(1, true)) { closeSheet(); render(); toast('All done — check the preview'); }
  }
  function pickerGo(step, quietEnd) {
    pickerSaveTeacher();
    var di = picker.di, pi = picker.pi + step;
    if (pi >= M.periods.length) { pi = 0; di++; }
    if (pi < 0) { pi = M.periods.length - 1; di--; }
    if (di < 0) return false;
    if (di >= M.days.length) return false;
    if (di !== picker.di) { phoneDay = di; renderPhoneOnly(); if (quietEnd) toast(dayLabel(M.days[picker.di]) + ' done ✓'); }
    picker.di = di; picker.pi = pi; picker.tEdited = false;
    paintPicker();
    return true;
  }
  function renderPhoneOnly() {
    if (!phone.matches || mode !== 'build') return;
    var keep = sheetBg; build();
    B.innerHTML = toolbarHTML() + phoneHTML();
    sheetBg = keep;
  }

  // Period sheet
  function openPeriod(pi) {
    var p = M.periods[pi]; if (!p) return;
    var lens = [30, 35, 40, 45, 60, 80, 90];
    var sh = openSheet('Period ' + (pi + 1) + ' · ' + esc(plabel(p)),
      '<div class="tb-two"><label class="td-f"><span>Starts</span><input type="time" class="tbp-t" value="' + esc(p.time) + '"></label>'
      + '<label class="td-f"><span>Minutes</span><input type="number" class="tbp-d" min="5" step="5" inputmode="numeric" value="' + esc(p.dur) + '"></label></div>'
      + '<div class="tb-lens">' + lens.map(function (n) { return '<button type="button" data-v="' + n + '" class="' + (String(n) === String(p.dur) ? 'on' : '') + '">' + n + '</button>'; }).join('') + '</div>'
      + (pi < M.periods.length - 1 ? '<label class="rs-check"><input type="checkbox" class="tbp-shift" checked> Move the later periods too, so nothing overlaps</label>' : '')
      + '<button type="button" class="rs-btn ghost tbp-brk"><i class="fas fa-mug-hot" aria-hidden="true"></i> Make this period a break for every ' + (sat() ? 'week' : 'day') + '</button>',
      '<button type="button" class="rs-btn danger tbp-del"><i class="fas fa-trash" aria-hidden="true"></i> Remove</button><button type="button" class="rs-btn primary tbp-ok">Save</button>');
    var t = sh.querySelector('.tbp-t'), d = sh.querySelector('.tbp-d');
    sh.querySelectorAll('.tb-lens button').forEach(function (b) {
      b.addEventListener('click', function () { d.value = b.dataset.v; sh.querySelectorAll('.tb-lens button').forEach(function (x) { x.classList.toggle('on', x === b); }); });
    });
    sh.querySelector('.tbp-del').addEventListener('click', function () {
      var n = rows.filter(function (r) { return r.subject && inPeriod(p)(r); }).length;
      if (n && !confirm('Remove this period and its ' + n + ' lesson' + (n > 1 ? 's' : '') + '?')) return;
      closeSheet(); change(function () { removeWhere(inPeriod(p)); });
    });
    sh.querySelector('.tbp-brk').addEventListener('click', function () {
      closeSheet(); change(function () { M.days.forEach(function (x) { setCell(x, p, 'Break', ''); }); });
    });
    sh.querySelector('.tbp-ok').addEventListener('click', function () {
      var nt = normTime(t.value) || p.time, nd = String(parseInt(d.value, 10) || p.dur);
      var shift = sh.querySelector('.tbp-shift') && sh.querySelector('.tbp-shift').checked;
      var oldEnd = addMinutes(p.time, p.dur), newEnd = addMinutes(nt, nd);
      var delta = (toMin(newEnd) - toMin(oldEnd));
      closeSheet();
      change(function () {
        var later = shift && delta ? M.periods.slice(pi + 1) : [];
        rows.forEach(function (r) {
          if (!r.time) return;
          var k = periodKey(r);
          if (k === p.k) { r.time = nt; r.dur = nd; return; }
          for (var i = 0; i < later.length; i++) if (later[i].k === k) { r.time = addMinutes(r.time, delta); break; }
        });
      });
    });
  }
  function toMin(t) { var a = (t || '0:0').split(':'); return (+a[0]) * 60 + (+a[1] || 0); }

  // Day sheet: rename / date / stream / copy / clear / delete
  function openDay(di) {
    var d = M.days[di]; if (!d) return;
    var word = sat() ? 'week' : 'day';
    var sh = openSheet(esc(dayLabel(d)) + (daySub(d) ? ' <small>' + esc(daySub(d)) + '</small>' : ''),
      '<div class="tb-two">'
      + (sat() ? '' : '<label class="td-f"><span>Date</span><input type="date" class="tbd-date" value="' + esc(d.date ? toISO(d.date) : '') + '"></label>')
      + '<label class="td-f"><span>Class / stream</span><input class="tbd-grp" value="' + esc(d.group) + '" placeholder="e.g. Science (optional)"></label></div>'
      + '<div class="tb-acts">'
      + '<button type="button" class="tb-act" data-a="copy"><i class="fas fa-clone" aria-hidden="true"></i><span><b>Copy this ' + word + ' to…</b><small>Same lessons on other ' + word + 's</small></span></button>'
      + '<button type="button" class="tb-act" data-a="stream"><i class="fas fa-layer-group" aria-hidden="true"></i><span><b>Add another class / stream</b><small>e.g. Science and Arts on the same ' + word + '</small></span></button>'
      + '<button type="button" class="tb-act" data-a="clear"><i class="fas fa-eraser" aria-hidden="true"></i><span><b>Clear the lessons</b><small>Keeps the ' + word + ', empties its boxes</small></span></button>'
      + '<div class="tbd-new" hidden>' + (d.group ? '' : '<label class="td-f"><span>This row is for</span><input class="tbd-n1" placeholder="e.g. Science"></label>')
      + '<label class="td-f"><span>New row is for</span><input class="tbd-n2" placeholder="e.g. Arts"></label><button type="button" class="rs-btn primary sm tbd-add"><i class="fas fa-plus" aria-hidden="true"></i> Add the row</button></div>'
      + '<button type="button" class="tb-act bad" data-a="del"><i class="fas fa-trash" aria-hidden="true"></i><span><b>Remove this ' + word + '</b><small>' + (sat() ? 'Later weeks keep their numbers' : 'Takes it off the timetable') + '</small></span></button>'
      + '</div>', '<button type="button" class="rs-btn primary tbd-ok">Save</button>');
    sh.querySelector('.tbd-ok').addEventListener('click', function () {
      var g = sh.querySelector('.tbd-grp').value.trim(), di2 = sh.querySelector('.tbd-date');
      var nd = di2 ? di2.value : null;
      closeSheet();
      change(function () {
        rows.forEach(function (r) {
          if (!inDay(d)(r)) return;
          r.group = g;
          if (nd != null && nd) { r.date = nd; r.day = dayFromDate(nd) || r.day; }
        });
      });
    });
    sh.addEventListener('click', function (e) {
      var b = e.target.closest('.tb-act'); if (!b) return;
      var a = b.dataset.a;
      if (a === 'copy') { openCopy(di); return; }
      if (a === 'stream') { var box = sh.querySelector('.tbd-new'); box.hidden = false; (box.querySelector('input')).focus(); return; }
      closeSheet();
      if (a === 'clear') change(function () { rows.forEach(function (r) { if (inDay(d)(r)) { r.subject = ''; r.teacher = ''; } }); });
      else if (a === 'del') {
        var n = rows.filter(function (r) { return r.subject && inDay(d)(r); }).length;
        if (n && !confirm('Remove ' + dayLabel(d) + ' and its ' + n + ' lesson' + (n > 1 ? 's' : '') + '?')) return;
        change(function () { removeWhere(inDay(d)); });
      }
    });
    sh.querySelector('.tbd-add').addEventListener('click', function () {
      var n1 = sh.querySelector('.tbd-n1'), n2 = sh.querySelector('.tbd-n2').value.trim();
      var first = n1 ? n1.value.trim() : d.group;
      if (!n2 || (n1 && !first)) { toast('Type a name for ' + (n1 && !first ? 'both rows' : 'the new row')); return; }
      if (n2.toLowerCase() === 'all' || first.toLowerCase() === 'all') { toast('“All” is kept for whole-day banners — pick another name'); return; }
      closeSheet();
      change(function () {
        if (n1) rows.forEach(function (r) { if (inDay(d)(r)) r.group = first; });
        addDayLike({ week: d.week, date: d.date, day: d.day }, [n2]);
      });
      toast('Added a row for ' + n2);
    });
  }
  function openCopy(di) {
    var d = M.days[di]; if (!d) return;
    var word = sat() ? 'weeks' : 'days';
    var opts = M.days.map(function (x, i) {
      if (i === di) return '';
      var n = M.periods.filter(function (p) { var r = cellRow(x, p); return r && r.subject; }).length;
      return '<label class="tb-opt"><input type="checkbox" value="' + i + '"><span><b>' + esc(dayLabel(x)) + '</b><small>' + esc(daySub(x)) + (n ? (daySub(x) ? ' · ' : '') + n + ' lessons — will be replaced' : (daySub(x) ? ' · ' : '') + 'empty') + '</small></span></label>';
    }).join('');
    var sh = openSheet('Copy ' + esc(dayLabel(d)) + ' to…',
      (opts ? '<label class="tb-opt all"><input type="checkbox" class="tbc-all"><span><b>All other ' + word + '</b></span></label>' + opts : '<p class="rs-muted">Add another ' + (sat() ? 'week' : 'day') + ' first.</p>')
      + '<label class="rs-check"><input type="checkbox" class="tbc-new"> …and add a new ' + (sat() ? 'week' : 'day') + ' with the same lessons</label>',
      '<button type="button" class="rs-btn primary tbc-ok"><i class="fas fa-clone" aria-hidden="true"></i> Copy</button>');
    var all = sh.querySelector('.tbc-all');
    if (all) all.addEventListener('change', function () { sh.querySelectorAll('.tb-opt input[value]').forEach(function (c) { c.checked = all.checked; }); });
    sh.querySelector('.tbc-ok').addEventListener('click', function () {
      var targets = Array.prototype.map.call(sh.querySelectorAll('.tb-opt input[value]:checked'), function (c) { return M.days[+c.value]; });
      var addNew = sh.querySelector('.tbc-new').checked;
      if (!targets.length && !addNew) { toast('Pick at least one ' + (sat() ? 'week' : 'day')); return; }
      closeSheet();
      change(function () {
        if (addNew) {
          var spec = nextDayFrom(M.days[M.days.length - 1]); spec.group = d.group;
          var nd = { week: spec.week, date: spec.date, day: spec.day, group: d.group }; nd.k = dayKey(nd);
          M.periods.forEach(function (p) { if (!cellRow(nd, p)) newRowFor(nd, p); });
          targets.push(nd);
        }
        targets.forEach(function (x) {
          M.periods.forEach(function (p) { var r = cellRow(d, p); setCell(x, p, r ? r.subject : '', r ? r.teacher : ''); });
        });
      });
      toast('Copied to ' + targets.length + ' ' + (targets.length === 1 ? (sat() ? 'week' : 'day') : word));
    });
  }

  // ---------------------------------------------------------- click wiring
  B.addEventListener('click', function (e) {
    var b = e.target.closest('[data-tb], .tb-cell'); if (!b) return;
    if (b.classList.contains('tb-cell')) {
      sel.d = +b.dataset.d; sel.p = +b.dataset.p; focusSel();
      openEditor();
      return;
    }
    var a = b.dataset.tb;
    if (a === 'undo') undo();
    else if (a === 'wide') { $('tdWrap').classList.toggle('td-wide'); render(); }
    else if (a === 'restart') {
      if (filled().n && !confirm('Start a new grid? The lessons you’ve entered will be cleared (you can undo).')) return;
      snap(); rows = []; refresh();
    }
    else if (a === 'wizgo') wizardGo();
    else if (a === 'addperiod') { change(function () { addPeriod(); }); }
    else if (a === 'addday') addDay();
    else if (a === 'period') openPeriod(+b.dataset.p);
    else if (a === 'day') openDay(+b.dataset.d);
    else if (a === 'copy') openCopy(+b.dataset.d);
    else if (a === 'pday') { phoneDay = +b.dataset.d; render(); var on = B.querySelector('.tb-dchip.on'); on && on.scrollIntoView({ inline: 'center', block: 'nearest' }); }
    else if (a === 'pcell') openPicker(phoneDay, +b.dataset.p);
    else if (a === 'pick') {
      var s = b.dataset.s;
      closeEditor();
      commitCell(sel.d, sel.p, s, teacherFor(s));
      move(0, 1, true) || focusSel();
    }
  });
  // keep focus in the grid when using the palette
  B.addEventListener('mousedown', function (e) { if (e.target.closest('.tb-chip[data-tb="pick"]')) e.preventDefault(); });

  // ---------------------------------------------------------------- modes
  function setMode(m, quiet) {
    mode = m;
    RE.dataset.mode = m;
    document.querySelectorAll('[data-td-mode]').forEach(function (b) {
      if (b.closest('#tdModes')) { b.classList.toggle('on', b.dataset.tdMode === m); b.setAttribute('aria-pressed', b.dataset.tdMode === m); }
    });
    if (m === 'paste') { var g = $('gridPasteBox'); if (g && g.style.display !== 'none') g.open = true; }
    if (!quiet && m === 'build') render();
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-td-mode]'); if (!b) return;
    setMode(b.dataset.tdMode);
    if (b.closest('#ttBuilder')) RE.scrollIntoView({ block: 'start', behavior: 'smooth' });
  });

  // After a paste / quick-add builds rows, jump back to the grid to show them.
  ['gridPaste', 'bulkAdd', 'fillRestOfDay'].forEach(function (fn) {
    var orig = window[fn]; if (typeof orig !== 'function') return;
    window[fn] = function () {
      var before = rows.length; snap();
      var out = orig.apply(this, arguments);
      if (rows.length !== before) { if (gridLayout()) setMode('build'); else setMode('list'); toast('Added ' + (rows.length - before) + ' lessons'); }
      else undoStack.pop();
      return out;
    };
  });
  var origRE = window.renderEditor;
  window.renderEditor = function () {
    var out = origRE.apply(this, arguments);
    if (!window.__tbQuiet) render();
    return out;
  };
  phone.addEventListener && phone.addEventListener('change', function () { closeSheet(); render(); });
  el('layout').addEventListener('change', function () { mode = null; undoStack = []; render(); });

  // Global undo / save shortcuts
  document.addEventListener('keydown', function (e) {
    var mod = e.ctrlKey || e.metaKey; if (!mod) return;
    var typing = e.target.matches && e.target.matches('input, textarea, select, [contenteditable="true"]');
    if ((e.key === 'z' || e.key === 'Z') && !e.shiftKey && !typing && mode === 'build' && gridLayout()) { e.preventDefault(); undo(); }
    else if (e.key === 's' || e.key === 'S') { e.preventDefault(); quickSave(); }
  });

  // List view (exam timetables): Enter in a session adds the next one.
  $('rowBody').addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || !e.target.matches('input')) return;
    var card = e.target.closest('.sess-card'); if (!card) return;
    e.preventDefault();
    if (+card.dataset.i === rows.length - 1) addRow();
    else { var nx = document.querySelector('#rowBody .sess-card[data-i="' + (+card.dataset.i + 1) + '"] [data-f="subject"]'); nx && nx.focus(); }
  });

  // ---------------------------------------------------------------- toast
  var toastT = null;
  function toast(msg) {
    var t = $('tdToast');
    if (!t) { t = document.createElement('div'); t.id = 'tdToast'; t.className = 'td-toast no-print'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.textContent = msg; t.classList.add('on');
    clearTimeout(toastT); toastT = setTimeout(function () { t.classList.remove('on'); }, 2200);
  }
  window.tdToast = toast;

  // ===================================================== saved + header save
  var savedSnap = null;
  function stateSnap() { try { return JSON.stringify(collectState()) + '§' + el('saveName').value; } catch (x) { return ''; } }
  function hasContent() { return rows.some(function (r) { return r.subject; }) || Object.keys(rosterCells || {}).length; }
  function docState() {
    var name = (el('saveName').value || '').trim();
    $('tdDocName').textContent = name || 'Untitled timetable';
    $('tdDocName').classList.toggle('untitled', !name);
    var st = $('tdDocState'), dirty = currentDesignId && savedSnap !== null && stateSnap() !== savedSnap;
    if (!currentDesignId) { st.className = 'sl-pill mid'; st.textContent = 'Not saved yet'; }
    else if (dirty) { st.className = 'sl-pill info'; st.textContent = 'Unsaved changes'; }
    else { st.className = 'sl-pill good'; st.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> Saved'; }
    $('tdSaveLbl').textContent = currentDesignId ? (dirty ? 'Save changes' : 'Saved') : 'Save';
    $('tdSaveBtn').classList.toggle('ghost', !!currentDesignId && !dirty);
    $('tdSaveBtn').classList.toggle('primary', !currentDesignId || !!dirty);
  }
  var origRS = window.renderSheet;
  window.renderSheet = function () { var o = origRS.apply(this, arguments); try { docState(); } catch (x) {} return o; };
  var origApply = window.applyState;
  window.applyState = function () { var o = origApply.apply(this, arguments); undoStack = []; mode = null; render(); savedSnap = stateSnap(); docState(); return o; };
  var origFlash = window.flashSaved;
  window.flashSaved = function () {
    origFlash.apply(this, arguments);
    savedSnap = stateSnap(); closeSheet(); docState(); toast('Saved ✓ — find it under “Saved”');
  };
  var origNew = window.newDesign;
  window.newDesign = function () { var o = origNew.apply(this, arguments); savedSnap = null; docState(); return o; };
  function suggestName() {
    var t = (el('title').value || layout().title || 'Timetable').trim(), sub = (el('subtitle').value || '').trim();
    return sub ? t + ' — ' + sub : t;
  }
  function openSave(asCopy) {
    var home = $('tdSaveForm');
    var sh = openSheet(currentDesignId && !asCopy ? 'Rename or save' : 'Save this timetable',
      '<p class="rs-muted tb-save-p">Saved timetables are kept for your school — open them any time from <b>Saved</b> to edit, print or duplicate.</p>',
      '');
    sh.querySelector('.tb-sheet-b').appendChild(home);
    if (!el('saveName').value) el('saveName').value = suggestName();
    if (asCopy) el('saveName').value = (el('saveName').value || 'Timetable').replace(/ \(copy\)$/, '') + ' (copy)';
    var cp = $('tdSaveCopy'); cp.hidden = !currentDesignId || asCopy;
    setTimeout(function () { el('saveName').focus(); el('saveName').select(); }, 60);
  }
  function quickSave() {
    if (currentDesignId && (el('saveName').value || '').trim()) saveDesign();
    else openSave(false);
  }
  $('tdSaveBtn').addEventListener('click', quickSave);
  $('tdDocName').addEventListener('click', function () { openSave(false); });
  $('tdSaveCopy').addEventListener('click', function () {
    var n = (el('saveName').value || 'Timetable').replace(/ \(copy\)$/, '') + ' (copy)';
    origNew(); el('saveName').value = n; saveDesign();
  });
  el('saveName').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); saveDesign(); } });
  el('saveName').addEventListener('input', docState);
  window.addEventListener('beforeunload', function (e) {
    var dirty = currentDesignId ? stateSnap() !== savedSnap : hasContent();
    if (dirty && hasContent()) { e.preventDefault(); e.returnValue = ''; }
  });

  // Saved timetables drawer
  var savedList = [];
  window.renderSavedList = function (list) {
    savedList = list || [];
    var n = savedList.length;
    el('savedCount').textContent = n;
    $('tdSavedBtn').setAttribute('aria-label', 'Saved timetables: ' + n);
    paintSaved();
  };
  function paintSaved(q) {
    var p = el('savedPanel');
    q = (q || '').trim().toLowerCase();
    if (!savedList.length) {
      p.innerHTML = '<div class="rs-blank tb-blank"><span><i class="fas fa-folder-open" aria-hidden="true"></i></span><h3>No saved timetables yet</h3><p>Tap <b>Save</b> at the top and give it a name — it’ll appear here, ready to open and edit later.</p></div>';
      return;
    }
    var list = savedList.filter(function (d) { return !q || (d.name || '').toLowerCase().indexOf(q) >= 0 || labelForLayout(d.layout).toLowerCase().indexOf(q) >= 0; });
    var icon = { saturday: 'fa-calendar-week', holiday: 'fa-umbrella-beach', exam: 'fa-file-signature', list_table: 'fa-table-list', grid: 'fa-table-cells', roster_week: 'fa-user-clock', roster_day: 'fa-user-clock' };
    p.innerHTML = (savedList.length > 5 ? '<label class="rs-search tb-sv-q"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><input type="search" id="tdSavedQ" placeholder="Find a saved timetable" value="' + esc(q) + '" autocomplete="off"></label>' : '')
      + (list.length ? list.map(function (d) {
        var cur = String(d.id) === String(currentDesignId);
        return '<div class="tb-sv' + (cur ? ' cur' : '') + '">'
          + '<button type="button" class="tb-sv-main" data-call="loadDesign" data-args="' + d.id + '"><i class="fas ' + (icon[d.layout] || 'fa-calendar') + '" aria-hidden="true"></i>'
          + '<span><b>' + esc(d.name) + '</b><small>' + esc(labelForLayout(d.layout)) + ' · ' + esc(ago(d.updated_at)) + (cur ? ' · <em>open now</em>' : '') + '</small></span></button>'
          + '<button type="button" class="rs-icon-btn" title="Duplicate" aria-label="Duplicate ' + esc(d.name) + '" data-call="dupDesign" data-args="' + d.id + '"><i class="fas fa-copy" aria-hidden="true"></i></button>'
          + '<button type="button" class="rs-icon-btn danger" title="Delete" aria-label="Delete ' + esc(d.name) + '" data-call="deleteDesign" data-args="' + d.id + '"><i class="fas fa-trash" aria-hidden="true"></i></button>'
          + '</div>';
      }).join('') : '<p class="rs-muted tb-sv-none">No match.</p>');
    var qi = $('tdSavedQ');
    if (qi) { qi.addEventListener('input', function () { var pos = qi.selectionStart; paintSaved(qi.value); var n = $('tdSavedQ'); n.focus(); n.setSelectionRange(pos, pos); }); }
  }
  function ago(s) {
    if (!s) return '';
    var d = new Date(String(s).replace(' ', 'T')); if (isNaN(d)) return 'updated ' + s;
    var m = Math.round((Date.now() - d.getTime()) / 60000);
    if (m < 1) return 'just now'; if (m < 60) return m + ' min ago';
    var h = Math.round(m / 60); if (h < 24) return h + ' h ago';
    var dd = Math.round(h / 24); if (dd < 8) return dd + ' day' + (dd > 1 ? 's' : '') + ' ago';
    return 'updated ' + fmtDate(String(s).slice(0, 10));
  }
  window.toggleSaved = function () {
    var p = el('savedPanel');
    var sh = openSheet('<i class="fas fa-folder-open" aria-hidden="true"></i> Saved timetables <span class="tb-cnt">' + savedList.length + '</span>', '',
      '<button type="button" class="rs-btn ghost" data-new-design><i class="fas fa-file" aria-hidden="true"></i> Start a new one</button>', 'tb-saved');
    p.style.display = 'block';
    sh.querySelector('.tb-sheet-b').appendChild(p);
    sh.querySelector('[data-new-design]').addEventListener('click', function () {
      if (hasContent() && !confirm('Start a new, empty timetable? Anything not saved here will be lost.')) return;
      closeSheet(); startNew();
    });
    loadSavedList(true);
  };
  function startNew() {
    window.newDesign();
    rows = []; rosterCells = {}; undoStack = []; mode = null;
    el('title').value = ''; delete el('title').dataset.touched; el('subtitle').value = '';
    refresh(); window.scrollTo({ top: 0, behavior: 'smooth' }); toast('New timetable');
  }
  ['loadDesign', 'dupDesign'].forEach(function (fn) {
    var orig = window[fn];
    window[fn] = function () { closeSheet(); return orig.apply(this, arguments); };
  });
  var origDel = window.deleteDesign;
  window.deleteDesign = function () { return origDel.apply(this, arguments); };

  // ------------------------------------------------------------------ go
  try { window.renderSavedList(DESIGNER_CONFIG.saved || []); } catch (x) {}
  render(); docState();
})();
