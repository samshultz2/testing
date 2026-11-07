import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Modal } from '../components/ui';

// Students → Export. Colours come entirely from the active theme's CSS
// variables (see .sx-* in templates/students/list.html), so the dialog follows
// whichever theme the user picked. The document itself is built server-side
// (utils/student_list_export.py); the preview is page 1 of that document.

const LABELS = {
  student_id: 'Student ID', name: 'Name', middle_name: 'Middle name', photo: 'Photo',
  gender: 'Gender', date_of_birth: 'Date of birth', age: 'Age', religion: 'Religion', hobbies: 'Hobbies',
  current_class: 'Class', parent_phone: 'Parent phone', home_address: 'Home address',
  nin: 'NIN', jamb_reg_number: 'JAMB reg.', jamb_profile_code: 'JAMB profile',
  waec_reg_number: 'WAEC reg.', neco_reg_number: 'NECO reg.',
};
const GROUPS = [
  ['Identity', ['student_id', 'name', 'middle_name', 'photo']],
  ['Personal', ['gender', 'date_of_birth', 'age', 'religion', 'hobbies']],
  ['Class & contact', ['current_class', 'parent_phone', 'home_address']],
  ['Exam numbers', ['nin', 'jamb_reg_number', 'jamb_profile_code', 'waec_reg_number', 'neco_reg_number']],
];
const ALL = GROUPS.flatMap(([, ks]) => ks);
const PRESETS = [
  ['class', 'Class list', 'fa-list-ul', ['student_id', 'name', 'gender', 'current_class', 'parent_phone']],
  ['contact', 'Contact list', 'fa-phone', ['name', 'current_class', 'parent_phone', 'home_address']],
  ['exam', 'Exam numbers', 'fa-id-card', ['student_id', 'name', 'gender', 'date_of_birth', 'nin', 'jamb_reg_number', 'waec_reg_number', 'neco_reg_number']],
  ['all', 'Everything', 'fa-table-cells', ALL.filter((k) => k !== 'middle_name' && k !== 'photo')],
];
const FORMATS = [
  ['pdf', 'PDF', 'fa-file-pdf', 'Print-ready A4, with letterhead', 'sx-fi-pdf'],
  ['excel', 'Excel', 'fa-file-excel', 'Sort, filter & edit the data', 'sx-fi-xls'],
  ['word', 'Word', 'fa-file-word', 'Editable document', 'sx-fi-doc'],
  ['image', 'Image', 'fa-image', 'Share on WhatsApp', 'sx-fi-img'],
];
const SAVED_KEY = 'stu.export.presets';
const loadSaved = () => { try { return JSON.parse(localStorage.getItem(SAVED_KEY) || '[]') || []; } catch (e) { return []; } };
const storeSaved = (v) => { try { localStorage.setItem(SAVED_KEY, JSON.stringify(v)); } catch (e) { /* private mode */ } };
const TOUCH = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(pointer: coarse)').matches;

function Seg({ value, options, onChange, label }) {
  return (
    <div className="sx-seg" role="radiogroup" aria-label={label}>
      {options.map(([v, l]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v}
                className={value === v ? 'on' : ''} onClick={() => onChange(v)}>{l}</button>
      ))}
    </div>
  );
}

function Toggle({ on, onChange, children }) {
  return (
    <label className="sx-tog">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
      <span className="sx-sw" aria-hidden="true" />{children}
    </label>
  );
}

