import React, { useState, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, PageHeader, Empty, SectionShell } from '../components/ui';

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
          <a href={d.urls.create} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Create Exam</a>
          {d.urls.bank && <a href={d.urls.bank} className="btn btn-outline" data-native><i aria-hidden="true" className="fas fa-database" /> Question Bank</a>}
          <a href={d.urls.analytics} className="btn btn-outline"><i aria-hidden="true" className="fas fa-chart-line" /> Analytics</a>
          {d.urls.trends && <a href={d.urls.trends} className="btn btn-outline"><i aria-hidden="true" className="fas fa-chart-line" /> Progress Trends</a>}
          {d.urls.validation && <a href={d.urls.validation} className="btn btn-outline"><i aria-hidden="true" className="fas fa-bullseye" /> Validation</a>}
          <a href={d.urls.predictions} className="btn btn-info"><i aria-hidden="true" className="fas fa-crystal-ball" /> Predictions</a>
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
          <div className="stat-card" key={l}><div className={'stat-icon ' + t}><i aria-hidden="true" className={'fas ' + ic} /></div>
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
                <p className="text-muted text-sm mb-3"><i aria-hidden="true" className="fas fa-calendar" /> {e.exam_date}</p>
                <div className="grid grid-3 gap-2 mb-3">
                  {[[e.student_count, 'Students'], [e.average_score ?? '-', 'Avg Score'], [e.above_200, '≥200']].map(([v, l], i) => (
                    <div className="text-center p-2" style={{ background: 'var(--bg-hover)', borderRadius: 'var(--border-radius-sm)' }} key={i}>
                      <div className="font-bold">{v}</div><div className="text-xs text-muted">{l}</div></div>))}
                </div>
                <div className="d-flex gap-2 flex-wrap">
                  <a href={e.view_url} className="btn btn-sm btn-primary"><i aria-hidden="true" className="fas fa-eye" /> View</a>
                  <a href={e.add_url} className="btn btn-sm btn-outline"><i aria-hidden="true" className="fas fa-plus" /> Add Results</a>
                  <a href={e.bulk_url} className="btn btn-sm btn-outline"><i aria-hidden="true" className="fas fa-list" /> Bulk Entry</a>
                  {e.deep_url && <a href={e.deep_url} className="btn btn-sm btn-info"><i aria-hidden="true" className="fas fa-brain" /> Deep</a>}
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
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-plus" /> Create Exam</button>
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
    if (!await confirm('Are you sure you want to delete this exam and ALL its results? This cannot be undone!')) return;
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
          <div className="d-flex gap-2"><button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Changes</button>
            <a href={d.view_url} className="btn btn-secondary">Cancel</a></div>
        </form>
        <hr className="my-4" />
        <div className="text-danger"><h4>Danger Zone</h4>
          <p className="text-sm">Deleting this exam will also delete all student results. This cannot be undone.</p>
          <button type="button" className="btn btn-danger" onClick={del}><i aria-hidden="true" className="fas fa-trash" /> Delete Exam</button></div>
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
    if (!await confirm('Delete this result?')) return;
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
          <div className="d-flex gap-2 mt-4"><button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Changes</button>
            <a href={d.view_url} className="btn btn-secondary">Cancel</a></div>
        </form>
        <hr className="my-4" />
        <button type="button" className="btn btn-danger btn-sm" onClick={del}><i aria-hidden="true" className="fas fa-trash" /> Delete Result</button>
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
        <a href={d.urls.view} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>
      </div></div>
      {d.students.length ? (
        <form onSubmit={submit}><div className="card">
          <div className="card-header"><h3 className="card-title">SSS3 Students ({d.students.length})</h3></div>
          <div className="card-body"><div className="table-responsive"><table className="table data-table">
            <thead><tr><th>Student</th><th>Arm</th><th>Total Score</th><th>Status</th></tr></thead>
            <tbody>{d.students.map((s) => (
              <tr key={s.id}>
                <td><strong>{s.full_name}</strong><div className="text-xs text-muted">{s.student_id}</div></td>
                <td>{s.arm || '—'}</td>
                <td><input type="number" className="form-control" style={{ width: 100 }} min="0" max="400" placeholder="0-400"
                           value={scores[s.id]} onChange={(e) => setScores((m) => ({ ...m, [s.id]: e.target.value }))} /></td>
                <td><span className={'badge ' + (s.entered ? 'badge-success' : 'badge-secondary')}>{s.entered ? 'Entered' : 'Pending'}</span></td>
              </tr>
            ))}</tbody>
          </table></div>
          <div className="mt-4"><button type="submit" className="btn btn-primary btn-lg" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save All Results</button></div>
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
      <PageHeader title="Add Result" actions={<a href={d.view_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>} />
      <div className="card" style={{ maxWidth: 760 }}><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Student <span className="text-danger">*</span></label>
          <select className="form-control" required value={studentId} onChange={(e) => onStudent(e.target.value)}>
            <option value="">Select Student</option>{d.students.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}</select></div>
        <hr className="my-4" /><h4 className="mb-2">Subject Scores</h4>
        <div className="entry-hint"><i aria-hidden="true" className="fas fa-circle-info" />
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
          <i aria-hidden="true" className="fas fa-calculator" style={{ fontSize: 'var(--text-2xl)', opacity: 0.6 }} /></div>
        <div className="form-check mb-4"><input type="checkbox" className="form-check-input" id="aa" checked={addAnother} onChange={(e) => setAddAnother(e.target.checked)} />
          <label htmlFor="aa" className="form-check-label"> Add another result after saving</label></div>
        <div className="d-flex gap-2"><button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Result</button>
          <a href={d.view_url} className="btn btn-secondary">Cancel</a></div>
      </form></div></div>
    </>
  );
}

// ---- View exam -------------------------------------------------------------
const r1 = (n) => Math.round((n || 0) * 10) / 10;
const scoreColor = (s) => (s >= 300 ? 'var(--success)' : s >= 250 ? 'var(--info)' : s >= 200 ? 'var(--warning)' : 'var(--danger)');
const rankClass = (r) => (r === 1 ? ' gold' : r === 2 ? ' silver' : r === 3 ? ' bronze' : '');

function ViewExam({ d, notify }) {
  const nav = useNav();
  const distRef = useRef();
  const subjRef = useRef();
  const st = d.statistics;
  const [filters, setFilters] = useState(d.filters);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!st || !distRef.current || !window.Chart) return;
    const dist = st.distribution;
    const chart = new window.Chart(distRef.current, {
      type: 'doughnut',
      data: { labels: ['300-400', '250-299', '200-249', '180-199', '0-179'],
        datasets: [{ data: [dist['300-400'], dist['250-299'], dist['200-249'], dist['180-199'], dist['0-179']],
          backgroundColor: ['var(--success)', 'var(--info)', 'var(--warning)', '#fd7e14', 'var(--danger)'] }] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'right', labels: { boxWidth: 12, font: { size: 10 } } } } },
    });
    return () => chart.destroy();
  }, [st]);

  useEffect(() => {
    if (!st || !st.subject_analysis.length || !subjRef.current || !window.Chart) return;
    const subjects = st.subject_analysis.slice(0, 8);
    const chart = new window.Chart(subjRef.current, {
      type: 'bar',
      data: { labels: subjects.map((s) => s.subject.substring(0, 10)),
        datasets: [{ label: 'Average', data: subjects.map((s) => s.average),
          backgroundColor: subjects.map((s) => (s.average >= 70 ? 'var(--success)' : s.average >= 50 ? 'var(--warning)' : 'var(--danger)')) }] },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, max: 100 } } },
    });
    return () => chart.destroy();
  }, [st]);

  const applyFilters = (e) => {
    e.preventDefault();
    navParams(nav.go, d.urls.self, { search: filters.search, min_score: filters.min_score, max_score: filters.max_score });
  };
  const clearFilters = () => nav.go(d.urls.self);

  const delResult = async (url) => {
    if (!await confirm('Delete?')) return;
    const r = await submitJson(url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not delete.');
  };
  const delExam = async () => {
    if (!await confirm(`DELETE ${d.exam.display_name} and ALL results?`)) return;
    const r = await submitJson(d.urls.delete_exam, {});
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not delete.');
  };

  const doExport = async (opts) => {
    setExporting(false);
    const node = buildExportNode(d, st, opts);
    document.body.appendChild(node);
    try {
      const canvas = await window.html2canvas(node.firstChild, { scale: opts.quality, backgroundColor: '#ffffff' });
      setSaveImg(canvas.toDataURL('image/png'));
    } catch (err) {
      notify('error', 'Could not generate image.');
    } finally {
      document.body.removeChild(node);
    }
  };
  const [saveImg, setSaveImg] = useState(null);

  const actions = (
    <>
      <a href={d.urls.add} className="btn btn-primary btn-sm" title="Add"><i aria-hidden="true" className="fas fa-plus" /></a>
      <a href={d.urls.bulk} className="btn btn-info btn-sm" title="Bulk"><i aria-hidden="true" className="fas fa-list" /></a>
      <a href={d.urls.export} className="btn btn-success btn-sm" title="Excel" data-native download><i aria-hidden="true" className="fas fa-file-excel" /></a>
      {d.urls.questions && <a href={d.urls.questions} className="btn btn-primary btn-sm" title="Question bank (online sitting)" data-native><i aria-hidden="true" className="fas fa-pen-to-square" /></a>}
      {d.urls.items && <a href={d.urls.items} className="btn btn-info btn-sm" title="Item &amp; topic analysis (online sitting)" data-native><i aria-hidden="true" className="fas fa-microscope" /></a>}
      {d.urls.deep && <a href={d.urls.deep} className="btn btn-info btn-sm" title="Deep analytics"><i aria-hidden="true" className="fas fa-brain" /></a>}
      {d.results.length > 0 && <button onClick={() => setExporting(true)} className="btn btn-secondary btn-sm" title="HD Image"><i aria-hidden="true" className="fas fa-image" /></button>}
      <a href={d.urls.edit} className="btn btn-warning btn-sm" title="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>
      <a href={d.urls.index} className="btn btn-secondary btn-sm" title="Back"><i aria-hidden="true" className="fas fa-arrow-left" /></a>
    </>
  );

  return (
    <>
      <div className="page-header">
        <div><h1>{d.exam.display_name}</h1>
          <p className="text-muted text-sm"><i aria-hidden="true" className="fas fa-calendar" /> {d.exam.exam_date}{d.exam.session_name ? ` | ${d.exam.session_name}` : ''}</p></div>
        <div className="page-header-actions">{actions}</div>
      </div>

      {st && (<>
        <div className="stats-grid">
          <div className="mj-stat-card highlight"><div className="stat-value">{r1(st.statistics.average)}</div><div className="stat-label">Average</div></div>
          <div className="mj-stat-card"><div className="stat-value">{st.student_count}</div><div className="stat-label">Students</div></div>
          <div className="mj-stat-card"><div className="stat-value" style={{ color: 'var(--success)' }}>{st.statistics.max}</div><div className="stat-label">Highest</div></div>
          <div className="mj-stat-card"><div className="stat-value" style={{ color: 'var(--danger)' }}>{st.statistics.min}</div><div className="stat-label">Lowest</div></div>
        </div>
        <div className="stats-grid">
          <div className="mj-stat-card"><div className="stat-value" style={{ color: '#6f42c1' }}>{st.statistics.above_300}</div><div className="stat-label">Above 300</div></div>
          <div className="mj-stat-card"><div className="stat-value" style={{ color: '#007bff' }}>{st.statistics.above_250}</div><div className="stat-label">Above 250</div></div>
          <div className="mj-stat-card"><div className="stat-value" style={{ color: 'var(--info)' }}>{st.statistics.above_200}</div><div className="stat-label">Above 200</div></div>
          <div className="mj-stat-card"><div className="stat-value">{st.statistics.median}</div><div className="stat-label">Median</div></div>
        </div>
        <div className="charts-row">
          <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-pie" /> Distribution</h3></div><div className="chart-body"><canvas ref={distRef} /></div></div>
          {st.subject_analysis.length > 0 && <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-bar" /> Subjects</h3></div><div className="chart-body"><canvas ref={subjRef} /></div></div>}
        </div>
        {st.subject_analysis.length > 0 && (
          <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-book" /> Subject Analysis</h3></div>
            <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
              <table className="subject-table">
                <thead><tr><th style={{ textAlign: 'left' }}>Subject</th><th>Count</th><th>Avg</th><th>Max</th><th>Min</th><th>≥70</th><th>≥50</th></tr></thead>
                <tbody>{st.subject_analysis.map((s) => (
                  <tr key={s.subject}><td>{s.subject}</td><td>{s.count}</td>
                    <td style={{ color: s.average >= 70 ? 'var(--success)' : s.average >= 50 ? 'var(--warning)' : 'var(--danger)' }}><strong>{r1(s.average)}</strong></td>
                    <td style={{ color: 'var(--success)' }}>{s.max}</td><td style={{ color: 'var(--danger)' }}>{s.min}</td><td>{s.above_70}</td><td>{s.above_50}</td></tr>))}
                </tbody>
              </table>
            </div></div>
        )}
      </>)}

      <div className="card">
        <div className="card-header">
          <h3><i aria-hidden="true" className="fas fa-list-ol" /> Results ({d.results.length})</h3>
          <form onSubmit={applyFilters} className="filter-form">
            <input type="text" className="form-control" placeholder="Search name..." style={{ width: 140 }}
                   value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
            <input type="number" className="form-control" placeholder="Min" style={{ width: 70 }}
                   value={filters.min_score} onChange={(e) => setFilters((f) => ({ ...f, min_score: e.target.value }))} />
            <input type="number" className="form-control" placeholder="Max" style={{ width: 70 }}
                   value={filters.max_score} onChange={(e) => setFilters((f) => ({ ...f, max_score: e.target.value }))} />
            <button type="submit" className="btn btn-sm btn-primary" aria-label="Search"><i aria-hidden="true" className="fas fa-search" /></button>
            {d.has_filter && <button type="button" className="btn btn-sm btn-secondary" onClick={clearFilters}>Clear</button>}
          </form>
        </div>

        {d.results.length ? (<>
          <div className="students-list">
            {d.results.map((it) => (
              <div className="student-card" key={it.rank}>
                <div className="student-card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span className={'student-rank' + rankClass(it.rank)}>{it.rank}</span>
                    <div>
                      <div className="student-name">{it.student.full_name}</div>
                      <div className="student-id">{it.student.student_id}</div>
                      <a href={it.student.progress_url} className="progress-link"><i aria-hidden="true" className="fas fa-chart-line" /> View Progress</a>
                    </div>
                  </div>
                  <span className={'score-badge score-' + it.perf_class}>{it.performance_level}</span>
                </div>
                <div className="student-score" style={{ color: scoreColor(it.total_score) }}>{it.total_score}</div>
                <div className="student-subjects">
                  {it.subjects.filter(Boolean).map((s, i) => (
                    <div className="student-subject" key={i}><span>{s.name.substring(0, 10)}</span><strong>{s.score}</strong></div>))}
                </div>
                <div className="student-actions">
                  <a href={it.student.progress_url} className="btn btn-info btn-sm" title="Progress"><i aria-hidden="true" className="fas fa-chart-line" /></a>
                  <a href={it.edit_url} className="btn btn-warning btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>
                  <button type="button" className="btn btn-danger btn-sm" onClick={() => delResult(it.delete_url)}><i aria-hidden="true" className="fas fa-trash" /></button>
                </div>
              </div>
            ))}
          </div>

          <div className="desktop-table">
            <table>
              <thead><tr><th>Rank</th><th>Student</th><th>Score</th><th>S1</th><th>S2</th><th>S3</th><th>S4</th><th>Level</th><th>Actions</th></tr></thead>
              <tbody>{d.results.map((it) => (
                <tr key={it.rank}>
                  <td><span className={'student-rank' + rankClass(it.rank)} style={{ width: 24, height: 24, fontSize: 'var(--text-xs)' }}>{it.rank}</span></td>
                  <td><strong>{it.student.full_name}</strong><br /><small style={{ color: 'var(--text-muted)' }}>{it.student.student_id}</small><br />
                    <a href={it.student.progress_url} className="progress-link"><i aria-hidden="true" className="fas fa-chart-line" /> Progress</a></td>
                  <td><strong style={{ fontSize: 'var(--text-lg)', color: scoreColor(it.total_score) }}>{it.total_score}</strong></td>
                  {it.subjects.map((s, i) => (
                    <td key={i}>{s ? <><small>{s.name.substring(0, 8)}</small><br /><strong>{s.score}</strong></> : '-'}</td>))}
                  <td><span className={'score-badge score-' + it.perf_class}>{it.performance_level}</span></td>
                  <td><div style={{ display: 'flex', gap: '0.25rem' }}>
                    <a href={it.student.progress_url} className="btn btn-info btn-sm" title="Progress"><i aria-hidden="true" className="fas fa-chart-line" /></a>
                    <a href={it.edit_url} className="btn btn-warning btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>
                    <button type="button" className="btn btn-danger btn-sm" onClick={() => delResult(it.delete_url)}><i aria-hidden="true" className="fas fa-trash" /></button>
                  </div></td>
                </tr>))}
              </tbody>
            </table>
          </div>
        </>) : (
          <div className="card-body"><Empty icon="fa-clipboard-list" title="No Results">
            <p>{filters.search ? `No students found matching "${filters.search}"` : 'Add results for this exam'}</p>
            <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</a></Empty></div>
        )}
      </div>

      <div className="card mt-3" style={{ borderColor: 'var(--danger)' }}>
        <div className="card-header" style={{ background: 'rgba(220,53,69,0.1)' }}><h3 className="text-danger"><i aria-hidden="true" className="fas fa-exclamation-triangle" /> Danger Zone</h3></div>
        <div className="card-body"><p className="text-muted mb-3">Delete exam and all results permanently.</p>
          <button type="button" className="btn btn-danger" onClick={delExam}><i aria-hidden="true" className="fas fa-trash" /> Delete Exam</button></div>
      </div>

      {exporting && <ExportModal d={d} st={st} onClose={() => setExporting(false)} onGenerate={doExport} />}
      {saveImg && <SaveModal src={saveImg} onClose={() => setSaveImg(null)} />}
    </>
  );
}

function ExportModal({ onClose, onGenerate }) {
  const [opts, setOpts] = useState({ rank: true, studentId: true, subjects: true, level: false,
    summary: true, distribution: true, timestamp: true, quality: 3 });
  const set = (k, v) => setOpts((o) => ({ ...o, [k]: v }));
  const Check = ({ k, label }) => (
    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem', background: 'var(--gray-50)', borderRadius: 6, marginBottom: '0.5rem', cursor: 'pointer' }}>
      <input type="checkbox" checked={opts[k]} onChange={(e) => set(k, e.target.checked)} /><span style={{ fontSize: 'var(--text-sm)' }}>{label}</span></label>
  );
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 9999, padding: '1rem', overflowY: 'auto' }}>
      <div style={{ background: 'var(--bg-card)', borderRadius: 12, maxWidth: 400, margin: '2rem auto', maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: 'var(--text-lg)' }}><i aria-hidden="true" className="fas fa-image" /> Export HD Image</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 'var(--text-2xl)', cursor: 'pointer', color: 'var(--text-muted)' }}>&times;</button>
        </div>
        <div style={{ padding: '1rem' }}>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginBottom: '1rem' }}>Select columns:</p>
          <div style={{ marginBottom: '1rem' }}>
            <Check k="rank" label="Rank" /><Check k="studentId" label="Student ID" /><Check k="subjects" label="Subject Scores" /><Check k="level" label="Performance Level" /></div>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Stats to include:</p>
          <div style={{ marginBottom: '1rem' }}>
            <Check k="summary" label="Summary Stats" /><Check k="distribution" label="Score Distribution" /><Check k="timestamp" label="Timestamp" /></div>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Quality:</p>
          <select value={opts.quality} onChange={(e) => set('quality', parseInt(e.target.value, 10))}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: 6, marginBottom: '1rem' }}>
            <option value="2">Standard (2x)</option><option value="3">HD (3x)</option><option value="4">Ultra HD (4x)</option>
          </select>
          <button onClick={() => onGenerate(opts)} className="btn btn-primary" style={{ width: '100%' }}><i aria-hidden="true" className="fas fa-download" /> Generate Image</button>
        </div>
      </div>
    </div>
  );
}

