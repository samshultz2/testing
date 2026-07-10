import React, { useState, useEffect, useRef } from 'react';
import { submitJson, postFile } from '../lib/forms';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, SectionTabs, Empty, Modal } from '../components/ui';

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'], ['staff', 'fa-users', 'Staff'],
  ['attendance', 'fa-user-clock', 'Attendance'], ['leave', 'fa-plane-departure', 'Leave'],
  ['payroll', 'fa-money-check-dollar', 'Payroll'], ['departments', 'fa-sitemap', 'Departments'],
  ['reports', 'fa-chart-line', 'Reports'], ['settings', 'fa-gear', 'Settings'],
];
const TAB_FOR = { staff_form: 'staff', staff_detail: 'staff', payroll_detail: 'payroll',
  checkin: 'attendance', checkin_qr: 'attendance' };

function Tabs({ d }) {
  const nav = useNav();
  return <SectionTabs tabs={TABS} urls={d.nav} active={TAB_FOR[d.page] || d.page} go={nav.go} />;
}

const nairaShort = (n) => {
  n = Number(n) || 0;
  if (n >= 1e6) return '₦' + (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return '₦' + (n / 1e3).toFixed(1) + 'k';
  return naira(n);
};
const statusBadge = (s) => 'badge ' + (s === 'Active' ? 'badge-success' : s === 'On Leave' ? 'badge-warning' : 'badge-danger');
const typeBadge = (t) => 'badge ' + (t === 'Teaching' ? 'badge-info' : 'badge-secondary');
const leaveBadge = (s) => 'badge ' + (s === 'Approved' ? 'badge-success' : s === 'Rejected' ? 'badge-danger' : 'badge-warning');
const runBadge = (s) => 'badge ' + (s === 'Paid' ? 'badge-success' : s === 'Finalized' ? 'badge-info' : 'badge-warning');

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const st = d.stats;
  const deptRef = useRef();
  const typeRef = useRef();
  useEffect(() => {
    if (!window.Chart) return;
    const charts = [];
    const cs = getComputedStyle(document.body);
    window.Chart.defaults.color = cs.getPropertyValue('--text-secondary') || '#666';
    const PALETTE = ['#4e73df', '#1cc88a', '#f6c23e', '#e74a3b', '#7e6cf0', '#11998e', '#fd7e14', '#20c997'];
    if (deptRef.current && st.dept_chart.length) {
      charts.push(new window.Chart(deptRef.current, {
        type: 'bar', data: { labels: st.dept_chart.map((x) => x.name), datasets: [{ data: st.dept_chart.map((x) => x.count), backgroundColor: '#4e73df', borderRadius: 5 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } },
      }));
    }
    if (typeRef.current && st.total) {
      charts.push(new window.Chart(typeRef.current, {
        type: 'doughnut', data: { labels: st.type_chart.map((x) => x.name), datasets: [{ data: st.type_chart.map((x) => x.count), backgroundColor: PALETTE, borderWidth: 0 }] },
        options: { maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } } },
      }));
    }
    return () => charts.forEach((c) => c.destroy());
  }, [st]);

  const kpis = [['blue', 'fa-users', st.total, 'Total staff', null, d.nav.staff],
    ['green', 'fa-chalkboard-user', st.teaching, 'Teaching', null, d.nav.staff + '?staff_type=Teaching'],
    ['purple', 'fa-user-gear', st.non_teaching, 'Non-teaching', null, d.nav.staff + '?staff_type=Non-teaching'],
    ['green', 'fa-user-check', st.active != null ? st.active : st.total, 'Active', null, null],
    ['amber', 'fa-plane-departure', st.on_leave, 'On leave', null, d.nav.staff + '?status=On Leave'],
    ['blue', 'fa-user-plus', st.new_hires || 0, 'New this month', null, null],
    ['red', 'fa-file-contract', st.contract_expiring || 0, 'Contracts expiring', null, d.urls.reports + '?type=contracts'],
    ['amber', 'fa-money-check-dollar', nairaShort(st.monthly_payroll), 'Monthly payroll', naira(st.monthly_payroll), null]];
  const quick = [
    [d.urls.add_staff, 'fa-user-plus', 'Add staff', 'btn-primary'],
    [d.urls.attendance, 'fa-user-clock', 'Attendance', 'btn-secondary'],
    [d.urls.leave_pending, 'fa-plane-departure', 'Approve leave', 'btn-secondary'],
    [d.urls.reports, 'fa-chart-line', 'Reports', 'btn-secondary'],
  ];
  return (
    <>
      <div className="page-header"><h1>Staff &amp; HR</h1>
        <div className="page-header-actions"><a href={d.urls.add_staff} className="btn btn-primary"><i aria-hidden="true" className="fas fa-user-plus" /> Add Staff</a></div>
      </div>
      <Tabs d={d} />
      <div className="d-flex gap-2 flex-wrap mb-3">
        {quick.map(([href, ic, label, cls]) => <a key={label} href={href} className={'btn btn-sm ' + cls}><i aria-hidden="true" className={'fas ' + ic} /> {label}</a>)}
      </div>
      <div className="kpi-row">{kpis.map(([c, ic, v, l, title, href]) => {
        const inner = <><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div>
          <div><div className="v" title={title || ''}>{v}</div><div className="l">{l}</div></div></>;
        return href ? <a className="kpi" key={l} href={href} style={{ textDecoration: 'none', color: 'inherit' }}>{inner}</a>
          : <div className="kpi" key={l}>{inner}</div>;
      })}
      </div>
      <div className="hr-grid c2">
        <div className="widget"><div className="wh"><h3><i aria-hidden="true" className="fas fa-sitemap" /> Staff by department</h3></div>
          <div className="wb"><div className="chart-box">{st.dept_chart.length ? <canvas ref={deptRef} /> : <Empty icon="fa-sitemap" title=""><p>No staff yet</p></Empty>}</div></div></div>
        <div className="widget"><div className="wh"><h3><i aria-hidden="true" className="fas fa-chart-pie" /> Teaching vs non-teaching</h3></div>
          <div className="wb"><div className="chart-box">{st.total ? <canvas ref={typeRef} /> : <Empty icon="fa-chart-pie" title=""><p>No staff yet</p></Empty>}</div></div></div>
      </div>
      <div className="hr-grid c2">
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-plane-departure" /> Pending leave ({st.pending_leave})</h3><a href={d.urls.leave_pending} className="text-sm">Review</a></div>
          <div className="wb" style={{ padding: 0 }}>
            {d.pending_leaves.length ? (
              <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
                <thead><tr><th>Staff</th><th>Type</th><th>Dates</th><th>Days</th></tr></thead>
                <tbody>{d.pending_leaves.map((lv, i) => (
                  <tr key={i}><td data-label="Staff">{lv.staff_name}</td><td data-label="Type">{lv.leave_type}</td><td data-label="Dates">{lv.dates}</td><td data-label="Days">{lv.days}</td></tr>))}</tbody>
              </table></div>
            ) : <Empty icon="fa-check" title="" style={{ padding: '1.4rem' }}><p>No pending leave requests</p></Empty>}
          </div>
        </div>
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-user-clock" /> Recently added</h3><a href={d.nav.staff} className="text-sm">All staff</a></div>
          <div className="wb" style={{ padding: 0 }}>
            {d.recent.length ? (
              <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
                <thead><tr><th>Name</th><th>Designation</th><th>Dept</th></tr></thead>
                <tbody>{d.recent.map((s) => (
                  <tr key={s.id}><td data-label="Name"><a href={s.url}>{s.full_name}</a></td><td data-label="Designation" className="text-muted text-sm">{s.designation}</td><td data-label="Dept">{s.department}</td></tr>))}</tbody>
              </table></div>
            ) : <Empty icon="fa-user-plus" title="" style={{ padding: '1.4rem' }}><p>No staff yet</p><a href={d.urls.add_staff} className="btn btn-primary btn-sm mt-2">Add staff</a></Empty>}
          </div>
        </div>
      </div>
      <div className="hr-grid c2">
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-cake-candles" /> Upcoming birthdays</h3></div>
          <div className="wb" style={{ padding: 0 }}>
            {(d.birthdays || []).length ? (
              <table className="data-table table-stack no-mobile-scroll"><tbody>
                {d.birthdays.map((b) => (
                  <tr key={b.id}><td data-label="Name"><a href={b.url}>{b.name}</a></td>
                    <td data-label="Birthday">{b.date}</td>
                    <td data-label="In" className="text-right"><span className="badge badge-secondary">{b.in_days === 0 ? 'Today' : `in ${b.in_days}d`}</span></td></tr>))}
              </tbody></table>
            ) : <Empty icon="fa-cake-candles" title="" style={{ padding: '1.4rem' }}><p>None in the next 30 days</p></Empty>}
          </div>
        </div>
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-file-contract" /> Contracts expiring</h3><a href={d.urls.reports + '?type=contracts'} className="text-sm">All</a></div>
          <div className="wb" style={{ padding: 0 }}>
            {(d.contracts || []).length ? (
              <table className="data-table table-stack no-mobile-scroll"><tbody>
                {d.contracts.map((c) => (
                  <tr key={c.id}><td data-label="Name"><a href={c.url}>{c.name}</a></td>
                    <td data-label="Ends">{c.ends}</td>
                    <td data-label="Left" className="text-right"><span className={'badge ' + (c.days_left <= 14 ? 'badge-danger' : 'badge-warning')}>{c.days_left}d</span></td></tr>))}
              </tbody></table>
            ) : <Empty icon="fa-file-contract" title="" style={{ padding: '1.4rem' }}><p>None expiring soon</p></Empty>}
          </div>
        </div>
      </div>
    </>
  );
}

