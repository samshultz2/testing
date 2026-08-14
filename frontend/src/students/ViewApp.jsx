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

// Lightweight attendance donut (conic-gradient ring, no chart library) — the
// headline percentage lives in the hole, the ring fills to that share and turns
// danger-red when below the school's warning threshold.
function AttendanceDonut({ pct, warning }) {
  const p = Math.max(0, Math.min(100, Math.round(Number(pct) || 0)));
  const color = warning ? 'var(--danger)' : 'var(--success)';
  return (
    <div className="att-donut" style={{ '--p': p, '--c': color }} role="img"
         aria-label={`Overall attendance ${p}%`}>
      <div className="att-donut-hole">
        <span className="att-donut-pct">{p}%</span>
        <span className="att-donut-cap">Overall</span>
      </div>
    </div>
  );
}

// Sections default open on desktop (bento cards expanded) and collapsed on
// phones (accordion rows), mirroring the reference exactly.
const IS_DESKTOP = typeof window !== 'undefined'
  && window.matchMedia && window.matchMedia('(min-width: 992px)').matches;

// A collapsible profile section: a clickable header (icon + title + optional
// status badge + chevron) toggles its body. An optional `action` (Edit / Add /
// View) sits in the header and doesn't toggle.
function Section({ icon, title, badge, action, defaultOpen = IS_DESKTOP, wide, children }) {
  const [open, setOpen] = useState(defaultOpen);
  const toggle = () => setOpen((o) => !o);
  return (
    <div className={'card mb-3 stu-sec' + (wide ? ' profile-wide' : '') + (open ? ' is-open' : ' is-closed')}>
      <div className="stu-sec-head">
        <button type="button" className="stu-sec-toggle" aria-expanded={open} onClick={toggle}>
          <i aria-hidden="true" className={'fas ' + icon + ' stu-sec-icon'} />
          <span className="stu-sec-title">{title}</span>
          {badge}
        </button>
        <span className="stu-sec-right">
          {action}
          <button type="button" className="stu-sec-chevbtn" aria-label={open ? 'Collapse' : 'Expand'} aria-expanded={open} onClick={toggle}>
            <i aria-hidden="true" className={'fas fa-chevron-' + (open ? 'down' : 'right')} />
          </button>
        </span>
      </div>
      {open && <div className="card-body">{children}</div>}
    </div>
  );
}

// Colour + icon for the chosen-course eligibility verdict.
const ELIG_STYLE = {
  ON_TRACK: { badge: 'badge-success', bar: 'var(--success)', icon: 'fa-circle-check' },
  CLOSE: { badge: 'badge-warning', bar: 'var(--warning)', icon: 'fa-circle-half-stroke' },
  OFF_TRACK: { badge: 'badge-danger', bar: 'var(--danger)', icon: 'fa-triangle-exclamation' },
  NO_DATA: { badge: 'badge-secondary', bar: 'var(--gray-300)', icon: 'fa-hourglass-half' },
  NO_TARGET: { badge: 'badge-secondary', bar: 'var(--gray-300)', icon: 'fa-circle-question' },
};

