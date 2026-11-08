import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Workflow, Scores, BulkEntry, Broadsheet, Affective, Comments } from './results';
import { Analytics, Institution, Teacher, SubjectScorecard } from './analytics';

// Whole numbers print without a trailing .0 (34, not 34.0); genuine decimals to
// two places (34.3 -> 34.30). Non-numeric / blank values pass through.
function fmtNum(v) {
  if (v == null || v === '') return v;
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}


// ---- Subjects list ---------------------------------------------------------
function List({ d, notify }) {
  const nav = useNav();
  const [tab, setTab] = useState('junior');
  const del = async (url, name) => {
    if (!await confirm(`Delete ${name}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  const categories = tab === 'junior' ? d.junior_categories : d.senior_categories;
  return (
    <>
      <div className="page-header"><h1>Subjects</h1>
        <div className="page-header-actions">
          {canWrite(d, 'subjects_create') && <a href={d.urls.bulk_add} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-list" /> Bulk Add</a>}
          {canWrite(d, 'subjects_create') && <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}
        </div>
      </div>
      <div className="card mb-3" style={{ padding: '.25rem' }}>
        <div style={{ display: 'flex', gap: '.25rem' }}>
          <button type="button" className={'btn btn-sm ' + (tab === 'junior' ? 'btn-primary' : 'btn-light')} onClick={() => setTab('junior')}>Junior Secondary (JSS)</button>
          <button type="button" className={'btn btn-sm ' + (tab === 'senior' ? 'btn-primary' : 'btn-light')} onClick={() => setTab('senior')}>Senior Secondary (SSS)</button>
        </div>
      </div>
      {categories.length ? categories.map((cat) => (
        <div className="card mb-3" key={cat.name}>
          <div className="card-header"><h3>{cat.name} ({cat.subjects.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <div className="data-cards" style={{ padding: '1rem' }}>
              {cat.subjects.map((s) => (
                <div className="data-card" key={s.id}>
                  <div className="data-card-header">
                    <div className="data-card-title">{s.name}</div>
                    <span className="badge badge-secondary">{s.short_name}</span>
                  </div>
                  {s.for_junior && s.for_senior && <div className="text-muted text-sm">JSS &amp; SSS</div>}
                  {(canWrite(d, 'subjects_edit') || canWrite(d, 'subjects_delete')) && <div className="data-card-actions">
                    {canWrite(d, 'subjects_edit') && <a href={s.edit_url} className="btn btn-secondary btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>}
                    {canWrite(d, 'subjects_delete') && <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(s.delete_url, s.name)}><i aria-hidden="true" className="fas fa-trash" /></button>}
                  </div>}
                </div>))}
            </div>
          </div>
        </div>
      )) : (
        <div className="card"><div className="card-body"><Empty icon="fa-book" title={`No ${tab === 'junior' ? 'JSS' : 'SSS'} Subjects`}><p>Add a subject and mark it for {tab === 'junior' ? 'Junior' : 'Senior'} Secondary</p>{canWrite(d, 'subjects_create') && <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Subject</a>}</Empty></div></div>
      )}
    </>
  );
}

// ---- Add / edit subject ----------------------------------------------------
function SubjectForm({ d, notify }) {
  const nav = useNav();
  const init = d.subject || { name: '', short_name: '', category: d.categories[0], has_practical: true, for_junior: true, for_senior: true };
  const [f, setF] = useState({ name: init.name, short_name: init.short_name, category: init.category,
    has_practical: init.has_practical, for_junior: init.for_junior, for_senior: init.for_senior });
  const [busy, setBusy] = useState(false);
  const isEdit = d.page === 'edit';
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify('error', 'Subject name is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, has_practical: f.has_practical ? 'on' : '',
      for_junior: f.for_junior ? 'on' : '', for_senior: f.for_senior ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>{isEdit ? 'Edit Subject' : 'Add Subject'}</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Subject Name <span className="required">*</span></label>
          <input type="text" className="form-control" required placeholder="e.g., Mathematics" value={f.name} onChange={(e) => set('name', e.target.value)} /></div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Short Name</label>
            <input type="text" className="form-control" placeholder="e.g., MATH" maxLength="10" value={f.short_name} onChange={(e) => set('short_name', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Category</label>
            <select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>{d.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        </div>
        <div className="form-group">
          <label className="form-label">Offered at</label>
          <div className="d-flex gap-3">
            <label className="d-flex gap-2 align-center mb-0"><input type="checkbox" checked={f.for_junior} onChange={(e) => set('for_junior', e.target.checked)} /> Junior Secondary (JSS)</label>
            <label className="d-flex gap-2 align-center mb-0"><input type="checkbox" checked={f.for_senior} onChange={(e) => set('for_senior', e.target.checked)} /> Senior Secondary (SSS)</label>
          </div>
          <span className="form-hint d-block">Controls which level's subject list this shows up in when assigning subjects to a class.</span>
        </div>
        <div className="form-check mb-3">
          <input type="checkbox" id="has_practical" className="form-check-input" checked={f.has_practical} onChange={(e) => set('has_practical', e.target.checked)} />
          <label htmlFor="has_practical" className="form-check-label">Has Midterm / Practical (P/ME)</label>
          <span className="form-hint d-block">If unchecked, the Midterm column is dropped and the Theory paper is worth 50 (instead of 40).</span>
        </div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Bulk add --------------------------------------------------------------
function BulkAdd({ d, notify }) {
  const nav = useNav();
  const [category, setCategory] = useState(d.categories[0]);
  const [text, setText] = useState(d.default_subjects);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.submit_url, { category, subjects: text });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not add.');
  };
  return (
    <>
      <div className="page-header"><h1>Bulk Add Subjects</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Category</label>
          <select className="form-control" value={category} onChange={(e) => setCategory(e.target.value)}>{d.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Subjects (one per line)</label>
          <textarea className="form-control" rows="15" value={text} onChange={(e) => setText(e.target.value)} /></div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Add All</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Class subjects list ---------------------------------------------------
function ClassSubjects({ d, notify }) {
  const nav = useNav();
  const [showCopy, setShowCopy] = useState(false);
  const [copyFrom, setCopyFrom] = useState('');
  const [sel, setSel] = useState(() => new Set());
  const [bulkName, setBulkName] = useState('');
  const [busy, setBusy] = useState(false);
  const [level, setLevel] = useState('all');
  const sectionByClassId = {}; d.classes.forEach((c) => { sectionByClassId[c.id] = c.section; });
  const levelClasses = d.classes.filter((c) => level === 'all' || c.section === level);
  const levelSubjects = d.class_subjects.filter((cs) => level === 'all' || sectionByClassId[cs.class_id] === level);
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, ...extra });
  const del = async (url, name) => {
    if (!await confirm(`Remove ${name}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not remove.');
  };
  const toggleSel = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allSelected = levelSubjects.length > 0 && levelSubjects.every((cs) => sel.has(cs.id));
  const toggleAll = () => setSel(() => allSelected ? new Set() : new Set(levelSubjects.map((cs) => cs.id)));
  const applyBulk = async () => {
    if (!sel.size) return;
    const name = bulkName.trim();
    if (!name && !await confirm(`Clear the teacher on ${sel.size} subject(s)?`)) return;
    setBusy(true);
    const r = await submitJson(d.urls.bulk_teacher, { term_id: d.term_id || '', class_id: d.class_id || '',
      'cs_ids[]': [...sel], teacher_name: name });
    setBusy(false);
    if (r.ok) { notify('success', r.message); setSel(new Set()); setBulkName(''); nav.refresh(); }
    else notify('error', r.error || 'Could not apply.');
  };
  const copy = async (e) => {
    e.preventDefault();
    if (!copyFrom) { notify('error', 'Select a source term.'); return; }
    if (!await confirm('Copy subject assignments into this term?')) return;
    const r = await submitJson(d.urls.copy, { to_term_id: d.term_id, from_term_id: copyFrom, class_id: d.class_id || '' });
    if (r.ok) { notify('success', r.message); setShowCopy(false); nav.refresh(); } else notify('error', r.error || 'Could not copy.');
  };
  return (
    <>
      <div className="page-header"><h1>Class Subjects</h1>
        <div className="page-header-actions">
          {canWrite(d, 'subjects_assign') && d.term_id && <button type="button" className="btn btn-info btn-sm" onClick={() => setShowCopy((s) => !s)}><i aria-hidden="true" className="fas fa-copy" /> Copy from term</button>}
          {canWrite(d, 'subjects_assign') && <a href={d.urls.assign} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Assign</a>}
        </div>
      </div>

      <div className="card mb-3" style={{ padding: '.25rem' }}>
        <div style={{ display: 'flex', gap: '.25rem' }}>
          <button type="button" className={'btn btn-sm ' + (level === 'all' ? 'btn-primary' : 'btn-light')} onClick={() => { setLevel('all'); if (d.class_id && sectionByClassId[d.class_id] && sectionByClassId[d.class_id] !== 'all') go({ class_id: '' }); }}>All</button>
          <button type="button" className={'btn btn-sm ' + (level === 'junior' ? 'btn-primary' : 'btn-light')} onClick={() => { setLevel('junior'); if (d.class_id && sectionByClassId[d.class_id] !== 'junior') go({ class_id: '' }); }}>Junior Secondary (JSS)</button>
          <button type="button" className={'btn btn-sm ' + (level === 'senior' ? 'btn-primary' : 'btn-light')} onClick={() => { setLevel('senior'); if (d.class_id && sectionByClassId[d.class_id] !== 'senior') go({ class_id: '' }); }}>Senior Secondary (SSS)</button>
        </div>
      </div>

      {d.term_id && showCopy && (
        <div className="card mb-3" style={{ borderColor: 'var(--info)' }}>
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-copy" /> Copy subject assignments into {d.selected_term || 'this term'}</h3></div>
          <div className="card-body">
            <p className="text-muted text-sm">Copy the subject-to-class assignments (and teachers) from another term. You can modify them afterwards. Existing assignments are kept.</p>
            <form onSubmit={copy} className="d-flex gap-2 align-center flex-wrap">
              <label className="form-label mb-0">Copy from</label>
              <select className="form-control" style={{ maxWidth: 240 }} required value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
                <option value="">Select source term…</option>
                {d.terms.filter((t) => String(t.id) !== String(d.term_id)).map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select>
              <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-copy" /> Copy{d.class_id ? ' (this class)' : ' (all classes)'}</button>
            </form>
          </div></div>
      )}

      <div className="card mb-3"><div className="card-body"><form className="filter-form">
        <div className="form-group"><label className="form-label">Term</label>
          <select className="form-control" value={d.term_id} onChange={(e) => go({ term_id: e.target.value })}>
            <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Class</label>
          <select className="form-control" value={d.class_id} onChange={(e) => go({ class_id: e.target.value })}>
            <option value="">All Classes</option>{levelClasses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      </form></div></div>

      {canWrite(d, 'subjects_edit') && levelSubjects.length > 0 && (
        <div className="card mb-3" style={{ borderColor: 'var(--primary)' }}>
          <div className="card-body">
            <div className="d-flex gap-2 align-center flex-wrap">
              <label className="d-flex gap-2 align-center mb-0" style={{ whiteSpace: 'nowrap' }}>
                <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                <span className="text-sm">{sel.size ? `${sel.size} selected` : 'Select all'}</span>
              </label>
              <span className="text-muted text-sm">Set teacher on selected:</span>
              <input type="text" className="form-control" style={{ maxWidth: 260 }} placeholder="Teacher name (blank clears)"
                     value={bulkName} onChange={(e) => setBulkName(e.target.value)} />
              <button type="button" className="btn btn-primary btn-sm" disabled={busy || !sel.size} onClick={applyBulk}>
                <i aria-hidden="true" className="fas fa-user-check" /> Apply to {sel.size || 0}</button>
              {sel.size > 0 && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSel(new Set())}>Clear</button>}
            </div>
            <p className="text-muted text-sm mb-0 mt-2">Tick the subjects a teacher takes, type the name once, and apply it to all of them.</p>
          </div></div>
      )}

      {levelSubjects.length ? (
        <div className="card"><div className="card-header"><h3>Subjects ({levelSubjects.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <div className="data-cards" style={{ padding: '1rem' }}>
              {levelSubjects.map((cs) => (
                <div className={`data-card${sel.has(cs.id) ? ' selected' : ''}`} key={cs.id} style={sel.has(cs.id) ? { borderColor: 'var(--primary)' } : undefined}>
                  <div className="data-card-header">
                    <div className="data-card-title d-flex gap-2 align-center">
                      {canWrite(d, 'subjects_edit') && <input type="checkbox" checked={sel.has(cs.id)} onChange={() => toggleSel(cs.id)} aria-label={`Select ${cs.subject}`} />}
                      {cs.subject}
                    </div>
                    <span className="badge badge-info">{cs.class_name}</span></div>
                  <div className="data-card-row"><span className="data-card-label">Teacher</span><span>{cs.teacher_name || '-'}</span></div>
                  {cs.arm && <div className="data-card-row"><span className="data-card-label">Arm</span><span>{cs.arm}</span></div>}
                  {(canWrite(d, 'subjects_edit') || canWrite(d, 'subjects_delete')) && <div className="data-card-actions">
                    {canWrite(d, 'subjects_edit') && <a href={cs.edit_url} className="btn btn-secondary btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>}
                    {canWrite(d, 'subjects_delete') && <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(cs.delete_url, `${cs.subject} from ${cs.class_name}`)}><i aria-hidden="true" className="fas fa-times" /></button>}
                  </div>}
                </div>))}
            </div>
          </div></div>
      ) : d.term_id ? (
        <div className="card"><div className="card-body"><Empty icon="fa-book-open" title="No Subjects Assigned"><p>Assign subjects to classes for this term</p>{canWrite(d, 'subjects_assign') && <a href={d.urls.assign} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Assign Subjects</a>}</Empty></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select a Term"><p>Choose a term to view class subjects</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Assign ----------------------------------------------------------------
function Assign({ d, notify }) {
  const nav = useNav();
  const [termId, setTermId] = useState(() => { const a = d.terms.find((t) => t.is_active); return a ? String(a.id) : ''; });
  const [classId, setClassId] = useState('');
  const [armId, setArmId] = useState('');
  const [rows, setRows] = useState(() => { const m = {}; d.subjects.forEach((s) => { m[s.id] = { checked: false, teacher: '' }; }); return m; });
  const [busy, setBusy] = useState(false);
  const selectedClass = d.classes.find((c) => String(c.id) === String(classId));
  const visibleSubjects = d.subjects.filter((s) => {
    if (!selectedClass) return true;              // no class picked yet — show everything
    if (selectedClass.section === 'junior') return s.for_junior;
    if (selectedClass.section === 'senior') return s.for_senior;
    return true;                                   // nursery/primary/unset — not level-restricted
  });
  const allChecked = visibleSubjects.length > 0 && visibleSubjects.every((s) => rows[s.id].checked);
  const toggleAll = (v) => setRows((m) => { const n = { ...m }; visibleSubjects.forEach((s) => { n[s.id] = { ...n[s.id], checked: v }; }); return n; });
  const setRow = (id, k, v) => setRows((m) => ({ ...m, [id]: { ...m[id], [k]: v } }));
  const submit = async (e) => {
    e.preventDefault();
    if (!termId || !classId) { notify('error', 'Term and class are required.'); return; }
    const subject_ids = []; const teacher_names = [];
    visibleSubjects.forEach((s) => { if (rows[s.id].checked) { subject_ids.push(s.id); teacher_names.push(rows[s.id].teacher); } });
    if (!subject_ids.length) { notify('error', 'Select at least one subject.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { term_id: termId, class_id: classId, arm_id: armId || '',
      'subject_ids[]': subject_ids, 'teacher_names[]': teacher_names });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not assign.');
  };
  return (
    <>
      <div className="page-header"><h1>Assign Subjects to Class</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Term <span className="required">*</span></label>
            <select className="form-control" required value={termId} onChange={(e) => setTermId(e.target.value)}>
              <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Class <span className="required">*</span></label>
            <select className="form-control" required value={classId} onChange={(e) => setClassId(e.target.value)}>
              <option value="">Select Class</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Arm (optional)</label>
            <select className="form-control" value={armId} onChange={(e) => setArmId(e.target.value)}>
              <option value="">All Arms</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
            <small className="text-muted">Leave blank for all arms in class</small></div>
        </div>
        <h4 style={{ margin: '1.5rem 0 1rem' }}>Select Subjects &amp; Teachers</h4>
        {selectedClass && (selectedClass.section === 'junior' || selectedClass.section === 'senior') && (
          <p className="text-muted text-sm" style={{ marginTop: '-.5rem' }}>
            Showing {selectedClass.section === 'junior' ? 'Junior Secondary' : 'Senior Secondary'} subjects only.
          </p>
        )}
        <div className="table-container"><table className="data-table">
          <thead><tr><th style={{ width: 40 }}><input type="checkbox" checked={allChecked} onChange={(e) => toggleAll(e.target.checked)} /></th><th>Subject</th><th>Teacher Name</th></tr></thead>
          <tbody>{visibleSubjects.map((s) => (
            <tr key={s.id}>
              <td><input type="checkbox" checked={rows[s.id].checked} onChange={(e) => setRow(s.id, 'checked', e.target.checked)} /></td>
              <td>{s.name} <small className="text-muted">({s.category})</small></td>
              <td><input type="text" className="form-control" placeholder="Teacher name" value={rows[s.id].teacher} onChange={(e) => setRow(s.id, 'teacher', e.target.value)} /></td>
            </tr>))}</tbody>
        </table></div>
        <div className="page-header-actions mt-3">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Assign Selected</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Edit class subject ----------------------------------------------------
function EditClassSubject({ d, notify }) {
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
  const Row = ({ k, v }) => <div className="info-row"><span className="text-muted">{k}</span><strong>{v}</strong></div>;
  return (
    <>
      <div className="page-header"><h1>Edit: {cs.subject}</h1></div>
      <div className="card"><div className="card-body">
        <div className="info-grid mb-3"><Row k="Subject" v={cs.subject} /><Row k="Class" v={cs.class_name} /><Row k="Arm" v={cs.arm} /><Row k="Term" v={cs.term} /></div>
        <form onSubmit={submit}>
          <div className="form-group"><label className="form-label">Teacher Name</label>
            <input type="text" className="form-control" placeholder="Enter teacher name" value={teacher} onChange={(e) => setTeacher(e.target.value)} /></div>
          <div className="page-header-actions">
            <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</button>
            <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
          </div>
        </form>
      </div></div>
    </>
  );
}

// ---- Results Explorer (cross-class / cross-arm filter + compare) -----------
function Explore({ d }) {
  const nav = useNav();
  const rows = d.rows || [];
  const subjects = d.subjects_union || [];
  const scopes = d.scope_meta || [];
  const passMark = d.pass_mark || 50;

  // Local scope picker (assignment ids) — applied on demand so ticking several
  // boxes doesn't fire a fetch per click.
  const [sel, setSel] = useState(() => new Set((d.scopes || []).map(String)));
  const toggle = (id) => setSel((s) => { const n = new Set(s); const k = String(id); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleClass = (cls, on) => setSel((s) => {
    const n = new Set(s); cls.arms.forEach((a) => { on ? n.add(String(a.assignment_id)) : n.delete(String(a.assignment_id)); }); return n;
  });
  const classAll = (cls) => cls.arms.every((a) => sel.has(String(a.assignment_id)));
  const load = () => navParams(nav.go, d.self_url, { term_id: d.term_id, scopes: [...sel].join(',') });
  const selChanged = [...sel].sort().join(',') !== (d.scopes || []).map(String).sort().join(',');

  // ---- Filter: field × operator × value(s) --------------------------------
  const [field, setField] = useState('average');
  const [op, setOp] = useState('gte');
  const [v1, setV1] = useState('');
  const [v2, setV2] = useState('');
  const n1 = parseFloat(v1), n2 = parseFloat(v2);
  const has1 = !Number.isNaN(n1), has2 = !Number.isNaN(n2);
  const active = op === 'between' ? (has1 && has2) : has1;
  const fieldVal = (r) => field === 'average' ? r.average : field === 'total' ? r.total
    : (r.subjects[String(field)] == null ? null : r.subjects[String(field)]);
  const matches = (r) => {
    const x = fieldVal(r);
    if (x == null) return false;
    if (op === 'gte') return x >= n1;
    if (op === 'lte') return x <= n1;
    if (op === 'eq') return x === n1;
    if (op === 'between') return x >= Math.min(n1, n2) && x <= Math.max(n1, n2);
    return true;
  };
  const fieldName = field === 'average' ? 'Average (%)' : field === 'total' ? 'Total'
    : (subjects.find((s) => String(s.id) === String(field)) || {}).name || 'Subject';
  const opText = { gte: '≥', lte: '≤', eq: '=', between: 'between' }[op];

  // Server export/print URL carries the current scope + filter so the file
  // matches the on-screen view (a combined, filtered cross-class document).
  const exportUrl = (fmt) => {
    const p = new URLSearchParams();
    p.set('term_id', d.term_id || '');
    p.set('scopes', (d.scopes || []).join(','));
    p.set('format', fmt);
    if (active) { p.set('field', field); p.set('op', op); p.set('v1', v1); if (op === 'between') p.set('v2', v2); }
    return `${d.urls.export}?${p.toString()}`;
  };

  // ---- Sorting -------------------------------------------------------------
  const [sortKey, setSortKey] = useState('average');   // 'average'|'total'|subjectId
  const [sortDir, setSortDir] = useState('desc');
  const sortVal = (r) => sortKey === 'average' ? r.average : sortKey === 'total' ? r.total
    : (r.subjects[String(sortKey)] == null ? -1 : r.subjects[String(sortKey)]);
  const clickSort = (k) => { if (sortKey === k) setSortDir((x) => x === 'desc' ? 'asc' : 'desc'); else { setSortKey(k); setSortDir('desc'); } };

  const shown = React.useMemo(() => {
    let r = active ? rows.filter(matches) : rows.slice();
    r.sort((a, b) => { const d2 = sortVal(b) - sortVal(a); return sortDir === 'desc' ? d2 : -d2; });
    return r;
  }, [rows, active, op, n1, n2, field, sortKey, sortDir]);

  // ---- Per-scope comparison ------------------------------------------------
  const mean = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
  const statFor = (list) => {
    const avgs = list.map((r) => r.average);
    const fieldVals = list.map(fieldVal).filter((x) => x != null);
    const passed = list.filter((r) => r.average >= passMark).length;
    return {
      n: list.length,
      meanAvg: mean(avgs),
      passRate: list.length ? (passed / list.length) * 100 : null,
      meanField: mean(fieldVals),
      matching: active ? list.filter(matches).length : list.length,
    };
  };
  const scopeRows = scopes.map((sc) => ({ sc, st: statFor(rows.filter((r) => r.assignment_id === sc.assignment_id)) }));
  const overall = statFor(rows);

  const exportCsv = () => {
    const head = ['Position', 'Student', 'Class', 'Arm', ...subjects.map((s) => s.name), 'Total', 'Average', 'Passed', 'Failed'];
    const lines = [head.join(',')];
    shown.forEach((r, i) => {
      const cells = [i + 1, r.student, r.class_name, r.arm_name,
        ...subjects.map((s) => r.subjects[String(s.id)] ?? ''),
        r.total, r.average, r.passed, r.failed];
      lines.push(cells.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'results_explorer.csv'; a.click(); URL.revokeObjectURL(a.href);
  };

  const sortIcon = (k) => sortKey === k ? (sortDir === 'desc' ? ' ▼' : ' ▲') : '';
  const cellHi = (r, subjId) => active && String(field) === String(subjId) && matches(r);

  return (
    <>
      <div className="page-header">
        <div><h1>Results Explorer</h1>
          <p className="text-muted text-sm">Filter and compare results within a class arm, across arms and across classes.</p></div>
        <div className="page-header-actions">
          {d.urls.combine && <a href={d.urls.combine} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-layer-group" /> Combine subjects</a>}
          {d.urls.broadsheet && <a href={d.urls.broadsheet} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-table" /> Broadsheet</a>}
        </div>
      </div>

      {/* Term + scope picker */}
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form" style={{ marginBottom: '.6rem' }}>
          <div className="form-group"><label className="form-label">Term</label>
            <select className="form-control" value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value, scopes: '' })}>
              <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
        </div>
        {d.scope_options.length ? (
          <>
            <label className="form-label">Classes &amp; arms to include</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.9rem', margin: '.3rem 0 .7rem' }}>
              {d.scope_options.map((cls) => (
                <div key={cls.class_id} className="card" style={{ padding: '.5rem .7rem', minWidth: 150 }}>
                  <label className="form-check" style={{ fontWeight: 700, display: 'flex', gap: '.4rem', alignItems: 'center' }}>
                    <input type="checkbox" checked={classAll(cls)} onChange={(e) => toggleClass(cls, e.target.checked)} /> {cls.class_name}
                  </label>
                  <div style={{ paddingLeft: '.4rem', marginTop: '.2rem' }}>
                    {cls.arms.map((a) => (
                      <label key={a.assignment_id} className="form-check" style={{ display: 'flex', gap: '.4rem', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                        <input type="checkbox" checked={sel.has(String(a.assignment_id))} onChange={() => toggle(a.assignment_id)} /> {a.arm_name || cls.class_name}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <button type="button" className="btn btn-primary btn-sm" disabled={!sel.size} onClick={load}>
              <i aria-hidden="true" className="fas fa-layer-group" /> {selChanged ? 'Load selection' : 'Reload'} ({sel.size})
            </button>
          </>
        ) : <p className="text-muted text-sm">Select a term to choose classes.</p>}
      </div></div>

      {rows.length ? (<>
        {/* Filter bar */}
        <div className="card mb-3"><div className="card-body">
          <form className="filter-form" onSubmit={(e) => e.preventDefault()} style={{ display: 'flex', gap: '.6rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="form-group"><label className="form-label">Field</label>
              <select className="form-control" value={field} onChange={(e) => setField(e.target.value)}>
                <option value="average">Average (%)</option>
                <option value="total">Total</option>
                {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select></div>
            <div className="form-group"><label className="form-label">Condition</label>
              <select className="form-control" value={op} onChange={(e) => setOp(e.target.value)}>
                <option value="gte">at or above (≥)</option>
                <option value="lte">at or below (≤)</option>
                <option value="between">between</option>
                <option value="eq">exactly (=)</option>
              </select></div>
            <div className="form-group"><label className="form-label">{op === 'between' ? 'From' : 'Value'}</label>
              <input type="number" className="form-control" style={{ maxWidth: 110 }} value={v1} step="0.1" placeholder="e.g. 50" onChange={(e) => setV1(e.target.value)} /></div>
            {op === 'between' && <div className="form-group"><label className="form-label">To</label>
              <input type="number" className="form-control" style={{ maxWidth: 110 }} value={v2} step="0.1" placeholder="e.g. 70" onChange={(e) => setV2(e.target.value)} /></div>}
            {active && <div className="form-group"><button type="button" className="btn btn-secondary" onClick={() => { setV1(''); setV2(''); }}><i aria-hidden="true" className="fas fa-times" /> Clear</button></div>}
            <div className="form-group" style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
              <a href={exportUrl('excel')} data-native download className="btn btn-success"><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
              <a href={exportUrl('pdf')} data-native download className="btn btn-success"><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>
              <a href={exportUrl('pdf')} data-native target="_blank" rel="noopener" className="btn btn-secondary" title="Open a print-ready PDF in a new tab"><i aria-hidden="true" className="fas fa-print" /> Print</a>
              <button type="button" className="btn btn-secondary" onClick={exportCsv}><i aria-hidden="true" className="fas fa-file-csv" /> CSV</button>
            </div>
          </form>
          <p className="text-muted text-sm" style={{ margin: '.3rem 0 0' }}>
            {active ? <><strong>{shown.length}</strong> of {rows.length} student(s) with {fieldName} {opText} {op === 'between' ? `${Math.min(n1, n2)}–${Math.max(n1, n2)}` : n1}</> : <><strong>{rows.length}</strong> student(s) across {scopes.length} scope(s)</>}
          </p>
        </div></div>

        {/* Comparison */}
        <div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-scale-balanced" /> Compare scopes</h3></div>
          <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table" style={{ minWidth: '100%' }}>
              <thead><tr>
                <th>Class arm</th><th style={{ textAlign: 'center' }}>Students</th>
                <th style={{ textAlign: 'center' }}>Mean avg</th><th style={{ textAlign: 'center' }}>Pass rate</th>
                <th style={{ textAlign: 'center' }}>Mean {fieldName}</th>
                {active && <th style={{ textAlign: 'center' }}>Matching</th>}
              </tr></thead>
              <tbody>
                {scopeRows.map(({ sc, st }) => (
                  <tr key={sc.assignment_id}>
                    <td>{sc.label}</td>
                    <td style={{ textAlign: 'center' }}>{st.n}</td>
                    <td style={{ textAlign: 'center' }}>{st.meanAvg == null ? '-' : fmtNum(Math.round(st.meanAvg * 100) / 100)}</td>
                    <td style={{ textAlign: 'center' }}>{st.passRate == null ? '-' : `${Math.round(st.passRate)}%`}</td>
                    <td style={{ textAlign: 'center' }}>{st.meanField == null ? '-' : fmtNum(Math.round(st.meanField * 100) / 100)}</td>
                    {active && <td style={{ textAlign: 'center' }}><span className="badge badge-info">{st.matching}</span></td>}
                  </tr>
                ))}
                {scopes.length > 1 && (
                  <tr style={{ fontWeight: 700, borderTop: '2px solid var(--border-color)' }}>
                    <td>All selected</td>
                    <td style={{ textAlign: 'center' }}>{overall.n}</td>
                    <td style={{ textAlign: 'center' }}>{overall.meanAvg == null ? '-' : fmtNum(Math.round(overall.meanAvg * 100) / 100)}</td>
                    <td style={{ textAlign: 'center' }}>{overall.passRate == null ? '-' : `${Math.round(overall.passRate)}%`}</td>
                    <td style={{ textAlign: 'center' }}>{overall.meanField == null ? '-' : fmtNum(Math.round(overall.meanField * 100) / 100)}</td>
                    {active && <td style={{ textAlign: 'center' }}><span className="badge badge-info">{overall.matching}</span></td>}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Detail table */}
        <div className="card">
          <div className="card-header"><h3>Students</h3>
            <span className="badge badge-info">{shown.length}{active ? ` of ${rows.length}` : ''}</span></div>
          <div className="card-body" style={{ padding: 0, overflow: 'auto', maxHeight: '70vh' }}>
            <table className="data-table" style={{ minWidth: '100%' }}>
              <thead><tr>
                <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>#</th>
                <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Student</th>
                <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Class</th>
                <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Arm</th>
                {subjects.map((s) => (
                  <th key={s.id} title={s.name} onClick={() => clickSort(s.id)}
                      style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
                    {s.short}{sortIcon(s.id)}</th>
                ))}
                <th onClick={() => clickSort('total')} style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center', cursor: 'pointer' }}>Total{sortIcon('total')}</th>
                <th onClick={() => clickSort('average')} style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center', cursor: 'pointer' }}>Avg{sortIcon('average')}</th>
                <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center' }}>P/F</th>
              </tr></thead>
              <tbody>{shown.length ? shown.map((r, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 'bold' }}>{i + 1}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{r.student}</td>
                  <td>{r.class_name}</td>
                  <td>{r.arm_name}</td>
                  {subjects.map((s) => {
                    const v = r.subjects[String(s.id)];
                    return <td key={s.id} style={{ textAlign: 'center', background: cellHi(r, s.id) ? 'rgba(37,99,235,.14)' : undefined }}>{v != null ? fmtNum(v) : '-'}</td>;
                  })}
                  <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{fmtNum(r.total)}</td>
                  <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{fmtNum(r.average)}</td>
                  <td style={{ textAlign: 'center' }}><span className="badge badge-success">{r.passed}</span> <span className="badge badge-danger">{r.failed}</span></td>
                </tr>
              )) : (
                <tr><td colSpan={subjects.length + 7} style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)' }}>No students match this condition.</td></tr>
              )}</tbody>
            </table>
          </div>
        </div>
      </>) : d.scopes && d.scopes.length ? (
        <div className="card"><div className="card-body"><Empty icon="fa-table" title="No scores"><p>No entered scores for the selected class arm(s) yet.</p></Empty></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Pick your scopes"><p>Choose a term, tick the classes and arms to include, then Load.</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Subject Combination Explorer -----------------------------------------
// Pick any set of subjects; filter students by their COMBINED total/average
// across just those subjects; export the view (with a column picker).
function Combine({ d, notify }) {
  const nav = useNav();
  const rows = d.rows || [];
  const subjects = d.subjects_union || [];

  const [sel, setSel] = useState(() => new Set((d.scopes || []).map(String)));
  const toggleScope = (id) => setSel((s) => { const n = new Set(s); const k = String(id); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleClass = (cls, on) => setSel((s) => { const n = new Set(s); cls.arms.forEach((a) => { on ? n.add(String(a.assignment_id)) : n.delete(String(a.assignment_id)); }); return n; });
  const classAll = (cls) => cls.arms.every((a) => sel.has(String(a.assignment_id)));
  const load = () => navParams(nav.go, d.self_url, { term_id: d.term_id, scopes: [...sel].join(',') });
  const selChanged = [...sel].sort().join(',') !== (d.scopes || []).map(String).sort().join(',');

  // Subject combination
  const [subjSel, setSubjSel] = useState(() => new Set());
  const toggleSubj = (id) => setSubjSel((s) => { const n = new Set(s); const k = String(id); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const chosen = subjects.filter((s) => subjSel.has(String(s.id)));

  // Multi-condition AND filter. Each condition tests a basis (all subjects vs the
  // chosen combination, total vs average) optionally on one assessment component
  // (e.g. Exam) — so you can ask e.g. "all-subject average ≥ 50 AND exam average
  // ≥ 67 across Physics+Chemistry+Biology" to pick who qualifies for a stream.
  const ats = d.assessment_types || [];
  let condId = React.useRef(1);
  const [conds, setConds] = useState(() => [{ id: 0, basis: 'combo_average', component: '', op: 'gte', value: '' }]);
  const addCond = () => setConds((cs) => [...cs, { id: condId.current++, basis: 'combo_average', component: '', op: 'gte', value: '' }]);
  const rmCond = (id) => setConds((cs) => (cs.length > 1 ? cs.filter((c) => c.id !== id) : cs));
  const setCond = (id, k, v) => setConds((cs) => cs.map((c) => (c.id === id ? { ...c, [k]: v } : c)));

  const computed = React.useMemo(() => {
    const n = chosen.length;
    return rows.map((r) => {
      let total = 0;
      chosen.forEach((s) => { const v = r.subjects[String(s.id)]; if (v != null) total += v; });
      total = Math.round(total * 10) / 10;
      const average = n ? Math.round((total / n) * 100) / 100 : 0;
      return { ...r, combo_total: total, combo_average: average };
    });
  }, [rows, subjSel]);

  const condValue = (r, basis, component) => {
    if (basis === 'all_total') return r.total;
    if (basis === 'all_average') return r.average;
    const n = chosen.length;
    if (!n) return null;
    let tot = 0;
    chosen.forEach((s) => {
      const sid = String(s.id);
      let v;
      if (component) v = (r.components && r.components[sid]) ? r.components[sid][String(component)] : undefined;
      else v = r.subjects[sid];
      tot += (v != null ? v : 0);
    });
    tot = Math.round(tot * 10) / 10;
    return basis === 'combo_total' ? tot : Math.round((tot / n) * 100) / 100;
  };
  const activeConds = conds.filter((c) => c.value !== '' && !Number.isNaN(parseFloat(c.value)));
  const active = activeConds.length > 0 && chosen.length > 0;
  const passes = (r, c) => {
    const x = condValue(r, c.basis, c.basis.indexOf('combo') === 0 ? c.component : '');
    if (x == null) return false;
    const v = parseFloat(c.value);
    if (c.op === 'gte') return x >= v;
    if (c.op === 'lte') return x <= v;
    if (c.op === 'eq') return x === v;
    return true;
  };
  const shown = React.useMemo(() => {
    const list = active ? computed.filter((r) => activeConds.every((c) => passes(r, c))) : computed.slice();
    list.sort((a, b) => b.combo_total - a.combo_total);
    return list;
  }, [computed, conds]);

  // Export column picker
  const [showExport, setShowExport] = useState(false);
  const [expTitle, setExpTitle] = useState('');
  const [groupsN, setGroupsN] = useState(1);   // 1 = don't split
  const [cols, setCols] = useState({ sn: true, student: true, class: true, arm: true, subjects: true, total: true, average: true, missing: false });
  const setCol = (k) => setCols((c) => ({ ...c, [k]: !c[k] }));
  const exportUrl = (fmt) => {
    const keys = [];
    if (cols.sn) keys.push('sn');
    if (cols.student) keys.push('student');
    if (cols.class) keys.push('class');
    if (cols.arm) keys.push('arm');
    if (cols.subjects) chosen.forEach((s) => keys.push('subj:' + s.id));
    if (cols.total) keys.push('total');
    if (cols.average) keys.push('average');
    if (cols.missing) keys.push('missing');
    const p = new URLSearchParams();
    p.set('term_id', d.term_id || '');
    p.set('scopes', (d.scopes || []).join(','));
    p.set('subjects', chosen.map((s) => s.id).join(','));
    if (activeConds.length) {
      p.set('conditions', JSON.stringify(activeConds.map((c) => ({
        basis: c.basis, component: c.basis.indexOf('combo') === 0 ? c.component : '',
        op: c.op, value: c.value }))));
    }
    p.set('columns', keys.join(','));
    if (expTitle.trim()) p.set('title', expTitle.trim());
    if (groupsN >= 2) p.set('groups', String(groupsN));
    p.set('format', fmt);
    return `${d.urls.export}?${p.toString()}`;
  };
  const saveBlob = (blob, name) => {
    const u = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = u; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 4000);
  };
  // Images can span several A4 pages; download each page as its own file.
  const downloadImages = async (url) => {
    let page = 1, total = 1;
    do {
      const res = await fetch(url + '&page=' + page, { credentials: 'same-origin' });
      if (!res.ok) { notify('error', 'Could not generate the image.'); return; }
      total = parseInt(res.headers.get('X-Total-Pages') || '1', 10) || 1;
      const blob = await res.blob();
      saveBlob(blob, total > 1 ? `subject_combination_p${page}.png` : 'subject_combination.png');
      page += 1;
    } while (page <= total);
    if (total > 1) notify('success', `Downloaded ${total} image pages.`);
  };
  const doExport = (fmt) => {
    if (!chosen.length) { notify('error', 'Pick at least one subject to combine.'); return; }
    if (fmt === 'image') { downloadImages(exportUrl(fmt)); setShowExport(false); return; }
    window.location.href = exportUrl(fmt);
    setShowExport(false);
  };

  return (
    <>
      <div className="page-header">
        <div><h1>Subject Combination</h1>
          <p className="text-muted text-sm">Pick subjects (e.g. Physics + Chemistry + Biology) and stack conditions — e.g. all-subject average ≥ 50 AND exam average ≥ 67 across the chosen subjects — to find who qualifies (for a stream, an award, etc.).</p></div>
        <div className="page-header-actions">
          {d.urls.explore && <a href={d.urls.explore} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-filter" /> Explorer</a>}
          {d.urls.broadsheet && <a href={d.urls.broadsheet} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-table" /> Broadsheet</a>}
        </div>
      </div>

      {/* Term + scope picker */}
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form" style={{ marginBottom: '.6rem' }}>
          <div className="form-group"><label className="form-label">Term</label>
            <select className="form-control" value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value, scopes: '' })}>
              <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
        </div>
        {d.scope_options.length ? (
          <>
            <label className="form-label">Classes &amp; arms to include</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.9rem', margin: '.3rem 0 .7rem' }}>
              {d.scope_options.map((cls) => (
                <div key={cls.class_id} className="card" style={{ padding: '.5rem .7rem', minWidth: 150 }}>
                  <label className="form-check" style={{ fontWeight: 700, display: 'flex', gap: '.4rem', alignItems: 'center' }}>
                    <input type="checkbox" checked={classAll(cls)} onChange={(e) => toggleClass(cls, e.target.checked)} /> {cls.class_name}
                  </label>
                  <div style={{ paddingLeft: '.4rem', marginTop: '.2rem' }}>
                    {cls.arms.map((a) => (
                      <label key={a.assignment_id} className="form-check" style={{ display: 'flex', gap: '.4rem', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                        <input type="checkbox" checked={sel.has(String(a.assignment_id))} onChange={() => toggleScope(a.assignment_id)} /> {a.arm_name || cls.class_name}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <button type="button" className="btn btn-primary btn-sm" onClick={load} disabled={!selChanged && rows.length > 0}>
              <i aria-hidden="true" className="fas fa-rotate" /> Load selected</button>
          </>
        ) : <p className="text-muted text-sm">Pick a term to choose classes and arms.</p>}
      </div></div>

      {rows.length > 0 && (
        <div className="card mb-3"><div className="card-body">
          <label className="form-label">Subjects to combine</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.5rem 1.1rem', margin: '.3rem 0 .8rem' }}>
            {subjects.map((s) => (
              <label key={s.id} className="form-check" style={{ display: 'flex', gap: '.4rem', alignItems: 'center' }}>
                <input type="checkbox" checked={subjSel.has(String(s.id))} onChange={() => toggleSubj(s.id)} /> {s.name}
              </label>
            ))}
          </div>
          {chosen.length > 0 && (
            <div style={{ marginTop: '.3rem' }}>
              <label className="form-label">Conditions <span className="text-muted" style={{ fontWeight: 400 }}>(all must be met)</span></label>
              {conds.map((c) => {
                const isCombo = c.basis.indexOf('combo') === 0;
                return (
                  <div key={c.id} className="filter-form" style={{ alignItems: 'flex-end', marginBottom: '.4rem' }}>
                    <div className="form-group"><label className="form-label">Basis</label>
                      <select className="form-control" value={c.basis} onChange={(e) => setCond(c.id, 'basis', e.target.value)}>
                        <option value="combo_average">Selected subjects · average</option>
                        <option value="combo_total">Selected subjects · total</option>
                        <option value="all_average">All subjects · average</option>
                        <option value="all_total">All subjects · total</option>
                      </select></div>
                    {isCombo && ats.length > 0 && (
                      <div className="form-group"><label className="form-label">Component</label>
                        <select className="form-control" value={c.component} onChange={(e) => setCond(c.id, 'component', e.target.value)}>
                          <option value="">Whole subject</option>
                          {ats.map((at) => <option key={at.id} value={at.id}>{at.name} only</option>)}
                        </select></div>
                    )}
                    <div className="form-group"><label className="form-label">Is</label>
                      <select className="form-control" value={c.op} onChange={(e) => setCond(c.id, 'op', e.target.value)}>
                        <option value="gte">≥ (at least)</option><option value="lte">≤ (at most)</option><option value="eq">= (exactly)</option></select></div>
                    <div className="form-group"><label className="form-label">Value</label>
                      <input type="number" className="form-control" style={{ width: 110 }} value={c.value} onChange={(e) => setCond(c.id, 'value', e.target.value)} placeholder="e.g. 50" /></div>
                    <div className="form-group">
                      <button type="button" className="btn btn-secondary btn-sm" title="Remove condition" disabled={conds.length <= 1} onClick={() => rmCond(c.id)}><i aria-hidden="true" className="fas fa-times" /></button>
                    </div>
                  </div>
                );
              })}
              <div className="d-flex gap-2" style={{ marginTop: '.2rem' }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={addCond}><i aria-hidden="true" className="fas fa-plus" /> Add condition</button>
                <button type="button" className="btn btn-success btn-sm" onClick={() => setShowExport(true)}><i aria-hidden="true" className="fas fa-download" /> Export</button>
              </div>
            </div>
          )}
          {chosen.length > 0 && (
            <p className="text-muted text-sm mb-0" style={{ marginTop: '.5rem' }}>
              Combining <strong>{chosen.map((s) => s.name).join(' + ')}</strong>
              {active ? <> · <strong>{shown.length}</strong> of {rows.length} students meet all {activeConds.length} condition(s)</> : <> · {rows.length} students</>}
              . Averages divide by {chosen.length} chosen subject(s); missing scores count as 0.
            </p>
          )}
        </div></div>
      )}

      {chosen.length > 0 && (
        <div className="card">
          <div className="card-header"><h3>Students ({shown.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container" style={{ maxHeight: '70vh', overflow: 'auto' }}>
            <table className="data-table"><thead><tr>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>#</th>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Student</th>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Class</th>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Arm</th>
              {chosen.map((s) => <th key={s.id} title={s.name} style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center', fontSize: 'var(--text-xs)' }}>{s.short}</th>)}
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center' }}>Total</th>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center' }}>Avg</th>
            </tr></thead>
            <tbody>{shown.length ? shown.map((r, i) => (
              <tr key={i}>
                <td style={{ fontWeight: 'bold' }}>{i + 1}</td>
                <td style={{ whiteSpace: 'nowrap' }}>{r.student}</td>
                <td>{r.class_name}</td><td>{r.arm_name}</td>
                {chosen.map((s) => { const v = r.subjects[String(s.id)]; return <td key={s.id} style={{ textAlign: 'center' }}>{v != null ? fmtNum(v) : '-'}</td>; })}
                <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{fmtNum(r.combo_total)}</td>
                <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{fmtNum(r.combo_average)}</td>
              </tr>
            )) : <tr><td colSpan={6 + chosen.length} style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)' }}>No students match this condition.</td></tr>}</tbody>
            </table>
          </div></div>
        </div>
      )}

      {showExport && (
        <div className="modal-backdrop" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowExport(false)}>
          <div className="card" style={{ maxWidth: 460, width: '92%' }} onClick={(e) => e.stopPropagation()}>
            <div className="card-header"><h3><i aria-hidden="true" className="fas fa-download" /> Export combination</h3></div>
            <div className="card-body">
              <p className="text-muted text-sm">Choose the columns to include, then pick a format.</p>
              <label className="form-label" style={{ fontWeight: 600 }}>Heading <span className="text-muted" style={{ fontWeight: 400 }}>(optional)</span></label>
              <input type="text" className="form-control" style={{ marginBottom: '.8rem' }} maxLength={120}
                     placeholder="e.g. SSS2 SCIENCE CLASS MERIT LIST" value={expTitle}
                     onChange={(e) => setExpTitle(e.target.value)} />
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.4rem 1.1rem', marginBottom: '.8rem' }}>
                {[['sn', 'S/N'], ['student', 'Student'], ['class', 'Class'], ['arm', 'Arm'], ['subjects', 'Each subject'], ['total', 'Combined total'], ['average', 'Combined average'], ['missing', 'Missing count']].map(([k, label]) => (
                  <label key={k} className="form-check" style={{ display: 'flex', gap: '.4rem', alignItems: 'center' }}>
                    <input type="checkbox" checked={!!cols[k]} onChange={() => setCol(k)} /> {label}
                  </label>
                ))}
              </div>
              <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '.7rem', marginBottom: '.8rem' }}>
                <label className="form-label" style={{ fontWeight: 600 }}>Split into balanced groups</label>
                <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center' }}>
                  <select className="form-control" style={{ width: 'auto' }} value={groupsN}
                          onChange={(e) => setGroupsN(parseInt(e.target.value, 10) || 1)}>
                    <option value={1}>Don't split — one list</option>
                    {[2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n} groups</option>)}
                  </select>
                  <span className="text-muted text-sm">Group A, B, … balanced by average</span>
                </div>
                {groupsN >= 2 && <p className="text-muted text-sm" style={{ margin: '.4rem 0 0' }}>
                  Students are shared evenly across {groupsN} groups by their combined average, so each group has a similar mix of abilities and roughly the same size.</p>}
              </div>
              <div className="page-header-actions">
                <button type="button" className="btn btn-danger btn-sm" onClick={() => doExport('pdf')}><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</button>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => doExport('image')}><i aria-hidden="true" className="fas fa-file-image" /> Image</button>
                <button type="button" className="btn btn-success btn-sm" onClick={() => doExport('excel')}><i aria-hidden="true" className="fas fa-file-excel" /> Excel</button>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => doExport('word')}><i aria-hidden="true" className="fas fa-file-word" /> Word</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => doExport('csv')}>CSV</button>
                <button type="button" className="btn btn-link btn-sm" onClick={() => setShowExport(false)}>Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const SCREENS = { list: List, add: SubjectForm, edit: SubjectForm, bulk_add: BulkAdd,
  class_subjects: ClassSubjects, assign: Assign, edit_class_subject: EditClassSubject,
  scores: Scores, workflow: Workflow, bulk_entry: BulkEntry, broadsheet: Broadsheet,
  affective: Affective, comments: Comments, analytics: Analytics, institution: Institution,
  teacher: Teacher, subject: SubjectScorecard, explore: Explore, combine: Combine };

export default function SubjectsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || List;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
