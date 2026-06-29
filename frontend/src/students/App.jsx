import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet } from '../lib/api';
import { postForm } from '../lib/forms';
import ExportModal from './ExportModal';
import ImportModal from './ImportModal';
import { confirm, Empty, Pagination } from '../components/ui';

const SORTS = [
  ['surname|asc', 'Name A–Z'], ['surname|desc', 'Name Z–A'],
  ['first_name|asc', 'First name'], ['student_id|asc', 'Student ID'],
  ['created_at|desc', 'Recently added'],
  ['age|desc', 'Oldest (by age)'], ['age|asc', 'Youngest (by age)'],
];

// Filters are kept in React state (not the URL), so they'd be lost the moment
// you open a student and come back. We stash them per-tab and restore them when
// returning from a student's detail/edit page.
const FILTER_KEY = 'students:filters';

function cameFromStudentPage() {
  try {
    const r = new URL(document.referrer);
    return r.origin === window.location.origin && /\/students\/\d+/.test(r.pathname);
  } catch (e) { return false; }
}

function startState(applied, page) {
  const base = {
    gender: applied.gender || '', religion: applied.religion || '', stream: applied.stream || '',
    subject: applied.subject || '', class_id: applied.class_id || '', arm_id: applied.arm_id || '',
    sort: applied.sort || 'surname', order: applied.order || 'asc', search: applied.search || '',
    page: page || 1,
  };
  const urlHasFilters = !!(applied.gender || applied.religion || applied.stream || applied.subject
    || applied.class_id || applied.arm_id || applied.search);
  if (!urlHasFilters && cameFromStudentPage()) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(FILTER_KEY) || 'null');
      if (saved && typeof saved === 'object') {
        return { query: { ...base, ...saved, page: saved.page || 1 }, restored: true };
      }
    } catch (e) { /* ignore bad/empty storage */ }
  }
  return { query: base, restored: false };
}

// Reusable labelled filter field (label above the control).
function Field({ label, full, children }) {
  return (
    <label className={'stu-field-wrap' + (full ? ' full' : '')}>
      <span className="stu-field-label">{label}</span>
      {children}
    </label>
  );
}

