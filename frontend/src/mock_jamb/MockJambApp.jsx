import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { chartPalette } from '../lib/hooks';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, PageHeader, Empty, SectionShell } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Menu, Blank } from '../subjects/results';

const ORD = { 1: '1st', 2: '2nd', 3: '3rd', 4: '4th' };

// ---- Shared tabs -------------------------------------------------------------
// Module tabs (exams / analytics / trends / validation / question bank) and,
// on a screen about one exam, that exam's tabs. URLs come from `d.mjnav`.
function MjNav({ d, active }) {
  const n = d.mjnav;
  if (!n) return null;
  const tabs = [['index', 'fa-clipboard-list', 'Mock exams', n.index], ['analytics', 'fa-chart-column', 'Analytics', n.analytics],
    ['trends', 'fa-chart-line', 'Progress trends', n.trends], ['validation', 'fa-bullseye', 'Validation', n.validation],
    ['bank', 'fa-database', 'Question bank', n.bank, true]];
  return (
    <nav className="sl-nav" aria-label="Mock JAMB sections">
      {tabs.map(([k, ic, l, href, native]) => href && (
        <a key={k} href={href} className={active === k ? 'on' : ''} data-native={native ? '' : undefined}>
          <i className={'fas ' + ic} aria-hidden="true" /><span>{l}</span></a>))}
    </nav>
  );
}

function ExamNav({ d, active }) {
  const x = d.mjnav && d.mjnav.exam;
  if (!x) return null;
  const enter = canWrite(d, 'mock_jamb_results_create');
  return (
    <>
      <nav className="sl-nav" aria-label={x.name + ' sections'}>
        <a href={x.view} className={active === 'view' ? 'on' : ''}><i className="fas fa-users" aria-hidden="true" /><span>Results</span></a>
        <a href={x.deep} className={active === 'deep' ? 'on' : ''}><i className="fas fa-brain" aria-hidden="true" /><span>Deep analytics</span></a>
        <a href={x.questions} data-native=""><i className="fas fa-pen-to-square" aria-hidden="true" /><span>Questions</span></a>
        <a href={x.items} data-native=""><i className="fas fa-microscope" aria-hidden="true" /><span>Item analysis</span></a>
        {enter && <a href={x.bulk} className={active === 'add' || active === 'bulk' ? 'on' : ''}><i className="fas fa-plus" aria-hidden="true" /><span>Enter results</span></a>}
      </nav>
      {enter && (active === 'add' || active === 'bulk') && (
        <nav className="sl-sub" aria-label="Ways to enter results">
          <a href={x.bulk} className={active === 'bulk' ? 'on' : ''}><i className="fas fa-table-cells" aria-hidden="true" /> Many students</a>
          <a href={x.add} className={active === 'add' ? 'on' : ''}><i className="fas fa-keyboard" aria-hidden="true" /> One student</a>
        </nav>)}
    </>
  );
}

const jt = (s) => (s >= 250 ? 'a1' : s >= 200 ? 'c4' : s >= 180 ? 'd7' : 'f9');
const js = (s) => (s >= 70 ? 'a1' : s >= 50 ? 'c4' : s >= 40 ? 'd7' : 'f9');
const LEVEL_TONE = { excellent: 'good', very_good: 'good', good: 'info', fair: 'mid', average: 'mid', below_average: 'bad', below: 'bad', needs_improvement: 'bad', poor: 'bad' };
const abbr = (n) => (n || '').replace(/[^A-Za-z ]/g, '').split(/\s+/).filter(Boolean).map((w) => w[0]).join('').slice(0, 3).toUpperCase().padEnd(3, (n || '').slice(1, 3).toUpperCase());

