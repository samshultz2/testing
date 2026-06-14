import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet, csrfToken } from '../lib/api';
import ExportModal from './ExportModal';

// Form-encoded POST to the existing student endpoints (delete/graduate/bulk),
// carrying CSRF. Returns the response so callers can read JSON where provided.
async function postForm(url, fields) {
  const body = new URLSearchParams();
  Object.entries(fields).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach((x) => body.append(k, x));
    else if (v !== undefined && v !== null) body.append(k, v);
  });
  return fetch(url, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch',
               'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
}

const SORTS = [
  ['surname|asc', 'Name A–Z'], ['surname|desc', 'Name Z–A'],
  ['first_name|asc', 'First name'], ['student_id|asc', 'Student ID'],
  ['created_at|desc', 'Newest'], ['age|desc', 'Oldest'],
];

export default function App({ initial }) {
  const [data, setData] = useState(initial || {});
  const a = (initial && initial.applied) || {};
  const [query, setQuery] = useState({
    gender: a.gender || '', religion: a.religion || '', stream: a.stream || '',
    subject: a.subject || '', class_id: a.class_id || '', arm_id: a.arm_id || '',
    sort: a.sort || 'surname', order: a.order || 'asc', search: a.search || '',
    page: (initial && initial.page) || 1,
  });
  const [search, setSearch] = useState(a.search || '');
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [showExport, setShowExport] = useState(false);
  const [bulkStream, setBulkStream] = useState('');
  const [bulkSubject, setBulkSubject] = useState('');
  const skip = useRef(true);

  const load = useCallback(async (q) => {
    setLoading(true);
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => { if (v) p.set(k, v); });
    try { setData(await apiGet('/api/students?' + p.toString())); }
    catch (e) { setMsg({ tone: 'error', text: 'Could not load students.' }); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (skip.current) { skip.current = false; return; }
    load(query);
  }, [query, load]);

  // Debounced search → query.
  useEffect(() => {
    const t = setTimeout(() => setQuery((q) => (q.search === search ? q : { ...q, search, page: 1 })), 350);
    return () => clearTimeout(t);
  }, [search]);

  const d = data || {};
  const students = d.students || [];
  const filters = d.filters || {};
  const canManage = !!d.can_manage;
  const setFilter = (k, v) => setQuery((q) => ({ ...q, [k]: v, page: 1 }));
  const goPage = (p) => setQuery((q) => ({ ...q, page: p }));

  const allOnPage = students.length && students.every((s) => selected.has(s.id));
  const toggleSel = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected((s) => {
    const n = new Set(s); const ids = students.map((x) => x.id);
    if (ids.every((i) => n.has(i))) ids.forEach((i) => n.delete(i)); else ids.forEach((i) => n.add(i));
    return n;
  });
  const selectedIds = [...selected];

  const refresh = async () => { setSelected(new Set()); await load(query); };
  const runAction = async (url, fields, okMsg) => {
    try {
      const res = await postForm(url, fields);
      let text = okMsg;
      if ((res.headers.get('content-type') || '').includes('application/json')) {
        const j = await res.json();
        if (j.error) { setMsg({ tone: 'error', text: j.error }); return; }
        if (j.updated !== undefined) text = `Updated ${j.updated}${j.skipped ? `, skipped ${j.skipped}` : ''}.`;
      } else if (!res.ok) { setMsg({ tone: 'error', text: 'Action failed.' }); return; }
      setMsg({ tone: 'success', text });
      await refresh();
    } catch (e) { setMsg({ tone: 'error', text: e.message || 'Action failed.' }); }
  };

  const needSel = () => { if (!selectedIds.length) { setMsg({ tone: 'warn', text: 'Select some students first.' }); return false; } return true; };

  return (
    <div>
      <div className="page-header">
        <div><h1><i className="fas fa-user-graduate" /> Students</h1></div>
        <div className="page-header-actions stu-toolbar">
          {d.can_add && <a href={d.add_url} className="btn btn-primary"><i className="fas fa-plus" /> Add Student</a>}
          {canManage && <button type="button" className="btn btn-outline btn-sm" title="Fill WAEC subjects from each student's stream"
                                onClick={() => runAction(d.waec_by_stream_url, {}, 'WAEC subjects filled from stream.')}><i className="fas fa-wand-magic-sparkles" /> WAEC by stream</button>}
          {canManage && <a href={d.trash_url} className="btn btn-secondary btn-sm" title="Deleted students"><i className="fas fa-trash" /></a>}
        </div>
      </div>

      {msg && (
        <div className={'alert alert-' + ({ success: 'success', error: 'danger', warn: 'warning' }[msg.tone] || 'info')}
             role="status" style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <span>{msg.text}</span>
          <button type="button" className="att-x" onClick={() => setMsg(null)} aria-label="Dismiss" style={{ background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
        </div>
      )}

      <div className="card"><div className="card-body">
        <div className="stu-filters">
          <input className="form-control full" type="text" placeholder="Search name or Student ID…"
                 value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search students" />
          <select className="form-control" value={query.class_id} onChange={(e) => setFilter('class_id', e.target.value)} aria-label="Class">
            <option value="">All classes</option>
            {(filters.classes || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="form-control" value={query.arm_id} onChange={(e) => setFilter('arm_id', e.target.value)} aria-label="Arm">
            <option value="">All arms</option>
            {(filters.arms || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="form-control" value={query.gender} onChange={(e) => setFilter('gender', e.target.value)} aria-label="Gender">
            <option value="">Any gender</option><option>Male</option><option>Female</option>
          </select>
          <select className="form-control" value={query.religion} onChange={(e) => setFilter('religion', e.target.value)} aria-label="Religion">
            <option value="">Any religion</option>
            {(filters.religions || []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <select className="form-control" value={query.stream} onChange={(e) => setFilter('stream', e.target.value)} aria-label="Stream">
            <option value="">Any stream</option>
            {(filters.streams || []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <select className="form-control" value={query.subject} onChange={(e) => setFilter('subject', e.target.value)} aria-label="WAEC subject (SSS3)">
            <option value="">Any WAEC subject</option>
            {(filters.subjects || []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <select className="form-control" value={query.sort + '|' + query.order}
                  onChange={(e) => { const [s, o] = e.target.value.split('|'); setQuery((q) => ({ ...q, sort: s, order: o, page: 1 })); }} aria-label="Sort">
            {SORTS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </div>
      </div></div>

      <div className="stu-bulkbar">
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', margin: 0 }}>
          <input type="checkbox" checked={!!allOnPage} onChange={toggleAll} /> Select page
        </label>
        <span className="stu-count">{selectedIds.length ? `${selectedIds.length} selected · ` : ''}{d.total || 0} student(s){loading ? ' · loading…' : ''}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: '.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" className="btn btn-success btn-sm" onClick={() => setShowExport(true)}><i className="fas fa-download" /> Export</button>
          {canManage && <>
            <select className="form-control" style={{ width: 'auto' }} value={bulkStream} onChange={(e) => setBulkStream(e.target.value)} aria-label="Bulk stream">
              <option value="">Set stream…</option>
              {(filters.streams || []).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button type="button" className="btn btn-primary btn-sm" disabled={!bulkStream}
                    onClick={() => needSel() && runAction(d.bulk_stream_url, { stream: bulkStream, student_ids: selectedIds }, 'Stream updated.')}>Apply</button>
            <select className="form-control" style={{ width: 'auto' }} value={bulkSubject} onChange={(e) => setBulkSubject(e.target.value)} aria-label="Bulk WAEC subject">
              <option value="">Add WAEC subject…</option>
              {(filters.subjects || []).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button type="button" className="btn btn-primary btn-sm" disabled={!bulkSubject} title="SSS3 students only"
                    onClick={() => needSel() && runAction(d.bulk_subject_url, { subject: bulkSubject, student_ids: selectedIds }, 'Subject added.')}>Add (SSS3)</button>
            <button type="button" className="btn btn-danger btn-sm"
                    onClick={() => needSel() && window.confirm(`Delete ${selectedIds.length} selected student(s)?`)
                      && runAction(d.bulk_delete_url, { student_ids: selectedIds }, 'Deleted selected students.')}><i className="fas fa-trash" /> Delete selected</button>
          </>}
        </span>
      </div>

      {students.length === 0 ? (
        <div className="empty-state"><i className="fas fa-users" /><h3>No students found</h3><p>Try adjusting your filters.</p></div>
      ) : (
        <div className="stu-grid">
          {students.map((s) => (
            <div key={s.id} className={'stu-card' + (selected.has(s.id) ? ' is-sel' : '')}>
              <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggleSel(s.id)} aria-label={'Select ' + s.name} />
              <div className="stu-card-main">
                <div className="stu-card-head">
                  <span className="stu-name">{s.name} {s.is_graduated && <span className="badge badge-success" title="Graduate"><i className="fas fa-user-graduate" /></span>}</span>
                  <span className="stu-sid">{s.student_id}</span>
                </div>
                <div className="stu-meta">
                  <span>{s.current_class || '—'}</span>
                  <span className={'badge ' + (s.gender === 'Male' ? 'badge-male' : 'badge-female')}>{s.gender}</span>
                  {s.stream && <span className="badge badge-info">{s.stream}</span>}
                  <span>Age {s.age || '—'}</span>
                  {s.religion && <span>{s.religion}</span>}
                </div>
                <div className="stu-actions">
                  <a href={s.url} className="btn btn-secondary btn-sm"><i className="fas fa-eye" /> View</a>
                  {canManage && <a href={s.edit_url} className="btn btn-secondary btn-sm"><i className="fas fa-edit" /> Edit</a>}
                  {canManage && <button type="button" className={'btn btn-sm ' + (s.is_graduated ? 'btn-warning' : 'btn-success')}
                                        title={s.is_graduated ? 'Undo graduate' : 'Mark as graduate'}
                                        onClick={() => window.confirm(`${s.is_graduated ? 'Undo graduation for' : 'Mark as graduate:'} ${s.name}?`)
                                          && runAction(s.graduate_url, {}, 'Updated graduation status.')}>
                    <i className={'fas ' + (s.is_graduated ? 'fa-rotate-left' : 'fa-user-graduate')} /></button>}
                  {canManage && <button type="button" className="btn btn-danger btn-sm" title="Delete"
                                        onClick={() => window.confirm(`Delete ${s.name}?`) && runAction(s.delete_url, {}, 'Student deleted.')}><i className="fas fa-trash" /></button>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {(d.pages || 1) > 1 && (
        <div className="pagination" style={{ marginTop: '1rem' }}>
          <button type="button" disabled={!d.has_prev} onClick={() => goPage(d.page - 1)} aria-label="Previous"><i className="fas fa-chevron-left" /></button>
          <span style={{ padding: '0 .6rem' }}>Page {d.page} of {d.pages}</span>
          <button type="button" disabled={!d.has_next} onClick={() => goPage(d.page + 1)} aria-label="Next"><i className="fas fa-chevron-right" /></button>
        </div>
      )}

      {showExport && (
        <ExportModal total={d.total || 0} selectedIds={selectedIds} exportUrl={d.export_url}
                     applied={{ ...query, page: undefined }} onClose={() => setShowExport(false)} />
      )}
    </div>
  );
}