// The university-aspiration section of the profile: chosen-course verdict with a
// gap-to-target progress bar, second choice, career goal, admission outcome and
// any scholarships. Rendered whenever the student has any aspiration data.
function AspirationCard({ s, asp, scholarships }) {
  const hasAny = s.target_university || s.target_course || s.jamb_target || s.career_goal ||
    s.admission_status || (scholarships && scholarships.length) ||
    (s.waec_subjects && s.waec_subjects.length) || (s.jamb_subjects && s.jamb_subjects.length);
  if (!hasAny) return null;
  const st = (asp && ELIG_STYLE[asp.status]) || ELIG_STYLE.NO_TARGET;
  const target = (asp && asp.target) || s.jamb_target;
  const proj = asp && asp.projected;
  const pct = (target && proj != null) ? Math.max(0, Math.min(100, Math.round((proj / target) * 100))) : null;
  return (
    <Section icon="fa-graduation-cap" title="University Aspiration"
             badge={asp && asp.status ? <span className={'badge ' + st.badge}><i aria-hidden="true" className={'fas ' + st.icon} /> {asp.status_label}</span> : null}>
        <div className="info-grid">
          <Info label="Target University">{s.target_university || 'Not set'}</Info>
          <Info label="Target Course">{s.target_course || 'Not set'}</Info>
          <Info label="Department / Faculty">{s.target_department || 'Not set'}</Info>
          <Info label="JAMB Target Score">{target ? `${target} / 400` : 'Not set'}</Info>
          {(s.target2_university || s.target2_course) &&
            <Info label="Second Choice">{[s.target2_university, s.target2_course].filter(Boolean).join(' · ') || 'Not set'}</Info>}
          {s.career_goal && <Info label="Career Goal">{s.career_goal}</Info>}
          {s.admission_status && <Info label="Admission Status"><span className="badge badge-info">{s.admission_status}</span></Info>}
          {(s.admitted_university || s.admitted_course) &&
            <Info label="Admitted To">{[s.admitted_university, s.admitted_course].filter(Boolean).join(' · ')}</Info>}
          <Info label="WAEC Subjects">{(s.waec_subjects || []).join(', ') || 'Not set'}</Info>
          <Info label="JAMB Subjects">{(s.jamb_subjects || []).join(', ') || 'Not set'}</Info>
        </div>

        {pct != null && (
          <div style={{ marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.85rem', marginBottom: '.3rem' }}>
              <span className="text-muted">Projected JAMB {proj} of target {target}</span>
              <strong>{asp.gap != null && asp.gap > 0 ? `${asp.gap} to go` : 'Target met'}</strong>
            </div>
            <div style={{ height: 10, borderRadius: 6, background: 'var(--gray-200, #e5e7eb)', overflow: 'hidden' }}>
              <div style={{ width: pct + '%', height: '100%', background: st.bar, transition: 'width .4s' }} />
            </div>
          </div>
        )}

        {asp && (asp.missing_jamb || []).length > 0 && (
          <p className="text-muted" style={{ marginTop: '.75rem', marginBottom: 0, fontSize: '.85rem' }}>
            <i aria-hidden="true" className="fas fa-triangle-exclamation" style={{ color: 'var(--danger)' }} /> Missing required JAMB subject(s): <strong>{asp.missing_jamb.join(', ')}</strong>
          </p>
        )}
        {asp && (asp.missing_waec || []).length > 0 && (
          <p className="text-muted" style={{ marginTop: '.35rem', marginBottom: 0, fontSize: '.85rem' }}>
            <i aria-hidden="true" className="fas fa-triangle-exclamation" style={{ color: 'var(--warning)' }} /> O'level subject(s) not yet projected to credit: <strong>{asp.missing_waec.join(', ')}</strong>
          </p>
        )}
        {asp && (asp.reasons || []).length > 0 && asp.status === 'ON_TRACK' && (
          <p className="text-muted" style={{ marginTop: '.75rem', marginBottom: 0, fontSize: '.85rem' }}>
            <i aria-hidden="true" className="fas fa-circle-check" style={{ color: 'var(--success)' }} /> Projected to meet subject, credit and score requirements for this course.
          </p>
        )}

        {(scholarships && scholarships.length > 0) && (
          <div style={{ marginTop: '1rem' }}>
            <strong style={{ display: 'block', marginBottom: '.5rem' }}><i aria-hidden="true" className="fas fa-award" /> Scholarships</strong>
            <div className="data-cards">
              {scholarships.map((sc, i) => (
                <div className="data-card" key={i}>
                  <div className="data-card-header">
                    <div className="data-card-title">{sc.name}</div>
                    {sc.status && <span className="badge badge-info">{sc.status}</span>}
                  </div>
                  {sc.provider && <div className="data-card-row"><span className="data-card-label">Provider</span><span>{sc.provider}</span></div>}
                  {sc.amount != null && <div className="data-card-row"><span className="data-card-label">Amount</span><span>₦{Number(sc.amount).toLocaleString()}</span></div>}
                </div>
              ))}
            </div>
          </div>
        )}
    </Section>
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
                               photo: s.photo_url || '',
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
    <div className="student-profile">
      <div className="sp-hero">
        <div className="sp-hero-top">
          {s.photo_url
            ? <img className="sp-avatar" src={s.photo_url} alt={s.full_name} />
            : <div className="sp-avatar sp-avatar-ph" aria-hidden="true">{initials}</div>}
          <div className="sp-id">
            <h1 className="sp-name">{s.full_name}</h1>
            {s.is_graduated && <span className="sp-grad"><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate</span>}
            <div className="sp-chips">
              <span className="sp-chip sp-chip-primary"><i aria-hidden="true" className="fas fa-id-badge" /> {s.student_id}</span>
              {s.gender && <span className={'sp-chip ' + (s.gender === 'Male' ? 'sp-chip-blue' : 'sp-chip-rose')}><i aria-hidden="true" className={'fas ' + (s.gender === 'Male' ? 'fa-mars' : 'fa-venus')} /> {s.gender}</span>}
              {s.age != null && <span className="sp-chip"><i aria-hidden="true" className="fas fa-cake-candles" /> {s.age} years</span>}
              {s.stream && <span className="sp-chip"><i aria-hidden="true" className="fas fa-cube" /> {s.stream}</span>}
              {s.is_graduated && s.graduated_on && <span className="sp-chip"><i aria-hidden="true" className="fas fa-calendar-check" /> Graduated on {s.graduated_on}</span>}
            </div>
          </div>
        </div>
        <div className="sp-actions">
          {canManage && <button type="button" className={'sp-btn ' + (s.is_graduated ? 'sp-btn-warning' : 'sp-btn-success')} disabled={busy}
            onClick={async () => { if (await confirm(`${s.is_graduated ? 'Undo graduation for' : 'Mark as graduate:'} ${s.full_name}?`))
              run(urls.graduate, {}, 'Updated graduation status.'); }}>
            <i aria-hidden="true" className={'fas ' + (s.is_graduated ? 'fa-rotate-left' : 'fa-user-graduate')} /> {s.is_graduated ? 'Undo' : 'Graduate'}
          </button>}
          <a href={urls.exam_report} className="sp-btn sp-btn-primary"><i aria-hidden="true" className="fas fa-file-lines" /> Exam Report</a>
          <a href={urls.predictions} className="sp-btn sp-btn-info"><i aria-hidden="true" className="fas fa-chart-line" /> Predictions</a>
          <a href={urls.report_card} className="sp-btn sp-btn-success"><i aria-hidden="true" className="fas fa-file-invoice" /> Report Card</a>
          {urls.id_card && <a href={urls.id_card} className="sp-btn sp-btn-info"><i aria-hidden="true" className="fas fa-id-card" /> ID Card</a>}
          {canManage && <a href={urls.edit} className="sp-btn sp-btn-primary"><i aria-hidden="true" className="fas fa-pen" /> Edit Profile</a>}
          <a href={urls.list} className="sp-btn sp-btn-back"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>
        </div>
      </div>

      {msg && (
        <div className={'alert alert-' + ({ success: 'success', error: 'danger' }[msg.tone] || 'info')} role="status"
             style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <span>{msg.text}</span>
          <button type="button" onClick={() => setMsg(null)} aria-label="Dismiss" style={{ background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
        </div>
      )}

      <div className="profile-grid">
      <Section icon="fa-user" title="Personal Information"
               action={canManage ? <a href={urls.edit} className="sp-btn sp-btn-sm"><i aria-hidden="true" className="fas fa-pen" /> Edit</a> : null}>
          <div className="info-grid">
            <Info label="Full Name">{s.full_name}</Info>
            <Info label="Gender"><span className={'badge ' + (s.gender === 'Male' ? 'badge-info' : 'badge-warning')}>{s.gender}</span></Info>
            <Info label="Date of Birth">{s.date_of_birth || 'Not set'}</Info>
            <Info label="Age">{s.age != null ? s.age + ' years' : 'N/A'}</Info>
            <Info label="Religion">{s.religion || 'Not set'}</Info>
            <Info label="Address">{s.home_address || 'Not set'}</Info>
            <Info label="Hobbies">{s.hobbies || 'Not set'}</Info>
            <Info label="Stream">{s.stream ? <span className="badge badge-info">{s.stream}</span> : 'Not set'}</Info>
          </div>
      </Section>

      <AspirationCard s={s} asp={d.aspiration} scholarships={d.scholarships || []} />


      {(d.identity || s.house || s.boarding_status) && (
        <Section icon="fa-id-card" title="Identity & Pastoral">
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
        </Section>
      )}

      <Section icon="fa-school" title="Class History"
               badge={(d.enrollments || []).length ? <span className="badge badge-secondary">{d.enrollments.length}</span> : null}>
          {(d.enrollments || []).length ? (
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table no-mobile-scroll">
                <thead><tr><th>Term</th><th>Class</th><th>Arm</th></tr></thead>
                <tbody>{d.enrollments.map((e, i) => <tr key={i}><td>{e.term}</td><td>{e.class}</td><td>{e.arm || '—'}</td></tr>)}</tbody>
              </table>
            </div>
          ) : <div className="empty-state"><p>Not enrolled yet</p></div>}
      </Section>

      {d.medical && (
        <Section icon="fa-notes-medical" title="Medical Information">
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
        </Section>
      )}

      <Section icon="fa-phone" title="Contacts"
               badge={(d.contacts || []).length ? <span className="badge badge-secondary">{d.contacts.length}</span> : null}>
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
      </Section>

      {d.attendance && (
        <Section icon="fa-calendar-check" title="Attendance Summary"
                 badge={<span className={'badge ' + (d.attendance.warning ? 'badge-danger' : 'badge-success')}>{d.attendance.percentage}%</span>}
                 action={d.attendance.url ? <a href={d.attendance.url} className="sp-btn sp-btn-sm"><i aria-hidden="true" className="fas fa-chart-line" /> Full profile</a> : null}>
            <div className="att-summary">
              <div className="att-donut-wrap">
                <AttendanceDonut pct={d.attendance.percentage} warning={d.attendance.warning} />
                {d.attendance.warning && d.attendance.threshold != null &&
                  <span className="text-muted att-donut-warn">below {d.attendance.threshold}% threshold</span>}
              </div>
              <div className="info-grid att-legend">
                {d.attendance.latest_term && <Info label={d.attendance.latest_term}>{d.attendance.latest_percentage}%</Info>}
                <Info label="Present days">{d.attendance.present_days}</Info>
                <Info label="Late days">{d.attendance.late_days}</Info>
                <Info label="Absent days">{d.attendance.absent_days}</Info>
                <Info label="Terms tracked">{d.attendance.terms}</Info>
              </div>
            </div>
        </Section>
      )}

      <Section icon="fa-file-alt" title="WAEC"
               badge={(d.waec || {}).count ? <span className="badge badge-secondary">{d.waec.count}</span> : null}
               action={<a href={(d.waec || {}).add_url} className="sp-btn sp-btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}>
          {(d.waec || {}).count ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '.75rem', flexWrap: 'wrap' }}>
              <span>{d.waec.count} subject{d.waec.count === 1 ? '' : 's'} recorded</span>
              <a href={d.waec.view_url} className="sp-btn sp-btn-sm sp-btn-primary"><i aria-hidden="true" className="fas fa-eye" /> View details</a>
            </div>
          ) : <p className="text-muted">No WAEC results yet.</p>}
      </Section>

      <Section icon="fa-file-contract" title="JAMB"
               badge={(d.jamb || {}).latest ? <span className="badge badge-secondary">{d.jamb.latest.score}/400</span> : null}
               action={<a href={(d.jamb || {}).add_url} className="sp-btn sp-btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}>
          {(d.jamb || {}).latest ? (
            <div className="info-grid">
              <Info label="Year">{d.jamb.latest.year}</Info>
              <Info label="Score"><strong style={{ fontSize: 'var(--text-lg)' }}>{d.jamb.latest.score}/400</strong></Info>
            </div>
          ) : <p className="text-muted">No JAMB results yet.</p>}
      </Section>

      {d.communications && d.communications.count > 0 && (
        <Section icon="fa-comments" title="Communication History" wide
                 badge={<span className="badge badge-secondary">{d.communications.count}</span>}>
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
        </Section>
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
                <td className="actions"><button type="button" className="sp-btn sp-btn-sm sp-btn-danger" disabled={busy}
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
                <td className="actions"><button type="button" className="sp-btn sp-btn-sm sp-btn-danger" disabled={busy}
                            onClick={async () => { if (await confirm('Remove this visit?')) run(v.delete_url, {}, 'Visit removed.'); }}><i aria-hidden="true" className="fas fa-times" /></button></td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <p className="text-muted">No clinic visits.</p>}
      </Welfare>
      </div>{/* .profile-grid */}
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
    <Section icon="fa-clock-rotate-left" title="Change History" wide
             badge={<span className="badge badge-secondary">{rows.length}</span>}>
        <input type="search" className="form-control" style={{ maxWidth: 240, marginBottom: '.7rem' }} placeholder="Search history…"
               value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search change history" />
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
        ) : <p className="text-muted">No matching history.</p>}
    </Section>
  );
}

function Welfare({ title, icon, count, children }) {
  return (
    <div className="card mb-3 profile-wide">
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
      <div className="filter-actions"><button type="submit" className="sp-btn sp-btn-sm sp-btn-primary" disabled={disabled}><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
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
      <div className="filter-actions"><button type="submit" className="sp-btn sp-btn-sm sp-btn-primary" disabled={disabled}><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
    </form>
  );
}
