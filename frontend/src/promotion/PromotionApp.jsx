import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, PageHeader, Empty, SectionShell } from '../components/ui';


// ---- Index -----------------------------------------------------------------
function Index({ d }) {
  const links = [
    ['rules', 'fa-list-alt', 'Promotion Rules', 'Configure promotion criteria and streams'],
    ['process', 'fa-user-graduate', 'Process Promotions', 'Review and promote students'],
    ['graduates', 'fa-graduation-cap', 'Graduates', 'View graduated students with WAEC/JAMB results'],
    ['history', 'fa-history', 'Promotion History', 'View past promotion records'],
  ];
  return (
    <>
      <PageHeader title="Student Promotion" />
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-cog" /></div>
          <div className="stat-content"><h3>{d.rules_count}</h3><p>Promotion Rules</p></div></div>
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-calendar" /></div>
          <div className="stat-content"><h3>{d.active_session || '-'}</h3><p>Active Session</p></div></div>
      </div>
      <div className="data-cards" style={{ padding: 0 }}>
        {links.map(([key, icon, title, desc]) => (
          <a key={key} href={d.urls[key]} className="data-card" style={{ textDecoration: 'none', color: 'inherit' }}>
            <div className="data-card-header"><div className="data-card-title"><i aria-hidden="true" className={'fas ' + icon} /> {title}</div></div>
            <div className="data-card-row">{desc}</div>
          </a>
        ))}
      </div>
      {d.recent.length > 0 && (
        <div className="card mt-3"><div className="card-header"><h3>Recent Promotions</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="data-cards" style={{ padding: '1rem' }}>
            {d.recent.map((p, i) => (
              <div className="data-card" key={i}>
                <div className="data-card-header"><div className="data-card-title">{p.name}</div>
                  <span className={'badge ' + p.status_badge}>{p.status}</span></div>
                <div className="data-card-row"><span className="data-card-label">From</span><span>{p.from_class}</span></div>
                <div className="data-card-row"><span className="data-card-label">To</span><span>{p.to_class}</span></div>
                {p.stream && <div className="data-card-row"><span className="data-card-label">Stream</span><span>{p.stream}</span></div>}
              </div>
            ))}
          </div></div></div>
      )}
    </>
  );
}

