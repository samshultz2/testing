import React, { useState, useEffect, useRef } from 'react';
import { submitJson, postFile } from '../lib/forms';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, promptDialog, Banner, SectionShell, Empty, Modal } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Menu, Sheet, Blank, Bar, usePhone } from '../subjects/results';
import { DataList, Pill, Bars } from '../sales/kit';

// Small localStorage helpers for recently-viewed staff + saved directory filters.
const lsGet = (key, fallback) => {
  try { return JSON.parse(window.localStorage.getItem(key)) || fallback; } catch (_) { return fallback; }
};
const lsSet = (key, val) => { try { window.localStorage.setItem(key, JSON.stringify(val)); } catch (_) { /* ignore */ } };
// Initials for an avatar fallback (first + last word of a name).
const initials = (name) => {
  const parts = (name || '').split(' ').filter(Boolean);
  if (!parts.length) return '—';
  return ((parts[0][0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
};
const pushRecent = (staff) => {
  if (!staff || !staff.id) return;
  const list = lsGet('hr_recent', []).filter((x) => x.id !== staff.id);
  list.unshift({ id: staff.id, name: staff.name, staff_id: staff.staff_id, url: staff.url });
  lsSet('hr_recent', list.slice(0, 8));
};

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'], ['staff', 'fa-users', 'Staff'],
  ['attendance', 'fa-user-clock', 'Attendance'], ['leave', 'fa-plane-departure', 'Leave'],
  ['payroll', 'fa-money-check-dollar', 'Payroll'], ['departments', 'fa-sitemap', 'Departments'],
  ['recruitment', 'fa-user-plus', 'Recruitment'], ['loans', 'fa-hand-holding-dollar', 'Loans'],
  ['reports', 'fa-chart-line', 'Reports'], ['settings', 'fa-gear', 'Settings'],
];
const TAB_FOR = { staff_form: 'staff', staff_detail: 'staff', payroll_detail: 'payroll',
  checkin: 'attendance', checkin_qr: 'attendance', vacancy: 'recruitment' };

const nairaShort = (n) => {
  n = Number(n) || 0;
  if (n >= 1e6) return '₦' + (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return '₦' + (n / 1e3).toFixed(1) + 'k';
  return naira(n);
};
const leaveBadge = (s) => 'badge ' + (s === 'Approved' ? 'badge-success' : s === 'Rejected' ? 'badge-danger' : 'badge-warning');

// ---- Shared HR shell bits (redesign) ----------------------------------------
function Tabs({ d }) {
  const active = TAB_FOR[d.page] || d.page;
  return (
    <nav className="sl-nav" aria-label="HR sections">
      {TABS.map(([k, ic, label]) => (d.nav && d.nav[k]) && (
        <a key={k} href={d.nav[k]} className={active === k ? 'on' : ''} aria-current={active === k ? 'page' : undefined}>
          <i className={'fas ' + ic} aria-hidden="true" /><span>{label}</span></a>
      ))}
    </nav>
  );
}
const STATUS_TONE = { Active: 'good', 'On Leave': 'mid', Suspended: 'bad', Resigned: '', Retired: '', Terminated: 'bad', Inactive: '' };
const LEAVE_TONE = { Approved: 'good', Rejected: 'bad', Pending: 'mid' };
const RUN_TONE = { Paid: 'good', Finalized: 'info', Draft: 'mid' };
function Face({ name, photo, size }) {
  return photo ? <img className="hr-face" src={photo} alt="" loading="lazy" style={size ? { width: size, height: size } : undefined} />
    : <span className="hr-face" aria-hidden="true" style={size ? { width: size, height: size } : undefined}>{initials(name)}</span>;
}

// ---- Overview -----------------------------------------------------------------
function Dashboard({ d, notify }) {
  const nav = useNav();
  const st = d.stats;
  const ta = d.today_att;
  const decide = async (lv, status) => {
    const r = await submitJson(lv.approve_url, { status });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not update.');
  };
  const alerts = [
    st.pending_leave > 0 && { tone: 'mid', icon: 'fa-plane-departure', n: st.pending_leave, label: st.pending_leave === 1 ? 'leave request to review' : 'leave requests to review', href: d.urls.leave_pending },
    (st.contract_expiring || 0) > 0 && { tone: 'bad', icon: 'fa-file-contract', n: st.contract_expiring, label: st.contract_expiring === 1 ? 'contract expiring soon' : 'contracts expiring soon', href: d.urls.reports + '?type=contracts' },
    ta && ta.unmarked > 0 && { tone: 'info', icon: 'fa-user-clock', n: ta.unmarked, label: 'not marked for attendance today', href: d.urls.attendance },
    ta && ta.absent > 0 && { tone: 'bad', icon: 'fa-user-xmark', n: ta.absent, label: 'absent today', href: d.urls.attendance },
  ].filter(Boolean);
  const maxDept = Math.max(1, ...st.dept_chart.map((x) => x.count));
  return (
    <>
      <Head icon="fa-users-gear" title="Staff & HR" sub={`${st.total} staff · ${nairaShort(st.monthly_payroll)} monthly payroll`}>
        {canWrite(d, 'staff_create') && <a href={d.urls.add_staff} className="rs-btn primary"><i className="fas fa-user-plus" aria-hidden="true" /><span className="rs-hide-sm">Add staff</span></a>}
      </Head>
      <Tabs d={d} />
      <Tiles items={[
        { label: 'Staff', value: st.total, sub: `${st.teaching} teaching · ${st.non_teaching} non-teaching` },
        ta ? { label: 'In today', value: `${ta.present + ta.late}/${ta.total}`, sub: ta.late ? `${ta.late} late` : ta.unmarked === ta.total ? 'not marked yet' : 'on time', tone: ta.absent ? 'mid' : 'good' }
          : { label: 'Active', value: st.active != null ? st.active : st.total },
        { label: 'On leave', value: st.on_leave, tone: st.on_leave ? 'mid' : '' },
        { label: 'Monthly payroll', value: nairaShort(st.monthly_payroll), sub: st.new_hires ? `${st.new_hires} new this month` : '' },
      ]} />
      {alerts.length > 0 ? (
        <div className="sl-alerts">{alerts.map((a, i) => (
          <a key={i} href={a.href} className={'sl-alert ' + a.tone}><i className={'fas ' + a.icon} aria-hidden="true" /><span><b>{a.n}</b> {a.label}</span><i className="fas fa-chevron-right sl-go" aria-hidden="true" /></a>))}</div>
      ) : <p className="rs-ok-line"><i className="fas fa-circle-check" aria-hidden="true" /> No leave to review, no contracts expiring and attendance is up to date.</p>}
      <div className="rs-split">
        <div className="rs-main">
          {d.pending_leaves.length > 0 && (
            <section className="rs-card flush">
              <header className="rs-card-h pad"><h3><i className="fas fa-plane-departure" aria-hidden="true" /> Leave waiting for you</h3><a href={d.urls.leave_pending} className="rs-link">All requests</a></header>
              <div className="hr-list">{d.pending_leaves.map((lv) => (
                <div key={lv.id} className="hr-lv">
                  <Face name={lv.staff_name} />
                  <span className="n"><a href={lv.staff_url}><b>{lv.staff_name}</b></a><small>{lv.leave_type} · {lv.dates} · {lv.days} day{lv.days === 1 ? '' : 's'}</small></span>
                  {canWrite(d, 'leave_approve') && lv.approve_url && <span className="hr-yn">
                    <button type="button" className="rs-btn sm success" onClick={() => decide(lv, 'Approved')}><i className="fas fa-check" aria-hidden="true" /><span className="rs-hide-sm">Approve</span></button>
                    <button type="button" className="rs-btn sm ghost" onClick={() => decide(lv, 'Rejected')} aria-label="Reject"><i className="fas fa-xmark" aria-hidden="true" /></button></span>}
                </div>))}</div>
            </section>
          )}
          <section className="rs-card">
            <header className="rs-card-h"><h3><i className="fas fa-sitemap" aria-hidden="true" /> Staff by department</h3><a href={d.nav.departments} className="rs-link">Departments</a></header>
            {st.dept_chart.length ? <Bars rows={st.dept_chart} label={(x) => x.name} value={(x) => x.count} fmt={(v) => v} max={maxDept} /> : <p className="rs-muted">No staff yet.</p>}
          </section>
          <section className="rs-card flush">
            <header className="rs-card-h pad"><h3><i className="fas fa-user-plus" aria-hidden="true" /> Recently added</h3><a href={d.nav.staff} className="rs-link">All staff</a></header>
            {d.recent.length ? <div className="hr-list">{d.recent.map((s) => (
              <a key={s.id} href={s.url} className="hr-person"><Face name={s.full_name} /><span className="n"><b>{s.full_name}</b><small>{s.designation} · {s.department}</small></span><i className="fas fa-chevron-right" aria-hidden="true" /></a>))}</div>
              : <Blank icon="fa-user-plus" title="No staff yet"><p>Add your first staff member.</p></Blank>}
          </section>
        </div>
        <aside className="rs-rail">
          <section className="rs-card">
            <header className="rs-card-h"><h3><i className="fas fa-bolt" aria-hidden="true" /> Quick actions</h3></header>
            <div className="sl-quick">
              {canWrite(d, 'staff_create') && <a href={d.urls.add_staff}><i className="fas fa-user-plus" aria-hidden="true" />Add staff</a>}
              <a href={d.urls.attendance}><i className="fas fa-user-clock" aria-hidden="true" />Attendance</a>
              <a href={d.urls.leave_pending}><i className="fas fa-plane-departure" aria-hidden="true" />Leave</a>
              <a href={d.nav.payroll}><i className="fas fa-money-check-dollar" aria-hidden="true" />Payroll</a>
              <a href={d.nav.recruitment}><i className="fas fa-bullhorn" aria-hidden="true" />Hiring</a>
              <a href={d.urls.reports}><i className="fas fa-chart-line" aria-hidden="true" />Reports</a>
            </div>
          </section>
          <section className="rs-card">
            <header className="rs-card-h"><h3><i className="fas fa-file-contract" aria-hidden="true" /> Contracts ending</h3></header>
            {(d.contracts || []).length ? <div className="hr-list">{d.contracts.map((c) => (
              <a key={c.id} href={c.url} className="hr-person"><span className="n"><b>{c.name}</b><small>ends {c.ends}</small></span><Pill tone={c.days_left <= 14 ? 'bad' : 'mid'}>{c.days_left}d</Pill></a>))}</div>
              : <p className="rs-muted">None in the next few weeks.</p>}
          </section>
          <section className="rs-card">
            <header className="rs-card-h"><h3><i className="fas fa-cake-candles" aria-hidden="true" /> Birthdays</h3></header>
            {(d.birthdays || []).length ? <div className="hr-list">{d.birthdays.map((b) => (
              <a key={b.id} href={b.url} className="hr-person"><span className="n"><b>{b.name}</b><small>{b.date}</small></span><Pill tone={b.in_days === 0 ? 'good' : ''}>{b.in_days === 0 ? 'Today 🎉' : `in ${b.in_days}d`}</Pill></a>))}</div>
              : <p className="rs-muted">None in the next 30 days.</p>}
          </section>
        </aside>
      </div>
    </>
  );
}

// ---- Staff directory -------------------------------------------------------------
function Staff({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const a = d.applied;
  const [q, setQ] = useState(a.q || '');
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef();
  const [recent] = useState(() => lsGet('hr_recent', []));
  const [saved, setSaved] = useState(() => lsGet('hr_saved_filters', []));
  const go = (extra) => navParams(nav.go, d.self_url, { department_id: a.department_id, staff_type: a.staff_type, status: a.status, q, ...extra });
  const onImport = async (e) => {
    const file = e.target.files && e.target.files[0]; e.target.value = '';
    if (!file) return;
    setBusy(true); const r = await postFile(d.urls.import, file); setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Import failed.');
  };
  const saveFilter = async () => {
    const name = await promptDialog({ title: 'Save this view', label: 'Name it' });
    if (!name) return;
    const next = [...saved.filter((x) => x.name !== name), { name, params: { department_id: a.department_id, staff_type: a.staff_type, status: a.status } }];
    setSaved(next); lsSet('hr_saved_filters', next); notify('success', `Saved “${name}”.`);
  };
  const removeSaved = (name) => { const next = saved.filter((x) => x.name !== name); setSaved(next); lsSet('hr_saved_filters', next); };
  const t = q.trim().toLowerCase();
  const rows = d.staff.filter((s) => !t || `${s.full_name} ${s.staff_id} ${s.designation || ''} ${s.phone || ''}`.toLowerCase().includes(t));
  const filtered = a.department_id || a.staff_type || a.status;
  return (
    <>
      <input type="file" ref={fileRef} accept=".csv,text/csv" style={{ display: 'none' }} onChange={onImport} />
      <Head icon="fa-users" title="Staff" sub={`${d.staff.length} staff${filtered ? ' in this view' : ''}`}>
        {canWrite(d, 'staff_create') && <a href={d.urls.add} className="rs-btn primary"><i className="fas fa-user-plus" aria-hidden="true" /><span className="rs-hide-sm">Add staff</span></a>}
        <Menu label="More" items={[
          canWrite(d, 'staff_notify') && { icon: 'fa-bullhorn', label: 'Message staff', onClick: () => setNotifyOpen(true) },
          canWrite(d, 'staff_import') && { icon: 'fa-file-import', label: busy ? 'Importing…' : 'Import from CSV', onClick: () => fileRef.current && fileRef.current.click() },
          canWrite(d, 'staff_export') && { icon: 'fa-file-csv', label: 'Export to CSV', href: d.urls.export, native: true, download: true },
          filtered && { icon: 'fa-bookmark', label: 'Save this view', onClick: saveFilter },
        ]} />
      </Head>
      <Tabs d={d} />
      {notifyOpen && <NotifyStaffModal d={d} onClose={() => setNotifyOpen(false)} notify={notify} />}
      <div className="rs-toolbar">
        <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Name, staff ID, role or phone" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') go(); }} aria-label="Search staff" /></label>
        <select className="sl-select" value={a.department_id} onChange={(e) => go({ department_id: e.target.value })} aria-label="Department">
          <option value="">All departments</option>{d.departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
      </div>
      <div className="hr-filters">
        <Seg label="Type" value={a.staff_type || ''} onChange={(v) => go({ staff_type: v })} options={[{ value: '', label: 'Everyone' }, ...d.staff_types.map((x) => ({ value: x, label: x }))]} />
        <Seg label="Status" value={a.status || ''} onChange={(v) => go({ status: v })} options={[{ value: '', label: 'Any status' }, ...d.statuses.slice(0, phone ? 2 : 4).map((x) => ({ value: x, label: x }))]} />
      </div>
      {(saved.length > 0 || recent.length > 0) && (
        <div className="as-quick">
          {saved.map((sf) => <span key={sf.name} className="rs-chip"><button type="button" className="hr-chipbtn" onClick={() => navParams(nav.go, d.self_url, { ...sf.params, q: '' })}><i className="fas fa-bookmark" aria-hidden="true" /> {sf.name}</button><button type="button" className="hr-chipbtn" onClick={() => removeSaved(sf.name)} aria-label={`Remove ${sf.name}`}><i className="fas fa-xmark" aria-hidden="true" /></button></span>)}
          {recent.length > 0 && <span>Recent:</span>}
          {recent.slice(0, phone ? 3 : 6).map((r) => <a key={r.id} href={r.url} className="rs-chip">{r.name}</a>)}
        </div>
      )}
      {rows.length ? (
        <section className="rs-card flush"><div className="hr-staff">
          {rows.map((s) => (
            <div key={s.id} className="hr-srow">
              <a href={s.url} className="hr-sname"><Face name={s.full_name} photo={s.photo_url} /><span className="n"><b>{s.full_name}</b><small>{s.designation || 'No role set'} · {s.staff_id}</small></span></a>
              <span className="hr-sdept"><small>{s.department || 'No department'}</small></span>
              <span className="hr-stags"><Pill tone={s.staff_type === 'Teaching' ? 'info' : ''}>{s.staff_type}</Pill><Pill tone={STATUS_TONE[s.status]}>{s.status}</Pill></span>
              <span className="hr-sact">{s.phone && <a href={'tel:' + s.phone} className="rs-icon-btn hr-call" aria-label={`Call ${s.full_name}`}><i className="fas fa-phone" aria-hidden="true" /></a>}
                <a href={s.url} className="rs-icon-btn hr-call" aria-label={`Open ${s.full_name}`}><i className="fas fa-chevron-right" aria-hidden="true" /></a></span>
            </div>))}
        </div></section>
      ) : <Blank icon="fa-users" title="No staff found"><p>{d.staff.length ? 'Nothing matches your search.' : 'Add your first staff member or change the filters.'}</p>
          {canWrite(d, 'staff_create') && !d.staff.length && <a href={d.urls.add} className="rs-btn primary">Add staff</a>}</Blank>}
    </>
  );
}

// ---- Staff profile -------------------------------------------------------------
function StaffDetail({ d, notify }) {
  const nav = useNav();
  const s = d.s;
  const [tab, setTab] = useState(() => { try { return sessionStorage.getItem('hr:ptab') || 'overview'; } catch (e) { return 'overview'; } });
  const pick = (t) => { setTab(t); try { sessionStorage.setItem('hr:ptab', t); } catch (e) { /* ignore */ } };
  useEffect(() => { pushRecent({ id: s.id, name: s.full_name, staff_id: s.staff_id, url: d.urls.self }); }, [s.id, s.full_name, s.staff_id, d.urls.self]);
  const act = async (url, fields, confirmMsg, follow) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); follow ? nav.go(r.redirect) : nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const Row = ({ k, v }) => <div className="info-row"><span className="k">{k}</span><span className="v">{v || '—'}</span></div>;
  const lv = d.leave_summary || {};
  const att = d.attendance_summary || {};
  return (
    <>
      <section className="rs-card hr-hero">
        <Face name={s.full_name} photo={s.photo_url} size={72} />
        <div className="hr-hero-t">
          <h1>{s.full_name}</h1>
          <p>{s.designation || 'No role set'}{s.department && ` · ${s.department}`}</p>
          <div className="hr-hero-p">
            <Pill tone={STATUS_TONE[s.status]}>{s.status}</Pill><Pill tone={s.staff_type === 'Teaching' ? 'info' : ''}>{s.staff_type}</Pill>
            <Pill>{s.employment_type}</Pill><Pill>{s.staff_id}</Pill>
            {s.years_of_service > 0 && <Pill>{s.years_of_service} yr{s.years_of_service !== 1 ? 's' : ''} service</Pill>}
          </div>
        </div>
        <div className="hr-hero-a">
          {s.phone && <a href={'tel:' + s.phone} className="rs-btn ghost" aria-label="Call"><i className="fas fa-phone" aria-hidden="true" /><span className="rs-hide-sm">Call</span></a>}
          {s.phone && <a href={'https://wa.me/' + s.wa_intl} target="_blank" rel="noopener" className="rs-btn ghost" aria-label="WhatsApp"><i className="fab fa-whatsapp" aria-hidden="true" /><span className="rs-hide-sm">WhatsApp</span></a>}
          {canWrite(d, 'staff_edit') && <a href={d.urls.edit} className="rs-btn primary"><i className="fas fa-pen" aria-hidden="true" /><span className="rs-hide-sm">Edit</span></a>}
          <Menu label="More" items={[
            { icon: 'fa-arrow-left', label: 'Back to staff', href: d.nav.staff },
            canWrite(d, 'staff_delete') && { icon: 'fa-trash', label: 'Delete or deactivate', danger: true, onClick: () => act(d.urls.delete, {}, `Delete ${s.full_name}? If they have payroll, attendance, leave history or a login, they'll be deactivated (hidden everywhere) instead.`, true) },
          ]} />
        </div>
      </section>
      {s.contract_expiring && (
        <div className={'sc-alert' + (s.contract_days_left < 0 ? ' bad' : '')}><i className="fas fa-file-contract" aria-hidden="true" />
          <span>{s.contract_days_left < 0 ? `Contract expired on ${s.contract_end} (${-s.contract_days_left} day(s) ago).` : `Contract ends on ${s.contract_end} — in ${s.contract_days_left} day(s).`}</span></div>
      )}
      <Tiles items={[
        { label: 'Salary', value: s.salary ? nairaShort(s.salary) : '—', sub: 'per month' },
        { label: 'This month', value: `${att.present || 0} in`, sub: `${att.late || 0} late · ${att.absent || 0} absent`, tone: (att.absent || 0) > 2 ? 'bad' : (att.late || 0) > 3 ? 'mid' : '' },
        { label: 'Leave this year', value: `${lv.total_days || 0}d`, sub: lv.pending ? `${lv.pending} pending` : 'taken', tone: lv.pending ? 'mid' : '' },
        { label: 'With the school', value: s.years_of_service ? `${s.years_of_service} yrs` : 'New', sub: s.date_employed ? `since ${s.date_employed}` : '' },
      ]} />
      <Seg label="Profile sections" value={tab} onChange={pick} options={[
        { value: 'overview', label: 'Overview', icon: 'fa-id-card' }, { value: 'details', label: 'Details', icon: 'fa-address-book' },
        { value: 'pay', label: 'Pay', icon: 'fa-money-check-dollar' }, { value: 'time', label: 'Leave & time', icon: 'fa-calendar-check' },
        { value: 'growth', label: 'Files & growth', icon: 'fa-folder-open' }]} />
      {tab === 'overview' && (<><ProfileHub d={d} /><LifecycleTimeline d={d} act={act} /></>)}
      {tab === 'details' && (
        <div className="hr-2col">
          <div className="card"><div className="card-header"><h3><i className="fas fa-briefcase" aria-hidden="true" /> Personal & employment</h3></div><div className="card-body"><div className="info-grid">
            <Row k="Phone" v={s.phone} /><Row k="Email" v={s.email} /><Row k="Gender" v={s.gender} />
            <Row k="Date of birth" v={s.date_of_birth + (s.age != null ? ` (${s.age})` : '')} />
            <Row k="Date employed" v={s.date_employed} /><Row k="Confirmed" v={s.confirmation_date} />
            <Row k="Experience" v={s.total_experience_years ? `${s.total_experience_years} yr(s)` : ''} />
            <Row k="Qualification" v={s.qualification} /><Row k="Certifications" v={s.certifications} /><Row k="Address" v={s.address} />
            {(s.contract_start || s.contract_end) && <Row k="Contract" v={[s.contract_start, s.contract_end].filter(Boolean).join(' – ')} />}
          </div></div></div>
          <div className="card"><div className="card-header"><h3><i className="fas fa-shield-heart" aria-hidden="true" /> Kin, bank, statutory & medical</h3></div><div className="card-body"><div className="info-grid">
            <Row k="Next of kin" v={s.nok_name} /><Row k="NOK phone" v={s.nok_phone} /><Row k="Relationship" v={s.nok_relationship} />
            <Row k="Emergency" v={s.emergency_name} /><Row k="Emergency phone" v={s.emergency_phone} />
            <Row k="Bank" v={s.bank_name} /><Row k="Account no." v={s.account_number} /><Row k="Account name" v={s.account_name} />
            <Row k="Tax ID" v={s.tax_id} /><Row k="Pension PIN" v={s.pension_pin} /><Row k="PFA" v={s.pension_provider} />
            <Row k="Blood group" v={s.blood_group} /><Row k="Medical" v={s.medical_notes} />
          </div>{s.notes && <p className="text-muted text-sm mt-2">{s.notes}</p>}</div></div>
        </div>
      )}
      {tab === 'pay' && (<>
        <SalarySection d={d} act={act} />
        {d.payslips.length > 0 && (
          <section className="rs-card flush">
            <header className="rs-card-h pad"><h3><i className="fas fa-money-check-dollar" aria-hidden="true" /> Payslips</h3></header>
            <DataList rows={d.payslips} rowKey={(p, i) => i} cols={[
              { key: 'period', label: 'Period', main: true, render: (p) => p.period },
              { key: 'basic', label: 'Basic', align: 'right', render: (p) => naira(p.basic) },
              { key: 'allow', label: 'Allowances', align: 'right', render: (p) => naira(p.allowances) },
              { key: 'ded', label: 'Deductions', align: 'right', render: (p) => <span className="bad">{naira(p.total_deductions)}</span> },
              { key: 'net', label: 'Net pay', align: 'right', value: true, render: (p) => <b>{naira(p.net)}</b> },
              { key: 'print', label: '', hideSm: true, render: (p) => <a href={p.print_url} className="rs-icon-btn hr-call" data-native aria-label="Print payslip"><i className="fas fa-print" aria-hidden="true" /></a> },
            ]} />
          </section>
        )}
        <DeductionsSection d={d} notify={notify} />
      </>)}
      {tab === 'time' && (<><LeaveSection d={d} act={act} /><LatenessSection d={d} /></>)}
      {tab === 'growth' && (<><DocumentsSection d={d} act={act} notify={notify} /><TrainingSection d={d} act={act} notify={notify} /><ReviewsSection d={d} act={act} notify={notify} /></>)}
    </>
  );
}

// ---- Leave ------------------------------------------------------------------------
function Leave({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ staff_id: '', leave_type: d.leave_types[0], start_date: '', end_date: '' });
  const [view, setView] = useState('list');
  const [adding, setAdding] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const add = async (e) => {
    e.preventDefault();
    if (!f.staff_id) { notify('error', 'Choose a staff member.'); return; }
    const r = await submitJson(d.add_url, f);
    if (r.ok) { setF({ staff_id: '', leave_type: d.leave_types[0], start_date: '', end_date: '' }); setAdding(false); notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Could not add.');
  };
  const today = d.today || new Date().toISOString().slice(0, 10);
  const pending = d.leaves.filter((l) => l.status === 'Pending');
  const offToday = d.leaves.filter((l) => l.status === 'Approved' && l.start && l.end && l.start <= today && l.end >= today);
  const days = (a, b) => (a && b ? Math.round((new Date(b) - new Date(a)) / 864e5) + 1 : 0);
  return (
    <>
      <Head icon="fa-plane-departure" title="Leave" sub="Requests, approvals and who's away">
        {canWrite(d, 'leave_create') && <button type="button" className="rs-btn primary" onClick={() => setAdding(true)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Record leave</span></button>}
      </Head>
      <Tabs d={d} />
      <Tiles items={[
        { label: 'Waiting for approval', value: pending.length, tone: pending.length ? 'mid' : 'good' },
        { label: 'Away today', value: offToday.length, sub: offToday.slice(0, 2).map((l) => l.staff_name.split(' ')[0]).join(', ') },
        { label: 'Days in this list', value: d.leaves.reduce((t, l) => t + (Number(l.days) || 0), 0) },
      ]} />
      <div className="hr-filters">
        <Seg label="Status" value={d.status || ''} onChange={(v) => navParams(nav.go, d.self_url, { status: v })} options={[{ value: '', label: 'All' }, { value: 'Pending', label: 'Pending' }, { value: 'Approved', label: 'Approved' }, { value: 'Rejected', label: 'Rejected' }]} />
        <Seg label="View" value={view} onChange={setView} options={[{ value: 'list', label: 'List', icon: 'fa-list' }, { value: 'calendar', label: 'Calendar', icon: 'fa-calendar-days' }]} />
      </div>
      {view === 'calendar' ? <LeaveCalendar leaves={d.leaves} today={d.today} /> : d.leaves.length ? (
        <section className="rs-card flush"><div className="hr-list">
          {d.leaves.map((lv) => (
            <div key={lv.id} className="hr-lv">
              <Face name={lv.staff_name} />
              <span className="n"><a href={lv.staff_url}><b>{lv.staff_name}</b></a><small>{lv.leave_type} · {lv.dates} · {lv.days} day{lv.days === 1 ? '' : 's'}</small></span>
              <Pill tone={LEAVE_TONE[lv.status]}>{lv.status}</Pill>
              <span className="hr-yn">
                {canWrite(d, 'leave_approve') && lv.status !== 'Approved' && <button type="button" className="rs-btn sm success" onClick={() => act(lv.approve_url, { status: 'Approved' })}><i className="fas fa-check" aria-hidden="true" /><span className="rs-hide-sm">Approve</span></button>}
                {canWrite(d, 'leave_approve') && lv.status !== 'Rejected' && <button type="button" className="rs-btn sm ghost" onClick={() => act(lv.approve_url, { status: 'Rejected' })} aria-label="Reject"><i className="fas fa-xmark" aria-hidden="true" /></button>}
                {canWrite(d, 'leave_delete') && <Menu label="" items={[{ icon: 'fa-trash', label: 'Delete record', danger: true, onClick: () => act(lv.delete_url, {}, 'Delete this leave record?') }]} />}
              </span>
            </div>))}
        </div></section>
      ) : <Blank icon="fa-plane-departure" title="No leave here"><p>{d.status ? `No ${d.status.toLowerCase()} leave.` : 'Record a leave request to get started.'}</p></Blank>}
      {adding && (
        <Sheet title="Record leave" onClose={() => setAdding(false)}>
          <form onSubmit={add} className="sl-form">
            <label className="sl-f"><span>Staff member</span><select value={f.staff_id} onChange={(e) => set('staff_id', e.target.value)} required><option value="">Choose…</option>{d.staff.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}</select></label>
            <div className="sl-f"><span>Type</span><Seg label="Leave type" value={f.leave_type} onChange={(v) => set('leave_type', v)} options={d.leave_types.slice(0, 4).map((t) => ({ value: t, label: t }))} />
              {d.leave_types.length > 4 && <select value={f.leave_type} onChange={(e) => set('leave_type', e.target.value)} aria-label="Other types">{d.leave_types.map((t) => <option key={t}>{t}</option>)}</select>}</div>
            <div className="sl-two">
              <label className="sl-f"><span>From</span><input type="date" required value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></label>
              <label className="sl-f"><span>To</span><input type="date" required value={f.end_date} min={f.start_date} onChange={(e) => set('end_date', e.target.value)} /></label>
            </div>
            {f.start_date && f.end_date && <p className="rs-muted">{days(f.start_date, f.end_date)} calendar day(s).</p>}
            <button className="rs-btn primary wide"><i className="fas fa-check" aria-hidden="true" /> Record leave</button>
          </form>
        </Sheet>
      )}
    </>
  );
}

// ---- Payroll ----------------------------------------------------------------------
function Payroll({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ month: d.cur_month, year: d.cur_year });
  const [gen, setGen] = useState(false);
  const create = async (e) => {
    e.preventDefault();
    const r = await submitJson(d.create_url, f);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not generate.');
  };
  const last = d.rows[0];
  const drafts = d.rows.filter((r) => r.status === 'Draft').length;
  const unpaid = d.rows.filter((r) => r.status === 'Finalized').length;
  return (
    <>
      <Head icon="fa-money-check-dollar" title="Payroll" sub="Monthly payslips for every active staff member">
        {canWrite(d, 'payroll_create') && <button type="button" className="rs-btn primary" onClick={() => setGen(true)}><i className="fas fa-gears" aria-hidden="true" /><span className="rs-hide-sm">Run payroll</span></button>}
      </Head>
      <Tabs d={d} />
      <Tiles items={[
        last && { label: 'Latest run', value: nairaShort(last.total), sub: `${last.period_label} · ${last.count} staff` },
        { label: 'Drafts to finalise', value: drafts, tone: drafts ? 'mid' : '' },
        { label: 'Finalised, not paid', value: unpaid, tone: unpaid ? 'bad' : '' },
        { label: 'Runs', value: d.rows.length },
      ]} />
      <section className="rs-card flush">
        <DataList rows={d.rows} onRow={(r) => nav.go(r.url)} empty={<Blank icon="fa-money-check-dollar" title="No payroll yet"><p>Run your first monthly payroll — it creates a payslip for each active staff member.</p></Blank>} cols={[
          { key: 'period', label: 'Month', main: true, render: (r) => r.period_label },
          { key: 'count', label: 'Staff', sub: true, render: (r) => `${r.count} staff` },
          { key: 'status', label: 'Status', render: (r) => <Pill tone={RUN_TONE[r.status]}>{r.status}</Pill> },
          { key: 'total', label: 'Net pay', align: 'right', value: true, render: (r) => <b>{naira(r.total)}</b> },
        ]} />
      </section>
      {gen && (
        <Sheet title="Run payroll" onClose={() => setGen(false)}>
          <form onSubmit={create} className="sl-form">
            <p className="rs-muted">Creates a draft payslip for every active staff member from their monthly salary, recurring deductions and this month's attendance. You can adjust before finalising.</p>
            <div className="sl-two">
              <label className="sl-f"><span>Month</span><select value={f.month} onChange={(e) => setF((s) => ({ ...s, month: e.target.value }))}>{d.months.map((m) => <option key={m.value} value={m.value}>{m.name}</option>)}</select></label>
              <label className="sl-f"><span>Year</span><input type="number" min="2000" max="2100" value={f.year} onChange={(e) => setF((s) => ({ ...s, year: e.target.value }))} /></label>
            </div>
            <button className="rs-btn primary wide"><i className="fas fa-gears" aria-hidden="true" /> Create draft payroll</button>
          </form>
        </Sheet>
      )}
    </>
  );
}

function PayrollDetail({ d, notify }) {
  const nav = useNav();
  const run = d.run;
  const [editing, setEditing] = useState(null);
  const [q, setQ] = useState('');
  const act = async (url, fields, confirmMsg, follow) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); follow ? nav.go(r.redirect) : nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const draft = run.status === 'Draft';
  const sum = (k) => d.slips.reduce((t, p) => t + (Number(p[k]) || 0), 0);
  const gross = sum('basic') + sum('allowances');
  const ded = sum('total_deductions');
  const att = sum('attendance_deduction');
  const t = q.trim().toLowerCase();
  const rows = d.slips.filter((p) => !t || p.staff_name.toLowerCase().includes(t));
  const STEPS = ['Draft', 'Finalized', 'Paid'];
  const idx = STEPS.indexOf(run.status);
  return (
    <>
      <Head icon="fa-money-check-dollar" title={`Payroll · ${run.period_label}`} sub={`${d.slips.length} payslips · ${naira(d.total)} net`}>
        {draft && canWrite(d, 'payroll_finalize') && <button type="button" className="rs-btn primary" onClick={() => act(d.urls.finalize, { post_expense: '1' }, 'Finalise this payroll? Payslips lock and the total is posted to Finance as an expense.')}><i className="fas fa-lock" aria-hidden="true" /><span className="rs-hide-sm">Finalise</span></button>}
        {run.status === 'Finalized' && canWrite(d, 'payroll_finalize') && <button type="button" className="rs-btn success" onClick={() => act(d.urls.mark_paid, {})}><i className="fas fa-check-double" aria-hidden="true" /><span className="rs-hide-sm">Mark paid</span></button>}
        <Menu label="More" items={[
          { icon: 'fa-arrow-left', label: 'All payroll runs', href: d.nav.payroll },
          draft && canWrite(d, 'payroll_edit') && { icon: 'fa-rotate', label: "Refresh deductions from attendance", onClick: () => act(d.urls.sync_deductions, {}, "Refresh every payslip's deductions from this month's attendance?") },
          canWrite(d, 'payroll_delete') && { icon: 'fa-trash', label: 'Delete this run', danger: true, onClick: () => act(d.urls.delete, {}, 'Delete this payroll run and all its payslips?', true) },
        ]} />
      </Head>
      <Tabs d={d} />
      <div className="sl-steps">{STEPS.map((x, i) => <span key={x} className={i < idx ? 'done' : i === idx ? 'on' : ''}><b>{i < idx ? <i className="fas fa-check" aria-hidden="true" /> : i + 1}</b>{x === 'Finalized' ? 'Finalised' : x}</span>)}
        {run.posted_expense_id && <Pill tone="good" icon="fa-building-columns">Posted to Finance</Pill>}</div>
      <Tiles items={[
        { label: 'Gross pay', value: nairaShort(gross), sub: `basic ${nairaShort(sum('basic'))} + allowances` },
        { label: 'Deductions', value: nairaShort(ded), sub: att ? `${nairaShort(att)} from attendance` : 'recurring + manual', tone: ded ? 'bad' : '' },
        { label: 'Net pay', value: nairaShort(d.total), tone: 'good', sub: `${d.slips.length} staff` },
      ]} />
      {d.slips.length > 6 && <div className="rs-toolbar"><label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" /><input type="search" placeholder="Find a staff member" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find" /></label></div>}
      {rows.length ? (
        <section className="rs-card flush"><div className="hr-list">
          {rows.map((ps) => (
            <div key={ps.id} className={'hr-slip' + (editing === ps.id ? ' open' : '')}>
              <div className="hr-slip-top">
                <span className="n"><b>{ps.staff_name}</b><small>basic {naira(ps.basic)}{ps.allowances ? ` + ${naira(ps.allowances)} allowances` : ''}</small></span>
                <span className="hr-slip-d">
                  {ps.attendance_deduction > 0 && <Pill tone="bad" icon="fa-user-clock">{nairaShort(ps.attendance_deduction)}</Pill>}
                  {ps.recurring_deductions > 0 && <Pill tone="mid" icon="fa-hand-holding-dollar">{nairaShort(ps.recurring_deductions)}</Pill>}
                  {ps.deductions > 0 && <Pill icon="fa-pen">{nairaShort(ps.deductions)}</Pill>}
                </span>
                <b className="hr-net">{naira(ps.net)}</b>
                <span className="hr-yn">
                  <a href={ps.print_url} className="rs-icon-btn hr-call" data-native aria-label={`Payslip for ${ps.staff_name}`}><i className="fas fa-print" aria-hidden="true" /></a>
                  {draft && canWrite(d, 'payroll_edit') && <button type="button" className="rs-icon-btn hr-call" onClick={() => setEditing(editing === ps.id ? null : ps.id)} aria-label={`Adjust ${ps.staff_name}`}><i className="fas fa-pen" aria-hidden="true" /></button>}
                </span>
              </div>
              {editing === ps.id && (
                <div className="hr-slip-edit">
                  <PayslipEdit ps={ps} notify={notify} onDone={() => { setEditing(null); nav.refresh(); }} />
                  <small className="rs-muted">Automatic: attendance {naira(ps.attendance_deduction)}{ps.items.map((i, k) => <span key={k}> · {i.name} {naira(i.amount)}</span>)} · total deductions {naira(ps.total_deductions)}</small>
                </div>
              )}
            </div>
          ))}
        </div></section>
      ) : <Blank icon="fa-money-check-dollar" title="No payslips"><p>{d.slips.length ? 'Nobody matches.' : 'This run has no payslips.'}</p></Blank>}
    </>
  );
}

// ---- Attendance -----------------------------------------------------------------
function Attendance({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [rows, setRows] = useState(() => d.rows.map((r) => ({ ...r })));
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');
  useEffect(() => { setRows(d.rows.map((r) => ({ ...r }))); }, [d.rows]);
  const setRow = (id, k, v) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, [k]: v } : r)));
  const can = canWrite(d, 'attendance_mark');
  const s = d.settings;
  const goDay = (iso) => navParams(nav.go, d.self_url, { date: iso, department_id: d.dept_id });
  const shift = (n) => { const x = new Date(d.day + 'T00:00:00'); x.setDate(x.getDate() + n); goDay(`${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`); };
  const changed = rows.filter((r, i) => { const o = d.rows[i]; return o && (o.status !== r.status || o.clock_in !== r.clock_in || !o.marked); }).length;
  const unmarked = d.rows.filter((r) => !r.marked).length;
  const save = async (e) => {
    if (e) e.preventDefault();
    setBusy(true);
    const fields = { date: d.day, staff_id: rows.map((r) => r.id) };
    rows.forEach((r) => { fields['status_' + r.id] = r.status; fields['clock_' + r.id] = r.clock_in; });
    const r = await submitJson(d.save_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.go(r.redirect); } else notify('error', r.error || 'Could not save.');
  };
  const t = q.trim().toLowerCase();
  const shown = rows.filter((r) => !t || r.full_name.toLowerCase().includes(t));
  const ST = { Present: 'good', Late: 'mid', Absent: 'bad', Excused: 'info' };
  const counts = rows.reduce((m, r) => ({ ...m, [r.status]: (m[r.status] || 0) + 1 }), {});
  return (
    <>
      <Head icon="fa-user-clock" title="Staff attendance" sub={d.day_label}>
        <Menu label="Check-in" items={[
          { icon: 'fa-location-crosshairs', label: 'Self check-in page', href: d.checkin_url },
          canWrite(d, 'attendance_qr') && { icon: 'fa-qrcode', label: "Show today's check-in QR", href: d.qr_url },
          { icon: 'fa-gear', label: 'Resumption time & deductions', href: d.settings_url },
        ]} />
      </Head>
      <Tabs d={d} />
      <section className="rs-pick"><div className="rs-pick-row hr-dayrow">
        <span className="hr-day"><button type="button" className="rs-icon-btn" onClick={() => shift(-1)} aria-label="Previous day"><i className="fas fa-chevron-left" aria-hidden="true" /></button>
          <input type="date" value={d.day} onChange={(e) => e.target.value && goDay(e.target.value)} aria-label="Date" />
          <button type="button" className="rs-icon-btn" onClick={() => shift(1)} aria-label="Next day"><i className="fas fa-chevron-right" aria-hidden="true" /></button></span>
        <label className="rs-sel grow"><span>Department</span>
          <select value={d.dept_id} onChange={(e) => navParams(nav.go, d.self_url, { date: d.day, department_id: e.target.value })}><option value="">All departments</option>{d.departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      </div></section>
      <Tiles items={[
        { label: 'Present', value: counts.Present || 0, tone: 'good' },
        { label: 'Late', value: counts.Late || 0, tone: counts.Late ? 'mid' : '', sub: `after ${s.late_time}` },
        { label: 'Absent', value: counts.Absent || 0, tone: counts.Absent ? 'bad' : '' },
        { label: 'Deductions', value: nairaShort(d.summary.deduction), sub: `₦${s.late_rate}/min late` },
      ]} />
      {unmarked > 0 && can && <div className="sc-alert"><i className="fas fa-circle-info" aria-hidden="true" /><span><b>{unmarked}</b> staff not marked yet — they start as Present. Change anyone who isn't, then save.</span></div>}
      {rows.length > 8 && <div className="rs-toolbar"><label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" /><input type="search" placeholder="Find a staff member" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find" /></label></div>}
      {rows.length ? (
        <form onSubmit={save} className="rs-card flush">
          <div className="hr-list">
            {shown.map((r) => (
              <div key={r.id} className={'hr-att ' + (ST[r.status] || '')}>
                <span className="n"><b>{r.full_name}{!r.marked && <i className="rs-dirty" title="Not marked yet" />}</b><small>{r.designation || ''}{r.minutes_late ? ` · ${r.minutes_late} min late` : ''}{r.deduction ? ` · −${naira(r.deduction)}` : ''}</small></span>
                <span className="hr-st" role="radiogroup" aria-label={`${r.full_name} status`}>
                  {d.att_statuses.map((x) => <button type="button" key={x} role="radio" aria-checked={r.status === x} disabled={!can} className={r.status === x ? 'on ' + (ST[x] || '') : ''} onClick={() => setRow(r.id, 'status', x)}>{phone ? x[0] : x}</button>)}
                </span>
                <input type="time" className="hr-time" disabled={!can || r.status === 'Absent'} value={r.clock_in} onChange={(e) => setRow(r.id, 'clock_in', e.target.value)} aria-label={`${r.full_name} clock-in`} />
              </div>
            ))}
          </div>
          {can && (
            <Bar>
              <span className="rs-bar-t"><b>{changed ? `${changed} to save` : 'All saved'}</b><small>Late after {s.late_time} · deductions go to payroll</small></span>
              <button type="submit" className="rs-btn primary" disabled={busy}><i className="fas fa-floppy-disk" aria-hidden="true" /> Save attendance</button>
            </Bar>
          )}
        </form>
      ) : <Blank icon="fa-user-clock" title="No active staff"><p>Add staff to mark attendance.</p></Blank>}
    </>
  );
}


// ---- Dashboard -------------------------------------------------------------
// ---- Staff list ------------------------------------------------------------
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
  // Render a field via a plain function call — NOT as <T/>. Defining a component
  // inside render gives it a new identity every keystroke, so React would remount
  // each <input> and the mobile keyboard would drop after every character.
  const T = ({ k, label, type = 'text', req, ...rest }) => (
    <div className="form-group" key={k}><label className="form-label">{label}{req && <span className="required"> *</span>}</label>
      <input type={type} className="form-control" required={req} value={f[k]} onChange={(e) => set(k, e.target.value)} {...rest} /></div>
  );
  return (
    <>
      <Head icon={d.mode === 'edit' ? 'fa-user-pen' : 'fa-user-plus'} title={d.mode === 'edit' ? `Edit ${[f.first_name, f.surname].filter(Boolean).join(' ') || 'staff'}` : 'Add staff'} sub="Only first name and surname are required — fill the rest any time" />
      <Tabs d={d} />
      <form onSubmit={submit}>
        <div className="card mb-3"><div className="card-header"><h3>Personal</h3></div><div className="card-body">
          <div className="form-row">{T({ k: 'first_name', label: 'First name', req: true })}{T({ k: 'surname', label: 'Surname', req: true })}</div>
          <div className="form-row">{T({ k: 'middle_name', label: 'Middle name' })}
            <div className="form-group"><label className="form-label">Gender</label>
              <select className="form-control" value={f.gender} onChange={(e) => set('gender', e.target.value)}><option value="">—</option><option>Male</option><option>Female</option></select></div>
            {T({ k: 'date_of_birth', label: 'Date of birth', type: 'date' })}</div>
          <div className="form-row">{T({ k: 'phone', label: 'Phone' })}{T({ k: 'email', label: 'Email', type: 'email' })}</div>
          {T({ k: 'address', label: 'Address' })}
        </div></div>

        <div className="card mb-3"><div className="card-header"><h3>Employment</h3></div><div className="card-body">
          <div className="form-row">
            <div className="form-group"><label className="form-label">Department</label>
              <select className="form-control" value={f.department_id} onChange={(e) => set('department_id', e.target.value)}><option value="">—</option>{d.departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
            {T({ k: 'designation', label: 'Designation', placeholder: 'e.g., Mathematics Teacher' })}</div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Staff type</label>
              <select className="form-control" value={f.staff_type} onChange={(e) => set('staff_type', e.target.value)}>{d.staff_types.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Employment</label>
              <select className="form-control" value={f.employment_type} onChange={(e) => set('employment_type', e.target.value)}>{d.employment_types.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Status</label>
              <select className="form-control" value={f.status} onChange={(e) => set('status', e.target.value)}>{d.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
          </div>
          <div className="form-row">{T({ k: 'date_employed', label: 'Date employed', type: 'date' })}{T({ k: 'salary', label: 'Monthly salary (₦)', type: 'number', min: '0', step: '500' })}</div>
          <div className="form-row">{T({ k: 'confirmation_date', label: 'Confirmation date', type: 'date' })}
            {T({ k: 'contract_start', label: 'Contract start', type: 'date' })}{T({ k: 'contract_end', label: 'Contract end / expiry', type: 'date' })}</div>
          <div className="form-row">{T({ k: 'qualification', label: 'Qualification', placeholder: 'e.g., B.Sc Mathematics, PGDE' })}
            {T({ k: 'prior_experience_years', label: 'Prior experience (yrs)', type: 'number', min: '0' })}</div>
          {T({ k: 'certifications', label: 'Professional certifications', placeholder: 'e.g., TRCN, ICAN' })}
        </div></div>

        <div className="card mb-3"><div className="card-header"><h3>Next of kin &amp; emergency</h3></div><div className="card-body">
          <div className="form-row">{T({ k: 'nok_name', label: 'Next of kin' })}{T({ k: 'nok_phone', label: 'NOK phone' })}{T({ k: 'nok_relationship', label: 'Relationship' })}</div>
          <div className="form-row">{T({ k: 'emergency_name', label: 'Emergency contact' })}{T({ k: 'emergency_phone', label: 'Emergency phone' })}</div>
        </div></div>

        <div className="card mb-3"><div className="card-header"><h3>Bank, statutory &amp; medical</h3></div><div className="card-body">
          <div className="form-row">{T({ k: 'bank_name', label: 'Bank' })}{T({ k: 'account_number', label: 'Account number' })}{T({ k: 'account_name', label: 'Account name' })}</div>
          <div className="form-row">{T({ k: 'tax_id', label: 'Tax ID (TIN)' })}{T({ k: 'pension_pin', label: 'Pension PIN' })}{T({ k: 'pension_provider', label: 'Pension provider (PFA)' })}</div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Blood group</label>
              <select className="form-control" value={f.blood_group} onChange={(e) => set('blood_group', e.target.value)}><option value="">—</option>{(d.blood_groups || []).map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
            <div className="form-group" style={{ flex: 2 }}><label className="form-label">Medical notes</label>
              <input type="text" className="form-control" placeholder="Allergies, conditions (confidential)" value={f.medical_notes} onChange={(e) => set('medical_notes', e.target.value)} /></div>
          </div>
          <div className="form-group"><label className="form-label">Notes</label><textarea className="form-control" rows="2" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></div>
        </div></div>

        {d.mode !== 'edit' && (
          <div className="card mb-3"><div className="card-header"><h3>Access</h3></div><div className="card-body">
            <label className="permission-item" style={{ display: 'inline-flex' }}>
              <input type="checkbox" checked={!!f.create_user} onChange={(e) => set('create_user', e.target.checked)} />
              <span>Also create a login account for this staff member (a temporary password is shown after saving)</span></label>
          </div></div>
        )}

        <Bar>
          <span className="rs-bar-t"><b>{[f.first_name, f.surname].filter(Boolean).join(' ') || 'New staff member'}</b><small>{f.designation || 'No role yet'}</small></span>
          <a href={d.cancel_url} className="rs-btn ghost">Cancel</a>
          <button type="submit" className="rs-btn primary" disabled={busy}><i className="fas fa-floppy-disk" aria-hidden="true" /> {d.mode === 'edit' ? 'Save changes' : 'Add staff'}</button>
        </Bar>
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
            ? <table className="data-table no-mobile-scroll" style={{ marginTop: '.5rem' }}><tbody>
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

function LatenessSection({ d }) {
  const nav = useNav();
  const lb = d.late_breakdown || { days: [], days_late: 0, total_minutes: 0, total_deduction: 0 };
  return (
    <div className="card mb-3">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '.5rem' }}>
        <h3><i aria-hidden="true" className="fas fa-clock" /> Lateness breakdown</h3>
        <input type="month" className="form-control" style={{ width: 'auto' }} value={d.late_breakdown_ym}
               onChange={(e) => e.target.value && navParams(nav.go, d.urls.self, { ym: e.target.value })} />
      </div>
      <div className="card-body">
        <div className="hub-stat-row mb-2">
          <div className="hub-stat"><div className="v text-warning">{lb.days_late}</div><div className="l">Days late</div></div>
          <div className="hub-stat"><div className="v">{lb.total_minutes}</div><div className="l">Total minutes late</div></div>
          <div className="hub-stat"><div className="v text-danger">{naira(lb.total_deduction)}</div><div className="l">Total cost</div></div>
        </div>
        {lb.days.length > 0 ? (
          <table className="data-table no-mobile-scroll">
            <thead><tr><th>Date</th><th>Clock-in</th><th className="text-right">Minutes late</th><th className="text-right">Cost</th></tr></thead>
            <tbody>
              {lb.days.map((r) => (
                <tr key={r.date}>
                  <td>{r.date_label}</td><td>{r.clock_in || '—'}</td>
                  <td className="text-right">{r.minutes_late}</td><td className="text-right">{naira(r.deduction)}</td>
                </tr>
              ))}
              <tr style={{ fontWeight: 700, borderTop: '2px solid var(--border-color)' }}>
                <td colSpan={2}>Total</td>
                <td className="text-right">{lb.total_minutes}</td>
                <td className="text-right">{naira(lb.total_deduction)}</td>
              </tr>
            </tbody>
          </table>
        ) : <p className="text-muted text-sm mb-0">No lateness recorded for {d.late_breakdown_label}.</p>}
      </div>
    </div>
  );
}

// ---- Staff detail ----------------------------------------------------------
// ---- Per-staff recurring deductions + contributions ------------------------
// Welfare, cooperative, union dues — set this person's own monthly amount and
// see how much they've contributed to each so far (from finalized payslips).
function DeductionsSection({ d, notify }) {
  const nav = useNav();
  const dd = d.deductions || { items: [], total_monthly: 0, total_contributed: 0 };
  const editable = dd.items.filter((i) => i.type_id);   // active types can be assigned
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(null);
  const val = (i) => (draft[i.type_id] !== undefined ? draft[i.type_id] : (i.monthly ? String(i.monthly) : ''));
  const save = async (i) => {
    setBusy(i.type_id);
    const r = await submitJson(d.urls.save_deduction, { type_id: i.type_id, amount: val(i) });
    setBusy(null);
    if (r.ok) { notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Could not save.');
  };
  if (!dd.items.length) {
    return (
      <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-hand-holding-dollar" /> Recurring deductions &amp; contributions</h3></div>
        <div className="card-body"><Empty icon="fa-hand-holding-dollar" title="No recurring deductions">
          <p>Add deduction items (Welfare, Cooperative…) in HR Settings, then set each staff member's amount here.</p></Empty></div></div>
    );
  }
  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-hand-holding-dollar" /> Recurring deductions &amp; contributions</h3></div>
      <div className="card-body" style={{ padding: 0 }}><div className="table-container"><table className="data-table table-stack no-mobile-scroll">
        <thead><tr><th>Item</th><th className="text-right">Monthly</th><th className="text-right">Contributed so far</th><th>Since / last</th>{canWrite(d, 'deductions_assign') && <th />}</tr></thead>
        <tbody>{dd.items.map((i, k) => (
          <tr key={k}>
            <td data-label="Item">{i.name}{i.assigned && <span className="badge badge-info ml-1" title="A per-staff amount is set for this person">custom</span>}{!i.type_id && <span className="badge badge-secondary ml-1" title="This deduction item is no longer active">archived</span>}</td>
            <td data-label="Monthly" className="text-right">
              {canWrite(d, 'deductions_assign') && i.type_id
                ? <span className="d-inline-flex gap-1" style={{ justifyContent: 'flex-end' }}>
                    <input type="number" min="0" step="100" inputMode="decimal" className="form-control form-control-sm text-right" style={{ maxWidth: 120 }}
                      value={val(i)} placeholder="0" aria-label={`${i.name} monthly amount`}
                      onChange={(e) => setDraft((x) => ({ ...x, [i.type_id]: e.target.value }))} />
                    <button className="btn btn-primary btn-sm" disabled={busy === i.type_id} onClick={() => save(i)} title="Save amount"><i aria-hidden="true" className="fas fa-check" /></button>
                  </span>
                : <>{i.monthly ? naira(i.monthly) : '—'}</>}
            </td>
            <td data-label="Contributed so far" className="text-right"><strong>{naira(i.contributed)}</strong>{i.months ? <span className="text-muted text-sm"> · {i.months} mo</span> : null}</td>
            <td data-label="Since / last">{i.last || '—'}</td>
            {canWrite(d, 'deductions_assign') && <td />}
          </tr>))}</tbody>
        <tfoot><tr>
          <th>Total</th>
          <th className="text-right">{naira(dd.total_monthly)}<span className="text-muted text-sm">/mo</span></th>
          <th className="text-right">{naira(dd.total_contributed)}</th>
          <th />{canWrite(d, 'deductions_assign') && <th />}
        </tr></tfoot>
      </table></div></div>
      {canWrite(d, 'deductions_assign') && <div className="card-footer text-muted text-sm"><i aria-hidden="true" className="fas fa-circle-info" /> Set a per-staff monthly amount (e.g. Welfare ₦10,000). Leave blank to use the item's default. Changes apply to payroll generated from now on. “Contributed so far” counts finalized &amp; paid payslips.</div>}
    </div>
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
        {canWrite(d, 'staff_lifecycle') && <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggle('promote', { designation: s.designation || '', new_salary: s.salary || '', effective_date: d.today })}><i aria-hidden="true" className="fas fa-arrow-trend-up" /> Promote</button>}
        {canWrite(d, 'staff_lifecycle') && branches.length > 0 && <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggle('transfer', { effective_date: d.today })}><i aria-hidden="true" className="fas fa-arrows-left-right" /> Transfer</button>}
        {canWrite(d, 'staff_lifecycle') && !s.confirmation_date && <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggle('confirm', { effective_date: d.today })}><i aria-hidden="true" className="fas fa-user-check" /> Confirm</button>}
        {canWrite(d, 'staff_edit') && <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggle('note', { effective_date: d.today })}><i aria-hidden="true" className="fas fa-note-sticky" /> Note</button>}
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
  const [showHist, setShowHist] = useState({});
  const fileRef = useRef();
  const replaceRef = useRef();
  const replacingRef = useRef(null);
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
  const onReplace = async (e) => {
    const picked = e.target.files && e.target.files[0];
    e.target.value = '';
    const doc = replacingRef.current;
    if (!picked || !doc) return;
    setBusy(true);
    const r = await postFile(doc.replace_url, picked, { title: doc.title, doc_type: doc.doc_type });
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Upload failed.');
  };
  return (
    <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-folder-open" /> Documents</h3></div>
      <div className="card-body">
        <input type="file" ref={replaceRef} style={{ display: 'none' }} onChange={onReplace} />
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
              <React.Fragment key={doc.id}>
              <tr><td data-label="Title">{doc.download_url ? <a href={doc.download_url} data-native>{doc.title}</a> : doc.title}{doc.version > 1 && <span className="badge badge-secondary" style={{ marginLeft: '.3rem' }}>v{doc.version}</span>}{doc.name && <div className="text-muted text-sm">{doc.name}{doc.size ? ` · ${doc.size}` : ''}{doc.prior && doc.prior.length > 0 && <> · <a href="#" onClick={(e) => { e.preventDefault(); setShowHist((h) => ({ ...h, [doc.id]: !h[doc.id] })); }}>{doc.prior.length} older</a></>}</div>}</td>
                <td data-label="Type"><span className="badge badge-secondary">{doc.doc_type}</span></td>
                <td data-label="Expires">{doc.expires_on ? <span className={doc.is_expired ? 'text-danger' : ''}>{doc.expires_on}{doc.is_expired ? ' (expired)' : ''}</span> : '—'}</td>
                <td className="actions"><div className="d-flex gap-1 justify-end">
                  <button className="btn btn-secondary btn-sm" title="Upload new version" onClick={() => { replacingRef.current = doc; replaceRef.current && replaceRef.current.click(); }}><i aria-hidden="true" className="fas fa-arrow-up-from-bracket" /></button>
                  <button className="btn btn-danger btn-sm" onClick={() => act(doc.delete_url, {}, `Delete “${doc.title}” and all its versions?`)}><i aria-hidden="true" className="fas fa-trash" /></button>
                </div></td></tr>
              {showHist[doc.id] && (doc.prior || []).map((pv, i) => (
                <tr key={doc.id + '-' + i} style={{ background: 'var(--gray-50)' }}><td className="stack-full" colSpan={4} style={{ paddingLeft: '1.5rem' }}>
                  <span className="text-muted text-sm">v{pv.version} · {pv.created} · </span>{pv.download_url ? <a href={pv.download_url} data-native className="text-sm">download</a> : <span className="text-muted text-sm">file removed</span>}
                </td></tr>))}
              </React.Fragment>))}</tbody>
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
      {canWrite(d, 'reviews_edit') && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(!open)}><i aria-hidden="true" className="fas fa-plus" /> Add review</button>}</div>
      <div className="card-body">
        {open && canWrite(d, 'reviews_edit') && (
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
                {canWrite(d, 'reviews_edit') && <button className="btn btn-danger btn-sm" onClick={() => act(r.delete_url, {}, `Delete the ${r.period} review?`)}><i aria-hidden="true" className="fas fa-trash" /></button>}
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
        {canWrite(d, 'staff_lifecycle') && (
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
        {canWrite(d, 'leave_create') && (
        <form onSubmit={add} className="d-flex gap-2 align-end flex-wrap mb-3">
          <div className="form-group mb-0"><label className="form-label">Type</label><select className="form-control" value={f.leave_type} onChange={(e) => set('leave_type', e.target.value)}>{d.leave_types.map((t) => <option key={t}>{t}</option>)}</select></div>
          <div className="form-group mb-0"><label className="form-label">From</label><input type="date" className="form-control" required value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
          <div className="form-group mb-0"><label className="form-label">To</label><input type="date" className="form-control" required value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
          <div className="form-group mb-0" style={{ flex: 1, minWidth: 160 }}><label className="form-label">Reason</label><input type="text" className="form-control" value={f.reason} onChange={(e) => set('reason', e.target.value)} /></div>
          <button className="btn btn-secondary"><i aria-hidden="true" className="fas fa-plus" /> Add</button>
        </form>
        )}
        {d.leaves.length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th /></tr></thead>
            <tbody>{d.leaves.map((lv) => (
              <tr key={lv.id}><td data-label="Type">{lv.leave_type}</td><td data-label="Dates">{lv.dates}</td><td data-label="Days">{lv.days}</td>
                <td data-label="Status"><span className={leaveBadge(lv.status)}>{lv.status}</span></td>
                <td className="actions"><div className="d-flex gap-1 justify-end">
                  {canWrite(d, 'leave_approve') && lv.status !== 'Approved' && <button className="btn btn-success btn-sm" title="Approve" onClick={() => act(lv.approve_url, { status: 'Approved' })}><i aria-hidden="true" className="fas fa-check" /></button>}
                  {canWrite(d, 'leave_approve') && lv.status !== 'Rejected' && <button className="btn btn-secondary btn-sm" title="Reject" onClick={() => act(lv.approve_url, { status: 'Rejected' })}><i aria-hidden="true" className="fas fa-xmark" /></button>}
                  {canWrite(d, 'leave_delete') && <button className="btn btn-danger btn-sm" onClick={() => act(lv.delete_url, {}, 'Delete leave record?')}><i aria-hidden="true" className="fas fa-trash" /></button>}
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
      <Head icon="fa-sitemap" title="Departments" sub={`${d.departments.length} departments · ${d.departments.reduce((t, x) => t + (x.count || 0), 0)} staff`} />
      <Tabs d={d} />
      {canWrite(d, 'departments_create') && (
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Add Department</h3></div>
          <div className="card-body"><form onSubmit={add} className="d-flex gap-2 align-end flex-wrap">
            <div className="form-group mb-0" style={{ flex: 1, minWidth: 200 }}><label className="form-label">Name</label><input type="text" className="form-control" placeholder="e.g., Sports" required value={name} onChange={(e) => setName(e.target.value)} /></div>
            <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Add</button>
          </form></div></div>
      )}
      <div className="card"><div className="card-header"><h3>Departments ({d.departments.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}><div className="table-container"><table className="data-table table-stack no-mobile-scroll">
          <thead><tr><th>Name</th><th className="text-right">Staff</th><th>Status</th>{(canWrite(d, 'departments_edit') || canWrite(d, 'departments_delete')) && <th />}</tr></thead>
          <tbody>{d.departments.map((dep) => (
            <React.Fragment key={dep.id}>
              <tr>
                <td data-label="Name"><strong>{dep.name}</strong></td>
                <td data-label="Staff" className="text-right">{dep.count}</td>
                <td data-label="Status">{dep.is_active ? <span className="badge badge-success">Active</span> : <span className="badge badge-secondary">Inactive</span>}</td>
                {(canWrite(d, 'departments_edit') || canWrite(d, 'departments_delete')) && <td className="actions"><div className="d-flex gap-1 justify-end">
                  {canWrite(d, 'departments_edit') && <button className="btn btn-secondary btn-sm" onClick={() => setEditing(editing === dep.id ? null : dep.id)}><i aria-hidden="true" className="fas fa-edit" /></button>}
                  {canWrite(d, 'departments_delete') && <button className="btn btn-danger btn-sm" onClick={() => act(dep.delete_url, {}, `Delete ${dep.name}?`)}><i aria-hidden="true" className="fas fa-trash" /></button>}
                </div></td>}
              </tr>
              {canWrite(d, 'departments_edit') && editing === dep.id && (
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
// ---- Payroll list ----------------------------------------------------------
// ---- Payroll detail --------------------------------------------------------
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
      <Head icon="fa-gear" title="HR settings" sub="Resumption time, deductions, leave allowances and check-in" />
      <Tabs d={d} />
      <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-user-clock" /> Attendance &amp; Deductions</h3></div>
        <div className="card-body"><form onSubmit={saveSettings}>
          <fieldset disabled={!canWrite(d, 'settings_edit')} style={{ border: 0, padding: 0, margin: 0 }}>
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
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>Deductions applied to staff payslips each month — e.g. pension (a % of basic) or welfare (a fixed amount). The value below is the <strong>default</strong> for everyone; use <strong>Per-staff amounts</strong> to set a different amount per person (Welfare ₦5,000 for one, ₦15,000 for another).</p>
          {canWrite(d, 'deduction_types_edit') && (
            <form onSubmit={addDed} className="d-flex gap-2 align-end flex-wrap mb-3">
              <div className="form-group mb-0" style={{ flex: 2, minWidth: 160 }}><label className="form-label">Name</label><input type="text" className="form-control" placeholder="e.g. Pension, Welfare, Union dues" required value={ded.name} onChange={(e) => setDed((x) => ({ ...x, name: e.target.value }))} /></div>
              <div className="form-group mb-0"><label className="form-label">Type</label><select className="form-control" value={ded.kind} onChange={(e) => setDed((x) => ({ ...x, kind: e.target.value }))}><option value="percent">% of basic</option><option value="fixed">Fixed ₦</option></select></div>
              <div className="form-group mb-0"><label className="form-label">Value</label><input type="number" className="form-control" min="0" step="0.5" placeholder="5 or 500" required value={ded.value} onChange={(e) => setDed((x) => ({ ...x, value: e.target.value }))} /></div>
              <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</button>
            </form>
          )}
          {d.deductions.length ? (
            <table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Name</th><th>Deduction</th><th>Status</th><th /></tr></thead>
              <tbody>{d.deductions.map((dd) => (
                <tr key={dd.id} style={dd.is_active ? undefined : { opacity: 0.55 }}>
                  <td data-label="Name">{dd.name}</td>
                  <td data-label="Deduction">{dd.kind === 'percent' ? `${Math.round(dd.value * 100) / 100}% of basic` : `${naira(dd.value)} fixed`}</td>
                  <td data-label="Status">{dd.is_active ? <span className="badge badge-success">Active</span> : <span className="badge badge-warning">Inactive</span>}</td>
                  <td className="actions"><div className="d-flex gap-1 justify-end">
                    {canWrite(d, 'deductions_assign') && <a className="btn btn-secondary btn-sm" title="Set each staff member's amount" href={dd.amounts_url} data-native><i aria-hidden="true" className="fas fa-user-pen" /> Per-staff amounts</a>}
                    {canWrite(d, 'deduction_types_edit') && <button className="btn btn-secondary btn-sm" title="Toggle active" onClick={() => act(dd.toggle_url, {})}><i aria-hidden="true" className="fas fa-power-off" /></button>}
                    {canWrite(d, 'deduction_types_edit') && <button className="btn btn-danger btn-sm" title="Delete" onClick={() => act(dd.delete_url, {}, 'Remove this deduction?')}><i aria-hidden="true" className="fas fa-trash" /></button>}
                  </div></td>
                </tr>))}</tbody>
            </table>
          ) : <p className="text-muted text-sm">No recurring deductions yet.</p>}
        </div></div>

      <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plane-departure" /> Leave Allowances</h3></div>
        <div className="card-body">
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>Annual entitlement (days) per leave type. Balances on each staff profile count approved leave against these.</p>
          <form onSubmit={saveAllowances}>
            <fieldset disabled={!canWrite(d, 'settings_edit')} style={{ border: 0, padding: 0, margin: 0 }}>
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
      <Head icon="fa-chart-line" title="HR reports" sub={rep.title}>
        <Menu label="Export" items={[
          { icon: 'fa-file-csv', label: 'Download CSV', href: `${d.urls.export}?format=csv&${qs()}`, native: true },
          { icon: 'fa-file-excel', label: 'Download Excel', href: `${d.urls.export}?format=xlsx&${qs()}`, native: true },
        ]} />
      </Head>
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
      <Head icon="fa-fingerprint" title="Check in" sub={d.today_label} />
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
            {/* Plain one-tap clock-in with the current time — the default when the
                school hasn't enabled GPS. Hidden once already checked in today. */}
            {!d.geo.enabled && !d.today && <button className="btn btn-primary" disabled={busy} onClick={() => post({ method: 'manual' })}><i aria-hidden="true" className="fas fa-fingerprint" /> Clock in now</button>}
            {d.geo.enabled && <button className="btn btn-primary" disabled={busy} onClick={gpsCheckin}><i aria-hidden="true" className="fas fa-location-crosshairs" /> Check in with location</button>}
            <a href={d.urls.qr} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-qrcode" /> Scan QR instead</a>
          </div>
          {d.prefill_code && !d.today && <button className="btn btn-primary mt-2" disabled={busy} onClick={() => post({ method: 'qr', code: d.prefill_code })}><i aria-hidden="true" className="fas fa-check" /> Confirm QR check-in</button>}
          {!d.geo.enabled && <p className="form-hint mt-2">Tip: an administrator can require on-site GPS check-in in HR Settings.</p>}
        </div></div>
      )}
    </>
  );
}

function CheckInQR({ d }) {
  return (
    <>
      <Head icon="fa-qrcode" title="Check-in QR" sub="Show this on a screen at the gate or staff room">
        <a href={d.urls.attendance} className="rs-btn ghost"><i className="fas fa-arrow-left" aria-hidden="true" /><span className="rs-hide-sm">Attendance</span></a>
      </Head>
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

// ---- Recruitment: vacancies list -------------------------------------------
const vacBadge = (s) => 'badge ' + (s === 'Open' ? 'badge-success' : s === 'Filled' ? 'badge-info' : 'badge-secondary');
const appBadge = (s) => 'badge ' + ({ Applied: 'badge-secondary', Shortlisted: 'badge-info', Interview: 'badge-warning', Offered: 'badge-primary', Hired: 'badge-success', Rejected: 'badge-danger' }[s] || 'badge-secondary');

function Recruitment({ d, notify }) {
  const nav = useNav();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: '', department_id: '', staff_type: (d.staff_types || ['Teaching'])[0], employment_type: (d.employment_types || ['Full-time'])[0], positions: 1, closing_date: '', description: '', requirements: '' });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const add = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Enter a job title.'); return; }
    const r = await submitJson(d.add_url, f);
    if (r.ok) { notify('success', r.message); nav.go(r.redirect); } else notify('error', r.error || 'Could not post.');
  };
  return (
    <>
      <Head icon="fa-user-plus" title="Recruitment" sub={`${d.vacancies.filter((v) => v.status === 'Open').length} open vacancies · ${d.vacancies.reduce((t, v) => t + (v.applicants || 0), 0)} applicants`}>
        {canWrite(d, 'recruitment_create') && <button type="button" className="rs-btn primary" onClick={() => setOpen(!open)}><i className="fas fa-bullhorn" aria-hidden="true" /><span className="rs-hide-sm">Post vacancy</span></button>}
      </Head>
      <Tabs d={d} />
      {open && canWrite(d, 'recruitment_create') && (
        <div className="card mb-3"><div className="card-header"><h3>New vacancy</h3></div><div className="card-body">
          <form onSubmit={add}>
            <div className="form-row">
              <div className="form-group" style={{ flex: 2 }}><label className="form-label">Job title <span className="required">*</span></label><input type="text" className="form-control" value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
              <div className="form-group"><label className="form-label">Department</label><select className="form-control" value={f.department_id} onChange={(e) => set('department_id', e.target.value)}><option value="">—</option>{d.departments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
              <div className="form-group"><label className="form-label">Openings</label><input type="number" className="form-control" min="1" value={f.positions} onChange={(e) => set('positions', e.target.value)} /></div>
            </div>
            <div className="form-row">
              <div className="form-group"><label className="form-label">Type</label><select className="form-control" value={f.staff_type} onChange={(e) => set('staff_type', e.target.value)}>{d.staff_types.map((t) => <option key={t}>{t}</option>)}</select></div>
              <div className="form-group"><label className="form-label">Employment</label><select className="form-control" value={f.employment_type} onChange={(e) => set('employment_type', e.target.value)}>{d.employment_types.map((t) => <option key={t}>{t}</option>)}</select></div>
              <div className="form-group"><label className="form-label">Closing date</label><input type="date" className="form-control" value={f.closing_date} onChange={(e) => set('closing_date', e.target.value)} /></div>
            </div>
            <div className="form-group"><label className="form-label">Description</label><textarea className="form-control" rows="2" value={f.description} onChange={(e) => set('description', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Requirements</label><textarea className="form-control" rows="2" value={f.requirements} onChange={(e) => set('requirements', e.target.value)} /></div>
            <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-bullhorn" /> Post</button>
          </form>
        </div></div>
      )}
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Status</label>
          <select className="form-control" value={d.status} onChange={(e) => navParams(nav.go, d.self_url, { status: e.target.value })}>
            <option value="">All</option>{d.statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
      </div></div></div>
      <div className="card"><div className="card-header"><h3>{d.vacancies.length} vacancy(ies)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.vacancies.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Title</th><th>Dept</th><th>Openings</th><th className="text-right">Applicants</th><th>Status</th><th /></tr></thead>
              <tbody>{d.vacancies.map((v) => (
                <tr key={v.id}><td data-label="Title"><a href={v.url}><strong>{v.title}</strong></a><div className="text-muted text-sm">{v.staff_type} · {v.employment_type}</div></td>
                  <td data-label="Dept">{v.department || '—'}</td><td data-label="Openings">{v.positions}</td>
                  <td data-label="Applicants" className="text-right">{v.applicants}{v.shortlisted ? <span className="text-muted text-sm"> ({v.shortlisted} short)</span> : ''}</td>
                  <td data-label="Status"><span className={vacBadge(v.status)}>{v.status}</span></td>
                  <td className="actions"><a href={v.url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-right" /></a></td></tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-user-plus" title="No vacancies"><p>Post an opening to start receiving applications.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Recruitment: vacancy detail + pipeline --------------------------------
function Vacancy({ d, notify }) {
  const nav = useNav();
  const v = d.vacancy;
  const [addOpen, setAddOpen] = useState(false);
  const [af, setAf] = useState({ first_name: '', surname: '', email: '', phone: '', qualification: '', experience_years: '', cover_note: '' });
  const [file, setFile] = useState(null);
  const [intvFor, setIntvFor] = useState(null);
  const setA = (k, val) => setAf((x) => ({ ...x, [k]: val }));
  const act = async (url, fields, confirmMsg, follow) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); follow ? nav.go(r.redirect) : nav.refresh(); }
    else notify('error', r.error || 'Action failed.');
  };
  const addApp = async (e) => {
    e.preventDefault();
    if (!af.first_name.trim() || !af.surname.trim()) { notify('error', 'Enter the candidate name.'); return; }
    const r = file ? await postFile(d.urls.add_application, file, af) : await submitJson(d.urls.add_application, af);
    if (r.ok) { notify('success', r.message); setAf({ first_name: '', surname: '', email: '', phone: '', qualification: '', experience_years: '', cover_note: '' }); setFile(null); setAddOpen(false); nav.refresh(); }
    else notify('error', r.error || 'Could not add.');
  };
  return (
    <>
      <Head icon="fa-briefcase" title={v.title} sub={[v.department, v.staff_type, v.employment_type].filter(Boolean).join(' · ')}>
        <Menu label="More" items={[
          { icon: 'fa-arrow-left', label: 'All vacancies', href: d.urls.back },
          canWrite(d, 'recruitment_delete') && { icon: 'fa-trash', label: 'Delete vacancy', danger: true, onClick: () => act(d.urls.delete, {}, 'Delete this vacancy and its applications?', true) },
        ]} />
      </Head>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <div className="d-flex gap-2 flex-wrap align-center mb-2">
          <span className={vacBadge(v.status)}>{v.status}</span>
          <span className="badge badge-secondary">{v.staff_type}</span>
          <span className="badge badge-secondary">{v.employment_type}</span>
          <span className="text-muted">{v.department || 'No department'} · {v.hired}/{v.positions} filled{v.posted ? ` · posted ${v.posted}` : ''}</span>
        </div>
        {v.description && <p className="mb-1">{v.description}</p>}
        {v.requirements && <p className="text-muted text-sm mb-0"><strong>Requirements:</strong> {v.requirements}</p>}
        {canWrite(d, 'recruitment_edit') && (
          <div className="d-flex gap-1 mt-2 flex-wrap">
            {d.statuses.filter((s) => s !== v.status).map((s) => (
              <button key={s} className="btn btn-secondary btn-sm" onClick={() => act(d.urls.edit, { title: v.title, department_id: v.department_id, staff_type: v.staff_type, employment_type: v.employment_type, positions: v.positions, closing_date: v.closing_date, description: v.description, requirements: v.requirements, status: s })}>Mark {s}</button>))}
          </div>)}
      </div></div>

      <div className="d-flex justify-between align-center mb-2">
        <h3 style={{ margin: 0 }}>Applications ({d.applications.length})</h3>
        {canWrite(d, 'recruitment_create') && <button className="btn btn-primary btn-sm" onClick={() => setAddOpen(!addOpen)}><i aria-hidden="true" className="fas fa-plus" /> Add applicant</button>}
      </div>
      {addOpen && canWrite(d, 'recruitment_create') && (
        <div className="card mb-3"><div className="card-body"><form onSubmit={addApp}>
          <div className="form-row">
            <div className="form-group"><label className="form-label">First name <span className="required">*</span></label><input type="text" className="form-control" value={af.first_name} onChange={(e) => setA('first_name', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Surname <span className="required">*</span></label><input type="text" className="form-control" value={af.surname} onChange={(e) => setA('surname', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Phone</label><input type="text" className="form-control" value={af.phone} onChange={(e) => setA('phone', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Email</label><input type="email" className="form-control" value={af.email} onChange={(e) => setA('email', e.target.value)} /></div>
          </div>
          <div className="form-row">
            <div className="form-group" style={{ flex: 2 }}><label className="form-label">Qualification</label><input type="text" className="form-control" value={af.qualification} onChange={(e) => setA('qualification', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Experience (yrs)</label><input type="number" className="form-control" min="0" value={af.experience_years} onChange={(e) => setA('experience_years', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">CV / résumé</label><input type="file" className="form-control" onChange={(e) => setFile(e.target.files && e.target.files[0])} /></div>
          </div>
          <div className="form-group"><label className="form-label">Cover note</label><textarea className="form-control" rows="2" value={af.cover_note} onChange={(e) => setA('cover_note', e.target.value)} /></div>
          <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Add</button>
        </form></div></div>
      )}

      {d.applications.length ? d.applications.map((a) => (
        <div key={a.id} className="card mb-2"><div className="card-body">
          <div className="d-flex justify-between align-center flex-wrap gap-1">
            <div><strong>{a.name}</strong> <span className={appBadge(a.status)}>{a.status}</span>
              <div className="text-muted text-sm">{[a.qualification, a.experience_years != null ? `${a.experience_years} yr(s)` : '', a.phone, a.email].filter(Boolean).join(' · ')}</div></div>
            <div className="d-flex gap-1 flex-wrap">
              {a.resume_url && <a href={a.resume_url} data-native className="btn btn-secondary btn-sm" title="CV"><i aria-hidden="true" className="fas fa-file-lines" /></a>}
              {a.staff_url && <a href={a.staff_url} className="btn btn-success btn-sm"><i aria-hidden="true" className="fas fa-id-badge" /> Staff</a>}
              {a.status !== 'Hired' && a.status !== 'Rejected' && <>
                {a.status === 'Applied' && canWrite(d, 'recruitment_edit') && <button className="btn btn-secondary btn-sm" onClick={() => act(a.status_url, { status: 'Shortlisted' })}>Shortlist</button>}
                {canWrite(d, 'recruitment_edit') && <button className="btn btn-secondary btn-sm" onClick={() => setIntvFor(intvFor === a.id ? null : a.id)}><i aria-hidden="true" className="fas fa-calendar-day" /> Interview</button>}
                {canWrite(d, 'recruitment_hire') && <button className="btn btn-primary btn-sm" onClick={() => act(a.hire_url, {}, `Hire ${a.name} and add them to staff?`, true)}><i aria-hidden="true" className="fas fa-user-check" /> Hire</button>}
                {canWrite(d, 'recruitment_edit') && <button className="btn btn-secondary btn-sm" onClick={() => act(a.status_url, { status: 'Rejected' }, `Reject ${a.name}?`)}>Reject</button>}
              </>}
              {canWrite(d, 'recruitment_delete') && <button className="btn btn-danger btn-sm" onClick={() => act(a.delete_url, {}, 'Delete this application?')}><i aria-hidden="true" className="fas fa-trash" /></button>}
            </div>
          </div>
          {a.cover_note && <p className="text-muted text-sm mt-1 mb-0">{a.cover_note}</p>}
          {a.interviews.length > 0 && (
            <div className="mt-2">{a.interviews.map((iv) => (
              <div key={iv.id} className="d-flex justify-between align-center flex-wrap gap-1" style={{ borderTop: '1px solid var(--border-light)', paddingTop: '.4rem', marginTop: '.4rem' }}>
                <span className="text-sm"><i aria-hidden="true" className="fas fa-calendar-day" /> {iv.when || 'TBD'} · {iv.mode}{iv.location ? ` · ${iv.location}` : ''}{iv.interviewer ? ` · ${iv.interviewer}` : ''}</span>
                <span className="d-flex gap-1 align-center">
                  <span className={'badge ' + (iv.outcome === 'Passed' ? 'badge-success' : iv.outcome === 'Failed' ? 'badge-danger' : 'badge-warning')}>{iv.outcome}</span>
                  {iv.outcome === 'Pending' && canWrite(d, 'recruitment_edit') && <>
                    <button className="btn btn-success btn-sm" onClick={() => act(iv.outcome_url, { outcome: 'Passed' })}><i aria-hidden="true" className="fas fa-check" /></button>
                    <button className="btn btn-secondary btn-sm" onClick={() => act(iv.outcome_url, { outcome: 'Failed' })}><i aria-hidden="true" className="fas fa-xmark" /></button>
                  </>}
                </span>
              </div>))}</div>
          )}
          {intvFor === a.id && <InterviewForm d={d} url={a.interview_url} onDone={() => { setIntvFor(null); nav.refresh(); }} notify={notify} />}
        </div></div>
      )) : <div className="card"><div className="card-body"><Empty icon="fa-users" title="No applications yet"><p>Add candidates above as they apply.</p></Empty></div></div>}
    </>
  );
}

function InterviewForm({ d, url, onDone, notify }) {
  const [f, setF] = useState({ scheduled_at: '', mode: (d.interview_modes || ['In-person'])[0], location: '', interviewer: '', notes: '' });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    const r = await submitJson(url, f);
    if (r.ok) { notify('success', r.message); onDone(); } else notify('error', r.error || 'Could not schedule.');
  };
  return (
    <form onSubmit={submit} className="lc-form mt-2">
      <div className="form-group mb-0"><label className="form-label">When</label><input type="datetime-local" className="form-control" value={f.scheduled_at} onChange={(e) => set('scheduled_at', e.target.value)} /></div>
      <div className="form-group mb-0"><label className="form-label">Mode</label><select className="form-control" value={f.mode} onChange={(e) => set('mode', e.target.value)}>{(d.interview_modes || []).map((m) => <option key={m}>{m}</option>)}</select></div>
      <div className="form-group mb-0"><label className="form-label">Location / link</label><input type="text" className="form-control" value={f.location} onChange={(e) => set('location', e.target.value)} /></div>
      <div className="form-group mb-0"><label className="form-label">Interviewer</label><input type="text" className="form-control" value={f.interviewer} onChange={(e) => set('interviewer', e.target.value)} /></div>
      <button className="btn btn-primary"><i aria-hidden="true" className="fas fa-calendar-plus" /> Schedule</button>
    </form>
  );
}

const SCREENS = { dashboard: Dashboard, staff: Staff, staff_form: StaffForm, staff_detail: StaffDetail,
  departments: Departments, leave: Leave, payroll: Payroll, payroll_detail: PayrollDetail,
  attendance: Attendance, checkin: CheckIn, checkin_qr: CheckInQR,
  recruitment: Recruitment, vacancy: Vacancy, reports: Reports, settings: Settings };

export default function HrApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Dashboard;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <div className={'rs hr hr-' + d.page}><Screen d={d} notify={notify} /></div>
      </SectionShell>
    </NavCtx.Provider>
  );
}