export default function ExportModal({ total, selectedIds, exportUrl, applied, filterText, onClose }) {
  const [scope, setScope] = useState(selectedIds.length ? 'selected' : 'all');
  const [fields, setFields] = useState(PRESETS[0][3]);
  const [preset, setPreset] = useState('class');
  const [saved, setSaved] = useState(loadSaved);
  const [naming, setNaming] = useState(null);
  const [format, setFormat] = useState('pdf');
  const [orientation, setOrientation] = useState('auto');
  const [size, setSize] = useState('m');
  const [group, setGroup] = useState(true);
  const [summary, setSummary] = useState(true);
  const [signatures, setSignatures] = useState(false);
  const [blank, setBlank] = useState(false);
  const [title, setTitle] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [pv, setPv] = useState({ url: '', pages: 1, page: 1, loading: true, error: false, title: '', subtitle: '', orient: 'portrait' });
  const [showPv, setShowPv] = useState(false);
  const dragFrom = useRef(null);
  const count = scope === 'selected' ? selectedIds.length : total;
  const docLike = format !== 'excel' && format !== 'csv';

  const params = useMemo(() => {
    const p = new URLSearchParams();
    p.set('fields', JSON.stringify(fields));
    p.set('preset', ['class', 'contact', 'exam', 'all'].includes(preset) ? preset : '');
    p.set('orientation', orientation); p.set('size', size);
    p.set('group', group ? '1' : '0'); p.set('summary', summary ? '1' : '0');
    p.set('signatures', signatures ? '1' : '0'); p.set('blank', blank ? '3' : '0');
    if (title.trim()) p.set('title', title.trim());
    if (subtitle.trim()) p.set('subtitle', subtitle.trim());
    if (scope === 'selected' && selectedIds.length) p.set('student_ids', JSON.stringify(selectedIds));
    else Object.entries(applied || {}).forEach(([k, v]) => { if (v) p.set(k, v); });
    return p;
  }, [fields, preset, orientation, size, group, summary, signatures, blank, title, subtitle, scope, selectedIds, applied]);

  // Live preview: page N of the real document, re-rendered (debounced) on change.
  useEffect(() => {
    if (!fields.length) return undefined;
    let cancelled = false; let objUrl = '';
    setPv((s) => ({ ...s, loading: true, error: false }));
    const t = setTimeout(async () => {
      try {
        const q = new URLSearchParams(params); q.set('format', 'image'); q.set('preview', '1'); q.set('page', String(pv.page));
        const res = await fetch(`${exportUrl}?${q.toString()}`, { credentials: 'same-origin' });
        if (res.status === 422) { if (!cancelled) setPv((s) => ({ ...s, loading: false, error: 'empty', url: '' })); return; }
        if (!res.ok || !(res.headers.get('Content-Type') || '').startsWith('image/')) throw new Error(String(res.status));
        const blob = await res.blob();
        if (cancelled) return;
        objUrl = URL.createObjectURL(blob);
        const dec = (h) => { try { return decodeURIComponent(res.headers.get(h) || ''); } catch (e) { return ''; } };
        setPv((s) => {
          if (s.url) URL.revokeObjectURL(s.url);
          return { ...s, url: objUrl, loading: false, pages: parseInt(res.headers.get('X-Total-Pages') || '1', 10) || 1,
                   title: dec('X-Export-Title'), subtitle: dec('X-Export-Subtitle'),
                   orient: res.headers.get('X-Export-Orientation') || 'portrait' };
        });
      } catch (e) {
        if (!cancelled) setPv((s) => ({ ...s, loading: false, error: true }));
      }
    }, 450);
    return () => { cancelled = true; clearTimeout(t); };
  }, [params, pv.page, exportUrl]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { if (pv.url) URL.revokeObjectURL(pv.url); }, []);   // eslint-disable-line

  const choosePreset = (key, flds, orient) => {
    setPreset(key); setFields(flds);
    if (orient) setOrientation(orient);
    setPv((s) => ({ ...s, page: 1 }));
  };
  const toggle = (k) => {
    setPreset('custom');
    setFields((f) => (f.includes(k) ? f.filter((x) => x !== k) : [...f, k]));
  };
  const move = (from, to) => {
    if (to < 0 || to >= fields.length || from === to) return;
    setPreset((p) => (p.startsWith('saved:') || p === 'custom' ? p : 'custom'));
    setFields((f) => { const n = [...f]; const [x] = n.splice(from, 1); n.splice(to, 0, x); return n; });
  };
  const saveCurrent = () => {
    const name = (naming || '').trim();
    if (!name) return;
    const next = [...saved.filter((s) => s.name !== name), { name, fields, orientation }].slice(-6);
    setSaved(next); storeSaved(next); setNaming(null); setPreset('saved:' + name);
  };
  const removeSaved = (name) => {
    const next = saved.filter((s) => s.name !== name);
    setSaved(next); storeSaved(next);
    if (preset === 'saved:' + name) setPreset('custom');
  };

  const saveBlob = (blob, name) => {
    const u = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = u; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 4000);
  };
  const download = async () => {
    if (!fields.length) return;
    const q = new URLSearchParams(params); q.set('format', format);
    const url = `${exportUrl}?${q.toString()}`;
    if (format === 'image') {
      const base = (pv.title || 'students').replace(/[^A-Za-z0-9]+/g, '_');
      let page = 1, pages = 1;
      do {
        const res = await fetch(url + '&page=' + page, { credentials: 'same-origin' });
        if (!res.ok) break;
        pages = parseInt(res.headers.get('X-Total-Pages') || '1', 10) || 1;
        saveBlob(await res.blob(), pages > 1 ? `${base}_p${page}.png` : `${base}.png`);
        page += 1;
      } while (page <= pages);
    } else {
      window.location.href = url;
    }
    onClose();
  };

  const fmtLabel = format === 'csv' ? 'CSV' : FORMATS.find((f) => f[0] === format)[1];
  const header = (
    <div className="sx-hd">
      <div className="sx-hd-ic" aria-hidden="true"><i className="fas fa-file-export" /></div>
      <div className="sx-hd-t">
        <h3 id="sx-title">Export students</h3>
        <div className="sx-hd-s">{count} student{count === 1 ? '' : 's'} {scope === 'selected' ? 'selected' : 'match your filters'}{filterText ? ' — ' + filterText : ''}</div>
      </div>
      <button type="button" className="sx-x" onClick={onClose} aria-label="Close"><i className="fas fa-xmark" aria-hidden="true" /></button>
    </div>
  );

  const previewPane = (
    <div className="sx-pv">
      <div className="sx-pv-h"><b>Live preview</b>
        {docLike && <span>Page {pv.page} of {pv.pages}</span>}</div>
      {docLike ? (
        <div className={'sx-paper' + (pv.orient === 'landscape' ? ' land' : '')} aria-busy={pv.loading}>
          {pv.url && <img src={pv.url} alt={`Preview of page ${pv.page}`} />}
          {pv.loading && <div className="sx-pv-load"><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Updating…</div>}
          {pv.error === 'empty' && !pv.loading && <div className="sx-pv-empty"><i className="fas fa-user-slash" aria-hidden="true" /> No students match these filters.</div>}
          {pv.error && pv.error !== 'empty' && !pv.loading && <div className="sx-pv-load">Preview unavailable — the export will still work.</div>}
        </div>
      ) : (
        <div className="sx-sheet" aria-label="Spreadsheet columns">
          <div className="sx-sheet-row sx-sheet-h">
            <span>#</span>{fields.flatMap((k) => (k === 'name' ? ['Surname', 'Other names'] : [LABELS[k]])).map((l) => <span key={l}>{l}</span>)}
          </div>
          {[1, 2, 3, 4, 5].map((i) => (
            <div className="sx-sheet-row" key={i}><span>{i}</span>{fields.flatMap((k) => (k === 'name' ? [k + 's', k + 'r'] : [k])).map((k) => <span key={k}><i /></span>)}</div>
          ))}
          <p className="sx-note"><i className="fas fa-filter" aria-hidden="true" /> {format === 'csv' ? 'Plain data, one row per student.' : 'One filterable table with a frozen header, plus Summary and About sheets.'}</p>
        </div>
      )}
      {docLike && pv.pages > 1 && (
        <div className="sx-pages">
          <button type="button" aria-label="Previous page" disabled={pv.page <= 1} onClick={() => setPv((s) => ({ ...s, page: s.page - 1 }))}><i className="fas fa-chevron-left" /></button>
          {Array.from({ length: Math.min(pv.pages, 8) }, (_, i) => <i key={i} className={i + 1 === pv.page ? 'on' : ''} />)}
          <button type="button" aria-label="Next page" disabled={pv.page >= pv.pages} onClick={() => setPv((s) => ({ ...s, page: s.page + 1 }))}><i className="fas fa-chevron-right" /></button>
        </div>
      )}
      <div className="sx-note"><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Your school’s logo, name and colours are added automatically. Change them in <b>Settings → School profile</b>.</div>
    </div>
  );

  return (
    <Modal onClose={onClose} bare size="xxl" ariaLabel="Export students"
           className="sx-dlg" backdropClassName="sx-backdrop">
      {header}
      <div className="sx-main">
        <div className="sx-left">
          <section className="sx-sec">
            <div className="sx-st"><span className="sx-n">1</span><b>Who to include</b></div>
            <Seg label="Who to include" value={scope} onChange={setScope}
                 options={[['all', <>All matching <span className="sx-c">{total}</span></>],
                           ...(selectedIds.length ? [['selected', <>Selected rows <span className="sx-c">{selectedIds.length}</span></>]] : [])]} />
            {!selectedIds.length && <span className="sx-hint">Tick rows in the list to export only those.</span>}
          </section>

          <section className="sx-sec">
            <div className="sx-st"><span className="sx-n">2</span><b>Columns</b>
              <span className="sx-hint sx-r">{fields.length} selected · {TOUCH ? 'use ‹ › to reorder' : 'drag to reorder'}</span></div>
            <div className="sx-presets" role="group" aria-label="Column presets">
              {PRESETS.map(([k, l, ic, f]) => (
                <button key={k} type="button" className={'sx-preset' + (preset === k ? ' on' : '')} aria-pressed={preset === k}
                        onClick={() => choosePreset(k, f, k === 'exam' ? 'auto' : null)}><i className={'fas ' + ic} aria-hidden="true" /> {l}</button>
              ))}
              {saved.map((s) => (
                <span key={s.name} className={'sx-preset sx-saved' + (preset === 'saved:' + s.name ? ' on' : '')}>
                  <button type="button" onClick={() => choosePreset('saved:' + s.name, s.fields.filter((k) => LABELS[k]), s.orientation)}>
                    <i className="fas fa-bookmark" aria-hidden="true" /> {s.name}</button>
                  <button type="button" className="sx-del" aria-label={`Delete saved set ${s.name}`} onClick={() => removeSaved(s.name)}><i className="fas fa-xmark" /></button>
                </span>
              ))}
              {naming === null ? (
                <button type="button" className="sx-preset sx-ghost" onClick={() => setNaming('')}><i className="fas fa-plus" aria-hidden="true" /> Save current</button>
              ) : (
                <span className="sx-name">
                  <input autoFocus value={naming} maxLength={24} placeholder="e.g. Bus list" aria-label="Name for this column set"
                         onChange={(e) => setNaming(e.target.value)}
                         onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); saveCurrent(); } if (e.key === 'Escape') { e.stopPropagation(); setNaming(null); } }} />
                  <button type="button" className="sx-ok" onClick={saveCurrent} disabled={!naming.trim()}>Save</button>
                </span>
              )}
            </div>
            <div className="sx-groups">
              {GROUPS.map(([g, keys]) => (
                <div className="sx-grp" key={g}>
                  <div className="sx-gl">{g}</div>
                  <div className="sx-pills">
                    {keys.map((k) => {
                      const on = fields.includes(k);
                      return (
                        <button key={k} type="button" className={'sx-pill' + (on ? ' on' : '')} aria-pressed={on} onClick={() => toggle(k)}>
                          {on && <i className="fas fa-check" aria-hidden="true" />}{LABELS[k]}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
            <div className="sx-order" aria-label="Column order">
              <span className="sx-lb">Order</span>
              <span className="sx-chip sx-fixed">#</span>
              {fields.map((k, i) => (
                <span key={k} className="sx-chip" draggable={!TOUCH} tabIndex={0}
                      aria-label={`${LABELS[k]}, position ${i + 1} of ${fields.length}. Use left and right arrow keys to move.`}
                      onDragStart={() => { dragFrom.current = i; }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => { e.preventDefault(); if (dragFrom.current != null) move(dragFrom.current, i); dragFrom.current = null; }}
                      onKeyDown={(e) => {
                        if (e.key === 'ArrowLeft') { e.preventDefault(); move(i, i - 1); }
                        if (e.key === 'ArrowRight') { e.preventDefault(); move(i, i + 1); }
                      }}>
                  {TOUCH ? <button type="button" aria-label={`Move ${LABELS[k]} left`} onClick={() => move(i, i - 1)}>‹</button>
                         : <i className="fas fa-grip-vertical" aria-hidden="true" />}
                  {LABELS[k]}
                  {TOUCH && <button type="button" aria-label={`Move ${LABELS[k]} right`} onClick={() => move(i, i + 1)}>›</button>}
                </span>
              ))}
              {!fields.length && <span className="sx-hint">Pick at least one column.</span>}
            </div>
          </section>

          <section className="sx-sec">
            <div className="sx-st"><span className="sx-n">3</span><b>Format</b>
              <button type="button" className={'sx-csv' + (format === 'csv' ? ' on' : '')} aria-pressed={format === 'csv'} onClick={() => setFormat('csv')}>or plain CSV</button></div>
            <div className="sx-formats" role="radiogroup" aria-label="Format">
              {FORMATS.map(([k, l, ic, d, cls]) => (
                <button key={k} type="button" role="radio" aria-checked={format === k} className={'sx-fmt' + (format === k ? ' on' : '')} onClick={() => setFormat(k)}>
                  <span className={'sx-fi ' + cls} aria-hidden="true"><i className={'fas ' + ic} /></span>
                  <span><b>{l}</b><small>{d}</small></span>
                </button>
              ))}
            </div>
          </section>

          <section className="sx-sec">
            <div className="sx-st"><span className="sx-n">4</span><b>Layout &amp; heading</b>
              {!docLike && <span className="sx-hint sx-r">Spreadsheets keep one table; class becomes a column.</span>}</div>
            <div className={'sx-lay' + (docLike ? '' : ' off')}>
              <span className="sx-k">Orientation</span>
              <Seg label="Orientation" value={orientation} onChange={setOrientation}
                   options={[['auto', orientation === 'auto' && docLike ? `Auto · ${pv.orient === 'landscape' ? 'Landscape' : 'Portrait'}` : 'Auto'], ['portrait', 'Portrait'], ['landscape', 'Landscape']]} />
              <span className="sx-k">Text size</span>
              <Seg label="Text size" value={size} onChange={setSize} options={[['s', 'S'], ['m', 'M'], ['l', 'L']]} />
            </div>
            <div className="sx-toggles">
              <Toggle on={group} onChange={setGroup}>Group by class</Toggle>
              <Toggle on={summary} onChange={setSummary}>Summary (boys / girls)</Toggle>
              {docLike && <Toggle on={signatures} onChange={setSignatures}>Signature lines</Toggle>}
              {docLike && <Toggle on={blank} onChange={setBlank}>Blank columns for marking</Toggle>}
            </div>
            <div className="sx-row2">
              <label className="sx-inp"><span>Title</span>
                <input value={title} maxLength={150} onChange={(e) => setTitle(e.target.value)} placeholder={pv.title || 'Automatic'} /></label>
              <label className="sx-inp"><span>Subtitle</span>
                <input value={subtitle} maxLength={200} onChange={(e) => setSubtitle(e.target.value)} placeholder={pv.subtitle || 'Automatic'} /></label>
            </div>
          </section>

          {/* Phone: preview collapses to a row that opens it full screen. */}
          <button type="button" className="sx-pvrow" onClick={() => setShowPv(true)}>
            {pv.url && docLike ? <img src={pv.url} alt="" /> : <span className="sx-pvrow-ic"><i className="fas fa-table" aria-hidden="true" /></span>}
            <span><b>{pv.title || 'Preview'}</b>{docLike ? `A4 ${pv.orient} · ${pv.pages} page${pv.pages === 1 ? '' : 's'}` : fmtLabel}</span>
            <span className="sx-go">Preview <i className="fas fa-chevron-right" aria-hidden="true" /></span>
          </button>
        </div>
        <aside className={'sx-right' + (showPv ? ' open' : '')}>
          {showPv && <button type="button" className="sx-pv-close" onClick={() => setShowPv(false)}><i className="fas fa-arrow-left" aria-hidden="true" /> Back to options</button>}
          {previewPane}
        </aside>
      </div>
      <div className="sx-ft">
        <div className="sx-sum" aria-live="polite">
          <span><b>{count}</b> students</span><span><b>{fields.length}</b> columns</span>
          <span>{fmtLabel}{docLike ? ` · A4 ${pv.orient}` : ''}</span>
          {docLike && <span>≈ <b>{pv.pages}</b> page{pv.pages === 1 ? '' : 's'}</span>}
        </div>
        <button type="button" className="btn btn-secondary sx-cancel" onClick={onClose}>Cancel</button>
        <button type="button" className="btn btn-primary sx-dl" onClick={download} disabled={!fields.length || !count}>
          <i className="fas fa-download" aria-hidden="true" /> Download {fmtLabel}
        </button>
      </div>
    </Modal>
  );
}
