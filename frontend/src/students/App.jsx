import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet } from '../lib/api';
import { postForm } from '../lib/forms';
import ExportModal from './ExportModal';
import ImportModal from './ImportModal';
import BulkMessageModal from './BulkMessageModal';
import ImportPhotosModal from './ImportPhotosModal';
import { confirm, promptDialog, Empty, Pagination } from '../components/ui';
import { recentSearches, rememberSearch, clearSearches, recentViewed,
         savedFilters, saveFilter, deleteFilter } from '../lib/studprefs';

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
    house: applied.house || '', boarding: applied.boarding || '',
    sort: applied.sort || 'surname', order: applied.order || 'asc', search: applied.search || '',
    page: page || 1,
  };
  const urlHasFilters = !!(applied.gender || applied.religion || applied.stream || applied.subject
    || applied.class_id || applied.arm_id || applied.house || applied.boarding || applied.search);
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

// Initials for an avatar fallback (first + last word of a name).
function initials(name) {
  const parts = (name || '').split(' ').filter(Boolean);
  if (!parts.length) return '—';
  return ((parts[0][0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

// Student avatar: passport photo when present, else initials on a tinted tile.
// Falls back to initials if the photo URL fails to load (deleted/again-404),
// so a broken image never shows the browser's broken-image glyph.
function StudentAvatar({ name, photo, size = 40 }) {
  const [broken, setBroken] = useState(false);
  const dim = { width: size, height: size, minWidth: size };
  return (photo && !broken)
    ? <img className="stu-av" src={photo} alt="" loading="lazy" style={dim} onError={() => setBroken(true)} />
    : <span className="stu-av stu-av-ph" aria-hidden="true" style={dim}>{initials(name)}</span>;
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
  const [showImportPhotos, setShowImportPhotos] = useState(false);
  const [bulkStream, setBulkStream] = useState('');
  const [bulkGender, setBulkGender] = useState('');
  const [bulkSubject, setBulkSubject] = useState('');
  const [bulkHouse, setBulkHouse] = useState('');
  const [bulkBoarding, setBulkBoarding] = useState('');
  const [bulkUni, setBulkUni] = useState('');
  const [bulkCourse, setBulkCourse] = useState('');
  const [showMessage, setShowMessage] = useState(false);
  const [menuFor, setMenuFor] = useState(null);   // which student card's ⋯ menu is open
  const [saved, setSaved] = useState(() => savedFilters());
  const [recentQ, setRecentQ] = useState(() => recentSearches());
  const viewed = useRef(recentViewed()).current;   // recently-viewed snapshot (page load)
  const [showSaved, setShowSaved] = useState(false);
  // Close the open row menu on any outside click (deferred so the opening click
  // doesn't immediately close it).
  useEffect(() => {
    if (menuFor == null) return undefined;
    const close = () => setMenuFor(null);
    const t = setTimeout(() => document.addEventListener('click', close, { once: true }), 0);
    return () => { clearTimeout(t); document.removeEventListener('click', close); };
  }, [menuFor]);
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

  // Debounced search → query. Once a term settles, remember it for quick reuse.
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery((q) => (q.search === search ? q : { ...q, search, page: 1 }));
      if (search.trim().length >= 2) { rememberSearch(search); setRecentQ(recentSearches()); }
    }, 500);
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
    || query.subject || query.class_id || query.arm_id || query.house || query.boarding);
  const resetFilters = () => {
    setSearch('');
    setQuery({ gender: '', religion: '', stream: '', subject: '', class_id: '', arm_id: '',
               house: '', boarding: '', sort: 'surname', order: 'asc', search: '', page: 1 });
  };
  // Apply a saved filter set: restore its query and mirror the search box.
  const applySaved = (f) => {
    const q = { ...query, ...f.query, page: 1 };
    setSearch(q.search || '');
    setQuery(q);
  };
  const doSaveFilter = async () => {
    const name = (await promptDialog({ title: 'Save filter set',
      label: 'Name this filter set', placeholder: 'e.g. SS3 Science boarders' }) || '').trim();
    if (!name) return;
    setSaved(saveFilter(name, { ...query, search }));
    setShowSaved(true);
  };
  const removeSaved = (name) => setSaved(deleteFilter(name));

  const allOnPage = students.length && students.every((s) => selected.has(s.id));
  const toggleSel = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected((s) => {
    const n = new Set(s); const ids = students.map((x) => x.id);
    if (ids.every((i) => n.has(i))) ids.forEach((i) => n.delete(i)); else ids.forEach((i) => n.add(i));
    return n;
  });
  const selectedIds = [...selected];
  const summary = d.summary || {};

  // One-click export in a given format using the default field set (mirrors the
  // Export modal's defaults) — powers the rail's Quick export buttons. Respects
  // the current selection, else the active filters.
  const quickExport = (format) => {
    if (!d.export_url) return;
    const p = new URLSearchParams();
    p.set('format', format);
    p.set('fields', JSON.stringify(['student_id', 'surname', 'first_name', 'gender', 'current_class']));
    if (selectedIds.length) p.set('student_ids', JSON.stringify(selectedIds));
    else Object.entries({ ...query, page: undefined }).forEach(([k, v]) => { if (v) p.set(k, v); });
    window.location.href = `${d.export_url}?${p.toString()}`;
  };

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

  // Whole-class ID-card sheet: POST the selection and download the returned PDF.
  const downloadIdCards = async () => {
    if (!needSel()) return;
    setMsg({ tone: 'info', text: `Building ID cards for ${selectedIds.length} student(s)…` });
    try {
      const res = await postForm(d.bulk_id_cards_url, { student_ids: selectedIds });
      if (!res.ok) {
        let text = 'Could not build ID cards.';
        try { const j = await res.json(); if (j.error) text = j.error; } catch (_) { /* not json */ }
        setMsg({ tone: 'error', text }); return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `id_cards_${selectedIds.length}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      setMsg({ tone: 'success', text: `ID cards for ${selectedIds.length} student(s) downloaded.` });
    } catch (e) { setMsg({ tone: 'error', text: e.message || 'Download failed.' }); }
  };

  // Row-level ⋯ menu (graduate / delete) — shared by the table and the cards.
  const renderRowMenu = (s) => canManage && (
    <div className="stu-menu-wrap" style={{ position: 'relative' }}>
      <button type="button" className="stu-act stu-act-caret" aria-haspopup="true" aria-expanded={menuFor === s.id}
              aria-label="More actions" onClick={(e) => { e.stopPropagation(); setMenuFor(menuFor === s.id ? null : s.id); }}>
        <i aria-hidden="true" className="fas fa-chevron-down" /></button>
      {menuFor === s.id && (
        <div className="row-menu" role="menu">
          <button type="button" role="menuitem" onClick={async () => { setMenuFor(null); if (await confirm(`${s.is_graduated ? 'Undo graduation for' : 'Mark as graduate:'} ${s.name}?`)) runAction(s.graduate_url, {}, 'Updated graduation status.'); }}>
            <i aria-hidden="true" className={'fas ' + (s.is_graduated ? 'fa-rotate-left' : 'fa-user-graduate')} /> {s.is_graduated ? 'Undo graduate' : 'Mark as graduate'}</button>
          <button type="button" role="menuitem" className="danger" onClick={async () => { setMenuFor(null); if (await confirm({ title: 'Delete student', message: `Delete ${s.name}?`, confirmText: 'Delete', tone: 'danger' })) runAction(s.delete_url, {}, 'Student deleted.'); }}>
            <i aria-hidden="true" className="fas fa-trash" /> Delete</button>
        </div>
      )}
    </div>
  );
  const renderActions = (s) => (
    <>
      <a href={s.url} className="stu-act stu-act-view"><i aria-hidden="true" className="fas fa-eye" /> View</a>
      {canManage && <a href={s.edit_url} className="stu-act"><i aria-hidden="true" className="fas fa-pen" /> Edit</a>}
      {renderRowMenu(s)}
    </>
  );

  return (
    <div>
      <div className="page-header">
        <div><h1><i aria-hidden="true" className="fas fa-user-graduate" /> Students</h1></div>
        <div className="page-header-actions stu-toolbar">
          {d.can_add && <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Student</a>}
          {d.can_add && <button type="button" className="btn btn-outline" onClick={() => setShowImport(true)}><i aria-hidden="true" className="fas fa-paste" /> Import (paste)</button>}
          {d.import_photos_url && <button type="button" className="btn btn-outline" onClick={() => setShowImportPhotos(true)}><i aria-hidden="true" className="fas fa-images" /> Import photos</button>}
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

      <div className="stu-shell">
      <div className="stu-main">
      <div className="card"><div className="card-body">
        <div className="stu-filters-head">
          <span className="stu-filters-title"><i aria-hidden="true" className="fas fa-sliders" /> Search &amp; Filters</span>
          {hasFilters && (
            <button type="button" className="stu-clear-link" onClick={resetFilters}>
              <i aria-hidden="true" className="fas fa-rotate-left" /> Clear filters
            </button>
          )}
        </div>
        <div className="stu-filters">
          <Field label="Search" full>
            <span className="stu-search">
              <i className="fas fa-magnifying-glass stu-search-ic" aria-hidden="true" />
              <input className="form-control stu-search-input" type="search" list="stu-recent-searches"
                     placeholder="Search by name, ID, parent phone/name, NIN or JAMB reg…"
                     value={search} onChange={(e) => setSearch(e.target.value)} />
            </span>
            <datalist id="stu-recent-searches">
              {recentQ.map((t) => <option key={t} value={t} />)}
            </datalist>
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
          {(filters.houses || []).length > 0 && <Field label="House">
            <select className="form-control" value={query.house} onChange={(e) => setFilter('house', e.target.value)}>
              <option value="">All</option>
              {filters.houses.map((h) => <option key={h} value={h}>{h}</option>)}
            </select>
          </Field>}
          <Field label="Boarding">
            <select className="form-control" value={query.boarding} onChange={(e) => setFilter('boarding', e.target.value)}>
              <option value="">All</option><option>Day</option><option>Boarding</option>
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
        <div style={{ marginTop: '.5rem', display: 'flex', gap: '.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
          {hasFilters && (
            <button type="button" className="btn btn-light btn-sm" onClick={resetFilters}>
              <i aria-hidden="true" className="fas fa-xmark" /> Clear filters
            </button>
          )}
          {hasFilters && (
            <button type="button" className="btn btn-light btn-sm" onClick={doSaveFilter} title="Save the current search + filters for one-click reuse">
              <i aria-hidden="true" className="fas fa-bookmark" /> Save filter
            </button>
          )}
          {saved.length > 0 && (
            <button type="button" className="btn btn-light btn-sm" aria-expanded={showSaved} onClick={() => setShowSaved((v) => !v)}>
              <i aria-hidden="true" className="fas fa-star" /> Saved ({saved.length})
            </button>
          )}
        </div>
        {showSaved && saved.length > 0 && (
          <div className="stu-chips" style={{ marginTop: '.5rem', display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
            {saved.map((f) => (
              <span key={f.name} className="badge badge-info" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                <button type="button" style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0, font: 'inherit' }}
                        onClick={() => applySaved(f)}>{f.name}</button>
                <button type="button" aria-label={'Delete saved filter ' + f.name} title="Delete"
                        style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
                        onClick={() => removeSaved(f.name)}>×</button>
              </span>
            ))}
          </div>
        )}
      </div></div>

      {viewed.length > 0 && (
        <div className="stu-recent-mobile card"><div className="card-body">
          <div className="stu-recent-head"><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Recently viewed</div>
          <div className="stu-recent-strip">
            {viewed.slice(0, 10).map((v) => (
              <a key={v.id} href={v.url} className="stu-recent-chip" title={v.name}>
                <StudentAvatar name={v.name} photo={v.photo} size={48} />
                <span className="stu-recent-name">{v.name}</span>
                <span className="stu-recent-id">{v.student_id}</span>
              </a>
            ))}
          </div>
        </div></div>
      )}

      <div className="stu-bulkbar">
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', margin: 0 }}>
          <input type="checkbox" checked={!!allOnPage} onChange={toggleAll} /> Select page
        </label>
        <span className="stu-count">{selectedIds.length ? `${selectedIds.length} selected · ` : ''}{d.total || 0} student(s){loading ? ' · loading…' : ''}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: '.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowExport(true)}><i aria-hidden="true" className="fas fa-download" /> Export</button>
          {canBulk && selectedIds.length > 0 && <>
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
            <input className="form-control" style={{ width: 130 }} value={bulkHouse} placeholder="Set house…"
                   onChange={(e) => setBulkHouse(e.target.value)} aria-label="Bulk house" maxLength={40} />
            <button type="button" className="btn btn-primary btn-sm" disabled={!bulkHouse.trim()}
                    onClick={() => needSel() && runAction(d.bulk_house_url, { house: bulkHouse.trim(), student_ids: selectedIds }, 'House updated.')}>Apply</button>
            <select className="form-control" style={{ width: 'auto' }} value={bulkBoarding} onChange={(e) => setBulkBoarding(e.target.value)} aria-label="Bulk boarding status">
              <option value="">Set boarding…</option>
              <option value="Day">Day</option>
              <option value="Boarding">Boarding</option>
            </select>
            <button type="button" className="btn btn-primary btn-sm" disabled={!bulkBoarding}
                    onClick={() => needSel() && runAction(d.bulk_boarding_url, { boarding: bulkBoarding, student_ids: selectedIds }, 'Boarding status updated.')}>Apply</button>
            {d.bulk_aspiration_url && (d.universities || []).length > 0 && <>
              <select className="form-control" style={{ width: 'auto', maxWidth: 170 }} value={bulkUni}
                      onChange={(e) => setBulkUni(e.target.value)} aria-label="Bulk university" title="Assign target university">
                <option value="">University…</option>
                {(d.universities || []).map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
              </select>
              <select className="form-control" style={{ width: 'auto', maxWidth: 170 }} value={bulkCourse}
                      onChange={(e) => setBulkCourse(e.target.value)} aria-label="Bulk course" title="Assign target course (fills JAMB target + subjects)">
                <option value="">Course…</option>
                {(d.courses || []).map((cc) => <option key={cc.id} value={cc.id}>{cc.label}</option>)}
              </select>
              <button type="button" className="btn btn-primary btn-sm" disabled={!bulkUni && !bulkCourse}
                      title="Set the target university and/or course for the selected students (a course also fills their JAMB target + subject requirements)"
                      onClick={() => needSel() && runAction(d.bulk_aspiration_url,
                        { student_ids: selectedIds, target_university_id: bulkUni, target_course_id: bulkCourse },
                        'Aspiration assigned.')}>Assign aspiration</button>
            </>}
            {d.bulk_message_url && <button type="button" className="btn btn-info btn-sm" title="Draft a message to the selected students' parents"
                    onClick={() => needSel() && setShowMessage(true)}><i aria-hidden="true" className="fas fa-comment-dots" /> Message parents</button>}
            {d.bulk_id_cards_url && <button type="button" className="btn btn-secondary btn-sm" title="Download printable ID cards for the selected students (6 per A4 sheet)"
                    onClick={downloadIdCards}><i aria-hidden="true" className="fas fa-id-card" /> Print ID cards</button>}
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

      {loading && students.length === 0 ? (
        <div className="card stu-tablecard"><div className="card-body">
          <div className="stu-cards" aria-busy="true" aria-label="Loading students">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="stu-card" style={{ display: 'block' }}>
                <div className="skeleton skeleton-title" style={{ width: '65%' }} />
                <div className="skeleton skeleton-text" />
                <div className="skeleton skeleton-text short" />
              </div>
            ))}
          </div>
        </div></div>
      ) : students.length === 0 ? (
        <Empty icon="fa-users" title="No students found">
          <p>No students match your filters yet.</p>
          {d.can_add && (
            <div className="empty-state-actions">
              <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add student</a>
              {d.import_url && <button type="button" className="btn btn-light" onClick={() => setShowImport(true)}><i aria-hidden="true" className="fas fa-paste" /> Import</button>}
            </div>
          )}
        </Empty>
      ) : (
        <>
          {/* Desktop: dense table */}
          <div className="card stu-tablecard">
            <div className="stu-table-wrap">
              <table className="data-table stu-table">
                <thead>
                  <tr>
                    <th className="stu-check-col"><input type="checkbox" checked={!!allOnPage} onChange={toggleAll} aria-label="Select page" /></th>
                    <th>Student</th><th>ID</th><th>Class / Arm</th><th>Stream</th>
                    <th>Gender</th><th>Age</th><th>Religion</th>
                    <th className="stu-act-col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.id} className={selected.has(s.id) ? 'is-sel' : ''}>
                      <td className="stu-check-col"><input type="checkbox" checked={selected.has(s.id)} onChange={() => toggleSel(s.id)} aria-label={'Select ' + s.name} /></td>
                      <td>
                        <a href={s.url} className="stu-row-student">
                          <StudentAvatar name={s.name} photo={s.photo_url} />
                          <span className="stu-row-name">{s.name}{s.is_graduated && <span className="badge badge-success stu-grad" title="Graduate"><i aria-hidden="true" className="fas fa-user-graduate" /></span>}</span>
                        </a>
                      </td>
                      <td className="text-muted">{s.student_id}</td>
                      <td>{s.current_class || '—'}</td>
                      <td>{s.stream ? <span className="badge badge-info">{s.stream}</span> : <span className="text-muted">—</span>}</td>
                      <td>{s.gender ? <span className={'stu-gender ' + (s.gender === 'Male' ? 'is-m' : 'is-f')}><i className={'fas ' + (s.gender === 'Male' ? 'fa-mars' : 'fa-venus')} aria-hidden="true" /> {s.gender}</span> : <span className="text-muted">—</span>}</td>
                      <td>{s.age || '—'}</td>
                      <td>{s.religion || <span className="text-muted">—</span>}</td>
                      <td className="stu-act-col"><div className="stu-row-actions">{renderActions(s)}</div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {/* Mobile: cards */}
          <div className="stu-cards">
            {students.map((s) => (
              <div key={s.id} className={'stu-card' + (selected.has(s.id) ? ' is-sel' : '')}>
                <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggleSel(s.id)} aria-label={'Select ' + s.name} />
                <StudentAvatar name={s.name} photo={s.photo_url} />
                <div className="stu-card-main">
                  <div className="stu-card-head">
                    <a href={s.url} className="stu-name">{s.name}{s.is_graduated && <span className="badge badge-success stu-grad" title="Graduate"><i aria-hidden="true" className="fas fa-user-graduate" /></span>}</a>
                    <span className="stu-sid">{s.student_id}</span>
                  </div>
                  <div className="stu-meta">
                    <span className="badge badge-secondary">{s.current_class || '—'}</span>
                    <span className={'badge ' + (s.gender === 'Male' ? 'badge-male' : 'badge-female')}>{s.gender}</span>
                    {s.stream && <span className="badge badge-info">{s.stream}</span>}
                    <span className="stu-meta-dim">Age {s.age || '—'}</span>
                    {s.religion && <span className="stu-meta-dim">{s.religion}</span>}
                  </div>
                  <div className="stu-actions">{renderActions(s)}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <Pagination page={d.page || 1} pages={d.pages || 1} onPage={goPage} />
      </div>{/* .stu-main */}

      <aside className="stu-rail">
        {viewed.length > 0 && (
          <div className="card stu-rail-card">
            <div className="card-header"><h3><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Recently viewed</h3></div>
            <div className="card-body stu-rail-recent">
              {viewed.slice(0, 8).map((v) => (
                <a key={v.id} href={v.url} className="stu-rr-item">
                  <span className="stu-rr-name">{v.name}</span>
                  <span className="stu-rr-id">{v.student_id}</span>
                </a>
              ))}
            </div>
          </div>
        )}
        <div className="card stu-rail-card">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-simple" /> Students summary</h3></div>
          <div className="card-body">
            <div className="stu-sum-grid">
              <div className="stu-sum stu-sum-total"><span className="stu-sum-v">{summary.total != null ? summary.total : (d.total || 0)}</span><span className="stu-sum-l">Total students</span></div>
              <div className="stu-sum"><span className="stu-sum-v">{summary.male || 0}</span><span className="stu-sum-l">Male</span></div>
              <div className="stu-sum"><span className="stu-sum-v">{summary.female || 0}</span><span className="stu-sum-l">Female</span></div>
              <div className="stu-sum"><span className="stu-sum-v">{summary.streams || 0}</span><span className="stu-sum-l">Streams</span></div>
            </div>
          </div>
        </div>
        <div className="card stu-rail-card">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-download" /> Quick export</h3></div>
          <div className="card-body stu-quick-export">
            <p className="text-muted text-sm" style={{ marginTop: 0 }}>Export {selectedIds.length ? `${selectedIds.length} selected` : 'the current list'}</p>
            <button type="button" className="btn btn-outline" onClick={() => quickExport('excel')}><i aria-hidden="true" className="fas fa-file-excel stu-x-excel" /> Excel (.xlsx)</button>
            <button type="button" className="btn btn-outline" onClick={() => quickExport('csv')}><i aria-hidden="true" className="fas fa-file-csv" /> CSV (.csv)</button>
            <button type="button" className="btn btn-outline" onClick={() => quickExport('pdf')}><i aria-hidden="true" className="fas fa-file-pdf stu-x-pdf" /> PDF (.pdf)</button>
            <button type="button" className="btn btn-light btn-sm" onClick={() => setShowExport(true)}><i aria-hidden="true" className="fas fa-sliders" /> More formats &amp; fields…</button>
          </div>
        </div>
        <div className="card stu-rail-card stu-tips">
          <div className="card-body">
            <div className="stu-tips-head"><i aria-hidden="true" className="fas fa-lightbulb" /> Tips</div>
            <p className="text-muted text-sm">Use the filters to find students fast, then export the list for offline use. Select rows to message parents or print ID cards.</p>
          </div>
        </div>
      </aside>
      </div>{/* .stu-shell */}

      {showExport && (
        <ExportModal total={d.total || 0} selectedIds={selectedIds} exportUrl={d.export_url}
                     applied={{ ...query, page: undefined }} onClose={() => setShowExport(false)} />
      )}

      {showImport && (
        <ImportModal importUrl={d.import_url} enrolment={d.enrolment}
                     onClose={() => setShowImport(false)}
                     onDone={(text) => { setShowImport(false); setMsg({ tone: 'success', text }); refresh(); }} />
      )}

      {showImportPhotos && (
        <ImportPhotosModal importUrl={d.import_photos_url}
                     onClose={() => setShowImportPhotos(false)}
                     onDone={(text) => { setMsg({ tone: 'success', text }); refresh(); }} />
      )}

      {showMessage && (
        <BulkMessageModal count={selectedIds.length} selectedIds={selectedIds} messageUrl={d.bulk_message_url}
                          onClose={() => setShowMessage(false)}
                          onDone={(j) => {
                            setShowMessage(false);
                            setMsg({ tone: 'success', text: (
                              <span>{j.info || 'Message drafted.'}{' '}
                                {j.review_url && <a href={j.review_url}>Review &amp; send →</a>}</span>
                            ) });
                          }} />
      )}
    </div>
  );
}