// ---- Staff list ------------------------------------------------------------
function Staff({ d, notify }) {
  const nav = useNav();
  const a = d.applied;
  const [q, setQ] = useState(a.q);
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef();
  const go = (extra) => navParams(nav.go, d.self_url, { department_id: a.department_id, staff_type: a.staff_type, status: a.status, q, ...extra });
  const onImport = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    const r = await postFile(d.urls.import, file);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Import failed.');
  };
  return (
    <>
      <div className="page-header"><h1>Staff Directory</h1>
        <div className="page-header-actions">
          <input type="file" ref={fileRef} accept=".csv,text/csv" style={{ display: 'none' }} onChange={onImport} />
          {d.is_admin !== false && <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => fileRef.current && fileRef.current.click()}><i aria-hidden="true" className="fas fa-file-import" /> Import</button>}
          <button type="button" className="btn btn-secondary" onClick={() => setNotifyOpen(true)}><i aria-hidden="true" className="fas fa-bullhorn" /> Notify</button>
          <a href={d.urls.export} className="btn btn-secondary" data-native download><i aria-hidden="true" className="fas fa-file-csv" /> Export</a>
          <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-user-plus" /> Add Staff</a>
        </div>
      </div>
      <Tabs d={d} />
      {notifyOpen && <NotifyStaffModal d={d} onClose={() => setNotifyOpen(false)} notify={notify} />}
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form" onSubmit={(e) => { e.preventDefault(); go(); }}>
          <div className="form-group"><label className="form-label">Department</label>
            <select className="form-control" value={a.department_id} onChange={(e) => go({ department_id: e.target.value })}>
              <option value="">All</option>{d.departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Type</label>
            <select className="form-control" value={a.staff_type} onChange={(e) => go({ staff_type: e.target.value })}>
              <option value="">All</option>{d.staff_types.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Status</label>
            <select className="form-control" value={a.status} onChange={(e) => go({ status: e.target.value })}>
              <option value="">All</option>{d.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Search</label>
            <input type="text" className="form-control" value={q} placeholder="Name, ID, role, phone" onChange={(e) => setQ(e.target.value)} /></div>
        </form>
      </div></div>
      <div className="card"><div className="card-header"><h3>{d.staff.length} staff</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.staff.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Staff ID</th><th>Name</th><th>Designation</th><th>Department</th><th>Type</th><th>Status</th><th /></tr></thead>
              <tbody>{d.staff.map((s) => (
                <tr key={s.id}>
                  <td data-label="Staff ID">{s.staff_id}</td>
                  <td data-label="Name"><a href={s.url}><strong>{s.full_name}</strong></a>{s.phone && <div className="text-muted text-sm">{s.phone}</div>}</td>
                  <td data-label="Designation">{s.designation}</td>
                  <td data-label="Department">{s.department}</td>
                  <td data-label="Type"><span className={typeBadge(s.staff_type)}>{s.staff_type}</span></td>
                  <td data-label="Status"><span className={statusBadge(s.status)}>{s.status}</span></td>
                  <td className="actions"><a href={s.url} className="btn btn-secondary btn-sm" aria-label="Open"><i aria-hidden="true" className="fas fa-arrow-right" /></a></td>
                </tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-users" title="No staff found"><p>Add your first staff member or adjust filters.</p><a href={d.urls.add} className="btn btn-primary mt-2">Add Staff</a></Empty>}
        </div></div>
    </>
  );
}

// ---- Staff form (add / edit) ----------------------------------------------
function StaffForm({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState(d.staff);
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
  const T = ({ k, label, type = 'text', req, ...rest }) => (
    <div className="form-group"><label className="form-label">{label}{req && <span className="required"> *</span>}</label>
      <input type={type} className="form-control" required={req} value={f[k]} onChange={(e) => set(k, e.target.value)} {...rest} /></div>
  );
  return (
    <>
      <div className="page-header"><h1>{d.mode === 'edit' ? 'Edit Staff' : 'Add Staff'}</h1></div>
      <form onSubmit={submit}>
        <div className="card mb-3"><div className="card-header"><h3>Personal</h3></div><div className="card-body">
          <div className="form-row"><T k="first_name" label="First name" req /><T k="surname" label="Surname" req /></div>
          <div className="form-row"><T k="middle_name" label="Middle name" />
            <div className="form-group"><label className="form-label">Gender</label>
              <select className="form-control" value={f.gender} onChange={(e) => set('gender', e.target.value)}><option value="">—</option><option>Male</option><option>Female</option></select></div>
            <T k="date_of_birth" label="Date of birth" type="date" /></div>
          <div className="form-row"><T k="phone" label="Phone" /><T k="email" label="Email" type="email" /></div>
          <T k="address" label="Address" />
        </div></div>

        <div className="card mb-3"><div className="card-header"><h3>Employment</h3></div><div className="card-body">
          <div className="form-row">
            <div className="form-group"><label className="form-label">Department</label>
              <select className="form-control" value={f.department_id} onChange={(e) => set('department_id', e.target.value)}><option value="">—</option>{d.departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
            <T k="designation" label="Designation" placeholder="e.g., Mathematics Teacher" /></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Staff type</label>
              <select className="form-control" value={f.staff_type} onChange={(e) => set('staff_type', e.target.value)}>{d.staff_types.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Employment</label>
              <select className="form-control" value={f.employment_type} onChange={(e) => set('employment_type', e.target.value)}>{d.employment_types.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Status</label>
              <select className="form-control" value={f.status} onChange={(e) => set('status', e.target.value)}>{d.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
          </div>
          <div className="form-row"><T k="date_employed" label="Date employed" type="date" /><T k="salary" label="Monthly salary (₦)" type="number" min="0" step="500" /></div>
          <div className="form-row"><T k="confirmation_date" label="Confirmation date" type="date" />
            <T k="contract_start" label="Contract start" type="date" /><T k="contract_end" label="Contract end / expiry" type="date" /></div>
          <div className="form-row"><T k="qualification" label="Qualification" placeholder="e.g., B.Sc Mathematics, PGDE" />
            <T k="prior_experience_years" label="Prior experience (yrs)" type="number" min="0" /></div>
          <T k="certifications" label="Professional certifications" placeholder="e.g., TRCN, ICAN" />
        </div></div>

        <div className="card mb-3"><div className="card-header"><h3>Next of kin &amp; emergency</h3></div><div className="card-body">
          <div className="form-row"><T k="nok_name" label="Next of kin" /><T k="nok_phone" label="NOK phone" /><T k="nok_relationship" label="Relationship" /></div>
          <div className="form-row"><T k="emergency_name" label="Emergency contact" /><T k="emergency_phone" label="Emergency phone" /></div>
        </div></div>

        <div className="card mb-3"><div className="card-header"><h3>Bank, statutory &amp; medical</h3></div><div className="card-body">
          <div className="form-row"><T k="bank_name" label="Bank" /><T k="account_number" label="Account number" /><T k="account_name" label="Account name" /></div>
          <div className="form-row"><T k="tax_id" label="Tax ID (TIN)" /><T k="pension_pin" label="Pension PIN" /><T k="pension_provider" label="Pension provider (PFA)" /></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Blood group</label>
              <select className="form-control" value={f.blood_group} onChange={(e) => set('blood_group', e.target.value)}><option value="">—</option>{(d.blood_groups || []).map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
            <div className="form-group" style={{ flex: 2 }}><label className="form-label">Medical notes</label>
              <input type="text" className="form-control" placeholder="Allergies, conditions (confidential)" value={f.medical_notes} onChange={(e) => set('medical_notes', e.target.value)} /></div>
          </div>
          <div className="form-group"><label className="form-label">Notes</label><textarea className="form-control" rows="2" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></div>
        </div></div>

        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> {d.mode === 'edit' ? 'Save Changes' : 'Add Staff'}</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form>
    </>
  );
}

// ---- Profile hub: cross-module snapshot (teaching, attendance, leave) ------
function ProfileHub({ d }) {
  const tl = d.teaching_load;
  const att = d.attendance_summary || {};
  const lv = d.leave_summary || {};
  const leaveTypes = Object.entries(lv.by_type || {});
  return (
    <div className="hr-hub-grid mb-3">
      {tl && tl.is_teacher && (
        <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chalkboard-user" /> Teaching load</h3></div>
          <div className="card-body">
            <div className="hub-stat-row">
              <div className="hub-stat"><div className="v">{tl.class_count}</div><div className="l">Classes</div></div>
              <div className="hub-stat"><div className="v">{tl.subject_count}</div><div className="l">Subject slots</div></div>
              <div className="hub-stat"><div className="v">{tl.form_classes.length}</div><div className="l">Form classes</div></div>
            </div>
            {tl.form_classes.length > 0 && <p className="text-sm mt-2 mb-1"><strong>Form teacher:</strong> {tl.form_classes.join(', ')}</p>}
            {tl.subjects.length > 0
              ? <div className="chip-wrap">{tl.subjects.slice(0, 12).map((x, i) => <span key={i} className="badge badge-secondary">{x.subject} · {x.class}</span>)}
                  {tl.subjects.length > 12 && <span className="badge badge-light">+{tl.subjects.length - 12}</span>}</div>
              : <p className="text-muted text-sm mb-0">No subject assignments this term.</p>}
          </div>
        </div>
      )}
      <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-user-clock" /> Attendance</h3>
        <span className="text-muted text-sm">{d.attendance_month}</span></div>
        <div className="card-body">
          <div className="hub-stat-row">
            <div className="hub-stat"><div className="v text-success">{att.present || 0}</div><div className="l">Present</div></div>
            <div className="hub-stat"><div className="v text-warning">{att.late || 0}</div><div className="l">Late</div></div>
            <div className="hub-stat"><div className="v text-danger">{att.absent || 0}</div><div className="l">Absent</div></div>
            <div className="hub-stat"><div className="v">{att.excused || 0}</div><div className="l">Excused</div></div>
          </div>
          {att.deduction > 0 && <p className="text-sm mt-2 mb-0 text-muted">Deductions this month: <strong>{naira(att.deduction)}</strong></p>}
          {!att.marked && <p className="text-muted text-sm mb-0 mt-2">No attendance marked yet this month.</p>}
        </div>
      </div>
      <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plane-departure" /> Leave (this year)</h3>
        {lv.pending > 0 && <span className="badge badge-warning">{lv.pending} pending</span>}</div>
        <div className="card-body">
          <div className="hub-stat-row">
            <div className="hub-stat"><div className="v">{lv.total_days || 0}</div><div className="l">Days taken</div></div>
            <div className="hub-stat"><div className="v">{lv.pending || 0}</div><div className="l">Pending</div></div>
          </div>
          {(d.leave_balances || []).length > 0
            ? <table className="data-table" style={{ marginTop: '.5rem' }}><tbody>
                {d.leave_balances.map((b) => (
                  <tr key={b.type}><td>{b.type}</td>
                    <td className="text-right text-muted text-sm">{b.taken}/{b.allowance}</td>
                    <td className="text-right"><span className={'badge ' + (b.remaining > 0 ? 'badge-success' : b.remaining < 0 ? 'badge-danger' : 'badge-secondary')}>{b.remaining} left</span></td></tr>))}
              </tbody></table>
            : (leaveTypes.length > 0
                ? <div className="chip-wrap mt-2">{leaveTypes.map(([t, n]) => <span key={t} className="badge badge-secondary">{t}: {n}d</span>)}</div>
                : <p className="text-muted text-sm mb-0 mt-2">No approved leave this year.</p>)}
        </div>
      </div>
    </div>
  );
}

// ---- Staff detail ----------------------------------------------------------
function StaffDetail({ d, notify }) {
  const nav = useNav();
  const s = d.s;
  const act = async (url, fields, confirmMsg, follow) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); follow ? nav.go(r.redirect) : nav.refresh(); }
    else notify('error', r.error || 'Action failed.');
  };
  const Row = ({ k, v }) => <div className="info-row"><span className="k">{k}</span><span className="v">{v || '—'}</span></div>;
  return (
    <>
      <div className="page-header"><h1>Staff Profile</h1>
        <div className="page-header-actions">
          {s.phone && <><a href={'tel:' + s.phone} className="btn btn-secondary" aria-label="Call"><i aria-hidden="true" className="fas fa-phone" /></a>
            <a href={'https://wa.me/' + s.wa_intl} target="_blank" rel="noopener" className="btn btn-secondary" aria-label="WhatsApp"><i aria-hidden="true" className="fab fa-whatsapp" /></a></>}
          <a href={d.urls.edit} className="btn btn-primary"><i aria-hidden="true" className="fas fa-edit" /> Edit</a>
          {d.is_admin && <button className="btn btn-danger" onClick={() => act(d.urls.delete, {}, `Archive ${s.full_name}?`, true)}><i aria-hidden="true" className="fas fa-box-archive" /></button>}
        </div>
      </div>

      <div className="card mb-3"><div className="card-body"><div className="profile-head">
        {s.photo_url ? <img className="avatar" src={s.photo_url} alt="" /> : <div className="avatar">{s.initials}</div>}
        <div style={{ flex: 1, minWidth: 200 }}>
          <h2 style={{ margin: 0 }}>{s.full_name}</h2>
          <div className="text-muted">{s.designation || '—'}{s.department && ` · ${s.department}`}</div>
          <div className="mt-1">
            <span className={typeBadge(s.staff_type)}>{s.staff_type}</span>{' '}
            <span className="badge badge-secondary">{s.employment_type}</span>{' '}
            <span className={statusBadge(s.status)}>{s.status}</span>{' '}
            <span className="badge badge-primary">{s.staff_id}</span>
            {s.years_of_service > 0 && <> <span className="badge badge-info">{s.years_of_service} yr{s.years_of_service !== 1 ? 's' : ''} service</span></>}
          </div>
        </div>
      </div></div></div>

      {s.contract_expiring && (
        <Banner tone={s.contract_days_left < 0 ? 'error' : 'warning'}>
          <i aria-hidden="true" className="fas fa-file-contract" />{' '}
          {s.contract_days_left < 0
            ? `Contract expired on ${s.contract_end} (${-s.contract_days_left} day(s) ago).`
            : `Contract expires on ${s.contract_end} — in ${s.contract_days_left} day(s).`}
        </Banner>
      )}

      <ProfileHub d={d} />

      <div className="hr-2col">
        <div className="card"><div className="card-header"><h3>Details</h3></div><div className="card-body"><div className="info-grid">
          <Row k="Phone" v={s.phone} /><Row k="Email" v={s.email} /><Row k="Gender" v={s.gender} />
          <Row k="Date of birth" v={s.date_of_birth + (s.age != null ? ` (${s.age})` : '')} />
          <Row k="Date employed" v={s.date_employed} /><Row k="Confirmed" v={s.confirmation_date} />
          <Row k="Experience" v={s.total_experience_years ? `${s.total_experience_years} yr(s)` : ''} />
          <Row k="Salary" v={s.salary ? naira(s.salary) : ''} /><Row k="Qualification" v={s.qualification} />
          <Row k="Certifications" v={s.certifications} /><Row k="Address" v={s.address} />
          {(s.contract_start || s.contract_end) && <Row k="Contract" v={[s.contract_start, s.contract_end].filter(Boolean).join(' – ')} />}
        </div></div></div>
        <div className="card"><div className="card-header"><h3>Kin, statutory &amp; medical</h3></div><div className="card-body"><div className="info-grid">
          <Row k="Next of kin" v={s.nok_name} /><Row k="NOK phone" v={s.nok_phone} /><Row k="Relationship" v={s.nok_relationship} />
          <Row k="Emergency" v={s.emergency_name} /><Row k="Emergency phone" v={s.emergency_phone} />
          <Row k="Bank" v={s.bank_name} /><Row k="Account no." v={s.account_number} /><Row k="Account name" v={s.account_name} />
          <Row k="Tax ID" v={s.tax_id} /><Row k="Pension PIN" v={s.pension_pin} /><Row k="PFA" v={s.pension_provider} />
          <Row k="Blood group" v={s.blood_group} /><Row k="Medical" v={s.medical_notes} />
        </div>{s.notes && <p className="text-muted text-sm mt-2">{s.notes}</p>}</div></div>
      </div>

      <LifecycleTimeline d={d} act={act} />
      <div className="hr-2col">
        <DocumentsSection d={d} act={act} notify={notify} />
        <TrainingSection d={d} act={act} notify={notify} />
      </div>
      <ReviewsSection d={d} act={act} notify={notify} />
      <SalarySection d={d} act={act} />
      <LeaveSection d={d} act={act} notify={notify} />
      {d.payslips.length > 0 && (
        <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-money-check-dollar" /> Payslips</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Period</th><th className="text-right">Basic</th><th className="text-right">Allow.</th><th className="text-right">Deduct.</th><th className="text-right">Net</th><th /></tr></thead>
            <tbody>{d.payslips.map((ps, i) => (
              <tr key={i}><td data-label="Period">{ps.period}</td><td data-label="Basic" className="text-right">{naira(ps.basic)}</td>
                <td data-label="Allow." className="text-right">{naira(ps.allowances)}</td><td data-label="Deduct." className="text-right">{naira(ps.total_deductions)}</td>
                <td data-label="Net" className="text-right"><strong>{naira(ps.net)}</strong></td>
                <td className="actions"><a href={ps.print_url} className="btn btn-secondary btn-sm" title="Payslip" data-native><i aria-hidden="true" className="fas fa-print" /></a></td></tr>))}</tbody>
          </table></div></div></div>
      )}
    </>
  );
}

// ---- Lifecycle quick-actions + merged timeline -----------------------------
const TL_TONE = { green: 'var(--success)', blue: 'var(--primary)', amber: 'var(--warning)', purple: '#7e6cf0', muted: 'var(--text-muted)' };

function LifecycleTimeline({ d, act }) {
  const s = d.s;
  const [open, setOpen] = useState(null);   // 'promote' | 'transfer' | 'confirm' | 'note'
  const [f, setF] = useState({});
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const toggle = (which, seed) => { setOpen(open === which ? null : which); setF(seed || {}); };
  const done = () => { setOpen(null); setF({}); };
  const submit = async (url, fields, confirmMsg) => { await act(url, fields, confirmMsg); done(); };
  const branches = d.can_transfer || [];

  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-timeline" /> Employment timeline</h3>
      <div className="d-flex gap-1 flex-wrap">
        {d.is_admin && <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggle('promote', { designation: s.designation || '', new_salary: s.salary || '', effective_date: d.today })}><i aria-hidden="true" className="fas fa-arrow-trend-up" /> Promote</button>}
        {d.is_admin && branches.length > 0 && <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggle('transfer', { effective_date: d.today })}><i aria-hidden="true" className="fas fa-arrows-left-right" /> Transfer</button>}
        {d.is_admin && !s.confirmation_date && <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggle('confirm', { effective_date: d.today })}><i aria-hidden="true" className="fas fa-user-check" /> Confirm</button>}
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggle('note', { effective_date: d.today })}><i aria-hidden="true" className="fas fa-note-sticky" /> Note</button>
      </div>
    </div>
      <div className="card-body">
        {open === 'promote' && (
          <form className="lc-form" onSubmit={(e) => { e.preventDefault(); if (!(f.designation || '').trim()) return; submit(d.urls.promote, f); }}>
            <div className="form-group mb-0"><label className="form-label">New position/title</label><input type="text" className="form-control" required value={f.designation || ''} onChange={(e) => set('designation', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">New salary (optional)</label><input type="number" className="form-control" min="0" step="500" value={f.new_salary || ''} onChange={(e) => set('new_salary', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Effective</label><input type="date" className="form-control" value={f.effective_date || ''} onChange={(e) => set('effective_date', e.target.value)} /></div>
            <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-check" /> Save</button>
          </form>
        )}
        {open === 'transfer' && (
          <form className="lc-form" onSubmit={(e) => { e.preventDefault(); if (!f.branch_id) return; submit(d.urls.transfer, f, `Transfer ${s.full_name} to another branch?`); }}>
            <div className="form-group mb-0"><label className="form-label">Destination branch</label>
              <select className="form-control" required value={f.branch_id || ''} onChange={(e) => set('branch_id', e.target.value)}>
                <option value="">Select…</option>{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></div>
            <div className="form-group mb-0"><label className="form-label">Effective</label><input type="date" className="form-control" value={f.effective_date || ''} onChange={(e) => set('effective_date', e.target.value)} /></div>
            <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-check" /> Transfer</button>
          </form>
        )}
        {open === 'confirm' && (
          <form className="lc-form" onSubmit={(e) => { e.preventDefault(); submit(d.urls.confirm, f, `Confirm ${s.full_name} off probation?`); }}>
            <div className="form-group mb-0"><label className="form-label">Confirmation date</label><input type="date" className="form-control" value={f.effective_date || ''} onChange={(e) => set('effective_date', e.target.value)} /></div>
            <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-check" /> Confirm</button>
          </form>
        )}
        {open === 'note' && (
          <form className="lc-form" onSubmit={(e) => { e.preventDefault(); if (!(f.title || '').trim()) return; submit(d.urls.add_note, f); }}>
            <div className="form-group mb-0" style={{ flex: 2 }}><label className="form-label">Note</label><input type="text" className="form-control" required placeholder="e.g., Received award, Warning issued" value={f.title || ''} onChange={(e) => set('title', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Date</label><input type="date" className="form-control" value={f.effective_date || ''} onChange={(e) => set('effective_date', e.target.value)} /></div>
            <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-check" /> Add</button>
          </form>
        )}
        {(d.timeline || []).length ? (
          <ul className="hr-timeline">
            {d.timeline.map((t, i) => (
              <li key={i}><span className="tl-dot" style={{ background: TL_TONE[t.tone] || TL_TONE.muted }}><i aria-hidden="true" className={'fas ' + t.icon} /></span>
                <div className="tl-body"><div className="tl-top"><strong>{t.title}</strong><span className="tl-date">{t.date_label}</span></div>
                  {t.detail && <div className="text-muted text-sm">{t.detail}</div>}</div></li>))}
          </ul>
        ) : <p className="text-muted mb-0">No timeline events yet. Employment, promotions, transfers, salary changes and approved leave appear here.</p>}
      </div></div>
  );
}

// ---- Documents -------------------------------------------------------------
function DocumentsSection({ d, act, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ title: '', doc_type: (d.doc_types || ['Other'])[0], expires_on: '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef();
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Give the document a title.'); return; }
    if (!file) { notify('error', 'Choose a file to upload.'); return; }
    setBusy(true);
    const r = await postFile(d.urls.upload_document, file, f);
    setBusy(false);
    if (r.ok) { notify('success', r.message); setF({ title: '', doc_type: (d.doc_types || ['Other'])[0], expires_on: '' }); setFile(null); if (fileRef.current) fileRef.current.value = ''; nav.refresh(); }
    else notify('error', r.error || 'Upload failed.');
  };
  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-folder-open" /> Documents</h3></div>
      <div className="card-body">
        <form onSubmit={submit} className="lc-form">
          <div className="form-group mb-0" style={{ flex: 2 }}><label className="form-label">Title</label><input type="text" className="form-control" placeholder="e.g. Appointment letter 2024" value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
          <div className="form-group mb-0"><label className="form-label">Type</label><select className="form-control" value={f.doc_type} onChange={(e) => set('doc_type', e.target.value)}>{(d.doc_types || []).map((t) => <option key={t}>{t}</option>)}</select></div>
          <div className="form-group mb-0"><label className="form-label">Expires (optional)</label><input type="date" className="form-control" value={f.expires_on} onChange={(e) => set('expires_on', e.target.value)} /></div>
          <div className="form-group mb-0"><label className="form-label">File</label><input ref={fileRef} type="file" className="form-control" onChange={(e) => setFile(e.target.files && e.target.files[0])} /></div>
          <button className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-upload" /> Upload</button>
        </form>
        {(d.documents || []).length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Title</th><th>Type</th><th>Expires</th><th /></tr></thead>
            <tbody>{d.documents.map((doc) => (
              <tr key={doc.id}><td data-label="Title">{doc.download_url ? <a href={doc.download_url} data-native>{doc.title}</a> : doc.title}{doc.name && <div className="text-muted text-sm">{doc.name}{doc.size ? ` · ${doc.size}` : ''}</div>}</td>
                <td data-label="Type"><span className="badge badge-secondary">{doc.doc_type}</span></td>
                <td data-label="Expires">{doc.expires_on ? <span className={doc.is_expired ? 'text-danger' : ''}>{doc.expires_on}{doc.is_expired ? ' (expired)' : ''}</span> : '—'}</td>
                <td className="actions"><button className="btn btn-danger btn-sm" onClick={() => act(doc.delete_url, {}, `Delete “${doc.title}”?`)}><i aria-hidden="true" className="fas fa-trash" /></button></td></tr>))}</tbody>
          </table></div>
        ) : <p className="text-muted mb-0">No documents on file yet.</p>}
      </div></div>
  );
}

// ---- Training / professional development ------------------------------------
function TrainingSection({ d, act, notify }) {
  const nav = useNav();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: '', kind: (d.training_kinds || ['Training'])[0], provider: '', start_date: '', end_date: '', hours: '', note: '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Enter the programme title.'); return; }
    setBusy(true);
    const r = file ? await postFile(d.urls.add_training, file, f) : await submitJson(d.urls.add_training, f);
    setBusy(false);
    if (r.ok) { notify('success', r.message); setF({ title: '', kind: (d.training_kinds || ['Training'])[0], provider: '', start_date: '', end_date: '', hours: '', note: '' }); setFile(null); setOpen(false); nav.refresh(); }
    else notify('error', r.error || 'Could not add.');
  };
  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-graduation-cap" /> Training &amp; development</h3>
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(!open)}><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
      <div className="card-body">
        {open && (
          <form onSubmit={submit} className="lc-form" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <div className="form-row">
              <div className="form-group mb-0" style={{ flex: 2 }}><label className="form-label">Programme</label><input type="text" className="form-control" value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
              <div className="form-group mb-0"><label className="form-label">Kind</label><select className="form-control" value={f.kind} onChange={(e) => set('kind', e.target.value)}>{(d.training_kinds || []).map((k) => <option key={k}>{k}</option>)}</select></div>
              <div className="form-group mb-0"><label className="form-label">Provider</label><input type="text" className="form-control" value={f.provider} onChange={(e) => set('provider', e.target.value)} /></div>
            </div>
            <div className="form-row">
              <div className="form-group mb-0"><label className="form-label">From</label><input type="date" className="form-control" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
              <div className="form-group mb-0"><label className="form-label">To</label><input type="date" className="form-control" value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
              <div className="form-group mb-0"><label className="form-label">Hours</label><input type="number" className="form-control" min="0" step="0.5" value={f.hours} onChange={(e) => set('hours', e.target.value)} /></div>
              <div className="form-group mb-0"><label className="form-label">Certificate (optional)</label><input type="file" className="form-control" onChange={(e) => setFile(e.target.files && e.target.files[0])} /></div>
            </div>
            <div><button className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</button></div>
          </form>
        )}
        {(d.training || []).length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Programme</th><th>Kind</th><th>Dates</th><th className="text-right">Hrs</th><th /></tr></thead>
            <tbody>{d.training.map((t) => (
              <tr key={t.id}><td data-label="Programme"><strong>{t.title}</strong>{t.provider && <div className="text-muted text-sm">{t.provider}</div>}{t.certificate_url && <a href={t.certificate_url} data-native className="text-sm"><i aria-hidden="true" className="fas fa-certificate" /> Certificate</a>}</td>
                <td data-label="Kind"><span className="badge badge-secondary">{t.kind}</span></td>
                <td data-label="Dates">{t.dates || '—'}</td><td data-label="Hrs" className="text-right">{t.hours || '—'}</td>
                <td className="actions"><button className="btn btn-danger btn-sm" onClick={() => act(t.delete_url, {}, `Remove “${t.title}”?`)}><i aria-hidden="true" className="fas fa-trash" /></button></td></tr>))}</tbody>
          </table></div>
        ) : <p className="text-muted mb-0">No training recorded yet.</p>}
      </div></div>
  );
}

