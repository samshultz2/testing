import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

// The broadsheet export dialog: every option on the left, the real document on
// the right (page N rendered by the server), re-rendered as options change. On
// phones the preview is a row that opens full screen.
const PREF = 'bsExportPrefs';
const FORMATS = [
  { v: 'pdf', l: 'PDF', i: 'fa-file-pdf' }, { v: 'image', l: 'Image', i: 'fa-file-image' },
  { v: 'word', l: 'Word', i: 'fa-file-word' }, { v: 'excel', l: 'Excel', i: 'fa-file-excel' },
];

function loadPrefs(options) {
  const base = { format: 'pdf', theme: 'aurora', style: 'colour', paper: 'A4', orient: 'landscape', size: 'm', sort: 'position' };
  options.forEach((o) => { base[o.key] = o.on; });
  try { return { ...base, ...(JSON.parse(localStorage.getItem(PREF) || '{}')) }; } catch (_) { return base; }
}

function Seg({ value, onChange, options, label }) {
  return (
    <div className="bxe-seg" role="radiogroup" aria-label={label}>
      {options.map(([v, l]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? 'on' : ''} onClick={() => onChange(v)}>{l}</button>))}
    </div>
  );
}

export default function BroadsheetExport({ url, options, filter, rowsShown, onClose }) {
  const [o, setO] = useState(() => loadPrefs(options));
  const [pv, setPv] = useState({ page: 1, total: 1, src: '', loading: true, error: '' });
  const [full, setFull] = useState(false);
  const [zoom, setZoom] = useState(false);
  const urlRef = useRef('');
  const set = (k, v) => setO((x) => { const n = { ...x, [k]: v }; try { localStorage.setItem(PREF, JSON.stringify(n)); } catch (_) { /* ignore */ } return n; });

  const query = (format, extra = {}) => {
    const q = new URLSearchParams();
    q.set('format', format);
    ['theme', 'style', 'paper', 'orient', 'size', 'sort'].forEach((k) => q.set(k, o[k]));
    options.forEach((op) => q.set(op.key, o[op.key] ? '1' : '0'));
    if (filter) { q.set('min_score', filter.min); q.set('filter_field', filter.field); }
    Object.entries(extra).forEach(([k, v]) => q.set(k, v));
    return url + (url.includes('?') ? '&' : '?') + q.toString();
  };

  // Debounced preview render.
  const optsKey = JSON.stringify(o);
  useEffect(() => { setPv((p) => ({ ...p, page: 1 })); }, [optsKey]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let live = true;
    setPv((p) => ({ ...p, loading: true, error: '' }));
    const t = setTimeout(async () => {
      try {
        const r = await fetch(query('image', { preview: '1', page: String(pv.page) }), { credentials: 'same-origin' });
        if (!r.ok) throw new Error(String(r.status));
        const total = parseInt(r.headers.get('X-Total-Pages') || '1', 10) || 1;
        const blob = await r.blob();
        if (!live) return;
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = URL.createObjectURL(blob);
        setPv((p) => ({ ...p, total, src: urlRef.current, loading: false }));
      } catch (e) {
        if (live) setPv((p) => ({ ...p, loading: false, error: 'Preview unavailable — the download will still work.' }));
      }
    }, 380);
    return () => { live = false; clearTimeout(t); };
  }, [optsKey, pv.page]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); }, []);
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') { if (full) setFull(false); else onClose(); } };
    document.addEventListener('keydown', esc);
    const prev = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', esc); document.body.style.overflow = prev; };
  }, [full]); // eslint-disable-line react-hooks/exhaustive-deps

  const download = () => { window.location.href = query(o.format === 'excel' ? 'excel' : o.format); };
  const group = (g) => options.filter((op) => op.group === g);
  const fmtNote = {
    pdf: 'Ready to print. Long classes run onto more pages with the headings repeated.',
    image: pv.total > 1 ? `Downloads ${pv.total} PNG pages in a zip.` : 'Downloads one sharp PNG — good for WhatsApp.',
    word: 'An editable Word document with the same table.',
    excel: 'A spreadsheet with the same columns, highlights and statistics rows.',
  }[o.format];

  const preview = (
    <section className={'bxe-pv' + (full ? ' full' : '')} aria-label="Live preview">
      <div className="bxe-pv-h">
        {full && <button type="button" className="bxe-back" onClick={() => setFull(false)} aria-label="Back to options"><i className="fas fa-arrow-left" aria-hidden="true" /></button>}
        <b>Live preview</b>
        <span className="bxe-nav">
          <button type="button" disabled={pv.page <= 1} onClick={() => setPv((p) => ({ ...p, page: p.page - 1 }))} aria-label="Previous page"><i className="fas fa-chevron-left" aria-hidden="true" /></button>
          <span aria-live="polite">Page {pv.page} of {pv.total}</span>
          <button type="button" disabled={pv.page >= pv.total} onClick={() => setPv((p) => ({ ...p, page: p.page + 1 }))} aria-label="Next page"><i className="fas fa-chevron-right" aria-hidden="true" /></button>
        </span>
      </div>
      <div className="bxe-stage">
        {pv.src && <img src={pv.src} alt={`Preview of page ${pv.page} of ${pv.total}`} title={zoom ? 'Tap to fit' : 'Tap to zoom'}
                        className={(pv.loading ? 'dim' : '') + (zoom ? ' zoom' : '')} onClick={() => setZoom((z) => !z)} />}
        {(pv.loading || pv.error) && <div className="bxe-msg">{pv.error || <><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Rendering preview…</>}</div>}
      </div>
      <p className="bxe-foot">{o.format === 'excel' || o.format === 'word' ? 'Shown as the PDF layout; ' + fmtNote.charAt(0).toLowerCase() + fmtNote.slice(1) : fmtNote}</p>
    </section>
  );

  return createPortal(
    <div className="bxe-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bxe" role="dialog" aria-modal="true" aria-label="Export broadsheet">
        <div className="bxe-h"><strong><i className="fas fa-file-export" aria-hidden="true" /> Export broadsheet</strong>
          <button type="button" className="bxe-x" onClick={onClose} aria-label="Close"><i className="fas fa-xmark" aria-hidden="true" /></button></div>
        <div className="bxe-cols">
          <div className="bxe-opts">
            {filter && <p className="bxe-note"><i className="fas fa-filter" aria-hidden="true" /> Only the {rowsShown} students matching your filter ({filter.label}) are exported.</p>}
            <div className="bxe-l">Format</div>
            <div className="bxe-fmt">
              {FORMATS.map((f) => (
                <button key={f.v} type="button" className={o.format === f.v ? 'on' : ''} aria-pressed={o.format === f.v} onClick={() => set('format', f.v)}>
                  <i className={'fas ' + f.i} aria-hidden="true" />{f.l}</button>))}
            </div>
            <button type="button" className="bxe-pvbar" onClick={() => setFull(true)}>
              <span><b>Preview</b><small>Page {pv.page} of {pv.total}</small></span><span className="go">Open <i className="fas fa-chevron-right" aria-hidden="true" /></span></button>
            {o.style !== 'bw' && (
              <>
                <div className="bxe-l">Design</div>
                <div className="bxe-themes" role="radiogroup" aria-label="Design">
                  {[['aurora', 'Aurora', 'Dark header band, heat-mapped scores'], ['minimal', 'Minimal', 'Light and quiet, red marks only']].map(([v, l, d]) => (
                    <button key={v} type="button" role="radio" aria-checked={o.theme === v} className={'bxe-theme ' + v + (o.theme === v ? ' on' : '')} onClick={() => set('theme', v)}>
                      <span className="sw" aria-hidden="true"><i /><b /><b /><b /></span><strong>{l}</strong><small>{d}</small></button>))}
                </div>
              </>)}
            <div className="bxe-row">
              <div><div className="bxe-l">Style</div><Seg label="Style" value={o.style} onChange={(v) => set('style', v)} options={[['colour', 'Colour'], ['bw', 'Black & white']]} /></div>
              <div><div className="bxe-l">Text size</div><Seg label="Text size" value={o.size} onChange={(v) => set('size', v)} options={[['s', 'S'], ['m', 'M'], ['l', 'L']]} /></div>
            </div>
            {o.format !== 'excel' && (
              <div className="bxe-row">
                <div><div className="bxe-l">Paper</div><Seg label="Paper" value={o.paper} onChange={(v) => set('paper', v)} options={[['A4', 'A4'], ['A3', 'A3']]} /></div>
                <div><div className="bxe-l">Orientation</div><Seg label="Orientation" value={o.orient} onChange={(v) => set('orient', v)} options={[['landscape', 'Landscape'], ['portrait', 'Portrait']]} /></div>
              </div>)}
            <div className="bxe-l">Order students</div>
            <Seg label="Order" value={o.sort} onChange={(v) => set('sort', v)} options={[['position', 'By position'], ['name', 'A–Z'], ['gender', 'Boys, then girls']]} />
            <div className="bxe-l">Columns <small>(every subject is always included)</small></div>
            <div className="bxe-checks">
              {group('columns').map((op) => (
                <label key={op.key} className="bxe-ck"><input type="checkbox" checked={!!o[op.key]} onChange={(e) => set(op.key, e.target.checked)} /><span>{op.label}</span></label>))}
            </div>
            <div className="bxe-l">On the page</div>
            <div className="bxe-checks">
              {group('blocks').map((op) => (
                <label key={op.key} className="bxe-ck"><input type="checkbox" checked={!!o[op.key]} onChange={(e) => set(op.key, e.target.checked)} /><span>{op.label}</span></label>))}
            </div>
          </div>
          {preview}
        </div>
        <div className="bxe-act">
          <button type="button" className="rs-btn" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" onClick={download}><i className="fas fa-download" aria-hidden="true" />Download {FORMATS.find((f) => f.v === o.format).l}</button>
        </div>
      </div>
    </div>, document.body);
}
