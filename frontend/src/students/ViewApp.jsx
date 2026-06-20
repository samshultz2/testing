import React, { useState } from 'react';
import { apiGet } from '../lib/api';
import { postForm } from '../lib/forms';
import { confirm } from '../components/ui';

function Info({ label, children }) {
  return (
    <div className="info-row">
      <span className="text-muted">{label}</span>
      <strong>{children}</strong>
    </div>
  );
}

export default function ViewApp({ initial }) {
  const [data, setData] = useState(initial || {});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const d = data || {};
  const s = d.student || {};
  const urls = d.urls || {};
  const canManage = !!d.can_manage;

  const refresh = async () => {
    try { setData(await apiGet(`/api/students/${s.id}`)); } catch (e) { /* keep */ }
  };
  const run = async (url, fields, okMsg) => {
    setBusy(true); setMsg(null);
    try {
      const res = await postForm(url, fields);
      if (!res.ok && !(res.redirected || res.type === 'opaqueredirect')) {
        const ct = res.headers.get('content-type') || '';
        const text = ct.includes('json') ? (await res.json()).error : 'Action failed.';
        setMsg({ tone: 'error', text: text || 'Action failed.' }); return false;
      }
      setMsg({ tone: 'success', text: okMsg });
      await refresh();
      return true;
    } catch (e) { setMsg({ tone: 'error', text: e.message || 'Action failed.' }); return false; }
    finally { setBusy(false); }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{s.full_name}</h1>{' '}
          <span className="badge badge-primary">{s.student_id}</span>{' '}
          {s.is_graduated && <span className="badge badge-success"><i className="fas fa-user-graduate" /> Graduate</span>}
        </div>
        <div className="page-header-actions" style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
          {canManage && <button type="button" className={'btn ' + (s.is_graduated ? 'btn-warning' : 'btn-success')} disabled={busy}
            onClick={async () => { if (await confirm(`${s.is_graduated ? 'Undo graduation for' : 'Mark as graduate:'} ${s.full_name}?`))
              run(urls.graduate, {}, 'Updated graduation status.'); }}>
            <i className={'fas ' + (s.is_graduated ? 'fa-rotate-left' : 'fa-user-graduate')} /> {s.is_graduated ? 'Undo Graduate' : 'Mark as Graduate'}
          </button>}
          <a href={urls.exam_report} className="btn btn-info"><i className="fas fa-file-pdf" /> Exam Report</a>
          <a href={urls.predictions} className="btn btn-info"><i className="fas fa-chart-line" /> Predictions</a>
          <a href={urls.report_card} className="btn btn-success"><i className="fas fa-file-invoice" /> Report Card</a>
          {canManage && <a href={urls.edit} className="btn btn-primary"><i className="fas fa-edit" /> Edit</a>}
          <a href={urls.list} className="btn btn-secondary"><i className="fas fa-arrow-left" /> Back</a>
        </div>
      </div>

      {msg && (
        <div className={'alert alert-' + ({ success: 'success', error: 'danger' }[msg.tone] || 'info')} role="status"
             style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <span>{msg.text}</span>
          <button type="button" onClick={() => setMsg(null)} aria-label="Dismiss" style={{ background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
        </div>
      )}

      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-user" /> Personal Info</h3></div>
        <div className="card-body">
          <div className="info-grid">
            <Info label="Full Name">{s.full_name}</Info>
            <Info label="Gender"><span className={'badge ' + (s.gender === 'Male' ? 'badge-info' : 'badge-warning')}>{s.gender}</span></Info>
            <Info label="Date of Birth">{s.date_of_birth || 'Not set'}</Info>
            <Info label="Age">{s.age != null ? s.age + ' years' : 'N/A'}</Info>
            <Info label="Religion">{s.religion || 'Not set'}</Info>
            <Info label="Address">{s.home_address || 'Not set'}</Info>
            <Info label="Hobbies">{s.hobbies || 'Not set'}</Info>
            <Info label="Stream">{s.stream ? <span className="badge badge-info">{s.stream}</span> : 'Not set'}</Info>
            <Info label="WAEC Subjects">{(s.waec_subjects || []).join(', ') || 'Not set'}</Info>
            <Info label="JAMB Subjects">{(s.jamb_subjects || []).join(', ') || 'Not set'}</Info>
          </div>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-phone" /> Contacts</h3></div>
        <div className="card-body">
          {(d.contacts || []).length ? (
            <div className="data-cards">
              {d.contacts.map((c, i) => (
                <div className="data-card" key={i}>
                  <div className="data-card-header">
                    <div className="data-card-title">{c.name || 'Contact'}</div>
                    {c.is_primary && <span className="badge badge-success">Primary</span>}
                  </div>
                  <div className="data-card-row"><span className="data-card-label">Phone</span><span>{c.phone_number}</span></div>
                  <div className="data-card-row"><span className="data-card-label">Relationship</span><span>{c.relationship}</span></div>
                </div>
              ))}
            </div>
          ) : <p className="text-muted">No contacts added</p>}
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-school" /> Class History</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {(d.enrollments || []).length ? (
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table">
                <thead><tr><th>Term</th><th>Class</th><th>Arm</th></tr></thead>
                <tbody>{d.enrollments.map((e, i) => <tr key={i}><td>{e.term}</td><td>{e.class}</td><td>{e.arm}</td></tr>)}</tbody>
              </table>
            </div>
          ) : <div className="empty-state"><p>Not enrolled yet</p></div>}
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-file-alt" /> WAEC</h3>
          <a href={(d.waec || {}).add_url} className="btn btn-secondary btn-sm"><i className="fas fa-plus" /> Add</a></div>
        <div className="card-body">
          {(d.waec || {}).count ? (<>
            <p>{d.waec.count} subjects recorded</p>
            <a href={d.waec.view_url} className="btn btn-primary btn-sm">View Details</a>
          </>) : <p className="text-muted">No WAEC results</p>}
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-file-contract" /> JAMB</h3>
          <a href={(d.jamb || {}).add_url} className="btn btn-secondary btn-sm"><i className="fas fa-plus" /> Add</a></div>
        <div className="card-body">
          {(d.jamb || {}).latest ? (
            <div className="info-grid">
              <Info label="Year">{d.jamb.latest.year}</Info>
              <Info label="Score"><span style={{ fontSize: '1.25rem' }}>{d.jamb.latest.score}/400</span></Info>
            </div>
          ) : <p className="text-muted">No JAMB results</p>}
        </div>
      </div>

      <Welfare title="Discipline" icon="fa-gavel" count={(d.discipline || []).length}>
        <DisciplineForm categories={d.discipline_categories || []} today={d.today} disabled={busy}
                        onAdd={(f) => run(urls.discipline_add, f, 'Discipline record added.')} />
        {(d.discipline || []).length ? (
          <div className="table-container" style={{ border: 'none' }}><table className="data-table">
            <thead><tr><th>Date</th><th>Category</th><th>Severity</th><th>Incident</th><th>Action</th><th>By</th><th /></tr></thead>
            <tbody>{d.discipline.map((r) => (
              <tr key={r.id}>
                <td>{r.date}</td><td>{r.category || '—'}</td>
                <td>{r.severity && <span className={'badge ' + (r.severity === 'Major' ? 'badge-danger' : 'badge-warning')}>{r.severity}</span>}</td>
                <td>{r.description}</td><td>{r.action_taken || '—'}</td><td className="text-muted">{r.reported_by || ''}</td>
                <td><button type="button" className="btn btn-danger btn-sm" disabled={busy}
                            onClick={async () => { if (await confirm('Remove this record?')) run(r.delete_url, {}, 'Record removed.'); }}><i className="fas fa-times" /></button></td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <p className="text-muted">No discipline records.</p>}
      </Welfare>

      <Welfare title="Sick Bay" icon="fa-briefcase-medical" count={(d.clinic || []).length}>
        <ClinicForm today={d.today} disabled={busy}
                    onAdd={(f) => run(urls.clinic_add, f, 'Clinic visit added.')} />
        {(d.clinic || []).length ? (
          <div className="table-container" style={{ border: 'none' }}><table className="data-table">
            <thead><tr><th>Date</th><th>Complaint</th><th>Treatment</th><th>Parent told</th><th>By</th><th /></tr></thead>
            <tbody>{d.clinic.map((v) => (
              <tr key={v.id}>
                <td>{v.date}</td><td>{v.complaint}</td><td>{v.treatment || '—'}</td>
                <td><span className={'badge ' + (v.parent_notified ? 'badge-success' : 'badge-warning')}>{v.parent_notified ? 'Yes' : 'No'}</span></td>
                <td className="text-muted">{v.attended_by || ''}</td>
                <td><button type="button" className="btn btn-danger btn-sm" disabled={busy}
                            onClick={async () => { if (await confirm('Remove this visit?')) run(v.delete_url, {}, 'Visit removed.'); }}><i className="fas fa-times" /></button></td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <p className="text-muted">No clinic visits.</p>}
      </Welfare>
    </div>
  );
}

function Welfare({ title, icon, count, children }) {
  return (
    <div className="card mb-3">
      <div className="card-header"><h3><i className={'fas ' + icon} /> {title} ({count})</h3></div>
      <div className="card-body">{children}</div>
    </div>
  );
}

function DisciplineForm({ categories, today, disabled, onAdd }) {
  const [f, setF] = useState({ date: today || '', category: categories[0] || '', severity: 'Minor', description: '', action_taken: '' });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.description.trim()) return;
    if (await onAdd(f)) setF((x) => ({ ...x, description: '', action_taken: '' }));
  };
  return (
    <form onSubmit={submit} className="filter-form mb-3" style={{ alignItems: 'flex-end' }}>
      <div className="form-group"><label className="form-label">Date</label><input type="date" className="form-control" value={f.date} onChange={(e) => set('date', e.target.value)} /></div>
      <div className="form-group"><label className="form-label">Category</label>
        <select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select></div>
      <div className="form-group"><label className="form-label">Severity</label>
        <select className="form-control" value={f.severity} onChange={(e) => set('severity', e.target.value)}><option>Minor</option><option>Major</option></select></div>
      <div className="form-group" style={{ flex: 2, minWidth: 200 }}><label className="form-label">What happened</label>
        <input type="text" className="form-control" placeholder="Describe the incident" required value={f.description} onChange={(e) => set('description', e.target.value)} /></div>
      <div className="form-group" style={{ flex: 2, minWidth: 200 }}><label className="form-label">Action taken</label>
        <input type="text" className="form-control" placeholder="e.g., Warning, parent called" value={f.action_taken} onChange={(e) => set('action_taken', e.target.value)} /></div>
      <div className="filter-actions"><button type="submit" className="btn btn-primary btn-sm" disabled={disabled}><i className="fas fa-plus" /> Add</button></div>
    </form>
  );
}

function ClinicForm({ today, disabled, onAdd }) {
  const [f, setF] = useState({ date: today || '', complaint: '', treatment: '', parent_notified: false });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.complaint.trim()) return;
    const ok = await onAdd({ ...f, parent_notified: f.parent_notified ? 'on' : '' });
    if (ok) setF((x) => ({ ...x, complaint: '', treatment: '', parent_notified: false }));
  };
  return (
    <form onSubmit={submit} className="filter-form mb-3" style={{ alignItems: 'flex-end' }}>
      <div className="form-group"><label className="form-label">Date</label><input type="date" className="form-control" value={f.date} onChange={(e) => set('date', e.target.value)} /></div>
      <div className="form-group" style={{ flex: 2, minWidth: 200 }}><label className="form-label">Complaint / symptom</label>
        <input type="text" className="form-control" placeholder="e.g., Headache, fever" required value={f.complaint} onChange={(e) => set('complaint', e.target.value)} /></div>
      <div className="form-group" style={{ flex: 2, minWidth: 200 }}><label className="form-label">Treatment given</label>
        <input type="text" className="form-control" placeholder="e.g., Paracetamol, rest" value={f.treatment} onChange={(e) => set('treatment', e.target.value)} /></div>
      <div className="form-group"><label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
        <input type="checkbox" checked={f.parent_notified} onChange={(e) => set('parent_notified', e.target.checked)} /> Parent notified</label></div>
      <div className="filter-actions"><button type="submit" className="btn btn-primary btn-sm" disabled={disabled}><i className="fas fa-plus" /> Add</button></div>
    </form>
  );
}
