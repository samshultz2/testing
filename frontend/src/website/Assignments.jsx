// Holiday assignments: upload per class, show or hide, download, delete.
import React, { useState, useRef, useMemo } from 'react';
import { confirm } from '../components/ui';
import { Sheet, Blank, Menu } from '../subjects/results';
import { useWs, postFiles, submitJson, Field } from './kit';

export function Assignments() {
  const { d, setData, notify, write } = useWs();
  const [adding, setAdding] = useState(false);
  const items = d.items;
  const groups = useMemo(() => {
    const m = new Map();
    items.forEach((a) => { if (!m.has(a.class_label)) m.set(a.class_label, []); m.get(a.class_label).push(a); });
    return Array.from(m.entries());
  }, [items]);
  const replace = (a) => setData({ ...d, items: items.map((x) => (x.id === a.id ? a : x)) });
  const toggle = async (a) => {
    replace({ ...a, published: !a.published });
    const r = await submitJson(a.toggle, {});
    if (r.ok) { replace(r.item); notify('ok', r.message); } else { replace(a); notify('error', r.error || 'Could not change that.'); }
  };
  const del = async (a) => {
    if (!(await confirm({ title: 'Delete this assignment?', message: `“${a.title}” for ${a.class_label} will be removed.`, confirmText: 'Delete', tone: 'danger' }))) return;
    const r = await submitJson(a.delete, {});
    if (r.ok) { setData({ ...d, items: items.filter((x) => x.id !== a.id) }); notify('ok', r.message); } else notify('error', r.error || 'Could not delete.');
  };
  const live = items.filter((a) => a.published).length;
  return (
    <div className="ws-list-page">
      <header className="ws-page-h">
        <div><h1>Holiday assignments</h1><p>Students download these from any page with a “Holiday assignments” section. {items.length ? `${live} of ${items.length} visible.` : ''}</p></div>
        {write && <button type="button" className="rs-btn primary" onClick={() => setAdding(true)}><i className="fas fa-arrow-up-from-bracket" aria-hidden="true" />Upload</button>}
      </header>
      {!items.length && (
        <Blank icon="fa-file-arrow-down" title="No assignments yet">
          <p>Upload a PDF or Word file for each class before the holiday.</p>
          {write && <button type="button" className="rs-btn primary" onClick={() => setAdding(true)}>Upload the first one</button>}
        </Blank>
      )}
      {groups.map(([cls, list]) => (
        <section key={cls} className="ws-card ws-group">
          <header className="ws-group-h"><b>{cls}</b><em>{list.length}</em></header>
          <ul className="ws-files">
            {list.map((a) => (
              <li key={a.id} className={a.published ? '' : 'off'}>
                <span className={'ws-file-ic ' + a.ext.toLowerCase()}><i className={'fas ' + a.icon} aria-hidden="true" /></span>
                <span className="ws-file-t"><b>{a.title}</b><small>{[a.session_label, a.ext, a.size, a.date].filter(Boolean).join(' · ')}</small></span>
                {write && (
                  <label className="ws-mini-sw" title={a.published ? 'Visible on the website' : 'Hidden'}>
                    <input type="checkbox" role="switch" checked={a.published} onChange={() => toggle(a)} aria-label={(a.published ? 'Hide ' : 'Show ') + a.title} />
                    <i aria-hidden="true" /><span className="rs-hide-sm">{a.published ? 'Visible' : 'Hidden'}</span>
                  </label>
                )}
                <Menu label="" items={[
                  { icon: 'fa-download', label: 'Download', href: a.download, native: true },
                  write && { icon: 'fa-trash-can', label: 'Delete', danger: true, onClick: () => del(a) },
                ]} />
              </li>
            ))}
          </ul>
        </section>
      ))}
      {adding && <UploadSheet onClose={() => setAdding(false)} onDone={(a) => { setData({ ...d, items: [a].concat(items) }); setAdding(false); }} />}
    </div>
  );
}

function UploadSheet({ onClose, onDone }) {
  const { d, notify } = useWs();
  const [f, setF] = useState({ class_id: '', title: '', session_label: '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  const ok = f.title.trim() && file;
  const submit = async (e) => {
    e.preventDefault();
    if (!ok) return;
    if (file.size > 20 * 1024 * 1024) { notify('error', 'That file is larger than 20 MB.'); return; }
    setBusy(true);
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => fd.append(k, v));
    fd.append('file', file);
    const r = await postFiles(d.urls.upload, fd);
    setBusy(false);
    if (r.ok) { notify('ok', r.message); onDone(r.item); } else notify('error', r.error || 'Upload failed.');
  };
  return (
    <Sheet title="Upload an assignment" onClose={onClose}>
      <form className="ws-pad" onSubmit={submit}>
        <Field label="Class">
          <select value={f.class_id} onChange={(e) => setF({ ...f, class_id: e.target.value })}>
            <option value="">All classes (general)</option>
            {d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></Field>
        <Field label="Title"><input value={f.title} maxLength={200} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="e.g. Christmas holiday assignment" required /></Field>
        <Field label="Session or term" hint="Optional"><input value={f.session_label} maxLength={60} onChange={(e) => setF({ ...f, session_label: e.target.value })} placeholder="e.g. 2025/2026 · First term" /></Field>
        <button type="button" className={'ws-drop' + (file ? ' has' : '')} onClick={() => input.current && input.current.click()}>
          <i className={'fas ' + (file ? 'fa-file-circle-check' : 'fa-file-arrow-up')} aria-hidden="true" />
          <span><b>{file ? file.name : 'Choose a PDF or Word file'}</b><small>{file ? `${Math.round(file.size / 1024)} KB — tap to change` : 'PDF, DOC or DOCX up to 20 MB'}</small></span>
        </button>
        <input ref={input} type="file" accept=".pdf,.doc,.docx" hidden onChange={(e) => setFile(e.target.files[0] || null)} />
        <button className="rs-btn primary wide" disabled={busy || !ok}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />{busy ? 'Uploading…' : 'Upload'}</button>
      </form>
    </Sheet>
  );
}