function SaveModal({ src, onClose }) {
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.8)', zIndex: 10000, padding: '1rem', overflowY: 'auto' }}>
      <div style={{ maxWidth: '100%', margin: '1rem auto', textAlign: 'center' }}>
        <p style={{ color: 'white', marginBottom: '1rem' }}>Long-press image to save</p>
        <img src={src} alt="Results export" style={{ maxWidth: '100%', borderRadius: 8, boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }} />
        <div><button onClick={onClose} style={{ marginTop: '1rem', padding: '0.75rem 2rem', background: 'white', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer' }}>Close</button></div>
      </div>
    </div>
  );
}

// Build an off-screen node for html2canvas to snapshot (ported from the Jinja version).
function buildExportNode(d, st, o) {
  const wrap = document.createElement('div');
  wrap.style.cssText = 'position:absolute;left:-9999px;width:500px;';
  const dist = (st && st.distribution) || {};
  const stats = (st && st.statistics) || {};
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  let thead = '<tr style="background:#11998e;color:white;">';
  if (o.rank) thead += '<th style="padding:6px;text-align:center;">#</th>';
  thead += '<th style="padding:6px;">Name</th>';
  if (o.studentId) thead += '<th style="padding:6px;">ID</th>';
  thead += '<th style="padding:6px;text-align:center;">Score</th>';
  if (o.subjects) thead += '<th style="padding:6px;text-align:center;">Subjects</th>';
  if (o.level) thead += '<th style="padding:6px;text-align:center;">Level</th>';
  thead += '</tr>';

  let tbody = '';
  d.results.forEach((r, i) => {
    const bg = i % 2 === 0 ? '#fff' : '#f8f9fa';
    const sc = scoreColor(r.total_score);
    const subs = r.subjects.filter(Boolean);
    tbody += `<tr style="background:${bg};">`;
    if (o.rank) tbody += `<td style="padding:5px;text-align:center;font-weight:bold;">${r.rank}</td>`;
    tbody += `<td style="padding:5px;font-size:10px;">${esc(r.student.full_name)}</td>`;
    if (o.studentId) tbody += `<td style="padding:5px;font-size:9px;color:#666;">${esc(r.student.student_id)}</td>`;
    tbody += `<td style="padding:5px;text-align:center;font-weight:bold;color:${sc};">${r.total_score}</td>`;
    if (o.subjects) tbody += `<td style="padding:5px;font-size:9px;">${subs.map((s) => esc(s.name).substring(0, 3) + ':' + s.score).join(' ')}</td>`;
    if (o.level) tbody += `<td style="padding:5px;font-size:9px;text-align:center;">${esc(r.performance_level)}</td>`;
    tbody += '</tr>';
  });

  const summary = o.summary
    ? `Students: ${st ? st.student_count : 0} | Avg: ${r1(stats.average)} | High: ${stats.max || 0} | Low: ${stats.min || 0}` : '';
  const below = (dist['180-199'] || 0) + (dist['0-179'] || 0);
  const distHtml = o.distribution
    ? `<div style="font-size:10px;font-weight:bold;margin-bottom:4px;">Distribution:</div><div style="font-size:9px;display:flex;gap:8px;flex-wrap:wrap;"><span style="color:var(--success);">300+: ${dist['300-400'] || 0}</span><span style="color:var(--info);">250-299: ${dist['250-299'] || 0}</span><span style="color:var(--warning);">200-249: ${dist['200-249'] || 0}</span><span style="color:var(--danger);">&lt;200: ${below}</span></div>` : '';
  const footer = o.timestamp ? `Generated: ${new Date().toLocaleString()}` : '';

  wrap.innerHTML = `<div style="padding:12px;background:white;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <h2 style="color:#11998e;text-align:center;margin:0 0 8px 0;font-size:18px;">${esc(d.exam.display_name)}</h2>
    <p style="text-align:center;color:#666;margin:0 0 4px 0;font-size:11px;">${esc(d.exam.exam_date)}${d.exam.session_name ? ' | ' + esc(d.exam.session_name) : ''}</p>
    <p style="text-align:center;color:#666;margin:0 0 10px 0;font-size:11px;">${summary}</p>
    <table style="width:100%;border-collapse:collapse;font-size:11px;"><thead>${thead}</thead><tbody>${tbody}</tbody></table>
    ${o.distribution ? `<div style="margin-top:10px;padding:8px;background:#f8f9fa;border-radius:6px;">${distHtml}</div>` : ''}
    <p style="text-align:center;margin:8px 0 0 0;color:#999;font-size:9px;">${footer}</p>
  </div>`;
  return wrap;
}

