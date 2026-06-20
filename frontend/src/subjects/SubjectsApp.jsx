import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';

// Shared term + class (assignment) filter bar used by the score-workflow pages.
function ClassFilter({ d, extraTerm = false }) {
  const nav = useNav();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, ...extra });
  return (
    <div className="card mb-3"><div className="card-body"><form className="filter-form" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <div className="form-group"><label className="form-label">Term</label>
        <select className="form-control" value={d.term_id} onChange={(e) => go({ term_id: e.target.value, assignment_id: '' })}>
          {extraTerm && <option value="">Select Term</option>}
          {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
      <div className="form-group"><label className="form-label">Class</label>
        <select className="form-control" value={d.assignment_id} onChange={(e) => go({ assignment_id: e.target.value })}>
          <option value="">Select class…</option>{d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}</select></div>
    </form></div></div>
  );
}

// ---- Subjects list ---------------------------------------------------------
function List({ d, notify }) {
  const nav = useNav();
  const del = async (url, name) => {
    if (!await confirm(`Delete ${name}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <div className="page-header"><h1>Subjects</h1>
        <div className="page-header-actions">
          <a href={d.urls.bulk_add} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-list" /> Bulk Add</a>
          <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</a>
        </div>
      </div>
      {d.categories.length ? d.categories.map((cat) => (
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
                  <div className="data-card-actions">
                    <a href={s.edit_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-edit" /></a>
                    <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(s.delete_url, s.name)}><i aria-hidden="true" className="fas fa-trash" /></button>
                  </div>
                </div>))}
            </div>
          </div>
        </div>
      )) : (
        <div className="card"><div className="card-body"><Empty icon="fa-book" title="No Subjects"><p>Add your first subject</p><a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Subject</a></Empty></div></div>
      )}
    </>
  );
}

// ---- Add / edit subject ----------------------------------------------------
function SubjectForm({ d, notify }) {
  const nav = useNav();
  const init = d.subject || { name: '', short_name: '', category: d.categories[0], has_practical: true };
  const [f, setF] = useState({ name: init.name, short_name: init.short_name, category: init.category, has_practical: init.has_practical });
  const [busy, setBusy] = useState(false);
  const isEdit = d.page === 'edit';
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify('error', 'Subject name is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, has_practical: f.has_practical ? 'on' : '' });
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
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, ...extra });
  const del = async (url, name) => {
    if (!await confirm(`Remove ${name}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not remove.');
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
          {d.term_id && <button type="button" className="btn btn-info btn-sm" onClick={() => setShowCopy((s) => !s)}><i aria-hidden="true" className="fas fa-copy" /> Copy from term</button>}
          <a href={d.urls.assign} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Assign</a>
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

      {d.class_subjects.length ? (
        <div className="card"><div className="card-header"><h3>Subjects ({d.class_subjects.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <div className="data-cards" style={{ padding: '1rem' }}>
              {d.class_subjects.map((cs) => (
                <div className="data-card" key={cs.id}>
                  <div className="data-card-header"><div className="data-card-title">{cs.subject}</div><span className="badge badge-info">{cs.class_name}</span></div>
                  <div className="data-card-row"><span className="data-card-label">Teacher</span><span>{cs.teacher_name || '-'}</span></div>
                  {cs.arm && <div className="data-card-row"><span className="data-card-label">Arm</span><span>{cs.arm}</span></div>}
                  <div className="data-card-actions">
                    <a href={cs.edit_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-edit" /></a>
                    <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(cs.delete_url, `${cs.subject} from ${cs.class_name}`)}><i aria-hidden="true" className="fas fa-times" /></button>
                  </div>
                </div>))}
            </div>
          </div></div>
      ) : d.term_id ? (
        <div className="card"><div className="card-body"><Empty icon="fa-book-open" title="No Subjects Assigned"><p>Assign subjects to classes for this term</p><a href={d.urls.assign} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Assign Subjects</a></Empty></div></div>
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
  const allChecked = d.subjects.length > 0 && d.subjects.every((s) => rows[s.id].checked);
  const toggleAll = (v) => setRows((m) => { const n = { ...m }; d.subjects.forEach((s) => { n[s.id] = { ...n[s.id], checked: v }; }); return n; });
  const setRow = (id, k, v) => setRows((m) => ({ ...m, [id]: { ...m[id], [k]: v } }));
  const submit = async (e) => {
    e.preventDefault();
    if (!termId || !classId) { notify('error', 'Term and class are required.'); return; }
    const subject_ids = []; const teacher_names = [];
    d.subjects.forEach((s) => { if (rows[s.id].checked) { subject_ids.push(s.id); teacher_names.push(rows[s.id].teacher); } });
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
        <div className="table-container"><table className="data-table">
          <thead><tr><th style={{ width: 40 }}><input type="checkbox" checked={allChecked} onChange={(e) => toggleAll(e.target.checked)} /></th><th>Subject</th><th>Teacher Name</th></tr></thead>
          <tbody>{d.subjects.map((s) => (
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
function Scores({ d, notify }) {
  const nav = useNav();
  const [scores, setScores] = useState(() => { const m = {}; d.students_data.forEach((s) => { m[s.id] = s.score === '' ? '' : String(s.score); }); return m; });
  const [busy, setBusy] = useState(false);
  React.useEffect(() => { const m = {}; d.students_data.forEach((s) => { m[s.id] = s.score === '' ? '' : String(s.score); }); setScores(m); }, [d.students_data]);
  const set = (params) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, class_subject_id: d.class_subject_id, assessment_type_id: d.assessment_type_id, ...params });
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id, class_subject_id: d.class_subject_id, assessment_type_id: d.assessment_type_id,
      'student_id[]': d.students_data.map((s) => s.id), 'score[]': d.students_data.map((s) => scores[s.id] ?? '') };
    const r = await submitJson(d.save_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Score Entry</h1>
        <div className="page-header-actions">
          <a href={d.urls.scan} className="btn btn-primary" data-native><i aria-hidden="true" className="fas fa-camera" /> Scan Score Sheet</a>
          <a href={d.urls.import} className="btn btn-secondary" data-native><i aria-hidden="true" className="fas fa-file-excel" /> Import Excel</a>
        </div>
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
        <div className="form-group"><label className="form-label">Assessment</label>
          <select className="form-control" value={d.assessment_type_id} onChange={(e) => set({ assessment_type_id: e.target.value })}>
            <option value="">Select Assessment</option>{d.assessment_types.map((at) => <option key={at.id} value={at.id}>{at.name} ({at.max_score})</option>)}</select></div>
      </form></div></div>

      {d.students_data.length ? (
        <div className="card">
          <div className="card-header"><h3>{d.selected_subject} - {d.selected_assessment}</h3><span className="badge badge-primary">Max: {d.max_score}</span></div>
          <div className="card-body"><form onSubmit={save}>
            <div className="table-container"><table className="data-table">
              <thead><tr><th>S/N</th><th>Student</th><th>Gender</th><th>Score (Max: {d.max_score})</th></tr></thead>
              <tbody>{d.students_data.map((s, i) => (
                <tr key={s.id}><td>{i + 1}</td><td>{s.full_name}</td>
                  <td><span className={'badge ' + (s.gender === 'Male' ? 'badge-info' : 'badge-warning')}>{s.gender}</span></td>
                  <td><input type="number" className="form-control" style={{ width: 100 }} min="0" max={d.max_score} step="0.5" value={scores[s.id] ?? ''} onChange={(e) => setScores((m) => ({ ...m, [s.id]: e.target.value }))} /></td></tr>))}</tbody>
            </table></div>
            <div className="page-header-actions mt-3"><button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Scores</button></div>
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
          <button type="button" className="btn btn-primary" onClick={compute}><i aria-hidden="true" className="fas fa-ranking-star" /> Finalize (compute results &amp; positions)</button>
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
            <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save all scores</button>
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
function Broadsheet({ d, notify }) {
  const nav = useNav();
  const compute = async () => {
    if (!await confirm("Compute and save term results and class positions for this class? This updates each student's report card.")) return;
    const r = await submitJson(d.urls.compute, { term_id: d.term_id, assignment_id: d.assignment_id });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not compute.');
  };
  const sticky = (left) => ({ position: 'sticky', left, background: 'var(--bg-primary)', whiteSpace: 'nowrap' });
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
        <div className="card">
          <div className="card-header"><h3>{d.selected_assignment}</h3>
            <div className="page-header-actions">
              <button type="button" className="btn btn-primary btn-sm" onClick={compute}><i aria-hidden="true" className="fas fa-ranking-star" /> Compute results &amp; positions</button>
              <a href={d.urls.bulk_entry} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-pen-to-square" /> Bulk Entry</a>
              <a href={d.urls.affective} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-star-half-stroke" /> Behaviour</a>
              <a href={d.urls.comments} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-comment-dots" /> Comments</a>
              <a href={d.urls.export} className="btn btn-success btn-sm" data-native download><i aria-hidden="true" className="fas fa-download" /> Export</a>
              <span className="badge badge-info">{d.rows.length} Students</span>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table" style={{ minWidth: '100%' }}>
              <thead><tr>
                <th style={{ position: 'sticky', left: 0, background: 'var(--bg-secondary)', zIndex: 2 }}>Pos</th>
                <th style={{ position: 'sticky', left: 40, background: 'var(--bg-secondary)', zIndex: 2 }}>Student</th>
                {d.class_subjects.map((cs) => <th key={cs.id} style={{ textAlign: 'center', fontSize: '0.75rem' }}>{cs.short}</th>)}
                <th style={{ textAlign: 'center' }}>Total</th><th style={{ textAlign: 'center' }}>Avg</th><th style={{ textAlign: 'center' }}>P/F</th>
              </tr></thead>
              <tbody>{d.rows.map((r, i) => (
                <tr key={i}>
                  <td style={{ ...sticky(0), fontWeight: 'bold' }}>{r.position}</td>
                  <td style={sticky(40)}>{r.student}</td>
                  {d.class_subjects.map((cs) => <td key={cs.id} style={{ textAlign: 'center' }}>{r.subjects[String(cs.id)] != null ? r.subjects[String(cs.id)] : '-'}</td>)}
                  <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{r.total}</td>
                  <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{r.average}</td>
                  <td style={{ textAlign: 'center' }}><span className="badge badge-success">{r.passed}</span> <span className="badge badge-danger">{r.failed}</span></td>
                </tr>))}</tbody>
            </table>
          </div>
        </div>
        <div className="card mt-3"><div className="card-header"><h3>Legend</h3></div>
          <div className="card-body"><div className="filter-form">
            {d.class_subjects.map((cs) => <div key={cs.id} style={{ marginRight: '1rem', marginBottom: '0.5rem' }}><strong>{cs.short}</strong> = {cs.name}</div>)}
          </div></div></div>
      </>) : d.has_selection ? (
        <div className="card"><div className="card-body"><Empty icon="fa-table" title="No Data"><p>No scores entered for this class yet</p><a href={d.urls.scores} className="btn btn-primary"><i aria-hidden="true" className="fas fa-edit" /> Enter Scores</a></Empty></div></div>
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
              <thead><tr><th>Student</th>{d.traits.map((t) => <th key={t.key} style={{ fontSize: '.7rem', writingMode: 'vertical-rl', transform: 'rotate(180deg)', whiteSpace: 'nowrap' }}>{t.label}</th>)}</tr></thead>
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
            <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save ratings</button>
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
          <div style={{ marginTop: '1rem' }}><button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save comments</button></div>
        </form>
      ) : d.selected ? (
        <div className="card"><div className="card-body"><Empty icon="fa-users" title=""><p>No students enrolled in this class for the term.</p></Empty></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title=""><p>Select a term and class to enter comments.</p></Empty></div></div>
      )}
    </>
  );
}

const SCREENS = { list: List, add: SubjectForm, edit: SubjectForm, bulk_add: BulkAdd,
  class_subjects: ClassSubjects, assign: Assign, edit_class_subject: EditClassSubject,
  scores: Scores, workflow: Workflow, bulk_entry: BulkEntry, broadsheet: Broadsheet,
  affective: Affective, comments: Comments };

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
