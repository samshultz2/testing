import React, { useState, useEffect } from 'react';
import { apiGet } from '../lib/api';
import { postForm } from '../lib/forms';
import { confirm } from '../components/ui';
import { rememberViewed } from '../lib/studprefs';

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
  const initials = (s.full_name || '?').split(' ').filter(Boolean).slice(0, 2)
    .map((w) => w[0]).join('').toUpperCase() || '?';

  // Record this profile in the "recently viewed" list the students list offers
  // as quick links. Keyed by id so re-opening just bumps it to the top.
  useEffect(() => {
    if (s.id) rememberViewed({ id: s.id, name: s.full_name, student_id: s.student_id,
                               url: (urls.self || window.location.pathname) });
  }, [s.id]);

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
      <div className="profile-hero">
        <div className="ph-cover" />
        <div className="ph-body">
          {s.photo_url
            ? <img className="ph-avatar" src={s.photo_url} alt={s.full_name} />
            : <div className="ph-avatar" style={{ background: 'linear-gradient(135deg,var(--primary),var(--primary-hover))' }} aria-hidden="true">{initials}</div>}
          <div className="ph-id">
            <h1 className="ph-name">{s.full_name}</h1>
            <div className="ph-meta">
              <span className="badge badge-primary">{s.student_id}</span>
              {s.current_class && <span className="badge badge-secondary">{s.current_class}</span>}
              {s.gender && <span className={'badge ' + (s.gender === 'Male' ? 'badge-info' : 'badge-warning')}>{s.gender}</span>}
              {s.age != null && <span className="badge badge-secondary">Age {s.age}</span>}
              {s.stream && <span className="badge badge-info">{s.stream}</span>}
              {s.is_graduated && <span className="badge badge-success"><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate</span>}
            </div>
          </div>
        </div>
        <div className="ph-actions">
          {canManage && <button type="button" className={'btn ' + (s.is_graduated ? 'btn-warning' : 'btn-success')} disabled={busy}
            onClick={async () => { if (await confirm(`${s.is_graduated ? 'Undo graduation for' : 'Mark as graduate:'} ${s.full_name}?`))
              run(urls.graduate, {}, 'Updated graduation status.'); }}>
            <i aria-hidden="true" className={'fas ' + (s.is_graduated ? 'fa-rotate-left' : 'fa-user-graduate')} /> {s.is_graduated ? 'Undo Graduate' : 'Mark as Graduate'}
          </button>}
          <a href={urls.exam_report} className="btn btn-info"><i aria-hidden="true" className="fas fa-file-pdf" /> Exam Report</a>
          <a href={urls.predictions} className="btn btn-info"><i aria-hidden="true" className="fas fa-chart-line" /> Predictions</a>
          <a href={urls.report_card} className="btn btn-success"><i aria-hidden="true" className="fas fa-file-invoice" /> Report Card</a>
          {urls.id_card && <a href={urls.id_card} className="btn btn-info"><i aria-hidden="true" className="fas fa-id-card" /> ID Card</a>}
          {canManage && <a href={urls.edit} className="btn btn-primary"><i aria-hidden="true" className="fas fa-edit" /> Edit</a>}
          <a href={urls.list} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>
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
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-user" /> Personal Info</h3></div>
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

      {(d.identity || s.house || s.boarding_status) && (
        <div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-id-card" /> Identity &amp; Pastoral</h3></div>
          <div className="card-body">
            <div className="info-grid">
              {d.identity && d.identity.nin && <Info label="NIN">{d.identity.nin}</Info>}
              {d.identity && d.identity.jamb_reg_number && <Info label="JAMB Reg. Number">{d.identity.jamb_reg_number}</Info>}
              {d.identity && d.identity.waec_reg_number && <Info label="WAEC Reg. Number">{d.identity.waec_reg_number}</Info>}
              {d.identity && d.identity.serial_number && <Info label="Serial Number">{d.identity.serial_number}</Info>}
              {d.identity && d.identity.waec_epin && <Info label="WAEC e-PIN">{d.identity.waec_epin}</Info>}
              {d.identity && d.identity.jamb_profile_code && <Info label="JAMB Profile Code">{d.identity.jamb_profile_code}</Info>}
              {s.house && <Info label="House">{s.house}</Info>}
              {s.boarding_status && <Info label="Boarding">{s.boarding_status}</Info>}
            </div>
          </div>
        </div>
      )}

      {d.medical && (
        <div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-notes-medical" /> Medical Information</h3></div>
          <div className="card-body">
            <div className="info-grid">
              {d.medical.blood_group && <Info label="Blood Group"><span className="badge badge-danger">{d.medical.blood_group}</span></Info>}
              {d.medical.genotype && <Info label="Genotype"><span className="badge badge-warning">{d.medical.genotype}</span></Info>}
              {d.medical.allergies && <Info label="Allergies">{d.medical.allergies}</Info>}
              {d.medical.medical_conditions && <Info label="Conditions">{d.medical.medical_conditions}</Info>}
              {d.medical.disabilities && <Info label="Disabilities">{d.medical.disabilities}</Info>}
              {d.medical.medications && <Info label="Medications">{d.medical.medications}</Info>}
              {d.medical.medical_notes && <Info label="Notes">{d.medical.medical_notes}</Info>}
              {d.medical.emergency_medical && <Info label="Emergency Instructions">{d.medical.emergency_medical}</Info>}
            </div>
          </div>
        </div>
      )}

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-phone" /> Contacts</h3></div>
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
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-school" /> Class History</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {(d.enrollments || []).length ? (
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              {/* no-mobile-scroll: this short 3-column table fills the card on
                  phones instead of collapsing to content width (display:block). */}
              <table className="data-table no-mobile-scroll">
                <thead><tr><th>Term</th><th>Class</th><th>Arm</th></tr></thead>
                <tbody>{d.enrollments.map((e, i) => <tr key={i}><td>{e.term}</td><td>{e.class}</td><td>{e.arm || '—'}</td></tr>)}</tbody>
              </table>
            </div>
          ) : <div className="empty-state"><p>Not enrolled yet</p></div>}
        </div>
      </div>

      {d.attendance && (
        <div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-calendar-check" /> Attendance Summary</h3>
            {d.attendance.url && <a href={d.attendance.url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-chart-line" /> Full profile</a>}</div>
          <div className="card-body">
            <div className="info-grid">
              <Info label="Overall">
                <span className={'badge ' + (d.attendance.warning ? 'badge-danger' : 'badge-success')}>{d.attendance.percentage}%</span>
                {d.attendance.warning && d.attendance.threshold != null &&
                  <span className="text-muted" style={{ marginLeft: 6, fontSize: '.8rem' }}>below {d.attendance.threshold}%</span>}
              </Info>
              {d.attendance.latest_term && <Info label={d.attendance.latest_term}>{d.attendance.latest_percentage}%</Info>}
              <Info label="Present days">{d.attendance.present_days}</Info>
              <Info label="Late days">{d.attendance.late_days}</Info>
              <Info label="Absent days">{d.attendance.absent_days}</Info>
              <Info label="Terms tracked">{d.attendance.terms}</Info>
            </div>
          </div>
        </div>
      )}

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-alt" /> WAEC</h3>
          <a href={(d.waec || {}).add_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a></div>
        <div className="card-body">
          {(d.waec || {}).count ? (<>
            <p>{d.waec.count} subjects recorded</p>
            <a href={d.waec.view_url} className="btn btn-primary btn-sm">View Details</a>
          </>) : <p className="text-muted">No WAEC results</p>}
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-contract" /> JAMB</h3>
          <a href={(d.jamb || {}).add_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a></div>
        <div className="card-body">
          {(d.jamb || {}).latest ? (
            <div className="info-grid">
              <Info label="Year">{d.jamb.latest.year}</Info>
              <Info label="Score"><span style={{ fontSize: 'var(--text-lg)' }}>{d.jamb.latest.score}/400</span></Info>
            </div>
          ) : <p className="text-muted">No JAMB results</p>}
        </div>
      </div>

      {d.communications && d.communications.count > 0 && (
        <div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-comments" /> Communication History ({d.communications.count})</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table table-stack no-mobile-scroll">
                <thead><tr><th>Date</th><th>Message</th><th>Channel</th><th>Status</th></tr></thead>
                <tbody>{d.communications.items.map((m, i) => (
                  <tr key={i}>
                    <td data-label="Date">{m.date || '—'}</td>
                    <td data-label="Message"><strong>{m.title}</strong>{m.snippet && <div className="text-muted" style={{ fontSize: '.82rem' }}>{m.snippet}</div>}</td>
                    <td data-label="Channel">{m.channel && <span className="badge badge-info">{m.channel}</span>}</td>
                    <td data-label="Status"><span className={'badge ' + (m.status === 'Sent' ? 'badge-success' : m.status === 'Failed' ? 'badge-danger' : 'badge-warning')}>{m.status}</span>
                      {m.read && <span className="badge badge-secondary" title="Read" style={{ marginLeft: 4 }}><i aria-hidden="true" className="fas fa-check-double" /></span>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {d.history && d.history.length > 0 && <ChangeHistory rows={d.history} />}

      <Welfare title="Discipline" icon="fa-gavel" count={(d.discipline || []).length}>
        <DisciplineForm categories={d.discipline_categories || []} today={d.today} disabled={busy}
                        onAdd={(f) => run(urls.discipline_add, f, 'Discipline record added.')} />
        {(d.discipline || []).length ? (
          <div className="table-container" style={{ border: 'none' }}><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Date</th><th>Category</th><th>Severity</th><th>Incident</th><th>Action</th><th>By</th><th /></tr></thead>
            <tbody>{d.discipline.map((r) => (
              <tr key={r.id}>
                <td data-label="Date">{r.date}</td><td data-label="Category">{r.category || '—'}</td>
                <td data-label="Severity">{r.severity && <span className={'badge ' + (r.severity === 'Major' ? 'badge-danger' : 'badge-warning')}>{r.severity}</span>}</td>
                <td data-label="Incident">{r.description}</td><td data-label="Action">{r.action_taken || '—'}</td><td data-label="By" className="text-muted">{r.reported_by || ''}</td>
                <td className="actions"><button type="button" className="btn btn-danger btn-sm" disabled={busy}
                            onClick={async () => { if (await confirm('Remove this record?')) run(r.delete_url, {}, 'Record removed.'); }}><i aria-hidden="true" className="fas fa-times" /></button></td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <p className="text-muted">No discipline records.</p>}
      </Welfare>

      <Welfare title="Sick Bay" icon="fa-briefcase-medical" count={(d.clinic || []).length}>
        <ClinicForm today={d.today} disabled={busy}
                    onAdd={(f) => run(urls.clinic_add, f, 'Clinic visit added.')} />
        {(d.clinic || []).length ? (
          <div className="table-container" style={{ border: 'none' }}><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Date</th><th>Complaint</th><th>Treatment</th><th>Parent told</th><th>By</th><th /></tr></thead>
            <tbody>{d.clinic.map((v) => (
              <tr key={v.id}>
                <td data-label="Date">{v.date}</td><td data-label="Complaint">{v.complaint}</td><td data-label="Treatment">{v.treatment || '—'}</td>
                <td data-label="Parent told"><span className={'badge ' + (v.parent_notified ? 'badge-success' : 'badge-warning')}>{v.parent_notified ? 'Yes' : 'No'}</span></td>
                <td data-label="By" className="text-muted">{v.attended_by || ''}</td>
                <td className="actions"><button type="button" className="btn btn-danger btn-sm" disabled={busy}
                            onClick={async () => { if (await confirm('Remove this visit?')) run(v.delete_url, {}, 'Visit removed.'); }}><i aria-hidden="true" className="fas fa-times" /></button></td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <p className="text-muted">No clinic visits.</p>}
      </Welfare>
    </div>
  );
}

const ACTION_LABELS = {
  'student.create': 'Created', 'student.update': 'Edited', 'student.import': 'Imported',
  'delete_student': 'Deleted', 'bulk_set_stream': 'Stream (bulk)', 'bulk_set_gender': 'Gender (bulk)',
  'bulk_set_house': 'House (bulk)', 'bulk_set_boarding': 'Boarding (bulk)',
  'bulk_message_students': 'Messaged parents', 'bulk_add_subject': 'WAEC subject (bulk)',
};

function ChangeHistory({ rows }) {
  const [q, setQ] = useState('');
  const term = q.trim().toLowerCase();
  const shown = term
    ? rows.filter((r) => `${ACTION_LABELS[r.action] || r.action} ${r.user} ${r.detail} ${r.when}`.toLowerCase().includes(term))
    : rows;
  return (
    <div className="card mb-3">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <h3><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Change History ({rows.length})</h3>
        <input type="search" className="form-control" style={{ maxWidth: 240 }} placeholder="Search history…"
               value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search change history" />
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {shown.length ? (
          <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
            <table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>When</th><th>Action</th><th>By</th><th>Details</th></tr></thead>
              <tbody>{shown.map((r, i) => (
                <tr key={i}>
                  <td data-label="When" style={{ whiteSpace: 'nowrap' }}>{r.when}</td>
                  <td data-label="Action"><span className="badge badge-secondary">{ACTION_LABELS[r.action] || r.action}</span></td>
                  <td data-label="By">{r.user}{r.role && <span className="text-muted"> · {r.role}</span>}</td>
                  <td data-label="Details" style={{ fontSize: '.85rem' }}>{r.detail || '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : <p className="text-muted" style={{ padding: '.75rem 1rem' }}>No matching history.</p>}
      </div>
    </div>
  );
}

function Welfare({ title, icon, count, children }) {
  return (
    <div className="card mb-3">
      <div className="card-header"><h3><i aria-hidden="true" className={'fas ' + icon} /> {title} ({count})</h3></div>
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
      <div className="filter-actions"><button type="submit" className="btn btn-primary btn-sm" disabled={disabled}><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
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
      <div className="filter-actions"><button type="submit" className="btn btn-primary btn-sm" disabled={disabled}><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
    </form>
  );
}
