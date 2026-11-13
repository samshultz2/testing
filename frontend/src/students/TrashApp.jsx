import React, { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { postForm } from '../lib/forms';
import { Banner, confirm } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Blank, usePhone, initials } from '../subjects/results';

// Students → Deleted. Soft-deleted students can be found by name / ID / last
// class, narrowed by when they were deleted, and restored or removed for good
// (one at a time or in bulk). Styles: .tr-* in templates/students/trash.html.

const DAY = 86400000;
const parseDay = (s) => (s ? new Date(s + 'T00:00:00').getTime() : NaN);

function ago(days) {
  if (days == null || Number.isNaN(days)) return '';
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 30) { const w = Math.round(days / 7); return `${w} week${w === 1 ? '' : 's'} ago`; }
  if (days < 365) { const m = Math.round(days / 30); return `${m} month${m === 1 ? '' : 's'} ago`; }
  const y = Math.round(days / 365); return `${y} year${y === 1 ? '' : 's'} ago`;
}

function Photo({ s }) {
  const [bad, setBad] = useState(false);
  return (
    <span className="tr-av" aria-hidden="true">
      {s.photo_url && !bad ? <img src={s.photo_url} alt="" loading="lazy" onError={() => setBad(true)} /> : initials(s.full_name)}
    </span>
  );
}

const WHEN = [
  { value: 'all', label: 'All' },
  { value: 'week', label: 'This week' },
  { value: 'month', label: 'This month' },
  { value: 'old', label: 'Older' },
];
const SORTS = [
  ['recent', 'Recently deleted'],
  ['name', 'Name A–Z'],
  ['class', 'Last class'],
  ['oldest', 'Deleted longest ago'],
];

