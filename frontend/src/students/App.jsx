import React, { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { apiGet } from '../lib/api';
import { postForm } from '../lib/forms';
import { canWrite } from '../lib/perms';
import ExportModal from './ExportModal';
import ImportModal from './ImportModal';
import UpdateImportModal from './UpdateImportModal';
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

// "Class: JSS3 · Gold · Female · “ada”" — the active filters, for the Export dialog.
function exportFilterText(q, filters) {
  const bits = [];
  const find = (list, id) => (list || []).find((x) => String(x.id) === String(id));
  const c = q.class_id && find(filters.classes, q.class_id);
  const a = q.arm_id && find(filters.arms, q.arm_id);
  if (c) bits.push('Class: ' + c.name + (a ? ' ' + a.name : ' · all arms'));
  else if (a) bits.push('Arm: ' + a.name);
  if (q.gender) bits.push(q.gender);
  if (q.religion) bits.push(q.religion);
  if (q.stream) bits.push(q.stream);
  if (q.profile) bits.push(profileLabel(filters, q.profile));
  if (q.search) bits.push('“' + q.search + '”');
  return bits.join(' · ');
}

function profileLabel(filters, key) {
  for (const g of (filters && filters.profile) || []) {
    const o = g.options.find((x) => x.value === key);
    if (o) return o.label;
  }
  return key === 'incomplete' ? 'Incomplete profile' : key;
}

// Saved filter sets from before the Profile filter used the old
// `incomplete: '1'` key — carry them over to `profile: 'incomplete'`.
function migrateQuery(q) {
  if (!q || !('incomplete' in q)) return q;
  const { incomplete, ...rest } = q;
  return { ...rest, profile: rest.profile || (incomplete === '1' ? 'incomplete' : '') };
}

function startState(applied, page) {
  const base = {
    gender: applied.gender || '', religion: applied.religion || '', stream: applied.stream || '',
    subject: applied.subject || '', class_id: applied.class_id || '', arm_id: applied.arm_id || '',
    house: applied.house || '', boarding: applied.boarding || '', profile: applied.profile || '',
    sort: applied.sort || 'surname', order: applied.order || 'asc', search: applied.search || '',
    page: page || 1,
  };
  const urlHasFilters = !!(applied.gender || applied.religion || applied.stream || applied.subject
    || applied.class_id || applied.arm_id || applied.house || applied.boarding || applied.profile
    || applied.search);
  if (!urlHasFilters && cameFromStudentPage()) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(FILTER_KEY) || 'null');
      if (saved && typeof saved === 'object') {
        return { query: migrateQuery({ ...base, ...saved, page: saved.page || 1 }), restored: true };
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
// A stable colour per name, so a long list isn't a wall of identical circles.
const AV_HUES = [210, 262, 330, 20, 160, 190, 45, 290, 0, 140];
function hueFor(name) {
  let h = 0;
  for (let i = 0; i < (name || '').length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return AV_HUES[h % AV_HUES.length];
}
function StudentAvatar({ name, photo, size = 40, tint = false }) {
  const [broken, setBroken] = useState(false);
  const dim = { width: size, height: size, minWidth: size, fontSize: Math.round(size * 0.36) };
  const hue = hueFor(name);
  const tinted = tint ? { ...dim, background: `hsl(${hue} 70% 92%)`, color: `hsl(${hue} 55% 36%)` } : dim;
  return (photo && !broken)
    ? <img className="stu-av" src={photo} alt="" loading="lazy" style={dim} onError={() => setBroken(true)} />
    : <span className={'stu-av stu-av-ph' + (tint ? ' tinted' : '')} aria-hidden="true" style={tinted}>{initials(name)}</span>;
}

// Small dropdown menu (header actions, export, row ⋯). Closes on outside click / Esc.
function Menu({ label, icon, items, align = 'right', className = 'btn btn-outline', title }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('touchstart', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('touchstart', close); document.removeEventListener('keydown', esc); };
  }, [open]);
  const list = items.filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="sl-menu" ref={ref}>
      <button type="button" className={className} aria-haspopup="true" aria-expanded={open} title={title}
              aria-label={label ? undefined : title} onClick={() => setOpen((v) => !v)}>
        {icon && <i aria-hidden="true" className={'fas ' + icon} />}{label && <span>{label}</span>}
        {label && <i aria-hidden="true" className="fas fa-chevron-down sl-caret" />}
      </button>
      {open && (
        <div className={'sl-menu-pop ' + align} role="menu">
          {list.map((it, i) => it.href
            ? <a key={i} role="menuitem" href={it.href} className={it.danger ? 'danger' : ''} onClick={() => setOpen(false)}>
                <i aria-hidden="true" className={'fas ' + it.icon} /> {it.label}</a>
            : <button key={i} type="button" role="menuitem" className={it.danger ? 'danger' : ''}
                      onClick={() => { setOpen(false); it.onClick(); }}>
                <i aria-hidden="true" className={'fas ' + it.icon} /> {it.label}</button>)}
        </div>
      )}
    </div>
  );
}