// ---- Index -----------------------------------------------------------------
function Index({ d }) {
  const nav = useNav();
  const st = d.stats;
  const last = d.comparison.length ? d.comparison[d.comparison.length - 1] : null;
  const first = d.comparison.length > 1 ? d.comparison[0] : null;
  const maxAvg = Math.max(400, ...d.comparison.map((c) => c.average || 0));
  return (
    <>
      <Head icon="fa-clipboard-list" title="Mock JAMB" sub="UTME rehearsals — scored out of 400 across four subjects">
        <select className="mj-sel" aria-label="Academic session" value={d.selected_session_id}
                onChange={(e) => navParams(nav.go, d.urls.self, { session_id: e.target.value })}>
          {d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        {!d.derived && <a href={d.urls.predictions} className="rs-btn ghost"><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /><span className="rs-hide-sm">Predictions</span></a>}
        {!d.derived && canWrite(d, 'mock_jamb_exam_create') && <a href={d.urls.create} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">New mock</span></a>}
      </Head>
      <MjNav d={d} active="index" />

      {d.exams.length > 0 && (
        <Tiles items={[
          { label: 'Mocks this session', value: st.count, sub: st.remaining > 0 ? st.remaining + ' more planned' : 'all four held' },
          { label: 'Results recorded', value: st.total_results, sub: 'across all mocks' },
          { label: 'Average score', value: st.avg_score ?? '—', unit: st.avg_score != null ? '/400' : '', sub: 'all mocks this session',
            tone: st.avg_score == null ? '' : st.avg_score >= 250 ? 'good' : st.avg_score >= 200 ? '' : 'mid' },
          last && { label: 'Scored 250+ (latest)', value: last.above_250, sub: first ? (last.above_250 - first.above_250 >= 0 ? '+' : '') + (last.above_250 - first.above_250) + ' since ' + first.label : last.label, tone: 'good' },
        ]} />
      )}

      {d.exams.length ? (
        <div className={d.comparison.length > 1 ? 'bx-two' : ''}>
          <section className="rs-card flush">
            <div className="rs-card-h pad"><h3><i className="fas fa-list" aria-hidden="true" /> Mock exams</h3><small>{d.exams.length}</small></div>
            <div className="mw-exams">
              {d.exams.map((e) => (
                <div className="mw-exam mj-exam" key={e.id}>
                  <span className="mw-no">{e.exam_number || e.display_name.match(/\d/)?.[0] || '•'}</span>
                  <a className="n" href={d.derived ? e.add_url : e.view_url}>
                    <b>{e.display_name}</b>
                    <small>{e.exam_date} · {e.student_count} students{e.average_score != null ? ' · avg ' + e.average_score : ''}{e.above_200 != null ? ' · ' + e.above_200 + ' scored 200+' : ''}</small>
                  </a>
                  <span className={'sl-pill ' + (e.is_completed ? 'good' : 'mid')}>{e.is_completed ? 'Completed' : 'In progress'}</span>
                  <span className="a">
                    {(d.derived || canWrite(d, 'mock_jamb_results_create')) && (
                      <a href={d.derived ? e.add_url : e.bulk_url} className={d.derived ? 'rs-btn primary sm' : 'rs-icon-btn'} title="Enter results" aria-label={'Enter results for ' + e.display_name}>
                        <i className="fas fa-pen-to-square" aria-hidden="true" />{d.derived && ' Enter results'}</a>)}
                    {!d.derived && e.deep_url && <a href={e.deep_url} className="rs-icon-btn" title="Deep analytics" aria-label={'Deep analytics for ' + e.display_name}><i className="fas fa-brain" aria-hidden="true" /></a>}
                  </span>
                </div>
              ))}
            </div>
          </section>
          {d.comparison.length > 1 && (
            <section className="rs-card">
              <div className="rs-card-h"><h3><i className="fas fa-chart-line" aria-hidden="true" /> Performance across mocks</h3><small>average /400</small></div>
              <div className="bx-yoy">
                {d.comparison.map((c) => (
                  <div className="bx-yoy-r" key={c.label}>
                    <span className="y">{c.label}</span>
                    <span className="m"><span className="an-hbar"><span className="t"><i className={c.average >= 250 ? 'good' : c.average >= 200 ? '' : 'mid'} style={{ width: (c.average / maxAvg * 100) + '%' }} /></span></span>
                      <small>average {c.average}</small></span>
                    <span className="b"><b>{c.above_250}</b><small>scored 250+</small></span>
                  </div>))}
              </div>
            </section>)}
        </div>
      ) : (
        <Blank icon="fa-clipboard-list" title="No mock exams yet">
          <p>Create the first mock for this session to start recording results.</p>
          {canWrite(d, 'mock_jamb_exam_create') && <a href={d.urls.create} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /> New mock</a>}
        </Blank>
      )}
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
      <Head icon="fa-plus" title="Create Mock JAMB Exam" sub="Set up a new mock examination" />
      <MjNav d={d} active="create" />
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
      <Head icon="fa-pen" title="Edit Mock Exam" sub={e0.display_name + (e0.session_name ? ' · ' + e0.session_name : '')} />
      <MjNav d={d} active="" />
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
        {canWrite(d, 'mock_jamb_exam_delete') && (<>
        <hr className="my-4" />
        <div className="text-danger"><h4>Danger Zone</h4>
          <p className="text-sm">Deleting this exam will also delete all student results. This cannot be undone.</p>
          <button type="button" className="btn btn-danger" onClick={del}><i aria-hidden="true" className="fas fa-trash" /> Delete Exam</button></div>
        </>)}
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
      <Head icon="fa-pen" title="Edit Result" sub={r0.student_name + ' · ' + r0.exam_name} />
      <MjNav d={d} active="" />
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
        {canWrite(d, 'mock_jamb_results_delete') && (<>
        <hr className="my-4" />
        <button type="button" className="btn btn-danger btn-sm" onClick={del}><i aria-hidden="true" className="fas fa-trash" /> Delete Result</button>
        </>)}
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
      <Head icon="fa-table-cells" title="Bulk Entry" sub={d.exam.display_name + ' · enter scores for many students'} />
      <ExamNav d={d} active="bulk" />
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
      <Head icon="fa-keyboard" title="Add Result" />
      <MjNav d={d} active="" />
      <div className="card" style={{ maxWidth: 760 }}><div className="card-body"><Empty icon="fa-user-slash" title="">
        <p>All students already have results for this exam</p>
        <a href={d.view_url} className="btn btn-primary">View Results</a></Empty></div></div>
    </>);
  }
  return (
    <>
      <Head icon="fa-keyboard" title="Add Result" sub={d.exam ? d.exam.display_name : ''} />
      <ExamNav d={d} active="add" />
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
  const st = d.statistics;
  const [filters, setFilters] = useState(d.filters);
  const [exporting, setExporting] = useState(false);

  // Live filters: name/ID and min/max score narrow the already-loaded results
  // instantly (no round-trip). A min/max the server already applied (it was in
  // the URL) can only be widened by the server, so changing it reloads.
  const q = (filters.search || '').trim().toLowerCase();
  const serverRange = useRef((d.filters.min_score !== '' && d.filters.min_score != null)
                             || (d.filters.max_score !== '' && d.filters.max_score != null)).current;
  const num = (v) => (v === '' || v == null || isNaN(parseFloat(v)) ? null : parseFloat(v));
  const lo = serverRange ? null : num(filters.min_score);
  const hi = serverRange ? null : num(filters.max_score);
  const shown = d.results.filter((it) => (
    (!q || (it.student.full_name + ' ' + it.student.student_id).toLowerCase().includes(q))
    && (lo == null || (it.total_score || 0) >= lo) && (hi == null || (it.total_score || 0) <= hi)));
  const narrowed = shown.length !== d.results.length;
  useEffect(() => {
    if (!serverRange) return undefined;
    if (String(filters.min_score ?? '') === String(d.filters.min_score ?? '')
        && String(filters.max_score ?? '') === String(d.filters.max_score ?? '')) return undefined;
    const t = setTimeout(() => navParams(nav.go, d.urls.self,
      { search: filters.search, min_score: filters.min_score, max_score: filters.max_score }), 700);
    return () => clearTimeout(t);
  }, [filters.min_score, filters.max_score]);

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

  // Every format is the server's branded results document (same design as the
  // JAMB / WAEC exports); images arrive one A4 page per request.
  const doExport = async (opts) => {
    setExporting(false);
    const p = new URLSearchParams({ format: opts.format, type: opts.type, cols: opts.cols.join(','), size: opts.size });
    if (filters.min_score !== '' && filters.min_score != null) p.set('min_score', filters.min_score);
    if (filters.max_score !== '' && filters.max_score != null) p.set('max_score', filters.max_score);
    const url = d.urls.export + (d.urls.export.includes('?') ? '&' : '?') + p.toString();
    if (opts.format !== 'image') { window.location.href = url; return; }
    const stem = 'mock_jamb_' + (opts.type === 'subjects' ? 'subject_analysis' : 'results');
    try {
      let page = 1, total = 1;
      do {
        const res = await fetch(url + '&page=' + page, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        total = parseInt(res.headers.get('X-Total-Pages') || '1', 10) || 1;
        const blob = await res.blob();
        const u = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = u; a.download = stem + (total > 1 ? '_p' + page : '') + '.png';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(u), 4000);
        page += 1;
      } while (page <= total);
    } catch (err) {
      notify('error', 'Could not generate the image.');
    }
  };

  const [showF, setShowF] = useState(false);
  const s = st && st.statistics;
  const dist = st && st.distribution;
  const bands = dist ? [['0-179', 'f9', 'Below 180'], ['180-199', 'd7', '180–199'], ['200-249', 'c4', '200–249'], ['250-299', 'a1', '250–299'], ['300-400', 'a1', '300+']] : [];
  const mx = dist ? Math.max(1, ...bands.map(([k]) => dist[k] || 0)) : 1;
  const subj = st ? [...st.subject_analysis].sort((a, b) => a.average - b.average) : [];
  const n = st ? st.student_count || 1 : 1;
  const menu = [
    canWrite(d, 'mock_jamb_results_export') && d.results.length > 0 && { icon: 'fa-file-pdf', label: 'PDF, image or Word…', onClick: () => setExporting(true) },
    canWrite(d, 'mock_jamb_results_export') && { icon: 'fa-file-excel', label: 'Excel spreadsheet', href: d.urls.export, native: true, download: true },
    canWrite(d, 'mock_jamb_exam_edit') && { icon: 'fa-pen', label: 'Edit exam', href: d.urls.edit },
    { icon: 'fa-list', label: 'All mock exams', href: d.urls.index },
    canWrite(d, 'mock_jamb_exam_delete') && { icon: 'fa-trash', label: 'Delete exam', danger: true, onClick: delExam },
  ];

  return (
    <>
      <Head icon="fa-clipboard-list" title={d.exam.display_name} sub={[d.exam.exam_date, d.exam.session_name].filter(Boolean).join(' · ')}>
        <Menu items={menu} label="Export & more" />
        {canWrite(d, 'mock_jamb_results_create') && <a href={d.urls.bulk} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Enter results</span></a>}
      </Head>
      <ExamNav d={d} active="view" />

      {s && (
        <Tiles items={[
          { label: 'Average score', value: r1(s.average), unit: '/400', sub: 'median ' + s.median },
          { label: 'Scored 200+', value: Math.round(s.above_200 / n * 100), unit: '%', sub: s.above_200 + ' of ' + st.student_count + ' students', tone: s.above_200 / n >= 0.6 ? 'good' : s.above_200 / n >= 0.4 ? 'mid' : 'bad' },
          { label: 'Scored 250+', value: s.above_250, sub: 'competitive courses' },
          { label: 'Scored 300+', value: s.above_300, sub: 'top band', tone: 'good' },
          { label: 'Range', value: s.min + '–' + s.max, sub: 'lowest – highest' },
        ]} />
      )}

      {st && (
        <div className="bx-two">
          <section className="rs-card">
            <div className="rs-card-h"><h3><i className="fas fa-chart-column" aria-hidden="true" /> Score distribution</h3><small>{st.student_count} students</small></div>
            <div className="bx-dist bx-dist5">
              {bands.map(([k, t, l]) => (
                <div className="bx-dist-c" key={k} title={l + ': ' + (dist[k] || 0)}>
                  <b>{dist[k] || 0}</b><span className="bar"><i className={t} style={{ height: ((dist[k] || 0) / mx * 100) + '%' }} /></span><small>{l}</small>
                </div>))}
            </div>
          </section>
          <section className="rs-card">
            <div className="rs-card-h"><h3><i className="fas fa-book" aria-hidden="true" /> Subjects</h3><small>average /100 · weakest first</small></div>
            {subj.length ? (
              <div className="an-hbars">
                {subj.map((x) => (
                  <a key={x.subject} className="an-hbar bx-hbar" href={'/mock-jamb/exam/' + d.exam.id + '/subject/' + encodeURIComponent(x.subject)} title={'Full analysis for ' + x.subject}>
                    <span className="l">{x.subject}<small>{x.count} sat · {x.above_50} scored 50+</small></span>
                    <span className="t"><i className={x.average >= 70 ? 'good' : x.average >= 50 ? 'mid' : 'bad'} style={{ width: x.average + '%' }} /></span>
                    <b>{r1(x.average)}</b>
                  </a>))}
              </div>) : <p className="rs-muted">No subject scores yet.</p>}
          </section>
        </div>
      )}

      <section className="rs-card flush">
        <form className="bx-filters" onSubmit={applyFilters}>
          <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
            <input type="search" placeholder="Search name or ID" aria-label="Search by name or ID" value={filters.search}
                   onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
            {narrowed && <span className="bx-count">{shown.length} of {d.results.length}</span>}</label>
          <button type="button" className={'rs-btn ghost bx-ftoggle' + (showF ? ' on' : '')} onClick={() => setShowF((v) => !v)} aria-expanded={showF}>
            <i className="fas fa-sliders" aria-hidden="true" /> Filters</button>
          <div className={'bx-fset' + (showF ? ' open' : '')}>
            <label className="bx-f xs"><span>Min score</span><input type="number" inputMode="numeric" placeholder="0" value={filters.min_score}
              onChange={(e) => setFilters((f) => ({ ...f, min_score: e.target.value }))} /></label>
            <label className="bx-f xs"><span>Max score</span><input type="number" inputMode="numeric" placeholder="400" value={filters.max_score}
              onChange={(e) => setFilters((f) => ({ ...f, max_score: e.target.value }))} /></label>
            {(d.has_filter || narrowed) && <button type="button" className="rs-btn ghost sm"
              onClick={() => (d.has_filter ? clearFilters() : setFilters((f) => ({ ...f, search: '', min_score: '', max_score: '' })))}>Clear</button>}
          </div>
        </form>
        {shown.length ? (
          <div className="jx-list">
            {shown.map((it) => (
              <div className="jx-row" key={it.rank}>
                <span className={'bx-pos sm' + rankClass(it.rank)}>{it.rank}</span>
                <a className="n" href={it.student.progress_url}><b>{it.student.full_name}</b>
                  <small>{it.student.student_id} <span className={'sl-pill ' + (LEVEL_TONE[it.perf_class] || '')}>{it.performance_level}</span></small></a>
                <span className="jx-score"><span className={'jx-total ' + jt(it.total_score || 0)}>{it.total_score}</span>
                  <span className={'rs-meter ' + ((it.total_score || 0) >= 250 ? 'good' : (it.total_score || 0) >= 200 ? 'n' : (it.total_score || 0) >= 180 ? 'mid' : 'bad')}><i style={{ width: ((it.total_score || 0) / 4) + '%' }} /></span></span>
                <span className="bx-grades">{it.subjects.filter(Boolean).map((x, i) => (
                  <span key={i} className={'bx-g ' + js(x.score)} title={x.name}>{abbr(x.name)} <b>{x.score}</b></span>))}</span>
                <span className="a">
                  <a href={it.student.progress_url} className="rs-icon-btn" title="Progress" aria-label={'Progress for ' + it.student.full_name}><i className="fas fa-chart-line" aria-hidden="true" /></a>
                  {canWrite(d, 'mock_jamb_results_edit') && <a href={it.edit_url} className="rs-icon-btn" aria-label={'Edit ' + it.student.full_name} title="Edit"><i className="fas fa-pen" aria-hidden="true" /></a>}
                  {canWrite(d, 'mock_jamb_results_delete') && <button type="button" className="rs-icon-btn danger" aria-label={'Delete ' + it.student.full_name} title="Delete" onClick={() => delResult(it.delete_url)}><i className="fas fa-trash" aria-hidden="true" /></button>}
                </span>
              </div>))}
          </div>
        ) : (
          <Blank icon="fa-clipboard-list" title="No results">
            <p>{filters.search ? 'No students found matching "' + filters.search + '"' : 'Add results for this exam.'}</p>
            {canWrite(d, 'mock_jamb_results_create') && <a href={d.urls.bulk} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /> Enter results</a>}
          </Blank>
        )}
      </section>

      {exporting && <ExportModal onClose={() => setExporting(false)} onGenerate={doExport} spec={d.export_cols}
                                 hasSubjects={!!(st && st.subject_analysis && st.subject_analysis.length)} />}
    </>
  );
}

function ExportModal({ onClose, onGenerate, hasSubjects, spec }) {
  const defaults = (t) => (spec[t] || []).filter((c) => c[2]).map((c) => c[0]);
  const [format, setFormat] = useState('pdf');
  const [size, setSize] = useState('m');
  const [type, setType] = useState('students');
  const [cols, setCols] = useState({ students: defaults('students'), subjects: defaults('subjects') });
  const toggle = (k) => setCols((c) => ({ ...c, [type]: c[type].includes(k) ? c[type].filter((x) => x !== k) : [...c[type], k] }));
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  const Opt = ({ val, cur, set, children }) => (
    <label className={'mjx-opt' + (cur === val ? ' on' : '')}>
      <input type="radio" checked={cur === val} onChange={() => set(val)} /><span>{children}</span></label>
  );
  // Portal to <body>: an ancestor in the section shell breaks position:fixed,
  // which left the dialog far down the page on phones.
  return createPortal((
    <div className="mjx-backdrop" role="dialog" aria-modal="true" aria-labelledby="mjxTitle"
         onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="mjx-dialog">
        <div className="mjx-head">
          <h3 id="mjxTitle"><i aria-hidden="true" className="fas fa-file-export" /> Export Results</h3>
          <button type="button" className="mjx-x" onClick={onClose} aria-label="Close">&times;</button>
        </div>
        <div className="mjx-body">
          <div className="mjx-label">Format:</div>
          <div className="mjx-grid3">
            <Opt val="pdf" cur={format} set={setFormat}><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</Opt>
            <Opt val="image" cur={format} set={setFormat}><i aria-hidden="true" className="fas fa-image" /> Image</Opt>
            <Opt val="word" cur={format} set={setFormat}><i aria-hidden="true" className="fas fa-file-word" /> Word</Opt>
          </div>
          <div className="mjx-label">Text size:</div>
          <div className="mjx-size" role="radiogroup" aria-label="Text size">
            {[['s', 'Small'], ['m', 'Medium'], ['l', 'Large']].map(([v, l]) => (
              <label key={v}><input type="radio" name="mjxSize" checked={size === v} onChange={() => setSize(v)} /><span>{l}</span></label>
            ))}
          </div>
          {hasSubjects && (<>
            <div className="mjx-label">Export Type:</div>
            <div className="mjx-grid2">
              <Opt val="students" cur={type} set={setType}>Students List</Opt>
              <Opt val="subjects" cur={type} set={setType}>Subjects Analysis</Opt>
            </div>
          </>)}
          <div className="mjx-label">{type === 'students' ? 'Student Columns:' : 'Subject Columns:'}</div>
          <div className="mjx-checks">
            <label className="mjx-check"><input type="checkbox" checked disabled /><span>{type === 'students' ? 'Name & total score (required)' : 'Subject (required)'}</span></label>
            {(spec[type] || []).map(([k, label]) => (
              <label key={k} className="mjx-check"><input type="checkbox" checked={cols[type].includes(k)} onChange={() => toggle(k)} /><span>{label}</span></label>
            ))}
          </div>
          <p className="mjx-note"><i aria-hidden="true" className="fas fa-circle-info" /> Subject scores are out of 100 and totals out of 400. Any score filter on this page is applied to the export.</p>
          <div className="mjx-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="button" className="btn btn-primary" onClick={() => onGenerate({ format, size, type, cols: cols[type] })}>
              <i aria-hidden="true" className="fas fa-download" /> Export</button>
          </div>
        </div>
      </div>
    </div>
  ), document.body);
}

// ---- Student progress ------------------------------------------------------
// Score-over-mocks line chart (SVG, no library): JAMB bands, target line, points.
function ScoreLine({ points, target }) {
  const W = 640, H = 220, L = 34, R = 12, T = 12, B = 26;
  const ys = points.map((x) => x.score).concat(target ? [target] : []);
  const lo = Math.max(0, Math.floor((Math.min(...ys) - 30) / 50) * 50);
  const hi = Math.min(400, Math.ceil((Math.max(...ys) + 30) / 50) * 50);
  const x = (i) => L + (points.length === 1 ? (W - L - R) / 2 : i * (W - L - R) / (points.length - 1));
  const y = (v) => T + (hi - v) / (hi - lo || 1) * (H - T - B);
  const ticks = []; for (let v = lo; v <= hi; v += 50) ticks.push(v);
  const bands = [[250, 400, 'var(--g-d)'], [200, 250, 'var(--g-c)'], [180, 200, 'var(--g-p)'], [0, 180, 'var(--g-f)']];
  return (
    <svg className="mj-line" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Mock JAMB score over time">
      {bands.map(([a, b2, c]) => { const t = Math.min(hi, b2), f = Math.max(lo, a); return t > f ? <rect key={a} x={L} width={W - L - R} y={y(t)} height={y(f) - y(t)} fill={c} opacity=".07" /> : null; })}
      {ticks.map((v) => <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="gl" /><text x={L - 6} y={y(v) + 4} textAnchor="end" className="tk">{v}</text></g>)}
      {target != null && target >= lo && target <= hi && <g><line x1={L} x2={W - R} y1={y(target)} y2={y(target)} className="tg" /><text x={W - R} y={y(target) - 5} textAnchor="end" className="tgl">Target {target}</text></g>}
      <polyline points={points.map((p, i) => x(i) + ',' + y(p.score)).join(' ')} className="ln" />
      {points.map((p, i) => <g key={i}><circle cx={x(i)} cy={y(p.score)} r="5" className="pt" /><text x={x(i)} y={y(p.score) - 10} textAnchor="middle" className="pv">{p.score}</text>
        <text x={x(i)} y={H - 6} textAnchor="middle" className="tk">M{p.exam_number || i + 1}</text></g>)}
    </svg>
  );
}

function StudentProgress({ d }) {
  const nav = useNav();
  const p = d.progress;
  const pred = d.prediction;
  const recs = d.recommendations;
  const s = d.student;
  const latest = p && p.progress.length ? p.progress[p.progress.length - 1] : null;
  const gap = s.jamb_target != null && p ? s.jamb_target - p.latest_score : null;
  // Subject × mock matrix — which subjects are rising or slipping.
  const subjNames = [];
  (p ? p.progress : []).forEach((m) => (m.subjects || []).forEach((x) => { if (x && !subjNames.includes(x.name)) subjNames.push(x.name); }));
  const subjRows = subjNames.map((nm) => {
    const sc = p.progress.map((m) => { const f = (m.subjects || []).find((x) => x && x.name === nm); return f ? f.score : null; });
    const got = sc.filter((v) => v != null);
    return { nm, sc, last: got[got.length - 1], delta: got.length > 1 ? got[got.length - 1] - got[0] : null };
  }).sort((a, b) => (a.last ?? 0) - (b.last ?? 0));
  const weakest = subjRows[0];
  const PRI = { critical: 'bad', high: 'bad', medium: 'mid', low: '', none: 'good' };

  return (
    <>
      <Head icon="fa-user-graduate" title={s.full_name} sub={[s.student_id, s.gender, 'Mock JAMB progress'].filter(Boolean).join(' · ')}>
        <select className="mj-sel" aria-label="Session" value={d.selected_session_id}
                onChange={(e) => navParams(nav.go, d.urls.self, { session_id: e.target.value })}>
          {d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        <a href={d.urls.predictions} className="rs-btn primary"><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /><span className="rs-hide-sm">All predictions</span></a>
      </Head>
      <MjNav d={d} active="" />

      {p ? (<>
        {s.jamb_target != null && (
          <div className={'bx-verdict ' + (gap <= 0 ? 'good' : gap <= 20 ? 'mid' : 'bad')}>
            <i className={'fas ' + (gap <= 0 ? 'fa-circle-check' : 'fa-bullseye')} aria-hidden="true" />
            <div><b>{gap <= 0 ? `Target met — ${-gap} above the ${s.jamb_target} target` : `${gap} points to go to reach the ${s.jamb_target} target`}</b>
              <span>Latest mock {p.latest_score} · best {p.best_score}{pred ? ` · projected real JAMB ${pred.predicted_score}` : ''}</span></div>
          </div>)}

        <Tiles items={[
          { label: 'Latest score', value: p.latest_score, unit: '/400', sub: latest && latest.change != null ? (latest.change > 0 ? '+' : '') + latest.change + ' vs previous mock' : 'first mock', tone: p.latest_score >= 250 ? 'good' : p.latest_score >= 200 ? '' : p.latest_score >= 180 ? 'mid' : 'bad' },
          { label: 'Best score', value: p.best_score, unit: '/400' },
          { label: 'Average', value: r1(p.average_score), unit: '/400', sub: p.exam_count + ' mock' + (p.exam_count === 1 ? '' : 's') + ' taken' },
          pred && { label: 'Projected real JAMB', value: pred.predicted_score, sub: `likely ${pred.predicted_range.low}–${pred.predicted_range.high} · ${pred.confidence_level}% confidence`, tone: pred.predicted_score >= 200 ? 'good' : 'mid' },
        ]} />

        <div className="bx-two">
          <section className="rs-card">
            <div className="rs-card-h"><h3><i className="fas fa-chart-line" aria-hidden="true" /> Score progression</h3><small>shaded: 250+ · 200–249 · 180–199 · below 180</small></div>
            <ScoreLine points={p.progress} target={s.jamb_target} />
          </section>
          {pred ? (
            <section className="rs-card mj-pred">
              <div className="rs-card-h"><h3><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Predicted real JAMB</h3><small>from {pred.mock_count} mock{pred.mock_count === 1 ? '' : 's'}</small></div>
              <div className="mj-pred-n"><b className={'jx-total ' + jt(pred.predicted_score)}>{pred.predicted_score}</b>
                <div><span>Expected range <b>{pred.predicted_range.low}–{pred.predicted_range.high}</b></span>
                  <span className={pred.improvement_trend > 0 ? 'bx-good' : pred.improvement_trend < 0 ? 'bx-bad' : 'rs-muted'}>
                    <i className={'fas fa-arrow-' + (pred.improvement_trend > 0 ? 'up' : pred.improvement_trend < 0 ? 'down' : 'right')} aria-hidden="true" /> {pred.improvement_trend > 0 ? '+' : ''}{pred.improvement_trend || 'Stable'} trend</span></div></div>
              <div className="mj-conf"><span className="rs-meter good"><i style={{ width: pred.confidence_level + '%' }} /></span><small>{pred.confidence_level}% confidence — rises with each mock</small></div>
              <p className="mj-reco">{pred.recommendation}</p>
            </section>
          ) : (
            <section className="rs-card"><div className="rs-card-h"><h3><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Prediction</h3></div>
              <p className="rs-muted">A real-JAMB projection appears after this student sits more mocks.</p></section>
          )}
        </div>

        <div className="bx-two">
          {subjRows.length > 0 && (
            <section className="rs-card flush">
              <div className="rs-card-h pad"><h3><i className="fas fa-book" aria-hidden="true" /> Subjects across mocks</h3><small>weakest first · out of 100</small></div>
              <div className="sl-tbl-wrap"><table className="sl-tbl mj-subj">
                <thead><tr><th>Subject</th>{p.progress.map((m, i) => <th key={i} className="c">M{m.exam_number || i + 1}</th>)}<th className="r">Change</th></tr></thead>
                <tbody>{subjRows.map((r) => (
                  <tr key={r.nm}><td className="main">{r.nm}</td>
                    {r.sc.map((v, i) => <td key={i} className="c">{v == null ? <span className="rs-muted">—</span> : <span className={'bx-g ' + js(v)}><b>{v}</b></span>}</td>)}
                    <td className="r">{r.delta == null ? <span className="rs-muted">—</span> : <span className={r.delta > 0 ? 'bx-good' : r.delta < 0 ? 'bx-bad' : 'rs-muted'}>{r.delta > 0 ? '+' : ''}{r.delta}</span>}</td></tr>))}
                </tbody></table></div>
              {weakest && weakest.last != null && weakest.last < 60 && <p className="rs-muted bx-small bx-pad" style={{ paddingTop: 0 }}><b>{weakest.nm}</b> is the subject holding the total back — each 10 marks gained there adds 10 to the JAMB score.</p>}
            </section>)}

          <section className="rs-card flush">
            <div className="rs-card-h pad"><h3><i className="fas fa-clock-rotate-left" aria-hidden="true" /> Exam history</h3><small>{p.exam_count}</small></div>
            <div className="bx-rank">{[...p.progress].reverse().map((x, i) => (
              <div className="bx-rank-row jx-rank" key={i}>
                <span className="mw-no mj-no">{x.exam_number}</span>
                <span className="n"><b>{x.exam}</b><small>{x.exam_date}</small></span>
                <span>{x.change != null && <span className={'mj-chg ' + (x.change > 0 ? 'bx-good' : x.change < 0 ? 'bx-bad' : 'rs-muted')}>{x.change > 0 ? '+' : ''}{x.change}</span>}</span>
                <span className={'jx-total ' + jt(x.score)}>{x.score}</span>
              </div>))}</div>
          </section>
        </div>

        {recs && recs.length > 0 && (
          <section className="rs-card mw-find">
            <div className="rs-card-h"><h3><i className="fas fa-lightbulb" aria-hidden="true" /> Improvement recommendations</h3></div>
            <ul>{recs.map((rec, i) => <li key={i} className={PRI[rec.priority] || ''}><b>{rec.subject}</b> <span className="rs-muted">({rec.score})</span><br />{rec.recommendation}</li>)}</ul>
          </section>)}
      </>) : (
        <Blank icon="fa-chart-line" title="No mock exam results"><p>This student hasn't taken any mock exams in this session yet.</p></Blank>
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
      <MjNav d={d} active="analytics" />
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
          {v && !meta.insufficient && canWrite(d, 'mock_jamb_analytics_export') && <><a href={d.urls.export_pdf} className="btn btn-success" data-native download><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>
          <a href={d.urls.export_excel} className="btn btn-secondary" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a></>}
          <a href={d.urls.analytics} className="btn btn-outline"><i aria-hidden="true" className="fas fa-chart-line" /> Analytics</a>
        </div>
      </div>
      <MjNav d={d} active="validation" />
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
      {canWrite(d, 'mock_jamb_analytics_export') && <>
      <a href={d.urls.export_pdf} className="btn btn-danger btn-sm" title="PDF" data-native download><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>
      <a href={d.urls.export_excel} className="btn btn-success btn-sm" title="Excel" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
      <a href={d.urls.export_image} className="btn btn-info btn-sm" title="HD image" data-native download><i aria-hidden="true" className="fas fa-image" /> Image</a>
      </>}
      {d.urls.items && <a href={d.urls.items} className="btn btn-outline btn-sm" title="Item &amp; topic analysis" data-native><i aria-hidden="true" className="fas fa-microscope" /> Items</a>}
      {d.urls.trends && <a href={d.urls.trends} className="btn btn-outline btn-sm" title="Progress trends"><i aria-hidden="true" className="fas fa-chart-line" /> Trends</a>}
      <a href={d.urls.view} className="btn btn-secondary btn-sm" title="Back"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>
    </>
  );

  const header = (<>
    <div className="page-header">
      <div><h1>Deep Analytics — {d.exam.display_name}</h1>
        <p className="text-muted text-sm">{d.exam.exam_date}{d.exam.session_name ? ` | ${d.exam.session_name}` : ''} · per subject · per teacher · per class arm</p></div>
      <div className="page-header-actions">{actions}</div>
    </div>
    <ExamNav d={d} active="deep" />
  </>);

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

  const header = (<>
    <div className="page-header">
      <div><h1>Progress Trends — Mock JAMB</h1>
        <p className="text-muted text-sm">Track mean score, subjects, teachers and arms across mocks{t && t.meta.multi_session ? ' and across sessions' : ''}.</p></div>
      <div className="page-header-actions">
        {!insufficient && canWrite(d, 'mock_jamb_analytics_export') && <>
          <a href={d.urls.export_pdf} className="btn btn-danger btn-sm" data-native download><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>
          <a href={d.urls.export_excel} className="btn btn-success btn-sm" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
          <a href={d.urls.export_image} className="btn btn-info btn-sm" data-native download><i aria-hidden="true" className="fas fa-image" /> Image</a>
        </>}
        <a href={d.urls.index} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>
      </div>
    </div>
    <MjNav d={d} active="trends" />
  </>);

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
        <div className={'rs bx bx-legacy mj mj-' + d.page}><Screen d={d} notify={notify} /></div>
      </SectionShell>
    </NavCtx.Provider>
  );
}
