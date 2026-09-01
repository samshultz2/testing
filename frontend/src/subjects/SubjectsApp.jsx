import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';
import { canWrite } from '../lib/perms';

// Whole numbers print without a trailing .0 (34, not 34.0); genuine decimals to
// two places (34.3 -> 34.30). Non-numeric / blank values pass through.
function fmtNum(v) {
  if (v == null || v === '') return v;
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

// Recently-accessed classes, shared across every results screen (localStorage),
// so a teacher resumes any class they've touched this term with one click
// instead of re-picking term + class each time.
const RECENT_KEY = 'results:recentClasses';
function readRecent() {
  try { const a = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); return Array.isArray(a) ? a : []; } catch (e) { return []; }
}
function pushRecent(termId, asgId, label) {
  if (!asgId || !label) return;
  try {
    const list = readRecent().filter((r) => String(r.id) !== String(asgId));
    list.unshift({ id: String(asgId), term: String(termId || ''), label });
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 6)));
  } catch (e) { /* storage unavailable */ }
}
// Record the current class and render a one-click "Recent" strip. `onPick`
// receives (termId, assignmentId).
function useRecordRecent(termId, asgId, label) {
  React.useEffect(() => { if (asgId && label) pushRecent(termId, asgId, label); }, [asgId, label]); // eslint-disable-line react-hooks/exhaustive-deps
}
function RecentClasses({ currentId, onPick }) {
  const shown = readRecent().filter((r) => String(r.id) !== String(currentId || ''));
  if (!shown.length) return null;
  return (
    <div className="recent-classes" style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap', alignItems: 'center', marginBottom: '.6rem' }}>
      <span className="text-muted text-sm"><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Recent:</span>
      {shown.map((r) => <button type="button" key={r.id} className="btn btn-sm btn-light" onClick={() => onPick(r.term, r.id)}>{r.label}</button>)}
    </div>
  );
}

