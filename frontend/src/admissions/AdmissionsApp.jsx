import React, { useState, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, PageHeader, Empty, SectionTabs, SectionShell } from '../components/ui';

const Tabs = ({ d }) => { const { go } = useNav(); return <SectionTabs tabs={d.tabs} urls={d.urls} active={d.active} go={go} />; };

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const nav = useNav();
  const ref = useRef();
  useEffect(() => {
    if (!ref.current || !window.Chart || !d.class_chart.length) return;
    window.Chart.defaults.color = getComputedStyle(document.body).getPropertyValue('--text-secondary') || '#666';
    const chart = new window.Chart(ref.current, {
      type: 'bar',
      data: { labels: d.class_chart.map((x) => x.name), datasets: [{ data: d.class_chart.map((x) => x.count), backgroundColor: '#4e73df', borderRadius: 5 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } },
    });
    return () => chart.destroy();
  }, [d.class_chart]);

  const s = d.stats;
  const maxc = Math.max(1, ...s.funnel.map((f) => f.count));
  const kpis = [['blue', 'fa-file-lines', s.total, 'Applications'], ['amber', 'fa-hourglass-half', s.pending, 'In pipeline'],
    ['green', 'fa-user-graduate', s.admitted, 'Admitted'], ['red', 'fa-percent', s.conversion + '%', 'Conversion']];
  return (
    <>
      <PageHeader title="Admissions" actions={<a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-user-plus" /> New Application</a>} />
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form"><div className="form-group"><label className="form-label">Session</label>
          <select className="form-control" value={d.session_id} onChange={(e) => navParams(nav.go, d.urls.dashboard, { session_id: e.target.value })}>
            <option value="">All sessions</option>{d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div></div>
      </div></div>

      <div className="kpi-row">{kpis.map(([c, ic, v, l]) => (
        <div className="kpi" key={l}><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div><div><div className="v">{v}</div><div className="l">{l}</div></div></div>))}</div>

      <div className="adm-grid split">
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-filter" /> Pipeline funnel</h3></div>
          <div className="wb"><div className="funnel">
            {s.funnel.map((f) => (
              <div className="funnel-row" key={f.stage}>
                <a className="lab" href={d.urls.applicants + '?' + new URLSearchParams({ status: f.stage, session_id: d.session_id || '' })}>{f.stage}</a>
                <div className="track"><div className="fill" style={{ width: (f.count / maxc * 100) + '%' }}>{f.count}</div></div>
              </div>
            ))}
          </div></div>
        </div>
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-school" /> By intended class</h3></div>
          <div className="wb"><div className="chart-box">
            {d.class_chart.length ? <canvas ref={ref} /> : <Empty icon="fa-school" title="No applications yet" />}
          </div></div>
        </div>
      </div>

      <div className="widget">
        <div className="wh"><h3><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Recent applications</h3><a href={d.urls.applicants} className="text-sm">View all</a></div>
        <div className="wb" style={{ padding: 0 }}>
          {d.recent.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>App No</th><th>Name</th><th>Class</th><th>Status</th><th>Applied</th></tr></thead>
              <tbody>{d.recent.map((a) => (
                <tr key={a.id}><td data-label="App No">{a.application_no}</td>
                  <td data-label="Name"><a href={a.detail_url}>{a.full_name}</a></td>
                  <td data-label="Class">{a.intended_class}</td>
                  <td data-label="Status"><span className={'badge ' + a.status_badge}>{a.status}</span></td>
                  <td data-label="Applied" className="text-muted text-sm">{a.applied}</td></tr>
              ))}</tbody></table></div>
          ) : <Empty icon="fa-user-plus" title="No applications yet" style={{ padding: '1.5rem' }}><a href={d.urls.add} className="btn btn-primary btn-sm mt-2">New application</a></Empty>}
        </div>
      </div>
    </>
  );
}

// ---- Applicants list -------------------------------------------------------
function Applicants({ d }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q || '');
  const params = (over) => ({ status: d.status, session_id: d.session_id, class_id: d.class_id, q, ...over });
  return (
    <>
      <PageHeader title="Applicants" actions={<>
        <a href={d.urls.export} data-native className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-csv" /> Export</a>
        <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-user-plus" /> New Application</a>
      </>} />
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form">
          <div className="form-group"><label className="form-label">Status</label>
            <select className="form-control" value={d.status} onChange={(e) => navParams(nav.go, d.urls.applicants, params({ status: e.target.value }))}>
              <option value="">All</option>{d.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Session</label>
            <select className="form-control" value={d.session_id} onChange={(e) => navParams(nav.go, d.urls.applicants, params({ session_id: e.target.value }))}>
              <option value="">All</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Intended class</label>
            <select className="form-control" value={d.class_id} onChange={(e) => navParams(nav.go, d.urls.applicants, params({ class_id: e.target.value }))}>
              <option value="">All</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <form className="form-group" onSubmit={(e) => { e.preventDefault(); navParams(nav.go, d.urls.applicants, params({})); }}>
            <label className="form-label">Search</label>
            <input type="text" className="form-control" value={q} placeholder="Name, app no, phone" onChange={(e) => setQ(e.target.value)} /></form>
        </div>
      </div></div>
      <div className="card">
        <div className="card-header"><h3>{d.rows.length} applicant(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.rows.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>App No</th><th>Name</th><th>Class</th><th>Parent</th><th>Score</th><th>Status</th><th /></tr></thead>
              <tbody>{d.rows.map((a) => (
                <tr key={a.id}>
                  <td data-label="App No">{a.application_no}</td>
                  <td data-label="Name"><a href={a.detail_url}><strong>{a.full_name}</strong></a>{a.gender && <div className="text-muted text-sm">{a.gender}</div>}</td>
                  <td data-label="Class">{a.intended_class}</td>
                  <td data-label="Parent">{a.parent_name || '—'}{a.parent_phone && <div className="text-muted text-sm">{a.parent_phone}</div>}</td>
                  <td data-label="Score">{a.entrance_score}</td>
                  <td data-label="Status"><span className={'badge ' + a.status_badge}>{a.status}</span>{a.linked && <i aria-hidden="true" className="fas fa-link text-muted" title="Linked to student" style={{ marginLeft: 4 }} />}</td>
                  <td className="actions"><a href={a.detail_url} className="btn btn-secondary btn-sm" aria-label="Open"><i aria-hidden="true" className="fas fa-arrow-right" /></a></td>
                </tr>
              ))}</tbody></table></div>
          ) : <Empty icon="fa-user-plus" title="No applicants"><p>Create an application or adjust filters.</p><a href={d.urls.add} className="btn btn-primary mt-2">New Application</a></Empty>}
        </div>
      </div>
    </>
  );
}

