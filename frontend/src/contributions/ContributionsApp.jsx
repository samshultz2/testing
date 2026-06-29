import React, { useState, useMemo } from 'react';
import { submitJson } from '../lib/forms';
import { useDraft } from '../lib/draft';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';

const money = (n) => '₦' + Math.round(Number(n) || 0).toLocaleString();
const armColor = (arm) => (arm === 'Iris' ? 'primary' : arm === 'Rose' ? 'danger' : arm === 'Lily' ? 'warning' : 'info');

function useSave(notify) {
  return async (url, fields, after, okMsg) => {
    const r = await submitJson(url, fields);
    if (r.ok) { notify('success', okMsg || r.message); after && after(r); }
    else notify('error', r.error || 'Something went wrong.');
    return r;
  };
}

const A = ({ to, className, children, title, style }) => {
  const nav = useNav();
  return <a href={to} title={title} className={className} style={style}
    onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};

const Stat = ({ icon, tone, value, label }) => (
  <div className="stat-card">
    <div className={`stat-icon ${tone}`}><i aria-hidden="true" className={`fas ${icon}`} /></div>
    <div className="stat-content"><h3>{value}</h3><p>{label}</p></div>
  </div>
);

function Bar({ pct, color = 'var(--success)', height = 8 }) {
  return (
    <div style={{ background: 'var(--border-color)', borderRadius: 4, height, overflow: 'hidden' }}>
      <div style={{ background: color, height: '100%', width: `${Math.min(100, pct)}%` }} />
    </div>
  );
}

