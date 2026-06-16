import React, { useState, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { Banner, PageHeader, Empty, SectionShell } from '../components/ui';

const ORD = { 1: '1st', 2: '2nd', 3: '3rd', 4: '4th' };

// ---- Index -----------------------------------------------------------------
function Index({ d }) {
  const nav = useNav();
  const ref = useRef();
  useEffect(() => {
    if (!ref.current || !window.Chart || d.comparison.length < 2) return;
    const cs = getComputedStyle(document.body);
    window.Chart.defaults.color = cs.getPropertyValue('--text-secondary') || '#666';
    const chart = new window.Chart(ref.current, {
      type: 'bar',
      data: { labels: d.comparison.map((c) => c.label), datasets: [
        { label: 'Average Score', data: d.comparison.map((c) => c.average), backgroundColor: '#4e73df', borderRadius: 6 },
        { label: 'Students ≥250', data: d.comparison.map((c) => c.above_250), backgroundColor: '#1cc88a', borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } },
        scales: { y: { beginAtZero: true }, x: { grid: { display: false } } } },
    });
    return () => chart.destroy();
  }, [d.comparison]);

  const st = d.stats;
  const stats = [['primary', 'fa-clipboard-list', st.count, 'Mock Exams'],
    ['success', 'fa-users', st.total_results, 'Total Results'],
    ['info', 'fa-chart-bar', st.avg_score ?? '-', 'Avg Score'],
    ['warning', 'fa-calendar-plus', st.remaining, 'Exams Remaining']];

  return (
    <>
      <div className="mb-4"><div className="d-flex justify-between align-center flex-wrap gap-2">
        <div><h1>Mock JAMB Examinations</h1><p className="text-muted text-sm mt-1">Track and analyze mock JAMB performance</p></div>
        <div className="d-flex gap-2">
          <a href={d.urls.create} className="btn btn-primary"><i className="fas fa-plus" /> Create Exam</a>
          <a href={d.urls.analytics} className="btn btn-outline"><i className="fas fa-chart-line" /> Analytics</a>
          <a href={d.urls.predictions} className="btn btn-info"><i className="fas fa-crystal-ball" /> Predictions</a>
        </div>
      </div></div>

      <div className="card mb-4"><div className="card-body">
        <div className="d-flex gap-2 flex-wrap align-center">
          <label className="form-label mb-0">Academic Session:</label>
          <select className="form-control" style={{ maxWidth: 200 }} value={d.selected_session_id}
                  onChange={(e) => navParams(nav.go, d.urls.self, { session_id: e.target.value })}>
            {d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      </div></div>

      {d.exams.length > 0 && (
        <div className="stats-grid mb-4">{stats.map(([t, ic, v, l]) => (
          <div className="stat-card" key={l}><div className={'stat-icon ' + t}><i className={'fas ' + ic} /></div>
            <div className="stat-content"><h3>{v}</h3><p>{l}</p></div></div>))}</div>
      )}

      {d.comparison.length > 1 && (
        <div className="card mb-4"><div className="card-header"><h3 className="card-title">Performance Comparison</h3></div>
          <div className="card-body"><div style={{ height: 300 }}><canvas ref={ref} /></div></div></div>
      )}

      <div className="card"><div className="card-header"><h3 className="card-title">Mock Examinations</h3></div>
        <div className="card-body">
          {d.exams.length ? (
            <div className="grid grid-2 gap-3">{d.exams.map((e) => (
              <div className="card" style={{ borderLeft: '4px solid var(--primary)' }} key={e.id}><div className="card-body">
                <div className="d-flex justify-between align-center mb-2"><h4 className="mb-0">{e.display_name}</h4>
                  <span className={'badge ' + (e.is_completed ? 'badge-success' : 'badge-warning')}>{e.is_completed ? 'Completed' : 'In Progress'}</span></div>
                <p className="text-muted text-sm mb-3"><i className="fas fa-calendar" /> {e.exam_date}</p>
                <div className="grid grid-3 gap-2 mb-3">
                  {[[e.student_count, 'Students'], [e.average_score ?? '-', 'Avg Score'], [e.above_200, '≥200']].map(([v, l], i) => (
                    <div className="text-center p-2" style={{ background: 'var(--bg-hover)', borderRadius: 'var(--border-radius-sm)' }} key={i}>
                      <div className="font-bold">{v}</div><div className="text-xs text-muted">{l}</div></div>))}
                </div>
                <div className="d-flex gap-2 flex-wrap">
                  <a href={e.view_url} className="btn btn-sm btn-primary"><i className="fas fa-eye" /> View</a>
                  <a href={e.add_url} className="btn btn-sm btn-outline"><i className="fas fa-plus" /> Add Results</a>
                  <a href={e.bulk_url} className="btn btn-sm btn-outline"><i className="fas fa-list" /> Bulk Entry</a>
                </div>
              </div></div>
            ))}</div>
          ) : <Empty icon="fa-clipboard-list" title="No mock exams created yet"><a href={d.urls.create} className="btn btn-primary mt-2">Create First Exam</a></Empty>}
        </div></div>
    </>
  );
}

// ---- Create exam -----------------------------------------------------------
function CreateExam({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ session_id: '', exam_number: '', exam_date: '', name: '', description: '' });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const taken = (d.existing_exams[f.session_id] || []);
  const submit = async (e) => {
    e.preventDefault();
    if (!f.session_id || !f.exam_number || !f.exam_date) { notify('error', 'Please fill all required fields.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not create the exam.');
  };
  return (
    <>
      <div className="mb-4"><h1>Create Mock JAMB Exam</h1><p className="text-muted text-sm">Set up a new mock examination</p></div>
      <div className="card" style={{ maxWidth: 600 }}><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Academic Session <span className="text-danger">*</span></label>
          <select className="form-control" required value={f.session_id} onChange={(e) => set('session_id', e.target.value)}>
            <option value="">Select Session</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Exam Number <span className="text-danger">*</span></label>
          <select className="form-control" required value={f.exam_number} onChange={(e) => set('exam_number', e.target.value)}>
            <option value="">Select Exam Number</option>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n} disabled={taken.includes(n)}>{ORD[n]} Mock JAMB</option>)}</select>
          {taken.length > 0 && <small className="text-muted">Already created: {taken.map((n) => ORD[n]).join(', ')} Mock</small>}</div>
        <div className="form-group"><label className="form-label">Exam Date <span className="text-danger">*</span></label>
          <input type="date" className="form-control" required value={f.exam_date} onChange={(e) => set('exam_date', e.target.value)} /></div>
        <div className="form-group"><label className="form-label">Custom Name (Optional)</label>
          <input type="text" className="form-control" placeholder="Leave blank for auto-generated name" value={f.name} onChange={(e) => set('name', e.target.value)} /></div>
        <div className="form-group"><label className="form-label">Description (Optional)</label>
          <textarea className="form-control" rows="3" placeholder="Any notes about this exam..." value={f.description} onChange={(e) => set('description', e.target.value)} /></div>
        <div className="d-flex gap-2 mt-4">
          <button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-plus" /> Create Exam</button>
          <a href={d.urls.index} className="btn btn-secondary">Cancel</a></div>
      </form></div></div>
    </>
  );
}