// ---- Applicant form --------------------------------------------------------
function ApplicantForm({ d, notify }) {
  const nav = useNav();
  const a = d.applicant || {};
  const editing = !!d.applicant;
  const [f, setF] = useState({
    first_name: a.first_name || '', surname: a.surname || '', middle_name: a.middle_name || '',
    gender: a.gender || '', date_of_birth: a.date_of_birth || '', previous_school: a.previous_school || '',
    source: a.source || '', session_id: a.session_id ? String(a.session_id) : (editing ? '' : String(d.active_session_id || '')),
    intended_class_id: a.intended_class_id ? String(a.intended_class_id) : '', status: 'Applied',
    entrance_score: a.entrance_score === '' || a.entrance_score == null ? '' : String(a.entrance_score),
    parent_name: a.parent_name || '', relationship: a.relationship || '', parent_phone: a.parent_phone || '',
    parent_email: a.parent_email || '', address: a.address || '', notes: a.notes || '',
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.first_name.trim() || !f.surname.trim()) { notify('error', 'First name and surname are required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const F = ({ label, k, type = 'text', req, ...rest }) => (
    <div className="form-group"><label className="form-label">{label}{req && <span className="required"> *</span>}</label>
      <input type={type} className="form-control" required={req} value={f[k]} onChange={(e) => set(k, e.target.value)} {...rest} /></div>
  );
  return (
    <>
      <PageHeader title={editing ? 'Edit Application' : 'New Application'} />
      <form onSubmit={submit}>
        <div className="card mb-3"><div className="card-header"><h3>Applicant</h3></div><div className="card-body">
          <div className="form-row"><F label="First name" k="first_name" req /><F label="Surname" k="surname" req /></div>
          <div className="form-row"><F label="Middle name" k="middle_name" />
            <div className="form-group"><label className="form-label">Gender</label>
              <select className="form-control" value={f.gender} onChange={(e) => set('gender', e.target.value)}><option value="">—</option><option>Male</option><option>Female</option></select></div>
            <F label="Date of birth" k="date_of_birth" type="date" /></div>
          <div className="form-row"><F label="Previous school" k="previous_school" />
            <div className="form-group"><label className="form-label">How did they hear?</label>
              <select className="form-control" value={f.source} onChange={(e) => set('source', e.target.value)}><option value="">—</option>{d.sources.map((s) => <option key={s}>{s}</option>)}</select></div>
          </div>
        </div></div>

        <div className="card mb-3"><div className="card-header"><h3>Application</h3></div><div className="card-body">
          <div className="form-row">
            <div className="form-group"><label className="form-label">Session</label>
              <select className="form-control" value={f.session_id} onChange={(e) => set('session_id', e.target.value)}><option value="">—</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Intended class</label>
              <select className="form-control" value={f.intended_class_id} onChange={(e) => set('intended_class_id', e.target.value)}><option value="">—</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          </div>
          <div className="form-row">
            {!editing && <div className="form-group"><label className="form-label">Initial status</label>
              <select className="form-control" value={f.status} onChange={(e) => set('status', e.target.value)}>{d.statuses.map((s) => <option key={s}>{s}</option>)}</select></div>}
            <F label="Entrance score" k="entrance_score" type="number" step="0.5" />
          </div>
        </div></div>

        <div className="card mb-3"><div className="card-header"><h3>Parent / Guardian</h3></div><div className="card-body">
          <div className="form-row"><F label="Name" k="parent_name" /><F label="Relationship" k="relationship" placeholder="Father/Mother/Guardian" /></div>
          <div className="form-row"><F label="Phone" k="parent_phone" /><F label="Email" k="parent_email" type="email" /></div>
          <F label="Address" k="address" />
          <div className="form-group mb-0"><label className="form-label">Notes</label><textarea className="form-control" rows="2" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></div>
        </div></div>

        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> {editing ? 'Save Changes' : 'Create Application'}</button>
          <a href={editing ? a.detail_url : d.urls.applicants} className="btn btn-secondary">Cancel</a>
        </div>
      </form>
    </>
  );
}

// ---- Applicant detail ------------------------------------------------------
function ApplicantDetail({ d, notify }) {
  const nav = useNav();
  const a = d.applicant;
  const [busy, setBusy] = useState(false);
  const [assignment, setAssignment] = useState('');
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    setBusy(true);
    const r = await submitJson(url, fields);
    setBusy(false);
    if (r.ok) nav.go(r.redirect || window.location.pathname);
    else notify('error', r.error || 'Action failed.');
  };
  const setStatus = (st) => act(d.urls.status, { status: st });

  return (
    <>
      <PageHeader title="Application" actions={<>
        {a.parent_phone && <a href={'tel:' + a.parent_phone} className="btn btn-secondary" aria-label="Call"><i aria-hidden="true" className="fas fa-phone" /></a>}
        <a href={d.urls.edit} className="btn btn-primary"><i aria-hidden="true" className="fas fa-edit" /> Edit</a>
        {d.is_admin && <button type="button" className="btn btn-danger" disabled={busy}
          onClick={() => act(d.urls.delete, {}, 'Delete this application?')}><i aria-hidden="true" className="fas fa-trash" /></button>}
      </>} />
      <Tabs d={d} />

      <div className="card mb-3"><div className="card-body">
        <div className="d-flex gap-3 align-center flex-wrap">
          <div className="avatar">{a.initials.toUpperCase()}</div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <h2 style={{ margin: 0 }}>{a.full_name}</h2>
            <div className="text-muted">{a.application_no}{a.intended_class && ' · ' + a.intended_class}{a.session && ' · ' + a.session}</div>
            <div className="mt-1"><span className={'badge ' + a.status_badge}>{a.status}</span>
              {a.admitted_student_id && <a href={a.student_url} className="badge badge-success" style={{ marginLeft: 6 }}><i aria-hidden="true" className="fas fa-link" /> View student</a>}</div>
          </div>
        </div>
      </div></div>

      {!a.admitted_student_id && (
        <div className="card mb-3" style={{ borderColor: 'var(--primary)' }}>
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-diagram-project" /> Move through pipeline</h3></div>
          <div className="card-body">
            <div className="pipe mb-2">{d.stages.map((st) => (
              <button key={st} type="button" disabled={busy} className={'btn btn-sm ' + (a.status === st ? 'btn-primary' : 'btn-secondary')} onClick={() => setStatus(st)}>{st}</button>))}</div>
            <div className="pipe">{d.outcomes.map((st) => (
              <button key={st} type="button" disabled={busy} className={'btn btn-sm ' + (a.status === st ? 'btn-danger' : 'btn-secondary')} onClick={() => setStatus(st)}>{st}</button>))}</div>
          </div>
        </div>
      )}

      {!a.admitted_student_id && d.is_admin && (
        <div className="card mb-3" style={{ borderColor: 'var(--success)' }}>
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-user-graduate" /> Admit &amp; convert to student</h3></div>
          <div className="card-body">
            <p className="text-muted text-sm">Creates a student record (with the parent contact) and links it to this application. Optionally enrol into a class arm now.</p>
            <div className="d-flex gap-2 align-end flex-wrap">
              <div className="form-group mb-0" style={{ minWidth: 220 }}><label className="form-label">Enrol into (optional)</label>
                <select className="form-control" value={assignment} onChange={(e) => setAssignment(e.target.value)}>
                  <option value="">Don't enrol yet</option>{d.assignments.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</select></div>
              <button type="button" className="btn btn-success" disabled={busy}
                onClick={() => act(d.urls.convert, { assignment_id: assignment }, `Admit ${a.full_name} and create a student record?`)}>
                <i aria-hidden="true" className="fas fa-user-check" /> Admit &amp; create student</button>
            </div>
            {!a.gender && <p className="text-danger text-sm mt-2"><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Add the applicant's gender (Edit) before converting.</p>}
          </div>
        </div>
      )}

      <div className="adm-2col">
        <div className="card"><div className="card-header"><h3>Applicant details</h3></div>
          <div className="card-body"><div className="info-grid">
            {d.info.map(([k, v]) => <div className="info-row" key={k}><span className="k">{k}</span><span className="v">{v}</span></div>)}
          </div></div></div>
        <div className="card"><div className="card-header"><h3>Parent / Guardian</h3></div>
          <div className="card-body"><div className="info-grid">
            {d.parent.map(([k, v]) => <div className="info-row" key={k}><span className="k">{k}</span><span className="v">{v}</span></div>)}
          </div>{d.notes && <p className="text-muted text-sm mt-2">{d.notes}</p>}</div></div>
      </div>
    </>
  );
}

const SCREENS = { dashboard: Dashboard, applicants: Applicants, applicant_form: ApplicantForm, applicant_detail: ApplicantDetail };

export default function AdmissionsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Dashboard;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