// ---- Student progress ------------------------------------------------------
function StudentProgress({ d }) {
  const nav = useNav();
  const chartRef = useRef();
  const p = d.progress;
  const pred = d.prediction;
  const recs = d.recommendations;
  const s = d.student;

  useEffect(() => {
    if (!p || !p.progress.length || !chartRef.current || !window.Chart) return;
    const scores = p.progress.map((x) => x.score);
    const chart = new window.Chart(chartRef.current, {
      type: 'line',
      data: { labels: p.progress.map((x) => x.exam),
        datasets: [{ label: 'Score', data: scores, borderColor: '#11998e', backgroundColor: 'rgba(17,153,142,0.1)',
          borderWidth: 3, fill: true, tension: 0.3, pointRadius: 6, pointBackgroundColor: '#11998e' }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: false, min: Math.max(0, Math.min(...scores) - 50), max: Math.min(400, Math.max(...scores) + 50), grid: { color: 'rgba(0,0,0,0.05)' } },
          x: { grid: { display: false } } } },
    });
    return () => chart.destroy();
  }, [p]);

  const latest = p && p.progress.length ? p.progress[p.progress.length - 1] : null;
  const gap = s.jamb_target != null && p ? s.jamb_target - p.latest_score : null;

  return (
    <>
      <div className="student-header">
        <div className="student-avatar">{s.full_name[0]}</div>
        <div className="student-info"><h1>{s.full_name}</h1><p>{s.student_id}{s.gender ? ` | ${s.gender}` : ''}</p></div>
        <div style={{ marginLeft: 'auto' }}>
          <select className="form-control" value={d.selected_session_id}
                  onChange={(e) => navParams(nav.go, d.urls.self, { session_id: e.target.value })}>
            {d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </div>
      </div>

      {p ? (<>
        <div className="stats-row">
          <div className="stat-box highlight"><div className="value">{r1(p.average_score)}</div><div className="label">Average Score</div></div>
          <div className="stat-box"><div className="value">{p.best_score}</div><div className="label">Best Score</div></div>
          <div className="stat-box"><div className="value">{p.latest_score}</div><div className="label">Latest Score</div></div>
          <div className="stat-box"><div className="value">{p.exam_count}</div><div className="label">Exams Taken</div></div>
        </div>

        {s.jamb_target != null && (
          <div className="card mb-3"><div className="card-body d-flex justify-content-between align-items-center" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
            <div><strong><i aria-hidden="true" className="fas fa-bullseye" /> JAMB Target: {s.jamb_target}</strong>
              <p className="text-muted mb-0" style={{ fontSize: 'var(--text-sm)' }}>Latest mock: {p.latest_score}</p></div>
            <div style={{ textAlign: 'right' }}>
              {gap <= 0 ? <span className="badge badge-success" style={{ fontSize: 'var(--text-base)' }}><i aria-hidden="true" className="fas fa-check" /> Target met (+{-gap})</span>
                : <span className="badge badge-warning" style={{ fontSize: 'var(--text-base)' }}>{gap} to go</span>}
            </div>
          </div></div>
        )}

        {pred && (<>
          <div className="prediction-card">
            <h3 style={{ textAlign: 'center', margin: '0 0 0.5rem', fontSize: 'var(--text-md)', opacity: 0.9 }}><i aria-hidden="true" className="fas fa-crystal-ball" /> Predicted Real JAMB Score</h3>
            <div className="prediction-score">{pred.predicted_score}</div>
            <div className="prediction-range">Expected Range: {pred.predicted_range.low} - {pred.predicted_range.high}</div>
            <div className="prediction-details">
              <div className="prediction-detail"><div className="val">
                <span className={'trend-badge ' + (pred.improvement_trend > 0 ? 'trend-improving' : pred.improvement_trend < 0 ? 'trend-declining' : 'trend-stable')}>
                  {pred.improvement_trend > 0 ? <><i aria-hidden="true" className="fas fa-arrow-up" /> +{pred.improvement_trend}</>
                    : pred.improvement_trend < 0 ? <><i aria-hidden="true" className="fas fa-arrow-down" /> {pred.improvement_trend}</>
                    : <><i aria-hidden="true" className="fas fa-minus" /> Stable</>}
                </span></div><div className="lbl">Trend</div></div>
              <div className="prediction-detail"><div className="val">{pred.confidence_level}%</div><div className="lbl">Confidence</div></div>
              <div className="prediction-detail"><div className="val">{pred.mock_count}</div><div className="lbl">Based on Exams</div></div>
            </div>
            <div style={{ textAlign: 'center', marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.2)', fontSize: 'var(--text-sm)', opacity: 0.9 }}>
              {pred.recommendation}</div>
          </div>
          <div className="card mb-3"><div className="card-body d-flex justify-content-between align-items-center">
            <div><strong><i aria-hidden="true" className="fas fa-file-alt" /> Want to see predicted WAEC grades?</strong>
              <p className="text-muted mb-0" style={{ fontSize: 'var(--text-sm)' }}>Based on your Mock JAMB subject scores</p></div>
            <a href={d.urls.predictions} className="btn btn-primary"><i aria-hidden="true" className="fas fa-chart-line" /> View All Predictions</a>
          </div></div>
        </>)}

        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-line" /> Score Progression</h3></div>
          <div className="card-body"><div className="progress-chart"><canvas ref={chartRef} /></div></div></div>

        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-history" /> Exam History</h3></div>
          <div className="card-body"><div className="exam-timeline">
            {p.progress.map((x, i) => (
              <div className="exam-item" key={i}>
                <div className="exam-number">{x.exam_number}</div>
                <div className="exam-details"><div className="exam-name">{x.exam}</div><div className="exam-date">{x.exam_date}</div></div>
                <div style={{ textAlign: 'right' }}>
                  <div className="exam-score" style={{ color: scoreColor(x.score) }}>{x.score}</div>
                  {x.change != null && <div className={'exam-change ' + (x.change > 0 ? 'positive' : x.change < 0 ? 'negative' : '')}>{x.change > 0 ? '+' : ''}{x.change}</div>}
                </div>
              </div>))}
          </div></div></div>

        {latest && latest.subjects && latest.subjects.length > 0 && (
          <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-book" /> Latest Subject Scores</h3></div>
            <div className="card-body"><div className="subject-breakdown">
              {latest.subjects.map((sub, i) => (
                <div className="subject-card" key={i}><div className="name">{sub.name}</div>
                  <div className="score" style={{ color: sub.score >= 70 ? 'var(--success)' : sub.score >= 50 ? 'var(--warning)' : 'var(--danger)' }}>{sub.score}</div></div>))}
            </div></div></div>
        )}

        {recs && recs.length > 0 && (
          <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-lightbulb" /> Improvement Recommendations</h3></div>
            <div className="card-body"><div className="recommendation-list">
              {recs.map((rec, i) => (
                <div className={'rec-item ' + rec.priority} key={i}>
                  <div style={{ flex: 1 }}><div className="rec-subject">{rec.subject} <span className="rec-score">({rec.score})</span></div>
                    <div className="rec-text">{rec.recommendation}</div></div>
                </div>))}
            </div></div></div>
        )}
      </>) : (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-line" title="No Mock Exam Results">
          <p>This student hasn't taken any mock exams yet</p></Empty></div></div>
      )}
    </>
  );
}

// ---- Analytics -------------------------------------------------------------
function Analytics({ d }) {
  const nav = useNav();
  const chartRef = useRef();
  const comp = d.comparison;

  useEffect(() => {
    if (!comp.length || !chartRef.current || !window.Chart) return;
    const chart = new window.Chart(chartRef.current, {
      type: 'bar',
      data: { labels: comp.map((c) => c.exam.display_name),
        datasets: [
          { label: 'Average Score', data: comp.map((c) => r1(c.average)), backgroundColor: 'rgba(17,153,142,0.8)', borderRadius: 4, order: 2 },
          { label: 'Max Score', data: comp.map((c) => c.max), type: 'line', borderColor: 'var(--success)', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 4, order: 1 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } },
        scales: { y: { beginAtZero: false, min: 100, max: 400, grid: { color: 'rgba(0,0,0,0.05)' } } } },
    });
    return () => chart.destroy();
  }, [comp]);

  const latest = comp.length ? comp[comp.length - 1] : null;
  const first = comp.length ? comp[0] : null;
  const change = latest && first ? latest.average - first.average : 0;

  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-chart-bar" /> Mock JAMB Analytics</h1>
        {d.urls.validation && <div className="page-header-actions"><a href={d.urls.validation} className="btn btn-outline"><i aria-hidden="true" className="fas fa-bullseye" /> Mock Validation</a></div>}
      </div>
      <div className="filter-bar">
        <div className="form-group mb-0">
          <label className="form-label">Academic Session</label>
          <select className="form-control" value={d.selected_session_id}
                  onChange={(e) => navParams(nav.go, d.urls.self, { session_id: e.target.value })}>
            {d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      </div>

      {comp.length > 0 ? (<>
        <div className="stats-row">
          <div className="stat-box highlight"><div className="value">{comp.length}</div><div className="label">Exams Conducted</div></div>
          <div className="stat-box"><div className="value">{latest.student_count}</div><div className="label">Latest Participants</div></div>
          <div className="stat-box"><div className="value">{r1(latest.average)}</div><div className="label">Latest Average</div></div>
          <div className="stat-box"><div className="value" style={{ color: change > 0 ? 'var(--success)' : change < 0 ? 'var(--danger)' : '#6c757d' }}>
            {change > 0 ? '+' : ''}{r1(change)}</div><div className="label">Change from 1st</div></div>
        </div>

        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-line" /> Exam Comparison</h3></div>
          <div className="card-body"><div className="chart-container"><canvas ref={chartRef} /></div></div></div>

        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-table" /> Exam Statistics</h3></div>
          <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="comparison-table">
              <thead><tr><th>Exam</th><th>Students</th><th>Average</th><th>Change</th><th>Max</th><th>Min</th><th>≥200</th><th>≥250%</th></tr></thead>
              <tbody>{comp.map((c, i) => {
                const ch = i > 0 ? c.average - comp[i - 1].average : null;
                return (
                  <tr key={c.exam.id}>
                    <td><strong>{c.exam.display_name}</strong></td>
                    <td>{c.student_count}</td>
                    <td><strong>{r1(c.average)}</strong></td>
                    <td>{ch == null ? '-' : <span className={ch > 0 ? 'trend-up' : ch < 0 ? 'trend-down' : ''}>{ch > 0 ? '+' : ''}{r1(ch)}</span>}</td>
                    <td style={{ color: 'var(--success)' }}>{c.max}</td>
                    <td style={{ color: 'var(--danger)' }}>{c.min}</td>
                    <td>{c.above_200}</td>
                    <td>{c.above_250_pct}%</td>
                  </tr>);
              })}</tbody>
            </table>
          </div></div>

        <h3 className="mb-3"><i aria-hidden="true" className="fas fa-clipboard-list" /> Detailed Breakdown</h3>
        {d.exams_stats.map((stats) => {
          const total = stats.student_count;
          const pct = (n) => (total > 0 ? (n / total) * 100 : 0);
          const dist = stats.distribution;
          const below = dist['180-199'] + dist['0-179'];
          return (
            <div className="exam-card" key={stats.exam.id}>
              <div className="exam-card-header">
                <div><div className="exam-card-title">{stats.exam.display_name}</div><div className="exam-card-date">{stats.exam.exam_date}</div></div>
                <a href={stats.exam.view_url} className="btn btn-sm btn-primary">View</a>
              </div>
              <div className="exam-card-body">
                <div className="mini-stats">
                  <div className="mini-stat"><div className="val">{stats.student_count}</div><div className="lbl">Students</div></div>
                  <div className="mini-stat"><div className="val">{r1(stats.statistics.average)}</div><div className="lbl">Average</div></div>
                  <div className="mini-stat"><div className="val" style={{ color: 'var(--success)' }}>{stats.statistics.max}</div><div className="lbl">Highest</div></div>
                  <div className="mini-stat"><div className="val" style={{ color: 'var(--danger)' }}>{stats.statistics.min}</div><div className="lbl">Lowest</div></div>
                </div>
                <div className="distribution-bars">
                  <div className="dist-row"><span className="dist-label">300-400</span><div className="dist-bar-bg"><div className="dist-bar excellent" style={{ width: pct(dist['300-400']) + '%' }} /></div><span className="dist-count">{dist['300-400']}</span></div>
                  <div className="dist-row"><span className="dist-label">250-299</span><div className="dist-bar-bg"><div className="dist-bar good" style={{ width: pct(dist['250-299']) + '%' }} /></div><span className="dist-count">{dist['250-299']}</span></div>
                  <div className="dist-row"><span className="dist-label">200-249</span><div className="dist-bar-bg"><div className="dist-bar average" style={{ width: pct(dist['200-249']) + '%' }} /></div><span className="dist-count">{dist['200-249']}</span></div>
                  <div className="dist-row"><span className="dist-label">Below 200</span><div className="dist-bar-bg"><div className="dist-bar below" style={{ width: pct(below) + '%' }} /></div><span className="dist-count">{below}</span></div>
                </div>
                {stats.subject_analysis.length > 0 && (
                  <div className="improvement-section"><div className="improvement-title">Subject Performance</div>
                    <div className="improvement-list">{stats.subject_analysis.slice(0, 6).map((su) => (
                      <span className={'improvement-badge ' + (su.average >= 60 ? 'improving' : su.average < 45 ? 'declining' : '')} key={su.subject}>
                        {su.subject}: {r1(su.average)}</span>))}
                    </div></div>
                )}
              </div>
            </div>);
        })}
      </>) : (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-bar" title="No Data Yet">
          <p>Conduct mock exams to see analytics</p>
          <a href={d.urls.create} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Create Exam</a></Empty></div></div>
      )}
    </>
  );
}

function Validation({ d }) {
  const nav = useNav();
  const v = d.validation;
  const meta = (v && v.meta) || {};
  const s = (v && v.summary) || {};
  const scatterRef = useRef();
  useEffect(() => {
    if (!v || meta.insufficient || !scatterRef.current || !window.Chart) return;
    const pts = (v.scatter || []).map((p) => ({ x: p.mock, y: p.actual }));
    const lo = 0; const hi = 400;
    const chart = new window.Chart(scatterRef.current, {
      data: {
        datasets: [
          { type: 'scatter', label: 'Candidate', data: pts, backgroundColor: 'rgba(17,153,142,0.7)', pointRadius: 4 },
          { type: 'line', label: 'Perfect prediction', data: [{ x: lo, y: lo }, { x: hi, y: hi }], borderColor: 'rgba(0,0,0,0.35)', borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0 },
          { type: 'line', label: 'Cut-off', data: [{ x: meta.cutoff, y: lo }, { x: meta.cutoff, y: hi }], borderColor: '#e74a3b', borderWidth: 1, pointRadius: 0 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'top' }, tooltip: { callbacks: { label: (c) => `mock ${c.parsed.x} → actual ${c.parsed.y}` } } },
        scales: { x: { title: { display: true, text: 'Mock score' }, min: lo, max: hi }, y: { title: { display: true, text: 'Actual JAMB' }, min: lo, max: hi } },
      },
    });
    return () => chart.destroy();
  }, [v]); // eslint-disable-line react-hooks/exhaustive-deps

  const TONE = { positive: ['fa-circle-check', 'var(--success,#1c8c53)'], negative: ['fa-triangle-exclamation', '#b43a2e'], watch: ['fa-eye', '#c9a227'] };
  const kpi = (label, value, tone) => (
    <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: tone }}>{value}</div><div className="text-muted text-sm">{label}</div></div></div>
  );
  const th = s.threshold || {};
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-bullseye" /> Mock → Actual Validation</h1>
        <div className="page-header-actions">
          {v && !meta.insufficient && <><a href={d.urls.export_pdf} className="btn btn-success" data-native download><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>
          <a href={d.urls.export_excel} className="btn btn-secondary" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a></>}
          <a href={d.urls.analytics} className="btn btn-outline"><i aria-hidden="true" className="fas fa-chart-line" /> Analytics</a>
        </div>
      </div>
      <div className="filter-bar">
        <div className="form-group mb-0"><label className="form-label">Academic Session</label>
          <select className="form-control" value={d.selected_session_id} onChange={(e) => navParams(nav.go, d.urls.self, { session_id: e.target.value })}>
            {d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
        {d.exams.length > 0 && (
          <div className="form-group mb-0"><label className="form-label">Mock</label>
            <select className="form-control" value={d.selected_mock_exam_id} onChange={(e) => navParams(nav.go, d.urls.self, { session_id: d.selected_session_id, mock_exam_id: e.target.value })}>
              {d.exams.map((x) => <option key={x.id} value={x.id}>{x.display_name}</option>)}</select></div>
        )}
        {d.years.length > 0 && (
          <div className="form-group mb-0"><label className="form-label">Actual JAMB year</label>
            <select className="form-control" value={d.selected_year} onChange={(e) => navParams(nav.go, d.urls.self, { session_id: d.selected_session_id, mock_exam_id: d.selected_mock_exam_id, year: e.target.value })}>
              <option value="">Latest available</option>
              {d.years.map((y) => <option key={y} value={y}>{y}</option>)}</select></div>
        )}
      </div>

      {!v || meta.insufficient ? (
        <div className="card"><div className="card-body"><Empty icon="fa-bullseye" title="Not enough matched candidates">
          <p>{(meta && meta.reason) || 'Validation needs candidates with both a Mock JAMB and an actual JAMB result. Record actual JAMB results to unlock it.'}</p></Empty></div></div>
      ) : (<>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
          {kpi('Correlation (r)', s.correlation == null ? '—' : s.correlation, s.correlation >= 0.7 ? 'var(--success)' : (s.correlation >= 0.4 ? '#c9a227' : '#e74a3b'))}
          {kpi('R² explained', s.r_squared == null ? '—' : s.r_squared)}
          {kpi('Mean abs error', `±${s.mae}`)}
          {kpi('Bias', `${s.bias > 0 ? '+' : ''}${s.bias}`, Math.abs(s.bias) <= 8 ? 'var(--success)' : '#e74a3b')}
          {kpi('Within 40 pts', `${s.within40_pct}%`)}
          {kpi('Calibration', s.bias_direction, s.bias_direction === 'well-calibrated' ? 'var(--success)' : '#c9a227')}
        </div>
        <div className="text-muted text-sm mb-2" style={{ marginTop: '-.4rem' }}>
          {s.matched} matched candidate(s) · mock mean {s.mock_mean} vs actual mean {s.actual_mean} · bias 95% CI {s.bias_ci_low}…{s.bias_ci_high}
        </div>

        {v.recommendations && v.recommendations.length > 0 && (
          <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-lightbulb" /> Findings &amp; recommendations</h3></div>
            <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: '.6rem' }}>
              {v.recommendations.map((r, i) => { const [ic, col] = TONE[r.tone] || ['fa-lightbulb', 'var(--primary)']; return (
                <div key={i} style={{ borderLeft: `4px solid ${col}`, background: 'var(--bg-secondary,#f8f9fb)', borderRadius: 6, padding: '.6rem .8rem' }}>
                  <div style={{ fontWeight: 700, marginBottom: '.2rem' }}><i aria-hidden="true" className={`fas ${ic}`} style={{ color: col, marginRight: '.4rem' }} />{r.title}</div>
                  <div className="text-sm" style={{ color: 'var(--text-secondary,#4a5568)' }}>{r.text}</div>
                </div>); })}
            </div></div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <div className="card"><div className="card-header"><h3>Mock vs actual</h3><span className="text-muted text-sm">points near the dashed line predicted well</span></div>
            <div className="card-body"><div style={{ height: 300 }}><canvas ref={scatterRef} /></div></div></div>
          <div className="card"><div className="card-header"><h3>Cut-off ({th.cutoff}) reliability</h3></div>
            <div className="card-body">
              <table className="data-table"><thead><tr><th /><th className="text-center">Actual ≥ {th.cutoff}</th><th className="text-center">Actual &lt; {th.cutoff}</th></tr></thead>
                <tbody>
                  <tr><td><strong>Mock ≥ {th.cutoff}</strong></td><td className="text-center" style={{ color: 'var(--success)', fontWeight: 700 }}>{th.tp}</td><td className="text-center">{th.fp}</td></tr>
                  <tr><td><strong>Mock &lt; {th.cutoff}</strong></td><td className="text-center">{th.fn}</td><td className="text-center" style={{ fontWeight: 700 }}>{th.tn}</td></tr>
                </tbody></table>
              <div className="text-sm mt-2 text-muted">Accuracy {th.accuracy}% · sensitivity {th.sensitivity}% · specificity {th.specificity}% · PPV {th.ppv}%</div>
            </div></div>
        </div>

        {v.per_mock && v.per_mock.length > 1 && (
          <div className="card mb-3"><div className="card-header"><h3>Which mock predicts best</h3></div>
            <div className="card-body" style={{ padding: 0 }}>
              <table className="data-table"><thead><tr><th>Mock</th><th className="text-right">Matched</th><th className="text-right">Correlation</th><th className="text-right">MAE</th></tr></thead>
                <tbody>{v.per_mock.map((m) => (
                  <tr key={m.number}><td><strong>{m.name}</strong></td><td className="text-right">{m.matched}</td>
                    <td className="text-right" style={{ fontWeight: 600 }}>{m.correlation == null ? '—' : m.correlation}</td><td className="text-right">±{m.mae}</td></tr>
                ))}</tbody></table>
            </div></div>
        )}

        <div className="card"><div className="card-header"><h3>Candidate mock vs actual (largest gaps)</h3></div>
          <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table"><thead><tr><th>Candidate</th><th className="text-right">Mock</th><th className="text-right">Actual</th><th className="text-right">Δ</th></tr></thead>
              <tbody>{[...v.pairs].sort((a, b) => (a.actual - a.mock) - (b.actual - b.mock)).slice(0, 30).map((p) => {
                const delta = p.actual - p.mock;
                return <tr key={p.student_id}><td>{p.name}</td><td className="text-right">{p.mock}</td><td className="text-right">{p.actual}</td>
                  <td className="text-right" style={{ color: delta < 0 ? '#e74a3b' : 'var(--success)', fontWeight: 600 }}>{delta > 0 ? '+' : ''}{delta}</td></tr>;
              })}</tbody></table>
          </div></div>
      </>)}
    </>
  );
}