// Shared term + class (assignment) filter bar used by the score-workflow pages.
function ClassFilter({ d, extraTerm = false }) {
  const nav = useNav();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, ...extra });
  const curLabel = (d.assignments.find((a) => String(a.id) === String(d.assignment_id)) || {}).display_name;
  useRecordRecent(d.term_id, d.assignment_id, curLabel);
  return (
    <>
      <RecentClasses currentId={d.assignment_id} onPick={(term, asg) => go({ term_id: term, assignment_id: asg })} />
    <div className="card mb-3"><div className="card-body"><form className="filter-form" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <div className="form-group"><label className="form-label">Term</label>
        <select className="form-control" value={d.term_id} onChange={(e) => go({ term_id: e.target.value, assignment_id: '' })}>
          {extraTerm && <option value="">Select Term</option>}
          {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
      <div className="form-group"><label className="form-label">Class</label>
        <select className="form-control" value={d.assignment_id} onChange={(e) => go({ assignment_id: e.target.value })}>
          <option value="">Select class…</option>{d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}</select></div>
    </form></div></div>
    </>
  );
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
          {canWrite(d) && <a href={d.urls.bulk_add} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-list" /> Bulk Add</a>}
          {canWrite(d) && <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}
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
                  {canWrite(d) && <div className="data-card-actions">
                    <a href={s.edit_url} className="btn btn-secondary btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>
                    <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(s.delete_url, s.name)}><i aria-hidden="true" className="fas fa-trash" /></button>
                  </div>}
                </div>))}
            </div>
          </div>
        </div>
      )) : (
        <div className="card"><div className="card-body"><Empty icon="fa-book" title={`No ${tab === 'junior' ? 'JSS' : 'SSS'} Subjects`}><p>Add a subject and mark it for {tab === 'junior' ? 'Junior' : 'Senior'} Secondary</p>{canWrite(d) && <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Subject</a>}</Empty></div></div>
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
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, ...extra });
  const del = async (url, name) => {
    if (!await confirm(`Remove ${name}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not remove.');
  };
  const toggleSel = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allSelected = d.class_subjects.length > 0 && d.class_subjects.every((cs) => sel.has(cs.id));
  const toggleAll = () => setSel(() => allSelected ? new Set() : new Set(d.class_subjects.map((cs) => cs.id)));
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
          {canWrite(d) && d.term_id && <button type="button" className="btn btn-info btn-sm" onClick={() => setShowCopy((s) => !s)}><i aria-hidden="true" className="fas fa-copy" /> Copy from term</button>}
          {canWrite(d) && <a href={d.urls.assign} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Assign</a>}
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
            <option value="">All Classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      </form></div></div>

      {canWrite(d) && d.class_subjects.length > 0 && (
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

      {d.class_subjects.length ? (
        <div className="card"><div className="card-header"><h3>Subjects ({d.class_subjects.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <div className="data-cards" style={{ padding: '1rem' }}>
              {d.class_subjects.map((cs) => (
                <div className={`data-card${sel.has(cs.id) ? ' selected' : ''}`} key={cs.id} style={sel.has(cs.id) ? { borderColor: 'var(--primary)' } : undefined}>
                  <div className="data-card-header">
                    <div className="data-card-title d-flex gap-2 align-center">
                      {canWrite(d) && <input type="checkbox" checked={sel.has(cs.id)} onChange={() => toggleSel(cs.id)} aria-label={`Select ${cs.subject}`} />}
                      {cs.subject}
                    </div>
                    <span className="badge badge-info">{cs.class_name}</span></div>
                  <div className="data-card-row"><span className="data-card-label">Teacher</span><span>{cs.teacher_name || '-'}</span></div>
                  {cs.arm && <div className="data-card-row"><span className="data-card-label">Arm</span><span>{cs.arm}</span></div>}
                  {canWrite(d) && <div className="data-card-actions">
                    <a href={cs.edit_url} className="btn btn-secondary btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>
                    <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(cs.delete_url, `${cs.subject} from ${cs.class_name}`)}><i aria-hidden="true" className="fas fa-times" /></button>
                  </div>}
                </div>))}
            </div>
          </div></div>
      ) : d.term_id ? (
        <div className="card"><div className="card-body"><Empty icon="fa-book-open" title="No Subjects Assigned"><p>Assign subjects to classes for this term</p>{canWrite(d) && <a href={d.urls.assign} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Assign Subjects</a>}</Empty></div></div>
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

// ---- Score entry -----------------------------------------------------------
// ---- Single-student entry: one student, every assessment of a subject -------
function StudentEntry({ d, notify }) {
  const roster = d.roster || [];
  const [q, setQ] = useState('');
  const [studentId, setStudentId] = useState('');
  const [rows, setRows] = useState(null);       // [{assessment_type_id,name,max_score,score}]
  const [vals, setVals] = useState({});          // at_id -> string
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const filtered = React.useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? roster.filter((s) => s.full_name.toLowerCase().includes(t)) : roster;
  }, [q, roster]);

  const load = React.useCallback(async (sid) => {
    if (!sid || !d.class_subject_id) { setRows(null); return; }
    setLoading(true);
    try {
      const p = new URLSearchParams({ term_id: d.term_id || '', assignment_id: d.assignment_id || '',
        class_subject_id: d.class_subject_id || '', student_id: sid });
      const res = await fetch(`${d.student_scores_api}?${p.toString()}`,
        { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      const body = await res.json();
      if (!res.ok) { notify('error', body.error || 'Could not load scores.'); setRows(null); }
      else { setRows(body.rows); const m = {}; body.rows.forEach((r) => { m[r.assessment_type_id] = r.score === '' ? '' : String(r.score); }); setVals(m); }
    } catch (e) { notify('error', 'Network error loading scores.'); setRows(null); }
    finally { setLoading(false); }
  }, [d.term_id, d.assignment_id, d.class_subject_id, d.student_scores_api, notify]);

  const pick = (sid) => { setStudentId(String(sid)); load(sid); };
  // Reloading when the subject changes keeps the grid in sync with the picker.
  React.useEffect(() => { if (studentId) load(studentId); }, [d.class_subject_id]); // eslint-disable-line

  const save = async () => {
    if (!studentId || !rows) return;
    setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id, class_subject_id: d.class_subject_id,
      student_id: studentId, 'assessment_type_id[]': rows.map((r) => r.assessment_type_id),
      'score[]': rows.map((r) => vals[r.assessment_type_id] ?? '') };
    const r = await submitJson(d.save_student_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); load(studentId); } else notify('error', r.error || 'Could not save.');
  };

  if (!d.assignment_id || !d.class_subject_id) {
    return <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select class and subject">
      <p>Pick a term, class and subject above, then choose a student to enter all their {`${d.selected_subject || 'subject'}`} scores at once.</p></Empty></div></div>;
  }
  const picked = roster.find((s) => String(s.id) === String(studentId));
  const invalid = (r) => { const raw = vals[r.assessment_type_id]; if (raw === '' || raw == null) return false; const n = Number(raw); return !Number.isFinite(n) || n < 0 || n > r.max_score; };

  return (
    <div className="row" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-start' }}>
      <div className="card" style={{ flex: '1 1 260px', minWidth: 240 }}>
        <div className="card-header"><h3>Students ({filtered.length})</h3></div>
        <div className="card-body">
          <input type="search" className="form-control mb-2" placeholder="Filter students by name…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter students" />
          <div className="stu-picker">
            {filtered.map((s) => (
              <button type="button" key={s.id} onClick={() => pick(s.id)}
                      className={'stu-pick' + (String(s.id) === String(studentId) ? ' active' : '')}>
                <span className="nm">{s.full_name}</span>
                <span className={'g ' + (s.gender === 'Male' ? 'm' : 'f')}>{s.gender || '—'}</span>
              </button>
            ))}
            {!filtered.length && <p className="text-muted text-sm">No students match.</p>}
          </div>
        </div>
      </div>

      <div className="card" style={{ flex: '2 1 340px', minWidth: 300 }}>
        <div className="card-header"><h3>{picked ? picked.full_name : 'Pick a student'}{d.selected_subject ? ` · ${d.selected_subject}` : ''}</h3></div>
        <div className="card-body">
          {loading ? <p className="text-muted"><i aria-hidden="true" className="fas fa-spinner fa-spin" /> Loading…</p>
           : !picked ? <Empty icon="fa-user" title="No student selected"><p>Choose a student on the left to enter their scores.</p></Empty>
           : rows && rows.length ? (
            <form onSubmit={(e) => { e.preventDefault(); save(); }}>
              <table className="data-table"><thead><tr><th>Assessment</th><th>Max</th><th>Score</th></tr></thead>
                <tbody>{rows.map((r) => (
                  <tr key={r.assessment_type_id}>
                    <td>{r.name}</td><td>{r.max_score}</td>
                    <td><input type="number" className={'form-control' + (invalid(r) ? ' is-invalid' : '')} style={{ width: 110, ...(invalid(r) ? { borderColor: '#e74a3b', background: '#fff5f5' } : {}) }}
                               min="0" max={r.max_score} step="0.5" value={vals[r.assessment_type_id] ?? ''}
                               onChange={(e) => setVals((m) => ({ ...m, [r.assessment_type_id]: e.target.value }))} /></td>
                  </tr>))}</tbody>
              </table>
              {canWrite(d) && <div className="page-header-actions mt-3">
                <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save all scores</button>
              </div>}
            </form>
          ) : <Empty icon="fa-list" title="No assessments"><p>No assessment types are configured.</p></Empty>}
        </div>
      </div>
    </div>
  );
}

function Scores({ d, notify }) {
  const nav = useNav();
  // Entry mode: 'assessment' = one assessment for the whole class (classic);
  // 'student' = one student, every assessment of a subject at once.
  const [mode, setMode] = useState('assessment');
  const [scores, setScores] = useState(() => { const m = {}; d.students_data.forEach((s) => { m[s.id] = s.score === '' ? '' : String(s.score); }); return m; });
  const [busy, setBusy] = useState(false);
  // Multi-select + bulk fill: tick several students and set them all to one score
  // at once (e.g. everyone who scored 5 in 1st CA).
  const [selected, setSelected] = useState({});
  const [fillValue, setFillValue] = useState('');
  // Baseline of saved scores, so we can tell what's unsaved (dirty tracking).
  const baseline = React.useRef({});
  React.useEffect(() => { const m = {}; d.students_data.forEach((s) => { m[s.id] = s.score === '' ? '' : String(s.score); }); setScores(m); setSelected({}); baseline.current = { ...m }; }, [d.students_data]);
  // Live completeness + validity for the summary bar and per-cell highlighting.
  const isInvalid = (raw) => { if (raw === '' || raw == null) return false; const n = Number(raw); return !Number.isFinite(n) || n < 0 || n > d.max_score; };
  const stats = React.useMemo(() => {
    let entered = 0, invalid = 0;
    d.students_data.forEach((s) => { const raw = scores[s.id]; if (raw === '' || raw == null) return; entered += 1; if (isInvalid(raw)) invalid += 1; });
    return { entered, invalid, missing: d.students_data.length - entered, total: d.students_data.length };
  }, [scores, d.students_data, d.max_score]);
  const dirty = React.useMemo(() => d.students_data.some((s) => String(scores[s.id] ?? '') !== String(baseline.current[s.id] ?? '')), [scores, d.students_data]);
  // Warn on full-page unload while there are unsaved score edits.
  React.useEffect(() => {
    if (!dirty) return undefined;
    const h = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [dirty]);
  // Paste a column of scores straight from Excel/Sheets: fills consecutive
  // students from the focused row down. A single value pastes normally.
  const onPaste = (startIndex) => (e) => {
    const text = (e.clipboardData && e.clipboardData.getData('text')) || '';
    if (!/[\n\t]/.test(text)) return;                    // single cell → default paste
    e.preventDefault();
    const values = text.replace(/\r/g, '').split('\n').map((line) => line.split('\t')[0].trim());
    if (values.length && values[values.length - 1] === '') values.pop();
    setScores((m) => { const n = { ...m }; values.forEach((v, k) => { const st = d.students_data[startIndex + k]; if (st) n[st.id] = v; }); return n; });
    notify('success', `Pasted ${Math.min(values.length, d.students_data.length - startIndex)} score(s).`);
  };
  const selectedIds = d.students_data.filter((s) => selected[s.id]).map((s) => s.id);
  const allSelected = d.students_data.length > 0 && d.students_data.every((s) => selected[s.id]);
  const toggleAll = (on) => { const m = {}; if (on) d.students_data.forEach((s) => { m[s.id] = true; }); setSelected(m); };
  const applyFill = () => { if (!selectedIds.length) return; setScores((m) => { const n = { ...m }; selectedIds.forEach((id) => { n[id] = fillValue; }); return n; }); };
  const set = (params) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, class_subject_id: d.class_subject_id, assessment_type_id: d.assessment_type_id, ...params });
  useRecordRecent(d.term_id, d.assignment_id, (d.assignments.find((a) => String(a.id) === String(d.assignment_id)) || {}).display_name);
  // Remember the last term+class so returning to score entry doesn't re-ask for
  // them; restore once on a fresh visit when nothing is selected yet.
  React.useEffect(() => {
    try {
      if (d.assignment_id) {
        localStorage.setItem('scores:last', JSON.stringify({ term_id: d.term_id, assignment_id: String(d.assignment_id) }));
        return;
      }
      const last = JSON.parse(localStorage.getItem('scores:last') || 'null');
      if (last && last.assignment_id && (d.assignments || []).some((a) => String(a.id) === String(last.assignment_id))) {
        set({ term_id: last.term_id || d.term_id, assignment_id: last.assignment_id });
      }
    } catch (e) { /* storage unavailable */ }
  }, [d.assignment_id]); // eslint-disable-line react-hooks/exhaustive-deps
  // Keyboard flow: Enter/Down -> next student's score, Up -> previous, so a whole
  // class is entered from the number pad without touching the mouse.
  const onScoreKey = (e) => {
    if (e.key !== 'Enter' && e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const inputs = Array.prototype.slice.call(e.currentTarget.closest('tbody').querySelectorAll('input.score-input'));
    const idx = inputs.indexOf(e.currentTarget);
    const next = e.key === 'ArrowUp' ? inputs[idx - 1] : inputs[idx + 1];
    if (next) { next.focus(); next.select(); }
  };
  // Subject order + the next one, so a teacher can save and roll straight on to
  // the next subject without re-picking term/class/assessment each time.
  const subjList = d.class_subjects || [];
  const curIdx = subjList.findIndex((cs) => String(cs.id) === String(d.class_subject_id));
  const nextSubject = (curIdx >= 0 && curIdx < subjList.length - 1) ? subjList[curIdx + 1] : null;
  const save = async (e, advance) => {
    if (e) e.preventDefault();
    setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id, class_subject_id: d.class_subject_id, assessment_type_id: d.assessment_type_id,
      'student_id[]': d.students_data.map((s) => s.id), 'score[]': d.students_data.map((s) => scores[s.id] ?? '') };
    const r = await submitJson(d.save_url, fields);
    setBusy(false);
    if (r.ok) {
      notify('success', r.message);
      if (advance && nextSubject) set({ class_subject_id: nextSubject.id }); else nav.refresh();
    } else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Score Entry</h1>
        {canWrite(d) && (
        <div className="score-actions">
          {d.urls.subject_sheet_import && <a href={d.urls.subject_sheet_import} className="btn btn-primary btn-sm" data-native><i aria-hidden="true" className="fas fa-file-import" /> Import subject sheet</a>}
          {d.urls.broadsheet_import && <a href={d.urls.broadsheet_import} className="btn btn-secondary btn-sm" data-native><i aria-hidden="true" className="fas fa-table" /> Import broadsheet</a>}
          {d.urls.scan && <a href={d.urls.scan} className="btn btn-secondary btn-sm" data-native><i aria-hidden="true" className="fas fa-camera" /> Scan photo</a>}
          {d.urls.blank_sheet && <a href={d.urls.blank_sheet} className="btn btn-secondary btn-sm" data-native target="_blank" rel="noopener"><i aria-hidden="true" className="fas fa-file-lines" /> Blank sheet</a>}
        </div>)}
      </div>
      <RecentClasses currentId={d.assignment_id} onPick={(term, asg) => set({ term_id: term, assignment_id: asg, class_subject_id: '', assessment_type_id: '' })} />
      <div className="score-tabs" role="tablist" aria-label="Score entry mode">
        <button type="button" role="tab" aria-selected={mode === 'assessment'}
                className={'score-tab' + (mode === 'assessment' ? ' active' : '')} onClick={() => setMode('assessment')}>
          <i aria-hidden="true" className="fas fa-users" />
          <span><strong>By assessment</strong><small>Whole class · one assessment</small></span>
        </button>
        <button type="button" role="tab" aria-selected={mode === 'student'}
                className={'score-tab' + (mode === 'student' ? ' active' : '')} onClick={() => setMode('student')}>
          <i aria-hidden="true" className="fas fa-user-graduate" />
          <span><strong>By student</strong><small>One student · all assessments</small></span>
        </button>
      </div>
      <div className="card mb-3"><div className="card-body"><form className="filter-form">
        <div className="form-group"><label className="form-label">Term</label>
          <select className="form-control" value={d.term_id} onChange={(e) => set({ term_id: e.target.value, assignment_id: '', class_subject_id: '', assessment_type_id: '' })}>
            <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Class</label>
          <select className="form-control" value={d.assignment_id} onChange={(e) => set({ assignment_id: e.target.value, class_subject_id: '', assessment_type_id: '' })}>
            <option value="">Select Class</option>{d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Subject</label>
          <select className="form-control" value={d.class_subject_id} onChange={(e) => set({ class_subject_id: e.target.value, assessment_type_id: d.assessment_type_id })}>
            <option value="">Select Subject</option>{d.class_subjects.map((cs) => <option key={cs.id} value={cs.id}>{cs.subject_name}</option>)}</select></div>
        {mode === 'assessment' && (
        <div className="form-group"><label className="form-label">Assessment</label>
          <select className="form-control" value={d.assessment_type_id} onChange={(e) => set({ assessment_type_id: e.target.value })}>
            <option value="">Select Assessment</option>{d.assessment_types.map((at) => <option key={at.id} value={at.id}>{at.name} ({at.max_score})</option>)}</select></div>
        )}
      </form></div></div>

      {mode === 'student' ? (
        <StudentEntry d={d} notify={notify} />
      ) : d.students_data.length ? (
        <div className="card">
          <div className="card-header"><h3>{d.selected_subject} - {d.selected_assessment}</h3><span className="badge badge-primary">Max: {d.max_score}</span></div>
          <div className="card-body"><form onSubmit={save}>
            <p className="text-muted text-sm mb-2"><i aria-hidden="true" className="fas fa-keyboard" /> Type a score and press <kbd>Enter</kbd> (or <kbd>↓</kbd>/<kbd>↑</kbd>) to jump to the next student. You can also <strong>paste a column of scores</strong> from Excel into any cell.</p>
            <div className="score-summary" role="status" aria-live="polite" style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap', alignItems: 'center', marginBottom: '.6rem' }}>
              <span className="badge badge-success"><i aria-hidden="true" className="fas fa-check" /> {stats.entered} entered</span>
              <span className={'badge ' + (stats.missing ? 'badge-warning' : 'badge-secondary')}>{stats.missing} missing</span>
              {stats.invalid > 0 && <span className="badge badge-danger"><i aria-hidden="true" className="fas fa-triangle-exclamation" /> {stats.invalid} out of range (0–{d.max_score})</span>}
              {dirty && <span className="badge badge-info"><i aria-hidden="true" className="fas fa-pen" /> Unsaved changes</span>}
            </div>
            <div className="bulk-fill" style={{ display: 'flex', alignItems: 'center', gap: '.6rem', flexWrap: 'wrap', padding: '.6rem .75rem', marginBottom: '.75rem', background: 'var(--surface-2, #f4f6f9)', border: '1px solid var(--border, #e5e7eb)', borderRadius: 10 }}>
              <span className="text-sm" style={{ fontWeight: 600 }}><i aria-hidden="true" className="fas fa-people-group" /> Tick students, then set them all at once:</span>
              <input type="number" className="form-control" style={{ width: 110 }} min="0" max={d.max_score} step="0.5"
                     value={fillValue} placeholder="e.g. 5" aria-label="Value to fill selected students"
                     onChange={(e) => setFillValue(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applyFill(); } }} />
              <button type="button" className="btn btn-secondary btn-sm" onClick={applyFill} disabled={!selectedIds.length}>
                <i aria-hidden="true" className="fas fa-fill-drip" /> Fill {selectedIds.length ? selectedIds.length + ' selected' : 'selected'}</button>
              {selectedIds.length > 0 && <button type="button" className="btn btn-link btn-sm" onClick={() => setSelected({})}>Clear selection</button>}
            </div>
            <div className="table-container"><table className="data-table">
              <thead><tr>
                <th style={{ width: 34 }}><input type="checkbox" checked={allSelected} onChange={(e) => toggleAll(e.target.checked)} aria-label="Select all students" /></th>
                <th>S/N</th><th>Student</th><th>Gender</th><th>Score (Max: {d.max_score})</th></tr></thead>
              <tbody>{d.students_data.map((s, i) => (
                <tr key={s.id} className={selected[s.id] ? 'row-selected' : ''}>
                  <td><input type="checkbox" checked={!!selected[s.id]} aria-label={'Select ' + s.full_name}
                             onChange={(e) => setSelected((m) => ({ ...m, [s.id]: e.target.checked }))} /></td>
                  <td>{i + 1}</td><td>{s.full_name}</td>
                  <td><span className={'badge ' + (s.gender === 'Male' ? 'badge-info' : 'badge-warning')}>{s.gender}</span></td>
                  <td><input type="number" className={'form-control score-input' + (isInvalid(scores[s.id]) ? ' is-invalid' : '')}
                             style={{ width: 100, ...(isInvalid(scores[s.id]) ? { borderColor: '#e74a3b', background: '#fff5f5' } : {}) }}
                             min="0" max={d.max_score} step="0.5" aria-invalid={isInvalid(scores[s.id]) ? 'true' : undefined}
                             value={scores[s.id] ?? ''} onKeyDown={onScoreKey} onPaste={onPaste(i)}
                             onChange={(e) => setScores((m) => ({ ...m, [s.id]: e.target.value }))} /></td></tr>))}</tbody>
            </table></div>
            {canWrite(d) && <div className="page-header-actions mt-3">
              <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Scores</button>
              {nextSubject && <button type="button" className="btn btn-success" disabled={busy} onClick={() => save(null, true)} title={`Save and continue to ${nextSubject.subject_name}`}><i aria-hidden="true" className="fas fa-forward" /> Save &amp; next subject</button>}
            </div>}
          </form></div>
        </div>
      ) : d.has_selection ? (
        <div className="card"><div className="card-body"><Empty icon="fa-users" title="No Students"><p>No students enrolled in this class</p></Empty></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select Options"><p>Select term, class, subject, and assessment type to enter scores</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Results workflow ------------------------------------------------------
function Workflow({ d, notify }) {
  const nav = useNav();
  const s = d.steps;
  const compute = async () => {
    const r = await submitJson(d.urls.compute, { term_id: d.term_id, assignment_id: d.assignment_id });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not compute.');
  };
  const Step = ({ done, total, icon, title, desc, link, label }) => {
    const ok = done && (total == null || done >= total);
    return (
      <div className="wf-step">
        <div className={'wf-ico ' + (ok ? 'wf-done' : 'wf-todo')}><i aria-hidden="true" className={'fas fa-' + (ok ? 'check' : icon)} /></div>
        <div className="wf-body"><h4>{title}</h4><p>{desc}</p></div>
        <a href={link} className="btn btn-secondary btn-sm">{label}</a>
      </div>
    );
  };
  return (
    <>
      <div className="page-header"><h1>Results Workflow</h1></div>
      <ClassFilter d={d} />
      {s ? (<>
        <div className="card"><div className="card-body" style={{ padding: 0 }}>
          <Step done={s.subjects} icon="book" title="Subjects configured" desc={`${s.subjects} subject(s) assigned to this class`} link={d.urls.class_subjects} label="Manage" />
          <Step done={s.students} icon="users" title="Students enrolled" desc={`${s.students} student(s) in this class`} link={d.urls.enrol} label="Enrol" />
          <Step done={s.scores_entered} total={s.scores_expected} icon="pen" title="Scores entered" desc={`${s.scores_entered} of ${s.scores_expected} score cells filled`} link={d.urls.bulk_entry} label="Enter" />
          <Step done={s.positions} total={s.students} icon="ranking-star" title="Results & positions computed" desc={`${s.positions} of ${s.students} student(s) ranked`} link={d.urls.broadsheet} label="Broadsheet" />
          <Step done={s.comments} total={s.students} icon="comment-dots" title="Comments entered" desc={`${s.comments} of ${s.students} have a form-teacher comment`} link={d.urls.comments} label="Comments" />
          <Step done={s.behaviour} total={s.students} icon="star-half-stroke" title="Behaviour rated" desc={`${s.behaviour} of ${s.students} have behaviour ratings`} link={d.urls.affective} label="Behaviour" />
        </div></div>
        <div className="card mt-3"><div className="card-body" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
          {canWrite(d) && <button type="button" className="btn btn-primary" onClick={compute}><i aria-hidden="true" className="fas fa-ranking-star" /> Finalize (compute results &amp; positions)</button>}
          <a href={d.urls.print_all} className="btn btn-success" data-native><i aria-hidden="true" className="fas fa-print" /> Print all report cards</a>
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: '.6rem' }}>
            <span className={'badge ' + (d.published ? 'badge-success' : 'badge-secondary')}><i aria-hidden="true" className={'fas fa-' + (d.published ? 'eye' : 'eye-slash')} /> {d.published ? 'Released to parents/checker' : 'Not released'}</span>
            <form method="POST" action={d.urls.publish} style={{ display: 'inline' }}>
              <input type="hidden" name="_csrf_token" value={csrfToken()} />
              <input type="hidden" name="next" value={d.self_url + '?term_id=' + d.term_id + '&assignment_id=' + d.assignment_id} />
              {!d.published && <label className="text-sm" style={{ marginRight: '.4rem' }}><input type="checkbox" name="notify" /> Notify parents</label>}
              <button type="submit" className={'btn btn-sm ' + (d.published ? 'btn-danger' : 'btn-success')}>{d.published ? 'Hide results' : 'Release results'}</button>
            </form>
          </span>
        </div></div>
        <p className="text-muted text-sm mt-2"><i aria-hidden="true" className="fas fa-info-circle" /> Releasing makes this term's results visible on the Parent Portal and the public result checker (applies to the whole term).</p>
      </>) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title=""><p>Select a term and class to see the results checklist.</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Bulk score entry ------------------------------------------------------
function BulkEntry({ d, notify }) {
  const nav = useNav();
  const [cells, setCells] = useState(d.scores);
  const [busy, setBusy] = useState(false);
  React.useEffect(() => setCells(d.scores), [d.scores]);
  const key = (sid, csid, atid) => `${sid}_${csid}_${atid}`;
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id };
    d.students.forEach((st) => d.class_subjects.forEach((cs) => d.assessment_types.forEach((at) => {
      fields['s_' + key(st.id, cs.id, at.id)] = cells[key(st.id, cs.id, at.id)] ?? '';
    })));
    const r = await submitJson(d.submit_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const nAt = d.assessment_types.length;
  return (
    <>
      <div className="page-header"><h1>Bulk Score Entry</h1>
        <div className="page-header-actions">{d.assignment_id && <a href={d.broadsheet_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-table" /> Broadsheet</a>}</div>
      </div>
      <ClassFilter d={d} />
      {d.has_grid ? (
        <form onSubmit={save}>
          <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table bulk-table">
              <thead>
                <tr><th className="bulk-name" rowSpan={2}>Student</th>
                  {d.class_subjects.map((cs) => <th className="subj" colSpan={nAt} key={cs.id}>{cs.subject_name}</th>)}</tr>
                <tr>{d.class_subjects.map((cs) => d.assessment_types.map((at, i) => (
                  <th key={cs.id + '_' + at.id} className={i === 0 ? 'subj' : ''} title={at.name}>{at.short_name}</th>)))}</tr>
              </thead>
              <tbody>{d.students.map((st) => (
                <tr key={st.id}><td className="bulk-name">{st.full_name}</td>
                  {d.class_subjects.map((cs) => d.assessment_types.map((at, i) => {
                    const k = key(st.id, cs.id, at.id);
                    return <td key={k} className={i === 0 ? 'subj' : ''}>
                      <input type="number" step="0.01" min="0" max={at.max_score} value={cells[k] ?? ''} onChange={(e) => setCells((m) => ({ ...m, [k]: e.target.value }))} /></td>;
                  }))}</tr>))}</tbody>
            </table>
          </div></div>
          <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
            {canWrite(d) && <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save all scores</button>}
            <span className="text-muted text-sm">Leave a cell blank to clear it. Positions update automatically.</span>
          </div>
        </form>
      ) : d.assignment_id ? (
        <div className="card"><div className="card-body"><Empty icon="fa-circle-info" title=""><p>This class has no subjects or no enrolled students yet.</p></Empty></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title=""><p>Select a term and class to enter scores.</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Broadsheet ------------------------------------------------------------
function ExportMenu({ urls, extraParams }) {
  const [pos, setPos] = useState(null);        // null = closed; {top,left} = open
  const btnRef = React.useRef(null);
  const MENU_W = 180;
  const withParams = (href) => {
    if (!href || !extraParams) return href;
    const qs = Object.entries(extraParams)
      .filter(([, v]) => v !== '' && v != null)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
    if (!qs) return href;
    return href + (href.includes('?') ? '&' : '?') + qs;
  };
  const items = [
    { href: withParams(urls.export), icon: 'fa-file-excel', label: 'Excel' },
    { href: withParams(urls.export_pdf), icon: 'fa-file-pdf', label: 'PDF' },
    { href: withParams(urls.export_word), icon: 'fa-file-word', label: 'Word' },
    { href: withParams(urls.export_image), icon: 'fa-file-image', label: 'HD Image' },
  ].filter((i) => i.href);
  const toggle = () => {
    if (pos) { setPos(null); return; }
    const r = btnRef.current.getBoundingClientRect();
    // Anchor under the button, right-aligned, clamped into the viewport.
    let left = r.right - MENU_W;
    left = Math.max(8, Math.min(left, window.innerWidth - MENU_W - 8));
    setPos({ top: Math.min(r.bottom + 4, window.innerHeight - 200), left });
  };
  return (
    <>
      <button ref={btnRef} type="button" className="btn btn-success btn-sm" onClick={toggle}>
        <i aria-hidden="true" className="fas fa-download" /> Export <i aria-hidden="true" className="fas fa-caret-down" />
      </button>
      {pos && (
        <>
          <div onClick={() => setPos(null)} style={{ position: 'fixed', inset: 0, zIndex: 1000 }} />
          <div className="card" style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 1001, width: MENU_W, padding: '.35rem', boxShadow: '0 6px 20px rgba(0,0,0,.18)' }}>
            {items.map((i) => (
              <a key={i.label} href={i.href} data-native download onClick={() => setPos(null)}
                 className="btn btn-light btn-sm" style={{ display: 'flex', gap: '.5rem', width: '100%', justifyContent: 'flex-start', marginBottom: 2 }}>
                <i aria-hidden="true" className={'fas ' + i.icon} /> {i.label}
              </a>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function BlankSheetButton({ url }) {
  if (!url) return null;
  const go = () => {
    const subj = window.prompt('Subject name for the sheet (optional — leave blank for a write-in space):', '');
    if (subj === null) return;                    // cancelled
    const sep = url.includes('?') ? '&' : '?';
    window.open(subj.trim() ? `${url}${sep}subject=${encodeURIComponent(subj.trim())}` : url, '_blank');
  };
  return (
    <button type="button" className="btn btn-secondary btn-sm" onClick={go} title="Printable blank score-entry sheet (A4)">
      <i aria-hidden="true" className="fas fa-file-lines" /> Blank sheet
    </button>
  );
}

function Broadsheet({ d, notify }) {
  const nav = useNav();
  const [filterField, setFilterField] = useState('average');
  const [minScore, setMinScore] = useState('');
  const compute = async () => {
    if (!await confirm("Compute and save term results and class positions for this class? This updates each student's report card.")) return;
    const r = await submitJson(d.urls.compute, { term_id: d.term_id, assignment_id: d.assignment_id });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not compute.');
  };
  // Client-side "who scored X and above" filter: by a subject, the class
  // Average (%) or the Total. Non-scored cells never match.
  const minVal = parseFloat(minScore);
  const hasFilter = !Number.isNaN(minVal);
  const valueFor = (r) => {
    if (filterField === 'average') return r.average;
    if (filterField === 'total') return r.total;
    return r.subjects[String(filterField)];
  };
  const rows = hasFilter ? d.rows.filter((r) => { const v = valueFor(r); return v != null && v >= minVal; }) : d.rows;
  const filterLabel = filterField === 'average' ? 'Average (%)' : filterField === 'total' ? 'Total'
    : (d.class_subjects.find((cs) => String(cs.id) === String(filterField)) || {}).name || 'Subject';
  // Frozen first columns (Pos + Student). bg must be opaque so scrolled cells
  // don't bleed through — use real theme tokens (the old var(--bg-primary) didn't exist).
  const sticky = (left) => ({ position: 'sticky', left, background: 'var(--bg-card)', whiteSpace: 'nowrap', zIndex: 1 });
  const headCell = { position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 };
  const headCorner = (left) => ({ ...headCell, left, zIndex: 3 });
  return (
    <>
      <div className="page-header"><h1>Broadsheet</h1></div>
      <div className="card mb-3"><div className="card-body"><form className="filter-form">
        <div className="form-group"><label className="form-label">Term</label>
          <select className="form-control" value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value, assignment_id: '' })}>
            <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Class</label>
          <select className="form-control" value={d.assignment_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: e.target.value })}>
            <option value="">Select Class</option>{d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}</select></div>
      </form></div></div>

      {d.rows.length ? (<>
        <div className="card mb-3"><div className="card-body"><form className="filter-form" onSubmit={(e) => e.preventDefault()} style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group"><label className="form-label">Show students scoring in</label>
            <select className="form-control" value={filterField} onChange={(e) => setFilterField(e.target.value)}>
              <option value="average">Average (%)</option>
              <option value="total">Total</option>
              {d.class_subjects.map((cs) => <option key={cs.id} value={cs.id}>{cs.name}</option>)}
            </select></div>
          <div className="form-group"><label className="form-label">at or above</label>
            <input type="number" className="form-control" style={{ maxWidth: 120 }} value={minScore} min="0" step="0.1"
              placeholder="e.g. 50" onChange={(e) => setMinScore(e.target.value)} /></div>
          {hasFilter && <div className="form-group"><button type="button" className="btn btn-secondary" onClick={() => setMinScore('')}><i aria-hidden="true" className="fas fa-times" /> Clear</button></div>}
          {hasFilter && <div className="form-group"><span className="text-muted text-sm">{rows.length} of {d.rows.length} student(s) with {filterLabel} ≥ {minVal}</span></div>}
        </form></div></div>

        <div className="card">
          <div className="card-header"><h3>{d.selected_assignment}</h3>
            <div className="page-header-actions">
              {canWrite(d) && <button type="button" className="btn btn-primary btn-sm" onClick={compute}><i aria-hidden="true" className="fas fa-ranking-star" /> Compute results &amp; positions</button>}
              {canWrite(d) && <a href={d.urls.bulk_entry} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-pen-to-square" /> Bulk Entry</a>}
              <a href={d.urls.affective} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-star-half-stroke" /> Behaviour</a>
              <a href={d.urls.comments} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-comment-dots" /> Comments</a>
              {d.urls.analytics && <a href={d.urls.analytics} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-chart-column" /> Analytics</a>}
              {d.urls.explore && <a href={d.urls.explore} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-filter" /> Explore / Compare</a>}
              <ExportMenu urls={d.urls} extraParams={hasFilter ? { min_score: minVal, filter_field: filterField } : null} />
              <BlankSheetButton url={d.urls.blank_sheet} />
              <span className="badge badge-info">{hasFilter ? `${rows.length} of ${d.rows.length}` : d.rows.length} Students</span>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0, overflow: 'auto', maxHeight: '70vh' }}>
            <table className="data-table" style={{ minWidth: '100%' }}>
              <thead><tr>
                <th style={{ ...headCorner(0) }}>Pos</th>
                <th style={{ ...headCorner(40) }}>Student</th>
                {d.class_subjects.map((cs) => <th key={cs.id} style={{ ...headCell, textAlign: 'center', fontSize: 'var(--text-xs)' }}>{cs.short}</th>)}
                <th style={{ ...headCell, textAlign: 'center' }}>Total</th><th style={{ ...headCell, textAlign: 'center' }}>Avg</th><th style={{ ...headCell, textAlign: 'center' }}>P/F</th>
              </tr></thead>
              <tbody>{rows.length ? rows.map((r, i) => (
                <tr key={i}>
                  <td style={{ ...sticky(0), fontWeight: 'bold' }}>{r.position}</td>
                  <td style={sticky(40)}>{r.student}</td>
                  {d.class_subjects.map((cs) => <td key={cs.id} style={{ textAlign: 'center' }}>{r.subjects[String(cs.id)] != null ? fmtNum(r.subjects[String(cs.id)]) : '-'}</td>)}
                  <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{fmtNum(r.total)}</td>
                  <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{fmtNum(r.average)}</td>
                  <td style={{ textAlign: 'center' }}><span className="badge badge-success">{r.passed}</span> <span className="badge badge-danger">{r.failed}</span></td>
                </tr>)) : (
                <tr><td colSpan={d.class_subjects.length + 5} style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)' }}>No students with {filterLabel} ≥ {minVal}.</td></tr>
              )}</tbody>
            </table>
          </div>
        </div>
        <div className="card mt-3"><div className="card-header"><h3>Legend</h3></div>
          <div className="card-body"><div className="filter-form">
            {d.class_subjects.map((cs) => <div key={cs.id} style={{ marginRight: '1rem', marginBottom: '0.5rem' }}><strong>{cs.short}</strong> = {cs.name}</div>)}
          </div></div></div>
      </>) : d.has_selection ? (
        <div className="card"><div className="card-body"><Empty icon="fa-table" title="No Data"><p>No scores entered for this class yet</p>{canWrite(d) && <a href={d.urls.scores} className="btn btn-primary"><i aria-hidden="true" className="fas fa-edit" /> Enter Scores</a>}</Empty></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select Options"><p>Select term and class to view broadsheet</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Behavioural ratings ---------------------------------------------------
function Affective({ d, notify }) {
  const nav = useNav();
  const [vals, setVals] = useState(() => { const m = {}; d.students.forEach((s) => d.traits.forEach((t) => { m[`${s.id}_${t.key}`] = s.ratings[t.key] != null ? String(s.ratings[t.key]) : ''; })); return m; });
  const [busy, setBusy] = useState(false);
  React.useEffect(() => { const m = {}; d.students.forEach((s) => d.traits.forEach((t) => { m[`${s.id}_${t.key}`] = s.ratings[t.key] != null ? String(s.ratings[t.key]) : ''; })); setVals(m); }, [d.students]);
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id };
    d.students.forEach((s) => d.traits.forEach((t) => { fields[`r_${s.id}_${t.key}`] = vals[`${s.id}_${t.key}`] ?? ''; }));
    const r = await submitJson(d.submit_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Behavioural Ratings</h1>
        <div className="page-header-actions">{d.assignment_id && <a href={d.broadsheet_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-table" /> Broadsheet</a>}</div>
      </div>
      <ClassFilter d={d} />
      {d.has_students ? (
        <form onSubmit={save}>
          <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table">
              <thead><tr><th>Student</th>{d.traits.map((t) => <th key={t.key} style={{ fontSize: 'var(--text-xs)', writingMode: 'vertical-rl', transform: 'rotate(180deg)', whiteSpace: 'nowrap' }}>{t.label}</th>)}</tr></thead>
              <tbody>{d.students.map((s) => (
                <tr key={s.id}><td style={{ whiteSpace: 'nowrap' }}>{s.full_name}</td>
                  {d.traits.map((t) => (
                    <td key={t.key} style={{ textAlign: 'center' }}>
                      <select className="form-control" style={{ padding: '.2rem', minWidth: 48 }} value={vals[`${s.id}_${t.key}`] ?? ''} onChange={(e) => setVals((m) => ({ ...m, [`${s.id}_${t.key}`]: e.target.value }))}>
                        <option value="">–</option>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n}</option>)}</select></td>))}
                </tr>))}</tbody>
            </table>
          </div></div>
          <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
            {canWrite(d) && <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save ratings</button>}
            <span className="text-muted text-sm">Scale: 5 Excellent · 4 Very Good · 3 Good · 2 Fair · 1 Poor</span>
          </div>
        </form>
      ) : d.selected ? (
        <div className="card"><div className="card-body"><Empty icon="fa-users" title=""><p>No students enrolled in this class for the term.</p></Empty></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title=""><p>Select a term and class to rate behaviour.</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Report comments -------------------------------------------------------
function Comments({ d, notify }) {
  const nav = useNav();
  const [vals, setVals] = useState(() => { const m = {}; d.students.forEach((s) => { m['t_' + s.id] = s.teacher_comment; m['p_' + s.id] = s.principal_comment; }); return m; });
  const [busy, setBusy] = useState(false);
  React.useEffect(() => { const m = {}; d.students.forEach((s) => { m['t_' + s.id] = s.teacher_comment; m['p_' + s.id] = s.principal_comment; }); setVals(m); }, [d.students]);
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id };
    d.students.forEach((s) => { fields['t_' + s.id] = vals['t_' + s.id] ?? ''; fields['p_' + s.id] = vals['p_' + s.id] ?? ''; });
    const r = await submitJson(d.submit_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Report Comments</h1>
        <div className="page-header-actions">{d.assignment_id && <a href={d.broadsheet_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-table" /> Broadsheet</a>}</div>
      </div>
      <ClassFilter d={d} />
      {d.has_students ? (
        <form onSubmit={save}>
          <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table">
              <thead><tr><th style={{ minWidth: 160 }}>Student</th><th>Form Teacher's Comment</th><th>Principal's Comment</th></tr></thead>
              <tbody>{d.students.map((s) => (
                <tr key={s.id}><td style={{ whiteSpace: 'nowrap' }}>{s.full_name}</td>
                  <td><textarea className="form-control" rows="2" style={{ minWidth: 240 }} value={vals['t_' + s.id] ?? ''} onChange={(e) => setVals((m) => ({ ...m, ['t_' + s.id]: e.target.value }))} /></td>
                  <td><textarea className="form-control" rows="2" style={{ minWidth: 240 }} value={vals['p_' + s.id] ?? ''} onChange={(e) => setVals((m) => ({ ...m, ['p_' + s.id]: e.target.value }))} /></td>
                </tr>))}</tbody>
            </table>
          </div></div>
          {canWrite(d) && <div style={{ marginTop: '1rem' }}><button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save comments</button></div>}
        </form>
      ) : d.selected ? (
        <div className="card"><div className="card-body"><Empty icon="fa-users" title=""><p>No students enrolled in this class for the term.</p></Empty></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title=""><p>Select a term and class to enter comments.</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Academic analytics ----------------------------------------------------
function Bar({ label, value, max, pct, tone }) {
  const w = max > 0 ? Math.round((value / max) * 100) : 0;
  const colour = tone || 'var(--primary, #4e73df)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', margin: '.2rem 0' }}>
      <span style={{ width: 120, flexShrink: 0, fontSize: 'var(--text-sm)' }} className="text-truncate" title={label}>{label}</span>
      <div style={{ flex: 1, background: 'var(--gray-100, #eef0f4)', borderRadius: 6, height: 18, overflow: 'hidden' }}>
        <div style={{ width: `${w}%`, background: colour, height: '100%' }} /></div>
      <span style={{ width: 64, textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600 }}>{pct != null ? `${fmtNum(value)}%` : fmtNum(value)}</span>
    </div>
  );
}

function AStat({ value, label, tone }) {
  return <div className="card"><div className="card-body">
    <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: tone }}>{value}</div>
    <div className="text-muted text-sm">{label}</div></div></div>;
}

// Dependency-free SVG donut (pass vs fail, etc.)
function Donut({ segments, size = 150, center }) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  const r = size / 2 - 12; const cx = size / 2; const cy = size / 2; const circ = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--gray-100,#eef0f4)" strokeWidth="18" />
        {segments.map((s, i) => {
          const frac = s.value / total; const dash = frac * circ;
          const el = <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth="18"
            strokeDasharray={`${dash} ${circ - dash}`} strokeDashoffset={-offset}
            transform={`rotate(-90 ${cx} ${cy})`} />;
          offset += dash; return el;
        })}
        {center != null && <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central"
          style={{ fontSize: 22, fontWeight: 700, fill: 'var(--text-primary,#1f2d3d)' }}>{center}</text>}
      </svg>
      <div>{segments.map((s, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '.4rem', margin: '.2rem 0', fontSize: 'var(--text-sm)' }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: s.color, display: 'inline-block' }} />
          {s.label} <strong>{s.value}</strong></div>))}</div>
    </div>
  );
}

// Dependency-free SVG column chart (score-band histogram, etc.)
function ColumnChart({ bars, height = 170, color = 'var(--primary,#0D6A4E)' }) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  const bw = 100 / bars.length;
  return (
    <svg width="100%" height={height} viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" role="img" style={{ overflow: 'visible' }}>
      {bars.map((b, i) => {
        const h = (b.value / max) * (height - 34); const x = i * bw + bw * 0.15; const w = bw * 0.7;
        const y = height - 20 - h;
        return (
          <g key={i}>
            <rect x={x} y={y} width={w} height={Math.max(h, 0.5)} fill={b.color || color} rx="1" />
            <text x={x + w / 2} y={y - 3} textAnchor="middle" style={{ fontSize: 6, fontWeight: 700, fill: 'var(--text-primary,#333)' }}>{b.value || ''}</text>
            <text x={x + w / 2} y={height - 8} textAnchor="middle" style={{ fontSize: 5, fill: 'var(--text-muted,#888)' }}>{b.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function SubjectDifficulty({ subjects }) {
  const [open, setOpen] = useState(null);
  return (
    <div className="card"><div className="card-header"><h3>Subject difficulty (hardest first)</h3>
      <span className="text-muted text-sm">tap a subject for its breakdown</span></div>
      <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="data-table"><thead><tr><th /><th>Subject</th><th className="text-right">Avg</th><th className="text-right">Pass %</th></tr></thead>
          <tbody>{subjects.map((sub) => {
            const isOpen = open === sub.id;
            return (
              <React.Fragment key={sub.id}>
                <tr onClick={() => sub.assessed && setOpen(isOpen ? null : sub.id)} style={{ cursor: sub.assessed ? 'pointer' : 'default' }}>
                  <td style={{ width: 24, color: 'var(--text-muted)' }}>{sub.assessed ? <i aria-hidden="true" className={'fas fa-chevron-' + (isOpen ? 'down' : 'right')} /> : ''}</td>
                  <td>{sub.name}</td>
                  <td className="text-right"><strong>{sub.assessed ? fmtNum(sub.average) : '—'}</strong></td>
                  <td className="text-right"><span className={'badge ' + (sub.pass_rate >= 50 ? 'badge-success' : 'badge-danger')}>{sub.assessed ? fmtNum(sub.pass_rate) + '%' : '—'}</span></td>
                </tr>
                {isOpen && (
                  <tr><td colSpan={4} style={{ background: 'var(--surface-2,#f8f9fb)' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: '1rem', padding: '.5rem' }}>
                      <div>
                        <div className="text-muted text-sm mb-1">Grade spread · {sub.assessed} assessed · high {fmtNum(sub.highest)} · low {fmtNum(sub.lowest)}</div>
                        <ColumnChart height={130} bars={(sub.grades || []).map((g) => ({ label: g.grade, value: g.count }))} />
                      </div>
                      <div>
                        <div className="text-muted text-sm mb-1">Score bands</div>
                        <ColumnChart height={130} bars={(sub.bands || []).map((b) => ({ label: b.band, value: b.count, color: b.band === '0–39' ? '#e74a3b' : (parseInt(b.band) >= 70 ? 'var(--success,#1c8c53)' : 'var(--primary,#0D6A4E)') }))} />
                      </div>
                    </div>
                  </td></tr>
                )}
              </React.Fragment>
            );
          })}</tbody></table>
      </div></div>
  );
}

function Analytics({ d, notify }) {
  const nav = useNav();
  const a = d.analytics;
  const s = (a && a.summary) || {};
  const refresh = async () => { nav.go(d.refresh_url); notify('success', 'Recomputing…'); };
  const gradeMax = a ? Math.max(1, ...a.grade_distribution.map((g) => g.count)) : 1;
  const cardLink = (id) => `${d.report_card_base}${id}?term_id=${d.term_id}`;
  return (
    <>
      <div className="page-header"><h1>Academic Analytics</h1>
        <div className="page-header-actions">
          {d.urls.institution && <a href={d.urls.institution} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-building-columns" /> Institution view</a>}
          {d.has_selection && <button type="button" className="btn btn-secondary btn-sm" onClick={refresh}><i aria-hidden="true" className="fas fa-rotate" /> Refresh</button>}
          {d.has_selection && a && s.assessed && d.urls.report_pdf && <a href={d.urls.report_pdf} className="btn btn-success btn-sm" data-native download><i aria-hidden="true" className="fas fa-file-pdf" /> Report PDF</a>}
          {d.assignment_id && <a href={d.urls.broadsheet} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-table" /> Broadsheet</a>}
          {d.assignment_id && <a href={d.urls.scores} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-pen" /> Enter scores</a>}
        </div>
      </div>
      <ClassFilter d={d} />
      {!d.has_selection ? (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-column" title="Select a class"><p>Pick a term and class to see grade distribution, subject difficulty and students needing attention.</p></Empty></div></div>
      ) : !a || !s.assessed ? (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-column" title="No scores yet"><p>Enter some scores for this class to unlock analytics.</p></Empty></div></div>
      ) : (<>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
          <AStat value={fmtNum(s.class_average)} label="Class average" />
          <AStat value={`${fmtNum(s.pass_rate)}%`} label="Pass rate" tone={s.pass_rate >= 50 ? 'var(--success)' : '#e74a3b'} />
          <AStat value={fmtNum(s.highest)} label="Highest average" tone="var(--success)" />
          <AStat value={fmtNum(s.lowest)} label="Lowest average" tone="#e74a3b" />
          <AStat value={`${fmtNum(s.completion)}%`} label="Entry completion" />
          {s.trend != null && <AStat value={`${s.trend > 0 ? '+' : ''}${fmtNum(s.trend)}`} label="vs last term" tone={s.trend >= 0 ? 'var(--success)' : '#e74a3b'} />}
        </div>
        <div className="text-muted text-sm mb-2">
          {s.assessed} of {s.students} students assessed · pass mark {s.pass_mark}
          {s.top_student && <> · top: <strong>{s.top_student}</strong></>}
          {a.cached === false && <> · <span className="badge badge-secondary">fresh</span></>}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <div className="card"><div className="card-header"><h3>Pass vs fail</h3></div>
            <div className="card-body" style={{ display: 'flex', justifyContent: 'center' }}>
              <Donut center={`${s.pass_rate}%`} segments={[
                { label: 'Passed', value: Math.round((s.pass_rate / 100) * s.assessed), color: 'var(--success,#1c8c53)' },
                { label: 'Below pass', value: s.assessed - Math.round((s.pass_rate / 100) * s.assessed), color: '#e74a3b' },
              ]} />
            </div></div>
          {a.score_bands && a.score_bands.length > 0 && (
            <div className="card"><div className="card-header"><h3>Spread of averages</h3></div>
              <div className="card-body">
                <ColumnChart bars={a.score_bands.map((b) => ({ label: b.band, value: b.count, color: b.band === '0–39' ? '#e74a3b' : (parseInt(b.band) >= 70 ? 'var(--success,#1c8c53)' : 'var(--primary,#0D6A4E)') }))} />
              </div></div>
          )}
          {a.gender && a.gender.length > 0 && (
            <div className="card"><div className="card-header"><h3>By gender</h3></div>
              <div className="card-body">
                {a.gender.map((g) => (
                  <div key={g.group} style={{ marginBottom: '.6rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                      <strong>{g.group}</strong><span className="text-muted">{g.count} · avg {fmtNum(g.average)}</span></div>
                    <Bar label={`${fmtNum(g.pass_rate)}% pass`} value={g.pass_rate} max={100} pct tone={g.pass_rate >= 50 ? 'var(--success)' : '#e74a3b'} />
                  </div>))}
              </div></div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: '1rem' }}>
          <div className="card"><div className="card-header"><h3>Grade distribution</h3></div>
            <div className="card-body">
              {a.grade_distribution.map((g) => <Bar key={g.grade} label={`Grade ${g.grade}`} value={g.count} max={gradeMax} />)}
            </div></div>

          <SubjectDifficulty subjects={a.subjects} />

          <div className="card"><div className="card-header"><h3>Top students</h3></div>
            <div className="card-body">
              <ol style={{ margin: 0, paddingLeft: '1.2rem' }}>
                {a.top_students.map((t, i) => <li key={i} style={{ margin: '.15rem 0' }}>{t.name} <span className="text-muted">— {fmtNum(t.average)}</span></li>)}
              </ol></div></div>

          <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Needs attention ({a.intervention.length})</h3></div>
            <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
              {a.intervention.length ? (
                <table className="data-table"><thead><tr><th>Student</th><th className="text-right">Avg</th><th className="text-right">Failing</th><th /></tr></thead>
                  <tbody>{a.intervention.map((st) => (
                    <tr key={st.id}><td>{st.name}</td>
                      <td className="text-right" style={{ color: '#e74a3b', fontWeight: 600 }}>{fmtNum(st.average)}</td>
                      <td className="text-right">{st.failed}</td>
                      <td className="text-right"><a href={cardLink(st.id)} className="btn btn-sm btn-light" data-native><i aria-hidden="true" className="fas fa-id-card" /></a></td></tr>
                  ))}</tbody></table>
              ) : <div style={{ padding: '1rem' }} className="text-muted">No students below the pass mark. 🎉</div>}
            </div></div>
        </div>

        {a.trends && a.trends.term_names.length > 1 && (
          <div className="card mt-3"><div className="card-header"><h3>Performance trend across terms</h3></div>
            <div className="card-body">
              <div style={{ marginBottom: '.8rem' }}>
                <div className="text-muted text-sm mb-1">Class average</div>
                {a.trends.term_names.map((tn, i) => (
                  <Bar key={tn} label={tn} value={a.trends.averages[i] == null ? 0 : a.trends.averages[i]} max={100} />
                ))}
              </div>
              {a.trends.subjects.length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                  <table className="data-table"><thead><tr><th>Subject</th>{a.trends.term_names.map((tn) => <th key={tn} className="text-right">{tn}</th>)}</tr></thead>
                    <tbody>{a.trends.subjects.map((sub) => (
                      <tr key={sub.name}><td>{sub.name}</td>
                        {sub.values.map((v, i) => {
                          const prev = i > 0 ? sub.values[i - 1] : null;
                          const up = v != null && prev != null && v > prev;
                          const down = v != null && prev != null && v < prev;
                          return <td key={i} className="text-right">{v == null ? '—' : fmtNum(v)}{up && <span style={{ color: 'var(--success)' }}> ▲</span>}{down && <span style={{ color: '#e74a3b' }}> ▼</span>}</td>;
                        })}</tr>
                    ))}</tbody></table>
                </div>
              )}
            </div></div>
        )}
      </>)}
    </>
  );
}

// ---- Institution-wide executive analytics ---------------------------------
const FLAG_STYLE = {
  strong: { bg: 'var(--success-light,#e6f4ec)', fg: 'var(--success,#1c8c53)' },
  good: { bg: 'var(--gray-100,#eef0f4)', fg: 'var(--text-primary,#1f2d3d)' },
  watch: { bg: '#fdf3d7', fg: '#9a7b0a' },
  review: { bg: '#fbe6e3', fg: '#b43a2e' },
  compliance: { bg: '#fbe6e3', fg: '#b43a2e' },
  insufficient: { bg: 'var(--gray-100,#eef0f4)', fg: 'var(--text-muted,#889)' },
};
const TONE_STYLE = {
  positive: { border: 'var(--success,#1c8c53)', icon: 'fa-circle-check' },
  negative: { border: '#b43a2e', icon: 'fa-triangle-exclamation' },
  watch: { border: '#c9a227', icon: 'fa-eye' },
  insight: { border: 'var(--primary,#0D6A4E)', icon: 'fa-lightbulb' },
};

function avgColour(v, pass) {
  if (v >= 75) return 'var(--success,#1c8c53)';
  if (v >= (pass || 50)) return 'var(--primary,#0D6A4E)';
  return '#e74a3b';
}

function LeagueTable({ rows, cols, onRow, rank }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table"><thead><tr>
        {rank && <th style={{ width: 34 }}>#</th>}
        {cols.map((c) => <th key={c.key} className={c.right ? 'text-right' : ''}>{c.label}</th>)}
      </tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={r._k || i} onClick={onRow ? () => onRow(r) : undefined}
            style={onRow ? { cursor: 'pointer' } : undefined}>
            {rank && <td style={{ fontWeight: 700, color: 'var(--text-muted)' }}>{i + 1}</td>}
            {cols.map((c) => <td key={c.key} className={c.right ? 'text-right' : ''}>{c.render ? c.render(r) : r[c.key]}</td>)}
          </tr>
        ))}</tbody></table>
    </div>
  );
}

function ScopePicker({ d }) {
  const nav = useNav();
  const a = d.analytics || {};
  const sel = a.selectors || { sections: [], classes: [], arms: [] };
  const goScope = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, scope: d.scope, scope_id: d.scope_id, ...extra });
  return (
    <div className="card mb-3"><div className="card-body">
      <form className="filter-form" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="form-group"><label className="form-label">Term</label>
          <select className="form-control" value={d.term_id} onChange={(e) => goScope({ term_id: e.target.value, scope: 'school', scope_id: '' })}>
            {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Level</label>
          <select className="form-control" value={d.scope} onChange={(e) => goScope({ scope: e.target.value, scope_id: '' })}>
            <option value="school">Whole School</option>
            <option value="section">Section</option>
            <option value="class">Class</option>
            <option value="arm">Class arm</option>
          </select></div>
        {d.scope === 'section' && (
          <div className="form-group"><label className="form-label">Section</label>
            <select className="form-control" value={d.scope_id} onChange={(e) => goScope({ scope_id: e.target.value })}>
              <option value="">Select section…</option>
              {sel.sections.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></div>
        )}
        {d.scope === 'class' && (
          <div className="form-group"><label className="form-label">Class</label>
            <select className="form-control" value={d.scope_id} onChange={(e) => goScope({ scope_id: e.target.value })}>
              <option value="">Select class…</option>
              {sel.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        )}
        {d.scope === 'arm' && (
          <div className="form-group"><label className="form-label">Class arm</label>
            <select className="form-control" value={d.scope_id} onChange={(e) => goScope({ scope_id: e.target.value })}>
              <option value="">Select class arm…</option>
              {sel.arms.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></div>
        )}
      </form>
    </div></div>
  );
}

function Institution({ d, notify }) {
  const nav = useNav();
  const a = d.analytics;
  const s = (a && a.summary) || {};
  const pm = s.pass_mark || 50;
  const [auto, setAuto] = useState(!!d.auto_board_pack);
  const [emailing, setEmailing] = useState(false);
  const emailOwners = async () => {
    if (emailing) return;
    setEmailing(true);
    const r = await submitJson(d.urls.email_report, { term_id: d.term_id, scope: d.scope, scope_id: d.scope_id });
    setEmailing(false);
    if (r.ok) notify('success', r.message); else notify('error', r.error || 'Could not send.');
  };
  const toggleAuto = async (on) => {
    setAuto(on);
    const r = await submitJson(d.urls.toggle_auto, { enabled: on ? '1' : '0' });
    if (r.ok) notify('success', r.message); else { setAuto(!on); notify('error', r.error || 'Could not change.'); }
  };
  const cardLink = (id) => `${d.report_card_base}${id}?term_id=${d.term_id}`;
  const drill = (u) => navParams(nav.go, d.self_url, { term_id: d.term_id, scope: u.scope, scope_id: u.scope_id });
  const refresh = () => { navParams(nav.go, d.self_url, { term_id: d.term_id, scope: d.scope, scope_id: d.scope_id, refresh: 1 }); notify('success', 'Recomputing…'); };
  const needsPick = d.scope !== 'school' && !d.scope_id;
  const gradeMax = a && a.grade_distribution.length ? Math.max(1, ...a.grade_distribution.map((g) => g.count)) : 1;
  return (
    <>
      <div className="page-header"><h1>Institution Analytics</h1>
        <div className="page-header-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={refresh}><i aria-hidden="true" className="fas fa-rotate" /> Refresh</button>
          {a && s.assessed && d.is_admin && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={emailOwners} disabled={emailing} title="Email this board pack to the school owners/admins">
              <i aria-hidden="true" className="fas fa-envelope" /> {emailing ? 'Sending…' : 'Email to owners'}</button>
          )}
          {a && s.assessed ? (() => {
            const base = d.urls.report_base; const sep = base.includes('?') ? '&' : '?';
            const exp = (fmt) => `${base}${sep}format=${fmt}`;
            return <ExportMenu urls={{ export: exp('excel'), export_pdf: exp('pdf'), export_image: exp('image') }} />;
          })() : null}
        </div>
      </div>
      <ScopePicker d={d} />
      {d.is_admin && (
        <div className="text-sm" style={{ display: 'flex', alignItems: 'center', gap: '.5rem', margin: '-.4rem 0 .8rem' }}>
          <label className="form-check" style={{ display: 'inline-flex', alignItems: 'center', gap: '.4rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={auto} onChange={(e) => toggleAuto(e.target.checked)} />
            <span><i aria-hidden="true" className="fas fa-clock" /> Auto-email the board pack to owners each term</span>
          </label>
          <span className="text-muted">(fires once when a term's results are published)</span>
        </div>
      )}

      {needsPick ? (
        <div className="card"><div className="card-body"><Empty icon="fa-layer-group" title={`Select a ${d.scope}`}><p>Choose a {d.scope} above to roll up its results.</p></Empty></div></div>
      ) : !a || !s.assessed ? (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-column" title="No scores yet"><p>No entered scores for <strong>{a ? a.scope_label : 'this scope'}</strong> yet. Enter some scores to unlock analytics.</p></Empty></div></div>
      ) : (<>
        <div className="text-muted text-sm mb-2" style={{ marginTop: '-.4rem' }}>
          Showing <strong>{a.scope_label}</strong> · {s.assessed} of {s.students} students assessed across {s.units} unit(s) · pass mark {pm}
          {a.cached === false && <> · <span className="badge badge-secondary">fresh</span></>}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
          <AStat value={fmtNum(s.class_average)} label="Average score" tone={avgColour(s.class_average, pm)} />
          <AStat value={`${fmtNum(s.pass_rate)}%`} label="Pass rate" tone={s.pass_rate >= 50 ? 'var(--success)' : '#e74a3b'} />
          <AStat value={`${fmtNum(s.distinction_rate)}%`} label="Distinctions" tone="var(--success)" />
          <AStat value={fmtNum(s.highest)} label="Highest" tone="var(--success)" />
          <AStat value={fmtNum(s.lowest)} label="Lowest" tone="#e74a3b" />
          <AStat value={`${fmtNum(s.completion)}%`} label="Entry completion" tone={s.completion >= 85 ? undefined : '#c9a227'} />
        </div>

        {a.recommendations && a.recommendations.length > 0 && (
          <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-briefcase" /> Insights &amp; recommendations</h3>
            <span className="text-muted text-sm">what to do next</span></div>
            <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: '.6rem' }}>
              {a.recommendations.map((r, i) => {
                const t = TONE_STYLE[r.tone] || TONE_STYLE.insight;
                return (
                  <div key={i} style={{ borderLeft: `4px solid ${t.border}`, background: 'var(--bg-secondary,#f8f9fb)', borderRadius: 6, padding: '.6rem .8rem' }}>
                    <div style={{ fontWeight: 700, marginBottom: '.2rem' }}><i aria-hidden="true" className={`fas ${t.icon}`} style={{ color: t.border, marginRight: '.4rem' }} />{r.title}</div>
                    <div className="text-sm" style={{ color: 'var(--text-secondary,#4a5568)' }}>{r.text}</div>
                  </div>
                );
              })}
            </div></div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <div className="card"><div className="card-header"><h3>Pass vs below pass</h3></div>
            <div className="card-body" style={{ display: 'flex', justifyContent: 'center' }}>
              <Donut center={`${fmtNum(s.pass_rate)}%`} segments={[
                { label: 'Passed', value: Math.round((s.pass_rate / 100) * s.assessed), color: 'var(--success,#1c8c53)' },
                { label: 'Below pass', value: s.assessed - Math.round((s.pass_rate / 100) * s.assessed), color: '#e74a3b' },
              ]} /></div></div>
          {a.score_bands && a.score_bands.length > 0 && (
            <div className="card"><div className="card-header"><h3>Spread of student averages</h3></div>
              <div className="card-body"><ColumnChart bars={a.score_bands.map((b) => ({ label: b.band, value: b.count, color: b.band === '0–39' ? '#e74a3b' : (parseInt(b.band, 10) >= 70 ? 'var(--success,#1c8c53)' : 'var(--primary,#0D6A4E)') }))} /></div></div>
          )}
          <div className="card"><div className="card-header"><h3>Grade distribution</h3></div>
            <div className="card-body">{a.grade_distribution.map((g) => <Bar key={g.grade} label={`Grade ${g.grade}`} value={g.count} max={gradeMax} />)}</div></div>
          {a.gender && a.gender.length > 0 && (
            <div className="card"><div className="card-header"><h3>By gender</h3></div>
              <div className="card-body">{a.gender.map((g) => (
                <div key={g.group} style={{ marginBottom: '.6rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}><strong>{g.group}</strong><span className="text-muted">{g.count} · avg {fmtNum(g.average)}</span></div>
                  <Bar label={`${fmtNum(g.pass_rate)}% pass`} value={g.pass_rate} max={100} pct tone={g.pass_rate >= 50 ? 'var(--success)' : '#e74a3b'} />
                </div>))}</div></div>
          )}
        </div>

        {a.units && a.units.length > 0 && (
          <div className="card mb-3"><div className="card-header"><h3>{a.unit_kind} league (best → worst)</h3>
            <span className="text-muted text-sm">tap a row to drill in</span></div>
            <div className="card-body" style={{ padding: 0 }}>
              <LeagueTable rank rows={a.units.map((u, i) => ({ ...u, _k: i }))} onRow={a.unit_kind !== 'Subject' ? drill : undefined} cols={[
                { key: 'label', label: a.unit_kind, render: (r) => <strong>{r.label}</strong> },
                { key: 'average', label: 'Avg', right: true, render: (r) => <span style={{ color: avgColour(r.average, pm), fontWeight: 700 }}>{fmtNum(r.average)}</span> },
                { key: 'pass_rate', label: 'Pass %', right: true, render: (r) => `${fmtNum(r.pass_rate)}%` },
                { key: 'students', label: 'Students', right: true },
              ]} /></div></div>
        )}

        {((a.branches && a.branches.length > 0) || (a.attendance && a.attendance.bands && a.attendance.bands.length > 0)) && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(340px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
            {a.branches && a.branches.length > 0 && (
              <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-code-branch" /> Campus league</h3></div>
                <div className="card-body" style={{ padding: 0 }}>
                  <LeagueTable rank rows={a.branches.map((b, i) => ({ ...b, _k: i }))} cols={[
                    { key: 'label', label: 'Branch', render: (r) => <strong>{r.label}</strong> },
                    { key: 'average', label: 'Avg', right: true, render: (r) => <span style={{ color: avgColour(r.average, pm), fontWeight: 700 }}>{fmtNum(r.average)}</span> },
                    { key: 'pass_rate', label: 'Pass %', right: true, render: (r) => `${fmtNum(r.pass_rate)}%` },
                    { key: 'students', label: 'Students', right: true },
                  ]} /></div></div>
            )}
            {a.attendance && a.attendance.bands && a.attendance.bands.length > 0 && (
              <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-user-check" /> Attendance vs results</h3>
                {a.attendance.correlation != null && <span className="text-muted text-sm">r = {fmtNum(a.attendance.correlation)}</span>}</div>
                <div className="card-body">
                  {a.attendance.correlation != null && (
                    <div className="text-sm mb-2" style={{ color: 'var(--text-secondary,#4a5568)' }}>
                      {a.attendance.correlation >= 0.3 ? 'Attendance and scores move together — chasing absences should lift results.'
                        : a.attendance.correlation <= -0.1 ? 'Weak link — poor results here are driven more by teaching than absence.'
                          : 'A mild relationship between attendance and scores.'} ({a.attendance.coverage} students)
                    </div>
                  )}
                  {a.attendance.bands.map((b) => (
                    <div key={b.band} style={{ marginBottom: '.4rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                        <span>{b.band} <span className="text-muted">({b.count})</span></span></div>
                      <Bar label={`avg ${fmtNum(b.average)}`} value={b.average} max={100} tone={avgColour(b.average, pm)} />
                    </div>
                  ))}
                </div></div>
            )}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(340px,1fr))', gap: '1rem' }}>
          <div className="card"><div className="card-header"><h3>Subject league (hardest → easiest)</h3>
            <span className="text-muted text-sm">tap a subject for its scorecard</span></div>
            <div className="card-body" style={{ padding: 0 }}>
              <LeagueTable rows={a.subjects.map((x, i) => ({ ...x, _k: i }))}
                onRow={(r) => { if (r.id && d.urls.subject_base) { const b = d.urls.subject_base; nav.go(`${b}${b.includes('?') ? '&' : '?'}subject_id=${r.id}`); } }}
                cols={[
                { key: 'name', label: 'Subject' },
                { key: 'average', label: 'Avg', right: true, render: (r) => <span style={{ color: avgColour(r.average, pm), fontWeight: 700 }}>{fmtNum(r.average)}</span> },
                { key: 'pass_rate', label: 'Pass %', right: true, render: (r) => `${fmtNum(r.pass_rate)}%` },
                { key: 'assessed', label: 'N', right: true },
              ]} /></div></div>

          <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chalkboard-user" /> Teacher effectiveness</h3>
            <span className="text-muted text-sm">tap a teacher for their scorecard</span></div>
            <div className="card-body" style={{ padding: 0 }}>
              {a.teachers.length ? (
                <LeagueTable rank rows={a.teachers.map((x, i) => ({ ...x, _k: i }))}
                  onRow={(r) => { if (r.name && r.name !== 'Unassigned') { const b = d.urls.teacher_base; nav.go(`${b}${b.includes('?') ? '&' : '?'}name=${encodeURIComponent(r.name)}`); } }}
                  cols={[
                  { key: 'name', label: 'Teacher', render: (r) => <div><strong>{r.name}</strong><div className="text-muted text-sm">{r.subject_count} subj · {r.class_count} class{r.class_count === 1 ? '' : 'es'}</div></div> },
                  { key: 'average', label: 'Avg', right: true, render: (r) => <span style={{ color: avgColour(r.average, pm), fontWeight: 700 }}>{fmtNum(r.average)}</span> },
                  { key: 'pass_rate', label: 'Pass %', right: true, render: (r) => `${fmtNum(r.pass_rate)}%` },
                  { key: 'verdict', label: 'Verdict', render: (r) => { const st = FLAG_STYLE[r.flag] || FLAG_STYLE.good; return <span className="badge" style={{ background: st.bg, color: st.fg }}>{r.verdict}</span>; } },
                ]} />
              ) : <div style={{ padding: '1rem' }} className="text-muted">No teachers attributed to these subjects yet — set the teacher on each class-subject.</div>}
            </div></div>

          <div className="card"><div className="card-header"><h3>🏅 Honour roll ({a.honour_roll.length})</h3>
            <span className="text-muted text-sm">distinctions (avg ≥ {s.distinction_mark})</span></div>
            <div className="card-body" style={{ padding: 0 }}>
              {a.honour_roll.length ? (
                <LeagueTable rank rows={a.honour_roll.map((x, i) => ({ ...x, _k: i }))} cols={[
                  { key: 'name', label: 'Student', render: (r) => <span>{r.name} <span className="text-muted text-sm">· {r.class}</span></span> },
                  { key: 'average', label: 'Avg', right: true, render: (r) => <span style={{ color: 'var(--success)', fontWeight: 700 }}>{fmtNum(r.average)}</span> },
                ]} />
              ) : <div style={{ padding: '1rem' }} className="text-muted">No distinctions yet.</div>}
            </div></div>

          <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Needs intervention ({a.intervention.length})</h3>
            {a.intervention.length > 0 && d.urls.compose && (() => {
              const ids = a.intervention.map((x) => x.id).join(',');
              const body = 'Dear Parent, this is to notify you that your ward is performing below expectations this term and would benefit from extra support at home. Please arrange to meet the class teacher. Thank you.';
              const url = `${d.urls.compose}?students=${ids}&body=${encodeURIComponent(body)}`;
              return <a href={url} data-native className="btn btn-primary btn-sm" title="Draft a message to these students' parents"><i aria-hidden="true" className="fas fa-paper-plane" /> Message parents</a>;
            })()}
          </div>
            <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
              {a.intervention.length ? (
                <table className="data-table"><thead><tr><th>Student</th><th>Class</th><th className="text-right">Avg</th><th className="text-right">Failing</th><th /></tr></thead>
                  <tbody>{a.intervention.map((st_) => (
                    <tr key={st_.id}><td>{st_.name}</td><td className="text-muted text-sm">{st_.class}</td>
                      <td className="text-right" style={{ color: '#e74a3b', fontWeight: 600 }}>{fmtNum(st_.average)}</td>
                      <td className="text-right">{st_.failed}</td>
                      <td className="text-right"><a href={cardLink(st_.id)} className="btn btn-sm btn-light" data-native><i aria-hidden="true" className="fas fa-id-card" /></a></td></tr>
                  ))}</tbody></table>
              ) : <div style={{ padding: '1rem' }} className="text-muted">No students below the pass mark. 🎉</div>}
            </div></div>
        </div>

        {a.trends && a.trends.term_names.length > 1 && a.trends.averages.some((v) => v != null) && (
          <div className="card mt-3"><div className="card-header"><h3>Performance trend across terms</h3>
            <span className="text-muted text-sm">{a.scope_label} · this session</span></div>
            <div className="card-body">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: '1.5rem' }}>
                <div>
                  <div className="text-muted text-sm mb-1">Average score</div>
                  {a.trends.term_names.map((tn, i) => (
                    <Bar key={tn} label={tn} value={a.trends.averages[i] == null ? 0 : a.trends.averages[i]} max={100} tone={avgColour(a.trends.averages[i] || 0, pm)} />
                  ))}
                </div>
                <div>
                  <div className="text-muted text-sm mb-1">Pass rate</div>
                  {a.trends.term_names.map((tn, i) => (
                    <Bar key={tn} label={tn} value={a.trends.pass_rates[i] == null ? 0 : a.trends.pass_rates[i]} max={100} pct tone={(a.trends.pass_rates[i] || 0) >= 50 ? 'var(--success)' : '#e74a3b'} />
                  ))}
                </div>
              </div>
            </div></div>
        )}
      </>)}
    </>
  );
}

function Teacher({ d, notify }) {
  const nav = useNav();
  const sc = d.scorecard;
  const s = (sc && sc.summary) || {};
  const pm = s.pass_mark || 50;
  const goTerm = (tid) => navParams(nav.go, d.self_url, { term_id: tid, name: d.teacher_name });
  const hasData = sc && s.entries;
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-chalkboard-user" /> Teacher scorecard</h1>
        <div className="page-header-actions">
          {hasData && d.is_admin && d.staff_id && d.urls.compose && (() => {
            const body = `Dear ${d.teacher_name}, I would like to discuss your class results for this term and how we can support stronger outcomes. Please see me at your earliest convenience. Thank you.`;
            const url = `${d.urls.compose}?to=staff&staff_ids=${d.staff_id}&body=${encodeURIComponent(body)}`;
            return <a href={url} data-native className="btn btn-primary btn-sm" title="Message this teacher privately"><i aria-hidden="true" className="fas fa-paper-plane" /> Message this teacher</a>;
          })()}
          {hasData && (() => {
            const base = d.urls.report_base; const sep = base.includes('?') ? '&' : '?';
            const exp = (fmt) => `${base}${sep}format=${fmt}`;
            return <ExportMenu urls={{ export: exp('excel'), export_pdf: exp('pdf'), export_image: exp('image') }} />;
          })()}
          <a href={d.back_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Institution</a>
        </div>
      </div>
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group"><label className="form-label">Term</label>
            <select className="form-control" value={d.term_id} onChange={(e) => goTerm(e.target.value)}>
              {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
          <div className="form-group" style={{ flex: 1 }}><label className="form-label">Teacher</label>
            <div style={{ fontWeight: 700, fontSize: 'var(--text-lg)', paddingTop: '.3rem' }}>{d.teacher_name || '—'}</div></div>
          {hasData && <span className="badge" style={{ background: (FLAG_STYLE[s.flag] || FLAG_STYLE.good).bg, color: (FLAG_STYLE[s.flag] || FLAG_STYLE.good).fg, alignSelf: 'center' }}>{s.verdict}</span>}
        </form>
      </div></div>

      {!d.teacher_name ? (
        <div className="card"><div className="card-body"><Empty icon="fa-chalkboard-user" title="No teacher selected"><p>Open a teacher from the Institution Analytics teacher league.</p></Empty></div></div>
      ) : !hasData ? (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-column" title="No scores"><p>No scored subjects attributed to <strong>{d.teacher_name}</strong> this term.</p></Empty></div></div>
      ) : (<>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
          <AStat value={fmtNum(s.average)} label="Average score" tone={avgColour(s.average, pm)} />
          <AStat value={`${fmtNum(s.pass_rate)}%`} label="Pass rate" tone={s.pass_rate >= 50 ? 'var(--success)' : '#e74a3b'} />
          <AStat value={s.subjects} label="Subjects" />
          <AStat value={s.classes} label="Classes" />
          <AStat value={s.students} label="Students" />
          <AStat value={`${fmtNum(s.completion)}%`} label="Entry completion" tone={s.completion >= 85 ? undefined : '#c9a227'} />
        </div>

        <div className="card mb-3"><div className="card-header"><h3>Per class-subject (weakest → strongest)</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <LeagueTable rows={sc.rows.map((r, i) => ({ ...r, _k: i }))} cols={[
              { key: 'subject', label: 'Subject', render: (r) => <strong>{r.subject}</strong> },
              { key: 'class', label: 'Class' },
              { key: 'average', label: 'Avg', right: true, render: (r) => <span style={{ color: avgColour(r.average, pm), fontWeight: 700 }}>{fmtNum(r.average)}</span> },
              { key: 'pass_rate', label: 'Pass %', right: true, render: (r) => `${fmtNum(r.pass_rate)}%` },
              { key: 'assessed', label: 'Assessed', right: true, render: (r) => `${r.assessed}/${r.students}` },
              { key: 'completion', label: 'Entry %', right: true, render: (r) => `${fmtNum(r.completion)}%` },
              { key: 'range', label: 'Low–High', right: true, render: (r) => `${fmtNum(r.lowest)}–${fmtNum(r.highest)}` },
            ]} /></div></div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: '1rem' }}>
          <div className="card"><div className="card-header"><h3>By subject</h3></div>
            <div className="card-body">{sc.by_subject.map((x) => (
              <div key={x.name} style={{ marginBottom: '.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}><strong>{x.name}</strong><span className="text-muted">{x.assessed} · {fmtNum(x.pass_rate)}% pass</span></div>
                <Bar label={`avg ${fmtNum(x.average)}`} value={x.average} max={100} tone={avgColour(x.average, pm)} />
              </div>))}</div></div>
          <div className="card"><div className="card-header"><h3>By class</h3></div>
            <div className="card-body">{sc.by_class.map((x) => (
              <div key={x.name} style={{ marginBottom: '.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}><strong>{x.name}</strong><span className="text-muted">{x.assessed} · {fmtNum(x.pass_rate)}% pass</span></div>
                <Bar label={`avg ${fmtNum(x.average)}`} value={x.average} max={100} tone={avgColour(x.average, pm)} />
              </div>))}</div></div>
        </div>

        {sc.trend && sc.trend.term_names.length > 1 && sc.trend.averages.some((v) => v != null) && (
          <div className="card mt-3"><div className="card-header"><h3>Trend across terms</h3></div>
            <div className="card-body">{sc.trend.term_names.map((tn, i) => (
              <Bar key={tn} label={tn} value={sc.trend.averages[i] == null ? 0 : sc.trend.averages[i]} max={100} tone={avgColour(sc.trend.averages[i] || 0, pm)} />
            ))}</div></div>
        )}
      </>)}
    </>
  );
}

function SubjectScorecard({ d, notify }) {
  const nav = useNav();
  const sc = d.scorecard;
  const s = (sc && sc.summary) || {};
  const pm = s.pass_mark || 50;
  const goTerm = (tid) => navParams(nav.go, d.self_url, { term_id: tid, subject_id: d.subject_id });
  const hasData = sc && s.entries;
  const gradeMax = sc && sc.grade_distribution && sc.grade_distribution.length ? Math.max(1, ...sc.grade_distribution.map((g) => g.count)) : 1;
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-book" /> Subject scorecard</h1>
        <div className="page-header-actions">
          {hasData && (() => {
            const base = d.urls.report_base; const sep = base.includes('?') ? '&' : '?';
            const exp = (fmt) => `${base}${sep}format=${fmt}`;
            return <ExportMenu urls={{ export: exp('excel'), export_pdf: exp('pdf'), export_image: exp('image') }} />;
          })()}
          <a href={d.back_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Institution</a>
        </div>
      </div>
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group"><label className="form-label">Term</label>
            <select className="form-control" value={d.term_id} onChange={(e) => goTerm(e.target.value)}>
              {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
          <div className="form-group" style={{ flex: 1 }}><label className="form-label">Subject</label>
            <div style={{ fontWeight: 700, fontSize: 'var(--text-lg)', paddingTop: '.3rem' }}>{sc ? sc.subject : '—'}</div></div>
        </form>
      </div></div>

      {!d.subject_id ? (
        <div className="card"><div className="card-body"><Empty icon="fa-book" title="No subject selected"><p>Open a subject from the Institution Analytics subject league.</p></Empty></div></div>
      ) : !hasData ? (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-column" title="No scores"><p>No scores for <strong>{sc ? sc.subject : 'this subject'}</strong> this term.</p></Empty></div></div>
      ) : (<>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
          <AStat value={fmtNum(s.average)} label="Average score" tone={avgColour(s.average, pm)} />
          <AStat value={`${fmtNum(s.pass_rate)}%`} label="Pass rate" tone={s.pass_rate >= 50 ? 'var(--success)' : '#e74a3b'} />
          <AStat value={`${fmtNum(s.distinction_rate)}%`} label="Distinctions" tone="var(--success)" />
          <AStat value={s.classes} label="Class arms" />
          <AStat value={s.teachers} label="Teachers" />
          <AStat value={`${fmtNum(s.completion)}%`} label="Entry completion" tone={s.completion >= 85 ? undefined : '#c9a227'} />
        </div>

        <div className="card mb-3"><div className="card-header"><h3>Per class-arm (weakest → strongest)</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <LeagueTable rows={sc.rows.map((r, i) => ({ ...r, _k: i }))} cols={[
              { key: 'class', label: 'Class', render: (r) => <strong>{r.class}</strong> },
              { key: 'teacher', label: 'Teacher', render: (r) => <span className="text-muted">{r.teacher}</span> },
              { key: 'average', label: 'Avg', right: true, render: (r) => <span style={{ color: avgColour(r.average, pm), fontWeight: 700 }}>{fmtNum(r.average)}</span> },
              { key: 'pass_rate', label: 'Pass %', right: true, render: (r) => `${fmtNum(r.pass_rate)}%` },
              { key: 'assessed', label: 'Assessed', right: true, render: (r) => `${r.assessed}/${r.students}` },
              { key: 'range', label: 'Low–High', right: true, render: (r) => `${fmtNum(r.lowest)}–${fmtNum(r.highest)}` },
            ]} /></div></div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: '1rem' }}>
          <div className="card"><div className="card-header"><h3>By teacher (who gets the best results)</h3></div>
            <div className="card-body">{sc.by_teacher.map((x) => (
              <div key={x.name} style={{ marginBottom: '.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}><strong>{x.name}</strong><span className="text-muted">{x.assessed} · {fmtNum(x.pass_rate)}% pass</span></div>
                <Bar label={`avg ${fmtNum(x.average)}`} value={x.average} max={100} tone={avgColour(x.average, pm)} />
              </div>))}</div></div>
          <div className="card"><div className="card-header"><h3>Grade distribution</h3></div>
            <div className="card-body">{(sc.grade_distribution || []).map((g) => <Bar key={g.grade} label={`Grade ${g.grade}`} value={g.count} max={gradeMax} />)}</div></div>
          {sc.score_bands && sc.score_bands.length > 0 && (
            <div className="card"><div className="card-header"><h3>Score spread</h3></div>
              <div className="card-body"><ColumnChart bars={sc.score_bands.map((b) => ({ label: b.band, value: b.count, color: b.band === '0–39' ? '#e74a3b' : (parseInt(b.band, 10) >= 70 ? 'var(--success,#1c8c53)' : 'var(--primary,#0D6A4E)') }))} /></div></div>
          )}
        </div>

        {sc.trend && sc.trend.term_names.length > 1 && sc.trend.averages.some((v) => v != null) && (
          <div className="card mt-3"><div className="card-header"><h3>Trend across terms</h3></div>
            <div className="card-body">{sc.trend.term_names.map((tn, i) => (
              <Bar key={tn} label={tn} value={sc.trend.averages[i] == null ? 0 : sc.trend.averages[i]} max={100} tone={avgColour(sc.trend.averages[i] || 0, pm)} />
            ))}</div></div>
        )}
      </>)}
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