// ---- Dashboard --------------------------------------------------------------
function Dashboard({ d }) {
  const u = d.urls;
  const s = d.stats;
  const [search, setSearch] = useState('');
  const [arm, setArm] = useState('');
  const [status, setStatus] = useState('');
  const shown = d.students.filter((st) =>
    st.name.toLowerCase().includes(search.toLowerCase())
    && (!arm || st.arm === arm) && (!status || st.status === status));
  const netTone = s.net_balance >= 0 ? 'success' : 'danger';
  return (
    <>
      <div className="page-header">
        <h1><i aria-hidden="true" className="fas fa-hand-holding-usd" /> SSS3 Contributions</h1>
        <div className="header-actions">
          <A to={u.quick_entry} className="btn btn-success"><i aria-hidden="true" className="fas fa-bolt" /> Quick Entry</A>
          <A to={u.add_payment} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Payment</A>
          <A to={u.import} className="btn btn-warning"><i aria-hidden="true" className="fas fa-file-import" /> Import</A>
          <a href={u.export} className="btn btn-info"><i aria-hidden="true" className="fas fa-file-excel" /> Export</a>
          <a href={u.logout} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-sign-out-alt" /> Exit</a>
        </div>
      </div>
      <div className="stats-grid mb-3">
        <Stat icon="fa-users" tone="primary" value={s.total_students} label="Total Students" />
        <Stat icon="fa-coins" tone="info" value={money(s.total_expected)} label="Expected" />
        <Stat icon="fa-hand-holding-usd" tone="success" value={money(s.total_received)} label="Received" />
        <Stat icon="fa-receipt" tone="warning" value={money(s.total_expenses)} label="Expenses" />
        <Stat icon="fa-wallet" tone={netTone} value={money(s.net_balance)} label="Net Balance" />
        <Stat icon="fa-check-circle" tone="success" value={`${s.fully_paid_count}/${s.total_students}`} label="Fully Paid" />
      </div>
      <div className="stats-grid mb-3">
        <Stat icon="fa-exclamation-circle" tone="danger" value={money(s.total_outstanding)} label="Outstanding" />
        <Stat icon="fa-calculator" tone="info" value={money(s.avg_paid)} label="Avg. Paid/Student" />
        <Stat icon="fa-clipboard-list" tone="primary" value={s.total_payments} label="Total Transactions" />
        <Stat icon="fa-calendar-day" tone="warning" value={money(s.today_collections)} label="Today's Collection" />
        <Stat icon="fa-calendar-week" tone="info" value={money(s.week_collections)} label="This Week" />
        <Stat icon="fa-percentage" tone="primary" value={`${s.collection_rate.toFixed(1)}%`} label="Collection Rate" />
      </div>

      <div className="card mb-3"><div className="card-body">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <span><strong>Collection Progress</strong></span>
          <strong>{money(s.total_received)} / {money(s.total_expected)}</strong>
        </div>
        <div style={{ background: 'var(--border-color)', borderRadius: 10, height: 24, overflow: 'hidden', position: 'relative' }}>
          <div style={{ background: 'linear-gradient(90deg, #1a5f4a, var(--success))', height: '100%', width: `${s.collection_rate}%` }} />
          <span style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%, -50%)', fontWeight: 'bold', color: s.collection_rate > 50 ? 'white' : '#333' }}>{s.collection_rate.toFixed(1)}%</span>
        </div>
      </div></div>

      <div className="card mb-3" style={{ borderLeft: `4px solid ${s.net_balance >= 0 ? 'var(--success)' : 'var(--danger)'}` }}>
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-calculator" /> Financial Summary</h3></div>
        <div className="card-body">
          <div className="financial-grid">
            <div className="financial-item"><span className="financial-label">Total Collected</span><span className="financial-value text-success">{money(s.total_received)}</span></div>
            <div className="financial-item"><span className="financial-label">Total Expenses</span><span className="financial-value text-danger">- {money(s.total_expenses)}</span></div>
            <div className="financial-item financial-total"><span className="financial-label">Available Balance</span><span className={`financial-value ${netTone === 'success' ? 'text-success' : 'text-danger'}`}>{money(s.net_balance)}</span></div>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <A to={u.expenses} className="btn btn-sm btn-outline-danger"><i aria-hidden="true" className="fas fa-receipt" /> View All Expenses</A>{' '}
            <A to={u.add_expense} className="btn btn-sm btn-outline-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Expense</A>
          </div>
        </div>
      </div>

      <div className="data-cards mb-3">
        {[['payments', 'fa-list', 'All Payments', `${s.total_payments}`, 'primary', 'View and manage payment records'],
          ['expenses', 'fa-receipt', 'Expenses', `${s.expense_count}`, 'warning', 'Track fund expenses'],
          ['report', 'fa-chart-bar', 'Report by Arm', null, null, 'Detailed breakdown by class arm'],
          ['defaulters', 'fa-user-times', 'Defaulters', `${s.total_students - s.fully_paid_count}`, 'danger', 'Students with outstanding balance'],
          ['daily_summary', 'fa-calendar-alt', 'Daily Summary', null, null, 'Collections by date'],
          ['history', 'fa-history', 'Session History', null, null, 'View past session records'],
          ['settings', 'fa-cog', 'Settings', null, null, 'Configure max due, dates']].map(([key, icon, title, badge, tone, sub]) => (
          <A key={key} to={u[key]} className="data-card" style={{ textDecoration: 'none', color: 'inherit' }}>
            <div className="data-card-header"><div className="data-card-title"><i aria-hidden="true" className={`fas ${icon}`} /> {title}</div>
              {badge != null && <span className={`badge badge-${tone}`}>{badge}</span>}</div>
            <div className="data-card-row">{sub}</div>
          </A>
        ))}
      </div>

      {d.arms_summary.some((a) => a.name) && <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-layer-group" /> Progress by Arm</h3></div>
        <div className="card-body">
          {d.arms_summary.map((a) => (
            <div className="arm-progress-row" key={a.name}>
              <div className="arm-info">
                <span className={`arm-name badge badge-${armColor(a.name)}`}>{a.name}</span>
                <span className="arm-stats">{a.paid}/{a.total} paid</span>
              </div>
              <div className="arm-bar-container">
                <div className="arm-bar" style={{ width: `${a.percentage}%`, background: a.percentage >= 75 ? 'var(--success)' : a.percentage >= 50 ? 'var(--warning)' : 'var(--danger)' }} />
              </div>
              <div className="arm-amount">{money(a.collected)}</div>
            </div>
          ))}
        </div>
      </div>}

      <div className="row mb-3">
        <div className="col-md-6"><div className="card h-100">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-clock" /> Recent Payments</h3>
            <A to={u.payments} className="btn btn-sm btn-outline-primary">View All</A></div>
          <div className="card-body" style={{ padding: 0 }}><table className="data-table"><tbody>
            {d.recent_payments.length ? d.recent_payments.map((p, i) => (
              <tr key={i}>
                <td><A to={p.detail_url}>{p.student_name.slice(0, 20)}{p.student_name.length > 20 ? '…' : ''}</A></td>
                <td><strong>{money(p.amount)}</strong></td>
                <td><small className="text-muted">{p.date_short}</small></td>
              </tr>
            )) : <tr><td colSpan="3" className="text-center text-muted">No payments yet</td></tr>}
          </tbody></table></div>
        </div></div>
        <div className="col-md-6"><div className="card h-100">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-trophy" /> Top Contributors</h3></div>
          <div className="card-body" style={{ padding: 0 }}><table className="data-table"><tbody>
            {d.top_contributors.length ? d.top_contributors.map((st, i) => (
              <tr key={i}>
                <td><span className={`rank-badge ${i < 3 ? `top-${i + 1}` : ''}`}>{i + 1}</span>
                  <A to={st.detail_url}>{st.name.slice(0, 18)}{st.name.length > 18 ? '…' : ''}</A></td>
                <td><strong>{money(st.total_paid)}</strong></td>
                <td>{st.total_paid >= s.max_due ? <span className="badge badge-success"><i aria-hidden="true" className="fas fa-check" /></span> : <small className="text-muted">{(st.total_paid / s.max_due * 100).toFixed(0)}%</small>}</td>
              </tr>
            )) : <tr><td colSpan="3" className="text-center text-muted">No payments yet</td></tr>}
          </tbody></table></div>
        </div></div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3><i aria-hidden="true" className="fas fa-users" /> All Students ({d.students.length})</h3>
          <div className="filter-group">
            <input type="text" className="form-control" placeholder="Search students..." style={{ width: 200 }} value={search} onChange={(e) => setSearch(e.target.value)} />
            <select className="form-control" style={{ width: 120 }} value={arm} onChange={(e) => setArm(e.target.value)}>
              <option value="">All Arms</option><option>Iris</option><option>Rose</option><option>Lily</option><option>Daisy</option>
            </select>
            <select className="form-control" style={{ width: 120 }} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All Status</option><option value="Paid">Paid</option><option value="Ongoing">Ongoing</option>
            </select>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table">
            <thead><tr><th>#</th><th>Name</th><th>Arm</th><th>Paid</th><th>Remaining</th><th>Progress</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {shown.map((st, i) => (
                <tr key={st.id}>
                  <td>{i + 1}</td>
                  <td><strong>{st.name}</strong></td>
                  <td>{st.arm ? <span className={`badge badge-${armColor(st.arm)}`}>{st.arm}</span> : <span className="text-muted">—</span>}</td>
                  <td><strong>{money(st.total_paid)}</strong></td>
                  <td>{st.remaining > 0 ? <span className="text-danger">{money(st.remaining)}</span> : <span className="text-success">-</span>}</td>
                  <td style={{ width: 100 }}>
                    <Bar pct={st.percentage} color={st.percentage >= 100 ? 'var(--success)' : st.percentage >= 50 ? 'var(--warning)' : 'var(--danger)'} />
                    <small className="text-muted">{st.percentage.toFixed(0)}%</small>
                  </td>
                  <td>{st.status === 'Paid' ? <span className="badge badge-success"><i aria-hidden="true" className="fas fa-check" /> Paid</span> : <span className="badge badge-warning">Owing</span>}</td>
                  <td>
                    <A to={st.detail_url} className="btn btn-sm btn-info" title="View"><i aria-hidden="true" className="fas fa-eye" /></A>{' '}
                    <A to={st.add_payment_url} className="btn btn-sm btn-success" title="Add Payment"><i aria-hidden="true" className="fas fa-plus" /></A>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ---- Quick entry ------------------------------------------------------------
function QuickEntry({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [date, setDate] = useState(d.today);
  const [receivedBy, setReceivedBy] = useState('');
  // Recover a half-entered batch of amounts if the page is reloaded/navigated away.
  const [amounts, setAmounts, clearAmounts] = useDraft('contrib-quick-entry', {});
  const [search, setSearch] = useState('');
  const [arm, setArm] = useState('');
  const [statusF, setStatusF] = useState('');
  const setAmt = (id, v) => setAmounts((a) => ({ ...a, [id]: v }));
  const shown = d.students.filter((s) =>
    s.name.toLowerCase().includes(search.toLowerCase()) && (!arm || s.arm === arm)
    && (!statusF || (statusF === 'owing' && s.remaining > 0) || (statusF === 'paid' && s.remaining <= 0)));
  const entered = Object.entries(amounts).filter(([, v]) => parseFloat(v) > 0);
  const total = entered.reduce((t, [, v]) => t + parseFloat(v), 0);
  const submit = (e) => {
    e.preventDefault();
    const fields = { payment_date: date, received_by: receivedBy };
    entered.forEach(([id, v]) => { fields[`amount_${id}`] = v; });
    save(d.submit_url, fields, () => { clearAmounts(); setAmounts({}); nav.refresh(); });
  };
  const clear = () => { clearAmounts(); setAmounts({}); };
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-bolt" /> Quick Payment Entry</h1>
        <A to={d.urls.dashboard} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A></div>
      <div className="card mb-3">
        <div className="card-header"><h3>Enter Multiple Payments</h3></div>
        <div className="card-body">
          <p className="text-muted mb-3">Set the date and receiver, then enter amounts for students who paid.</p>
          <form onSubmit={submit}>
            <div className="row mb-3">
              <div className="col-md-4"><label className="form-label">Payment Date *</label>
                <input type="date" className="form-control" value={date} onChange={(e) => setDate(e.target.value)} required /></div>
              <div className="col-md-4"><label className="form-label">Received By</label>
                <input type="text" className="form-control" placeholder="Name of collector" value={receivedBy} onChange={(e) => setReceivedBy(e.target.value)} /></div>
            </div>
            <div className="row mb-3">
              <div className="col-md-4"><input type="text" className="form-control" placeholder="🔍 Search student..." value={search} onChange={(e) => setSearch(e.target.value)} /></div>
              <div className="col-md-4"><select className="form-control" value={arm} onChange={(e) => setArm(e.target.value)}>
                <option value="">All Arms</option><option>Iris</option><option>Rose</option><option>Lily</option><option>Daisy</option></select></div>
              <div className="col-md-4"><select className="form-control" value={statusF} onChange={(e) => setStatusF(e.target.value)}>
                <option value="">All Status</option><option value="owing">Owing Only</option><option value="paid">Fully Paid</option></select></div>
            </div>
            <div className="students-grid">
              {shown.map((s) => {
                const has = parseFloat(amounts[s.id]) > 0;
                return (
                  <div className={`student-entry ${has ? 'has-amount' : ''}`} key={s.id}>
                    <div className="student-info">
                      <span className="student-name">{s.name}</span>
                      {s.arm && <span className={`badge badge-${armColor(s.arm)}`}>{s.arm}</span>}
                      {s.remaining <= 0 && <span className="badge badge-success"><i aria-hidden="true" className="fas fa-check" /></span>}
                    </div>
                    <div className="student-status"><small>Paid: {money(s.total_paid)} | Rem: {money(s.remaining)}</small></div>
                    <div className="student-input">
                      <input type="number" className="form-control" placeholder="₦ Amount" min="0" step="1"
                        value={amounts[s.id] || ''} onChange={(e) => setAmt(s.id, e.target.value)} />
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="entry-summary">
              <div className="summary-item"><span>Students:</span><strong>{entered.length}</strong></div>
              <div className="summary-item"><span>Total:</span><strong>{money(total)}</strong></div>
            </div>
            <div className="form-actions">
              <button type="submit" className="btn btn-success btn-lg"><i aria-hidden="true" className="fas fa-save" /> Save All Payments</button>
              <button type="button" className="btn btn-secondary" onClick={clear}><i aria-hidden="true" className="fas fa-eraser" /> Clear</button>
              <A to={d.urls.dashboard} className="btn btn-outline-secondary"><i aria-hidden="true" className="fas fa-times" /> Cancel</A>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

// ---- Add payment ------------------------------------------------------------
function AddPayment({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [studentId, setStudentId] = useState(d.preselect ? String(d.preselect) : '');
  const [amount, setAmount] = useState('');
  const [date, setDate] = useState(d.today);
  const [receivedBy, setReceivedBy] = useState('');
  const [notes, setNotes] = useState('');
  const [info, setInfo] = useState(null);
  const loadInfo = async (id) => {
    if (!id) { setInfo(null); return; }
    try {
      const res = await fetch(d.info_url_base.replace(/0$/, id), { headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' });
      setInfo(await res.json());
    } catch (_) { setInfo(null); }
  };
  React.useEffect(() => { if (d.preselect) loadInfo(d.preselect); }, []);
  const onStudent = (e) => { setStudentId(e.target.value); loadInfo(e.target.value); };
  const submit = (e) => {
    e.preventDefault();
    save(d.submit_url, { student_id: studentId, amount, payment_date: date, received_by: receivedBy, notes },
      (r) => nav.go(r.redirect || d.urls.dashboard));
  };
  const quick = [100, 200, 500, 1000, 2000, 5000];
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-plus-circle" /> Add Payment</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Student *</label>
          <select className="form-control" value={studentId} onChange={onStudent} required>
            <option value="">Select Student</option>
            {d.students.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select></div>
        {info && (
          <div style={{ marginBottom: '1rem', padding: '1rem', background: 'var(--gray-50)', borderRadius: 8 }}>
            <div className="info-row"><span>Total Paid:</span> <strong>{money(info.total_paid)}</strong></div>
            <div className="info-row"><span>Remaining:</span> <strong>{money(info.remaining)}</strong></div>
          </div>
        )}
        <div className="form-group"><label className="form-label">Amount (₦) *</label>
          <input type="number" className="form-control" required min="1" step="1" placeholder="Enter amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <div style={{ marginTop: '0.5rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {quick.map((q) => <button type="button" key={q} className="btn btn-sm btn-outline-secondary" onClick={() => setAmount(String(q))}>₦{q.toLocaleString()}</button>)}
          </div></div>
        <div className="form-group"><label className="form-label">Payment Date *</label>
          <input type="date" className="form-control" value={date} onChange={(e) => setDate(e.target.value)} required /></div>
        <div className="form-group"><label className="form-label">Received By</label>
          <input type="text" className="form-control" placeholder="Name of person who received payment" value={receivedBy} onChange={(e) => setReceivedBy(e.target.value)} /></div>
        <div className="form-group"><label className="form-label">Notes</label>
          <textarea className="form-control" rows="2" placeholder="Any additional notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Payment</button>
          <A to={d.urls.dashboard} className="btn btn-secondary">Cancel</A>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Payments list ----------------------------------------------------------
function PaymentsList({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const del = async (p) => { if (await confirm('Delete this payment?')) save(p.delete_url, {}, () => nav.refresh()); };
  const onFilter = (e) => { const v = e.target.value; nav.go(v ? `${d.urls.payments}?date=${v}` : d.urls.payments); };
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-list" /> All Payments</h1>
        <A to={d.urls.quick_entry} className="btn btn-success"><i aria-hidden="true" className="fas fa-plus" /> Add Payments</A></div>
      <div className="card mb-3"><div className="card-body">
        <div className="filter-group">
          <div className="form-group"><label className="form-label">Filter by Date</label>
            <select className="form-control" value={d.filter_date || ''} onChange={onFilter}>
              <option value="">All Dates</option>
              {d.unique_dates.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
            </select></div>
        </div>
      </div></div>
      <div className="card">
        <div className="card-header"><h3>Payments ({d.payments.length})</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table">
            <thead><tr><th>#</th><th>Date</th><th>Student</th><th>Amount</th><th>Received By</th><th>Notes</th><th>Actions</th></tr></thead>
            <tbody>
              {d.payments.length ? d.payments.map((p, i) => (
                <tr key={p.id}>
                  <td>{i + 1}</td><td>{p.date}</td>
                  <td><A to={p.detail_url}>{p.student_name}</A></td>
                  <td><strong>{money(p.amount)}</strong></td>
                  <td>{p.received_by}</td><td>{p.notes}</td>
                  <td><button type="button" className="btn btn-sm btn-danger" title="Delete" onClick={() => del(p)}><i aria-hidden="true" className="fas fa-trash" /></button></td>
                </tr>
              )) : <tr><td colSpan="7" className="text-center text-muted">No payments found</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ---- Expenses list ----------------------------------------------------------
function Expenses({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const u = d.urls;
  const del = async (e) => { if (await confirm('Delete this expense?')) save(e.delete_url, {}, () => nav.refresh()); };
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-receipt" /> Expenses Management</h1>
        <div className="header-actions">
          <A to={u.dashboard} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A>
          <A to={u.add_expense} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Expense</A>
        </div></div>
      <div className="stats-grid mb-3">
        <Stat icon="fa-hand-holding-usd" tone="success" value={money(d.total_collected)} label="Total Collected" />
        <Stat icon="fa-money-bill-wave" tone="danger" value={money(d.total_expenses)} label="Total Spent" />
        <Stat icon="fa-wallet" tone={d.available_balance >= 0 ? 'info' : 'danger'} value={money(d.available_balance)} label="Available Balance" />
        <Stat icon="fa-percentage" tone="warning" value={`${d.expense_rate.toFixed(1)}%`} label="Expense Rate" />
      </div>
      <div className="card mb-3"><div className="card-body">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <span><strong>Fund Utilization</strong></span>
          <span><span className="text-danger">Spent: {money(d.total_expenses)}</span> | <span className="text-success">Available: {money(d.available_balance)}</span></span>
        </div>
        <div style={{ background: 'var(--border-color)', borderRadius: 10, height: 24, overflow: 'hidden', display: 'flex' }}>
          <div style={{ background: 'var(--danger)', height: '100%', width: `${d.expense_rate}%` }} />
          <div style={{ background: 'var(--success)', height: '100%', width: `${100 - d.expense_rate}%` }} />
        </div>
      </div></div>
      {d.category_summary.length > 0 && (
        <div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-pie" /> Expenses by Category</h3></div>
          <div className="card-body">
            {d.category_summary.map((c) => (
              <div className="category-row" key={c.name}>
                <span className="category-name">{c.name}</span>
                <div className="category-bar-container"><div className="category-bar" style={{ width: `${d.total_expenses > 0 ? (c.amount / d.total_expenses * 100) : 0}%` }} /></div>
                <span className="category-amount">{money(c.amount)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="card">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-list" /> All Expenses ({d.expenses.length})</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table">
            <thead><tr><th>#</th><th>Date</th><th>Description</th><th>Amount</th><th>Notes</th><th>Actions</th></tr></thead>
            <tbody>
              {d.expenses.length ? d.expenses.map((e, i) => (
                <tr key={e.id}>
                  <td>{i + 1}</td><td>{e.date}</td><td><strong>{e.description}</strong></td>
                  <td><strong className="text-danger">{money(e.amount)}</strong></td>
                  <td><small>{e.notes}</small></td>
                  <td><button type="button" className="btn btn-sm btn-danger" title="Delete" onClick={() => del(e)}><i aria-hidden="true" className="fas fa-trash" /></button></td>
                </tr>
              )) : <tr><td colSpan="6" className="text-center text-muted">No expenses recorded yet</td></tr>}
            </tbody>
            {d.expenses.length > 0 && (
              <tfoot><tr style={{ background: 'var(--gray-50)', fontWeight: 'bold' }}>
                <td colSpan="3" className="text-right">Total:</td>
                <td className="text-danger">{money(d.total_expenses)}</td><td colSpan="2" />
              </tr></tfoot>
            )}
          </table>
        </div>
      </div>
    </>
  );
}

// ---- Simple forms (add expense, settings) -----------------------------------
function AddExpense({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [f, setF, clearDraft] = useDraft('contrib-add-expense', { expense_date: d.today, description: '', amount: '', notes: '' });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => { e.preventDefault(); save(d.submit_url, f, (r) => { clearDraft(); nav.go(r.redirect || d.back_url); }); };
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-plus-circle" /> Add Expense</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Date *</label><input type="date" className="form-control" value={f.expense_date} onChange={set('expense_date')} required /></div>
        <div className="form-group"><label className="form-label">Description *</label><input type="text" className="form-control" value={f.description} onChange={set('description')} required placeholder="What was this expense for?" /></div>
        <div className="form-group"><label className="form-label">Amount (₦) *</label><input type="number" className="form-control" value={f.amount} onChange={set('amount')} required min="1" step="1" placeholder="Enter amount" /></div>
        <div className="form-group"><label className="form-label">Notes</label><textarea className="form-control" rows="2" value={f.notes} onChange={set('notes')} placeholder="Any additional details" /></div>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Expense</button>
          <A to={d.back_url} className="btn btn-secondary">Cancel</A>
        </div>
      </form></div></div>
    </>
  );
}

function Settings({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [f, setF, clearDraft] = useDraft('contrib-settings', { max_due: d.max_due, start_date: d.start_date, access_code: '' }, { omit: ['access_code'] });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => { e.preventDefault(); save(d.submit_url, f, () => { clearDraft(); setF({ ...f, access_code: '' }); nav.refresh(); }); };
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-cog" /> Contribution Settings</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Maximum Due Amount (₦)</label>
          <input type="number" className="form-control" value={f.max_due} onChange={set('max_due')} min="1000" step="1000" />
          <small className="text-muted">The total amount each student is expected to pay</small></div>
        <div className="form-group"><label className="form-label">Start Date (Week 1)</label>
          <input type="date" className="form-control" value={f.start_date} onChange={set('start_date')} />
          <small className="text-muted">The date when Week 1 starts (for weekly breakdown)</small></div>
        <div className="form-group"><label className="form-label">Access Password</label>
          <input type="password" className="form-control" value={f.access_code} onChange={set('access_code')}
            placeholder={d.has_custom_code ? 'Leave blank to keep current' : 'Set a password (replaces the default)'} autoComplete="new-password" />
          <small className="text-muted">The password required to open this Contributions module. {d.has_custom_code ? 'A custom password is set.' : 'Currently using the built-in default.'} Leave blank to keep it unchanged.</small></div>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Settings</button>
          <A to={d.back_url} className="btn btn-secondary">Cancel</A>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Report by arm ----------------------------------------------------------
function Report({ d }) {
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-chart-bar" /> Report by Arm</h1></div>
      {d.arms.map((a) => {
        const pct = a.total_expected > 0 ? (a.total_paid / a.total_expected * 100) : 0;
        return (
          <div className="card mb-3" key={a.name}>
            <div className="card-header"><h3><i aria-hidden="true" className="fas fa-users" /> {a.name || 'All Students'}</h3>
              <div><span className="badge badge-primary">{a.total_students} students</span> <span className="badge badge-success">{a.fully_paid} paid</span></div></div>
            <div className="card-body">
              <div className="info-grid mb-3">
                <div className="info-row"><span>Expected:</span><strong>{money(a.total_expected)}</strong></div>
                <div className="info-row"><span>Received:</span><strong style={{ color: 'var(--success)' }}>{money(a.total_paid)}</strong></div>
                <div className="info-row"><span>Progress:</span><strong>{pct.toFixed(1)}%</strong></div>
              </div>
              <div style={{ background: 'var(--border-color)', borderRadius: 8, height: 16, overflow: 'hidden', marginBottom: '1rem' }}>
                <div style={{ background: 'linear-gradient(90deg, #1a5f4a, var(--success))', height: '100%', width: `${pct}%` }} />
              </div>
              <table className="data-table">
                <thead><tr><th>#</th><th>Name</th><th>Paid</th><th>Remaining</th><th>Status</th></tr></thead>
                <tbody>
                  {a.students.map((s, i) => (
                    <tr key={i}><td>{i + 1}</td><td>{s.name}</td><td><strong>{money(s.total_paid)}</strong></td>
                      <td>{s.remaining > 0 ? money(s.remaining) : '-'}</td>
                      <td>{s.status === 'Paid' ? <span className="badge badge-success"><i aria-hidden="true" className="fas fa-check" /> Paid</span> : <span className="badge badge-warning">Ongoing</span>}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
      <A to={d.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A>
    </>
  );
}

// ---- Defaulters -------------------------------------------------------------
function Defaulters({ d }) {
  const [arm, setArm] = useState('');
  const [sort, setSort] = useState('remaining-desc');
  const list = useMemo(() => {
    let l = d.defaulters.filter((s) => !arm || s.arm === arm);
    l = [...l].sort((a, b) => {
      switch (sort) {
        case 'remaining-asc': return a.remaining - b.remaining;
        case 'name-asc': return a.name.localeCompare(b.name);
        case 'paid-desc': return b.total_paid - a.total_paid;
        default: return b.remaining - a.remaining;
      }
    });
    return l;
  }, [d.defaulters, arm, sort]);
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-user-times" /> Defaulters List</h1>
        <div className="header-actions">
          <A to={d.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A>
          <a href={d.export_url} className="btn btn-info"><i aria-hidden="true" className="fas fa-file-excel" /> Export List</a>
        </div></div>
      <div className="stats-grid mb-3">
        <Stat icon="fa-users" tone="danger" value={d.defaulters.length} label="Total Defaulters" />
        <Stat icon="fa-coins" tone="warning" value={money(d.total_outstanding)} label="Total Outstanding" />
        <Stat icon="fa-calculator" tone="info" value={money(d.avg_outstanding)} label="Avg. Outstanding" />
      </div>
      <div className="card">
        <div className="card-header"><h3>Students with Outstanding Balance</h3>
          <div className="filter-group">
            <select className="form-control" style={{ width: 120 }} value={arm} onChange={(e) => setArm(e.target.value)}>
              <option value="">All Arms</option><option>Iris</option><option>Rose</option><option>Lily</option><option>Daisy</option></select>
            <select className="form-control" style={{ width: 150 }} value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="remaining-desc">Highest Owing</option><option value="remaining-asc">Lowest Owing</option>
              <option value="name-asc">Name A-Z</option><option value="paid-desc">Most Paid</option></select>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table">
            <thead><tr><th>#</th><th>Name</th><th>Arm</th><th>Paid</th><th>Outstanding</th><th>Progress</th><th>Last Payment</th><th>Actions</th></tr></thead>
            <tbody>
              {list.length ? list.map((s, i) => (
                <tr key={s.id}>
                  <td>{i + 1}</td><td><strong>{s.name}</strong></td>
                  <td>{s.arm ? <span className={`badge badge-${armColor(s.arm)}`}>{s.arm}</span> : <span className="text-muted">—</span>}</td>
                  <td>{money(s.total_paid)}</td>
                  <td><strong className="text-danger">{money(s.remaining)}</strong></td>
                  <td style={{ width: 100 }}><Bar pct={s.percentage} color={s.percentage >= 50 ? 'var(--warning)' : 'var(--danger)'} /><small>{s.percentage.toFixed(0)}%</small></td>
                  <td><small>{s.last_payment}</small></td>
                  <td><A to={s.detail_url} title="View" className="btn btn-sm btn-info"><i aria-hidden="true" className="fas fa-eye" /></A>{' '}
                    <A to={s.add_payment_url} title="Add payment" className="btn btn-sm btn-success"><i aria-hidden="true" className="fas fa-plus" /></A></td>
                </tr>
              )) : <tr><td colSpan="8" className="text-center text-success"><i aria-hidden="true" className="fas fa-check-circle" /> No defaulters! All students have paid in full.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ---- Daily summary ----------------------------------------------------------
function DailySummary({ d }) {
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-calendar-alt" /> Daily Collection Summary</h1>
        <A to={d.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A></div>
      <div className="stats-grid mb-3">
        <Stat icon="fa-calendar-check" tone="primary" value={d.days_count} label="Collection Days" />
        <Stat icon="fa-chart-line" tone="success" value={money(d.avg_daily)} label="Avg. Daily Collection" />
        <Stat icon="fa-arrow-up" tone="info" value={money(d.best_day ? d.best_day.amount : 0)} label={`Best Day${d.best_day ? ` (${d.best_day.date_short})` : ''}`} />
      </div>
      <div className="card">
        <div className="card-header"><h3>Collections by Date</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table">
            <thead><tr><th>Date</th><th>Day</th><th>Transactions</th><th>Amount</th><th>Collectors</th><th>Actions</th></tr></thead>
            <tbody>
              {d.daily_data.length ? d.daily_data.map((day, i) => (
                <tr key={i}>
                  <td><strong>{day.date}</strong></td><td>{day.day}</td><td>{day.count}</td>
                  <td><strong className="text-success">{money(day.amount)}</strong></td>
                  <td><small>{day.collectors}</small></td>
                  <td><A to={day.view_url} className="btn btn-sm btn-info"><i aria-hidden="true" className="fas fa-eye" /> View</A></td>
                </tr>
              )) : <tr><td colSpan="6" className="text-center text-muted">No collections recorded yet</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ---- Session history & view -------------------------------------------------
function History({ d }) {
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-history" /> Contribution History by Session</h1>
        <A to={d.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A></div>
      <div className="card">
        <div className="card-header"><h3>All Sessions with Contribution Data</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table">
            <thead><tr><th>Session</th><th>Status</th><th>Payments</th><th>Collected</th><th>Expenses</th><th>Net Balance</th><th>Actions</th></tr></thead>
            <tbody>
              {d.sessions.length ? d.sessions.map((s) => (
                <tr key={s.id}>
                  <td><strong>{s.name}</strong></td>
                  <td>{s.is_active ? <span className="badge badge-success"><i aria-hidden="true" className="fas fa-check" /> Active</span> : <span className="badge badge-secondary">Closed</span>}</td>
                  <td>{s.payment_count}</td>
                  <td className="text-success"><strong>{money(s.total_collected)}</strong></td>
                  <td className="text-danger">{money(s.total_expenses)}</td>
                  <td><strong className={s.net_balance >= 0 ? 'text-success' : 'text-danger'}>{money(s.net_balance)}</strong></td>
                  <td><A to={s.view_url} className="btn btn-sm btn-info"><i aria-hidden="true" className="fas fa-eye" /> View</A></td>
                </tr>
              )) : <tr><td colSpan="7" className="text-center text-muted">No contribution data found</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function ViewSession({ d }) {
  const s = d.session;
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-calendar-alt" /> {s.name}</h1>
        <div className="header-actions">
          {s.is_active ? <span className="badge badge-success" style={{ fontSize: '1rem', padding: '0.5rem 1rem' }}><i aria-hidden="true" className="fas fa-check" /> Active Session</span>
            : <span className="badge badge-secondary" style={{ fontSize: '1rem', padding: '0.5rem 1rem' }}>Closed Session</span>}
          <A to={d.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A>
        </div></div>
      <div className="stats-grid mb-3">
        <Stat icon="fa-users" tone="primary" value={d.student_totals.length} label="Students" />
        <Stat icon="fa-receipt" tone="info" value={d.payments_count} label="Payments" />
        <Stat icon="fa-hand-holding-usd" tone="success" value={money(d.total_collected)} label="Collected" />
        <Stat icon="fa-money-bill-wave" tone="danger" value={money(d.total_expenses)} label="Expenses" />
        <Stat icon="fa-wallet" tone={d.net_balance >= 0 ? 'success' : 'danger'} value={money(d.net_balance)} label="Net Balance" />
      </div>
      <div className="row">
        <div className="col-md-8"><div className="card">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-users" /> Student Contributions</h3></div>
          <div className="card-body" style={{ padding: 0, overflowX: 'auto', maxHeight: 500 }}>
            <table className="data-table">
              <thead><tr><th>#</th><th>Student</th><th>Payments</th><th>Total</th></tr></thead>
              <tbody>{d.student_totals.map((it, i) => (
                <tr key={i}><td>{i + 1}</td><td><strong>{it.name}</strong></td><td>{it.payment_count}</td><td><strong className="text-success">{money(it.total)}</strong></td></tr>
              ))}</tbody>
            </table>
          </div>
        </div></div>
        <div className="col-md-4"><div className="card">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-receipt" /> Expenses</h3></div>
          <div className="card-body" style={{ padding: 0, maxHeight: 500, overflowY: 'auto' }}>
            {d.expenses.length ? (
              <table className="data-table"><tbody>{d.expenses.map((e, i) => (
                <tr key={i}><td><strong>{e.description}</strong><br /><small className="text-muted">{e.date}</small></td>
                  <td className="text-danger"><strong>{money(e.amount)}</strong></td></tr>
              ))}</tbody></table>
            ) : <div className="text-center text-muted p-3">No expenses recorded</div>}
          </div>
        </div></div>
      </div>
    </>
  );
}

// ---- Student detail ---------------------------------------------------------
function StudentDetail({ d }) {
  const pct = d.max_due > 0 ? (d.total_paid / d.max_due * 100) : 0;
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-user" /> {d.student.name}</h1></div>
      <div className="stats-grid mb-3">
        <Stat icon="fa-bullseye" tone="primary" value={money(d.max_due)} label="Max Due" />
        <Stat icon="fa-hand-holding-usd" tone="success" value={money(d.total_paid)} label="Total Paid" />
        <Stat icon="fa-calculator" tone={d.remaining > 0 ? 'warning' : 'success'} value={money(d.remaining)} label="Remaining" />
        <Stat icon={d.status === 'Paid' ? 'fa-check-circle' : 'fa-clock'} tone={d.status === 'Paid' ? 'success' : 'warning'} value={d.status} label="Status" />
      </div>
      <div className="card mb-3"><div className="card-body">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}><span>Payment Progress</span><strong>{pct.toFixed(1)}%</strong></div>
        <div style={{ background: 'var(--border-color)', borderRadius: 10, height: 24, overflow: 'hidden' }}>
          <div style={{ background: pct >= 100 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)', height: '100%', width: `${Math.min(100, pct)}%` }} />
        </div>
      </div></div>
      <div className="row">
        <div className="col-md-6"><div className="card">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-history" /> Payment History</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <table className="data-table"><thead><tr><th>Date</th><th>Amount</th><th>Received By</th></tr></thead>
              <tbody>{d.payments.length ? d.payments.map((p, i) => (
                <tr key={i}><td>{p.date}</td><td><strong>{money(p.amount)}</strong></td><td>{p.received_by}</td></tr>
              )) : <tr><td colSpan="3" className="text-center text-muted">No payments yet</td></tr>}</tbody>
            </table>
          </div>
        </div></div>
        <div className="col-md-6"><div className="card">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-calendar-week" /> Weekly Breakdown</h3></div>
          <div className="card-body" style={{ padding: 0, maxHeight: 400, overflowY: 'auto' }}>
            <table className="data-table"><thead><tr><th>Week</th><th>Period</th><th>Amount</th></tr></thead>
              <tbody>{d.weekly_data.map((w, i) => (
                <tr key={i} style={w.amount > 0 ? { background: '#e8f5e9' } : undefined}>
                  <td>Week {w.week}</td><td><small>{w.period}</small></td>
                  <td>{w.amount > 0 ? <strong>{money(w.amount)}</strong> : <span className="text-muted">-</span>}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div></div>
      </div>
      <div className="mt-3"><A to={d.urls.dashboard} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A></div>
    </>
  );
}

// ---- Import -----------------------------------------------------------------
function Import({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const clearAll = async (e) => {
    e.preventDefault();
    if (await confirm('Are you sure you want to DELETE ALL contribution payments and expenses? This cannot be undone!')) {
      save(d.clear_url, {}, () => nav.refresh());
    }
  };
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-file-import" /> Import from Excel</h1></div>
      <div className="card mb-3">
        <div className="card-header"><h3>Upload Excel File</h3></div>
        <div className="card-body">
          <div className="alert alert-info">
            <h4><i aria-hidden="true" className="fas fa-info-circle" /> Expected Format</h4>
            <p>Upload your contributions Excel file with the following sheets:</p>
            <ul>
              <li><strong>Students</strong> sheet with columns: StudentID, Name, Class, Arm</li>
              <li><strong>Payments</strong> sheet with columns: PaymentID, StudentID, Name, Date, ReceivedBy, Amount</li>
            </ul>
            <p>The system will match students by name to the database and import all payment records.</p>
          </div>
          <form method="POST" action={d.submit_url} encType="multipart/form-data">
            <input type="hidden" name="_csrf_token" value={csrfToken()} />
            <div className="form-group"><label className="form-label">Select Excel File (.xlsx)</label>
              <input type="file" name="file" className="form-control" accept=".xlsx" required /></div>
            <div className="form-actions">
              <button type="submit" className="btn btn-primary btn-lg"><i aria-hidden="true" className="fas fa-upload" /> Import Payments</button>
              <A to={d.back_url} className="btn btn-secondary">Cancel</A>
            </div>
          </form>
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-exclamation-triangle" /> Danger Zone</h3></div>
        <div className="card-body">
          <p className="text-muted">Use this to clear all existing contribution data before re-importing.</p>
          <form onSubmit={clearAll}><button type="submit" className="btn btn-danger"><i aria-hidden="true" className="fas fa-trash" /> Clear All Data</button></form>
        </div>
      </div>
    </>
  );
}

const SCREENS = {
  dashboard: Dashboard, quick_entry: QuickEntry, add_payment: AddPayment,
  payments: PaymentsList, expenses: Expenses, add_expense: AddExpense,
  report: Report, defaulters: Defaulters, daily_summary: DailySummary,
  history: History, view_session: ViewSession, student_detail: StudentDetail,
  settings: Settings, import: Import,
};

export default function ContributionsApp({ data }) {
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
