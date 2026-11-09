// Subjects catalogue + class-subject assignment screens, on the results kit.
import React, { useEffect, useMemo, useState } from 'react';
import { submitJson } from '../lib/forms';
import { useNav, navParams } from '../lib/section';
import { confirm } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Chips, Menu, Sheet, Blank, Bar } from './results';

const CAT_HUE = { Science: 160, Arts: 280, Commercial: 30, General: 215, Languages: 340, Vocational: 45 };
const hueOf = (cat) => (cat in CAT_HUE ? CAT_HUE[cat] : [...String(cat || '')].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 0));
const plural = (n, w, p) => `${n} ${n === 1 ? w : (p || w + 's')}`;

// Two-tab section nav shared by both catalogue screens.
function SubNav({ d, active }) {
  const n = d.nav || {};
  return (
    <nav className="sl-nav" aria-label="Subjects">
      <a href={n.subjects} className={active === 'subjects' ? 'on' : ''}><i className="fas fa-book" aria-hidden="true" /><span>Subjects</span></a>
      <a href={n.class_subjects} className={active === 'class' ? 'on' : ''}><i className="fas fa-chalkboard-user" aria-hidden="true" /><span>Class subjects</span></a>
      {n.flow && n.flow.workflow && <a href={n.flow.workflow}><i className="fas fa-list-check" aria-hidden="true" /><span>Results</span></a>}
    </nav>
  );
}

function Search({ value, onChange, placeholder, count }) {
  return (
    <label className="rs-search sj-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder} autoComplete="off" />
      {count != null && <span className="bx-count">{count}</span>}
    </label>
  );
}