// ---- Performance reviews ----------------------------------------------------
function ReviewsSection({ d, act, notify }) {
  const nav = useNav();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ period: '', review_date: d.today, reviewer: '', score: '', rating: '', strengths: '', improvements: '', comments: '' });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.period.trim()) { notify('error', 'Enter the review period.'); return; }
    const r = await submitJson(d.urls.add_review, f);
    if (r.ok) { notify('success', r.message); setF({ period: '', review_date: d.today, reviewer: '', score: '', rating: '', strengths: '', improvements: '', comments: '' }); setOpen(false); nav.refresh(); }
    else notify('error', r.error || 'Could not save.');
  };
  const ratingBadge = (r) => 'badge ' + (r === 'Excellent' ? 'badge-success' : r === 'Good' ? 'badge-info' : r === 'Poor' ? 'badge-danger' : 'badge-warning');
  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-star-half-stroke" /> Performance reviews</h3>
      {d.is_admin && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(!open)}><i aria-hidden="true" className="fas fa-plus" /> Add review</button>}</div>
      <div className="card-body">
        {open && d.is_admin && (
          <form onSubmit={submit} className="lc-form" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <div className="form-row">
              <div className="form-group mb-0"><label className="form-label">Period</label><input type="text" className="form-control" placeholder="e.g. 2024/2025" value={f.period} onChange={(e) => set('period', e.target.value)} /></div>
              <div className="form-group mb-0"><label className="form-label">Date</label><input type="date" className="form-control" value={f.review_date} onChange={(e) => set('review_date', e.target.value)} /></div>
              <div className="form-group mb-0"><label className="form-label">Reviewer</label><input type="text" className="form-control" value={f.reviewer} onChange={(e) => set('reviewer', e.target.value)} /></div>
              <div className="form-group mb-0"><label className="form-label">Score</label><input type="number" className="form-control" min="0" max="100" value={f.score} onChange={(e) => set('score', e.target.value)} /></div>
              <div className="form-group mb-0"><label className="form-label">Rating</label><select className="form-control" value={f.rating} onChange={(e) => set('rating', e.target.value)}><option value="">—</option>{['Excellent', 'Good', 'Fair', 'Poor'].map((x) => <option key={x}>{x}</option>)}</select></div>
            </div>
            <div className="form-row">
              <div className="form-group mb-0" style={{ flex: 1 }}><label className="form-label">Strengths</label><input type="text" className="form-control" value={f.strengths} onChange={(e) => set('strengths', e.target.value)} /></div>
              <div className="form-group mb-0" style={{ flex: 1 }}><label className="form-label">Areas to improve</label><input type="text" className="form-control" value={f.improvements} onChange={(e) => set('improvements', e.target.value)} /></div>
            </div>
            <div className="form-group mb-0"><label className="form-label">Comments</label><textarea className="form-control" rows="2" value={f.comments} onChange={(e) => set('comments', e.target.value)} /></div>
            <div><button className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save review</button></div>
          </form>
        )}
        {(d.reviews || []).length ? d.reviews.map((r) => (
          <div key={r.id} className="review-item">
            <div className="d-flex justify-between align-center flex-wrap gap-1">
              <div><strong>{r.period}</strong>{r.review_date && <span className="text-muted text-sm"> · {r.review_date}</span>}{r.reviewer && <span className="text-muted text-sm"> · by {r.reviewer}</span>}</div>
              <div className="d-flex gap-1 align-center">
                {r.score != null && <span className="badge badge-primary">{r.score}</span>}
                {r.rating && <span className={ratingBadge(r.rating)}>{r.rating}</span>}
                {d.is_admin && <button className="btn btn-danger btn-sm" onClick={() => act(r.delete_url, {}, `Delete the ${r.period} review?`)}><i aria-hidden="true" className="fas fa-trash" /></button>}
              </div>
            </div>
            {r.strengths && <div className="text-sm mt-1"><strong>Strengths:</strong> {r.strengths}</div>}
            {r.improvements && <div className="text-sm"><strong>Improve:</strong> {r.improvements}</div>}
            {r.comments && <div className="text-muted text-sm mt-1">{r.comments}</div>}
          </div>
        )) : <p className="text-muted mb-0">No performance reviews yet.</p>}
      </div></div>
  );
}

