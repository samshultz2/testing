import React, { useState } from 'react';
import { postForm } from '../lib/forms';
import { Banner, EmptyState } from '../components/ui';

export default function TrashApp({ initial }) {
  const [students, setStudents] = useState(initial.students || []);
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const urls = initial.urls || {};
  const canManage = initial.can_manage !== false;   // view-only users can't restore/purge

  const allSelected = students.length > 0 && selected.size === students.length;
  const toggle = (id) => setSelected((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(students.map((s) => s.id)));

  // Drop the rows we just acted on from local state (no full reload needed).
  const removeRows = (ids) => {
    const gone = new Set(ids);
    setStudents((list) => list.filter((s) => !gone.has(s.id)));
    setSelected((s) => { const n = new Set(s); ids.forEach((i) => n.delete(i)); return n; });
  };

  // `affected` are the rows to drop on success. Single restore/purge target
  // the student in the URL (empty body); bulk actions send student_ids.
  const act = async (url, body, affected, okMsg) => {
    setBusy(true); setMsg(null);
    try {
      const res = await postForm(url, body);
      let data = {};
      try { data = await res.json(); } catch (_) { /* redirect/html */ }
      if (res.ok && (data.ok || res.redirected)) {
        removeRows(affected);
        setMsg({ tone: 'success', text: okMsg });
      } else {
        setMsg({ tone: 'error', text: data.error || `Action failed (HTTP ${res.status}).` });
      }
    } catch (e) {
      setMsg({ tone: 'error', text: e.message || 'Network error — please try again.' });
    } finally { setBusy(false); }
  };

  const restoreOne = (s) => act(s.restore_url, {}, [s.id], `${s.full_name} restored.`);
  const purgeOne = (s) => window.confirm(`Permanently delete ${s.full_name}? This cannot be undone.`)
    && act(s.purge_url, {}, [s.id], `${s.full_name} permanently deleted.`);
  const bulkRestore = () => selected.size
    && act(urls.bulk_restore, { student_ids: [...selected] }, [...selected], `${selected.size} student(s) restored.`);
  const bulkPurge = () => selected.size
    && window.confirm(`Permanently delete ${selected.size} student(s)? This cannot be undone.`)
    && act(urls.bulk_purge, { student_ids: [...selected] }, [...selected], `${selected.size} student(s) permanently deleted.`);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Deleted Students</h1>
          <p className="text-muted text-sm">Restore students or remove them permanently.</p>
        </div>
        <div className="page-header-actions">
          <a href={urls.list} className="btn btn-secondary btn-sm"><i className="fas fa-arrow-left" /> Back</a>
        </div>
      </div>

      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}

      <div className="card">
        <div className="card-header"><h3><i className="fas fa-trash" /> Deleted ({students.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {students.length === 0 ? (
            <EmptyState icon="fa-trash" title="No deleted students." hint="Students you delete from the list show up here and can be restored." />
          ) : (
            <>
              {canManage && (
                <div className="selection-bar" style={{ display: 'flex', alignItems: 'center', gap: '.6rem', flexWrap: 'wrap', padding: '.75rem 1rem', borderBottom: '1px solid var(--border-color,#eee)' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem', margin: 0 }}>
                    <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all" /> Select all
                  </label>
                  <span className="text-muted text-sm">{selected.size} selected</span>
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: '.4rem' }}>
                    <button type="button" className="btn btn-success btn-sm" disabled={busy || !selected.size} onClick={bulkRestore}>
                      <i className="fas fa-rotate-left" /> Restore selected
                    </button>
                    <button type="button" className="btn btn-danger btn-sm" disabled={busy || !selected.size} onClick={bulkPurge}>
                      <i className="fas fa-trash" /> Delete forever
                    </button>
                  </div>
                </div>
              )}

              <div className="data-cards" style={{ padding: '1rem' }}>
                {students.map((s) => (
                  <div className="data-card" key={s.id}>
                    <div className="data-card-header">
                      <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', margin: 0 }}>
                        {canManage && <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggle(s.id)} aria-label={`Select ${s.full_name}`} />}
                        <span className="data-card-title">{s.full_name}</span>
                      </label>
                      <span className={'badge ' + (s.gender === 'Male' ? 'badge-male' : 'badge-female')}>{s.gender}</span>
                    </div>
                    <div className="data-card-row"><span className="data-card-label">ID</span><span>{s.student_id}</span></div>
                    {s.stream && <div className="data-card-row"><span className="data-card-label">Stream</span><span>{s.stream}</span></div>}
                    {canManage && (
                      <div className="data-card-actions" style={{ display: 'flex', gap: '.4rem' }}>
                        <button type="button" className="btn btn-success btn-sm w-100" style={{ flex: 1 }} disabled={busy} onClick={() => restoreOne(s)}>
                          <i className="fas fa-rotate-left" /> Restore
                        </button>
                        <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} disabled={busy} onClick={() => purgeOne(s)}>
                          <i className="fas fa-trash" /> Delete forever
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