// ---- Rules -----------------------------------------------------------------
function Rules({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const del = async (r) => {
    if (!await confirm('Delete this rule?')) return;
    setBusy(true);
    const res = await submitJson(r.delete_url, {});
    setBusy(false);
    if (res.ok) nav.refresh(); else notify('error', res.error || 'Could not delete.');
  };
  return (
    <>
      <PageHeader title="Promotion Rules" actions={<a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Rule</a>} />
      {d.rules.length ? (
        <div className="card"><div className="card-body" style={{ padding: 0 }}><div className="data-cards" style={{ padding: '1rem' }}>
          {d.rules.map((r) => (
            <div className="data-card" key={r.id}>
              <div className="data-card-header"><div className="data-card-title">{r.from_class} → {r.to_class}</div>
                {r.stream_name && <span className="badge badge-info">{r.stream_name}</span>}</div>
              <div className="data-card-row"><span className="data-card-label">Min Average</span><span>{r.min_average}%</span></div>
              <div className="data-card-row"><span className="data-card-label">Priority</span><span>{r.priority}</span></div>
              {r.required_count > 0 && <div className="data-card-row"><span className="data-card-label">Required Subjects</span><span>{r.required_count} subjects</span></div>}
              <div className="data-card-actions">
                <button type="button" className="btn btn-danger btn-sm w-100" disabled={busy} onClick={() => del(r)}><i aria-hidden="true" className="fas fa-trash" /> Delete</button>
              </div>
            </div>
          ))}
        </div></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-list-alt" title="No Rules">
          <p>Add promotion rules to define how students are promoted</p>
          <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Rule</a></Empty></div></div>
      )}
      <div className="card mt-3"><div className="card-header"><h3>How Rules Work</h3></div>
        <div className="card-body">
          <p><strong>Basic Promotion:</strong> Students meeting the promotion threshold are promoted to the next class.</p>
          <p><strong>Stream-based (SSS1 → SSS2):</strong> Create rules with different streams (Science, Arts, etc.) and required subjects. Higher priority rules are checked first.</p>
        </div></div>
    </>
  );
}

// ---- Add rule --------------------------------------------------------------
function AddRule({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ from_class_id: '', to_class_id: '', stream_name: '', min_average: '50', priority: '0' });
  const [subjects, setSubjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.from_class_id || !f.to_class_id) { notify('error', 'Select both classes.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, 'required_subjects[]': subjects });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const toggleSubj = (e) => setSubjects(Array.from(e.target.selectedOptions).map((o) => o.value));
  return (
    <>
      <PageHeader title="Add Promotion Rule" />
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-row">
          <div className="form-group"><label className="form-label">From Class <span className="required">*</span></label>
            <select className="form-control" required value={f.from_class_id} onChange={(e) => set('from_class_id', e.target.value)}>
              <option value="">Select</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">To Class <span className="required">*</span></label>
            <select className="form-control" required value={f.to_class_id} onChange={(e) => set('to_class_id', e.target.value)}>
              <option value="">Select</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        </div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Stream Name (optional)</label>
            <input type="text" className="form-control" placeholder="e.g., Science, Arts, Social Science" value={f.stream_name} onChange={(e) => set('stream_name', e.target.value)} />
            <small className="text-muted">Leave blank for basic promotion</small></div>
          <div className="form-group"><label className="form-label">Minimum Average (%)</label>
            <input type="number" className="form-control" min="0" max="100" step="0.5" value={f.min_average} onChange={(e) => set('min_average', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Priority</label>
            <input type="number" className="form-control" min="0" max="10" value={f.priority} onChange={(e) => set('priority', e.target.value)} />
            <small className="text-muted">Higher = checked first</small></div>
        </div>
        <div className="form-group"><label className="form-label">Required Subjects (for stream)</label>
          <select className="form-control" multiple size="8" value={subjects} onChange={toggleSubj}>
            {d.subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          <small className="text-muted">Hold Ctrl/Cmd to select multiple. Average of these subjects must meet minimum.</small></div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Rule</button>
          <a href={d.urls.rules} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Process ---------------------------------------------------------------
// Streams (class arms) available for a destination class, falling back to the
// global stream list when a class has no arms configured yet.
function streamsForClass(d, classId) {
  const byClass = (d.class_streams && d.class_streams[String(classId)]) || [];
  return byClass.length ? byClass : (d.streams || []);
}

function Process({ d, notify }) {
  const nav = useNav();
  const defaultClass = d.classes[0] ? String(d.classes[0].id) : '';
  const [rows, setRows] = useState(() => d.students.map((s) => ({
    id: s.id, action: s.recommendation.status === 'graduated' ? 'graduated'
      : (s.recommendation.status === 'promote' ? 'promoted' : (s.recommendation.status === 'repeat' ? 'repeated' : 'skip')),
    to_class_id: s.recommendation.to_class ? String(s.recommendation.to_class) : defaultClass,
    stream: s.recommendation.stream || '', average: s.average,
    isGrad: s.recommendation.status === 'graduated',
  })));
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState(() => new Set());      // selected student ids
  const [bulk, setBulk] = useState({ action: 'promoted', to_class_id: defaultClass, stream: '' });
  const setRow = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  // Only non-graduating rows can be bulk-promoted to a class/stream.
  const selectableIds = rows.filter((r) => !r.isGrad).map((r) => r.id);
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => sel.has(id));
  const toggleAll = () => setSel(allSelected ? new Set() : new Set(selectableIds));

  const applyBulk = () => {
    if (!sel.size) { notify('error', 'Select at least one student first.'); return; }
    setRows((rs) => rs.map((r) => (sel.has(r.id) && !r.isGrad ? {
      ...r, action: bulk.action,
      to_class_id: bulk.action === 'promoted' ? (bulk.to_class_id || r.to_class_id) : r.to_class_id,
      stream: bulk.action === 'promoted' && bulk.stream !== '' ? bulk.stream : r.stream,
    } : r)));
  };

  const submit = async () => {
    setBusy(true);
    const fields = { from_session_id: d.from_session_id, to_session_id: d.to_session_id,
      'student_id[]': rows.map((r) => r.id), 'average[]': rows.map((r) => r.average ?? ''),
      'action[]': rows.map((r) => r.action), 'to_class_id[]': rows.map((r) => r.to_class_id || ''),
      'stream[]': rows.map((r) => r.stream) };
    const res = await submitJson(d.execute_url, fields);
    setBusy(false);
    if (res.ok) nav.go(res.redirect); else notify('error', res.error || 'Could not save promotions.');
  };

  const bulkStreams = streamsForClass(d, bulk.to_class_id);

  return (
    <>
      <PageHeader title="Process Promotions" />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">From Session</label>
          <select className="form-control" value={d.from_session_id} onChange={(e) => navParams(nav.go, d.urls.self, { from_session_id: e.target.value, to_session_id: d.to_session_id, class_id: d.class_id })}>
            <option value="">Select Session</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">To Session</label>
          <select className="form-control" value={d.to_session_id} onChange={(e) => navParams(nav.go, d.urls.self, { from_session_id: d.from_session_id, to_session_id: e.target.value, class_id: d.class_id })}>
            <option value="">Select Session</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Class</label>
          <select className="form-control" value={d.class_id} onChange={(e) => navParams(nav.go, d.urls.self, { from_session_id: d.from_session_id, to_session_id: d.to_session_id, class_id: e.target.value })}>
            <option value="">Select Class</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      </div></div></div>

      {d.students.length ? (<>
        <div className="card mb-3"><div className="card-body">
          <p><strong>Promotion Threshold:</strong> {d.threshold}%</p>
          <p className="text-muted">Students are evaluated based on their Third Term average scores. Tick students and use the bar below to promote many at once.</p>
        </div></div>

        {/* Bulk action bar — apply one action/class/stream to all ticked students. */}
        <div className="card mb-3"><div className="card-body"><div className="filter-form" style={{ alignItems: 'flex-end' }}>
          <div className="form-group"><label className="form-label">With {sel.size} selected</label>
            <select className="form-control" value={bulk.action} onChange={(e) => setBulk((b) => ({ ...b, action: e.target.value }))}>
              <option value="promoted">Promote</option><option value="repeated">Repeat</option><option value="skip">Skip</option>
            </select></div>
          {bulk.action === 'promoted' && (<>
            <div className="form-group"><label className="form-label">Promote to</label>
              <select className="form-control" value={bulk.to_class_id} onChange={(e) => setBulk((b) => ({ ...b, to_class_id: e.target.value, stream: '' }))}>
                {d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Stream</label>
              <select className="form-control" value={bulk.stream} onChange={(e) => setBulk((b) => ({ ...b, stream: e.target.value }))}>
                <option value="">— No change —</option>
                {bulkStreams.map((nm) => <option key={nm} value={nm}>{nm}</option>)}</select></div>
          </>)}
          <div className="form-group"><button type="button" className="btn btn-secondary" onClick={applyBulk}><i aria-hidden="true" className="fas fa-wand-magic-sparkles" /> Apply to selected</button></div>
        </div></div></div>

        <div className="card">
          <div className="card-header"><h3>{d.selected_class_name} Students ({d.students.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container">
            <table className="data-table"><thead><tr>
              <th style={{ width: 32 }}><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all" /></th>
              <th>Student</th><th>Average</th><th>Recommendation</th><th>Action</th><th>Promote To</th><th>Stream</th></tr></thead>
              <tbody>{d.students.map((s, i) => {
                const r = rows[i];
                const isGrad = r.isGrad;
                const rowStreams = streamsForClass(d, r.to_class_id);
                // Keep the current value selectable even if not in the class's list.
                const opts = r.stream && !rowStreams.includes(r.stream) ? [r.stream, ...rowStreams] : rowStreams;
                return (
                  <tr key={s.id}>
                    <td>{isGrad ? null : <input type="checkbox" checked={sel.has(s.id)} onChange={() => toggle(s.id)} aria-label={'Select ' + s.name} />}</td>
                    <td>{s.name}<br /><small className="text-muted">{s.assignment}</small></td>
                    <td>{s.average != null ? <span className={'badge ' + (s.over_threshold ? 'badge-success' : 'badge-warning')}>{s.average}%</span> : <span className="text-muted">No scores</span>}</td>
                    <td>{s.existing_status ? <span className="badge badge-info">{s.existing_status}</span> : s.recommendation.message}</td>
                    <td><select className="form-control" style={{ width: 120 }} value={r.action} onChange={(e) => setRow(i, 'action', e.target.value)}>
                      <option value="skip">Skip</option>
                      {isGrad ? <option value="graduated">Graduate</option> : <><option value="promoted">Promote</option><option value="repeated">Repeat</option></>}
                    </select></td>
                    <td>{isGrad ? <span className="text-muted">N/A</span> : (
                      <select className="form-control" style={{ width: 110 }} value={r.to_class_id} onChange={(e) => setRow(i, 'to_class_id', e.target.value)}>
                        {d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>)}</td>
                    <td>{isGrad ? <span className="text-muted">N/A</span> : (
                      <select className="form-control" style={{ width: 120 }} value={r.stream} onChange={(e) => setRow(i, 'stream', e.target.value)}>
                        <option value="">— None —</option>
                        {opts.map((nm) => <option key={nm} value={nm}>{nm}</option>)}</select>)}</td>
                  </tr>
                );
              })}</tbody></table>
          </div></div>
          <div className="card-body"><div className="page-header-actions">
            <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}><i aria-hidden="true" className="fas fa-save" /> Save Promotions</button>
          </div></div>
        </div>
      </>) : (d.from_session_id && d.class_id
        ? <div className="card"><div className="card-body"><Empty icon="fa-users" title="No Students"><p>No students found for this class in the selected session's Third Term</p></Empty></div></div>
        : <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select Options"><p>Choose session and class to process promotions</p></Empty></div></div>)}
    </>
  );
}

// ---- Graduates -------------------------------------------------------------
function Graduates({ d }) {
  const nav = useNav();
  const males = d.graduates.filter((g) => g.gender === 'Male').length;
  const females = d.graduates.filter((g) => g.gender === 'Female').length;
  return (
    <>
      <PageHeader title="Graduates" actions={<a href={d.preview_url} className="btn btn-success"><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate current SSS3</a>} />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Graduation Session</label>
          <select className="form-control" value={d.session_id} onChange={(e) => navParams(nav.go, window.location.pathname, { session_id: e.target.value })}>
            <option value="">All Sessions</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
      </div></div></div>
      {d.graduates.length ? (<>
        <div className="stats-grid mb-3">
          <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-graduation-cap" /></div><div className="stat-content"><h3>{d.graduates.length}</h3><p>Total Graduates</p></div></div>
          <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-male" /></div><div className="stat-content"><h3>{males}</h3><p>Male</p></div></div>
          <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-female" /></div><div className="stat-content"><h3>{females}</h3><p>Female</p></div></div>
        </div>
        <div className="card"><div className="card-header"><h3>Graduates ({d.graduates.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="data-cards" style={{ padding: '1rem' }}>
            {d.graduates.map((s) => (
              <div className="data-card" key={s.id}>
                <div className="data-card-header"><div className="data-card-title">{s.full_name}</div><span className="badge badge-success"><i aria-hidden="true" className="fas fa-graduation-cap" /></span></div>
                <div className="data-card-row"><span className="data-card-label">ID</span><span>{s.student_id}</span></div>
                <div className="data-card-row"><span className="data-card-label">Gender</span><span>{s.gender}</span></div>
                {s.graduation_date && <div className="data-card-row"><span className="data-card-label">Graduated</span><span>{s.graduation_date}</span></div>}
                {s.graduation_session && <div className="data-card-row"><span className="data-card-label">Session</span><span>{s.graduation_session}</span></div>}
                <div className="data-card-row"><span className="data-card-label">Results</span><span>
                  {s.has_waec && <span className="badge badge-info">WAEC</span>} {s.has_jamb && <span className="badge badge-primary">JAMB</span>}</span></div>
                <div className="data-card-actions"><a href={s.profile_url} className="btn btn-primary btn-sm w-100"><i aria-hidden="true" className="fas fa-eye" /> View Profile</a></div>
              </div>
            ))}
          </div></div></div>
      </>) : <div className="card"><div className="card-body"><Empty icon="fa-graduation-cap" title="No Graduates">
        <p>{d.session_id ? 'No graduates found for this session' : 'No students have been marked as graduated yet'}</p></Empty></div></div>}
    </>
  );
}

// ---- Graduate preview ------------------------------------------------------
function GraduatePreview({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    if (!await confirm(`Mark these ${d.students.length} SSS3 student(s) as graduates?`)) return;
    setBusy(true);
    const r = await submitJson(d.confirm_url, {});
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not graduate students.');
  };
  return (
    <>
      <PageHeader title={<><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate SSS3 — Review</>}
        actions={<a href={d.urls.graduates} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>} />
      <div className="card"><div className="card-header"><h3>Will be graduated ({d.students.length})</h3></div>
        <div className="card-body">
          {d.students.length ? (<>
            <div className="table-container" style={{ border: 'none' }}><table className="data-table">
              <thead><tr><th>#</th><th>Student ID</th><th>Name</th><th>Gender</th></tr></thead>
              <tbody>{d.students.map((s, i) => <tr key={i}><td>{i + 1}</td><td>{s.student_id}</td><td>{s.full_name}</td><td>{s.gender}</td></tr>)}</tbody>
            </table></div>
            <button type="button" className="btn btn-primary" style={{ marginTop: '1rem' }} disabled={busy} onClick={confirm}>
              <i aria-hidden="true" className="fas fa-user-graduate" /> Confirm — graduate {d.students.length} student(s)</button>
          </>) : <Empty icon="fa-circle-check" title=""><p>No new SSS3 students to graduate — they're all already graduated, or no SSS3 class is set up for the active term.</p></Empty>}
          {d.already_count > 0 && <p className="text-muted text-sm" style={{ marginTop: '1rem' }}><i aria-hidden="true" className="fas fa-info-circle" /> {d.already_count} SSS3 student(s) are already graduates and will be skipped.</p>}
        </div></div>
    </>
  );
}

// ---- Graduate profile ------------------------------------------------------
function GraduateProfile({ d }) {
  const s = d.student;
  return (
    <>
      <div className="profile-header">
        <div className="profile-avatar"><i aria-hidden="true" className="fas fa-user-graduate" /></div>
        <div className="profile-info"><h1>{s.full_name}</h1><p>{s.student_id} • {s.gender}</p>
          {d.graduation_session && <p><i aria-hidden="true" className="fas fa-graduation-cap" /> Class of {d.graduation_session}</p>}</div>
      </div>
      <div className="page-header-actions mb-3">
        <a href={d.urls.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>
        <a href={d.urls.full_profile} className="btn btn-primary"><i aria-hidden="true" className="fas fa-user" /> Full Profile</a>
      </div>
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-graduation-cap" /> Graduation Info</h3></div>
        <div className="card-body"><div className="info-grid">
          <div className="info-row"><span className="text-muted">Status</span><strong><span className="badge badge-success">Graduated</span></strong></div>
          {d.graduation_date && <div className="info-row"><span className="text-muted">Graduation Date</span><strong>{d.graduation_date}</strong></div>}
          {d.graduation_session && <div className="info-row"><span className="text-muted">Session</span><strong>{d.graduation_session}</strong></div>}
        </div></div></div>

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-alt" /> WAEC Results</h3>
        <a href={d.urls.add_waec} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a></div>
        <div className="card-body">{d.waec_by_year.length ? d.waec_by_year.map((data, i) => (
          <div className="card" style={{ marginBottom: '1rem' }} key={i}>
            <div className="card-header"><span><strong>{data.exam_year}</strong></span>{data.exam_number && <span className="text-muted">Exam No: {data.exam_number}</span>}</div>
            <div className="card-body"><div className="subjects-grid">{data.subjects.map((r, j) => (
              <div className="subject-item" key={j}><span>{r.subject}</span><span className={'grade-badge grade-' + r.grade}>{r.grade}</span></div>))}</div></div>
          </div>
        )) : <Empty icon="fa-file-alt" title=""><p>No WAEC results recorded</p><a href={d.urls.add_waec} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add WAEC Result</a></Empty>}</div></div>

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-contract" /> JAMB Results</h3>
        <a href={d.urls.add_jamb} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a></div>
        <div className="card-body">{d.jamb_results.length ? d.jamb_results.map((j, i) => (
          <div className="card" style={{ marginBottom: '1rem' }} key={i}>
            <div className="card-header"><span><strong>{j.exam_year}</strong></span><span className="badge badge-primary" style={{ fontSize: '1rem' }}>{j.total_score}</span></div>
            <div className="card-body">{j.registration_number && <p className="text-muted mb-2">Reg No: {j.registration_number}</p>}
              <div className="jamb-subjects">{j.subjects.map((sub, k) => (
                <div className="subject-item" key={k}><span>{sub.name}</span><strong>{sub.score}</strong></div>))}</div></div>
          </div>
        )) : <Empty icon="fa-file-contract" title=""><p>No JAMB results recorded</p><a href={d.urls.add_jamb} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add JAMB Result</a></Empty>}</div></div>

      {d.contacts.length > 0 && (
        <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-phone" /> Contact Information</h3></div>
          <div className="card-body"><div className="data-cards" style={{ padding: 0 }}>
            {d.contacts.map((c, i) => (
              <div className="data-card" key={i}>
                <div className="data-card-header"><div className="data-card-title">{c.name}</div><span className="badge badge-secondary">{c.relationship}</span></div>
                <div className="data-card-row"><span className="data-card-label">Phone</span><span>{c.phone}</span></div>
              </div>
            ))}
          </div></div></div>
      )}
    </>
  );
}

// ---- History ---------------------------------------------------------------
function History({ d }) {
  const nav = useNav();
  const count = (st) => d.records.filter((r) => r.status === st).length;
  return (
    <>
      <PageHeader title="Promotion History" />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Session</label>
          <select className="form-control" value={d.session_id} onChange={(e) => navParams(nav.go, window.location.pathname, { session_id: e.target.value })}>
            <option value="">Select Session</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
      </div></div></div>
      {d.records.length ? (<>
        <div className="stats-grid mb-3">
          <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-arrow-up" /></div><div className="stat-content"><h3>{count('promoted')}</h3><p>Promoted</p></div></div>
          <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-redo" /></div><div className="stat-content"><h3>{count('repeated')}</h3><p>Repeated</p></div></div>
          <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-graduation-cap" /></div><div className="stat-content"><h3>{count('graduated')}</h3><p>Graduated</p></div></div>
        </div>
        <div className="card"><div className="card-header"><h3>Records ({d.records.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="data-cards" style={{ padding: '1rem' }}>
            {d.records.map((r, i) => (
              <div className="data-card" key={i}>
                <div className="data-card-header"><div className="data-card-title">{r.name}</div><span className={'badge ' + r.status_badge}>{r.status}</span></div>
                <div className="data-card-row"><span className="data-card-label">From</span><span>{r.from_class}</span></div>
                <div className="data-card-row"><span className="data-card-label">To</span><span>{r.to_class}</span></div>
                {r.stream && <div className="data-card-row"><span className="data-card-label">Stream</span><span>{r.stream}</span></div>}
                {r.average != null && <div className="data-card-row"><span className="data-card-label">Average</span><span>{r.average}%</span></div>}
                {r.is_manual && <div className="data-card-row"><span className="data-card-label">Type</span><span className="badge badge-info">Manual</span></div>}
              </div>
            ))}
          </div></div></div>
      </>) : (d.session_id
        ? <div className="card"><div className="card-body"><Empty icon="fa-history" title="No Records"><p>No promotion records for this session</p></Empty></div></div>
        : <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select a Session"><p>Choose a session to view promotion history</p></Empty></div></div>)}
    </>
  );
}

const SCREENS = { index: Index, rules: Rules, add_rule: AddRule, process: Process,
  graduates: Graduates, graduate_preview: GraduatePreview, graduate_profile: GraduateProfile, history: History };

export default function PromotionApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  // Remount the Process screen whenever its student set changes (new class/
  // session), so row state is re-derived instead of going stale — otherwise
  // rows[i] is undefined for the new list and the render crashes.
  const screenKey = d.page === 'process'
    ? 'process:' + (d.students || []).map((s) => s.id).join('-')
    : d.page;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen key={screenKey} d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