// ---- Subjects ---------------------------------------------------------------
export function List({ d, notify }) {
  const nav = useNav();
  const all = d.subjects || [];
  const [level, setLevel] = useState('all');
  const [cat, setCat] = useState('');
  const [q, setQ] = useState('');
  const canAdd = canWrite(d, 'subjects_create');
  const canEdit = canWrite(d, 'subjects_edit');
  const canDel = canWrite(d, 'subjects_delete');
  const del = async (s) => {
    if (!await confirm(`Delete ${s.name}? It will no longer be offered to classes.`)) return;
    const r = await submitJson(s.delete_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  const jss = all.filter((s) => s.for_junior).length;
  const sss = all.filter((s) => s.for_senior).length;
  const unused = all.filter((s) => !s.classes).length;
  const cats = useMemo(() => {
    const m = {}; all.forEach((s) => { m[s.category] = (m[s.category] || 0) + 1; });
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [all]);
  const ql = q.trim().toLowerCase();
  const shown = all.filter((s) => (level === 'all' || (level === 'junior' ? s.for_junior : level === 'senior' ? s.for_senior : !s.classes))
    && (!cat || s.category === cat)
    && (!ql || s.name.toLowerCase().includes(ql) || s.short_name.toLowerCase().includes(ql)));
  const groups = {};
  shown.forEach((s) => { (groups[s.category] = groups[s.category] || []).push(s); });

  return (
    <div className="rs bx sj">
      <Head icon="fa-book" title="Subjects" sub={`${plural(all.length, 'subject')} offered · ${jss} JSS · ${sss} SSS`}>
        {canAdd && <a href={d.urls.add} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Add subject</span></a>}
        <Menu items={[
          canAdd && { icon: 'fa-list', label: 'Bulk add subjects', href: d.urls.bulk_add },
          { icon: 'fa-chalkboard-user', label: 'Assign subjects to classes', href: d.urls.class_subjects },
        ]} />
      </Head>
      <SubNav d={d} active="subjects" />

      <Tiles items={[
        { label: 'Subjects', value: all.length, sub: plural(cats.length, 'category', 'categories') },
        { label: 'Junior (JSS)', value: jss, sub: 'offered' },
        { label: 'Senior (SSS)', value: sss, sub: 'offered' },
        { label: 'Not taught', value: unused, tone: unused ? 'mid' : 'good', sub: d.term_name ? `no class in ${d.term_name}` : 'no class this term' },
      ]} />

      <section className="rs-card flush">
        <div className="sj-tools">
          <Search value={q} onChange={setQ} placeholder="Find a subject" count={(q || cat || level !== 'all') ? `${shown.length} of ${all.length}` : null} />
          <Seg label="Level" value={level} onChange={setLevel} options={[
            { value: 'all', label: 'All', count: all.length },
            { value: 'junior', label: 'JSS', count: jss },
            { value: 'senior', label: 'SSS', count: sss },
            unused ? { value: 'unused', label: 'Not taught', count: unused } : null,
          ].filter(Boolean)} />
        </div>
        {cats.length > 1 && (
          <div className="sj-cats">
            <Chips label="Category" value={cat} onChange={(v) => setCat(v === cat ? '' : v)}
                   items={[{ value: '', label: 'All categories' }, ...cats.map(([c, n]) => ({ value: c, label: c, sub: n }))]} />
          </div>
        )}
        {shown.length ? Object.entries(groups).map(([c, list]) => (
          <div key={c} className="sj-group">
            <div className="sj-group-h" style={{ '--h': hueOf(c) }}><i aria-hidden="true" />{c}<span>{list.length}</span></div>
            <div className="sj-grid">
              {list.map((s) => (
                <div key={s.id} className="sj-sub" style={{ '--h': hueOf(s.category) }}>
                  <span className="sj-code">{s.short_name || s.name.slice(0, 3).toUpperCase()}</span>
                  <div className="sj-sub-t">
                    <b>{s.name}</b>
                    <small>
                      {s.for_junior && <span className="sj-lv">JSS</span>}
                      {s.for_senior && <span className="sj-lv">SSS</span>}
                      {s.has_practical ? <span title="Has midterm / practical (P/ME)">P/ME</span> : null}
                      <span className={s.classes ? '' : 'sj-warn'}>{s.classes ? plural(s.classes, 'class', 'classes') : 'No class yet'}</span>
                    </small>
                  </div>
                  {(canEdit || canDel) && (
                    <span className="sj-acts">
                      {canEdit && <a href={s.edit_url} className="rs-icon-btn" title="Edit" aria-label={`Edit ${s.name}`}><i className="fas fa-pen" aria-hidden="true" /></a>}
                      {canDel && <button type="button" className="rs-icon-btn danger" title="Delete" aria-label={`Delete ${s.name}`} onClick={() => del(s)}><i className="fas fa-trash" aria-hidden="true" /></button>}
                    </span>)}
                </div>))}
            </div>
          </div>
        )) : (
          <Blank icon="fa-book" title={all.length ? 'No subjects match' : 'No subjects yet'}>
            <p>{all.length ? 'Try another search or filter.' : 'Add the subjects your school offers, or bulk add a standard list.'}</p>
            {!all.length && canAdd && <a href={d.urls.bulk_add} className="rs-btn primary"><i className="fas fa-list" aria-hidden="true" /> Bulk add subjects</a>}
          </Blank>
        )}
      </section>
    </div>
  );
}

// ---- Add / edit subject -------------------------------------------------------
export function SubjectForm({ d, notify }) {
  const nav = useNav();
  const init = d.subject || { name: '', short_name: '', category: d.categories[0], has_practical: true, for_junior: true, for_senior: true };
  const [f, setF] = useState({ ...init });
  const [busy, setBusy] = useState(false);
  const isEdit = d.page === 'edit';
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify('error', 'Subject name is required.'); return; }
    if (!f.for_junior && !f.for_senior) { notify('error', 'Tick JSS, SSS or both.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { name: f.name, short_name: f.short_name, category: f.category,
      has_practical: f.has_practical ? 'on' : '', for_junior: f.for_junior ? 'on' : '', for_senior: f.for_senior ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const code = f.short_name || f.name.trim().slice(0, 3).toUpperCase() || 'ABC';
  return (
    <div className="rs bx sj">
      <Head icon={isEdit ? 'fa-pen' : 'fa-plus'} title={isEdit ? `Edit ${init.name}` : 'Add a subject'} sub="Name, code, category and which levels offer it" />
      <form className="rs-card sj-form" onSubmit={submit}>
        <div className="sj-preview" style={{ '--h': hueOf(f.category) }}>
          <span className="sj-code">{code}</span>
          <div><b>{f.name || 'Subject name'}</b><small>{f.category} · {[f.for_junior && 'JSS', f.for_senior && 'SSS'].filter(Boolean).join(' & ') || 'no level'}{f.has_practical ? ' · P/ME' : ''}</small></div>
        </div>
        <label className="sj-f"><span>Subject name</span>
          <input required autoFocus value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Mathematics" /></label>
        <div className="sj-row">
          <label className="sj-f"><span>Short code</span>
            <input maxLength="10" value={f.short_name} onChange={(e) => set('short_name', e.target.value.toUpperCase())} placeholder={code} /></label>
          <div className="sj-f"><span>Category</span>
            <div className="rs-chips">{d.categories.map((c) => (
              <button key={c} type="button" className={'rs-chip' + (f.category === c ? ' on' : '')} onClick={() => set('category', c)}>{c}</button>))}</div></div>
        </div>
        <div className="sj-f"><span>Offered at</span>
          <div className="sj-toggles">
            <label className={'sj-tog' + (f.for_junior ? ' on' : '')}><input type="checkbox" checked={f.for_junior} onChange={(e) => set('for_junior', e.target.checked)} />
              <b>Junior (JSS)</b><small>Shows in JSS class lists</small></label>
            <label className={'sj-tog' + (f.for_senior ? ' on' : '')}><input type="checkbox" checked={f.for_senior} onChange={(e) => set('for_senior', e.target.checked)} />
              <b>Senior (SSS)</b><small>Shows in SSS class lists</small></label>
            <label className={'sj-tog' + (f.has_practical ? ' on' : '')}><input type="checkbox" checked={f.has_practical} onChange={(e) => set('has_practical', e.target.checked)} />
              <b>Midterm / practical</b><small>{f.has_practical ? 'P/ME column kept' : 'No P/ME column — theory worth 50'}</small></label>
          </div></div>
        <div className="sj-actions">
          <a href={d.cancel_url} className="rs-btn ghost">Cancel</a>
          <button type="submit" className="rs-btn primary" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {isEdit ? 'Save changes' : 'Add subject'}</button>
        </div>
      </form>
    </div>
  );
}

// ---- Bulk add -------------------------------------------------------------------
export function BulkAdd({ d, notify }) {
  const nav = useNav();
  const [category, setCategory] = useState(d.categories[0]);
  const [text, setText] = useState(d.default_subjects);
  const [busy, setBusy] = useState(false);
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.submit_url, { category, subjects: text });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not add.');
  };
  return (
    <div className="rs bx sj">
      <Head icon="fa-list" title="Bulk add subjects" sub="One subject per line — ones that already exist are skipped" />
      <form className="rs-card sj-form" onSubmit={submit}>
        <div className="sj-f"><span>Category for these subjects</span>
          <div className="rs-chips">{d.categories.map((c) => (
            <button key={c} type="button" className={'rs-chip' + (category === c ? ' on' : '')} onClick={() => setCategory(c)}>{c}</button>))}</div></div>
        <label className="sj-f"><span>Subjects <em>({lines.length})</em></span>
          <textarea rows="14" value={text} onChange={(e) => setText(e.target.value)} /></label>
        <div className="sj-actions">
          <button type="button" className="rs-btn ghost" onClick={() => setText('')}>Clear list</button>
          <a href={d.cancel_url} className="rs-btn ghost">Cancel</a>
          <button type="submit" className="rs-btn primary" disabled={busy || !lines.length}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-plus')} aria-hidden="true" /> Add {lines.length}</button>
        </div>
      </form>
    </div>
  );
}

// Inline teacher editor: tap the name, type, Enter/blur saves.
function TeacherCell({ cs, can, notify, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState(cs.teacher_name);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setV(cs.teacher_name); }, [cs.teacher_name]);
  const save = async () => {
    setEdit(false);
    if (v.trim() === (cs.teacher_name || '')) return;
    setBusy(true);
    const r = await submitJson(cs.edit_url, { teacher_name: v.trim() });
    setBusy(false);
    if (r.ok) { onSaved(cs.id, v.trim()); notify('success', `${cs.subject} (${cs.class_name}): ${v.trim() ? 'teacher set to ' + v.trim() : 'teacher cleared'}.`); }
    else { setV(cs.teacher_name); notify('error', r.error || 'Could not save.'); }
  };
  if (!can) return <span className={'sj-teacher' + (cs.teacher_name ? '' : ' none')}>{cs.teacher_name || 'No teacher'}</span>;
  if (edit) {
    return <input className="sj-tin" autoFocus list="sjTeachers" value={v} placeholder="Teacher name"
                  onChange={(e) => setV(e.target.value)} onBlur={save}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); } if (e.key === 'Escape') { setV(cs.teacher_name); setEdit(false); } }} />;
  }
  return (
    <button type="button" className={'sj-teacher' + (v ? '' : ' none')} onClick={() => setEdit(true)} title="Tap to change the teacher">
      {busy ? <i className="fas fa-spinner fa-spin" aria-hidden="true" /> : <i className={'fas ' + (v ? 'fa-user' : 'fa-user-plus')} aria-hidden="true" />}
      <span>{v || 'Add teacher'}</span>
    </button>
  );
}