function SalarySection({ d, act }) {
  const s = d.s;
  const [f, setF] = useState({ new_salary: s.salary || '', effective_date: d.today, reason: '' });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = (e) => { e.preventDefault(); act(d.urls.adjust_salary, f, 'Update salary and record this change?'); };
  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-money-bill-trend-up" /> Salary &amp; increments</h3><span className="badge badge-primary" style={{ alignSelf: 'center' }}>Current: {naira(s.salary)}</span></div>
      <div className="card-body">
        {d.is_admin && (
          <form onSubmit={submit} className="d-flex gap-2 align-end flex-wrap mb-3">
            <div className="form-group mb-0"><label className="form-label">New salary (₦)</label><input type="number" className="form-control" min="0" step="500" required value={f.new_salary} onChange={(e) => set('new_salary', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Effective</label><input type="date" className="form-control" value={f.effective_date} onChange={(e) => set('effective_date', e.target.value)} /></div>
            <div className="form-group mb-0" style={{ flex: 1, minWidth: 160 }}><label className="form-label">Reason</label><input type="text" className="form-control" placeholder="e.g., Annual increment, Promotion" value={f.reason} onChange={(e) => set('reason', e.target.value)} /></div>
            <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-arrow-trend-up" /> Apply</button>
          </form>
        )}
        {d.salary_history.length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Effective</th><th className="text-right">Previous</th><th className="text-right">New</th><th className="text-right">Change</th><th>Reason</th></tr></thead>
            <tbody>{d.salary_history.map((h, i) => (
              <tr key={i}><td data-label="Effective">{h.effective}</td><td data-label="Previous" className="text-right">{naira(h.previous_salary)}</td>
                <td data-label="New" className="text-right">{naira(h.new_salary)}</td>
                <td data-label="Change" className="text-right"><span style={{ color: h.change >= 0 ? 'var(--success)' : 'var(--danger)' }}>{h.change >= 0 ? '+' : ''}{naira(h.change)}</span></td>
                <td data-label="Reason" className="text-muted text-sm">{h.reason}</td></tr>))}</tbody>
          </table></div>
        ) : <p className="text-muted mb-0">No salary changes recorded yet.</p>}
      </div></div>
  );
}