export default function TrashApp({ initial }) {
  const phone = usePhone();
  const today = parseDay(initial.today) || Date.now();
  const [students, setStudents] = useState(() => (initial.students || []).map((s) => ({
    ...s, days: Number.isNaN(parseDay(s.deleted_on)) ? null : Math.round((today - parseDay(s.deleted_on)) / DAY),
  })));
  const [q, setQ] = useState('');
  const [when, setWhen] = useState('all');
  const [cls, setCls] = useState('');
  const [gender, setGender] = useState('');
  const [sort, setSort] = useState('recent');
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const urls = initial.urls || {};
  const canRestore = canWrite(initial, 'restore');
  const canPurge = canWrite(initial, 'purge');
  const canSelect = canRestore || canPurge;

  const classes = useMemo(() => {
    const m = new Map();
    students.forEach((s) => { const k = s.last_class || ''; m.set(k, (m.get(k) || 0) + 1); });
    return [...m.entries()].sort((a, b) => (a[0] === '' ? 1 : b[0] === '' ? -1 : a[0].localeCompare(b[0], undefined, { numeric: true })));
  }, [students]);

  const inWhen = (s, w) => (w === 'all' ? true
    : s.days == null ? w === 'old'
      : w === 'week' ? s.days < 7 : w === 'month' ? s.days < 31 : s.days >= 31);

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    const words = t.split(/\s+/).filter(Boolean);
    const list = students.filter((s) => {
      if (!inWhen(s, when)) return false;
      if (cls !== '' && (s.last_class || '__none') !== cls) return false;
      if (gender && s.gender !== gender) return false;
      if (!words.length) return true;
      const hay = `${s.full_name} ${s.student_id} ${s.last_class} ${s.last_session} ${s.stream || ''} ${s.deleted_by || ''}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    });
    const byName = (a, b) => (a.surname || a.full_name).localeCompare(b.surname || b.full_name) || a.full_name.localeCompare(b.full_name);
    const d = (x) => (x.days == null ? 1e9 : x.days);
    list.sort(sort === 'name' ? byName
      : sort === 'class' ? (a, b) => (a.last_class || '~').localeCompare(b.last_class || '~', undefined, { numeric: true }) || byName(a, b)
        : sort === 'oldest' ? (a, b) => d(b) - d(a) || byName(a, b)
          : (a, b) => d(a) - d(b) || byName(a, b));
    return list;
  }, [students, q, when, cls, gender, sort]); // eslint-disable-line react-hooks/exhaustive-deps

  const count = (w) => students.filter((s) => inWhen(s, w)).length;
  const filtered = q.trim() || when !== 'all' || cls !== '' || gender;
  const clearAll = () => { setQ(''); setWhen('all'); setCls(''); setGender(''); };

  const shownIds = shown.map((s) => s.id);
  const allShownSelected = shownIds.length > 0 && shownIds.every((id) => selected.has(id));
  const toggle = (id) => setSelected((cur) => { const n = new Set(cur); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected((cur) => {
    const n = new Set(cur);
    if (allShownSelected) shownIds.forEach((id) => n.delete(id)); else shownIds.forEach((id) => n.add(id));
    return n;
  });

  const removeRows = (ids) => {
    const gone = new Set(ids);
    setStudents((list) => list.filter((s) => !gone.has(s.id)));
    setSelected((cur) => { const n = new Set(cur); ids.forEach((i) => n.delete(i)); return n; });
  };
  const act = async (url, body, affected, okMsg) => {
    setBusy(true); setMsg(null);
    try {
      const res = await postForm(url, body);
      let data = {};
      try { data = await res.json(); } catch (_) { /* redirect/html */ }
      if (res.ok && (data.ok || res.redirected)) { removeRows(affected); setMsg({ tone: 'success', text: okMsg }); }
      else setMsg({ tone: 'error', text: data.error || `That didn't work (HTTP ${res.status}).` });
    } catch (e) {
      setMsg({ tone: 'error', text: e.message || 'Network error — please try again.' });
    } finally { setBusy(false); }
  };
  const restoreOne = (s) => act(s.restore_url, {}, [s.id], `${s.full_name} is back on the student list.`);
  const purgeOne = async (s) => {
    if (await confirm({ title: 'Delete for good?', message: `${s.full_name} and all their records (results, attendance, payments) will be removed permanently. This can't be undone.`, confirmText: 'Delete for good', tone: 'danger' }))
      act(s.purge_url, {}, [s.id], `${s.full_name} was deleted permanently.`);
  };
  const sel = [...selected];
  const bulkRestore = () => sel.length && act(urls.bulk_restore, { student_ids: sel }, sel, `${sel.length} student${sel.length === 1 ? '' : 's'} restored.`);
  const bulkPurge = async () => {
    if (sel.length && await confirm({ title: 'Delete for good?', message: `${sel.length} student${sel.length === 1 ? '' : 's'} and all their records will be removed permanently. This can't be undone.`, confirmText: `Delete ${sel.length} for good`, tone: 'danger' }))
      act(urls.bulk_purge, { student_ids: sel }, sel, `${sel.length} student${sel.length === 1 ? '' : 's'} deleted permanently.`);
  };

  const week = count('week');
  const old = count('old');

  const selBar = canSelect && selected.size > 0 && (
    <div className={'tr-selbar' + (phone ? ' fixed' : '')} role="region" aria-label="Selected students">
      <button type="button" className="tr-selx" onClick={() => setSelected(new Set())} aria-label="Clear selection"><i className="fas fa-xmark" aria-hidden="true" /></button>
      <b>{selected.size} selected</b>
      <span className="tr-grow" />
      {canRestore && <button type="button" className="rs-btn sm success" disabled={busy} onClick={bulkRestore}><i className="fas fa-rotate-left" aria-hidden="true" /> Restore</button>}
      {canPurge && <button type="button" className="rs-btn sm danger" disabled={busy} onClick={bulkPurge}><i className="fas fa-trash" aria-hidden="true" /> {phone ? 'Delete' : 'Delete for good'}</button>}
    </div>
  );

  return (
    <div className={'rs tr' + (phone && selected.size ? ' has-bar' : '')}>
      <Head icon="fa-trash-can-arrow-up" title="Deleted students"
            sub="Bring back anyone removed by mistake, or clear out records for good.">
        <a href={urls.list} className="rs-btn ghost"><i className="fas fa-arrow-left" aria-hidden="true" /><span className="rs-hide-sm">All students</span></a>
      </Head>

      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}

      {students.length > 0 && (
        <Tiles items={[
          { label: 'In the bin', value: students.length, sub: 'Hidden from lists and reports' },
          { label: 'Last 7 days', value: week, sub: week ? 'Check these were meant to go' : 'Nothing recent', tone: week ? 'mid' : '' },
          { label: 'Over a month', value: old, sub: old ? 'Safe to clear out if not needed' : 'None', tone: '' },
        ]} />
      )}

      {students.length === 0 ? (
        <Blank icon="fa-trash-can" title="The bin is empty">
          <p>Students you delete from the list land here first, so they can be restored.</p>
          <a href={urls.list} className="rs-btn primary"><i className="fas fa-users" aria-hidden="true" /> Go to students</a>
        </Blank>
      ) : (
        <section className="rs-card flush tr-card">
          <div className="tr-tools">
            <label className="tr-search">
              <i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, ID, class or who deleted"
                     aria-label="Search deleted students" />
              {q && <button type="button" onClick={() => setQ('')} aria-label="Clear search"><i className="fas fa-xmark" aria-hidden="true" /></button>}
            </label>
            <div className="tr-row">
              <Seg label="Deleted" value={when} onChange={setWhen}
                   options={WHEN.map((w) => ({ ...w, count: count(w.value) }))} />
              <span className="tr-grow" />
              <label className="tr-sel"><span className="sr-only">Last class</span>
                <select value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Last class">
                  <option value="">All classes</option>
                  {classes.map(([c, n]) => <option key={c || '__none'} value={c || '__none'}>{c || 'No class'} ({n})</option>)}
                </select></label>
              <label className="tr-sel"><span className="sr-only">Gender</span>
                <select value={gender} onChange={(e) => setGender(e.target.value)} aria-label="Gender">
                  <option value="">Boys &amp; girls</option><option value="Male">Boys</option><option value="Female">Girls</option>
                </select></label>
              <label className="tr-sel"><span className="sr-only">Sort</span>
                <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort by">
                  {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select></label>
            </div>
          </div>

          <div className="tr-head">
            {canSelect && shown.length > 0 && (
              <label className="tr-all"><input type="checkbox" checked={allShownSelected} onChange={toggleAll} />
                <span>{allShownSelected ? 'Unselect' : 'Select'} {filtered ? 'shown' : 'all'}</span></label>
            )}
            <span className="tr-count">{shown.length === students.length ? `${students.length} student${students.length === 1 ? '' : 's'}` : `${shown.length} of ${students.length}`}</span>
            {filtered && <button type="button" className="tr-link" onClick={clearAll}>Clear filters</button>}
          </div>

          {shown.length === 0 ? (
            <div className="tr-none"><i className="fas fa-magnifying-glass" aria-hidden="true" /> No deleted student matches.
              <button type="button" className="tr-link" onClick={clearAll}>Clear filters</button></div>
          ) : (
            <ul className="tr-list">
              {shown.map((s) => (
                <li key={s.id} className={selected.has(s.id) ? 'sel' : ''}>
                  {canSelect && <input type="checkbox" className="tr-chk" checked={selected.has(s.id)} onChange={() => toggle(s.id)} aria-label={'Select ' + s.full_name} />}
                  <Photo s={s} />
                  <div className="tr-who">
                    <b>{s.full_name}{s.is_graduated && <span className="tr-tag">Graduate</span>}</b>
                    <small>
                      <span className={'tr-g ' + (s.gender === 'Male' ? 'm' : s.gender === 'Female' ? 'f' : '')} title={s.gender || ''} />
                      {s.student_id}{s.last_class ? <> · {s.last_class}{s.last_session ? <span className="tr-dim"> ({s.last_session})</span> : null}</> : <span className="tr-dim"> · no class on record</span>}
                    </small>
                    <small className={'tr-when' + (s.days != null && s.days < 7 ? ' new' : '')}>
                      <i className="fas fa-clock" aria-hidden="true" /> Deleted {ago(s.days) || 'earlier'}{s.deleted_by ? ` by ${s.deleted_by}` : ''}
                    </small>
                  </div>
                  <div className="tr-acts">
                    {canRestore && <button type="button" className="rs-btn sm tr-restore" disabled={busy} onClick={() => restoreOne(s)} title="Restore to the student list">
                      <i className="fas fa-rotate-left" aria-hidden="true" /><span>Restore</span></button>}
                    {canPurge && <button type="button" className="tr-purge" disabled={busy} onClick={() => purgeOne(s)} aria-label={'Delete ' + s.full_name + ' for good'} title="Delete for good">
                      <i className="fas fa-trash" aria-hidden="true" /></button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {selBar && (phone ? createPortal(selBar, document.body) : selBar)}
    </div>
  );
}
