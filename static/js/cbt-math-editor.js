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
  function makeChip(latex, display) {
    var wrap = document.createElement('span');
    wrap.className = 'mr-chip';
    wrap.contentEditable = 'false';
    wrap.dataset.latex = latex || '';
    if (display) wrap.dataset.display = '1';
    var mf = new window.MathfieldElement();
    mf.mathVirtualKeyboardPolicy = 'manual';
    mf.smartMode = false;
    mf.setAttribute('aria-label', 'Formula');
    wrap.appendChild(mf);
    return wrap;
  }

  function initChip(ed, chip) {
    var mf = chip.querySelector('math-field');
    if (!mf || mf.dataset.mrInit) return mf;
    mf.dataset.mrInit = '1';
    try { mf.value = chip.dataset.latex || ''; } catch (e) { /* keep empty */ }
    mf.addEventListener('input', function () { chip.dataset.latex = chipLatex(chip); sync(ed); });
    mf.addEventListener('focus', function () { ed._mrChip = chip; });
    mf.addEventListener('focusout', function () {
      // An emptied formula disappears instead of leaving a blank box.
      setTimeout(function () {
        if (!chip.isConnected || mf.contains(document.activeElement) || document.activeElement === mf) return;
        if (!chipLatex(chip)) { chip.remove(); tidy(ed); sync(ed); }
      }, 0);
    });
    mf.addEventListener('move-out', function (ev) {
      var d = ev.detail && ev.detail.direction;
      if (d === 'forward' || d === 'backward') { ev.preventDefault(); caretBeside(ed, chip, d === 'forward'); }
    });
    mf.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' || (ev.key === 'Enter' && !ev.shiftKey)) {
        ev.preventDefault(); ev.stopPropagation(); caretBeside(ed, chip, true);
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
    ed.addEventListener('keydown', function (ev) {
      if (ev.target !== ed) return;              // keys inside a formula belong to it
      if (ev.key === 'Enter') {
        if ((ev.ctrlKey || ev.metaKey)) return;  // form shortcut (Ctrl+Enter = add)
        ev.preventDefault();
        if (multi) { document.execCommand('insertLineBreak'); saveRange(ed); sync(ed); }
        return;
      }
      if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'm' || ev.key === 'M')) {
        ev.preventDefault();
        var res = insertChipAt(ed, ''); focusField(res.mf); return;
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

  function refresh(field) { if (field && field.mrEditor) fill(field.mrEditor, field.value); }

  window.MathRich = {
    get ready() { return load(); },
    enhance: enhance, setVisual: setVisual, isVisual: isVisual,
    insert: insert, refresh: refresh, parse: parse,
    serialize: function (field) { return field.mrEditor ? serialize(field.mrEditor) : field.value; }
  };
})();