function useMedia(query) {
  const get = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false);
  const [m, setM] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const on = () => setM(mq.matches);
    if (mq.addEventListener) mq.addEventListener('change', on); else mq.addListener(on);
    return () => { if (mq.removeEventListener) mq.removeEventListener('change', on); else mq.removeListener(on); };
  }, [query]);
  return m;
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
  const [showUpdateImport, setShowUpdateImport] = useState(false);
  const [showImportPhotos, setShowImportPhotos] = useState(false);
  const [bulkStream, setBulkStream] = useState('');
  const [bulkGender, setBulkGender] = useState('');
  const [bulkSubject, setBulkSubject] = useState('');
  const [bulkHouse, setBulkHouse] = useState('');
  const [bulkBoarding, setBulkBoarding] = useState('');
  const [bulkUni, setBulkUni] = useState('');
  const [bulkCourse, setBulkCourse] = useState('');
  const [showMessage, setShowMessage] = useState(false);
  const [saved, setSaved] = useState(() => savedFilters());
  const [recentQ, setRecentQ] = useState(() => recentSearches());
  const viewed = useRef(recentViewed()).current;   // recently-viewed snapshot (page load)
  const [showSaved, setShowSaved] = useState(false);
  // When filters were restored, the server-rendered page doesn't match them, so
  // let the first effect run fetch fresh (filtered) data instead of skipping it.
  const skip = useRef(!start.restored);

  // The universities/courses catalogue (1000+ / 600+ rows) for the bulk
  // "assign aspiration" dropdowns isn't in the list payload — it's fetched
  // once, lazily, only once the bulk-assign controls actually appear, so a
  // plain visit to the list (or any filter/page/sort change) never has to
  // move that dead weight over the wire. Cached in state for the rest of
  // this page visit once loaded.
  const [aspirationLists, setAspirationLists] = useState(null);
  const [loadingAspiration, setLoadingAspiration] = useState(false);

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

  // Fetch the universities/courses catalogue only once the bulk-assign
  // controls are actually shown (a bulk-capable user has selected at least
  // one student), and only once per visit.
  useEffect(() => {
    const url = data && data.aspiration_lists_url;
    const canShow = data && data.can_bulk && selected.size > 0;
    if (!canShow || !url || aspirationLists || loadingAspiration) return;
    setLoadingAspiration(true);
    apiGet(url).then(setAspirationLists).catch(() => {}).finally(() => setLoadingAspiration(false));
  }, [data, selected, aspirationLists, loadingAspiration]);

  const d = data || {};
  const students = d.students || [];
  const filters = d.filters || {};
  const canAdd = canWrite(d, 'create');
  const canEditStudent = canWrite(d, 'edit');
  const canDeleteStudent = canWrite(d, 'delete');
  const canAdmin = !!d.can_admin;   // admin-only bulk tools (subject / delete)
  const canBulk = !!d.can_bulk;     // mass-assign gender/stream (admins + teachers, scoped)
  const canSss3 = !!d.can_sss3;     // SSS3-only WAEC subject filter/tools
  const setFilter = (k, v) => setQuery((q) => ({ ...q, [k]: v, page: 1 }));
  const goPage = (p) => setQuery((q) => ({ ...q, page: p }));
  const hasFilters = !!(search || query.gender || query.religion || query.stream
    || query.subject || query.class_id || query.arm_id || query.house || query.boarding
    || query.profile);
  const resetFilters = () => {
    setSearch('');
    setQuery({ gender: '', religion: '', stream: '', subject: '', class_id: '', arm_id: '',
               house: '', boarding: '', profile: '', sort: 'surname', order: 'asc', search: '', page: 1 });
  };
  // Apply a saved filter set: restore its query and mirror the search box.
  const applySaved = (f) => {
    const q = migrateQuery({ ...query, ...f.query, page: 1 });
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
    p.set('fields', JSON.stringify(['student_id', 'name', 'gender', 'current_class']));
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

  // ── Layout state ──
  const phone = useMedia('(max-width: 759px)');
  const [selectMode, setSelectMode] = useState(false);       // phone: checkboxes only in Select mode
  const [showFilters, setShowFilters] = useState(false);     // laptop: panel · phone: bottom sheet
  const [showBulk, setShowBulk] = useState(false);
  const showChecks = !phone || selectMode;
  useEffect(() => { if (!selectedIds.length) setShowBulk(false); }, [selectedIds.length]);

  const find = (list, id) => (list || []).find((x) => String(x.id) === String(id));
  // Active filters as removable chips.
  const chips = [
    query.class_id && { k: 'class_id', label: (find(filters.classes, query.class_id) || {}).name || 'Class' },
    query.arm_id && { k: 'arm_id', label: 'Arm ' + ((find(filters.arms, query.arm_id) || {}).name || '') },
    query.gender && { k: 'gender', label: query.gender },
    query.religion && { k: 'religion', label: query.religion },
    query.stream && { k: 'stream', label: query.stream },
    query.house && { k: 'house', label: query.house },
    query.boarding && { k: 'boarding', label: query.boarding },
    query.profile && { k: 'profile', label: profileLabel(filters, query.profile) },
    query.subject && { k: 'subject', label: 'WAEC: ' + query.subject },
  ].filter(Boolean);
  // Filters not shown inline on the laptop bar (class / arm / gender are inline).
  const moreCount = chips.filter((c) => !['class_id', 'arm_id', 'gender'].includes(c.k)).length
    + (query.sort !== 'surname' || query.order !== 'asc' ? 1 : 0);

  const sortSelect = (
    <select className="form-control" value={query.sort + '|' + query.order} aria-label="Sort by"
            onChange={(e) => { const [so, o] = e.target.value.split('|'); setQuery((q) => ({ ...q, sort: so, order: o, page: 1 })); }}>
      {SORTS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
    </select>
  );
  const classSel = (
    <select className="form-control" value={query.class_id} onChange={(e) => setFilter('class_id', e.target.value)} aria-label="Class">
      <option value="">All classes</option>
      {(filters.classes || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
  );
  const armSel = (
    <select className="form-control" value={query.arm_id} onChange={(e) => setFilter('arm_id', e.target.value)} aria-label="Arm">
      <option value="">All arms</option>
      {(filters.arms || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
  );
  const genderSel = (
    <select className="form-control" value={query.gender} onChange={(e) => setFilter('gender', e.target.value)} aria-label="Gender">
      <option value="">Boys &amp; girls</option><option value="Male">Male</option><option value="Female">Female</option>
    </select>
  );
  const moreFilters = (
    <div className="sl-filter-grid">
      {phone && <><Field label="Class">{classSel}</Field><Field label="Arm">{armSel}</Field><Field label="Gender">{genderSel}</Field></>}
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
      <Field label="Profile & records">
        <select className="form-control" value={query.profile} onChange={(e) => setFilter('profile', e.target.value)}>
          <option value="">Any</option>
          {(filters.profile || []).map((g) => (
            <optgroup key={g.group} label={g.group}>
              {g.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </optgroup>))}
        </select>
      </Field>
      {canSss3 && <Field label="WAEC subject (SSS3)">
        <select className="form-control" value={query.subject} onChange={(e) => setFilter('subject', e.target.value)}>
          <option value="">All</option>
          {(filters.subjects || []).map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </Field>}
      <Field label="Sort by">{sortSelect}</Field>
    </div>
  );

  const importItems = [
    canAdd && { label: 'Import students (paste)', icon: 'fa-paste', onClick: () => setShowImport(true) },
    d.update_import_url && { label: 'Update students (paste)', icon: 'fa-pen-to-square', onClick: () => setShowUpdateImport(true) },
    d.import_photos_url && { label: 'Import photos', icon: 'fa-images', onClick: () => setShowImportPhotos(true) },
  ];
  const exportItems = [
    { label: 'Excel (.xlsx)', icon: 'fa-file-excel', onClick: () => quickExport('excel') },
    { label: 'CSV (.csv)', icon: 'fa-file-csv', onClick: () => quickExport('csv') },
    { label: 'PDF (.pdf)', icon: 'fa-file-pdf', onClick: () => quickExport('pdf') },
    { label: 'More formats & fields…', icon: 'fa-sliders', onClick: () => setShowExport(true) },
  ];
  const moreItems = [
    canAdmin && { label: 'Fill WAEC subjects by stream', icon: 'fa-wand-magic-sparkles',
      onClick: async () => { if (await confirm("Fill WAEC subjects from stream for students who don't have them set?"))
        runAction(d.waec_by_stream_url, {}, 'WAEC subjects filled from stream.'); } },
    d.trash_url && { label: 'Deleted students (trash)', icon: 'fa-trash', href: d.trash_url },
  ];
  const rowItems = (s) => [
    phone && canEditStudent && { label: 'Edit', icon: 'fa-pen', href: s.edit_url },
    canEditStudent && { label: s.is_graduated ? 'Undo graduate' : 'Mark as graduate', icon: s.is_graduated ? 'fa-rotate-left' : 'fa-user-graduate',
      onClick: async () => { if (await confirm(`${s.is_graduated ? 'Undo graduation for' : 'Mark as graduate:'} ${s.name}?`)) runAction(s.graduate_url, {}, 'Updated graduation status.'); } },
    canDeleteStudent && { label: 'Delete', icon: 'fa-trash', danger: true,
      onClick: async () => { if (await confirm({ title: 'Delete student', message: `Delete ${s.name}?`, confirmText: 'Delete', tone: 'danger' })) runAction(s.delete_url, {}, 'Student deleted.'); } },
  ];

  return (
    <div className={'sl' + (selectedIds.length ? ' has-sel' : '')}>
      {/* Header: title + live summary + actions */}
      <header className="sl-head">
        <div className="sl-title">
          <h1>Students</h1>
          <p>
            <b>{summary.total != null ? summary.total : (d.total || 0)}</b> students
            <span className="sl-dot" /> <i aria-hidden="true" className="fas fa-mars sl-m" /> {summary.male || 0}
            <span className="sl-dot" /> <i aria-hidden="true" className="fas fa-venus sl-f" /> {summary.female || 0}
            {summary.streams ? <><span className="sl-dot" />{summary.streams} stream{summary.streams === 1 ? '' : 's'}</> : null}
          </p>
        </div>
        <div className="sl-actions">
          {phone && students.length > 0 && (canBulk || d.bulk_message_url || d.bulk_id_cards_url || canAdmin) && (
            <button type="button" className={'sl-iconbtn' + (selectMode ? ' on' : '')} onClick={() => { setSelectMode((v) => !v); setSelected(new Set()); }}
                    aria-pressed={selectMode}>{selectMode ? 'Done' : 'Select'}</button>
          )}
          {!phone && canAdd && <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add student</a>}
          <Menu label={phone ? '' : 'Import'} icon="fa-file-import" items={importItems} title="Import" className={phone ? 'sl-iconbtn' : 'btn btn-outline'} />
          <Menu label={phone ? '' : 'Export'} icon="fa-download" items={exportItems} title="Export" className={phone ? 'sl-iconbtn' : 'btn btn-outline'} />
          <Menu icon="fa-ellipsis" items={moreItems} title="More" className={phone ? 'sl-iconbtn' : 'btn btn-outline sl-more'} />
        </div>
      </header>

      {msg && (
        <div className={'alert alert-' + ({ success: 'success', error: 'danger', warn: 'warning' }[msg.tone] || 'info')}
             role="status" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, margin: 0 }}>
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

      {/* Search + filters bar (sticky) */}
      <div className="sl-bar">
        <span className="sl-search">
          <i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" list="stu-recent-searches" aria-label="Search students"
                 placeholder={phone ? 'Search students' : 'Search name, ID, parent phone or name, NIN, JAMB reg…'}
                 value={search} onChange={(e) => setSearch(e.target.value)} />
          {loading && <i className="fas fa-circle-notch fa-spin sl-spin" aria-hidden="true" />}
        </span>
        <datalist id="stu-recent-searches">{recentQ.map((t) => <option key={t} value={t} />)}</datalist>
        {!phone && <>{classSel}{armSel}{genderSel}</>}
        <button type="button" className={'sl-filter-btn' + (showFilters ? ' on' : '')} aria-expanded={showFilters}
                onClick={() => setShowFilters((v) => !v)}>
          <i aria-hidden="true" className="fas fa-sliders" />{!phone && <span>Filters</span>}
          {(phone ? chips.length : moreCount) > 0 && <b className="sl-badge">{phone ? chips.length : moreCount}</b>}
        </button>
      </div>

      {/* Laptop: the rest of the filters, in place */}
      {showFilters && !phone && <div className="sl-panel">{moreFilters}</div>}

      {/* Phone: filters in a bottom sheet */}
      {showFilters && phone && createPortal((
        <div className="sl-sheet-bg" onClick={() => setShowFilters(false)}>
          <div className="sl-sheet" role="dialog" aria-modal="true" aria-label="Filters" onClick={(e) => e.stopPropagation()}>
            <div className="sl-sheet-grip" aria-hidden="true" />
            <div className="sl-sheet-head"><b>Filters</b>
              {hasFilters && <button type="button" className="sl-link" onClick={resetFilters}>Reset</button>}</div>
            {moreFilters}
            <button type="button" className="btn btn-primary sl-sheet-done" onClick={() => setShowFilters(false)}>
              Show {d.total || 0} student{d.total === 1 ? '' : 's'}</button>
          </div>
        </div>
      ), document.body)}

      {/* Active filters + saved filter sets */}
      {(chips.length > 0 || search || saved.length > 0) && (
        <div className="sl-chips">
          {search && <button type="button" className="sl-chip" onClick={() => setSearch('')}>“{search}” <i aria-hidden="true" className="fas fa-xmark" /></button>}
          {chips.map((c) => (
            <button key={c.k} type="button" className="sl-chip" onClick={() => setFilter(c.k, '')} aria-label={'Remove filter ' + c.label}>
              {c.label} <i aria-hidden="true" className="fas fa-xmark" /></button>
          ))}
          {hasFilters && <button type="button" className="sl-link" onClick={resetFilters}>Clear all</button>}
          {hasFilters && <button type="button" className="sl-link" onClick={doSaveFilter}><i aria-hidden="true" className="fas fa-bookmark" /> Save</button>}
          {saved.length > 0 && <button type="button" className="sl-link" aria-expanded={showSaved} onClick={() => setShowSaved((v) => !v)}>
            <i aria-hidden="true" className="fas fa-star" /> Saved ({saved.length})</button>}
          {showSaved && saved.map((f) => (
            <span key={f.name} className="sl-chip saved">
              <button type="button" onClick={() => applySaved(f)}>{f.name}</button>
              <button type="button" aria-label={'Delete saved filter ' + f.name} onClick={() => removeSaved(f.name)}>×</button>
            </span>
          ))}
        </div>
      )}

      {/* Recently viewed — one tap back to a student */}
      {viewed.length > 0 && !hasFilters && (
        <div className="sl-recent" aria-label="Recently viewed">
          <span className="sl-recent-l"><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Recent</span>
          {viewed.slice(0, 10).map((v) => (
            <a key={v.id} href={v.url} className="sl-recent-chip" title={v.name}>
              <StudentAvatar name={v.name} photo={v.photo} size={26} /><span>{v.name}</span>
            </a>
          ))}
        </div>
      )}

      {/* Selection bar: appears when students are selected (phone: docked at the bottom) */}
      {selectedIds.length > 0 && (
        <div className="sl-selbar" role="region" aria-label="Selected students">
          <div className="sl-selbar-top">
            <b>{selectedIds.length} selected</b>
            <button type="button" className="sl-link" onClick={() => setSelected(new Set())}>Clear</button>
            <span className="sl-selbar-acts">
              {d.bulk_message_url && <button type="button" className="btn btn-sm btn-info" aria-label="Message parents" title="Message parents" onClick={() => needSel() && setShowMessage(true)}>
                <i aria-hidden="true" className="fas fa-comment-dots" /><span> Message parents</span></button>}
              {d.bulk_id_cards_url && <button type="button" className="btn btn-sm btn-secondary" aria-label="Print ID cards" title="Print ID cards" onClick={downloadIdCards}>
                <i aria-hidden="true" className="fas fa-id-card" /><span> ID cards</span></button>}
              <button type="button" className="btn btn-sm btn-secondary" aria-label="Export selected" title="Export selected" onClick={() => setShowExport(true)}>
                <i aria-hidden="true" className="fas fa-download" /><span> Export</span></button>
              {(canBulk || canSss3) && <button type="button" className={'btn btn-sm ' + (showBulk ? 'btn-primary' : 'btn-outline')} aria-expanded={showBulk} aria-label="Bulk edit" title="Bulk edit"
                      onClick={() => setShowBulk((v) => !v)}><i aria-hidden="true" className="fas fa-pen-to-square" /><span> Bulk edit</span></button>}
              {canAdmin && <button type="button" className="btn btn-sm btn-danger" aria-label="Delete selected"
                      onClick={async () => { if (needSel() && await confirm({ title: 'Delete students', message: `Delete ${selectedIds.length} selected student(s)?`, confirmText: 'Delete', tone: 'danger' }))
                        runAction(d.bulk_delete_url, { student_ids: selectedIds }, 'Deleted selected students.'); }}><i aria-hidden="true" className="fas fa-trash" /></button>}
            </span>
          </div>
          {showBulk && (
            <div className="sl-bulk">
              {canBulk && <>
                <span className="sl-bulk-f"><select className="form-control" value={bulkGender} onChange={(e) => setBulkGender(e.target.value)} aria-label="Bulk gender">
                  <option value="">Set gender…</option><option value="Male">Male</option><option value="Female">Female</option></select>
                  <button type="button" className="btn btn-primary btn-sm" disabled={!bulkGender}
                          onClick={() => needSel() && runAction(d.bulk_gender_url, { gender: bulkGender, student_ids: selectedIds }, 'Gender updated.')}>Apply</button></span>
                <span className="sl-bulk-f"><select className="form-control" value={bulkStream} onChange={(e) => setBulkStream(e.target.value)} aria-label="Bulk stream">
                  <option value="">Set stream…</option>{(filters.streams || []).map((r) => <option key={r} value={r}>{r}</option>)}</select>
                  <button type="button" className="btn btn-primary btn-sm" disabled={!bulkStream} title="Also fills WAEC subjects from the stream where not already set"
                          onClick={() => needSel() && runAction(d.bulk_stream_url, { stream: bulkStream, student_ids: selectedIds }, 'Stream updated.')}>Apply</button></span>
                <span className="sl-bulk-f"><input className="form-control" value={bulkHouse} placeholder="Set house…" onChange={(e) => setBulkHouse(e.target.value)} aria-label="Bulk house" maxLength={40} />
                  <button type="button" className="btn btn-primary btn-sm" disabled={!bulkHouse.trim()}
                          onClick={() => needSel() && runAction(d.bulk_house_url, { house: bulkHouse.trim(), student_ids: selectedIds }, 'House updated.')}>Apply</button></span>
                <span className="sl-bulk-f"><select className="form-control" value={bulkBoarding} onChange={(e) => setBulkBoarding(e.target.value)} aria-label="Bulk boarding status">
                  <option value="">Set boarding…</option><option value="Day">Day</option><option value="Boarding">Boarding</option></select>
                  <button type="button" className="btn btn-primary btn-sm" disabled={!bulkBoarding}
                          onClick={() => needSel() && runAction(d.bulk_boarding_url, { boarding: bulkBoarding, student_ids: selectedIds }, 'Boarding status updated.')}>Apply</button></span>
                {d.bulk_aspiration_url && <span className="sl-bulk-f wide">
                  <select className="form-control" value={bulkUni} onChange={(e) => setBulkUni(e.target.value)} aria-label="Bulk university" disabled={loadingAspiration}>
                    <option value="">{loadingAspiration ? 'Loading…' : 'Target university…'}</option>
                    {(aspirationLists && aspirationLists.universities || []).map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}</select>
                  <select className="form-control" value={bulkCourse} onChange={(e) => setBulkCourse(e.target.value)} aria-label="Bulk course" disabled={loadingAspiration}>
                    <option value="">{loadingAspiration ? 'Loading…' : 'Target course…'}</option>
                    {(aspirationLists && aspirationLists.courses || []).map((cc) => <option key={cc.id} value={cc.id}>{cc.label}</option>)}</select>
                  <button type="button" className="btn btn-primary btn-sm" disabled={!bulkUni && !bulkCourse}
                          title="A course also fills their JAMB target + subject requirements"
                          onClick={() => needSel() && runAction(d.bulk_aspiration_url,
                            { student_ids: selectedIds, target_university_id: bulkUni, target_course_id: bulkCourse }, 'Aspiration assigned.')}>Assign</button></span>}
              </>}
              {canSss3 && <span className="sl-bulk-f"><select className="form-control" value={bulkSubject} onChange={(e) => setBulkSubject(e.target.value)} aria-label="Bulk WAEC subject">
                <option value="">Add WAEC subject…</option>{(filters.subjects || []).map((r) => <option key={r} value={r}>{r}</option>)}</select>
                <button type="button" className="btn btn-primary btn-sm" disabled={!bulkSubject} title="SSS3 students only"
                        onClick={() => needSel() && runAction(d.bulk_subject_url, { subject: bulkSubject, student_ids: selectedIds }, 'Subject added.')}>Add (SSS3)</button></span>}
            </div>
          )}
        </div>
      )}

      {loading && students.length === 0 ? (
        <div className="sl-list" aria-busy="true" aria-label="Loading students">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="sl-row sl-skel"><span className="skeleton" style={{ width: 40, height: 40, borderRadius: '50%' }} />
              <div style={{ flex: 1 }}><div className="skeleton skeleton-title" style={{ width: '55%' }} /><div className="skeleton skeleton-text short" /></div></div>
          ))}
        </div>
      ) : students.length === 0 ? (
        <Empty icon="fa-users" title="No students found">
          <p>No students match your filters yet.</p>
          {hasFilters && <div className="empty-state-actions"><button type="button" className="btn btn-light" onClick={resetFilters}>Clear filters</button></div>}
          {canAdd && !hasFilters && (
            <div className="empty-state-actions">
              <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add student</a>
              {d.import_url && <button type="button" className="btn btn-light" onClick={() => setShowImport(true)}><i aria-hidden="true" className="fas fa-paste" /> Import</button>}
            </div>
          )}
        </Empty>
      ) : phone ? (
        /* Phone: native-style list rows — tap to open, ⋯ for more */
        <div className={'sl-list' + (loading ? ' is-loading' : '')}>
          {selectMode && (
            <label className="sl-row sl-row-all"><input type="checkbox" checked={!!allOnPage} onChange={toggleAll} /> Select all on this page</label>
          )}
          {students.map((s, i) => {
            // A–Z section headers when the list is sorted by name (like a phone's contacts).
            const byName = (query.sort === 'surname' || query.sort === 'first_name');
            const letter = ((s.name || '').trim()[0] || '#').toUpperCase();
            const prev = i > 0 ? (((students[i - 1].name || '').trim()[0] || '#').toUpperCase()) : null;
            return (
              <React.Fragment key={s.id}>
                {byName && letter !== prev && <div className="sl-letter" aria-hidden="true">{letter}</div>}
                <div className={'sl-row' + (selected.has(s.id) ? ' is-sel' : '')}>
                  {showChecks && <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggleSel(s.id)} aria-label={'Select ' + s.name} />}
                  <a href={selectMode ? undefined : s.url} className="sl-row-main" onClick={selectMode ? (e) => { e.preventDefault(); toggleSel(s.id); } : undefined}>
                    <StudentAvatar name={s.name} photo={s.photo_url} size={42} tint />
                    <span className="sl-row-text">
                      <b>{s.name}{s.is_graduated && <i aria-hidden="true" className="fas fa-user-graduate sl-grad" title="Graduate" />}</b>
                      <small>
                        <span className={'sl-g ' + (s.gender === 'Male' ? 'm' : s.gender === 'Female' ? 'f' : '')} title={s.gender || ''} />
                        {s.current_class || 'No class'}<span className="sl-sep">·</span>{s.student_id}
                      </small>
                    </span>
                  </a>
                  {!selectMode && <Menu icon="fa-ellipsis-vertical" items={rowItems(s)} title={'More for ' + s.name} className="sl-rowbtn" />}
                </div>
              </React.Fragment>
            );
          })}
        </div>
      ) : (
        /* Laptop: full-width dense table */
        <div className={'sl-table-card' + (loading ? ' is-loading' : '')}>
          <table className="sl-table">
            <thead>
              <tr>
                <th className="sl-check"><input type="checkbox" checked={!!allOnPage} onChange={toggleAll} aria-label="Select page" /></th>
                <th>Student</th><th>Class</th><th>Stream</th><th>Gender</th><th className="num">Age</th><th>Religion</th><th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={s.id} className={selected.has(s.id) ? 'is-sel' : ''}>
                  <td className="sl-check"><input type="checkbox" checked={selected.has(s.id)} onChange={() => toggleSel(s.id)} aria-label={'Select ' + s.name} /></td>
                  <td><a href={s.url} className="sl-who"><StudentAvatar name={s.name} photo={s.photo_url} size={34} tint />
                    <span><b>{s.name}{s.is_graduated && <i aria-hidden="true" className="fas fa-user-graduate sl-grad" title="Graduate" />}</b><small>{s.student_id}</small></span></a></td>
                  <td>{s.current_class || <span className="text-muted">—</span>}</td>
                  <td>{s.stream ? <span className="sl-tag">{s.stream}</span> : <span className="text-muted">—</span>}</td>
                  <td>{s.gender ? <span className={'sl-gender ' + (s.gender === 'Male' ? 'm' : 'f')}><i className={'fas ' + (s.gender === 'Male' ? 'fa-mars' : 'fa-venus')} aria-hidden="true" /> {s.gender}</span> : <span className="text-muted">—</span>}</td>
                  <td className="num">{s.age || <span className="text-muted">—</span>}</td>
                  <td>{s.religion || <span className="text-muted">—</span>}</td>
                  <td className="sl-acts">
                    <a href={s.url} className="sl-rowbtn" title="View" aria-label={'View ' + s.name}><i aria-hidden="true" className="fas fa-eye" /></a>
                    {canEditStudent && <a href={s.edit_url} className="sl-rowbtn" title="Edit" aria-label={'Edit ' + s.name}><i aria-hidden="true" className="fas fa-pen" /></a>}
                    <Menu icon="fa-ellipsis" items={rowItems(s)} title={'More for ' + s.name} className="sl-rowbtn" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="sl-foot">
        <span className="sl-count">{selectedIds.length ? `${selectedIds.length} selected · ` : ''}{d.total || 0} student{d.total === 1 ? '' : 's'}{(d.pages || 1) > 1 ? ` · page ${d.page || 1} of ${d.pages}` : ''}</span>
        <Pagination page={d.page || 1} pages={d.pages || 1} onPage={goPage} />
      </div>

      {/* Phone: floating add button */}
      {phone && canAdd && !selectedIds.length && createPortal(
        <a href={d.add_url} className="sl-fab" aria-label="Add student"><i aria-hidden="true" className="fas fa-plus" /></a>,
        document.body)}

      {showExport && (
        <ExportModal total={d.total || 0} selectedIds={selectedIds} exportUrl={d.export_url}
                     filterText={exportFilterText(query, filters)}
                     applied={{ ...query, page: undefined }} onClose={() => setShowExport(false)} />
      )}

      {showImport && (
        <ImportModal importUrl={d.import_url} enrolment={d.enrolment}
                     onClose={() => setShowImport(false)}
                     onDone={(text) => { setShowImport(false); setMsg({ tone: 'success', text }); refresh(); }} />
      )}

      {showUpdateImport && (
        <UpdateImportModal updateImportUrl={d.update_import_url} filters={d.filters}
                     onClose={() => setShowUpdateImport(false)}
                     onDone={(text) => { setShowUpdateImport(false); setMsg({ tone: 'success', text }); refresh(); }} />
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