function LeaveSection({ d, act }) {
  const s = d.s;
  const [f, setF] = useState({ leave_type: d.leave_types[0], start_date: '', end_date: '', reason: '' });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const add = (e) => { e.preventDefault(); act(d.urls.add_leave, { ...f, staff_id: s.id }); };
  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plane-departure" /> Leave history</h3></div>
      <div className="card-body">
        <form onSubmit={add} className="d-flex gap-2 align-end flex-wrap mb-3">
          <div className="form-group mb-0"><label className="form-label">Type</label><select className="form-control" value={f.leave_type} onChange={(e) => set('leave_type', e.target.value)}>{d.leave_types.map((t) => <option key={t}>{t}</option>)}</select></div>
          <div className="form-group mb-0"><label className="form-label">From</label><input type="date" className="form-control" required value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
          <div className="form-group mb-0"><label className="form-label">To</label><input type="date" className="form-control" required value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
          <div className="form-group mb-0" style={{ flex: 1, minWidth: 160 }}><label className="form-label">Reason</label><input type="text" className="form-control" value={f.reason} onChange={(e) => set('reason', e.target.value)} /></div>
          <button className="btn btn-secondary"><i aria-hidden="true" className="fas fa-plus" /> Add</button>
        </form>
        {d.leaves.length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th /></tr></thead>
            <tbody>{d.leaves.map((lv) => (
              <tr key={lv.id}><td data-label="Type">{lv.leave_type}</td><td data-label="Dates">{lv.dates}</td><td data-label="Days">{lv.days}</td>
                <td data-label="Status"><span className={leaveBadge(lv.status)}>{lv.status}</span></td>
                <td className="actions"><div className="d-flex gap-1 justify-end">
                  {lv.status !== 'Approved' && <button className="btn btn-success btn-sm" title="Approve" onClick={() => act(lv.approve_url, { status: 'Approved' })}><i aria-hidden="true" className="fas fa-check" /></button>}
                  {lv.status !== 'Rejected' && <button className="btn btn-secondary btn-sm" title="Reject" onClick={() => act(lv.approve_url, { status: 'Rejected' })}><i aria-hidden="true" className="fas fa-xmark" /></button>}
                  <button className="btn btn-danger btn-sm" onClick={() => act(lv.delete_url, {}, 'Delete leave record?')}><i aria-hidden="true" className="fas fa-trash" /></button>
                </div></td></tr>))}</tbody>
          </table></div>
        ) : <p className="text-muted mb-0">No leave records.</p>}
      </div></div>
  );
}

