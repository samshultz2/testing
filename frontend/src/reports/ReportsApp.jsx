import React, { useState, useEffect, useRef } from 'react';
import { postFile } from '../lib/forms';
import { useSection, NavCtx, useNav } from '../lib/section';
import { Banner, PageHeader, Empty, SectionShell } from '../components/ui';

// ---- Index hub -------------------------------------------------------------
function Index({ d }) {
  const cards = [
    ['summary', 'primary', 'fa-chart-line', 'Summary', 'Overview'],
    ['import', 'success', 'fa-file-import', 'Import', 'From Excel'],
    ['export_students', 'info', 'fa-file-export', 'Export', 'Students'],
    ['export_template', 'secondary', 'fa-file-download', 'Template', 'Download'],
  ];
  return (
    <>
      <PageHeader title="Reports" />
      <div className="stats-grid">
        {cards.map(([key, tone, icon, title, sub]) => (
          <a key={key} href={d.urls[key]} data-native={['export_students', 'export_template'].includes(key) || undefined} className="stat-card" style={{ textDecoration: 'none' }}>
            <div className={'stat-icon ' + tone}><i aria-hidden="true" className={'fas ' + icon} /></div>
            <div className="stat-content"><h3>{title}</h3><p>{sub}</p></div>
          </a>
        ))}
      </div>
    </>
  );
}

// ---- Summary ---------------------------------------------------------------
function ChartCard({ title, url, type }) {
  const ref = useRef();
  useEffect(() => {
    let chart;
    (async () => {
      try {
        const res = await fetch(url, { credentials: 'same-origin' });
        const data = await res.json();
        if (!ref.current || !window.Chart) return;
        window.Chart.defaults.color = getComputedStyle(document.body).getPropertyValue('--text-secondary') || '#666';
        chart = new window.Chart(ref.current, {
          type,
          data: { labels: data.labels, datasets: [{
            data: data.data, backgroundColor: data.backgroundColor || '#4e73df',
            borderColor: data.borderColor, fill: type === 'line', tension: 0.3, borderRadius: type === 'bar' ? 5 : 0 }] },
          options: { maintainAspectRatio: false, plugins: { legend: { display: type === 'doughnut', position: 'bottom' } },
            scales: type === 'doughnut' ? {} : { y: { beginAtZero: true, ticks: { precision: 0 } } } },
        });
      } catch (_) { /* ignore */ }
    })();
    return () => chart && chart.destroy();
  }, [url, type]);
  return (
    <div className="card mb-3">
      <div className="card-header"><h3>{title}</h3></div>
      <div className="card-body"><div className="chart-container"><canvas ref={ref} /></div></div>
    </div>
  );
}

function Summary({ d }) {
  const k = d.kpis;
  const kpis = [['primary', 'fa-users', k.total, 'Total'], ['info', 'fa-male', k.male, 'Male'],
    ['secondary', 'fa-female', k.female, 'Female'], ['success', 'fa-user-check', k.enrolled, 'Enrolled']];
  const q = d.quick_info;
  return (
    <>
      <PageHeader title="Summary Report" />
      <div className="stats-grid">{kpis.map(([t, ic, v, l]) => (
        <div className="stat-card" key={l}><div className={'stat-icon ' + t}><i aria-hidden="true" className={'fas ' + ic} /></div>
          <div className="stat-content"><h3>{v}</h3><p>{l}</p></div></div>))}</div>
      <ChartCard title="Gender Distribution" url={d.chart_urls.gender} type="doughnut" />
      <ChartCard title="Attendance Trend" url={d.chart_urls.attendance} type="line" />
      <div className="card"><div className="card-header"><h3>Quick Info</h3></div>
        <div className="card-body"><div className="info-grid">
          <div className="info-row"><span className="text-muted">Active Session</span><strong>{q.session}</strong></div>
          <div className="info-row"><span className="text-muted">Active Term</span><strong>{q.term}</strong></div>
          <div className="info-row"><span className="text-muted">With WAEC</span><strong>{q.with_waec}</strong></div>
          <div className="info-row"><span className="text-muted">With JAMB</span><strong>{q.with_jamb}</strong></div>
        </div></div></div>
    </>
  );
}

