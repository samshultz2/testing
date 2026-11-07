/*
 * Visual equation editor for CBT questions ("what you see is what students see").
 *
 * Enhances a <textarea>/<input> into an editable box where ordinary text is
 * typed normally and every formula is a live, formatted MathLive field
 * ("chip") sitting inside the sentence. The original field stays in the form
 * (hidden) and is kept in sync, holding exactly what is saved and what the
 * student screen renders: plain text with formulas as \( … \) LaTeX.
 *
 *   MathRich.ready                    → Promise (MathLive loaded)
 *   MathRich.enhance(field)           → turn a field into a visual editor
 *   MathRich.setVisual(field, on)     → switch between visual and LaTeX code
 *   MathRich.isVisual(field)
 *   MathRich.insert(field, item, caretMark, opts) → used by the symbol toolbar
 *   MathRich.refresh(field)           → rebuild from field.value (after reset)
 *
 * MathLive is vendored (static/vendor/mathlive) and loaded on first use. If it
 * can't load, nothing is enhanced and the plain fields keep working.
 * External 'self' script so the admin's soft-navigation SPA can re-run it.
 */
(function () {
  'use strict';
  if (window.MathRich) return;

  var BASE = '/static/vendor/mathlive/';
  var ZW = '​';
  var loading = null;

  function load() {
    if (loading) return loading;
    loading = new Promise(function (resolve, reject) {
      if (window.customElements && customElements.get('math-field')) { resolve(); return; }
      var s = document.createElement('script');
      s.src = BASE + 'mathlive.min.js';
      s.async = true;
      s.onload = function () { customElements.whenDefined('math-field').then(resolve, reject); };
      s.onerror = function () { reject(new Error('MathLive failed to load')); };
      document.head.appendChild(s);
      setTimeout(function () { reject(new Error('MathLive load timed out')); }, 30000);
    }).then(function () {
      var M = window.MathfieldElement;
      M.fontsDirectory = BASE + 'fonts';
      M.soundsDirectory = null;
      try { M.keypressSound = null; M.plonkSound = null; } catch (e) { /* older API */ }
    });
    return loading;
  }

  // ---- text ⇄ parts -------------------------------------------------------
  var DELIM = /\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]|\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;
  function parse(text) {
    var parts = [], last = 0, m;
    text = text || '';
    DELIM.lastIndex = 0;
    while ((m = DELIM.exec(text))) {
      if (m.index > last) parts.push({ t: 'text', v: text.slice(last, m.index) });
      var display = m[2] != null || m[3] != null;
      parts.push({ t: 'math', v: (m[1] != null ? m[1] : m[2] != null ? m[2] : m[3] != null ? m[3] : m[4]).trim(), display: display });
      last = DELIM.lastIndex;
    }
    if (last < text.length) parts.push({ t: 'text', v: text.slice(last) });
    return parts;
  }

  function chipLatex(chip) {
    var mf = chip.querySelector('math-field');
    var v = '';
    if (mf && typeof mf.getValue === 'function' && mf.isConnected) {
      try { v = mf.getValue('latex-without-placeholders'); } catch (e) { v = chip.dataset.latex || ''; }
    } else {
      v = chip.dataset.latex || '';
    }
    return (v || '').trim();
  }

  function serialize(node, multiline) {
    var s = '';
    node.childNodes.forEach(function (n) {
      if (n.nodeType === 3) {
        s += n.nodeValue.replace(/​/g, '').replace(/ /g, ' ');
      } else if (n.nodeType === 1 && n.classList.contains('mr-chip')) {
        var v = chipLatex(n);
        if (v) s += n.dataset.display ? '\\[' + v + '\\]' : '\\(' + v + '\\)';
      } else if (n.nodeName === 'BR') {
        s += '\n';
      } else if (n.nodeName === 'DIV' || n.nodeName === 'P') {
        if (s && s.slice(-1) !== '\n') s += '\n';
        s += serialize(n, multiline);
      } else if (n.nodeType === 1) {
        s += serialize(n, multiline);
      }
    });
    return s;
  }

  // ---- chips --------------------------------------------------------------
  // Phones/tablets: a formula has no native keyboard, so MathLive's own maths
  // keyboard (digits, letters, operators) opens when a formula is tapped.
  var mq = function (q) { return !!(window.matchMedia && window.matchMedia(q).matches); };
  var TOUCH = mq('(pointer: coarse)') || mq('(any-pointer: coarse)') ||
              (navigator.maxTouchPoints || 0) > 0 || 'ontouchstart' in window;
  // Formulas are edited in the roomy "Edit formula" panel on every device
  // (a blank inside a fraction is far too small a target to tap or click).
  var PANEL = true;
  if (TOUCH) document.documentElement.classList.add('mr-touch');

  function makeChip(latex, display) {
    var wrap = document.createElement('span');
    wrap.className = 'mr-chip';
    wrap.contentEditable = 'false';
    wrap.dataset.latex = latex || '';
    if (display) wrap.dataset.display = '1';
    var mf = new window.MathfieldElement();
    mf.mathVirtualKeyboardPolicy = 'manual';
    // Touch screens edit formulas in the "Edit formula" panel (see openSheet):
    // inline they are display-only, so a tap never fights the text box.
    if (PANEL) { mf.setAttribute('read-only', ''); mf.tabIndex = -1; }
    mf.smartMode = false;
    mf.setAttribute('aria-label', 'Formula — type to edit; Backspace on an empty formula removes it');
    wrap.appendChild(mf);
    var x = document.createElement('button');
    x.type = 'button'; x.className = 'mr-chip-x'; x.tabIndex = -1;
    x.setAttribute('aria-label', 'Remove this formula'); x.title = 'Remove formula';
    x.textContent = '×';
    wrap.appendChild(x);
    return wrap;
  }

  function removeChip(ed, chip, focusAfter) {
    var prev = chip.previousSibling;
    chip.remove();
    if (ed._mrChip === chip) ed._mrChip = null;
    tidy(ed);
    if (focusAfter) {
      ed.focus();
      var r = document.createRange();
      if (prev && prev.isConnected && prev.nodeType === 3) r.setStart(prev, prev.nodeValue.length);
      else { r.selectNodeContents(ed); r.collapse(true); }
      r.collapse(true);
      var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
      ed._mrRange = r.cloneRange();
    }
    ed.contentEditable = 'true';
    sync(ed);
  }

  // The formula right before (dir -1) or after (dir 1) a collapsed caret in
  // the text, skipping the invisible spacer characters around formulas.
  function chipBeside(ed, dir) {
    var sel = window.getSelection();
    if (!sel.rangeCount || !sel.isCollapsed) return null;
    var r = sel.getRangeAt(0), n = r.startContainer, o = r.startOffset, cand = null;
    if (!ed.contains(n)) return null;
    if (n.nodeType === 3) {
      var part = dir < 0 ? n.nodeValue.slice(0, o) : n.nodeValue.slice(o);
      if (part.replace(/\u200B/g, '')) return null;
      cand = dir < 0 ? n.previousSibling : n.nextSibling;
    } else {
      cand = dir < 0 ? n.childNodes[o - 1] : n.childNodes[o];
    }
    while (cand && cand.nodeType === 3 && !cand.nodeValue.replace(/\u200B/g, '')) {
      cand = dir < 0 ? cand.previousSibling : cand.nextSibling;
    }
    return cand && cand.classList && cand.classList.contains('mr-chip') ? cand : null;
  }

  // ---- Touch: the "Edit formula" panel ------------------------------------
  // A standalone formula box (MathLive's best-supported setup on phones) with
  // the on-screen maths keyboard, pinned to the top so the keyboard below
  // never hides it. Done writes the formula back; Delete removes it.
  var sheet = null;
  function getSheet() {
    if (sheet && sheet.isConnected) return sheet;
    sheet = document.createElement('div');
    sheet.className = 'mr-sheet';
    sheet.hidden = true;
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-modal', 'true');
    sheet.setAttribute('aria-label', 'Edit formula');
    sheet.innerHTML =
      '<div class="mr-sheet-card">' +
        '<div class="mr-sheet-head"><strong>Edit formula</strong>' +
          '<span class="mr-sheet-hint">Tap or click a blank ▢ to fill it · Tab moves to the next blank</span></div>' +
        '<div class="mr-sheet-field"></div>' +
        '<div class="mr-sheet-tools"></div>' +
        '<div class="mr-sheet-actions">' +
          '<button type="button" class="btn btn-sm mr-sheet-del"><i class="fas fa-trash" aria-hidden="true"></i> Delete</button>' +
          '<button type="button" class="btn btn-sm mr-sheet-kbd" aria-pressed="false" title="Show or hide the maths keyboard"><i class="fas fa-keyboard" aria-hidden="true"></i><span class="mr-sheet-kbd-l"> Keyboard</span></button>' +
          '<span class="mr-sheet-gap"></span>' +
          '<button type="button" class="btn btn-secondary btn-sm mr-sheet-cancel">Cancel</button>' +
          '<button type="button" class="btn btn-primary btn-sm mr-sheet-done"><i class="fas fa-check" aria-hidden="true"></i> Done</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(sheet);
    var mf = newSheetField(sheet);
    function showKeyboard() {
      if (TOUCH && window.mathVirtualKeyboard) { try { window.mathVirtualKeyboard.show(); } catch (e) { /* ignore */ } }
    }
    sheet._showKeyboard = showKeyboard;
    var kb = sheet.querySelector('.mr-sheet-kbd');
    kb.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
    kb.addEventListener('click', function () {
      var vk = window.mathVirtualKeyboard; if (!vk) return;
      try { if (vk.visible) vk.hide(); else vk.show(); } catch (e) { /* ignore */ }
      kb.setAttribute('aria-pressed', vk.visible ? 'true' : 'false');
      setTimeout(fitAboveKeyboard, 350);
      sheet.mf.focus();
    });
    // The tap that opened the panel is followed by a synthetic click at the
    // same spot — swallow clicks for a moment so it can't hit a button that
    // has just appeared under the finger.
    sheet.addEventListener('click', function (ev) {
      if (Date.now() - (sheet._openedAt || 0) < 450) { ev.preventDefault(); ev.stopPropagation(); }
    }, true);
    // Keep the whole panel above the on-screen maths keyboard.
    function fitAboveKeyboard() {
      var vk = window.mathVirtualKeyboard, h = 0;
      try { if (vk && vk.visible && vk.boundingRect) h = vk.boundingRect.height || 0; } catch (e) { h = 0; }
      sheet.style.paddingBottom = h ? (h + 8) + 'px' : '';
    }
    sheet._fit = fitAboveKeyboard;
    if (window.mathVirtualKeyboard && window.mathVirtualKeyboard.addEventListener) {
      window.mathVirtualKeyboard.addEventListener('geometrychange', fitAboveKeyboard);
    }
    sheet.querySelector('.mr-sheet-done').addEventListener('click', function () { closeSheet('done'); });
    sheet.querySelector('.mr-sheet-cancel').addEventListener('click', function () { closeSheet('cancel'); });
    sheet.querySelector('.mr-sheet-del').addEventListener('click', function () { closeSheet('delete'); });
    return sheet;
  }

  // The panel's formula box. On touch screens a fresh one per opening: MathLive
  // ignores where the first tap lands on a box that was focused before, so a
  // reused (or auto-focused) box put the caret at the start instead of where
  // the teacher tapped — e.g. after the d in d/dx.
  function newSheetField(sh) {
    var holder = sh.querySelector('.mr-sheet-field');
    if (sh.mf) sh.mf.remove();
    var mf = new window.MathfieldElement();
    // Touch: MathLive shows its own keyboard when the box is tapped.
    mf.mathVirtualKeyboardPolicy = TOUCH ? 'auto' : 'manual';
    mf.smartMode = false;
    mf.setAttribute('aria-label', 'Formula');
    holder.appendChild(mf);
    mf.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); closeSheet('done'); }
      else if (ev.key === 'Escape') { ev.preventDefault(); closeSheet('cancel'); }
    }, true);
    mf.addEventListener('focus', function () { if (sh._fit) setTimeout(sh._fit, 350); });
    sh.mf = mf;
    return mf;
  }

  function sheetOpenFor(ed) { return !!(sheet && !sheet.hidden && sheet._ed === ed); }

  function openSheet(ed, chip, isNew, then) {
    var sh = getSheet();
    var mf = TOUCH ? newSheetField(sh) : sh.mf;
    sh._ed = ed; sh._chip = chip; sh._isNew = !!isNew;
    sh._before = chip.dataset.latex || '';
    try { mf.value = sh._before; } catch (e) { /* ignore */ }
    // Bring the page's subject symbol toolbar into the panel while it's open
    // (it inserts into this formula), and put it back on close.
    var form = ed.mrField && ed.mrField.form;
    var tb = form && form.querySelector('.mx');
    if (tb && !sh._tb) {
      sh._tbHome = document.createComment('mx-home');
      tb.parentNode.insertBefore(sh._tbHome, tb);
      sh.querySelector('.mr-sheet-tools').appendChild(tb);
      sh._tb = tb;
    }
    sh.hidden = false;
    sh._openedAt = Date.now();
    document.documentElement.classList.add('mr-sheet-open');
    chip.classList.add('is-editing');
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    sh.querySelector('.mr-sheet-hint').textContent = (TOUCH && !then)
      ? 'Tap exactly where you want to type — e.g. just after the d in d/dx'
      : 'Tap or click a blank ▢ to fill it · Tab moves to the next blank';
    if (TOUCH && !then) {
      // Existing formula on a touch screen: don't auto-focus (see newSheetField);
      // the teacher's first tap places the caret and opens the maths keyboard.
      if (window.mathVirtualKeyboard) { try { window.mathVirtualKeyboard.hide(); } catch (e) { /* ignore */ } }
      if (sh._fit) sh._fit();
      return;
    }
    focusField(mf, function () {
      if (TOUCH && window.mathVirtualKeyboard) { try { window.mathVirtualKeyboard.show(); } catch (e) { /* ignore */ } }
      var kb = sh.querySelector('.mr-sheet-kbd');
      if (kb && window.mathVirtualKeyboard) kb.setAttribute('aria-pressed', window.mathVirtualKeyboard.visible ? 'true' : 'false');
      if (sh._fit) { sh._fit(); setTimeout(sh._fit, 350); }
      if (then) then(mf);
    });
  }

  function closeSheet(how) {
    var sh = sheet;
    if (!sh || sh.hidden) return;
    var ed = sh._ed, chip = sh._chip, mf = sh.mf;
    var latex = '';
    try { latex = (mf.getValue('latex-without-placeholders') || '').trim(); } catch (e) { latex = ''; }
    if (how === 'done' && latex) {
      chip.dataset.latex = latex;
      var inline = chip.querySelector('math-field');
      try { inline.value = latex; } catch (e) { /* ignore */ }
    }
    var drop = how === 'delete' || (how === 'done' && !latex) || (how === 'cancel' && sh._isNew && !sh._before);
    sh.hidden = true;
    sh.style.paddingBottom = '';
    document.documentElement.classList.remove('mr-sheet-open');
    if (sh._tb && sh._tbHome && sh._tbHome.parentNode) {
      sh._tbHome.parentNode.insertBefore(sh._tb, sh._tbHome);
      sh._tbHome.remove();
    }
    sh._tb = sh._tbHome = null;
    if (window.mathVirtualKeyboard) { try { window.mathVirtualKeyboard.hide(); } catch (e) { /* ignore */ } }
    try { mf.blur(); } catch (e) { /* ignore */ }
    if (chip.isConnected) {
      chip.classList.remove('is-editing');
      if (drop) removeChip(ed, chip, false);
      else { tidy(ed); sync(ed); }
    }
    sh._ed = sh._chip = null;
  }

  function initChip(ed, chip) {
    var mf = chip.querySelector('math-field');
    if (!mf || mf.dataset.mrInit) return mf;
    mf.dataset.mrInit = '1';
    try { mf.value = chip.dataset.latex || ''; } catch (e) { /* keep empty */ }
    mf.addEventListener('input', function () { chip.dataset.latex = chipLatex(chip); sync(ed); });
    mf.addEventListener('focus', function () { ed._mrChip = chip; chip.classList.add('is-editing'); });
    mf.addEventListener('focusout', function () {
      setTimeout(function () {
        if (!chip.isConnected) { ed.contentEditable = 'true'; return; }
        if (mf.contains(document.activeElement) || document.activeElement === mf) return;
        chip.classList.remove('is-editing');
        ed.contentEditable = 'true';             // text editable again (see pointerdown)
        // Leaving formulas altogether: put the on-screen maths keyboard away.
        var a = document.activeElement;
        if (TOUCH && window.mathVirtualKeyboard && !(a && a.tagName === 'MATH-FIELD')) {
          try { window.mathVirtualKeyboard.hide(); } catch (e) { /* ignore */ }
        }
        // An emptied formula disappears instead of leaving a blank box.
        if (!chipLatex(chip)) removeChip(ed, chip, false);
      }, 0);
    });
    chip.querySelector('.mr-chip-x').addEventListener('click', function (ev) {
      ev.preventDefault(); ev.stopPropagation(); removeChip(ed, chip, !TOUCH);
    });
    if (PANEL) {
      // Open on release (capture phase): MathLive swallows the press and the
      // browser never fires "click" on its field. A finger that moved was a
      // scroll, not a tap; keyboard users open it with Enter/Space.
      var down = null;
      chip.addEventListener('pointerdown', function (ev) {
        if (ev.target.closest && ev.target.closest('.mr-chip-x')) { down = null; return; }
        down = { x: ev.clientX, y: ev.clientY };
        ev.stopPropagation();                    // keep MathLive from grabbing focus
      }, true);
      chip.addEventListener('pointercancel', function () { down = null; }, true);
      chip.addEventListener('pointerup', function (ev) {
        if (!down) return;
        var moved = Math.abs(ev.clientX - down.x) + Math.abs(ev.clientY - down.y);
        down = null;
        if (moved > 12) return;
        ev.preventDefault(); ev.stopPropagation();
        openSheet(ed, chip, false);
      }, true);
      chip.addEventListener('click', function (ev) {
        if (ev.target.closest && ev.target.closest('.mr-chip-x')) return;
        ev.preventDefault(); ev.stopPropagation();
      }, true);
      chip.tabIndex = 0;
      chip.setAttribute('role', 'button');
      chip.setAttribute('aria-label', 'Edit formula');
      chip.addEventListener('keydown', function (ev) {
        if (ev.target === chip && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); openSheet(ed, chip, false); }
      });
    }
    mf.addEventListener('move-out', function (ev) {
      var d = ev.detail && ev.detail.direction;
      if (d === 'forward' || d === 'backward') { ev.preventDefault(); caretBeside(ed, chip, d === 'forward'); }
    });
    mf.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' || (ev.key === 'Enter' && !ev.shiftKey)) {
        ev.preventDefault(); ev.stopPropagation(); caretBeside(ed, chip, true);
      } else if ((ev.key === 'Backspace' || ev.key === 'Delete') && !chipLatex(chip)) {
        // Backspace in an already-empty formula removes the formula itself.
        ev.preventDefault(); ev.stopPropagation(); removeChip(ed, chip, true);
      }
    }, true);
    return mf;
  }

  // Keep a (zero-width) text node on both sides of every chip so the caret
  // can always sit before / after a formula.
  function tidy(ed) {
    Array.prototype.slice.call(ed.querySelectorAll('.mr-chip')).forEach(function (c) {
      if (!c.previousSibling || c.previousSibling.nodeType !== 3) c.parentNode.insertBefore(document.createTextNode(ZW), c);
      if (!c.nextSibling || c.nextSibling.nodeType !== 3) c.parentNode.insertBefore(document.createTextNode(ZW), c.nextSibling);
    });
  }

  function caretBeside(ed, chip, after) {
    ed.contentEditable = 'true';
    chip.classList.remove('is-editing');
    tidy(ed);
    ed._mrChip = null;
    var t = after ? chip.nextSibling : chip.previousSibling;
    ed.focus();
    var r = document.createRange();
    var pos = after ? Math.min(1, t.nodeValue.length) : t.nodeValue.length;
    if (after && t.nodeValue.charAt(0) !== ZW) pos = 0;
    r.setStart(t, pos); r.collapse(true);
    var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
    ed._mrRange = r.cloneRange();
  }

  function fill(ed, text) {
    ed.innerHTML = '';
    parse(text).forEach(function (p) {
      if (p.t === 'text') {
        p.v.split('\n').forEach(function (line, i) {
          if (i) ed.appendChild(document.createElement('br'));
          if (line) ed.appendChild(document.createTextNode(line));
        });
      } else {
        ed.appendChild(makeChip(p.v, p.display));
      }
    });
    tidy(ed);
    ed.querySelectorAll('.mr-chip').forEach(function (c) { initChip(ed, c); });
    markEmpty(ed);
  }

  function markEmpty(ed) {
    var empty = !ed.querySelector('.mr-chip') && !ed.textContent.replace(/​/g, '').trim();
    ed.classList.toggle('is-empty', empty);
  }

  function sync(ed) {
    var f = ed.mrField;
    var v = serialize(ed, ed._mrMulti);
    v = ed._mrMulti ? v.replace(/\n+$/, '') : v.replace(/\n/g, ' ');
    if (f.value !== v) {
      f.value = v;
      f.dispatchEvent(new Event('input', { bubbles: true }));
    }
    markEmpty(ed);
    ed.classList.remove('is-invalid');
  }

  // ---- caret helpers --------------------------------------------------------
  function saveRange(ed) {
    var sel = window.getSelection();
    if (!sel.rangeCount) return;
    var r = sel.getRangeAt(0);
    if (ed.contains(r.startContainer) && !(r.startContainer.closest && r.startContainer.closest('.mr-chip'))) {
      ed._mrRange = r.cloneRange();
    }
  }
  function rangeIn(ed) {
    var r = ed._mrRange;
    if (!r || !ed.contains(r.startContainer)) {
      r = document.createRange(); r.selectNodeContents(ed); r.collapse(false);
    }
    return r;
  }
  // The formula the toolbar should add to: the focused one, or — when focus
  // went to a toolbar control by keyboard — the formula last edited here.
  function activeChipField(ed) {
    var a = document.activeElement;
    if (a && a.tagName === 'MATH-FIELD' && ed.contains(a)) return a;
    var c = ed._mrChip;
    if (c && c.isConnected && ed.contains(c) && !ed.contains(a)) return c.querySelector('math-field');
    return null;
  }

  function insertText(ed, text) {
    var r = rangeIn(ed);
    ed.focus();
    var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
    if (!document.execCommand('insertText', false, text)) {
      r.deleteContents(); var t = document.createTextNode(text); r.insertNode(t);
      r.setStartAfter(t); r.collapse(true); sel.removeAllRanges(); sel.addRange(r);
    }
    saveRange(ed); sync(ed);
  }

  function insertChipAt(ed, latex) {
    var r = rangeIn(ed);
    var selected = r.toString().replace(/​/g, '');
    r.deleteContents();
    var chip = makeChip('', false);
    r.insertNode(chip);
    tidy(ed);
    var mf = initChip(ed, chip);
    return { chip: chip, mf: mf, selected: selected };
  }

  function insertParts(ed, text) {
    parse(text).forEach(function (p) {
      if (p.t === 'text') { insertText(ed, p.v); return; }
      var res = insertChipAt(ed, p.v);
      res.chip.dataset.latex = p.v;
      try { res.mf.value = p.v; } catch (e) { /* ignore */ }
      caretBeside(ed, res.chip, true);
    });
    sync(ed);
  }

  // A just-created formula box mounts on the next frame — focus it now and
  // again once it is ready, then run ``then`` (styles need a live caret).
  function focusField(mf, then) {
    try { mf.focus(); } catch (e) { /* not mounted yet */ }
    requestAnimationFrame(function () {
      if (document.activeElement !== mf) { try { mf.focus(); } catch (e) { /* ignore */ } }
      if (then) then();
    });
  }

  // A palette snippet in MathLive's insert syntax: empty {} become tab-able
  // blanks (#?), the caret marker becomes the selection slot (#0).
  function toML(snippet, caretMark) {
    return snippet.replace(/\{\}/g, '{#?}').split(caretMark).join('#0');
  }

  // ---- enhance --------------------------------------------------------------
  function labelFor(field) {
    var l = field.id && document.querySelector('label[for="' + field.id + '"]');
    return field.getAttribute('aria-label') || (l && l.textContent.replace('*', '').trim()) || field.placeholder || 'Text';
  }

  function enhance(field) {
    if (!field || field.mrEditor) return field && field.mrEditor;
    var multi = field.tagName === 'TEXTAREA';
    var ed = document.createElement('div');
    ed.className = 'mr-edit ' + (multi ? 'mr-multi' : 'mr-single');
    ed.contentEditable = 'true';
    ed.spellcheck = true;
    ed.setAttribute('role', 'textbox');
    ed.setAttribute('aria-multiline', multi ? 'true' : 'false');
    ed.setAttribute('aria-label', labelFor(field));
    ed.dataset.placeholder = field.placeholder || '';
    ed._mrMulti = multi;
    ed.mrField = field;
    field.mrEditor = ed;
    if (field.hasAttribute('data-math-target')) ed.setAttribute('data-mr-target', field.getAttribute('data-math-target'));
    if (field.required) { field.required = false; field.dataset.mrRequired = '1'; }
    field.insertAdjacentElement('afterend', ed);
    field.classList.add('mr-hidden');
    var lbl = field.id && document.querySelector('label[for="' + field.id + '"]');
    if (lbl) lbl.addEventListener('click', function (e) { if (isVisual(field)) { e.preventDefault(); ed.focus(); } });

    ed.addEventListener('input', function () { saveRange(ed); sync(ed); });
    ed.addEventListener('keyup', function (ev) { if (ev.target === ed) { ed._mrChip = null; saveRange(ed); } });
    ed.addEventListener('mouseup', function (ev) { if (ev.target === ed || !(ev.target.closest && ev.target.closest('.mr-chip'))) { ed._mrChip = null; saveRange(ed); } });
    ed.addEventListener('focus', function () { saveRange(ed); });
    // Tapping/clicking a formula hands it the whole interaction: the outer
    // text box stops being editable until the formula loses focus, so no
    // browser can steal the tap or the caret from the formula.
    ed.addEventListener('pointerdown', function (ev) {
      var chip = ev.target.closest && ev.target.closest('.mr-chip');
      if (!chip) {
        // Back in the text: make it editable before the browser places the caret.
        var act = document.activeElement;
        var inFormula = act && act.tagName === 'MATH-FIELD' && ed.contains(act);
        if (ed.contentEditable !== 'true' || inFormula) {
          ed.contentEditable = 'true';
          var mfOpen = inFormula ? act : ed.querySelector('.mr-chip.is-editing math-field');
          if (mfOpen) { try { mfOpen.blur(); } catch (e) { /* ignore */ } }
          if (window.mathVirtualKeyboard) { try { window.mathVirtualKeyboard.hide(); } catch (e) { /* ignore */ } }
          // Touch browsers decide focus before we unlock the text: put the
          // caret where the finger landed ourselves if they didn't.
          var x = ev.clientX, y = ev.clientY;
          setTimeout(function () {
            if (document.activeElement === ed) return;
            ed.focus();
            var r = document.caretRangeFromPoint ? document.caretRangeFromPoint(x, y) : null;
            if (!r && document.caretPositionFromPoint) {
              var cp = document.caretPositionFromPoint(x, y);
              if (cp) { r = document.createRange(); r.setStart(cp.offsetNode, cp.offset); }
            }
            if (!r || !ed.contains(r.startContainer)) { r = document.createRange(); r.selectNodeContents(ed); r.collapse(false); }
            r.collapse(true);
            var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
            ed._mrRange = r.cloneRange();
          }, 0);
        }
        return;
      }
      if (ev.target.closest && ev.target.closest('.mr-chip-x')) return;
      if (PANEL) return;                         // opens the Edit formula panel on click
      ed.contentEditable = 'false';
      var mf = chip.querySelector('math-field');
      setTimeout(function () { if (document.activeElement !== mf) { try { mf.focus(); } catch (e) { /* ignore */ } } }, 0);
    }, true);

    // Phone keyboards (Android especially) don't send Backspace/Delete key
    // events, only "beforeinput" — remove a neighbouring formula there too.
    ed.addEventListener('beforeinput', function (ev) {
      if (ev.target !== ed) return;
      var t = ev.inputType;
      if (t !== 'deleteContentBackward' && t !== 'deleteContentForward' &&
          t !== 'deleteWordBackward' && t !== 'deleteWordForward') return;
      var c = chipBeside(ed, /Backward$/.test(t) ? -1 : 1);
      if (c) { ev.preventDefault(); removeChip(ed, c, true); }
    });

    ed.addEventListener('keydown', function (ev) {
      if (ev.target !== ed) return;              // keys inside a formula belong to it
      if (ev.key === 'Backspace' || ev.key === 'Delete') {
        var c = chipBeside(ed, ev.key === 'Backspace' ? -1 : 1);
        if (c) { ev.preventDefault(); removeChip(ed, c, true); return; }
      }
      if (ev.key === 'Enter') {
        if ((ev.ctrlKey || ev.metaKey)) return;  // form shortcut (Ctrl+Enter = add)
        ev.preventDefault();
        if (multi) { document.execCommand('insertLineBreak'); saveRange(ed); sync(ed); }
        return;
      }
      if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'm' || ev.key === 'M')) {
        ev.preventDefault();
        var res = insertChipAt(ed, '');
        if (PANEL) openSheet(ed, res.chip, true); else focusField(res.mf);
        return;
      }
      if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') {
        var sel = window.getSelection();
        if (!sel.rangeCount || !sel.isCollapsed) return;
        var r = sel.getRangeAt(0), n = r.startContainer, o = r.startOffset;
        var right = ev.key === 'ArrowRight', chip = null;
        if (n.nodeType === 3) {
          var rest = right ? n.nodeValue.slice(o).replace(/​/g, '') : n.nodeValue.slice(0, o).replace(/​/g, '');
          if (!rest) chip = right ? n.nextSibling : n.previousSibling;
        } else {
          chip = right ? n.childNodes[o] : n.childNodes[o - 1];
        }
        if (chip && chip.classList && chip.classList.contains('mr-chip')) {
          ev.preventDefault();
          var mf = chip.querySelector('math-field');
          mf.focus();
          try { mf.position = right ? 0 : mf.lastOffset; } catch (e) { /* ignore */ }
        }
      }
    });
    ed.addEventListener('paste', function (ev) {
      if (ev.target !== ed && !ed.contains(ev.target)) return;
      if (ev.target && ev.target.closest && ev.target.closest('.mr-chip')) return;  // formula handles it
      var cd = ev.clipboardData;
      if (!cd) return;
      if (cd.files && cd.files.length) return;   // images go to the figure upload
      ev.preventDefault();
      var t = cd.getData('text/plain') || '';
      if (!multi) t = t.replace(/\s*\n\s*/g, ' ');
      saveRange(ed); insertParts(ed, t);
    });
    ed.addEventListener('drop', function (ev) {
      if (ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files.length) return;
      ev.preventDefault();
    });

    if (field.form && !field.form.dataset.mrSubmit) {
      field.form.dataset.mrSubmit = '1';
      field.form.addEventListener('submit', function (ev) {
        var bad = null;
        field.form.querySelectorAll('[data-mr-required]').forEach(function (f) {
          if (f.mrEditor) sync(f.mrEditor);
          if (isVisual(f) && !f.value.trim() && !bad) bad = f;
        });
        if (bad) {
          ev.preventDefault(); ev.stopImmediatePropagation();
          bad.mrEditor.classList.add('is-invalid');
          bad.mrEditor.focus();
        }
      }, true);
      field.form.addEventListener('reset', function () {
        setTimeout(function () {
          field.form.querySelectorAll('.mr-hidden').forEach(function (f) { if (f.mrEditor) fill(f.mrEditor, f.value); });
        }, 0);
      });
    }

    fill(ed, field.value);
    return ed;
  }

  function isVisual(field) { return !!(field && field.mrEditor && !field.mrEditor.hidden); }

  function setVisual(field, on) {
    var ed = field && field.mrEditor;
    if (!ed) return;
    if (on) {
      fill(ed, field.value);
      ed.hidden = false; field.classList.add('mr-hidden');
      if (field.dataset.mrRequired) field.required = false;
    } else {
      sync(ed);
      ed.hidden = true; field.classList.remove('mr-hidden');
      if (field.dataset.mrRequired) field.required = true;
    }
  }

  function insert(field, item, caretMark, opts) {
    var ed = field.mrEditor;
    opts = opts || {};
    if (PANEL) { insertTouch(ed, item, caretMark); return; }
    var mf = activeChipField(ed);
    if (item.type === 'sym') {
      if (mf) { mf.executeCommand(['insert', item.insert]); mf.focus(); }
      else insertText(ed, item.insert);
      return;
    }
    var uprightSlot = item.insert === '\\mathrm{' + caretMark + '}';
    var snip = toML(item.insert, caretMark), selected = '';
    if (!mf) {
      var res = insertChipAt(ed, '');
      mf = res.mf;
      selected = res.selected;
      if (selected) snip = snip.indexOf('#0') > -1 ? snip.replace('#0', selected) : snip + selected;
    }
    var chip = mf.closest('.mr-chip');
    if (uprightSlot) {
      // "Chemical formula": an upright-letter formula box (H₂O, not italic).
      focusField(mf, function () {
        try { mf.applyStyle({ variantStyle: 'up' }); } catch (e) { /* older API */ }
        if (selected) mf.executeCommand(['insert', selected]);
        if (chip) chip.dataset.latex = chipLatex(chip);
        sync(ed);
      });
      return;
    }
    if (snip.replace('#0', '')) {
      mf.executeCommand(['insert', snip, { insertionMode: 'replaceSelection', selectionMode: 'placeholder' }]);
    }
    focusField(mf);
    if (chip) chip.dataset.latex = chipLatex(chip);
    sync(ed);
  }

  function insertTouch(ed, item, caretMark) {
    var upright = item.insert === '\\mathrm{' + caretMark + '}';
    var snip = toML(item.insert, caretMark);
    function put(mf) {
      if (upright) { try { mf.applyStyle({ variantStyle: 'up' }); } catch (e) { /* ignore */ } return; }
      if (item.type === 'sym') mf.executeCommand(['insert', item.insert]);
      else if (snip.replace('#0', '')) mf.executeCommand(['insert', snip, { insertionMode: 'replaceSelection', selectionMode: 'placeholder' }]);
    }
    if (sheet && !sheet.hidden) { put(sheet.mf); sheet.mf.focus(); return; }   // the formula being edited
    if (item.type === 'sym') { insertText(ed, item.insert); return; }
    var res = insertChipAt(ed, '');
    if (res.selected) snip = snip.indexOf('#0') > -1 ? snip.replace('#0', res.selected) : snip + res.selected;
    openSheet(ed, res.chip, true, put);
  }

  function refresh(field) { if (field && field.mrEditor) fill(field.mrEditor, field.value); }

  window.MathRich = {
    get ready() { return load(); },
    enhance: enhance, setVisual: setVisual, isVisual: isVisual,
    insert: insert, refresh: refresh, parse: parse,
    serialize: function (field) { return field.mrEditor ? serialize(field.mrEditor) : field.value; }
  };
})();