// ---- Edit exam -------------------------------------------------------------
function EditExam({ d, notify }) {
  const nav = useNav();
  const e0 = d.exam;
  const [f, setF] = useState({ name: e0.name, exam_date: e0.exam_date, description: e0.description, is_completed: e0.is_completed });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (ev) => {
    ev.preventDefault(); setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, is_completed: f.is_completed ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const del = async () => {
    if (!window.confirm('Are you sure you want to delete this exam and ALL its results? This cannot be undone!')) return;
    const r = await submitJson(d.delete_url, {});
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <div className="mb-4"><h1>Edit Mock Exam</h1><p className="text-muted">{e0.display_name} - {e0.session_name}</p></div>
      <div className="card" style={{ maxWidth: 600 }}><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-group"><label className="form-label">Exam Name <span className="text-danger">*</span></label>
            <input type="text" className="form-control" required value={f.name} onChange={(e) => set('name', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Exam Date <span className="text-danger">*</span></label>
            <input type="date" className="form-control" required value={f.exam_date} onChange={(e) => set('exam_date', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Description</label>
            <textarea className="form-control" rows="3" value={f.description} onChange={(e) => set('description', e.target.value)} /></div>
          <div className="form-check mb-4"><input type="checkbox" className="form-check-input" id="ic" checked={f.is_completed} onChange={(e) => set('is_completed', e.target.checked)} />
            <label htmlFor="ic" className="form-check-label"> Mark as Completed</label></div>
          <div className="d-flex gap-2"><button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> Save Changes</button>
            <a href={d.view_url} className="btn btn-secondary">Cancel</a></div>
        </form>
        <hr className="my-4" />
        <div className="text-danger"><h4>Danger Zone</h4>
          <p className="text-sm">Deleting this exam will also delete all student results. This cannot be undone.</p>
          <button type="button" className="btn btn-danger" onClick={del}><i className="fas fa-trash" /> Delete Exam</button></div>
      </div></div>
    </>
  );
}

// ---- Edit result -----------------------------------------------------------
function EditResult({ d, notify }) {
  const nav = useNav();
  const r0 = d.result;
  const [f, setF] = useState({
    subject1: r0.subject1, subject1_score: r0.subject1_score, subject2: r0.subject2, subject2_score: r0.subject2_score,
    subject3: r0.subject3, subject3_score: r0.subject3_score, subject4: r0.subject4, subject4_score: r0.subject4_score,
    total_score: r0.total_score,
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => {
    const n = { ...s, [k]: v };
    if (k.endsWith('_score') && k !== 'total_score') {
      n.total_score = [1, 2, 3, 4].reduce((t, i) => t + (parseInt(n['subject' + i + '_score']) || 0), 0);
    }
    return n;
  });
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const del = async () => {
    if (!window.confirm('Delete this result?')) return;
    const r = await submitJson(d.delete_url, {});
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <div className="mb-4"><h1>Edit Result</h1><p className="text-muted">{r0.student_name} - {r0.exam_name}</p></div>
      <div className="card" style={{ maxWidth: 700 }}><div className="card-body">
        <form onSubmit={submit}>
          <div className="mb-3 p-3" style={{ background: 'var(--gray-100)', borderRadius: 'var(--radius-md)' }}>
            <strong>Student:</strong> {r0.student_name} ({r0.student_id})</div>
          <h4 className="mb-3">Subject Scores</h4>
          {[1, 2, 3, 4].map((i) => (
            <div className="form-row" key={i}>
              <div className="form-group" style={{ flex: 2 }}><label className="form-label">Subject {i}</label>
                <select className="form-control" value={f['subject' + i]} onChange={(e) => set('subject' + i, e.target.value)}>
                  <option value="">—</option>{d.subjects.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
              <div className="form-group"><label className="form-label">Score</label>
                <input type="number" min="0" max="100" className="form-control" value={f['subject' + i + '_score']}
                       onChange={(e) => set('subject' + i + '_score', e.target.value)} /></div>
            </div>
          ))}
          <hr className="my-4" />
          <div className="form-group"><label className="form-label">Total Score <span className="text-danger">*</span></label>
            <input type="number" min="0" max="400" required className="form-control" value={f.total_score} onChange={(e) => set('total_score', e.target.value)} /></div>
          <div className="d-flex gap-2 mt-4"><button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> Save Changes</button>
            <a href={d.view_url} className="btn btn-secondary">Cancel</a></div>
        </form>
        <hr className="my-4" />
        <button type="button" className="btn btn-danger btn-sm" onClick={del}><i className="fas fa-trash" /> Delete Result</button>
      </div></div>
    </>
  );
}

// ---- Bulk entry ------------------------------------------------------------
function BulkEntry({ d, notify }) {
  const nav = useNav();
  const [scores, setScores] = useState(() => {
    const m = {}; d.students.forEach((s) => { m[s.id] = s.total_score === '' ? '' : String(s.total_score); }); return m;
  });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const fields = {};
    d.students.forEach((s) => { if (scores[s.id] !== '') fields['score_' + s.id] = scores[s.id]; });
    const r = await submitJson(d.submit_url, fields);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save results.');
  };
  return (
    <>
      <div className="mb-4"><div className="d-flex justify-between align-center flex-wrap gap-2">
        <div><h1>Bulk Entry</h1><p className="text-muted">{d.exam.display_name} - Enter scores for multiple students</p></div>
        <a href={d.urls.view} className="btn btn-secondary"><i className="fas fa-arrow-left" /> Back</a>
      </div></div>
      {d.students.length ? (
        <form onSubmit={submit}><div className="card">
          <div className="card-header"><h3 className="card-title">SSS3 Students ({d.students.length})</h3></div>
          <div className="card-body"><div className="table-responsive"><table className="table data-table">
            <thead><tr><th>Student</th><th>Arm</th><th>Total Score</th><th>Status</th></tr></thead>
            <tbody>{d.students.map((s) => (
              <tr key={s.id}>
                <td><strong>{s.full_name}</strong><div className="text-xs text-muted">{s.student_id}</div></td>
                <td>{s.arm}</td>
                <td><input type="number" className="form-control" style={{ width: 100 }} min="0" max="400" placeholder="0-400"
                           value={scores[s.id]} onChange={(e) => setScores((m) => ({ ...m, [s.id]: e.target.value }))} /></td>
                <td><span className={'badge ' + (s.entered ? 'badge-success' : 'badge-secondary')}>{s.entered ? 'Entered' : 'Pending'}</span></td>
              </tr>
            ))}</tbody>
          </table></div>
          <div className="mt-4"><button type="submit" className="btn btn-primary btn-lg" disabled={busy}><i className="fas fa-save" /> Save All Results</button></div>
          </div></div>
        </form>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-users" title="">
          <p>No SSS3 students found for the current term.</p>
          <p className="text-sm text-muted">Make sure students are enrolled in SSS3 for the active term.</p>
          <a href={d.urls.add} className="btn btn-primary">Add Individual Result</a></Empty></div></div>
      )}
    </>
  );
}

// ---- Add result ------------------------------------------------------------
function AddResult({ d, notify }) {
  const nav = useNav();
  const qFor = (subj) => d.question_counts[subj] || 40;
  const [studentId, setStudentId] = useState('');
  const [rows, setRows] = useState([{ subject: d.compulsory_subject, correct: '' }, { subject: '', correct: '' },
    { subject: '', correct: '' }, { subject: '', correct: '' }]);
  const [addAnother, setAddAnother] = useState(false);
  const [busy, setBusy] = useState(false);

  const scoreOf = (r) => {
    if (r.correct === '' || r.correct == null) return null;
    const q = qFor(r.subject);
    return Math.round((Math.max(0, Math.min(parseInt(r.correct, 10) || 0, q)) / q) * 100);
  };
  const total = rows.reduce((t, r) => t + (scoreOf(r) || 0), 0);
  const setRow = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  const onStudent = (v) => {
    setStudentId(v);
    const saved = (d.subject_map[v] || {}).jamb || [];
    if (saved.length) setRows((rs) => rs.map((r, i) => ({ ...r, subject: saved[i] || r.subject })));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!studentId) { notify('error', 'Please select a student.'); return; }
    setBusy(true);
    const fields = { student_id: studentId, total_score: total, add_another: addAnother ? 'on' : '' };
    rows.forEach((r, i) => { fields['subject' + (i + 1)] = r.subject; fields['subject' + (i + 1) + '_correct'] = r.correct; });
    const res = await submitJson(d.submit_url, fields);
    setBusy(false);
    if (res.ok) nav.go(res.redirect); else notify('error', res.error || 'Could not add the result.');
  };

  if (!d.students.length) {
    return (<>
      <PageHeader title="Add Result" />
      <div className="card" style={{ maxWidth: 760 }}><div className="card-body"><Empty icon="fa-user-slash" title="">
        <p>All students already have results for this exam</p>
        <a href={d.view_url} className="btn btn-primary">View Results</a></Empty></div></div>
    </>);
  }
  return (
    <>
      <PageHeader title="Add Result" actions={<a href={d.view_url} className="btn btn-secondary btn-sm"><i className="fas fa-arrow-left" /> Back</a>} />
      <div className="card" style={{ maxWidth: 760 }}><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Student <span className="text-danger">*</span></label>
          <select className="form-control" required value={studentId} onChange={(e) => onStudent(e.target.value)}>
            <option value="">Select Student</option>{d.students.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}</select></div>
        <hr className="my-4" /><h4 className="mb-2">Subject Scores</h4>
        <div className="entry-hint"><i className="fas fa-circle-info" />
          <span>Enter the number of <strong>correct answers</strong> for each subject. We convert it to a score over 100 automatically — English is marked over 60 questions, every other subject over 40.</span></div>
        {rows.map((r, i) => {
          const q = qFor(r.subject); const sc = scoreOf(r);
          return (
            <div className="subject-row" key={i}>
              <div className="field"><label>Subject {i + 1}{i === 0 && <span className="text-danger"> *</span>}</label>
                <select className="form-control" required={i === 0} value={r.subject} onChange={(e) => setRow(i, 'subject', e.target.value)}>
                  <option value="">Select Subject</option>{d.subjects.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
              <div className="field"><label>Correct <span className="qcount">(/{q})</span></label>
                <input type="number" className="form-control" min="0" max={q} placeholder="0" value={r.correct} onChange={(e) => setRow(i, 'correct', e.target.value)} /></div>
              <div className="field"><label>Score /100</label>
                <div className={'converted' + (sc == null ? ' empty' : '')}>{sc == null ? '—' : sc}</div></div>
            </div>
          );
        })}
        <div className="total-box"><div><div className="total-label">Total Score</div>
          <div><span className="total-value">{total}</span> <span className="total-max">/ {d.max_total}</span></div></div>
          <i className="fas fa-calculator" style={{ fontSize: '1.75rem', opacity: 0.6 }} /></div>
        <div className="form-check mb-4"><input type="checkbox" className="form-check-input" id="aa" checked={addAnother} onChange={(e) => setAddAnother(e.target.checked)} />
          <label htmlFor="aa" className="form-check-label"> Add another result after saving</label></div>
        <div className="d-flex gap-2"><button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> Save Result</button>
          <a href={d.view_url} className="btn btn-secondary">Cancel</a></div>
      </form></div></div>
    </>
  );
}

const SCREENS = { index: Index, create_exam: CreateExam, edit_exam: EditExam, edit_result: EditResult,
  bulk_entry: BulkEntry, add_result: AddResult };

export default function MockJambApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