// ---- Export class students -------------------------------------------------
function ExportClass({ d }) {
  const nav = useNav();
  return (
    <>
      <PageHeader title="Export Class Students" />
      <div className="card"><div className="card-header"><h3>Select Class to Export</h3></div>
        <div className="card-body">
          <div className="filter-form"><div className="form-group"><label className="form-label">Term</label>
            <select className="form-control" value={d.term_id} onChange={(e) => { nav.go(d.urls.self + '?term_id=' + e.target.value); }}>
              <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></div></div>

          {d.assignments.length ? (<>
            <h4 style={{ margin: '1.5rem 0 1rem' }}>Classes</h4>
            <div className="data-cards">{d.assignments.map((a) => (
              <div className="data-card" key={a.id}>
                <div className="data-card-header"><div className="data-card-title">{a.display_name}</div></div>
                <div className="data-card-row"><span className="data-card-label">Students</span><span>{a.student_count}</span></div>
                <div className="data-card-actions"><a href={a.export_url} data-native className="btn btn-success btn-sm w-100"><i aria-hidden="true" className="fas fa-download" /> Export</a></div>
              </div>
            ))}</div>
          </>) : d.term_id ? <Empty icon="fa-school" title="No Classes" style={{ marginTop: '1rem' }}><p>No class assignments for this term</p></Empty>
            : <Empty icon="fa-hand-pointer" title="Select a Term" style={{ marginTop: '1rem' }}><p>Choose a term to see available classes</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Import students -------------------------------------------------------
function Import({ d, notify }) {
  const [file, setFile] = useState(null);
  const [classId, setClassId] = useState('');
  const [armId, setArmId] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) { notify('error', 'Select a file to import.'); return; }
    setBusy(true); setResult(null);
    const r = await postFile(d.upload_url, file, { class_id: classId, arm_id: armId });
    setBusy(false);
    if (r.ok) setResult({ message: r.message, warnings: r.warnings || [], more: r.more || 0 });
    else notify('error', r.error || 'Could not import the file.');
  };

  return (
    <>
      <PageHeader title="Import Students" />
      {result && (
        <div className="card mb-3" style={{ borderColor: 'var(--success)' }}><div className="card-body">
          <p className="mb-1"><i aria-hidden="true" className="fas fa-circle-check text-success" /> {result.message}</p>
          {result.warnings.length > 0 && (
            <ul className="text-muted text-sm" style={{ margin: '.5rem 0 0', paddingLeft: '1.2rem' }}>
              {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
              {result.more > 0 && <li>… and {result.more} more</li>}
            </ul>
          )}
        </div></div>
      )}
      <div className="card"><div className="card-body">
        <p className="mb-3">Upload an Excel (<code>.xlsx</code>) or CSV (<code>.csv</code>) file to import students.{' '}
          <a href={d.template_url} data-native>Download the template</a> for the column layout. Only <strong>Surname</strong> and <strong>First Name</strong> are required.</p>
        <form onSubmit={submit}>
          <div className="form-row" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <div className="form-group" style={{ flex: 1, minWidth: 180 }}>
              <label className="form-label">Assign to Class <span className="text-muted">(optional)</span></label>
              <select className="form-control" value={classId} onChange={(e) => setClassId(e.target.value)}>
                <option value="">— Don't assign —</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div className="form-group" style={{ flex: 1, minWidth: 180 }}>
              <label className="form-label">Arm <span className="text-muted">(optional)</span></label>
              <select className="form-control" value={armId} onChange={(e) => setArmId(e.target.value)}>
                <option value="">— Don't assign —</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
          </div>
          <p className="text-muted" style={{ margin: '-0.25rem 0 1rem', fontSize: 'var(--text-sm)' }}>
            Pick both a class and an arm to enrol every imported student into that class for the current term. Leave blank to import without a class.</p>
          <div className="form-group"><label className="form-label">Select File</label>
            <input type="file" className="form-control" accept=".xlsx,.xls,.csv" onChange={(e) => setFile(e.target.files[0] || null)} required /></div>
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-upload')} /> {busy ? 'Importing…' : 'Import'}</button>
        </form>
      </div></div>
    </>
  );
}

const SCREENS = { index: Index, summary: Summary, export_class: ExportClass, import: Import };

export default function ReportsApp({ data }) {
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