const BAND = { critical: '#dc2626', weak: '#b45309', fair: '#0d9488', strong: '#047857', unknown: '#64748b' };
const FLAG = {
  strong: { bg: 'rgba(4,120,87,.14)', c: '#047857' }, solid: { bg: 'rgba(13,148,136,.14)', c: '#0d9488' },
  watch: { bg: 'rgba(180,83,9,.14)', c: '#b45309' }, support: { bg: 'rgba(220,38,38,.14)', c: '#dc2626' },
  insufficient: { bg: 'rgba(107,122,116,.16)', c: '#6b7a74' }, unassigned: { bg: 'rgba(107,122,116,.16)', c: '#6b7a74' },
};
const RECO = { positive: '#047857', negative: '#dc2626', warning: '#b45309', insight: '#2563eb' };

function Deep({ d }) {
  const deep = d.deep;
  const distRef = useRef();
  const subjRef = useRef();
  const armRef = useRef();
  const empty = !deep || (deep.meta && deep.meta.empty);

  useEffect(() => {
    if (empty || !window.Chart) return;
    const charts = [];
    const grid = 'rgba(140,140,140,.2)';
    if (distRef.current) {
      const dd = deep.distribution;
      const cols = ['#047857', '#0d9488', '#2563eb', '#b45309', '#dc2626'];
      charts.push(new window.Chart(distRef.current, {
        type: 'bar',
        data: { labels: dd.map((x) => x.band), datasets: [{ data: dd.map((x) => x.count), backgroundColor: cols, borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: { color: grid } }, x: { grid: { display: false } } } },
      }));
    }
    if (subjRef.current && deep.subjects.length) {
      charts.push(new window.Chart(subjRef.current, {
        type: 'bar',
        data: { labels: deep.subjects.map((s) => s.subject), datasets: [{ data: deep.subjects.map((s) => s.pass_rate), backgroundColor: deep.subjects.map((s) => BAND[s.band] || '#64748b'), borderRadius: 4 }] },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, max: 100, grid: { color: grid } }, y: { grid: { display: false } } } },
      }));
    }
    if (armRef.current && deep.arms.length) {
      charts.push(new window.Chart(armRef.current, {
        type: 'bar',
        data: { labels: deep.arms.map((a) => a.arm), datasets: [{ label: 'JAMB mean', data: deep.arms.map((a) => a.jamb_mean), backgroundColor: '#2563eb', borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: { color: grid } }, x: { grid: { display: false } } } },
      }));
    }
    return () => charts.forEach((c) => c.destroy());
  }, [deep, empty]);

  const actions = (
    <>
      <a href={d.urls.export_pdf} className="btn btn-danger btn-sm" title="PDF" data-native download><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>
      <a href={d.urls.export_excel} className="btn btn-success btn-sm" title="Excel" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
      <a href={d.urls.export_image} className="btn btn-info btn-sm" title="HD image" data-native download><i aria-hidden="true" className="fas fa-image" /> Image</a>
      {d.urls.items && <a href={d.urls.items} className="btn btn-outline btn-sm" title="Item &amp; topic analysis" data-native><i aria-hidden="true" className="fas fa-microscope" /> Items</a>}
      {d.urls.trends && <a href={d.urls.trends} className="btn btn-outline btn-sm" title="Progress trends"><i aria-hidden="true" className="fas fa-chart-line" /> Trends</a>}
      <a href={d.urls.view} className="btn btn-secondary btn-sm" title="Back"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>
    </>
  );

  const header = (
    <div className="page-header">
      <div><h1>Deep Analytics — {d.exam.display_name}</h1>
        <p className="text-muted text-sm">{d.exam.exam_date}{d.exam.session_name ? ` | ${d.exam.session_name}` : ''} · per subject · per teacher · per class arm</p></div>
      <div className="page-header-actions">{actions}</div>
    </div>
  );

  if (empty) {
    return <>{header}<Empty icon="fa-brain" title="No results yet"><p className="text-muted">Enter scores to unlock per-subject, per-teacher and per-arm deep analytics.</p><a href={d.urls.view} className="btn btn-primary mt-2">Enter results</a></Empty></>;
  }

  const kpiBorder = { blue: '#2563eb', teal: '#0d9488', green: '#047857', amber: '#b45309' };
  return (
    <>
      {header}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.75rem', marginBottom: '1.1rem' }}>
        {deep.kpis.map((k, i) => (
          <div key={i} className="card" style={{ padding: '.9rem 1rem', borderTop: `3px solid ${kpiBorder[k.tone] || '#2563eb'}` }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, lineHeight: 1 }}>{k.value}</div>
            <div style={{ fontSize: '.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.03em', color: 'var(--text-secondary)', marginTop: '.35rem' }}>{k.label}</div>
            <div style={{ fontSize: '.7rem', color: 'var(--text-muted)', marginTop: '.15rem' }}>{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="charts-row">
        <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-column" /> Score distribution</h3></div><div className="chart-body" style={{ height: 230 }}><canvas ref={distRef} /></div></div>
        <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-bar" /> Subject pass rate</h3></div><div className="chart-body" style={{ height: 230 }}><canvas ref={subjRef} /></div></div>
        {deep.arms.length > 0 && <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-layer-group" /> Class-arm JAMB mean</h3></div><div className="chart-body" style={{ height: 230 }}><canvas ref={armRef} /></div></div>}
      </div>

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-book" /> Subject league — weakest first</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table"><thead><tr><th style={{ textAlign: 'left' }}>Subject</th><th>N</th><th>Mean</th><th>SD</th><th>Pass %</th><th>Strong %</th><th>Verdict</th><th style={{ textAlign: 'left' }}>Recommended action</th></tr></thead>
            <tbody>{deep.subjects.map((s) => (
              <tr key={s.subject}><td><strong>{s.subject}</strong></td><td className="text-center">{s.n}</td><td className="text-center">{s.mean == null ? '—' : s.mean}</td><td className="text-center">{s.sd}</td>
                <td className="text-center" style={{ color: BAND[s.band], fontWeight: 700 }}>{s.pass_rate == null ? '—' : s.pass_rate}%</td>
                <td className="text-center">{s.distinction_rate == null ? '—' : s.distinction_rate}%</td>
                <td className="text-center" style={{ color: BAND[s.band], fontWeight: 700 }}>{s.band_label}</td>
                <td style={{ fontSize: '.78rem', color: 'var(--text-muted)' }}>{s.recommendation}</td></tr>
            ))}</tbody></table>
        </div></div>

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chalkboard-teacher" /> Teacher effectiveness <span className="text-muted text-sm">— evidence-based, one mock</span></h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table"><thead><tr><th style={{ textAlign: 'left' }}>Teacher</th><th style={{ textAlign: 'left' }}>Subjects</th><th>Students</th><th>Mean</th><th>Pass %</th><th>Δ cohort</th><th style={{ textAlign: 'left' }}>Verdict &amp; action</th><th /></tr></thead>
            <tbody>{deep.teachers.map((t, i) => {
              const f = FLAG[t.flag] || FLAG.insufficient;
              return (
                <tr key={i}><td><strong>{t.teacher}</strong></td><td className="text-sm">{t.subjects.join(', ')}</td><td className="text-center">{t.students}</td>
                  <td className="text-center">{t.mean == null ? '—' : t.mean}</td><td className="text-center">{t.pass_rate == null ? '—' : t.pass_rate}%</td>
                  <td className="text-center" style={{ color: t.delta == null ? 'inherit' : t.delta >= 0 ? '#047857' : '#dc2626', fontWeight: 700 }}>{t.delta == null ? '—' : (t.delta > 0 ? '+' : '') + t.delta}</td>
                  <td><span style={{ display: 'inline-block', fontSize: '.68rem', fontWeight: 700, padding: '.15rem .5rem', borderRadius: 999, background: f.bg, color: f.c }}>{t.verdict}</span>
                    <div style={{ fontSize: '.78rem', color: 'var(--text-muted)', marginTop: '.3rem' }}>{t.recommendation}</div></td>
                  <td>{t.staff_id && <a href={`${d.compose_base}?to=staff&staff_ids=${t.staff_id}`} className="btn btn-sm btn-outline" title="Message this teacher" data-native><i aria-hidden="true" className="fas fa-paper-plane" /></a>}</td></tr>
              );
            })}</tbody></table>
        </div>
        <div className="card-body" style={{ paddingTop: 0, fontSize: '.78rem', color: 'var(--text-muted)' }}>Subject results are attributed to the SSS3 subject teacher for each candidate's arm. No HR decision should rest on one mock — confirm across sittings and against intake ability.</div>
      </div>

      {deep.arms.length > 0 && (
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-layer-group" /> Class-arm league — best first</h3></div>
          <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table"><thead><tr><th>#</th><th style={{ textAlign: 'left' }}>Class arm</th><th>Students</th><th>JAMB mean</th><th>≥200</th><th>Subject pass</th></tr></thead>
              <tbody>{deep.arms.map((a, i) => (
                <tr key={a.arm}><td className="text-center">{i + 1}</td><td><strong>{a.arm}</strong></td><td className="text-center">{a.students}</td>
                  <td className="text-center">{a.jamb_mean == null ? '—' : a.jamb_mean}</td><td className="text-center">{a.above_200_rate == null ? '—' : a.above_200_rate}%</td><td className="text-center">{a.pass_rate == null ? '—' : a.pass_rate}%</td></tr>
              ))}</tbody></table>
          </div></div>
      )}

      <div className="charts-row">
        {[['critical', 'Critical — urgent', '#dc2626'], ['at_risk', 'At risk — borderline', '#b45309'], ['honour', 'Honour roll — stretch', '#047857']].map(([key, title, col]) => (
          <div key={key} className="card"><div className="card-header"><h3 style={{ color: col }}>{title}</h3></div>
            <div className="card-body" style={{ maxHeight: 340, overflow: 'auto' }}>
              {deep.segments[key].length === 0 ? <p className="text-muted text-sm">None.</p> : deep.segments[key].map((x) => (
                <div key={x.student_id} style={{ display: 'flex', justifyContent: 'space-between', gap: '.6rem', padding: '.4rem 0', borderBottom: '1px solid var(--border-color)' }}>
                  <div><div style={{ fontWeight: 600, fontSize: '.84rem' }}>{x.name}</div><div style={{ fontSize: '.74rem', color: 'var(--text-muted)' }}>{x.note}</div></div>
                  <div style={{ fontWeight: 700, whiteSpace: 'nowrap', color: col, fontSize: '.8rem' }}>{x.metric}</div>
                </div>
              ))}
            </div></div>
        ))}
      </div>

      <h3 style={{ margin: '1.2rem 0 .6rem' }}>Recommendations</h3>
      <div className="charts-row">
        {[['students', 'Students', 'fa-user-graduate', '#2563eb'], ['teachers', 'Teachers', 'fa-chalkboard-teacher', '#0d9488'], ['management', 'Management', 'fa-briefcase', '#b45309']].map(([bucket, title, icon, col]) => (
          <div key={bucket} className="card"><div className="card-header"><h3><i aria-hidden="true" className={`fas ${icon}`} style={{ color: col }} /> {title}</h3></div>
            <div className="card-body">
              {deep.recommendations[bucket].length === 0 ? <p className="text-muted text-sm">Nothing flagged.</p> : deep.recommendations[bucket].map((r, i) => (
                <div key={i} style={{ borderLeft: `3px solid ${RECO[r.tone] || '#64748b'}`, padding: '.35rem 0 .55rem .65rem', marginBottom: '.55rem' }}>
                  <div style={{ fontWeight: 700, fontSize: '.82rem' }}>{r.title}</div>
                  <div style={{ fontSize: '.78rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>{r.text}</div>
                </div>
              ))}
            </div></div>
        ))}
      </div>
    </>
  );
}

const PALETTE = ['#2563eb', '#047857', '#b45309', '#7c3aed', '#dc2626', '#0d9488', '#c2410c', '#0891b2', '#9333ea', '#65a30d'];
const arrow = (dir) => (dir === 'up' ? 'fa-arrow-up' : dir === 'down' ? 'fa-arrow-down' : 'fa-arrow-right');
const dirColor = (dir) => (dir === 'up' ? '#047857' : dir === 'down' ? '#dc2626' : 'var(--text-secondary)');

function Trends({ d }) {
  const nav = useNav();
  const t = d.trends;
  const cohortRef = useRef();
  const subjRef = useRef();
  const insufficient = !t || (t.meta && t.meta.insufficient);
  const labels = insufficient ? [] : t.periods.map((p) => p.label);

  useEffect(() => {
    if (insufficient || !window.Chart) return;
    const charts = [];
    const grid = 'rgba(140,140,140,.2)';
    if (cohortRef.current) {
      charts.push(new window.Chart(cohortRef.current, {
        type: 'line',
        data: { labels, datasets: [
          { label: t.headline.primary_label, data: t.cohort.map((c) => c.primary), borderColor: '#2563eb', backgroundColor: '#2563eb22', tension: 0.3, yAxisID: 'y', spanGaps: true },
          { label: t.headline.secondary_label, data: t.cohort.map((c) => c.secondary), borderColor: '#047857', backgroundColor: '#04785722', tension: 0.3, yAxisID: 'y1', spanGaps: true },
        ] },
        options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { position: 'bottom' } },
          scales: { y: { position: 'left', beginAtZero: true, grid: { color: grid } }, y1: { position: 'right', beginAtZero: true, grid: { display: false } }, x: { grid: { display: false } } } },
      }));
    }
    if (subjRef.current) {
      const subs = t.subject_trends.slice(0, 8);
      charts.push(new window.Chart(subjRef.current, {
        type: 'line',
        data: { labels, datasets: subs.map((s, i) => ({ label: s.name, data: s.points, borderColor: PALETTE[i % PALETTE.length], backgroundColor: 'transparent', tension: 0.3, spanGaps: true })) },
        options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } },
          scales: { y: { beginAtZero: true, max: 100, grid: { color: grid } }, x: { grid: { display: false } } } },
      }));
    }
    return () => charts.forEach((c) => c.destroy());
  }, [t, insufficient]);

  const go = (scope, sessionId) => {
    const params = scope === 'all' ? { scope: 'all' } : { session_id: sessionId };
    navParams(nav.go, d.urls.self, params);
  };

  const header = (
    <div className="page-header">
      <div><h1>Progress Trends — Mock JAMB</h1>
        <p className="text-muted text-sm">Track mean score, subjects, teachers and arms across mocks{t && t.meta.multi_session ? ' and across sessions' : ''}.</p></div>
      <div className="page-header-actions">
        {!insufficient && <>
          <a href={d.urls.export_pdf} className="btn btn-danger btn-sm" data-native download><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>
          <a href={d.urls.export_excel} className="btn btn-success btn-sm" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
          <a href={d.urls.export_image} className="btn btn-info btn-sm" data-native download><i aria-hidden="true" className="fas fa-image" /> Image</a>
        </>}
        <a href={d.urls.index} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>
      </div>
    </div>
  );

  const selector = (
    <div className="filter-form mb-3" style={{ display: 'flex', gap: '.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <label className="text-sm text-muted">Scope</label>
      <select className="form-control" style={{ width: 'auto' }} value={d.scope}
              onChange={(e) => go(e.target.value, d.selected_session_id)}>
        <option value="session">A single session</option>
        <option value="all">All sessions (year-over-year)</option>
      </select>
      {d.scope !== 'all' && (
        <select className="form-control" style={{ width: 'auto' }} value={d.selected_session_id || ''}
                onChange={(e) => go('session', e.target.value)}>
          {d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      )}
      <span className="text-muted text-sm">“All sessions” tracks year-over-year across cohorts.</span>
    </div>
  );

  if (insufficient) {
    return <>{header}{selector}<Empty icon="fa-chart-line" title="Not enough mocks yet"><p className="text-muted">Progress needs at least two mocks with results{d.scope !== 'all' ? ' in this session' : ''}. Add more mock results, or switch scope to “All sessions”.</p></Empty></>;
  }

  const hb = (lbl, first, last, delta, dir) => (
    <div className="card" style={{ padding: '1rem 1.1rem' }}>
      <div style={{ fontSize: '1.6rem', fontWeight: 800, lineHeight: 1.1, color: dirColor(dir) }}>
        {first} → {last} <i aria-hidden="true" className={`fas ${arrow(dir)}`} /></div>
      <div style={{ fontSize: '.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.03em', color: 'var(--text-secondary)', marginTop: '.3rem' }}>{lbl}</div>
      <div style={{ fontSize: '.74rem', color: 'var(--text-muted)', marginTop: '.15rem' }}>{delta == null ? '' : `${delta > 0 ? '+' : ''}${delta} first → latest`}</div>
    </div>
  );

  const trendTable = (title, rows, note) => (
    <div className="card mb-3"><div className="card-header"><h3>{title}</h3></div>
      <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="data-table"><thead><tr><th style={{ textAlign: 'left' }}>Name</th>{labels.map((l, i) => <th key={i}>{l}</th>)}<th>Trend</th></tr></thead>
          <tbody>{rows.length === 0 ? (
            <tr><td colSpan={labels.length + 2} className="text-muted text-sm">{note}</td></tr>
          ) : rows.map((r) => (
            <tr key={r.name}><td><strong>{r.name}</strong></td>
              {r.points.map((v, i) => <td key={i} className="text-center">{v == null ? '—' : v}</td>)}
              <td className="text-center" style={{ color: dirColor(r.direction), fontWeight: 700 }}>
                {r.delta == null ? '' : (r.delta > 0 ? '+' : '') + r.delta} {r.direction === 'up' ? '↑' : r.direction === 'down' ? '↓' : '→'}</td></tr>
          ))}</tbody></table>
      </div></div>
  );

  return (
    <>
      {header}
      {selector}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: '.75rem', marginBottom: '1.1rem' }}>
        {hb(t.headline.primary_label, t.headline.primary_first, t.headline.primary_last, t.headline.primary_delta, t.headline.primary_direction)}
        {hb(t.headline.secondary_label, t.headline.secondary_first, t.headline.secondary_last, t.headline.secondary_delta, t.headline.secondary_direction)}
      </div>
      <div style={{ fontSize: '.8rem', color: 'var(--text-muted)', marginBottom: '.6rem' }}>{t.meta.periods_count} mocks · {t.meta.span}</div>

      <div className="charts-row">
        <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-line" /> Cohort trajectory</h3></div><div className="chart-body" style={{ height: 260 }}><canvas ref={cohortRef} /></div></div>
        <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-line" /> Subject pass rate over time</h3></div><div className="chart-body" style={{ height: 260 }}><canvas ref={subjRef} /></div></div>
      </div>

      {trendTable('Subject trend — biggest movement first', t.subject_trends, '')}
      {trendTable('Teacher trend — pass rate per mock', t.teacher_trends, 'No teacher-attributed subjects yet. Set teachers on SSS3 Class Subjects.')}

      <div className="charts-row">
        {[['improving', 'Improving', 'fa-arrow-trend-up', '#047857'], ['declining', 'Declining — attention', 'fa-arrow-trend-down', '#dc2626']].map(([key, title, icon, col]) => (
          <div key={key} className="card"><div className="card-header"><h3><i aria-hidden="true" className={`fas ${icon}`} style={{ color: col }} /> {title}</h3></div>
            <div className="card-body">
              {t.movers[key].length === 0 ? <p className="text-muted text-sm">{key === 'improving' ? 'No clear improvers yet.' : 'Nothing declining — good.'}</p> : t.movers[key].map((m, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: '.6rem', padding: '.4rem 0', borderBottom: '1px solid var(--border-color)' }}>
                  <div><div style={{ fontWeight: 600, fontSize: '.84rem' }}>{m.name}</div><div style={{ fontSize: '.72rem', color: 'var(--text-muted)' }}>{m.kind} · now {m.current}%</div></div>
                  <div style={{ fontWeight: 700, color: col }}>{m.delta > 0 ? '+' : ''}{m.delta}</div>
                </div>
              ))}
            </div></div>
        ))}
      </div>

      <h3 style={{ margin: '1.2rem 0 .6rem' }}>Recommendations</h3>
      <div className="charts-row">
        {[['students', 'Students', 'fa-user-graduate', '#2563eb'], ['teachers', 'Teachers', 'fa-chalkboard-teacher', '#0d9488'], ['management', 'Management', 'fa-briefcase', '#b45309']].map(([bucket, title, icon, col]) => (
          <div key={bucket} className="card"><div className="card-header"><h3><i aria-hidden="true" className={`fas ${icon}`} style={{ color: col }} /> {title}</h3></div>
            <div className="card-body">
              {t.recommendations[bucket].length === 0 ? <p className="text-muted text-sm">Nothing flagged.</p> : t.recommendations[bucket].map((r, i) => (
                <div key={i} style={{ borderLeft: `3px solid ${RECO[r.tone] || '#64748b'}`, padding: '.35rem 0 .55rem .65rem', marginBottom: '.55rem' }}>
                  <div style={{ fontWeight: 700, fontSize: '.82rem' }}>{r.title}</div>
                  <div style={{ fontSize: '.78rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>{r.text}</div>
                </div>
              ))}
            </div></div>
        ))}
      </div>
    </>
  );
}

const SCREENS = { index: Index, create_exam: CreateExam, edit_exam: EditExam, edit_result: EditResult,
  bulk_entry: BulkEntry, add_result: AddResult, view_exam: ViewExam, student_progress: StudentProgress,
  analytics: Analytics, validation: Validation, deep: Deep, trends: Trends };

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
