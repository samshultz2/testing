// Shared bits for the Website Builder app: requests, toasts, toggles and the
// image picker every editor uses.
import React, { useState, useEffect, useRef, createContext, useContext } from 'react';
import { csrfToken } from '../lib/api';
import { submitJson } from '../lib/forms';
import { Sheet } from '../subjects/results';
import { copyText as copyToClipboard } from '../lib/clipboard';

export const Ctx = createContext({});
export const useWs = () => useContext(Ctx);

export { submitJson };

export async function postJson(url, body) {
  try {
    const res = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch', 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
    let j = {};
    try { j = await res.json(); } catch (e) { /* not json */ }
    return { status: res.status, ...j, ok: !!(res.ok && j.ok) };
  } catch (e) {
    return { ok: false, error: 'No connection — check your internet and try again.' };
  }
}

export async function postFiles(url, form) {
  try {
    const res = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch', Accept: 'application/json' },
      body: form,
    });
    let j = {};
    try { j = await res.json(); } catch (e) { /* not json */ }
    return { status: res.status, ...j, ok: !!(res.ok && j.ok) };
  } catch (e) {
    return { ok: false, error: 'No connection — check your internet and try again.' };
  }
}

export async function getJson(url) {
  const res = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' } });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

// One toast at a time, pinned above the phone save bar.
export function Toast({ toast, onDone }) {
  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(onDone, toast.tone === 'error' ? 6000 : 2800);
    return () => clearTimeout(t);
  }, [toast]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!toast) return null;
  return (
    <div className={'ws-toast ' + (toast.tone || 'ok')} role={toast.tone === 'error' ? 'alert' : 'status'}>
      <i className={'fas ' + (toast.tone === 'error' ? 'fa-circle-exclamation' : 'fa-circle-check')} aria-hidden="true" />
      <span>{toast.text}</span>
      <button type="button" onClick={onDone} aria-label="Dismiss"><i className="fas fa-xmark" aria-hidden="true" /></button>
    </div>
  );
}

export function Switch({ on, onChange, label, sub, disabled }) {
  return (
    <label className={'ws-switch' + (disabled ? ' off' : '')}>
      <span className="ws-switch-t"><b>{label}</b>{sub && <small>{sub}</small>}</span>
      <input type="checkbox" role="switch" checked={!!on} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <i aria-hidden="true" />
    </label>
  );
}

export function Field({ label, hint, children, count, max }) {
  return (
    <label className="ws-field">
      <span className="ws-field-l">{label}{max ? <em className={count > max ? 'over' : ''}>{count || 0}/{max}</em> : null}</span>
      {children}
      {hint && <small className="ws-field-h">{hint}</small>}
    </label>
  );
}

// Grow a textarea with its text so nobody types into a tiny box.
export function AutoText({ value, onChange, minRows = 3, ...rest }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight + 2, 520) + 'px';
  }, [value]);
  return <textarea ref={ref} rows={minRows} value={value || ''} onChange={(e) => onChange(e.target.value)} {...rest} />;
}

// Pick an image: upload a new one or reuse one from the library.
export function ImagePicker({ value, onChange, label = 'Picture', wide }) {
  const { urls, notify } = useWs();
  const [busy, setBusy] = useState(false);
  const [lib, setLib] = useState(false);
  const input = useRef(null);
  const upload = async (files) => {
    if (!files || !files.length) return;
    setBusy(true);
    const f = new FormData();
    f.append('file', files[0]);
    const r = await postFiles(urls.upload, f);
    setBusy(false);
    if (input.current) input.current.value = '';
    if (r.ok && r.items && r.items[0]) onChange(r.items[0].url);
    else notify('error', r.error || 'That image could not be uploaded.');
  };
  return (
    <div className={'ws-img' + (wide ? ' wide' : '') + (value ? ' has' : '')}>
      <div className="ws-img-box">
        {value ? <img src={value} alt="" /> : <span><i className="fas fa-image" aria-hidden="true" />No picture</span>}
        {busy && <div className="ws-img-busy"><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Uploading…</div>}
      </div>
      <div className="ws-img-a">
        <button type="button" className="rs-btn sm" onClick={() => input.current && input.current.click()} disabled={busy}>
          <i className="fas fa-arrow-up-from-bracket" aria-hidden="true" />{value ? 'Replace' : 'Upload'}</button>
        <button type="button" className="rs-btn sm ghost" onClick={() => setLib(true)} disabled={busy}>
          <i className="fas fa-photo-film" aria-hidden="true" />Library</button>
        {value && <button type="button" className="rs-btn sm ghost danger-t" onClick={() => onChange('')} aria-label={'Remove ' + label}>
          <i className="fas fa-trash-can" aria-hidden="true" /></button>}
      </div>
      <input ref={input} type="file" accept="image/*" hidden onChange={(e) => upload(e.target.files)} />
      {lib && <Library onClose={() => setLib(false)} onPick={(u) => { onChange(u); setLib(false); }} />}
    </div>
  );
}

// Choose from images already uploaded (fetched on open).
export function Library({ onClose, onPick, multi }) {
  const { urls } = useWs();
  const [items, setItems] = useState(null);
  const [sel, setSel] = useState([]);
  useEffect(() => {
    getJson(urls.library).then((d) => setItems(d.items || [])).catch(() => setItems([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const tap = (u) => {
    if (!multi) { onPick(u); return; }
    setSel((s) => (s.includes(u) ? s.filter((x) => x !== u) : s.concat(u)));
  };
  return (
    <Sheet title="Choose from your library" onClose={onClose}>
      <div className="ws-lib">
        {items == null && <p className="rs-muted ws-pad">Loading…</p>}
        {items && !items.length && <p className="rs-muted ws-pad">No images yet — upload one first.</p>}
        {items && items.length > 0 && (
          <div className="ws-lib-grid">
            {items.map((m) => (
              <button type="button" key={m.id} className={'ws-lib-it' + (sel.includes(m.url) ? ' on' : '')} onClick={() => tap(m.url)}>
                <img src={m.url} alt={m.name} loading="lazy" />
                {sel.includes(m.url) && <i className="fas fa-circle-check" aria-hidden="true" />}
              </button>
            ))}
          </div>
        )}
      </div>
      {multi && (
        <div className="ws-sheet-foot">
          <button type="button" className="rs-btn primary wide" disabled={!sel.length} onClick={() => onPick(sel)}>
            Add {sel.length || ''} photo{sel.length === 1 ? '' : 's'}</button>
        </div>
      )}
    </Sheet>
  );
}

export function copyText(text, notify) {
  const full = text.startsWith('/') ? window.location.origin + text : text;
  const ok = () => notify && notify('ok', 'Link copied.');
  copyToClipboard(full).then((done) => (done ? ok() : window.prompt('Copy this link', full)));
}

// Warn before leaving with unsaved edits.
export function useLeaveGuard(dirty) {
  useEffect(() => {
    if (!dirty) return undefined;
    const h = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [dirty]);
}