// ---- Departments -----------------------------------------------------------
function Departments({ d, notify }) {
  const nav = useNav();
  const [name, setName] = useState('');
  const [editing, setEditing] = useState(null);
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const add = async (e) => {
    e.preventDefault();
    if (!name.trim()) { notify('error', 'Enter a department name.'); return; }
    const r = await submitJson(d.add_url, { name });
    if (r.ok) { setName(''); notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not add.');
  };
  return (
    <>
      <div className="page-header"><h1>Departments</h1></div>
      <Tabs d={d} />
      {d.is_admin && (
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Add Department</h3></div>
          <div className="card-body"><form onSubmit={add} className="d-flex gap-2 align-end flex-wrap">
            <div className="form-group mb-0" style={{ flex: 1, minWidth: 200 }}><label className="form-label">Name</label><input type="text" className="form-control" placeholder="e.g., Sports" required value={name} onChange={(e) => setName(e.target.value)} /></div>
            <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Add</button>
          </form></div></div>
      )}
      <div className="card"><div className="card-header"><h3>Departments ({d.departments.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}><div className="table-container"><table className="data-table table-stack no-mobile-scroll">
          <thead><tr><th>Name</th><th className="text-right">Staff</th><th>Status</th>{d.is_admin && <th />}</tr></thead>
          <tbody>{d.departments.map((dep) => (
            <React.Fragment key={dep.id}>
              <tr>
                <td data-label="Name"><strong>{dep.name}</strong></td>
                <td data-label="Staff" className="text-right">{dep.count}</td>
                <td data-label="Status">{dep.is_active ? <span className="badge badge-success">Active</span> : <span className="badge badge-secondary">Inactive</span>}</td>
                {d.is_admin && <td className="actions"><div className="d-flex gap-1 justify-end">
                  <button className="btn btn-secondary btn-sm" onClick={() => setEditing(editing === dep.id ? null : dep.id)}><i aria-hidden="true" className="fas fa-edit" /></button>
                  <button className="btn btn-danger btn-sm" onClick={() => act(dep.delete_url, {}, `Delete ${dep.name}?`)}><i aria-hidden="true" className="fas fa-trash" /></button>
                </div></td>}
              </tr>
              {d.is_admin && editing === dep.id && (
                <tr><td colSpan={4} className="stack-full" style={{ background: 'var(--gray-50)' }}>
                  <DeptEdit dep={dep} notify={notify} onDone={() => { setEditing(null); nav.refresh(); }} />
                </td></tr>)}
            </React.Fragment>))}</tbody>
        </table></div></div></div>
    </>
  );
}

function DeptEdit({ dep, notify, onDone }) {
  const [name, setName] = useState(dep.name);
  const [active, setActive] = useState(dep.is_active);
  const submit = async (e) => {
    e.preventDefault();
    const r = await submitJson(dep.edit_url, { name, is_active: active ? 'on' : '' });
    if (r.ok) onDone(); else notify('error', r.error || 'Could not update.');
  };
  return (
    <form onSubmit={submit} className="d-flex gap-2 align-end flex-wrap">
      <div className="form-group mb-0" style={{ flex: 1, minWidth: 180 }}><label className="form-label">Name</label><input type="text" className="form-control" value={name} onChange={(e) => setName(e.target.value)} /></div>
      <label className="form-check mb-0"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label>
      <button className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-save" /> Update</button>
    </form>
  );
}

// ---- Leave calendar (month grid of who is off) -----------------------------
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];
const leaveDotTone = (s) => (s === 'Approved' ? 'var(--success)' : s === 'Rejected' ? 'var(--danger)' : 'var(--warning)');

function LeaveCalendar({ leaves, today }) {
  const base = today ? new Date(today) : new Date();
  const [ym, setYm] = useState({ y: base.getFullYear(), m: base.getMonth() });
  const first = new Date(ym.y, ym.m, 1);
  const startPad = first.getDay();
  const daysInMonth = new Date(ym.y, ym.m + 1, 0).getDate();
  const monthStart = new Date(ym.y, ym.m, 1); const monthEnd = new Date(ym.y, ym.m, daysInMonth);
  // Leaves overlapping this month, expanded to the days they touch.
  const byDay = {};
  (leaves || []).forEach((lv) => {
    if (!lv.start || !lv.end) return;
    const s = new Date(lv.start); const e = new Date(lv.end);
    if (e < monthStart || s > monthEnd) return;
    for (let day = 1; day <= daysInMonth; day++) {
      const dte = new Date(ym.y, ym.m, day);
      if (dte >= s && dte <= e) (byDay[day] = byDay[day] || []).push(lv);
    }
  });
  const cells = [];
  for (let i = 0; i < startPad; i++) cells.push(null);
  for (let day = 1; day <= daysInMonth; day++) cells.push(day);
  const shift = (delta) => setYm(({ y, m }) => { const nm = m + delta; return { y: y + Math.floor(nm / 12), m: ((nm % 12) + 12) % 12 }; });
  const todayStr = (today || new Date().toISOString().slice(0, 10));
  return (
    <div className="card"><div className="card-header">
      <h3><i aria-hidden="true" className="fas fa-calendar-days" /> {MONTHS[ym.m]} {ym.y}</h3>
      <div className="d-flex gap-1"><button type="button" className="btn btn-secondary btn-sm" onClick={() => shift(-1)} aria-label="Previous month"><i aria-hidden="true" className="fas fa-chevron-left" /></button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setYm({ y: base.getFullYear(), m: base.getMonth() })}>Today</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => shift(1)} aria-label="Next month"><i aria-hidden="true" className="fas fa-chevron-right" /></button></div>
    </div>
      <div className="card-body">
        <div className="leave-cal">
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((w) => <div key={w} className="lc-head">{w}</div>)}
          {cells.map((day, i) => {
            if (!day) return <div key={i} className="lc-cell lc-empty" />;
            const iso = `${ym.y}-${String(ym.m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const items = byDay[day] || [];
            return (
              <div key={i} className={'lc-cell' + (iso === todayStr ? ' lc-today' : '')}>
                <div className="lc-day">{day}</div>
                {items.slice(0, 3).map((lv, j) => (
                  <div key={j} className="lc-item" title={`${lv.staff_name} · ${lv.leave_type} (${lv.status})`}>
                    <span className="lc-dot" style={{ background: leaveDotTone(lv.status) }} />{lv.staff_name.split(' ')[0]}</div>))}
                {items.length > 3 && <div className="lc-more">+{items.length - 3}</div>}
              </div>);
          })}
        </div>
        <div className="d-flex gap-2 mt-2 text-sm text-muted flex-wrap">
          <span><span className="lc-dot" style={{ background: 'var(--success)' }} /> Approved</span>
          <span><span className="lc-dot" style={{ background: 'var(--warning)' }} /> Pending</span>
        </div>
      </div></div>
  );
}

// ---- Leave -----------------------------------------------------------------
function Leave({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ staff_id: '', leave_type: d.leave_types[0], start_date: '', end_date: '' });
  const [view, setView] = useState('list');
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const add = async (e) => {
    e.preventDefault();
    if (!f.staff_id) { notify('error', 'Select a staff member.'); return; }
    const r = await submitJson(d.add_url, f);
    if (r.ok) { setF({ staff_id: '', leave_type: d.leave_types[0], start_date: '', end_date: '' }); notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Could not add.');
  };
  return (
    <>
      <div className="page-header"><h1>Leave Management</h1></div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Record Leave</h3></div>
        <div className="card-body"><form onSubmit={add} className="d-flex gap-2 align-end flex-wrap">
          <div className="form-group mb-0" style={{ flex: 1, minWidth: 200 }}><label className="form-label">Staff</label>
            <select className="form-control" required value={f.staff_id} onChange={(e) => set('staff_id', e.target.value)}><option value="">Select…</option>{d.staff.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}</select></div>
          <div className="form-group mb-0"><label className="form-label">Type</label><select className="form-control" value={f.leave_type} onChange={(e) => set('leave_type', e.target.value)}>{d.leave_types.map((t) => <option key={t}>{t}</option>)}</select></div>
          <div className="form-group mb-0"><label className="form-label">From</label><input type="date" className="form-control" required value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
          <div className="form-group mb-0"><label className="form-label">To</label><input type="date" className="form-control" required value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
          <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Add</button>
        </form></div></div>

      <div className="card mb-3"><div className="card-body">
        <div className="d-flex justify-between align-end flex-wrap gap-2">
          <form className="filter-form"><div className="form-group"><label className="form-label">Status</label>
            <select className="form-control" value={d.status} onChange={(e) => navParams(nav.go, d.self_url, { status: e.target.value })}>
              <option value="">All</option>{['Pending', 'Approved', 'Rejected'].map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
          </form>
          <div className="btn-group" role="tablist" aria-label="View">
            <button type="button" className={'btn btn-sm ' + (view === 'list' ? 'btn-primary' : 'btn-secondary')} aria-selected={view === 'list'} onClick={() => setView('list')}><i aria-hidden="true" className="fas fa-list" /> List</button>
            <button type="button" className={'btn btn-sm ' + (view === 'calendar' ? 'btn-primary' : 'btn-secondary')} aria-selected={view === 'calendar'} onClick={() => setView('calendar')}><i aria-hidden="true" className="fas fa-calendar-days" /> Calendar</button>
          </div>
        </div>
      </div></div>

      {view === 'calendar' && <LeaveCalendar leaves={d.leaves} today={d.today} />}

      {view === 'list' && (
      <div className="card"><div className="card-header"><h3>{d.leaves.length} record(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.leaves.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Staff</th><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th /></tr></thead>
              <tbody>{d.leaves.map((lv) => (
                <tr key={lv.id}><td data-label="Staff"><a href={lv.staff_url}>{lv.staff_name}</a></td><td data-label="Type">{lv.leave_type}</td>
                  <td data-label="Dates">{lv.dates}</td><td data-label="Days">{lv.days}</td>
                  <td data-label="Status"><span className={leaveBadge(lv.status)}>{lv.status}</span></td>
                  <td className="actions"><div className="d-flex gap-1 justify-end">
                    {lv.status !== 'Approved' && <button className="btn btn-success btn-sm" onClick={() => act(lv.approve_url, { status: 'Approved' })}><i aria-hidden="true" className="fas fa-check" /></button>}
                    {lv.status !== 'Rejected' && <button className="btn btn-secondary btn-sm" onClick={() => act(lv.approve_url, { status: 'Rejected' })}><i aria-hidden="true" className="fas fa-xmark" /></button>}
                    <button className="btn btn-danger btn-sm" onClick={() => act(lv.delete_url, {}, 'Delete?')}><i aria-hidden="true" className="fas fa-trash" /></button>
                  </div></td></tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-plane-departure" title="No leave records"><p>Record staff leave above.</p></Empty>}
        </div></div>
      )}
    </>
  );
}

// ---- Payroll list ----------------------------------------------------------
function Payroll({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ month: d.cur_month, year: d.cur_year });
  const create = async (e) => {
    e.preventDefault();
    const r = await submitJson(d.create_url, f);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not generate.');
  };
  return (
    <>
      <div className="page-header"><h1>Payroll</h1></div>
      <Tabs d={d} />
      {d.is_admin && (
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Generate Payroll</h3></div>
          <div className="card-body">
            <p className="text-muted text-sm">Creates a payslip for every active staff member using their monthly salary. You can adjust allowances/deductions afterwards.</p>
            <form onSubmit={create} className="d-flex gap-2 align-end flex-wrap">
              <div className="form-group mb-0"><label className="form-label">Month</label><select className="form-control" value={f.month} onChange={(e) => setF((s) => ({ ...s, month: e.target.value }))}>{d.months.map((m) => <option key={m.value} value={m.value}>{m.name}</option>)}</select></div>
              <div className="form-group mb-0"><label className="form-label">Year</label><input type="number" className="form-control" min="2000" max="2100" style={{ width: 120 }} value={f.year} onChange={(e) => setF((s) => ({ ...s, year: e.target.value }))} /></div>
              <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-gears" /> Generate</button>
            </form>
          </div></div>
      )}
      <div className="card"><div className="card-header"><h3>Payroll Runs ({d.rows.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.rows.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Period</th><th className="text-right">Staff</th><th className="text-right">Total</th><th>Status</th><th /></tr></thead>
              <tbody>{d.rows.map((r) => (
                <tr key={r.id}><td data-label="Period"><a href={r.url}><strong>{r.period_label}</strong></a></td>
                  <td data-label="Staff" className="text-right">{r.count}</td><td data-label="Total" className="text-right">{naira(r.total)}</td>
                  <td data-label="Status"><span className={runBadge(r.status)}>{r.status}</span></td>
                  <td className="actions"><a href={r.url} className="btn btn-secondary btn-sm" aria-label="Open"><i aria-hidden="true" className="fas fa-arrow-right" /></a></td></tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-money-check-dollar" title="No payroll yet"><p>Generate your first monthly payroll above.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Payroll detail --------------------------------------------------------
function PayrollDetail({ d, notify }) {
  const nav = useNav();
  const run = d.run;
  const [editing, setEditing] = useState(null);
  const act = async (url, fields, confirmMsg, follow) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); follow ? nav.go(r.redirect) : nav.refresh(); }
    else notify('error', r.error || 'Action failed.');
  };
  return (
    <>
      <div className="page-header"><h1>Payroll · {run.period_label}</h1>
        <div className="page-header-actions">
          <span className={runBadge(run.status)} style={{ alignSelf: 'center' }}>{run.status}</span>
          {d.is_admin && run.status === 'Draft' && <>
            <button className="btn btn-secondary" onClick={() => act(d.urls.sync_deductions, {}, "Refresh every payslip's deductions from this month's attendance?")}><i aria-hidden="true" className="fas fa-rotate" /> Refresh deductions from attendance</button>
            <button className="btn btn-primary" onClick={() => act(d.urls.finalize, { post_expense: '1' }, 'Finalize this payroll? You can optionally post the total to Finance.')}><i aria-hidden="true" className="fas fa-lock" /> Finalize &amp; post to Finance</button>
          </>}
          {d.is_admin && run.status === 'Finalized' && <button className="btn btn-success" onClick={() => act(d.urls.mark_paid, {})}><i aria-hidden="true" className="fas fa-check-double" /> Mark paid</button>}
          {d.is_admin && <button className="btn btn-danger" onClick={() => act(d.urls.delete, {}, 'Delete this payroll run and all payslips?', true)}><i aria-hidden="true" className="fas fa-trash" /></button>}
        </div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body d-flex justify-between flex-wrap gap-2">
        <div><div className="text-muted text-sm">Staff</div><strong style={{ fontSize: 'var(--text-lg)' }}>{d.slips.length}</strong></div>
        <div><div className="text-muted text-sm">Total net pay</div><strong style={{ fontSize: 'var(--text-lg)' }}>{naira(d.total)}</strong></div>
        {run.posted_expense_id && <div><div className="text-muted text-sm">Finance</div><span className="badge badge-success">Posted to expenses</span></div>}
      </div></div>
      <div className="card"><div className="card-header"><h3>Payslips</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.slips.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Staff</th><th className="text-right">Basic</th><th className="text-right">Allowances</th><th className="text-right">Manual</th><th className="text-right">Recurring</th><th className="text-right">Attendance</th><th className="text-right">Net</th><th /></tr></thead>
              <tbody>{d.slips.map((ps) => (
                <React.Fragment key={ps.id}>
                  <tr>
                    <td data-label="Staff">{ps.staff_name}</td>
                    <td data-label="Basic" className="text-right">{naira(ps.basic)}</td>
                    <td data-label="Allowances" className="text-right">{naira(ps.allowances)}</td>
                    <td data-label="Manual" className="text-right">{naira(ps.deductions)}</td>
                    <td data-label="Recurring" className="text-right">{ps.recurring_deductions ? <span style={{ color: 'var(--danger)' }} title={ps.items.map((i) => `${i.name}: ${naira(i.amount)}`).join(' · ')}>{naira(ps.recurring_deductions)}</span> : '—'}</td>
                    <td data-label="Attendance" className="text-right">{ps.attendance_deduction ? <span style={{ color: 'var(--danger)' }}>{naira(ps.attendance_deduction)}</span> : '—'}</td>
                    <td data-label="Net" className="text-right"><strong>{naira(ps.net)}</strong></td>
                    <td className="actions"><div className="d-flex gap-1 justify-end">
                      <a href={ps.print_url} className="btn btn-secondary btn-sm" title="Payslip" data-native><i aria-hidden="true" className="fas fa-print" /></a>
                      {d.is_admin && run.status === 'Draft' && <button className="btn btn-secondary btn-sm" title="Edit" onClick={() => setEditing(editing === ps.id ? null : ps.id)}><i aria-hidden="true" className="fas fa-edit" /></button>}
                    </div></td>
                  </tr>
                  {d.is_admin && run.status === 'Draft' && editing === ps.id && (
                    <tr><td colSpan={8} className="stack-full" style={{ background: 'var(--gray-50)' }}>
                      <PayslipEdit ps={ps} notify={notify} onDone={() => { setEditing(null); nav.refresh(); }} />
                      <div className="text-muted text-sm" style={{ marginTop: '.5rem' }}>
                        Auto: attendance {naira(ps.attendance_deduction)}{ps.items.map((i, k) => <span key={k}> · {i.name} {naira(i.amount)}</span>)} · <strong>Total deductions {naira(ps.total_deductions)}</strong>
                      </div>
                    </td></tr>)}
                </React.Fragment>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-money-check-dollar" title="No payslips" />}
        </div></div>
    </>
  );
}

function PayslipEdit({ ps, notify, onDone }) {
  const [f, setF] = useState({ basic: ps.basic, allowances: ps.allowances, deductions: ps.deductions });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    const r = await submitJson(ps.edit_url, f);
    if (r.ok) onDone(); else notify('error', r.error || 'Could not update.');
  };
  return (
    <form onSubmit={submit} className="d-flex gap-2 align-end flex-wrap">
      <div className="form-group mb-0"><label className="form-label">Basic</label><input type="number" className="form-control" step="100" value={f.basic} onChange={(e) => set('basic', e.target.value)} /></div>
      <div className="form-group mb-0"><label className="form-label">Allowances</label><input type="number" className="form-control" step="100" value={f.allowances} onChange={(e) => set('allowances', e.target.value)} /></div>
      <div className="form-group mb-0"><label className="form-label">Manual deductions</label><input type="number" className="form-control" step="100" value={f.deductions} onChange={(e) => set('deductions', e.target.value)} /></div>
      <button className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-save" /> Update</button>
    </form>
  );
}

// ---- Attendance ------------------------------------------------------------
function Attendance({ d, notify }) {
  const nav = useNav();
  const [rows, setRows] = useState(() => d.rows.map((r) => ({ ...r })));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setRows(d.rows.map((r) => ({ ...r }))); }, [d.rows]);
  const setRow = (id, k, v) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, [k]: v } : r)));
  const s = d.settings;
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const fields = { date: d.day, staff_id: rows.map((r) => r.id) };
    rows.forEach((r) => { fields['status_' + r.id] = r.status; fields['clock_' + r.id] = r.clock_in; });
    const r = await submitJson(d.save_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.go(r.redirect); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Staff Attendance</h1>
        <div className="page-header-actions">
          <a href={d.checkin_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-location-crosshairs" /> Self check-in</a>
          <a href={d.qr_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-qrcode" /> Show QR</a>
        </div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form">
          <div className="form-group"><label className="form-label">Date</label><input type="date" className="form-control" value={d.day} onChange={(e) => navParams(nav.go, d.self_url, { date: e.target.value, department_id: d.dept_id })} /></div>
          <div className="form-group"><label className="form-label">Department</label>
            <select className="form-control" value={d.dept_id} onChange={(e) => navParams(nav.go, d.self_url, { date: d.day, department_id: e.target.value })}>
              <option value="">All</option>{d.departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
        </form>
        <div className="sum-chips mt-2">
          <span className="chip" style={{ background: 'rgba(28,200,138,.15)' }}>Resumption {s.late_time} · ₦{s.late_rate}/min late{s.absence_deduction ? ` · ₦${Math.round(s.absence_deduction).toLocaleString()}/absence` : ''}</span>
          <span className="chip">Present: {d.summary.present}</span>
          <span className="chip" style={{ background: 'rgba(246,194,62,.18)' }}>Late: {d.summary.late}</span>
          <span className="chip" style={{ background: 'rgba(231,74,59,.15)' }}>Absent: {d.summary.absent}</span>
          <span className="chip" style={{ background: 'rgba(231,74,59,.15)' }}>Deductions: {naira(d.summary.deduction)}</span>
        </div>
      </div></div>

      <form onSubmit={save}>
        <div className="card"><div className="card-header"><h3>{rows.length} staff · {d.day_label}</h3>
          <button type="submit" className="btn btn-primary btn-sm" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</button></div>
          <div className="card-body" style={{ padding: 0 }}>
            {rows.length ? (
              <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
                <thead><tr><th>Staff</th><th>Status</th><th>Clock-in</th><th>Late</th><th className="text-right">Deduction</th></tr></thead>
                <tbody>{rows.map((r) => (
                  <tr key={r.id}>
                    <td data-label="Staff">{r.full_name}</td>
                    <td data-label="Status" className="att-status"><select className="form-control" value={r.status} onChange={(e) => setRow(r.id, 'status', e.target.value)}>{d.att_statuses.map((st) => <option key={st} value={st}>{st}</option>)}</select></td>
                    <td data-label="Clock-in"><input type="time" className="form-control" style={{ maxWidth: 130 }} value={r.clock_in} onChange={(e) => setRow(r.id, 'clock_in', e.target.value)} /></td>
                    <td data-label="Late">{r.minutes_late ? <span className="badge badge-warning">{r.minutes_late} min</span> : '—'}</td>
                    <td data-label="Deduction" className="text-right">{r.deduction ? <span style={{ color: 'var(--danger)' }}>{naira(r.deduction)}</span> : '—'}</td>
                  </tr>))}</tbody>
              </table></div>
            ) : <Empty icon="fa-user-clock" title="No active staff"><p>Add staff to mark attendance.</p></Empty>}
          </div></div>
        {rows.length > 0 && <div className="page-header-actions mt-3"><button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Attendance</button></div>}
      </form>
      <p className="text-muted text-sm mt-2"><i aria-hidden="true" className="fas fa-circle-info" /> Lateness deductions are calculated from the clock-in time vs the resumption time set in <a href={d.settings_url}>Settings</a>, and flow into that month's payroll automatically.</p>
    </>
  );
}

// ---- Biometric / access-control device token -------------------------------
function DeviceTokenCard({ d, notify }) {
  const nav = useNav();
  const [token, setToken] = useState(d.device_token || '');
  const [busy, setBusy] = useState(false);
  const gen = async (action) => {
    if (action === 'clear' && !await confirm('Clear the device token? Existing devices will stop posting attendance.')) return;
    setBusy(true);
    const r = await submitJson(d.device_token_url, action ? { action } : {});
    setBusy(false);
    if (r.ok) { if (r.token) setToken(r.token); else setToken(''); notify('success', r.message || 'Done.'); nav.refresh(); }
    else notify('error', r.error || 'Could not update the token.');
  };
  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-fingerprint" /> Biometric / device API</h3></div>
      <div className="card-body">
        <p className="text-muted text-sm" style={{ marginTop: 0 }}>Let a biometric or access-control device post staff punches to the system. Configure the device to <code>POST</code> JSON <code>{'{ token, staff_code, time }'}</code> to:</p>
        <div className="form-group"><input type="text" className="form-control" readOnly value={d.punch_url} onFocus={(e) => e.target.select()} /></div>
        <div className="form-group"><label className="form-label">Device token</label>
          <div className="d-flex gap-2 align-center flex-wrap">
            <input type="text" className="form-control" readOnly value={token || '— not set —'} onFocus={(e) => token && e.target.select()} style={{ flex: 1, minWidth: 220, fontFamily: 'monospace' }} />
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => gen(null)}><i aria-hidden="true" className="fas fa-rotate" /> {token ? 'Regenerate' : 'Generate'}</button>
            {token && <button type="button" className="btn btn-danger" disabled={busy} onClick={() => gen('clear')}><i aria-hidden="true" className="fas fa-trash" /> Clear</button>}
          </div>
          <span className="form-hint d-block">Keep this secret. Regenerating invalidates the old token immediately.</span>
        </div>
      </div></div>
  );
}

// ---- Settings --------------------------------------------------------------
function Settings({ d, notify }) {
  const nav = useNav();
  const [s, setS] = useState(d.settings);
  const [ded, setDed] = useState({ name: '', kind: 'percent', value: '' });
  const [allow, setAllow] = useState(d.leave_allowances || {});
  const set = (k, v) => setS((x) => ({ ...x, [k]: v }));
  const saveAllowances = async (e) => {
    e.preventDefault();
    const fields = {};
    Object.entries(allow).forEach(([t, v]) => { fields['leave_allow_' + t] = v; });
    const r = await submitJson(d.urls.save, fields);
    if (r.ok) notify('success', 'Leave allowances saved.'); else notify('error', r.error || 'Could not save.');
  };
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const saveSettings = async (e) => {
    e.preventDefault();
    const r = await submitJson(d.urls.save, s);
    if (r.ok) notify('success', r.message); else notify('error', r.error || 'Could not save.');
  };
  const addDed = async (e) => {
    e.preventDefault();
    const r = await submitJson(d.urls.add_deduction, ded);
    if (r.ok) { setDed({ name: '', kind: 'percent', value: '' }); notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Could not add.');
  };
  return (
    <>
      <div className="page-header"><h1>HR Settings</h1></div>
      <Tabs d={d} />
      <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-user-clock" /> Attendance &amp; Deductions</h3></div>
        <div className="card-body"><form onSubmit={saveSettings}>
          <fieldset disabled={!d.is_admin} style={{ border: 0, padding: 0, margin: 0 }}>
            <div className="form-row">
              <div className="form-group"><label className="form-label">Resumption time</label><input type="time" className="form-control" value={s.late_time} onChange={(e) => set('late_time', e.target.value)} /><span className="form-hint d-block">Staff clocking in after this time are marked late.</span></div>
              <div className="form-group"><label className="form-label">Lateness rate (₦ per minute)</label><input type="number" className="form-control" min="0" step="1" value={s.late_rate} onChange={(e) => set('late_rate', e.target.value)} /><span className="form-hint d-block">e.g. 10 → ₦10 for every minute after the resumption time.</span></div>
              <div className="form-group"><label className="form-label">Absence deduction (₦ per day)</label><input type="number" className="form-control" min="0" step="100" value={s.absence_deduction} onChange={(e) => set('absence_deduction', e.target.value)} /><span className="form-hint d-block">Flat amount deducted for each day marked absent (0 to disable).</span></div>
            </div>
            <h4 style={{ margin: '.5rem 0' }}><i aria-hidden="true" className="fas fa-location-crosshairs" /> GPS check-in geofence</h4>
            <p className="text-muted text-sm" style={{ marginTop: 0 }}>Set the campus location to let staff check in with their phone's GPS. Leave latitude/longitude blank to disable.</p>
            <div className="form-row">
              <div className="form-group"><label className="form-label">Latitude</label><input type="number" step="any" className="form-control" placeholder="e.g. 6.5244" value={s.geo_lat != null ? s.geo_lat : ''} onChange={(e) => set('geo_lat', e.target.value)} /></div>
              <div className="form-group"><label className="form-label">Longitude</label><input type="number" step="any" className="form-control" placeholder="e.g. 3.3792" value={s.geo_lng != null ? s.geo_lng : ''} onChange={(e) => set('geo_lng', e.target.value)} /></div>
              <div className="form-group"><label className="form-label">Radius (metres)</label><input type="number" min="20" step="10" className="form-control" value={s.geo_radius != null ? s.geo_radius : 200} onChange={(e) => set('geo_radius', e.target.value)} /></div>
            </div>
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Settings</button>
          </fieldset>
        </form></div></div>

      {d.is_admin && <DeviceTokenCard d={d} notify={notify} />}

      <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-money-bill-trend-up" /> Recurring Deductions</h3></div>
        <div className="card-body">
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>Deductions applied to <strong>every</strong> staff member's payslip each month — e.g. pension (a % of basic) or welfare (a fixed amount).</p>
          {d.is_admin && (
            <form onSubmit={addDed} className="d-flex gap-2 align-end flex-wrap mb-3">
              <div className="form-group mb-0" style={{ flex: 2, minWidth: 160 }}><label className="form-label">Name</label><input type="text" className="form-control" placeholder="e.g. Pension, Welfare, Union dues" required value={ded.name} onChange={(e) => setDed((x) => ({ ...x, name: e.target.value }))} /></div>
              <div className="form-group mb-0"><label className="form-label">Type</label><select className="form-control" value={ded.kind} onChange={(e) => setDed((x) => ({ ...x, kind: e.target.value }))}><option value="percent">% of basic</option><option value="fixed">Fixed ₦</option></select></div>
              <div className="form-group mb-0"><label className="form-label">Value</label><input type="number" className="form-control" min="0" step="0.5" placeholder="5 or 500" required value={ded.value} onChange={(e) => setDed((x) => ({ ...x, value: e.target.value }))} /></div>
              <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</button>
            </form>
          )}
          {d.deductions.length ? (
            <table className="data-table table-stack">
              <thead><tr><th>Name</th><th>Deduction</th><th>Status</th><th /></tr></thead>
              <tbody>{d.deductions.map((dd) => (
                <tr key={dd.id} style={dd.is_active ? undefined : { opacity: 0.55 }}>
                  <td data-label="Name">{dd.name}</td>
                  <td data-label="Deduction">{dd.kind === 'percent' ? `${Math.round(dd.value * 100) / 100}% of basic` : `${naira(dd.value)} fixed`}</td>
                  <td data-label="Status">{dd.is_active ? <span className="badge badge-success">Active</span> : <span className="badge badge-warning">Inactive</span>}</td>
                  <td className="actions"><div className="d-flex gap-1 justify-end">
                    <button className="btn btn-secondary btn-sm" title="Toggle active" onClick={() => act(dd.toggle_url, {})}><i aria-hidden="true" className="fas fa-power-off" /></button>
                    <button className="btn btn-danger btn-sm" title="Delete" onClick={() => act(dd.delete_url, {}, 'Remove this deduction?')}><i aria-hidden="true" className="fas fa-trash" /></button>
                  </div></td>
                </tr>))}</tbody>
            </table>
          ) : <p className="text-muted text-sm">No recurring deductions yet.</p>}
        </div></div>

      <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plane-departure" /> Leave Allowances</h3></div>
        <div className="card-body">
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>Annual entitlement (days) per leave type. Balances on each staff profile count approved leave against these.</p>
          <form onSubmit={saveAllowances}>
            <fieldset disabled={!d.is_admin} style={{ border: 0, padding: 0, margin: 0 }}>
              <div className="form-row" style={{ flexWrap: 'wrap' }}>
                {(d.leave_types || []).map((t) => (
                  <div className="form-group" key={t} style={{ minWidth: 110 }}><label className="form-label">{t}</label>
                    <input type="number" className="form-control" min="0" value={allow[t] != null ? allow[t] : ''} onChange={(e) => setAllow((x) => ({ ...x, [t]: e.target.value }))} /></div>))}
              </div>
              <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Allowances</button>
            </fieldset>
          </form>
        </div></div>

      <div className="card mt-3"><div className="card-body">
        <h4 style={{ marginTop: 0 }}><i aria-hidden="true" className="fas fa-circle-question" /> How deductions work</h4>
        <ul className="text-sm text-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.7 }}>
          <li>Mark daily attendance under <strong>Attendance</strong>; entering a clock-in time auto-calculates minutes late and the naira deduction.</li>
          <li>When you <strong>generate payroll</strong> for a month, each staff member's total lateness + absence deductions for that month are pre-filled into their payslip.</li>
          <li>Already generated a run? Use <strong>“Refresh deductions from attendance”</strong> on the payroll page to pull the latest.</li>
        </ul>
      </div></div>
    </>
  );
}

// ---- Notify staff (HR → Communication) -------------------------------------
function NotifyStaffModal({ d, onClose, notify }) {
  const a = d.applied || {};
  const [f, setF] = useState({ channel: 'SMS', title: 'Staff notice', body: '' });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.body.trim()) { notify('error', 'Enter a message.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.notify, { ...f, department_id: a.department_id,
      staff_type: a.staff_type, status: a.status });
    setBusy(false);
    if (r.ok) { notify('success', r.message); onClose(); if (r.redirect) window.location.href = r.redirect; }
    else notify('error', r.error || 'Could not draft the message.');
  };
  const filterNote = [a.department_id && 'department', a.staff_type, a.status].filter(Boolean).join(' · ');
  return (
    <Modal title="Notify staff" icon="fa-bullhorn" onClose={onClose}
           footer={<>
             <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
             <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}><i aria-hidden="true" className="fas fa-paper-plane" /> Draft message</button>
           </>}>
      <form onSubmit={submit}>
        <p className="text-muted text-sm">Drafts a Communication campaign to the staff matching your current filter{filterNote ? ` (${filterNote})` : ' (all staff)'}. Nothing sends until you review it in Communication.</p>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Channel</label>
            <select className="form-control" value={f.channel} onChange={(e) => set('channel', e.target.value)}><option>SMS</option><option>Email</option></select></div>
          <div className="form-group" style={{ flex: 2 }}><label className="form-label">Title</label>
            <input type="text" className="form-control" value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
        </div>
        <div className="form-group"><label className="form-label">Message</label>
          <textarea className="form-control" rows="4" placeholder="You can use {first_name}, {surname}…" value={f.body} onChange={(e) => set('body', e.target.value)} /></div>
      </form>
    </Modal>
  );
}

// ---- Reports ---------------------------------------------------------------
function Reports({ d }) {
  const nav = useNav();
  const sel = d.sel || {};
  const rep = d.report || { columns: [], rows: [], summary: [], title: '' };
  const [flt, setFlt] = useState({ department_id: sel.department_id || '', staff_type: sel.staff_type || '', status: sel.status || '', from: sel.from || '', to: sel.to || '' });
  const params = (extra) => ({ type: sel.type, ...flt, ...extra });
  const go = (extra) => navParams(nav.go, d.urls.self, params(extra));
  const qs = () => Object.entries(params({})).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  const setF = (k, v) => setFlt((x) => ({ ...x, [k]: v }));
  const cell = (col, row) => {
    const v = row[col.key];
    if (col.money) return typeof v === 'number' ? naira(v) : v;
    return (v === '' || v == null) ? '—' : v;
  };
  return (
    <>
      <div className="page-header"><h1>HR Reports</h1>
        <div className="page-header-actions">
          <a href={`${d.urls.export}?format=csv&${qs()}`} data-native className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-csv" /> CSV</a>
          <a href={`${d.urls.export}?format=xlsx&${qs()}`} data-native className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
        </div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form">
          <div className="form-group"><label className="form-label">Report</label>
            <select className="form-control" value={sel.type} onChange={(e) => go({ type: e.target.value })}>
              {d.report_types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Department</label>
            <select className="form-control" value={flt.department_id} onChange={(e) => setF('department_id', e.target.value)}>
              <option value="">All</option>{d.departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Type</label>
            <select className="form-control" value={flt.staff_type} onChange={(e) => setF('staff_type', e.target.value)}>
              <option value="">All</option>{d.staff_types.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Status</label>
            <select className="form-control" value={flt.status} onChange={(e) => setF('status', e.target.value)}>
              <option value="">All</option>{d.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
          <div className="form-group"><label className="form-label">From</label><input type="date" className="form-control" value={flt.from} onChange={(e) => setF('from', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">To</label><input type="date" className="form-control" value={flt.to} onChange={(e) => setF('to', e.target.value)} /></div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}><button type="button" className="btn btn-primary" onClick={() => go({})}><i aria-hidden="true" className="fas fa-filter" /> Apply</button></div>
        </div>
      </div></div>

      {rep.summary && rep.summary.length > 0 && (
        <div className="kpi-row" style={{ gridTemplateColumns: `repeat(${Math.min(rep.summary.length, 4)}, 1fr)` }}>
          {rep.summary.map((s, i) => (
            <div className="kpi" key={i}><div className="ic blue"><i aria-hidden="true" className="fas fa-chart-simple" /></div>
              <div><div className="v" style={{ fontSize: '1.15rem' }}>{s.value}</div><div className="l">{s.label}</div></div></div>))}
        </div>)}

      <div className="card"><div className="card-header"><h3>{rep.title} · {rep.rows.length} row(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {rep.rows.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr>{rep.columns.map((c) => <th key={c.key} className={c.align === 'right' ? 'text-right' : ''}>{c.label}</th>)}</tr></thead>
              <tbody>{rep.rows.map((r, i) => (
                <tr key={i}>{rep.columns.map((c) => <td key={c.key} data-label={c.label} className={c.align === 'right' ? 'text-right' : ''}>{cell(c, r)}</td>)}</tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-chart-line" title="No data"><p>Nothing matches these filters.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Self-service check-in (QR / GPS) --------------------------------------
function CheckIn({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const [today, setToday] = useState(d.today);
  const post = async (fields) => {
    setBusy(true);
    const r = await submitJson(d.urls.self, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Check-in failed.');
  };
  // Auto-submit a scanned QR code once, on mount.
  useEffect(() => {
    if (d.prefill_code && d.staff && !d.today) post({ method: 'qr', code: d.prefill_code });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const gpsCheckin = () => {
    if (!navigator.geolocation) { notify('error', 'This device has no location support.'); return; }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => { setBusy(false); post({ method: 'gps', lat: pos.coords.latitude, lng: pos.coords.longitude }); },
      () => { setBusy(false); notify('error', 'Could not read your location. Allow location access and retry.'); },
      { enableHighAccuracy: true, timeout: 10000 });
  };
  const statusChip = (s) => 'badge ' + (s === 'Present' ? 'badge-success' : s === 'Late' ? 'badge-warning' : 'badge-secondary');
  return (
    <>
      <div className="page-header"><h1>Check In</h1></div>
      <Tabs d={d} />
      {!d.staff ? (
        <div className="card"><div className="card-body">
          <Empty icon="fa-id-badge" title="No staff record linked"><p>Your login isn’t linked to a staff profile. Ask an administrator to link it before you can check in.</p></Empty>
        </div></div>
      ) : (
        <div className="card" style={{ maxWidth: 520 }}><div className="card-body text-center">
          <div className="avatar" style={{ margin: '0 auto .75rem' }}>{(d.staff.name || '').split(' ').map((x) => x[0]).slice(0, 2).join('').toUpperCase()}</div>
          <h2 style={{ margin: '0 0 .25rem' }}>{d.staff.name}</h2>
          <div className="text-muted mb-2">{d.staff.staff_id} · {d.today_label}</div>
          {d.today ? (
            <div className="mb-3"><span className={statusChip(d.today.status)}>{d.today.status}</span>
              {d.today.clock_in && <span className="text-muted"> at {d.today.clock_in}</span>}
              <div className="text-muted text-sm mt-1">You’ve already checked in today.</div></div>
          ) : (
            <p className="text-muted">Resumption time is {d.settings.late_time}. Check in below.</p>
          )}
          <div className="d-flex gap-2 justify-center flex-wrap">
            {d.geo.enabled && <button className="btn btn-primary" disabled={busy} onClick={gpsCheckin}><i aria-hidden="true" className="fas fa-location-crosshairs" /> Check in with location</button>}
            <a href={d.urls.qr} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-qrcode" /> Scan QR instead</a>
          </div>
          {d.prefill_code && !d.today && <button className="btn btn-primary mt-2" disabled={busy} onClick={() => post({ method: 'qr', code: d.prefill_code })}><i aria-hidden="true" className="fas fa-check" /> Confirm QR check-in</button>}
          {!d.geo.enabled && <p className="form-hint mt-2">GPS check-in isn’t configured — an administrator can enable it in HR Settings.</p>}
        </div></div>
      )}
    </>
  );
}

function CheckInQR({ d }) {
  return (
    <>
      <div className="page-header"><h1>Attendance QR</h1>
        <div className="page-header-actions"><a href={d.urls.attendance} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Attendance</a></div>
      </div>
      <Tabs d={d} />
      <div className="card" style={{ maxWidth: 460 }}><div className="card-body text-center">
        <h3 style={{ marginTop: 0 }}>Staff check-in</h3>
        <p className="text-muted">{d.today_label} · today only</p>
        <img src={d.qr} alt="Attendance QR code" style={{ width: '100%', maxWidth: 300, height: 'auto', margin: '0 auto' }} />
        <p className="text-muted text-sm mt-2">Staff scan this with their phone (while signed in) to check in. The code changes each day.</p>
        <a href={d.url} className="text-sm" data-native>{d.url}</a>
      </div></div>
    </>
  );
}

const SCREENS = { dashboard: Dashboard, staff: Staff, staff_form: StaffForm, staff_detail: StaffDetail,
  departments: Departments, leave: Leave, payroll: Payroll, payroll_detail: PayrollDetail,
  attendance: Attendance, checkin: CheckIn, checkin_qr: CheckInQR, reports: Reports, settings: Settings };

export default function HrApp({ data }) {
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