// ---- Class subjects ---------------------------------------------------------
export function ClassSubjects({ d, notify }) {
  const nav = useNav();
  const [rowsState, setRows] = useState(d.class_subjects);
  useEffect(() => { setRows(d.class_subjects); }, [d.class_subjects]);
  const [sel, setSel] = useState(() => new Set());
  const [bulkName, setBulkName] = useState('');
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');
  const [missingOnly, setMissingOnly] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [copyFrom, setCopyFrom] = useState('');
  const [level, setLevel] = useState(() => {
    const c = d.classes.find((x) => String(x.id) === String(d.class_id));
    return c && (c.section === 'junior' || c.section === 'senior') ? c.section : 'all';
  });
  const canAssign = canWrite(d, 'subjects_assign');
  const canEdit = canWrite(d, 'subjects_edit');
  const canDel = canWrite(d, 'subjects_delete');
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, ...extra });
  const counts = d.class_counts || {};
  const missingBy = d.class_missing || {};
  const sectionOf = {}; d.classes.forEach((c) => { sectionOf[c.id] = c.section; });
  const levelClasses = d.classes.filter((c) => level === 'all' || c.section === level);
  const totalAssign = Object.values(counts).reduce((a, b) => a + b, 0);
  const totalMissing = Object.values(missingBy).reduce((a, b) => a + b, 0);
  const covered = d.classes.filter((c) => counts[c.id]).length;
  const empty = levelClasses.filter((c) => !counts[c.id]);
  const ql = q.trim().toLowerCase();
  const rows = rowsState.filter((cs) => (level === 'all' || sectionOf[cs.class_id] === level)
    && (!missingOnly || !cs.teacher_name)
    && (!ql || cs.subject.toLowerCase().includes(ql) || (cs.teacher_name || '').toLowerCase().includes(ql)));
  const byClass = [];
  const idx = {};
  rows.forEach((cs) => {
    const k = cs.class_name + (cs.arm ? ' ' + cs.arm : '');
    if (!(k in idx)) { idx[k] = byClass.length; byClass.push({ key: k, class_id: cs.class_id, list: [] }); }
    byClass[idx[k]].list.push(cs);
  });
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleMany = (ids, on) => setSel((s) => { const n = new Set(s); ids.forEach((id) => (on ? n.add(id) : n.delete(id))); return n; });
  const onSaved = (id, name) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, teacher_name: name } : r)));
  const del = async (cs) => {
    if (!await confirm(`Remove ${cs.subject} from ${cs.class_name}${cs.arm ? ' ' + cs.arm : ''}?`)) return;
    const r = await submitJson(cs.delete_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not remove.');
  };
  const applyBulk = async () => {
    const name = bulkName.trim();
    if (!name && !await confirm(`Clear the teacher on ${sel.size} subject(s)?`)) return;
    setBusy(true);
    const r = await submitJson(d.urls.bulk_teacher, { term_id: d.term_id || '', class_id: d.class_id || '', 'cs_ids[]': [...sel], teacher_name: name });
    setBusy(false);
    if (r.ok) { notify('success', r.message); setSel(new Set()); setBulkName(''); nav.refresh(); }
    else notify('error', r.error || 'Could not apply.');
  };
  const copy = async () => {
    if (!copyFrom) { notify('error', 'Choose the term to copy from.'); return; }
    const r = await submitJson(d.urls.copy, { to_term_id: d.term_id, from_term_id: copyFrom, class_id: d.class_id || '' });
    if (r.ok) { notify('success', r.message); setCopyOpen(false); nav.refresh(); } else notify('error', r.error || 'Could not copy.');
  };
  const selClass = d.classes.find((c) => String(c.id) === String(d.class_id));
  const assignHref = `${d.urls.assign}?term_id=${d.term_id || ''}${d.class_id ? '&class_id=' + d.class_id : ''}`;

  return (
    <div className="rs bx sj">
      <datalist id="sjTeachers">{(d.teachers || []).map((t) => <option key={t} value={t} />)}</datalist>
      <Head icon="fa-chalkboard-user" title="Class subjects" sub={d.selected_term ? `${d.selected_term} · which class takes which subject, and who teaches it` : 'Which class takes which subject, and who teaches it'}>
        {canAssign && d.term_id && <a href={assignHref} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Assign subjects</span></a>}
        <Menu items={[
          canAssign && d.term_id && { icon: 'fa-copy', label: 'Copy from another term', onClick: () => setCopyOpen(true) },
          { icon: 'fa-book', label: 'Subjects catalogue', href: d.nav && d.nav.subjects },
        ]} />
      </Head>
      <SubNav d={d} active="class" />

      <section className="rs-pick">
        <div className="rs-pick-row">
          <label className="rs-sel"><span>Term</span>
            <select value={d.term_id} onChange={(e) => go({ term_id: e.target.value })}>
              <option value="">Select term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
          <div className="rs-sel"><span>Level</span>
            <Seg label="Level" value={level} onChange={(v) => { setLevel(v); if (d.class_id && v !== 'all' && sectionOf[d.class_id] !== v) go({ class_id: '' }); }}
                 options={[{ value: 'all', label: 'All' }, { value: 'junior', label: 'JSS' }, { value: 'senior', label: 'SSS' }]} /></div>
        </div>
        {d.term_id && (
          <div className="sj-classes">
            <button type="button" className={'rs-chip' + (!d.class_id ? ' on' : '')} onClick={() => go({ class_id: '' })}>All classes</button>
            {levelClasses.map((c) => (
              <button key={c.id} type="button" className={'rs-chip' + (String(c.id) === String(d.class_id) ? ' on' : '') + (!counts[c.id] ? ' sj-empty' : missingBy[c.id] ? ' sj-miss' : '')}
                      onClick={() => go({ class_id: c.id })} title={counts[c.id] ? `${counts[c.id]} subjects${missingBy[c.id] ? `, ${missingBy[c.id]} without a teacher` : ''}` : 'No subjects yet'}>
                {c.name}<small>{counts[c.id] || 0}</small></button>))}
          </div>)}
      </section>

      {!d.term_id ? (
        <Blank icon="fa-hand-pointer" title="Choose a term"><p>Pick a term to see and assign class subjects.</p></Blank>
      ) : (
        <>
          <Tiles items={[
            { label: 'Assignments', value: totalAssign, sub: 'subject × class' },
            { label: 'Classes set up', value: covered, unit: `/${d.classes.length}`, tone: covered === d.classes.length ? 'good' : covered ? 'mid' : 'bad', sub: 'have subjects' },
            { label: 'No teacher', value: totalMissing, tone: totalMissing ? 'mid' : 'good', sub: totalMissing ? 'need a teacher' : 'all have one' },
            { label: 'Teachers', value: (d.teachers || []).length, sub: 'names in use' },
          ]} />

          {!d.class_id && empty.length > 0 && canAssign && (
            <div className="sj-gap" role="note">
              <i className="fas fa-triangle-exclamation" aria-hidden="true" />
              <div><b>{plural(empty.length, 'class', 'classes')} with no subjects this term</b>
                <span>{empty.slice(0, 6).map((c) => c.name).join(', ')}{empty.length > 6 ? ` +${empty.length - 6} more` : ''}</span></div>
              <button type="button" className="rs-btn ghost sm" onClick={() => setCopyOpen(true)}><i className="fas fa-copy" aria-hidden="true" /><span className="rs-hide-sm"> Copy from a term</span></button>
            </div>)}

          <section className="rs-card flush">
            <div className="sj-tools">
              <Search value={q} onChange={setQ} placeholder="Find a subject or teacher" count={(q || missingOnly) ? `${rows.length} of ${rowsState.length}` : null} />
              <button type="button" className={'rs-chip' + (missingOnly ? ' on' : '')} onClick={() => setMissingOnly((v) => !v)}>
                <i className="fas fa-user-slash" aria-hidden="true" /> No teacher</button>
            </div>
            {byClass.length ? byClass.map((g) => {
              const ids = g.list.map((x) => x.id);
              const allOn = ids.every((id) => sel.has(id));
              const miss = g.list.filter((x) => !x.teacher_name).length;
              return (
                <div key={g.key} className="sj-group">
                  <div className="sj-ch">
                    {canEdit && <input type="checkbox" checked={allOn} onChange={() => toggleMany(ids, !allOn)} aria-label={`Select all in ${g.key}`} />}
                    <b>{g.key}</b><span className="sj-n">{plural(g.list.length, 'subject')}</span>
                    {miss > 0 && <span className="sl-pill mid">{miss} no teacher</span>}
                    {canAssign && !d.class_id && <button type="button" className="sj-link" onClick={() => go({ class_id: g.class_id })}>Open</button>}
                  </div>
                  <ul className="sj-list">
                    {g.list.map((cs) => (
                      <li key={cs.id} className={'sj-li' + (sel.has(cs.id) ? ' on' : '')} style={{ '--h': hueOf(cs.category) }}>
                        {canEdit && <input type="checkbox" checked={sel.has(cs.id)} onChange={() => toggle(cs.id)} aria-label={`Select ${cs.subject}`} />}
                        <span className="sj-dot" aria-hidden="true" />
                        <span className="sj-name">{cs.subject}{cs.arm && <small>{cs.arm}</small>}</span>
                        <TeacherCell cs={cs} can={canEdit} notify={notify} onSaved={onSaved} />
                        {canDel && <button type="button" className="rs-icon-btn danger sj-x" title="Remove from class" aria-label={`Remove ${cs.subject}`} onClick={() => del(cs)}><i className="fas fa-xmark" aria-hidden="true" /></button>}
                      </li>))}
                  </ul>
                </div>
              );
            }) : (
              <Blank icon="fa-book-open" title={rowsState.length ? 'Nothing matches' : selClass ? `No subjects for ${selClass.name} yet` : 'No subjects assigned yet'}>
                <p>{rowsState.length ? 'Try another search or filter.' : 'Assign subjects to classes for this term, or copy last term’s set-up.'}</p>
                {!rowsState.length && canAssign && <div className="sj-actions center">
                  <button type="button" className="rs-btn ghost" onClick={() => setCopyOpen(true)}><i className="fas fa-copy" aria-hidden="true" /> Copy from a term</button>
                  <a href={assignHref} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /> Assign subjects</a></div>}
              </Blank>
            )}
          </section>
        </>
      )}

      {sel.size > 0 && (
        <Bar>
          <div className="rs-bar-t"><b>{sel.size} selected</b><small>Set one teacher on all of them</small></div>
          <input className="sj-bulk" list="sjTeachers" value={bulkName} onChange={(e) => setBulkName(e.target.value)} placeholder="Teacher name (blank clears)" aria-label="Teacher name" />
          <button type="button" className="rs-btn ghost" onClick={() => setSel(new Set())}>Clear</button>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={applyBulk}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-user-check')} aria-hidden="true" /><span className="rs-hide-sm"> Apply</span></button>
        </Bar>
      )}

      {copyOpen && (
        <Sheet title={`Copy into ${d.selected_term || 'this term'}`} onClose={() => setCopyOpen(false)}>
          <p className="rs-muted sj-p">Copies the subject-to-class assignments and teachers from another term{selClass ? ` for ${selClass.name}` : ' for every class'}. Anything already set up here is kept.</p>
          <label className="rs-sel"><span>Copy from</span>
            <select value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
              <option value="">Choose a term…</option>
              {d.terms.filter((t) => String(t.id) !== String(d.term_id)).map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
          <div className="sj-actions">
            <button type="button" className="rs-btn ghost" onClick={() => setCopyOpen(false)}>Cancel</button>
            <button type="button" className="rs-btn primary" onClick={copy}><i className="fas fa-copy" aria-hidden="true" /> Copy</button>
          </div>
        </Sheet>
      )}
    </div>
  );
}

// ---- Assign subjects to a class --------------------------------------------
export function Assign({ d, notify }) {
  const nav = useNav();
  const init = d.initial || {};
  const [termId, setTermId] = useState(() => String(init.term_id || (d.terms.find((t) => t.is_active) || {}).id || ''));
  const [classId, setClassId] = useState(String(init.class_id || ''));
  const [armId, setArmId] = useState('');
  const [rows, setRows] = useState(() => { const m = {}; d.subjects.forEach((s) => { m[s.id] = { checked: false, teacher: '' }; }); return m; });
  const [existing, setExisting] = useState({});   // subject_id -> teacher
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const selectedClass = d.classes.find((c) => String(c.id) === String(classId));
  useEffect(() => {
    setExisting({});
    if (!termId || !classId || !d.existing_url) return;
    fetch(`${d.existing_url}${termId}/${classId}`, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then((r) => r.json()).then((list) => {
        const m = {}; (list || []).forEach((x) => { m[x.subject_id] = x.teacher_name || ''; });
        setExisting(m);
      }).catch(() => {});
  }, [termId, classId]); // eslint-disable-line react-hooks/exhaustive-deps
  const visible = d.subjects.filter((s) => {
    if (selectedClass && selectedClass.section === 'junior' && !s.for_junior) return false;
    if (selectedClass && selectedClass.section === 'senior' && !s.for_senior) return false;
    return !q.trim() || s.name.toLowerCase().includes(q.trim().toLowerCase());
  });
  const groups = {};
  visible.forEach((s) => { (groups[s.category || 'General'] = groups[s.category || 'General'] || []).push(s); });
  const setRow = (id, k, v) => setRows((m) => ({ ...m, [id]: { ...m[id], [k]: v } }));
  const pickable = (s) => !(s.id in existing);
  const setMany = (list, v) => setRows((m) => { const n = { ...m }; list.filter(pickable).forEach((s) => { n[s.id] = { ...n[s.id], checked: v }; }); return n; });
  const chosen = d.subjects.filter((s) => rows[s.id].checked && pickable(s));
  const submit = async () => {
    if (!termId || !classId) { notify('error', 'Choose the term and class first.'); return; }
    if (!chosen.length) { notify('error', 'Tick at least one subject.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { term_id: termId, class_id: classId, arm_id: armId || '',
      'subject_ids[]': chosen.map((s) => s.id), 'teacher_names[]': chosen.map((s) => rows[s.id].teacher) });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not assign.');
  };
  const nExisting = Object.keys(existing).length;
  return (
    <div className="rs bx sj">
      <datalist id="sjTeachersA">{(d.teachers || []).map((t) => <option key={t} value={t} />)}</datalist>
      <Head icon="fa-plus" title="Assign subjects" sub="Pick a class, tick its subjects and (optionally) the teacher for each" />
      <section className="rs-pick">
        <div className="rs-pick-row">
          <label className="rs-sel"><span>Term</span>
            <select value={termId} onChange={(e) => setTermId(e.target.value)}>
              <option value="">Select term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
          <label className="rs-sel"><span>Arm</span>
            <select value={armId} onChange={(e) => setArmId(e.target.value)}>
              <option value="">All arms</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        </div>
        <div className="rs-pick-l"><span>Class</span>
          <div className="sj-classes">{d.classes.map((c) => (
            <button key={c.id} type="button" className={'rs-chip' + (String(c.id) === classId ? ' on' : '')} onClick={() => setClassId(String(c.id))}>{c.name}</button>))}</div></div>
      </section>

      {!classId ? <Blank icon="fa-hand-pointer" title="Choose a class"><p>Pick the class to assign subjects to.</p></Blank> : (
        <section className="rs-card flush">
          <div className="sj-tools">
            <Search value={q} onChange={setQ} placeholder="Find a subject" />
            <button type="button" className="rs-chip" onClick={() => setMany(visible, true)}><i className="fas fa-check-double" aria-hidden="true" /> Tick all</button>
            <button type="button" className="rs-chip" onClick={() => setMany(visible, false)}>None</button>
          </div>
          {(selectedClass.section === 'junior' || selectedClass.section === 'senior') && (
            <p className="sj-hint">Showing {selectedClass.section === 'junior' ? 'JSS' : 'SSS'} subjects for {selectedClass.name}.{nExisting ? ` ${nExisting} already assigned this term (greyed out).` : ''}</p>)}
          {Object.entries(groups).map(([cat, list]) => (
            <div key={cat} className="sj-group">
              <div className="sj-group-h" style={{ '--h': hueOf(cat) }}><i aria-hidden="true" />{cat}<span>{list.length}</span>
                <button type="button" className="sj-link" onClick={() => setMany(list, !list.filter(pickable).every((s) => rows[s.id].checked))}>Toggle</button></div>
              <ul className="sj-list">
                {list.map((s) => {
                  const done = s.id in existing;
                  const on = done || rows[s.id].checked;
                  return (
                    <li key={s.id} className={'sj-li sj-pick' + (on ? ' on' : '') + (done ? ' done' : '')} style={{ '--h': hueOf(s.category) }}>
                      <label className="sj-pick-l">
                        <input type="checkbox" checked={on} disabled={done} onChange={(e) => setRow(s.id, 'checked', e.target.checked)} />
                        <span className="sj-name">{s.name}{done && <small>already assigned</small>}</span>
                      </label>
                      {done ? <span className={'sj-teacher' + (existing[s.id] ? '' : ' none')}>{existing[s.id] || 'No teacher'}</span>
                        : rows[s.id].checked && <input className="sj-tin" list="sjTeachersA" placeholder="Teacher (optional)" value={rows[s.id].teacher} onChange={(e) => setRow(s.id, 'teacher', e.target.value)} />}
                    </li>);
                })}
              </ul>
            </div>))}
        </section>
      )}

      <Bar>
        <div className="rs-bar-t"><b>{chosen.length ? `${plural(chosen.length, 'subject')} to add` : 'Tick subjects to add'}</b>
          <small>{selectedClass ? `${selectedClass.name}${armId ? ' ' + (d.arms.find((a) => String(a.id) === armId) || {}).name : ''}` : 'No class chosen'}</small></div>
        <a href={d.cancel_url} className="rs-btn ghost">Cancel</a>
        <button type="button" className="rs-btn primary" disabled={busy || !chosen.length} onClick={submit}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> Assign</button>
      </Bar>
    </div>
  );
}

// ---- Edit one class subject -------------------------------------------------
export function EditClassSubject({ d, notify }) {
  const nav = useNav();
  const cs = d.cs;
  const [teacher, setTeacher] = useState(cs.teacher_name);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.submit_url, { teacher_name: teacher });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <div className="rs bx sj">
      <Head icon="fa-user-pen" title={cs.subject} sub={`${cs.class_name} · ${cs.arm} · ${cs.term}`} />
      <form className="rs-card sj-form" onSubmit={submit}>
        <label className="sj-f"><span>Teacher</span>
          <input autoFocus value={teacher} onChange={(e) => setTeacher(e.target.value)} placeholder="Teacher name (blank = none)" /></label>
        <div className="sj-actions">
          <a href={d.cancel_url} className="rs-btn ghost">Cancel</a>
          <button type="submit" className="rs-btn primary" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> Save</button>
        </div>
      </form>
    </div>
  );
}
