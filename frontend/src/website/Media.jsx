// Media library: drop or pick photos, see what's in use, copy or delete.
import React, { useState, useRef, useMemo } from 'react';
import { confirm } from '../components/ui';
import { Sheet, Seg, Blank } from '../subjects/results';
import { useWs, postFiles, submitJson, copyText } from './kit';

export function Media() {
  const { d, setData, notify, write } = useWs();
  const [busy, setBusy] = useState(0);
  const [over, setOver] = useState(false);
  const [show, setShow] = useState('all');
  const [open, setOpen] = useState(null);
  const input = useRef(null);
  const items = d.items;
  const used = items.filter((m) => m.used).length;
  const list = useMemo(() => items.filter((m) => show === 'all' || (show === 'used' ? m.used : !m.used)), [items, show]);
  const upload = async (files) => {
    const arr = Array.from(files || []).filter((f) => /^image\//.test(f.type) || /\.(png|jpe?g|webp|gif)$/i.test(f.name));
    if (!arr.length) { notify('error', 'Choose PNG, JPG, WEBP or GIF images.'); return; }
    setBusy(arr.length);
    const f = new FormData();
    arr.forEach((x) => f.append('file', x));
    const r = await postFiles(d.urls.upload, f);
    setBusy(0);
    if (input.current) input.current.value = '';
    if (r.ok) {
      const added = r.items.map((m) => ({ ...m, used: false }));
      setData({ ...d, items: added.concat(items), total_mb: Math.round((d.total_mb + added.reduce((a, m) => a + m.kb, 0) / 1024) * 100) / 100 });
      notify(r.errors && r.errors.length ? 'error' : 'ok', r.errors && r.errors.length ? `${r.message} ${r.errors.length} skipped: ${r.errors[0]}` : r.message);
    } else notify('error', r.error || 'Upload failed.');
  };
  const del = async (m) => {
    const ok = await confirm({ title: 'Delete this image?', confirmText: 'Delete', tone: 'danger',
      message: m.used ? 'This image is still used on your website or in a news post — it will disappear from there.' : 'It isn’t used anywhere on your website.' });
    if (!ok) return;
    const r = await submitJson(m.delete, {});
    if (r.ok) { setData({ ...d, items: items.filter((x) => x.id !== m.id), total_mb: Math.max(0, Math.round((d.total_mb - m.kb / 1024) * 100) / 100) }); setOpen(null); notify('ok', r.message); }
    else notify('error', r.error || 'Could not delete.');
  };
  const drop = write ? {
    onDragOver: (e) => { e.preventDefault(); setOver(true); },
    onDragLeave: (e) => { if (e.currentTarget === e.target) setOver(false); },
    onDrop: (e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files); },
  } : {};
  return (
    <div className={'ws-list-page ws-media' + (over ? ' over' : '')} {...drop}>
      <header className="ws-page-h">
        <div><h1>Photos &amp; media</h1><p>{items.length} image{items.length === 1 ? '' : 's'} · {d.total_mb} MB · stored in {d.storage_where}</p></div>
        {write && <button type="button" className="rs-btn primary" disabled={!!busy} onClick={() => input.current && input.current.click()}>
          <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-arrow-up-from-bracket')} aria-hidden="true" />{busy ? `Uploading ${busy}…` : 'Upload photos'}</button>}
        <input ref={input} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />
      </header>
      {write && (
        <button type="button" className="ws-drop" onClick={() => input.current && input.current.click()} disabled={!!busy}>
          <i className="fas fa-cloud-arrow-up" aria-hidden="true" />
          <span><b>{over ? 'Drop to upload' : 'Drag photos here, or tap to choose'}</b><small>PNG, JPG, WEBP or GIF up to 8 MB — resized and optimised for you.</small></span>
        </button>
      )}
      {items.length > 0 && (
        <div className="ws-filter">
          <Seg label="Show" value={show} onChange={setShow} options={[
            { value: 'all', label: 'All', count: items.length }, { value: 'used', label: 'In use', count: used },
            { value: 'unused', label: 'Not used', count: items.length - used }]} />
        </div>
      )}
      {!items.length && <Blank icon="fa-images" title="No photos yet"><p>Upload photos once, then use them in any section or news post.</p></Blank>}
      <div className="ws-grid">
        {list.map((m) => (
          <button type="button" key={m.id} className="ws-tile" onClick={() => setOpen(m)}>
            <img src={m.url} alt={m.name} loading="lazy" />
            {m.used && <em className="ws-used"><i className="fas fa-check" aria-hidden="true" />In use</em>}
            <span>{m.w}×{m.h} · {m.kb} KB</span>
          </button>
        ))}
      </div>
      {open && (
        <Sheet title={open.name} onClose={() => setOpen(null)}>
          <div className="ws-pad ws-media-one">
            <img src={open.url} alt={open.name} />
            <dl className="ws-dl">
              <div><dt>Size</dt><dd>{open.w}×{open.h} px · {open.kb} KB</dd></div>
              <div><dt>Added</dt><dd>{open.date || '—'}</dd></div>
              <div><dt>Used on site</dt><dd>{open.used ? 'Yes' : 'No'}</dd></div>
            </dl>
            <div className="ws-row-a">
              <button type="button" className="rs-btn" onClick={() => copyText(open.url, notify)}><i className="fas fa-link" aria-hidden="true" />Copy link</button>
              <a className="rs-btn ghost" href={open.url} target="_blank" rel="noopener"><i className="fas fa-arrow-up-right-from-square" aria-hidden="true" />Open</a>
              {write && <button type="button" className="rs-btn ghost danger-t" onClick={() => del(open)}><i className="fas fa-trash-can" aria-hidden="true" />Delete</button>}
            </div>
          </div>
        </Sheet>
      )}
    </div>
  );
}
