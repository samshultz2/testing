import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { Banner, SectionShell, Empty } from '../components/ui';

// ---- Subjects list ---------------------------------------------------------
function List({ d, notify }) {
  const nav = useNav();
  const del = async (url, name) => {
    if (!window.confirm(`Delete ${name}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <div className="page-header"><h1>Subjects</h1>
        <div className="page-header-actions">
          <a href={d.urls.bulk_add} className="btn btn-secondary"><i className="fas fa-list" /> Bulk Add</a>
          <a href={d.urls.add} className="btn btn-primary"><i className="fas fa-plus" /> Add</a>
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
                    <a href={s.edit_url} className="btn btn-secondary btn-sm"><i className="fas fa-edit" /></a>
                    <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(s.delete_url, s.name)}><i className="fas fa-trash" /></button>
                  </div>
                </div>))}
            </div>
          </div>
        </div>
      )) : (
        <div className="card"><div className="card-body"><Empty icon="fa-book" title="No Subjects"><p>Add your first subject</p><a href={d.urls.add} className="btn btn-primary"><i className="fas fa-plus" /> Add Subject</a></Empty></div></div>
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
          <button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> Save</button>
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
          <button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> Add All</button>
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
    if (!window.confirm(`Remove ${name}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not remove.');
  };
  const copy = async (e) => {
    e.preventDefault();
    if (!copyFrom) { notify('error', 'Select a source term.'); return; }
    if (!window.confirm('Copy subject assignments into this term?')) return;
    const r = await submitJson(d.urls.copy, { to_term_id: d.term_id, from_term_id: copyFrom, class_id: d.class_id || '' });
    if (r.ok) { notify('success', r.message); setShowCopy(false); nav.refresh(); } else notify('error', r.error || 'Could not copy.');
  };
  return (
    <>
      <div className="page-header"><h1>Class Subjects</h1>
        <div className="page-header-actions">
          {d.term_id && <button type="button" className="btn btn-info btn-sm" onClick={() => setShowCopy((s) => !s)}><i className="fas fa-copy" /> Copy from term</button>}
          <a href={d.urls.assign} className="btn btn-primary"><i className="fas fa-plus" /> Assign</a>
        </div>
      </div>

      {d.term_id && showCopy && (
        <div className="card mb-3" style={{ borderColor: 'var(--info)' }}>
          <div className="card-header"><h3><i className="fas fa-copy" /> Copy subject assignments into {d.selected_term || 'this term'}</h3></div>
          <div className="card-body">
            <p className="text-muted text-sm">Copy the subject-to-class assignments (and teachers) from another term. You can modify them afterwards. Existing assignments are kept.</p>
            <form onSubmit={copy} className="d-flex gap-2 align-center flex-wrap">
              <label className="form-label mb-0">Copy from</label>
              <select className="form-control" style={{ maxWidth: 240 }} required value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
                <option value="">Select source term…</option>
                {d.terms.filter((t) => String(t.id) !== String(d.term_id)).map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select>
              <button type="submit" className="btn btn-primary"><i className="fas fa-copy" /> Copy{d.class_id ? ' (this class)' : ' (all classes)'}</button>
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
                    <a href={cs.edit_url} className="btn btn-secondary btn-sm"><i className="fas fa-edit" /></a>
                    <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(cs.delete_url, `${cs.subject} from ${cs.class_name}`)}><i className="fas fa-times" /></button>
                  </div>
                </div>))}
            </div>
          </div></div>
      ) : d.term_id ? (
        <div className="card"><div className="card-body"><Empty icon="fa-book-open" title="No Subjects Assigned"><p>Assign subjects to classes for this term</p><a href={d.urls.assign} className="btn btn-primary"><i className="fas fa-plus" /> Assign Subjects</a></Empty></div></div>
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
          <button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> Assign Selected</button>
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
            <button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> Save</button>
            <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
          </div>
        </form>
      </div></div>
    </>
  );
}

const SCREENS = { list: List, add: SubjectForm, edit: SubjectForm, bulk_add: BulkAdd,
  class_subjects: ClassSubjects, assign: Assign, edit_class_subject: EditClassSubject };

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
