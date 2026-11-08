import React, { useState, useEffect } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Blank, Ring } from '../subjects/results';

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
        {d.neco_years && <Card kind="neco" title="NECO Results" sub="National Examinations Council (SSCE)" count={d.neco_count} years={d.neco_years} dash={u.neco_dashboard} add={u.add_neco} />}
        <Card kind="jamb" title="JAMB Results" sub="Joint Admissions and Matriculation Board" count={d.jamb_count} years={d.jamb_years} dash={u.jamb_dashboard} add={u.add_jamb} />
      </div>
      <div className="card"><div className="card-header"><h3>Quick Actions</h3></div>
        <div className="card-body"><div className="quick-actions">
          <a href={u.add_waec} className="quick-action-card"><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-plus-circle" /></div><div className="quick-action-label">Add WAEC Result</div></a>
          {u.add_neco && <a href={u.add_neco} className="quick-action-card"><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-plus-circle" /></div><div className="quick-action-label">Add NECO Result</div></a>}
          <a href={u.add_jamb} className="quick-action-card"><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-plus-circle" /></div><div className="quick-action-label">Add JAMB Result</div></a>
          {d.waec_years.length > 0 && <a href={u.export_waec} className="quick-action-card" data-native download><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-file-excel" /></div><div className="quick-action-label">Export WAEC {d.waec_years[0]}</div></a>}
          {d.neco_years && d.neco_years.length > 0 && <a href={u.export_neco} className="quick-action-card" data-native download><div className="quick-action-icon"><i aria-hidden="true" className="fas fa-file-excel" /></div><div className="quick-action-label">Export NECO {d.neco_years[0]}</div></a>}
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

// ---- Shared exam-analytics tabs (same links as the server pages) ----------
const AX_TABS = [['hub', 'fa-chart-pie', 'Overview'], ['insights', 'fa-microscope', 'Insights'], ['trends', 'fa-chart-line', 'Trends'],
  ['readiness', 'fa-list-check', 'Readiness'], ['funnel', 'fa-filter', 'Admission funnel'], ['predictions', 'fa-wand-magic-sparkles', 'Predictions'],
  ['focus', 'fa-bullseye', 'Focus areas'], ['enrolment', 'fa-book-open', 'Subject enrolment']];
function AxNav({ d, active }) {
  if (!d.axnav) return null;
  return (
    <nav className="sl-nav ax-nav" aria-label="Exam analytics">
      {AX_TABS.map(([k, ic, l]) => d.axnav[k] && (
        <a key={k} href={d.axnav[k]} className={active === k ? 'on' : ''} data-native={['readiness', 'enrolment'].includes(k) ? undefined : ''}>
          <i className={'fas ' + ic} aria-hidden="true" /><span>{l}</span></a>))}
    </nav>
  );
}

// ---- Exam readiness --------------------------------------------------------
const R_TONE = { no_jamb: 'bad', no_waec: 'bad', below_target: 'mid', no_stream: 'mid', no_jamb_subjects: 'mid', no_waec_subjects: 'mid' };
function Readiness({ d }) {
  const [open, setOpen] = useState(() => (d.groups.find((g) => g.students.length) || {}).key || null);
  const [q, setQ] = useState('');
  const pct = d.total ? Math.round(d.ready / d.total * 100) : 0;
  // Students who appear in several gaps come first — they need the most help.
  const gaps = {};
  d.groups.forEach((g) => g.students.forEach((s) => { (gaps[s.id] = gaps[s.id] || { s, keys: [] }).keys.push(g.title); }));
  const worst = Object.values(gaps).filter((x) => x.keys.length > 1).sort((a, b) => b.keys.length - a.keys.length).slice(0, 8);
  const g = d.groups.find((x) => x.key === open);
  const shown = g ? g.students.filter((s) => !q || (s.full_name + ' ' + s.student_id).toLowerCase().includes(q.toLowerCase())) : [];
  return (
    <>
      <Head icon="fa-list-check" title="Exam Readiness" sub="Who still needs attention before WAEC / JAMB — SSS3 cohort" />
      <AxNav d={d} active="readiness" />
      <div className="bx-two rd-top">
        <section className="rs-card rd-hero">
          <Ring value={pct} label="ready" />
          <div>
            <h3>{d.ready} of {d.total} candidates are fully ready</h3>
            <p className="rs-muted">Ready means: a Mock JAMB and a Mock WAEC result, at or above their JAMB target, a stream set, and both subject lists on the profile.</p>
            <div className="rd-chips">{d.groups.map((x) => (
              <button key={x.key} type="button" className={'rs-chip' + (open === x.key ? ' on' : '')} onClick={() => setOpen(x.key)}>
                {x.title.replace(/ yet$/, '')} <small>{x.students.length}</small></button>))}</div>
          </div>
        </section>
        <section className="rs-card flush">
          <div className="rs-card-h pad"><h3><i className="fas fa-user-clock" aria-hidden="true" /> Most gaps first</h3><small>students missing several items</small></div>
          {worst.length ? (
            <div className="bx-rank">{worst.map(({ s, keys }) => (
              <div className="bx-rank-row jx-rank" key={s.id}>
                <span className="bx-pos sm">{keys.length}</span>
                <span className="n"><b>{s.full_name}</b><small>{keys.join(' · ')}</small></span>
                <span />
                <a href={s.action.url} className="rs-btn ghost sm">{s.action.label}</a>
              </div>))}</div>
          ) : <p className="rs-muted bx-pad">No student is missing more than one item.</p>}
        </section>
      </div>

      <div className="rd-grid">
        {d.groups.map((x) => {
          const n = x.students.length; const done = d.total ? Math.round((d.total - n) / d.total * 100) : 100;
          return (
            <button key={x.key} type="button" className={'rd-card' + (open === x.key ? ' on' : '') + (n ? ' ' + R_TONE[x.key] : ' good')} onClick={() => setOpen(x.key)}>
              <span className="ic"><i className={'fas ' + (n ? x.icon : 'fa-circle-check')} aria-hidden="true" /></span>
              <span className="t"><b>{x.title}</b><small>{n ? n + ' student' + (n === 1 ? '' : 's') : 'All clear'}</small></span>
              <span className="rs-meter good"><i style={{ width: done + '%' }} /></span>
            </button>);
        })}
      </div>

      {g && (
        <section className="rs-card flush">
          <div className="bx-filters">
            <h3 className="rd-h"><i className={'fas ' + g.icon} aria-hidden="true" /> {g.title} <span className="sl-pill">{g.students.length}</span></h3>
            {g.students.length > 6 && <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" placeholder="Find a student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student" /></label>}
          </div>
          {g.students.length ? (
            <div className="rd-list">{shown.map((s) => (
              <div className="rd-row" key={s.id}>
                <span className="n"><b>{s.full_name}</b><small>{s.student_id}</small></span>
                <a href={s.action.url} className="rs-btn ghost sm"><i className="fas fa-arrow-right" aria-hidden="true" /> {s.action.label}</a>
              </div>))}</div>
          ) : <Blank icon="fa-circle-check" title="All good here"><p>Every SSS3 candidate is clear on this item.</p></Blank>}
        </section>
      )}
    </>
  );
}

// ---- Subject enrolment -----------------------------------------------------
function EnrolList({ rows, enrolled, label }) {
  const [all, setAll] = useState(false);
  if (!rows.length) return <Blank icon="fa-inbox" title={'No ' + label + ' subjects yet'}><p>Add them on student profiles.</p></Blank>;
  const list = all ? rows : rows.slice(0, 12);
  return (
    <>
      <div className="an-hbars">
        {list.map((r) => (
          <a key={r.subject} className="an-hbar bx-hbar" href={r.url}>
            <span className="l">{r.subject}<small>{r.pct}% of {label} candidates</small></span>
            <span className="t"><i className={label === 'JAMB' ? '' : 'good'} style={{ width: (enrolled ? r.count / enrolled * 100 : 0) + '%' }} /></span>
            <b>{r.count}</b>
          </a>))}
      </div>
      {rows.length > 12 && <button type="button" className="rs-btn ghost sm bx-cap" onClick={() => setAll((v) => !v)}>
        <i className={'fas fa-chevron-' + (all ? 'up' : 'down')} aria-hidden="true" /> {all ? 'Show fewer' : 'Show all ' + rows.length + ' subjects'}</button>}
    </>
  );
}

function SubjectEnrolment({ d }) {
  const nav = useNav();
  const issues = d.waec_mismatches.length + d.jamb_mismatches.length;
  const pct = (n) => (d.student_count ? Math.round(n / d.student_count * 100) : 0);
  return (
    <>
      <Head icon="fa-book-open" title="Subject Enrolment" sub="How many students are registered for each WAEC / JAMB subject — plan classes, papers and registration">
        <Seg options={[{ value: 'sss3', label: 'SSS3 / candidates' }, { value: 'all', label: 'All students' }]} value={d.only_sss3 ? 'sss3' : 'all'}
             onChange={(v) => nav.go(d.urls[v])} label="Scope" />
      </Head>
      <AxNav d={d} active="enrolment" />
      <Tiles items={[
        { label: 'Students in scope', value: d.student_count, sub: d.only_sss3 ? 'SSS3 / exam candidates' : 'all active students' },
        { label: 'With WAEC subjects', value: d.waec_enrolled, sub: pct(d.waec_enrolled) + '% · ' + d.waec_rows.length + ' distinct subjects', tone: pct(d.waec_enrolled) >= 90 ? 'good' : 'mid' },
        { label: 'With JAMB subjects', value: d.jamb_enrolled, sub: pct(d.jamb_enrolled) + '% · ' + d.jamb_rows.length + ' distinct subjects', tone: pct(d.jamb_enrolled) >= 90 ? 'good' : 'mid' },
        { label: 'Subject-count issues', value: issues, sub: 'WAEC must be ' + d.waec_expected + ', JAMB ' + d.jamb_expected, tone: issues ? 'bad' : 'good' },
      ]} />
      {issues > 0 && (
        <div className="bx-two">
          {d.waec_mismatches.length > 0 && <MismatchGroup icon="fa-file-alt" title="WAEC subject count issues"
            hint={`SSS3 / exam candidates (${d.sss3_count}) who don't have exactly ${d.waec_expected} WAEC subjects`} expected={d.waec_expected} rows={d.waec_mismatches} />}
          {d.jamb_mismatches.length > 0 && <MismatchGroup icon="fa-file-contract" title="JAMB subject count issues"
            hint={`SSS3 / exam candidates (${d.sss3_count}) who don't have exactly ${d.jamb_expected} JAMB subjects`} expected={d.jamb_expected} rows={d.jamb_mismatches} />}
        </div>)}
      <div className="bx-two">
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-file-alt" aria-hidden="true" /> WAEC Subjects</h3><small>{d.waec_enrolled} candidates · tap a subject for the list</small></div>
          <EnrolList rows={d.waec_rows} enrolled={d.waec_enrolled} label="WAEC" />
        </section>
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-file-contract" aria-hidden="true" /> JAMB Subjects</h3><small>{d.jamb_enrolled} candidates · tap a subject for the list</small></div>
          <EnrolList rows={d.jamb_rows} enrolled={d.jamb_enrolled} label="JAMB" />
        </section>
      </div>
    </>
  );
}

// A list of students whose subject count doesn't match the fixed exam rule
// (WAEC = 9, JAMB = 4) — click through to fix it on their profile.
function MismatchGroup({ icon, title, hint, expected, rows }) {
  return (
    <section className="rs-card flush">
      <div className="rs-card-h pad"><h3><i className={'fas ' + icon} aria-hidden="true" /> {title}</h3><span className="sl-pill bad">{rows.length}</span></div>
      <p className="rs-muted bx-small bx-pad" style={{ paddingTop: 0, paddingBottom: '.4rem' }}>{hint}</p>
      <div className="rd-list rd-scroll">{rows.map((r) => (
        <div className="rd-row" key={r.id}>
          <span className="n"><b>{r.name}</b><small>{r.student_id}</small></span>
          <span className={'sl-pill ' + (r.count > expected ? 'bad' : 'mid')}>{r.count} of {expected}</span>
          <a href={r.edit_url} className="rs-btn ghost sm"><i className="fas fa-pen" aria-hidden="true" /> Fix</a>
        </div>))}</div>
    </section>
  );
}

// ---- Subject enrolment detail ----------------------------------------------
function SubjectEnrolmentDetail({ d }) {
  const [q, setQ] = useState('');
  const shown = d.students.filter((s) => !q || (s.full_name + ' ' + s.student_id).toLowerCase().includes(q.toLowerCase()));
  const m = d.students.filter((s) => s.gender === 'Male').length;
  return (
    <>
      <Head icon="fa-book-open" title={d.subject} sub={`${d.exam_label} · ${d.students.length} student${d.students.length === 1 ? '' : 's'} enrolled · ${d.only_sss3 ? 'SSS3 / exam candidates' : 'all active students'}`}>
        <a href={d.back_url} className="rs-btn ghost"><i className="fas fa-arrow-left" aria-hidden="true" /><span className="rs-hide-sm">All subjects</span></a>
      </Head>
      <AxNav d={d} active="enrolment" />
      <Tiles items={[{ label: 'Enrolled', value: d.students.length, sub: d.exam_label },
        { label: 'Boys', value: m }, { label: 'Girls', value: d.students.length - m },
        { label: 'Graduates', value: d.students.filter((s) => s.is_graduated).length }]} />
      <section className="rs-card flush">
        <div className="bx-filters"><label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Find a student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student" /></label></div>
        {d.students.length ? (
          <div className="rd-list">{shown.map((s) => (
            <a className="rd-row" key={s.id} href={s.view_url}>
              <span className="n"><b>{s.full_name}{s.is_graduated && <span className="sl-pill good" title="Graduate"> Graduate</span>}</b><small>{s.student_id}</small></span>
              <span className={'sl-pill ' + (s.gender === 'Male' ? 'info' : '')}>{s.gender}</span>
              <i className="fas fa-chevron-right rs-muted" aria-hidden="true" />
            </a>))}</div>
        ) : <Blank icon="fa-user-slash" title="Nobody enrolled"><p>No students enrolled for {d.subject} in this scope.</p></Blank>}
      </section>
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
        {canWrite(d, 'cutoffs_write') && (
          <form className="d-flex gap-2 align-center" style={{ marginLeft: 'auto' }} onSubmit={setRefSubmit}>
            <label className="form-label mb-0" title="Which set the advisor uses">Advisor uses</label>
            <select className="form-control" style={{ maxWidth: 240 }} value={ref} onChange={(ev) => setRef(ev.target.value)}>
              {d.universities.map((u) => <option key={u} value={u}>{u}</option>)}</select>
            <button className="btn btn-primary btn-sm" type="submit">Set</button>
          </form>)}
      </div>

      <div className="cut-grid">
        {canWrite(d, 'cutoffs_write') && (
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
                <thead><tr><th>Course</th><th>Faculty</th><th>JAMB</th><th>Credits</th><th>Required</th>{(canWrite(d, 'cutoffs_write') || canWrite(d, 'cutoffs_delete')) && <th />}</tr></thead>
                <tbody>{d.rows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.course_name}</td><td className="text-muted">{r.faculty}</td>
                    <td>{r.jamb_cutoff || '—'}</td><td>{r.min_credits}</td>
                    <td style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>{r.required_subjects.join(', ')}</td>
                    {(canWrite(d, 'cutoffs_write') || canWrite(d, 'cutoffs_delete')) && <td style={{ whiteSpace: 'nowrap' }}>
                      {canWrite(d, 'cutoffs_write') && <a href={r.edit_url} className="btn btn-warning btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>}{' '}
                      {canWrite(d, 'cutoffs_delete') && <button className="btn btn-danger btn-sm" type="button" onClick={() => del(r.delete_url, r.course_name)}><i aria-hidden="true" className="fas fa-trash" /></button>}
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
        <div className={'rs bx ' + (['readiness', 'subject_enrolment', 'subject_enrolment_detail', 'cutoffs'].includes(d.page) ? 'rx-' + d.page : 'bx-legacy')}><Screen d={d} notify={notify} /></div>
      </SectionShell>
    </NavCtx.Provider>
  );
}
