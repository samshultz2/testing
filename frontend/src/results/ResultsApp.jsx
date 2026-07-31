import React, { useState, useEffect } from 'react';
import { submitJson } from '../lib/forms';
import { useChart } from '../lib/hooks';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';

// Horizontal bar config for the subject-enrolment charts (shared by WAEC/JAMB).
const enrolBarCfg = (rows, color) => ({
  type: 'bar',
  data: {
    labels: rows.slice(0, 12).map((r) => (r.subject.length > 14 ? r.subject.slice(0, 14) + '…' : r.subject)),
    datasets: [{ data: rows.slice(0, 12).map((r) => r.count), backgroundColor: color, borderRadius: 5 }],
  },
  options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } },
});

// ---- Results index ---------------------------------------------------------
function Index({ d }) {
  const u = d.urls;
  const Card = ({ kind, title, sub, count, years, latest, dash, add }) => (
    <div className="result-type-card">
      <div className={'result-type-header ' + kind}><div className="result-type-title">{title}</div><div className="result-type-subtitle">{sub}</div></div>
      <div className="result-type-body">
        <div className="result-stat"><span className="result-stat-label">Total Results</span><span className="result-stat-value">{count}</span></div>
        <div className="result-stat"><span className="result-stat-label">Years with Data</span><span className="result-stat-value">{years.length}</span></div>
        {years.length > 0 && <div className="result-stat"><span className="result-stat-label">Latest Year</span><span className="result-stat-value">{years[0]}</span></div>}
      </div>
      <div className="result-type-actions">
        <a href={dash} className="btn btn-primary"><i aria-hidden="true" className="fas fa-chart-bar" /> View Dashboard</a>
        <a href={add} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-plus" /> Add Results</a>
      </div>
    </div>
  );
  return (
    <>
      <div className="page-header"><h1>Results Management</h1></div>
      <div className="results-overview">
        <Card kind="waec" title="WAEC Results" sub="West African Examinations Council" count={d.waec_count} years={d.waec_years} dash={u.waec_dashboard} add={u.add_waec} />
        <Card kind="jamb" title="JAMB Results" sub="Joint Admissions and Matriculation Board" count={d.jamb_count} years={d.jamb_years} dash={u.jamb_dashboard} add={u.add_jamb} />
      </div>
      <div className="card"><div className="card-header"><h3>Quick Actions</h3></div>
        <div className="card-body"><div className="quick-actions">
          <a href={u.add_waec} className="quick-action-card"><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-plus-circle" /></div><div className="quick-action-label">Add WAEC Result</div></a>
          <a href={u.add_jamb} className="quick-action-card"><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-plus-circle" /></div><div className="quick-action-label">Add JAMB Result</div></a>
          {d.waec_years.length > 0 && <a href={u.export_waec} className="quick-action-card" data-native download><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-file-excel" /></div><div className="quick-action-label">Export WAEC {d.waec_years[0]}</div></a>}
          {d.jamb_years.length > 0 && <a href={u.export_jamb} className="quick-action-card" data-native download><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-file-excel" /></div><div className="quick-action-label">Export JAMB {d.jamb_years[0]}</div></a>}
        </div></div></div>
      <div className="card"><div className="card-header"><h3>Analytics Features</h3></div>
        <div className="card-body"><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
          {[['fa-chart-line', '#007bff', 'Performance Trends', 'Track year-over-year performance, pass rates, and grade distributions.'],
            ['fa-user-graduate', 'var(--success)', 'Student Profiles', 'Individual student analytics with strengths, weaknesses, and predictions.'],
            ['fa-calculator', 'var(--warning)', 'JAMB Predictions', 'ML-based JAMB score predictions from WAEC performance.'],
            ['fa-exclamation-triangle', 'var(--danger)', 'Risk Assessment', 'Identify at-risk students with actionable recommendations.']].map(([ic, col, t, p]) => (
            <div key={t} style={{ padding: '1rem', background: 'var(--gray-50)', borderRadius: 8 }}>
              <h4 style={{ marginBottom: '.5rem' }}><i aria-hidden="true" className={'fas ' + ic} style={{ color: col }} /> {t}</h4>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', margin: 0 }}>{p}</p></div>))}
        </div></div></div>
    </>
  );
}

// ---- Exam readiness --------------------------------------------------------
function Readiness({ d }) {
  return (
    <>
      <div className="page-header"><div><h1>Exam Readiness</h1><p className="text-muted text-sm">Who still needs attention before WAEC/JAMB — SSS3 cohort</p></div></div>
      <div className="kpi-grid">
        <div className="kpi good"><div className="v">{d.ready}</div><div className="l">Fully ready</div></div>
        <div className="kpi"><div className="v">{d.total}</div><div className="l">SSS3 candidates</div></div>
        {d.groups.slice(0, 2).map((g) => (
          <div className="kpi" key={g.key}><div className="v" style={{ color: g.students.length ? 'var(--danger)' : 'var(--success)' }}>{g.students.length}</div><div className="l">{g.title}</div></div>))}
      </div>
      {d.groups.map((g) => (
        <details className={'rgroup' + (g.students.length ? '' : ' clear')} open={g.students.length > 0} key={g.key}>
          <summary><span><i aria-hidden="true" className={'fas ' + g.icon} /> {g.title}</span><span className="count">{g.students.length}</span></summary>
          {g.students.length ? (
            <div className="slist">{g.students.map((s) => (
              <div className="srow" key={s.id}><span>{s.full_name} <span className="text-muted">{s.student_id}</span></span>
                <span><a href={s.action.url}>{s.action.label}</a></span></div>))}</div>
          ) : <div style={{ padding: '.75rem 1rem', color: 'var(--success)', fontSize: 'var(--text-sm)' }}><i aria-hidden="true" className="fas fa-check-circle" /> All good here.</div>}
        </details>))}
    </>
  );
}

// ---- Subject enrolment -----------------------------------------------------
function SubjectEnrolment({ d }) {
  const waecRef = useChart(() => (d.waec_rows.length ? enrolBarCfg(d.waec_rows, '#11998e') : null), [d]);
  const jambRef = useChart(() => (d.jamb_rows.length ? enrolBarCfg(d.jamb_rows, '#667eea') : null), [d]);

  const Table = ({ rows, enrolled, jamb }) => (
    rows.length ? (
      <table className="enrol-table">
        <thead><tr><th>Subject</th><th className="num">Students</th><th className="num">%</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.subject}>
            <td><a href={r.url}>{r.subject}</a><div className={'bar' + (jamb ? ' jamb' : '')}><span style={{ width: (enrolled ? r.count / enrolled * 100 : 0) + '%' }} /></div></td>
            <td className="num"><strong>{r.count}</strong></td><td className="num">{r.pct}%</td>
          </tr>))}</tbody>
      </table>
    ) : <Empty icon="fa-inbox" title=""><p>No {jamb ? 'JAMB' : 'WAEC'} subjects recorded yet. Add them on student profiles.</p></Empty>
  );

  return (
    <>
      <div className="page-header"><div><h1>Subject Enrolment</h1><p className="text-muted text-sm">How many students are registered for each WAEC / JAMB subject</p></div></div>
      <div className="scope-tabs">
        <a href={d.urls.sss3} className={'scope-tab' + (d.only_sss3 ? ' active' : '')}>SSS3 / Exam candidates</a>
        <a href={d.urls.all} className={'scope-tab' + (d.only_sss3 ? '' : ' active')}>All active students</a>
      </div>
      <div className="kpi-grid mb-3">
        <div className="kpi-card lead">
          <div className="kpi-head"><span className="kpi-label">Students in scope</span><span className="kpi-icon"><i aria-hidden="true" className="fas fa-users" /></span></div>
          <div className="kpi-value">{d.student_count}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-head"><span className="kpi-label">With WAEC subjects</span><span className="kpi-icon"><i aria-hidden="true" className="fas fa-file-alt" /></span></div>
          <div className="kpi-value">{d.waec_enrolled}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-head"><span className="kpi-label">With JAMB subjects</span><span className="kpi-icon"><i aria-hidden="true" className="fas fa-file-contract" /></span></div>
          <div className="kpi-value">{d.jamb_enrolled}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-head"><span className="kpi-label">Distinct WAEC subjects</span><span className="kpi-icon"><i aria-hidden="true" className="fas fa-list" /></span></div>
          <div className="kpi-value">{d.waec_rows.length}</div>
        </div>
      </div>
      <div className="enrol-grid">
        <div className="card">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-alt" /> WAEC Subjects</h3></div>
          <div className="chart-wrap"><canvas ref={waecRef} /></div>
          <div className="card-body" style={{ padding: 0, maxHeight: 420, overflow: 'auto' }}><Table rows={d.waec_rows} enrolled={d.waec_enrolled} /></div>
        </div>
        <div className="card">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-contract" /> JAMB Subjects</h3></div>
          <div className="chart-wrap"><canvas ref={jambRef} /></div>
          <div className="card-body" style={{ padding: 0, maxHeight: 420, overflow: 'auto' }}><Table rows={d.jamb_rows} enrolled={d.jamb_enrolled} jamb /></div>
        </div>
      </div>
    </>
  );
}

// ---- Subject enrolment detail ----------------------------------------------
function SubjectEnrolmentDetail({ d }) {
  return (
    <>
      <div className="page-header">
        <div><h1>{d.subject}</h1>
          <p className="text-muted text-sm">
            <span className={'badge ' + (d.exam === 'jamb' ? 'badge-primary' : 'badge-info')}>{d.exam_label}</span>{' '}
            {d.students.length} student{d.students.length === 1 ? '' : 's'} enrolled · {d.only_sss3 ? 'SSS3 / exam candidates' : 'all active students'}
          </p></div>
        <div className="page-header-actions"><a href={d.back_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a></div>
      </div>
      <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-users" /> Enrolled Students ({d.students.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.students.length ? (
            <div className="data-cards" style={{ padding: '1rem' }}>{d.students.map((s) => (
              <div className="data-card" key={s.id}>
                <div className="data-card-header"><div className="data-card-title">{s.full_name}{s.is_graduated && <span className="badge badge-success" title="Graduate"><i aria-hidden="true" className="fas fa-user-graduate" /></span>}</div>
                  <span className={'badge ' + (s.gender === 'Male' ? 'badge-male' : 'badge-female')}>{s.gender}</span></div>
                <div className="data-card-row"><span className="data-card-label">ID</span><span>{s.student_id}</span></div>
                <div className="data-card-actions"><a href={s.view_url} className="btn btn-secondary btn-sm w-100"><i aria-hidden="true" className="fas fa-eye" /> View Profile</a></div>
              </div>))}</div>
          ) : <Empty icon="fa-user-slash" title=""><p>No students enrolled for {d.subject} in this scope.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Admission cut-offs ----------------------------------------------------
function Cutoffs({ d, notify }) {
  const nav = useNav();
  const e = d.editing;
  const blank = { id: '', university_name: d.selected, course_name: '', faculty: '', jamb_cutoff: '', min_credits: 5, exam_year: 0, required_subjects: [] };
  const [f, setF] = useState(e ? { ...e, jamb_cutoff: e.jamb_cutoff ?? '' } : blank);
  const [ref, setRef] = useState(d.reference);
  useEffect(() => { setF(d.editing ? { ...d.editing, jamb_cutoff: d.editing.jamb_cutoff ?? '' } : blank); /* eslint-disable-next-line */ }, [d.editing, d.selected]);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const toggleSubj = (s) => setF((x) => ({ ...x, required_subjects: x.required_subjects.includes(s) ? x.required_subjects.filter((y) => y !== s) : [...x.required_subjects, s] }));

  const save = async (ev) => {
    ev.preventDefault();
    if (!f.course_name.trim()) { notify('error', 'Course name is required.'); return; }
    const r = await submitJson(d.urls.save, { id: f.id || '', university_name: f.university_name, course_name: f.course_name,
      faculty: f.faculty, jamb_cutoff: f.jamb_cutoff, min_credits: f.min_credits, exam_year: f.exam_year,
      'required_subjects[]': f.required_subjects });
    if (r.ok) { notify('success', r.message); nav.go(r.redirect); } else notify('error', r.error || 'Could not save.');
  };
  const del = async (url, course) => {
    if (!await confirm(`Delete ${course}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  const setRefSubmit = async (ev) => {
    ev.preventDefault();
    const r = await submitJson(d.urls.reference, { reference: ref });
    if (r.ok) { notify('success', r.message); nav.go(r.redirect); } else notify('error', r.error || 'Could not set.');
  };

  return (
    <>
      <div className="page-header">
        <div><h1>Admission Cut-offs</h1><p className="text-muted text-sm">Manage course requirements used by the admission advisor.</p></div>
        <div className="page-header-actions"><a href={d.urls.analytics} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a></div>
      </div>
      <div className="toolbar">
        <form className="d-flex gap-2 align-center" onSubmit={(ev) => ev.preventDefault()}>
          <label className="form-label mb-0">University</label>
          <select className="form-control" style={{ maxWidth: 240 }} value={d.selected} onChange={(ev) => navParams(nav.go, d.self_url, { university: ev.target.value })}>
            {d.universities.map((u) => <option key={u} value={u}>{u}</option>)}</select>
        </form>
        {d.is_admin && (
          <form className="d-flex gap-2 align-center" style={{ marginLeft: 'auto' }} onSubmit={setRefSubmit}>
            <label className="form-label mb-0" title="Which set the advisor uses">Advisor uses</label>
            <select className="form-control" style={{ maxWidth: 240 }} value={ref} onChange={(ev) => setRef(ev.target.value)}>
              {d.universities.map((u) => <option key={u} value={u}>{u}</option>)}</select>
            <button className="btn btn-primary btn-sm" type="submit">Set</button>
          </form>)}
      </div>

      <div className="cut-grid">
        {d.is_admin && (
          <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-pen" /> {e ? 'Edit' : 'Add'} Cut-off</h3></div>
            <div className="card-body"><form onSubmit={save}>
              <div className="form-group"><label className="form-label">University</label>
                <input type="text" className="form-control" list="unis" required value={f.university_name} onChange={(ev) => set('university_name', ev.target.value)} />
                <datalist id="unis">{d.universities.map((u) => <option key={u} value={u} />)}</datalist></div>
              <div className="form-group"><label className="form-label">Course <span className="text-danger">*</span></label>
                <input type="text" className="form-control" required value={f.course_name} onChange={(ev) => set('course_name', ev.target.value)} /></div>
              <div className="form-row">
                <div className="form-group"><label className="form-label">Faculty</label><input type="text" className="form-control" value={f.faculty} onChange={(ev) => set('faculty', ev.target.value)} /></div>
                <div className="form-group"><label className="form-label">JAMB cut-off</label><input type="number" className="form-control" min="0" max="400" value={f.jamb_cutoff} onChange={(ev) => set('jamb_cutoff', ev.target.value)} /></div>
              </div>
              <div className="form-row">
                <div className="form-group"><label className="form-label">Min credits</label><input type="number" className="form-control" min="1" max="9" value={f.min_credits} onChange={(ev) => set('min_credits', ev.target.value)} /></div>
                <div className="form-group"><label className="form-label">Exam year <span className="text-muted">(0 = generic)</span></label><input type="number" className="form-control" min="0" max="2100" value={f.exam_year} onChange={(ev) => set('exam_year', ev.target.value)} /></div>
              </div>
              <div className="form-group"><label className="form-label">Required O'level credits</label>
                <div className="subject-checks">{d.subjects.map((s) => (
                  <label className="subject-check" key={s}><input type="checkbox" checked={f.required_subjects.includes(s)} onChange={() => toggleSubj(s)} /> {s}</label>))}</div></div>
              <div className="d-flex gap-2">
                <button className="btn btn-primary" type="submit"><i aria-hidden="true" className="fas fa-save" /> {e ? 'Update' : 'Add'}</button>
                {e && <a href={d.self_url + '?university=' + encodeURIComponent(d.selected)} className="btn btn-secondary">Cancel</a>}
              </div>
            </form></div></div>
        )}
        <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-list" /> {d.selected} ({d.rows.length})</h3></div>
          <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
            {d.rows.length ? (
              <table className="ctable">
                <thead><tr><th>Course</th><th>Faculty</th><th>JAMB</th><th>Credits</th><th>Required</th>{d.is_admin && <th />}</tr></thead>
                <tbody>{d.rows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.course_name}</td><td className="text-muted">{r.faculty}</td>
                    <td>{r.jamb_cutoff || '—'}</td><td>{r.min_credits}</td>
                    <td style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>{r.required_subjects.join(', ')}</td>
                    {d.is_admin && <td style={{ whiteSpace: 'nowrap' }}>
                      <a href={r.edit_url} className="btn btn-warning btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>{' '}
                      <button className="btn btn-danger btn-sm" type="button" onClick={() => del(r.delete_url, r.course_name)}><i aria-hidden="true" className="fas fa-trash" /></button>
                    </td>}
                  </tr>))}</tbody>
              </table>
            ) : <Empty icon="fa-inbox" title="" style={{ padding: '1.5rem' }}><p>No cut-offs for {d.selected}. Add one on the left.</p></Empty>}
          </div></div>
      </div>
    </>
  );
}

const SCREENS = { index: Index, readiness: Readiness, subject_enrolment: SubjectEnrolment,
  subject_enrolment_detail: SubjectEnrolmentDetail, cutoffs: Cutoffs };

export default function ResultsApp({ data }) {
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