export default function App({ initial }) {
  const [data, setData] = useState(initial || {});
  const a = (initial && initial.applied) || {};
  const start = useRef(startState(a, initial && initial.page)).current;
  const [query, setQuery] = useState(start.query);
  const [search, setSearch] = useState(start.query.search || '');
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [showExport, setShowExport] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [bulkStream, setBulkStream] = useState('');
  const [bulkGender, setBulkGender] = useState('');
  const [bulkSubject, setBulkSubject] = useState('');
  // When filters were restored, the server-rendered page doesn't match them, so
  // let the first effect run fetch fresh (filtered) data instead of skipping it.
  const skip = useRef(!start.restored);

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

  // Remember the active filters so returning from a student page keeps them.
  useEffect(() => {
    try { sessionStorage.setItem(FILTER_KEY, JSON.stringify(query)); } catch (e) { /* ignore */ }
  }, [query]);

  // Returning via the browser's back/forward cache shows a stale snapshot — so
  // re-fetch on restore to pick up any edits made while away.
  useEffect(() => {
    const onShow = (e) => { if (e.persisted) load(query); };
    window.addEventListener('pageshow', onShow);
    return () => window.removeEventListener('pageshow', onShow);
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
  const canAdmin = !!d.can_admin;   // admin-only bulk tools (subject / delete)
  const canBulk = !!d.can_bulk;     // mass-assign gender/stream (admins + teachers, scoped)
  const canSss3 = !!d.can_sss3;     // SSS3-only WAEC subject filter/tools
  const setFilter = (k, v) => setQuery((q) => ({ ...q, [k]: v, page: 1 }));
  const goPage = (p) => setQuery((q) => ({ ...q, page: p }));
  const hasFilters = !!(search || query.gender || query.religion || query.stream
    || query.subject || query.class_id || query.arm_id);
  const resetFilters = () => {
    setSearch('');
    setQuery({ gender: '', religion: '', stream: '', subject: '', class_id: '', arm_id: '',
               sort: 'surname', order: 'asc', search: '', page: 1 });
  };

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
        if (j.updated !== undefined) text = `Updated ${j.updated}${j.skipped ? `, skipped ${j.skipped}` : ''}${j.waec_filled ? ` · WAEC subjects filled for ${j.waec_filled}` : ''}.`;
      } else if (!res.ok) { setMsg({ tone: 'error', text: 'Action failed.' }); return; }
      setMsg({ tone: 'success', text });
      await refresh();
    } catch (e) { setMsg({ tone: 'error', text: e.message || 'Action failed.' }); }
  };

  const needSel = () => { if (!selectedIds.length) { setMsg({ tone: 'warn', text: 'Select some students first.' }); return false; } return true; };

  return (
    <div>
      <div className="page-header">
        <div><h1><i aria-hidden="true" className="fas fa-user-graduate" /> Students</h1></div>
        <div className="page-header-actions stu-toolbar">
          {d.can_add && <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Student</a>}
          {d.can_add && <button type="button" className="btn btn-outline" onClick={() => setShowImport(true)}><i aria-hidden="true" className="fas fa-paste" /> Import (paste)</button>}
          {canAdmin && <button type="button" className="btn btn-outline btn-sm" title="Fill WAEC subjects from each student's stream"
                               onClick={async () => { if (await confirm("Fill WAEC subjects from stream for students who don't have them set?"))
                                 runAction(d.waec_by_stream_url, {}, 'WAEC subjects filled from stream.'); }}><i aria-hidden="true" className="fas fa-wand-magic-sparkles" /> WAEC by stream</button>}
          {d.trash_url && <a href={d.trash_url} className="btn btn-secondary btn-sm" title="View deleted students (restore / delete permanently)"><i aria-hidden="true" className="fas fa-trash" /> Trash</a>}
        </div>
      </div>

      {msg && (
        <div className={'alert alert-' + ({ success: 'success', error: 'danger', warn: 'warning' }[msg.tone] || 'info')}
             role="status" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <span>{msg.text}</span>
          <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {msg.tone === 'error' && (
              <button type="button" className="btn btn-light btn-sm" onClick={() => { setMsg(null); load(query); }}>
                <i aria-hidden="true" className="fas fa-rotate-right" /> Retry
              </button>
            )}
            <button type="button" className="att-x" onClick={() => setMsg(null)} aria-label="Dismiss" style={{ background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
          </span>
        </div>
      )}

      <div className="card"><div className="card-body">
        <div className="stu-filters">
          <Field label="Search" full>
            <input className="form-control" type="text" placeholder="Name or Student ID…"
                   value={search} onChange={(e) => setSearch(e.target.value)} />
          </Field>
          <Field label="Class">
            <select className="form-control" value={query.class_id} onChange={(e) => setFilter('class_id', e.target.value)}>
              <option value="">All classes</option>
              {(filters.classes || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Arm">
            <select className="form-control" value={query.arm_id} onChange={(e) => setFilter('arm_id', e.target.value)}>
              <option value="">All arms</option>
              {(filters.arms || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Gender">
            <select className="form-control" value={query.gender} onChange={(e) => setFilter('gender', e.target.value)}>
              <option value="">All</option><option>Male</option><option>Female</option>
            </select>
          </Field>
          <Field label="Religion">
            <select className="form-control" value={query.religion} onChange={(e) => setFilter('religion', e.target.value)}>
              <option value="">All</option>
              {(filters.religions || []).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
          <Field label="Stream">
            <select className="form-control" value={query.stream} onChange={(e) => setFilter('stream', e.target.value)}>
              <option value="">All</option>
              {(filters.streams || []).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
          {canSss3 && <Field label="WAEC subject (SSS3)">
            <select className="form-control" value={query.subject} onChange={(e) => setFilter('subject', e.target.value)}>
              <option value="">All</option>
              {(filters.subjects || []).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>}
          <Field label="Sort by">
            <select className="form-control" value={query.sort + '|' + query.order}
                    onChange={(e) => { const [s, o] = e.target.value.split('|'); setQuery((q) => ({ ...q, sort: s, order: o, page: 1 })); }}>
              {SORTS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
          </Field>
        </div>
        {hasFilters && (
          <div style={{ marginTop: '.5rem' }}>
            <button type="button" className="btn btn-light btn-sm" onClick={resetFilters}>
              <i aria-hidden="true" className="fas fa-xmark" /> Clear filters
            </button>
          </div>
        )}
      </div></div>

      <div className="stu-bulkbar">
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', margin: 0 }}>
          <input type="checkbox" checked={!!allOnPage} onChange={toggleAll} /> Select page
        </label>
        <span className="stu-count">{selectedIds.length ? `${selectedIds.length} selected · ` : ''}{d.total || 0} student(s){loading ? ' · loading…' : ''}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: '.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" className="btn btn-success btn-sm" onClick={() => setShowExport(true)}><i aria-hidden="true" className="fas fa-download" /> Export</button>
          {canBulk && <>
            <select className="form-control" style={{ width: 'auto' }} value={bulkGender} onChange={(e) => setBulkGender(e.target.value)} aria-label="Bulk gender">
              <option value="">Set gender…</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
            </select>
            <button type="button" className="btn btn-primary btn-sm" disabled={!bulkGender}
                    onClick={() => needSel() && runAction(d.bulk_gender_url, { gender: bulkGender, student_ids: selectedIds }, 'Gender updated.')}>Apply</button>
            <select className="form-control" style={{ width: 'auto' }} value={bulkStream} onChange={(e) => setBulkStream(e.target.value)} aria-label="Bulk stream">
              <option value="">Set stream…</option>
              {(filters.streams || []).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button type="button" className="btn btn-primary btn-sm" disabled={!bulkStream} title="Also fills WAEC subjects from the stream where not already set"
                    onClick={() => needSel() && runAction(d.bulk_stream_url, { stream: bulkStream, student_ids: selectedIds }, 'Stream updated.')}>Apply</button>
            {canSss3 && <>
              <select className="form-control" style={{ width: 'auto' }} value={bulkSubject} onChange={(e) => setBulkSubject(e.target.value)} aria-label="Bulk WAEC subject">
                <option value="">Add WAEC subject…</option>
                {(filters.subjects || []).map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <button type="button" className="btn btn-primary btn-sm" disabled={!bulkSubject} title="SSS3 students only"
                      onClick={() => needSel() && runAction(d.bulk_subject_url, { subject: bulkSubject, student_ids: selectedIds }, 'Subject added.')}>Add (SSS3)</button>
            </>}
            {canAdmin && <button type="button" className="btn btn-danger btn-sm"
                    onClick={async () => { if (needSel() && await confirm({ title: 'Delete students', message: `Delete ${selectedIds.length} selected student(s)?`, confirmText: 'Delete', tone: 'danger' }))
                      runAction(d.bulk_delete_url, { student_ids: selectedIds }, 'Deleted selected students.'); }}><i aria-hidden="true" className="fas fa-trash" /> Delete selected</button>}
          </>}
        </span>
      </div>

      {students.length === 0 ? (
        <Empty icon="fa-users" title="No students found"><p>Try adjusting your filters.</p></Empty>
      ) : (
        <div className="stu-grid">
          {students.map((s) => (
            <div key={s.id} className={'stu-card' + (selected.has(s.id) ? ' is-sel' : '')}>
              <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggleSel(s.id)} aria-label={'Select ' + s.name} />
              <div className="stu-card-main">
                <div className="stu-card-head">
                  <span className="stu-name">{s.name} {s.is_graduated && <span className="badge badge-success" title="Graduate"><i aria-hidden="true" className="fas fa-user-graduate" /></span>}</span>
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
                  <a href={s.url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-eye" /> View</a>
                  {canManage && <a href={s.edit_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-edit" /> Edit</a>}
                  {canManage && <button type="button" className={'btn btn-sm ' + (s.is_graduated ? 'btn-warning' : 'btn-success')}
                                        title={s.is_graduated ? 'Undo graduate' : 'Mark as graduate'}
                                        onClick={async () => { if (await confirm(`${s.is_graduated ? 'Undo graduation for' : 'Mark as graduate:'} ${s.name}?`))
                                          runAction(s.graduate_url, {}, 'Updated graduation status.'); }}>
                    <i aria-hidden="true" className={'fas ' + (s.is_graduated ? 'fa-rotate-left' : 'fa-user-graduate')} /></button>}
                  {canManage && <button type="button" className="btn btn-danger btn-sm" title="Delete"
                                        onClick={async () => { if (await confirm({ title: 'Delete student', message: `Delete ${s.name}?`, confirmText: 'Delete', tone: 'danger' })) runAction(s.delete_url, {}, 'Student deleted.'); }}><i aria-hidden="true" className="fas fa-trash" /></button>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Pagination page={d.page || 1} pages={d.pages || 1} onPage={goPage} />

      {showExport && (
        <ExportModal total={d.total || 0} selectedIds={selectedIds} exportUrl={d.export_url}
                     applied={{ ...query, page: undefined }} onClose={() => setShowExport(false)} />
      )}

      {showImport && (
        <ImportModal importUrl={d.import_url} enrolment={d.enrolment}
                     onClose={() => setShowImport(false)}
                     onDone={(text) => { setShowImport(false); setMsg({ tone: 'success', text }); refresh(); }} />
      )}
    </div>
  );
}
