import React, { useState, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { Banner, SectionShell, SectionTabs, Empty } from '../components/ui';

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'], ['record_payment', 'fa-cash-register', 'Record Payment'],
  ['payments', 'fa-receipt', 'Payments'], ['structure', 'fa-table-list', 'Fee Structure'],
  ['items', 'fa-tags', 'Fee Items'], ['expenses', 'fa-money-bill-wave', 'Expenses'],
  ['defaulters', 'fa-triangle-exclamation', 'Defaulters'], ['collections', 'fa-calendar-day', 'Collections'],
  ['reports', 'fa-chart-column', 'Reports'],
];
const TAB_FOR = { edit_payment: 'payments' };

function Tabs({ d }) {
  const nav = useNav();
  return <SectionTabs tabs={TABS} urls={d.nav} active={TAB_FOR[d.page] || d.page} go={nav.go} />;
}

const nairaShort = (n) => {
  n = Number(n) || 0;
  const s = n < 0 ? '-' : '';
  n = Math.abs(n);
  if (n >= 1e6) return s + '₦' + (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return s + '₦' + (n / 1e3).toFixed(1) + 'k';
  return s + naira(n);
};
const PALETTE = ['#4e73df', '#1cc88a', '#f6c23e', '#e74a3b', '#7e6cf0', '#11998e', '#fd7e14', '#20c997', '#6610f2', '#e83e8c'];
const chartDefaults = () => {
  if (window.Chart) window.Chart.defaults.color = getComputedStyle(document.body).getPropertyValue('--text-secondary') || '#666';
};
const balColor = (n) => (n > 0 ? 'var(--danger)' : 'var(--success)');

function TermSelect({ value, terms, onChange, label = 'Term', allLabel }) {
  return (
    <div className="form-group"><label className="form-label">{label}</label>
      <select className="form-control" value={value} onChange={(e) => onChange(e.target.value)}>
        {allLabel && <option value="">{allLabel}</option>}
        {terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
      </select></div>
  );
}

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const nav = useNav();
  const refs = { trend: useRef(), cls: useRef(), item: useRef(), method: useRef(), expense: useRef() };
  const [stepsOpen, setStepsOpen] = useState(!d.has_structure);
  useEffect(() => {
    if (!window.Chart) return;
    chartDefaults();
    const grid = 'rgba(128,128,128,.15)';
    const nairaTick = (v) => '₦' + (v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(0) + 'k' : v);
    const charts = [];
    const doughnut = (ref, rows, lk, vk) => {
      if (!ref.current || !rows.length) return;
      charts.push(new window.Chart(ref.current, { type: 'doughnut',
        data: { labels: rows.map((x) => x[lk]), datasets: [{ data: rows.map((x) => x[vk]), backgroundColor: PALETTE, borderWidth: 0 }] },
        options: { maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } }, tooltip: { callbacks: { label: (c) => ' ' + c.label + ': ₦' + c.raw.toLocaleString() } } } } }));
    };
    if (refs.trend.current && d.trend_chart.length) charts.push(new window.Chart(refs.trend.current, { type: 'line',
      data: { labels: d.trend_chart.map((x) => x.label), datasets: [{ label: 'Collected', data: d.trend_chart.map((x) => x.amount), borderColor: '#1cc88a', backgroundColor: 'rgba(28,200,138,.12)', fill: true, tension: 0.35, pointRadius: 3, borderWidth: 3 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ' ₦' + c.raw.toLocaleString() } } }, scales: { y: { beginAtZero: true, grid: { color: grid }, ticks: { callback: nairaTick } }, x: { grid: { display: false } } } } }));
    if (refs.cls.current && d.class_chart.length) charts.push(new window.Chart(refs.cls.current, { type: 'bar',
      data: { labels: d.class_chart.map((x) => x.name), datasets: [
        { label: 'Expected', data: d.class_chart.map((x) => x.expected), backgroundColor: '#cbd5e1', borderRadius: 5 },
        { label: 'Collected', data: d.class_chart.map((x) => x.collected), backgroundColor: '#1cc88a', borderRadius: 5 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } }, tooltip: { callbacks: { label: (c) => ' ' + c.dataset.label + ': ₦' + c.raw.toLocaleString() } } }, scales: { y: { beginAtZero: true, grid: { color: grid }, ticks: { callback: nairaTick } }, x: { grid: { display: false } } } } }));
    doughnut(refs.item, d.item_chart, 'name', 'amount');
    doughnut(refs.method, d.method_chart, 'method', 'amount');
    doughnut(refs.expense, d.expense_chart, 'name', 'amount');
    return () => charts.forEach((c) => c.destroy());
  }, [d]);

  const kpis = [['blue', 'fa-file-invoice-dollar', d.payable_total, 'Expected'], ['green', 'fa-coins', d.collected, 'Collected'],
    ['red', 'fa-hourglass-half', d.outstanding, 'Outstanding'], ['amber', 'fa-percent', d.rate + '%', 'Collection rate', true],
    ['orange', 'fa-money-bill-wave', d.expenses, 'Expenses'], [d.net >= 0 ? 'teal' : 'red', 'fa-scale-balanced', d.net, 'Net (cash)']];

  return (
    <>
      <div className="page-header"><h1>Finance &amp; Fees</h1>
        <div className="page-header-actions">
          <a href={d.urls.record_payment} className="btn btn-primary"><i className="fas fa-cash-register" /> Record Payment</a>
          <a href={d.urls.defaulters} className="btn btn-secondary"><i className="fas fa-triangle-exclamation" /> Defaulters</a>
        </div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form"><TermSelect value={d.term_id} terms={d.terms} onChange={(v) => navParams(nav.go, d.self_url, { term_id: v })} /></form>
      </div></div>

      <div className={'card mb-3 fin-steps' + (stepsOpen ? '' : ' is-collapsed')}>
        <div className="card-header" style={{ cursor: 'pointer' }} onClick={() => setStepsOpen((s) => !s)}>
          <h3><i className="fas fa-route" /> How fees work here {!d.has_structure && <span className="badge badge-warning">Start here</span>}</h3>
          <i className="fas fa-chevron-down" />
        </div>
        <div className="card-body fin-steps-body">
          <div className="steps-row">
            <a href={d.urls.items} className="step"><span className="step-n">1</span><span className="step-t"><strong>Create fee items</strong><span className="text-muted text-sm">Tuition, levies, PTA — the things you charge.</span></span></a>
            <i className="fas fa-arrow-right step-arrow" />
            <a href={d.urls.structure} className="step"><span className="step-n">2</span><span className="step-t"><strong>Set the fee structure</strong><span className="text-muted text-sm">How much each class pays this term.</span></span></a>
            <i className="fas fa-arrow-right step-arrow" />
            <a href={d.urls.record_payment} className="step"><span className="step-n">3</span><span className="step-t"><strong>Record payments</strong><span className="text-muted text-sm">Search a student, enter what they paid, print the receipt.</span></span></a>
          </div>
          <p className="text-muted text-sm mb-0 mt-2"><i className="fas fa-circle-info" /> Each student's bill, balance and the figures below are worked out automatically from steps 1–2 and the payments you record.</p>
        </div>
      </div>
      {!d.has_structure && (
        <div className="card mb-3" style={{ borderColor: 'var(--warning)' }}><div className="card-body d-flex align-center gap-2 flex-wrap">
          <i className="fas fa-circle-info" style={{ color: 'var(--warning)', fontSize: '1.4rem' }} />
          <div style={{ flex: 1, minWidth: 200 }}><strong>No fee structure for {d.selected_term || 'this term'} yet.</strong>
            <div className="text-muted text-sm">Finish steps 1 &amp; 2 above to start tracking collections for this term.</div></div>
          <a href={d.urls.structure} className="btn btn-primary btn-sm">Set Fee Structure</a>
        </div></div>
      )}

      <div className="kpi-row kpi-6">{kpis.map(([c, ic, v, l, isPct]) => (
        <div className="kpi" key={l}><div className={'ic ' + c}><i className={'fas ' + ic} /></div>
          <div><div className="v" title={isPct ? '' : naira(v)}>{isPct ? v : nairaShort(v)}</div><div className="l">{l}</div></div></div>))}
      </div>

      <div className="card mb-3"><div className="card-body">
        <div className="d-flex justify-between text-sm flex-wrap gap-1"><span>{naira(d.collected)} collected of {naira(d.payable_total)}</span>
          <span>{d.defaulter_count} owing · {d.enrolled} enrolled{d.discounts ? ` · ${naira(d.discounts)} waived` : ''}</span></div>
        <div className="progress-wrap"><div className="bar" style={{ width: (d.rate <= 100 ? d.rate : 100) + '%' }} /></div>
      </div></div>

      <div className="fin-grid c2">
        <Widget title="Collection trend" icon="fa-chart-line">{d.trend_chart.length ? <canvas ref={refs.trend} /> : <Empty icon="fa-chart-line" title=""><p>No payments yet</p></Empty>}</Widget>
        <Widget title="Expected vs Collected by class" icon="fa-school">{d.class_chart.length ? <canvas ref={refs.cls} /> : <Empty icon="fa-school" title=""><p>No fee structure set</p></Empty>}</Widget>
      </div>
      <div className="fin-grid c3">
        <Widget title="Income mix (by fee)" icon="fa-layer-group">{d.item_chart.length ? <canvas ref={refs.item} /> : <Empty icon="fa-layer-group" title=""><p>No fee structure</p></Empty>}</Widget>
        <Widget title="Payment methods" icon="fa-wallet">{d.method_chart.length ? <canvas ref={refs.method} /> : <Empty icon="fa-wallet" title=""><p>No payments yet</p></Empty>}</Widget>
        <Widget title="Expenses by category" icon="fa-money-bill-trend-up">{d.expense_chart.length ? <canvas ref={refs.expense} /> : <Empty icon="fa-money-bill-wave" title=""><p>No expenses recorded</p></Empty>}</Widget>
      </div>

      <div className="widget">
        <div className="wh"><h3><i className="fas fa-receipt" /> Recent payments</h3><a href={d.urls.payments} className="text-sm">View all</a></div>
        <div className="wb" style={{ padding: 0 }}>
          {d.recent.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Date</th><th>Student</th><th>Receipt</th><th>Method</th><th className="text-right">Amount</th></tr></thead>
              <tbody>{d.recent.map((p) => (
                <tr key={p.id}><td data-label="Date">{p.date}</td><td data-label="Student">{p.student}</td>
                  <td data-label="Receipt"><a href={p.receipt_url} data-native>{p.receipt_no}</a></td>
                  <td data-label="Method"><span className="badge badge-info">{p.method}</span></td>
                  <td data-label="Amount" className="text-right">{naira(p.amount)}</td></tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-receipt" title="" style={{ padding: '1.5rem' }}><p>No payments recorded for this term</p></Empty>}
        </div>
      </div>
    </>
  );
}

function Widget({ title, icon, children }) {
  return (
    <div className="widget"><div className="wh"><h3><i className={'fas ' + icon} /> {title}</h3></div>
      <div className="wb"><div className="chart-box">{children}</div></div></div>
  );
}

// ---- Fee items -------------------------------------------------------------
function Items({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ name: '', description: '' });
  const [editing, setEditing] = useState(null);
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const add = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify('error', 'Fee item name is required.'); return; }
    const r = await submitJson(d.add_url, f);
    if (r.ok) { setF({ name: '', description: '' }); notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not add.');
  };
  return (
    <>
      <div className="page-header"><h1>Fee Items</h1>
        <div className="page-header-actions"><a href={d.structure_url} className="btn btn-secondary"><i className="fas fa-table-list" /> Fee Structure</a></div>
      </div>
      <Tabs d={d} />
      {d.is_admin && (
        <div className="card mb-3"><div className="card-header"><h3><i className="fas fa-plus" /> Add Fee Item</h3></div>
          <div className="card-body"><form onSubmit={add} className="d-flex gap-2 align-end flex-wrap">
            <div className="form-group mb-0" style={{ flex: 1, minWidth: 180 }}><label className="form-label">Name <span className="required">*</span></label>
              <input type="text" className="form-control" placeholder="e.g., Tuition, Development Levy, PTA" required value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
            <div className="form-group mb-0" style={{ flex: 2, minWidth: 200 }}><label className="form-label">Description</label>
              <input type="text" className="form-control" placeholder="Optional note" value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
            <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Add</button>
          </form></div></div>
      )}
      <div className="card"><div className="card-header"><h3>Items ({d.items.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.items.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Name</th><th>Description</th><th>Status</th>{d.is_admin && <th>Actions</th>}</tr></thead>
              <tbody>{d.items.map((it) => (
                <React.Fragment key={it.id}>
                  <tr>
                    <td data-label="Name"><strong>{it.name}</strong></td>
                    <td data-label="Description" className="text-muted">{it.description || '—'}</td>
                    <td data-label="Status">{it.is_active ? <span className="badge badge-success">Active</span> : <span className="badge badge-secondary">Inactive</span>}</td>
                    {d.is_admin && <td className="actions"><div className="d-flex gap-1">
                      <button className="btn btn-secondary btn-sm" onClick={() => setEditing(editing === it.id ? null : it.id)}><i className="fas fa-edit" /></button>
                      <button className="btn btn-danger btn-sm" onClick={() => act(it.delete_url, {}, `Delete fee item ${it.name}?`)}><i className="fas fa-trash" /></button>
                    </div></td>}
                  </tr>
                  {d.is_admin && editing === it.id && (
                    <tr><td colSpan={4} className="stack-full" style={{ background: 'var(--gray-50)' }}>
                      <ItemEdit it={it} notify={notify} onDone={() => { setEditing(null); nav.refresh(); }} />
                    </td></tr>)}
                </React.Fragment>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-tags" title="No fee items yet"><p>Add the fees your school charges to get started.</p></Empty>}
        </div></div>
    </>
  );
}

function ItemEdit({ it, notify, onDone }) {
  const [f, setF] = useState({ name: it.name, description: it.description, is_active: it.is_active });
  const submit = async (e) => {
    e.preventDefault();
    const r = await submitJson(it.edit_url, { ...f, is_active: f.is_active ? 'on' : '' });
    if (r.ok) onDone(); else notify('error', r.error || 'Could not update.');
  };
  return (
    <form onSubmit={submit} className="d-flex gap-2 align-end flex-wrap">
      <div className="form-group mb-0" style={{ flex: 1, minWidth: 160 }}><label className="form-label">Name</label><input type="text" className="form-control" value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
      <div className="form-group mb-0" style={{ flex: 2, minWidth: 200 }}><label className="form-label">Description</label><input type="text" className="form-control" value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
      <label className="form-check mb-0"><input type="checkbox" checked={f.is_active} onChange={(e) => setF((s) => ({ ...s, is_active: e.target.checked }))} /> Active</label>
      <button type="submit" className="btn btn-primary btn-sm"><i className="fas fa-save" /> Update</button>
    </form>
  );
}

// ---- Fee structure ---------------------------------------------------------
function Structure({ d, notify }) {
  const nav = useNav();
  const [amounts, setAmounts] = useState(() => { const m = {}; d.items.forEach((i) => { m[i.id] = i.amount === '' ? '' : String(i.amount); }); return m; });
  const [copyFrom, setCopyFrom] = useState('');
  useEffect(() => { const m = {}; d.items.forEach((i) => { m[i.id] = i.amount === '' ? '' : String(i.amount); }); setAmounts(m); }, [d.items]);
  const total = d.items.reduce((t, i) => t + (parseFloat(amounts[i.id]) || 0), 0);
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, arm_id: d.arm_id, ...extra });
  const save = async (e) => {
    e.preventDefault();
    const fields = { term_id: d.term_id, class_id: d.class_id, arm_id: d.arm_id || '' };
    d.items.forEach((i) => { fields['amount_' + i.id] = amounts[i.id]; });
    const r = await submitJson(d.urls.save, fields);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const clear = async () => {
    if (!window.confirm("Remove ALL fee amounts for this class this term?")) return;
    const r = await submitJson(d.urls.clear, { term_id: d.term_id, class_id: d.class_id, arm_id: d.arm_id || '' });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not clear.');
  };
  const copy = async (e) => {
    e.preventDefault();
    if (!copyFrom) { notify('error', 'Select a source term.'); return; }
    if (!window.confirm('Copy the whole fee structure into this term? Existing rows are kept.')) return;
    const r = await submitJson(d.urls.copy, { from_term_id: copyFrom, to_term_id: d.term_id });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not copy.');
  };
  return (
    <>
      <div className="page-header"><h1>Fee Structure</h1>
        <div className="page-header-actions"><a href={d.items_url} className="btn btn-secondary"><i className="fas fa-tags" /> Fee Items</a></div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form">
          <TermSelect value={d.term_id} terms={d.terms} onChange={(v) => go({ term_id: v })} />
          <div className="form-group"><label className="form-label">Class</label>
            <select className="form-control" value={d.class_id} onChange={(e) => go({ class_id: e.target.value })}>
              <option value="">Select Class</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Arm <span className="text-muted text-sm">(optional)</span></label>
            <select className="form-control" value={d.arm_id} onChange={(e) => go({ arm_id: e.target.value })}>
              <option value="">All arms</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
        </form>
        <p className="text-muted text-sm mb-0 mt-2"><i className="fas fa-circle-info" /> Leave <strong>All arms</strong> selected to charge every arm of the class the same. Set an arm only if that arm pays a different amount — arm-specific amounts override the all-arms figure.</p>
      </div></div>

      {d.term_id && d.class_id ? (d.items.length ? (<>
        <form onSubmit={save}>
          <div className="card"><div className="card-header"><h3>Amounts per student</h3><span className="badge badge-primary">Total: {naira(total)}</span></div>
            <div className="card-body"><div className="fee-rows">
              {d.items.map((it) => (
                <div className="fee-row" key={it.id}>
                  <label className="fee-name"><strong>{it.name}</strong>{it.description && <span className="text-muted text-sm d-block">{it.description}</span>}</label>
                  <div className="fee-amt"><span className="fee-cur">₦</span>
                    <input type="number" className="form-control" inputMode="decimal" min="0" step="100" placeholder="0"
                           value={amounts[it.id]} onChange={(e) => setAmounts((m) => ({ ...m, [it.id]: e.target.value }))} /></div>
                </div>))}
            </div>
              <div className="page-header-actions mt-3">
                {d.is_admin ? <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Save Structure</button>
                  : <p className="text-muted">Only admins can edit the fee structure.</p>}
              </div>
            </div></div>
        </form>
        {d.is_admin && d.has_current && <div className="mt-2"><button className="btn btn-danger btn-sm" onClick={clear}><i className="fas fa-trash" /> Clear this class's fees</button></div>}
      </>) : (
        <div className="card"><div className="card-body"><Empty icon="fa-tags" title="No fee items"><p>Create fee items first, then set their amounts here.</p><a href={d.items_url} className="btn btn-primary">Add Fee Items</a></Empty></div></div>
      )) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select a class"><p>Choose a term and class to set its fees.</p></Empty></div></div>
      )}

      {d.is_admin && d.term_id && (
        <div className="card mt-3" style={{ borderColor: 'var(--info)' }}><div className="card-header"><h3><i className="fas fa-copy" /> Copy structure from another term</h3></div>
          <div className="card-body"><form onSubmit={copy} className="d-flex gap-2 align-end flex-wrap">
            <div className="form-group mb-0"><label className="form-label">Copy all classes from</label>
              <select className="form-control" required value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
                <option value="">Select source term…</option>
                {d.terms.filter((t) => String(t.id) !== String(d.term_id)).map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
            <button type="submit" className="btn btn-info"><i className="fas fa-copy" /> Copy into this term</button>
          </form></div></div>
      )}
    </>
  );
}

// ---- Payments list ---------------------------------------------------------
function Payments({ d, notify }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q);
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, q, ...extra });
  const del = async (url, receipt, amount) => {
    if (!window.confirm(`Delete receipt ${receipt} (${naira(amount)})?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <div className="page-header"><h1>Payments</h1>
        <div className="page-header-actions"><a href={d.record_url} className="btn btn-primary"><i className="fas fa-cash-register" /> Record Payment</a></div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form" onSubmit={(e) => { e.preventDefault(); go(); }}>
          <TermSelect value={d.term_id} terms={d.terms} onChange={(v) => go({ term_id: v })} />
          <div className="form-group"><label className="form-label">Class</label>
            <select className="form-control" value={d.class_id} onChange={(e) => go({ class_id: e.target.value })}>
              <option value="">All Classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Search</label><input type="text" className="form-control" value={q} placeholder="Name, ID or receipt" onChange={(e) => setQ(e.target.value)} /></div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}><button type="submit" className="btn btn-secondary"><i className="fas fa-search" /></button></div>
        </form>
      </div></div>
      <div className="card"><div className="card-header"><h3>{d.payments.length} payment(s)</h3><span className="badge badge-success">Total: {naira(d.total)}</span></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.payments.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Date</th><th>Receipt</th><th>Student</th><th>Method</th><th>By</th><th className="text-right">Amount</th><th /></tr></thead>
              <tbody>{d.payments.map((p) => (
                <tr key={p.id}>
                  <td data-label="Date">{p.date}</td>
                  <td data-label="Receipt"><a href={p.receipt_url} data-native>{p.receipt_no}</a></td>
                  <td data-label="Student"><a href={p.statement_url}>{p.student}</a> <span className="text-muted text-sm">({p.student_id})</span></td>
                  <td data-label="Method"><span className="badge badge-info">{p.method}</span></td>
                  <td data-label="By" className="text-muted text-sm">{p.received_by}</td>
                  <td data-label="Amount" className="text-right"><strong>{naira(p.amount)}</strong></td>
                  <td className="actions"><div className="d-flex gap-1">
                    <a href={p.receipt_url} className="btn btn-secondary btn-sm" title="Receipt" data-native><i className="fas fa-receipt" /></a>
                    <a href={p.edit_url} className="btn btn-secondary btn-sm" title="Edit"><i className="fas fa-edit" /></a>
                    {d.is_admin && <button className="btn btn-danger btn-sm" onClick={() => del(p.delete_url, p.receipt_no, p.amount)}><i className="fas fa-trash" /></button>}
                  </div></td>
                </tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-receipt" title="No payments found"><p>Record a payment or adjust the filters.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Record payment --------------------------------------------------------
function RecordPayment({ d, notify }) {
  const nav = useNav();
  const student = d.student;
  const bill = d.bill;
  const [mode, setMode] = useState('browse');
  const goWith = (params) => navParams(nav.go, d.self_url, params);

  if (!student) {
    return (
      <>
        <div className="page-header"><h1>Record Payment</h1></div>
        <Tabs d={d} />
        <div className="card mb-3"><div className="card-header"><h3>Step 1: Find Student</h3></div>
          <div className="card-body">
            <TermSelect value={d.term_id} terms={d.terms} onChange={(v) => goWith({ term_id: v, assignment_id: d.assignment_id })} />
            <div className="seg" role="tablist">
              <button type="button" className={mode === 'browse' ? 'active' : ''} onClick={() => setMode('browse')}>Browse a class</button>
              <button type="button" className={mode === 'search' ? 'active' : ''} onClick={() => setMode('search')}>Search by name</button>
            </div>
            {mode === 'browse' ? (
              <div>
                <div className="form-group"><label className="form-label">Class / Arm</label>
                  <select className="form-control" value={d.assignment_id} onChange={(e) => goWith({ term_id: d.term_id, assignment_id: e.target.value })}>
                    <option value="">Select class &amp; arm…</option>{d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}</select></div>
                {d.assignment_id ? (d.roster.length ? (<>
                  <div className="roster">{d.roster.map((r) => (
                    <a className="roster-item" href={r.pick_url} key={r.id}>
                      <div className="who"><div className="nm">{r.full_name}</div><div className="sid">{r.student_id}</div></div>
                      <div className="bal" style={{ color: balColor(r.balance) }}>{naira(r.balance)}</div>
                      <span className="btn btn-primary btn-sm"><i className="fas fa-chevron-right" /></span>
                    </a>))}</div>
                  <p className="text-muted text-sm mt-2">Showing balances for {d.roster.length} student(s). Tap a student to record a payment.</p>
                </>) : <Empty icon="fa-users" title="" style={{ padding: '1rem' }}><p>No active students in this class arm for the selected term.</p></Empty>)
                  : <p className="text-muted text-sm"><i className="fas fa-circle-info" /> Pick a class and arm to see its students and their balances.</p>}
              </div>
            ) : (
              <StudentSearch url={d.search_url} termId={d.term_id} onPick={(id) => goWith({ student_id: id, term_id: d.term_id })} />
            )}
          </div></div>
      </>
    );
  }

  // Student selected
  return (
    <>
      <div className="page-header"><h1>Record Payment</h1></div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body d-flex justify-between align-center flex-wrap gap-2">
        <div><h2 style={{ margin: 0 }}>{student.full_name}</h2><div className="text-muted">{student.student_id}</div></div>
        <a href={d.urls.change_student} className="btn btn-secondary btn-sm"><i className="fas fa-arrow-left" /> Change student</a>
      </div></div>
      {bill ? (
        <div className="pay-grid">
          <div className="card"><div className="card-header"><h3>Bill</h3></div><div className="card-body">
            {bill.lines.length ? (<>
              {bill.lines.map((l, i) => <div className="bill-line" key={i}><span>{l.name}</span><span>{naira(l.amount)}</span></div>)}
              <div className="bill-line"><span>Total billed</span><span>{naira(bill.billed)}</span></div>
              {bill.discount > 0 && <div className="bill-line"><span>Discount / waiver</span><span>− {naira(bill.discount)}</span></div>}
              <div className="bill-line"><span>Already paid</span><span>{naira(bill.paid)}</span></div>
              <div className="bill-line total"><span>Balance</span><span style={{ color: balColor(bill.balance) }}>{naira(bill.balance)}</span></div>
            </>) : (
              <Empty icon="fa-circle-info" title="" style={{ padding: '1rem' }}><p>No fee structure for this student's class this term.</p><a href={d.urls.structure} className="btn btn-secondary btn-sm">Set fee structure</a></Empty>
            )}
            <a href={d.urls.statement} className="btn btn-secondary btn-sm mt-2"><i className="fas fa-file-lines" /> Full statement</a>
          </div></div>
          <PayForm d={d} bill={bill} student={student} notify={notify} />
        </div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-circle-info" title=""><p>This student has no active enrolment for the selected term.</p><a href={d.urls.change_student} className="btn btn-secondary btn-sm">Pick another student</a></Empty></div></div>
      )}
    </>
  );
}

function PayForm({ d, bill, student, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ amount: bill.balance > 0 ? String(bill.balance) : '', payment_date: d.today, method: d.methods[0], reference: '', received_by: '', notes: '' });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    const amt = parseFloat(f.amount);
    if (!amt || amt <= 0) { notify('error', 'Enter a positive amount.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, student_id: student.id, term_id: d.term_id });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <div className="card"><div className="card-header"><h3>Payment Details</h3></div><div className="card-body">
      <form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Amount (₦) <span className="required">*</span></label>
          <input type="number" className="form-control" inputMode="decimal" min="0" step="50" required value={f.amount} onChange={(e) => set('amount', e.target.value)} /></div>
        <div className="pay-fields two">
          <div className="form-group mb-0"><label className="form-label">Date</label><input type="date" className="form-control" value={f.payment_date} onChange={(e) => set('payment_date', e.target.value)} /></div>
          <div className="form-group mb-0"><label className="form-label">Method</label><select className="form-control" value={f.method} onChange={(e) => set('method', e.target.value)}>{d.methods.map((m) => <option key={m} value={m}>{m}</option>)}</select></div>
        </div>
        <div className="pay-fields two mt-3">
          <div className="form-group mb-0"><label className="form-label">Reference / Teller No.</label><input type="text" className="form-control" placeholder="Optional" value={f.reference} onChange={(e) => set('reference', e.target.value)} /></div>
          <div className="form-group mb-0"><label className="form-label">Received by</label><input type="text" className="form-control" placeholder="Bursar name" value={f.received_by} onChange={(e) => set('received_by', e.target.value)} /></div>
        </div>
        <div className="form-group mt-3"><label className="form-label">Notes</label><textarea className="form-control" rows="2" placeholder="Optional" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></div>
        <button type="submit" className="btn btn-primary w-100" disabled={busy}><i className="fas fa-check" /> Save &amp; Print Receipt</button>
      </form>
    </div></div>
  );
}

function StudentSearch({ url, termId, onPick }) {
  const [text, setText] = useState('');
  const [list, setList] = useState(null);
  const [open, setOpen] = useState(false);
  const tRef = useRef();
  const onInput = (v) => {
    setText(v); clearTimeout(tRef.current);
    if (v.trim().length < 2) { setList(null); setOpen(false); return; }
    tRef.current = setTimeout(async () => {
      try { const r = await fetch(url + '?term_id=' + (termId || '') + '&q=' + encodeURIComponent(v.trim()), { credentials: 'same-origin' });
        setList(await r.json()); setOpen(true); } catch (_) { /* ignore */ }
    }, 220);
  };
  return (
    <div className="form-group ac-wrap">
      <label className="form-label">Student name or ID</label>
      <input type="text" className="form-control" placeholder="Type at least 2 letters…" autoComplete="off" value={text}
             onChange={(e) => onInput(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && list && (
        <div className="ac-list">
          {list.length ? list.map((s) => (
            <div key={s.id} onMouseDown={() => onPick(s.id)}><div>{s.name}</div><div className="sid">{s.sid}{s.cls ? ' · ' + s.cls : ''}</div></div>
          )) : <div className="sid">No matches</div>}
        </div>)}
      <span className="form-hint d-block">Same-named students are shown with their class so you can tell them apart.</span>
    </div>
  );
}

// ---- Statement -------------------------------------------------------------
function Statement({ d, notify }) {
  const nav = useNav();
  const s = d.student;
  const bill = d.bill;
  const [copied, setCopied] = useState(false);
  const act = async (url, fields, confirmMsg, follow) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); follow ? nav.go(r.redirect) : nav.refresh(); }
    else notify('error', r.error || 'Action failed.');
  };
  return (
    <>
      <div className="page-header"><h1>Fee Statement</h1>
        <div className="page-header-actions">
          <a href={d.urls.record_payment} className="btn btn-primary"><i className="fas fa-cash-register" /> Record Payment</a>
          {d.pay_enabled && bill && bill.balance > 0.005 && (
            <button className="btn btn-secondary" onClick={() => act(d.urls.payment_link, { term_id: d.term_id }, null, true)}><i className="fas fa-link" /> Online Payment Link</button>)}
        </div>
      </div>
      <Tabs d={d} />
      {d.paylink && (
        <div className="card mb-3"><div className="card-body">
          <strong><i className="fas fa-link" /> Share this secure payment link with the parent:</strong>
          <div style={{ display: 'flex', gap: '.5rem', marginTop: '.5rem', flexWrap: 'wrap' }}>
            <input className="form-control" value={d.paylink} readOnly style={{ flex: 1, minWidth: 240 }} />
            <button className="btn btn-primary" onClick={() => { navigator.clipboard.writeText(d.paylink); setCopied(true); }}><i className={'fas ' + (copied ? 'fa-check' : 'fa-copy')} /> {copied ? 'Copied' : 'Copy'}</button>
            <a className="btn btn-success" href={d.paylink} target="_blank" rel="noopener"><i className="fas fa-up-right-from-square" /> Open</a>
          </div>
          <p className="text-muted text-sm mt-2">The payment is recorded automatically once completed.</p>
        </div></div>
      )}
      <div className="card mb-3"><div className="card-body d-flex justify-between align-center flex-wrap gap-2">
        <div><h2 style={{ margin: 0 }}>{s.full_name}</h2><div className="text-muted">{s.student_id}{s.gender && ` · ${s.gender}`}</div></div>
        <TermSelect value={d.term_id} terms={d.terms} onChange={(v) => navParams(nav.go, d.self_url, { term_id: v })} />
      </div></div>

      {bill ? (<>
        <div className="two-col">
          <div className="card"><div className="card-header"><h3>Bill</h3></div><div className="card-body">
            {bill.lines.length ? (
              <table className="data-table no-mobile-scroll" style={{ width: '100%' }}><tbody>
                {bill.lines.map((l, i) => <tr key={i}><td>{l.name}</td><td className="text-right">{naira(l.amount)}</td></tr>)}
                <tr><td><strong>Total billed</strong></td><td className="text-right"><strong>{naira(bill.billed)}</strong></td></tr>
                {bill.discount > 0 && <tr><td>Discount / waiver</td><td className="text-right">− {naira(bill.discount)}</td></tr>}
                <tr><td>Paid</td><td className="text-right">{naira(bill.paid)}</td></tr>
                <tr><td><strong>Balance</strong></td><td className="text-right"><strong style={{ color: balColor(bill.balance) }}>{naira(bill.balance)}</strong></td></tr>
              </tbody></table>
            ) : <Empty icon="fa-circle-info" title="" style={{ padding: '1rem' }}><p>No fee structure set for this student's class this term.</p></Empty>}
          </div></div>
          <div className="card"><div className="card-header"><h3>Payments ({d.payments.length})</h3></div>
            <div className="card-body" style={{ padding: 0 }}>
              {d.payments.length ? (
                <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
                  <thead><tr><th>Date</th><th>Receipt</th><th>Method</th><th className="text-right">Amount</th><th /></tr></thead>
                  <tbody>{d.payments.map((p) => (
                    <tr key={p.id}><td data-label="Date">{p.date}</td><td data-label="Receipt"><a href={p.receipt_url} data-native>{p.receipt_no}</a></td>
                      <td data-label="Method"><span className="badge badge-info">{p.method}</span></td><td data-label="Amount" className="text-right">{naira(p.amount)}</td>
                      <td className="actions"><a href={p.edit_url} className="btn btn-secondary btn-sm" title="Edit"><i className="fas fa-edit" /></a></td></tr>))}</tbody>
                </table></div>
              ) : <Empty icon="fa-receipt" title="" style={{ padding: '1rem' }}><p>No payments yet</p></Empty>}
            </div></div>
        </div>
        {d.is_admin && <Discounts d={d} act={act} />}
      </>) : (
        <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title=""><p>Select a term.</p></Empty></div></div>
      )}
    </>
  );
}

function Discounts({ d, act }) {
  const [f, setF] = useState({ amount: '', reason: '' });
  const [editing, setEditing] = useState(null);
  return (
    <div className="card mt-3"><div className="card-header"><h3><i className="fas fa-tag" /> Discounts / Waivers</h3></div>
      <div className="card-body">
        {d.discounts.length > 0 && (
          <table className="data-table table-stack no-mobile-scroll mb-3">
            <thead><tr><th>Reason</th><th className="text-right">Amount</th><th /></tr></thead>
            <tbody>{d.discounts.map((dc) => (
              <React.Fragment key={dc.id}>
                <tr>
                  <td data-label="Reason">{dc.reason || '—'}</td>
                  <td data-label="Amount" className="text-right">{naira(dc.amount)}</td>
                  <td className="actions"><div className="d-flex gap-1 justify-end">
                    <button className="btn btn-secondary btn-sm" onClick={() => setEditing(editing === dc.id ? null : dc.id)}><i className="fas fa-edit" /></button>
                    <button className="btn btn-danger btn-sm" onClick={() => act(dc.delete_url, {}, 'Remove this discount?')}><i className="fas fa-trash" /></button>
                  </div></td>
                </tr>
                {editing === dc.id && (
                  <tr><td colSpan={3} className="stack-full" style={{ background: 'var(--gray-50)' }}>
                    <DiscountEdit dc={dc} act={act} />
                  </td></tr>)}
              </React.Fragment>))}</tbody>
          </table>)}
        <form onSubmit={(e) => { e.preventDefault(); act(d.urls.add_discount, { ...f, student_id: d.student_id, term_id: d.term_id }); }} className="d-flex gap-2 align-end flex-wrap">
          <div className="form-group mb-0"><label className="form-label">Amount (₦)</label><input type="number" className="form-control" min="0" step="100" required value={f.amount} onChange={(e) => setF((s) => ({ ...s, amount: e.target.value }))} /></div>
          <div className="form-group mb-0" style={{ flex: 1, minWidth: 200 }}><label className="form-label">Reason</label><input type="text" className="form-control" placeholder="e.g., Sibling discount, Staff ward, Scholarship" value={f.reason} onChange={(e) => setF((s) => ({ ...s, reason: e.target.value }))} /></div>
          <button type="submit" className="btn btn-secondary"><i className="fas fa-plus" /> Add Discount</button>
        </form>
      </div></div>
  );
}

function DiscountEdit({ dc, act }) {
  const [f, setF] = useState({ amount: String(dc.amount), reason: dc.reason });
  return (
    <form onSubmit={(e) => { e.preventDefault(); act(dc.edit_url, f); }} className="d-flex gap-2 align-end flex-wrap">
      <div className="form-group mb-0"><label className="form-label">Amount (₦)</label><input type="number" className="form-control" min="0" step="100" required value={f.amount} onChange={(e) => setF((s) => ({ ...s, amount: e.target.value }))} /></div>
      <div className="form-group mb-0" style={{ flex: 1, minWidth: 180 }}><label className="form-label">Reason</label><input type="text" className="form-control" value={f.reason} onChange={(e) => setF((s) => ({ ...s, reason: e.target.value }))} /></div>
      <button type="submit" className="btn btn-primary btn-sm"><i className="fas fa-save" /> Update</button>
    </form>
  );
}

// ---- Defaulters ------------------------------------------------------------
function Defaulters({ d }) {
  const nav = useNav();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, ...extra });
  return (
    <>
      <div className="page-header"><h1>Outstanding Fees</h1>
        {d.rows.length > 0 && <div className="page-header-actions"><a href={d.message_url} className="btn btn-primary"><i className="fab fa-whatsapp" /> Message defaulters</a></div>}
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body"><form className="filter-form">
        <TermSelect value={d.term_id} terms={d.terms} onChange={(v) => go({ term_id: v })} />
        <div className="form-group"><label className="form-label">Class</label>
          <select className="form-control" value={d.class_id} onChange={(e) => go({ class_id: e.target.value })}>
            <option value="">All Classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      </form></div></div>
      <div className="kpi-summary card mb-3"><div className="card-body d-flex justify-between flex-wrap gap-2">
        <div><div className="text-muted text-sm">Students owing</div><strong style={{ fontSize: '1.3rem' }}>{d.rows.length}</strong></div>
        <div><div className="text-muted text-sm">Total billed (owing)</div><strong style={{ fontSize: '1.3rem' }}>{naira(d.totals.billed)}</strong></div>
        <div><div className="text-muted text-sm">Paid so far</div><strong style={{ fontSize: '1.3rem' }}>{naira(d.totals.paid)}</strong></div>
        <div><div className="text-muted text-sm">Outstanding</div><strong style={{ fontSize: '1.3rem', color: 'var(--danger)' }}>{naira(d.totals.balance)}</strong></div>
      </div></div>
      <div className="card"><div className="card-header"><h3>Defaulters</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.rows.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Student</th><th>Class</th><th className="text-right">Payable</th><th className="text-right">Paid</th><th className="text-right">Balance</th><th /></tr></thead>
              <tbody>{d.rows.map((r, i) => (
                <tr key={i}>
                  <td data-label="Student">{r.student} <span className="text-muted text-sm">({r.student_id})</span></td>
                  <td data-label="Class">{r.class_name}{r.arm_name && ` ${r.arm_name}`}</td>
                  <td data-label="Payable" className="text-right">{naira(r.billed)}</td>
                  <td data-label="Paid" className="text-right">{naira(r.paid)}</td>
                  <td data-label="Balance" className="text-right"><strong style={{ color: 'var(--danger)' }}>{naira(r.balance)}</strong></td>
                  <td className="actions text-right"><div className="d-flex gap-1 justify-end">
                    <a href={r.statement_url} className="btn btn-secondary btn-sm" title="Statement"><i className="fas fa-file-lines" /></a>
                    <a href={r.record_url} className="btn btn-primary btn-sm" title="Record payment"><i className="fas fa-cash-register" /></a>
                  </div></td>
                </tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-circle-check" title="No outstanding fees"><p>Every enrolled student has cleared their bill for this selection.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Collections -----------------------------------------------------------
function Collections({ d }) {
  const nav = useNav();
  const ref = useRef();
  useEffect(() => {
    if (!ref.current || !window.Chart || !d.day_chart.length) return;
    chartDefaults();
    const chart = new window.Chart(ref.current, { type: 'bar',
      data: { labels: d.day_chart.map((x) => x.label), datasets: [{ label: 'Collected', data: d.day_chart.map((x) => x.amount), backgroundColor: '#1cc88a', borderRadius: 5 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ' ₦' + c.raw.toLocaleString() } } }, scales: { y: { beginAtZero: true, ticks: { callback: (v) => '₦' + (v >= 1000 ? (v / 1000) + 'k' : v) } }, x: { grid: { display: false } } } } });
    return () => chart.destroy();
  }, [d.day_chart]);
  const go = (extra) => navParams(nav.go, d.self_url, { from: d.from_date, to: d.to_date, term_id: d.term_id, ...extra });
  return (
    <>
      <div className="page-header"><h1>Collections</h1>
        <div className="page-header-actions"><a href={d.export_url} className="btn btn-primary" data-native download><i className="fas fa-file-csv" /> Export</a></div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form">
          <div className="form-group"><label className="form-label">From</label><input type="date" className="form-control" value={d.from_date} onChange={(e) => go({ from: e.target.value })} /></div>
          <div className="form-group"><label className="form-label">To</label><input type="date" className="form-control" value={d.to_date} onChange={(e) => go({ to: e.target.value })} /></div>
          <TermSelect value={d.term_id} terms={d.terms} onChange={(v) => go({ term_id: v })} allLabel="All terms" />
        </form>
        <div className="text-muted text-sm mt-2">Showing {d.from_label} – {d.to_label} · {d.term_id ? <span className="badge badge-info">single term</span> : <span className="badge badge-secondary">all terms</span>} · <a href={d.self_url}>reset to this month</a></div>
      </div></div>
      <div className="sum-cards">
        <div className="sum-card"><div className="v">{naira(d.total)}</div><div className="l">Total collected</div></div>
        <div className="sum-card"><div className="v">{d.count}</div><div className="l">Payments</div></div>
        <div className="sum-card"><div className="v">{naira(d.count ? d.total / d.count : 0)}</div><div className="l">Average</div></div>
      </div>
      <div className="card mb-3"><div className="card-header"><h3><i className="fas fa-chart-column" /> Daily collections</h3></div>
        <div className="card-body"><div className="chart-box">{d.day_chart.length ? <canvas ref={ref} /> : <Empty icon="fa-chart-column" title=""><p>No payments in this range</p></Empty>}</div></div></div>
      <div className="card mb-3"><div className="card-header"><h3><i className="fas fa-wallet" /> By method</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.method_rows.length ? (
            <table className="data-table table-stack no-mobile-scroll"><thead><tr><th>Method</th><th className="text-right">Amount</th></tr></thead>
              <tbody>{d.method_rows.map((m, i) => <tr key={i}><td data-label="Method"><span className="badge badge-info">{m.method}</span></td><td data-label="Amount" className="text-right">{naira(m.amount)}</td></tr>)}</tbody></table>
          ) : <Empty icon="fa-wallet" title="" style={{ padding: '1.2rem' }}><p>No data</p></Empty>}
        </div></div>
      <div className="card"><div className="card-header"><h3>Payments ({d.count})</h3><span className="badge badge-success">{naira(d.total)}</span></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.payments.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Date</th><th>Receipt</th><th>Student</th><th>Method</th><th className="text-right">Amount</th></tr></thead>
              <tbody>{d.payments.map((p) => (
                <tr key={p.id}><td data-label="Date">{p.date}</td><td data-label="Receipt"><a href={p.receipt_url} data-native>{p.receipt_no}</a></td>
                  <td data-label="Student">{p.student}</td><td data-label="Method"><span className="badge badge-info">{p.method}</span></td>
                  <td data-label="Amount" className="text-right"><strong>{naira(p.amount)}</strong></td></tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-receipt" title="No payments"><p>No collections in the selected range.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Expenses --------------------------------------------------------------
function Expenses({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ description: '', amount: '', category_id: '', expense_date: d.today, payee: '', method: d.methods[0] });
  const [editing, setEditing] = useState(null);
  const [cat, setCat] = useState('');
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, category_id: d.category_id, ...extra });
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const add = async (e) => {
    e.preventDefault();
    const r = await submitJson(d.urls.add, { ...f, term_id: d.term_id || '' });
    if (r.ok) { setF({ description: '', amount: '', category_id: '', expense_date: d.today, payee: '', method: d.methods[0] }); notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Could not record.');
  };
  const addCat = async (e) => {
    e.preventDefault();
    const r = await submitJson(d.urls.add_category, { name: cat });
    if (r.ok) { setCat(''); notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not add.');
  };
  return (
    <>
      <div className="page-header"><h1>Expenses</h1>
        <div className="page-header-actions"><a href={d.reports_url} className="btn btn-secondary"><i className="fas fa-chart-column" /> Reports</a></div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form">
          <TermSelect value={d.term_id} terms={d.terms} onChange={(v) => go({ term_id: v })} allLabel="All terms" />
          <div className="form-group"><label className="form-label">Category</label>
            <select className="form-control" value={d.category_id} onChange={(e) => go({ category_id: e.target.value })}>
              <option value="">All categories</option>{d.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        </form>
        {d.cat_summary.length > 0 && (
          <div className="chip-row mt-2">
            <span className="chip" style={{ background: 'var(--danger)', color: '#fff' }}>Total <span style={{ color: 'rgba(255,255,255,.85)' }}>{naira(d.total)}</span></span>
            {d.cat_summary.map((c, i) => <span className="chip" key={i}>{c.name} <span>{naira(c.amount)}</span></span>)}
          </div>)}
      </div></div>

      <div className="card mb-3"><div className="card-header"><h3><i className="fas fa-plus" /> Record Expense</h3></div>
        <div className="card-body"><form onSubmit={add}>
          <div className="exp-fields">
            <div className="form-group mb-0"><label className="form-label">Description <span className="required">*</span></label><input type="text" className="form-control" placeholder="e.g., June electricity bill" required value={f.description} onChange={(e) => set('description', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Amount (₦) <span className="required">*</span></label><input type="number" className="form-control" inputMode="decimal" min="0" step="50" required value={f.amount} onChange={(e) => set('amount', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Category</label><select className="form-control" value={f.category_id} onChange={(e) => set('category_id', e.target.value)}><option value="">—</option>{d.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div className="form-group mb-0"><label className="form-label">Date</label><input type="date" className="form-control" value={f.expense_date} onChange={(e) => set('expense_date', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Payee</label><input type="text" className="form-control" placeholder="Paid to" value={f.payee} onChange={(e) => set('payee', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Method</label><select className="form-control" value={f.method} onChange={(e) => set('method', e.target.value)}>{d.methods.map((m) => <option key={m} value={m}>{m}</option>)}</select></div>
          </div>
          <div className="mt-3"><button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Record Expense</button></div>
        </form></div></div>

      <div className="card"><div className="card-header"><h3>Expenses ({d.expenses.length})</h3><span className="badge badge-danger">{naira(d.total)}</span></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.expenses.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Date</th><th>Category</th><th>Description</th><th>Payee</th><th>Method</th><th className="text-right">Amount</th><th /></tr></thead>
              <tbody>{d.expenses.map((e) => (
                <React.Fragment key={e.id}>
                  <tr>
                    <td data-label="Date">{e.date}</td>
                    <td data-label="Category">{e.category ? <span className="badge badge-secondary">{e.category}</span> : '—'}</td>
                    <td data-label="Description">{e.description}</td>
                    <td data-label="Payee" className="text-muted text-sm">{e.payee || '—'}</td>
                    <td data-label="Method"><span className="badge badge-info">{e.method}</span></td>
                    <td data-label="Amount" className="text-right"><strong>{naira(e.amount)}</strong></td>
                    <td className="actions"><div className="d-flex gap-1 justify-end">
                      <button className="btn btn-secondary btn-sm" onClick={() => setEditing(editing === e.id ? null : e.id)}><i className="fas fa-edit" /></button>
                      {d.is_admin && <button className="btn btn-danger btn-sm" onClick={() => act(e.delete_url, {}, `Delete this expense (${naira(e.amount)})?`)}><i className="fas fa-trash" /></button>}
                    </div></td>
                  </tr>
                  {editing === e.id && (
                    <tr><td colSpan={7} className="stack-full" style={{ background: 'var(--gray-50)' }}>
                      <ExpenseEdit e={e} cats={d.categories} methods={d.methods} notify={notify} onDone={() => { setEditing(null); nav.refresh(); }} />
                    </td></tr>)}
                </React.Fragment>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-money-bill-wave" title="No expenses recorded"><p>Record school expenditure to track your net position.</p></Empty>}
        </div></div>

      {d.is_admin && (
        <div className="card mt-3"><div className="card-header"><h3><i className="fas fa-folder-tree" /> Expense Categories</h3></div>
          <div className="card-body">
            <div className="chip-row mb-3">{d.categories.map((c) => (
              <span className="chip d-flex align-center gap-1" key={c.id}>{c.name}
                <button className="btn btn-danger btn-sm" style={{ padding: '.1rem .35rem' }} onClick={() => act(c.delete_url, {}, `Delete category ${c.name}?`)}><i className="fas fa-times" /></button>
              </span>))}</div>
            <form onSubmit={addCat} className="d-flex gap-2 align-end flex-wrap">
              <div className="form-group mb-0" style={{ flex: 1, minWidth: 180 }}><label className="form-label">New category</label><input type="text" className="form-control" placeholder="e.g., Security" required value={cat} onChange={(e) => setCat(e.target.value)} /></div>
              <button type="submit" className="btn btn-secondary"><i className="fas fa-plus" /> Add</button>
            </form>
          </div></div>
      )}
    </>
  );
}

function ExpenseEdit({ e, cats, methods, notify, onDone }) {
  const [f, setF] = useState({ description: e.description, amount: String(e.amount), category_id: e.category_id || '', expense_date: e.expense_date, payee: e.payee, method: e.method });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (ev) => {
    ev.preventDefault();
    const r = await submitJson(e.edit_url, f);
    if (r.ok) onDone(); else notify('error', r.error || 'Could not update.');
  };
  return (
    <form onSubmit={submit} className="exp-fields">
      <div className="form-group mb-0"><label className="form-label">Description</label><input type="text" className="form-control" required value={f.description} onChange={(ev) => set('description', ev.target.value)} /></div>
      <div className="form-group mb-0"><label className="form-label">Amount (₦)</label><input type="number" className="form-control" min="0" step="50" required value={f.amount} onChange={(ev) => set('amount', ev.target.value)} /></div>
      <div className="form-group mb-0"><label className="form-label">Category</label><select className="form-control" value={f.category_id} onChange={(ev) => set('category_id', ev.target.value)}><option value="">—</option>{cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      <div className="form-group mb-0"><label className="form-label">Date</label><input type="date" className="form-control" value={f.expense_date} onChange={(ev) => set('expense_date', ev.target.value)} /></div>
      <div className="form-group mb-0"><label className="form-label">Payee</label><input type="text" className="form-control" value={f.payee} onChange={(ev) => set('payee', ev.target.value)} /></div>
      <div className="form-group mb-0"><label className="form-label">Method</label><select className="form-control" value={f.method} onChange={(ev) => set('method', ev.target.value)}>{methods.map((m) => <option key={m} value={m}>{m}</option>)}</select></div>
      <div className="form-group mb-0" style={{ alignSelf: 'end' }}><button type="submit" className="btn btn-primary btn-sm"><i className="fas fa-save" /> Update</button></div>
    </form>
  );
}

// ---- Reports ---------------------------------------------------------------
function Reports({ d }) {
  const nav = useNav();
  const rateBadge = (r) => 'badge ' + (r >= 80 ? 'badge-success' : r >= 40 ? 'badge-warning' : 'badge-danger');
  return (
    <>
      <div className="page-header"><h1>Finance Reports</h1>
        <div className="page-header-actions">{d.export_url && <a href={d.export_url} className="btn btn-primary" data-native download><i className="fas fa-file-excel" /> Export to Excel</a>}</div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body"><form className="filter-form">
        <TermSelect value={d.term_id} terms={d.terms} onChange={(v) => navParams(nav.go, d.self_url, { term_id: v })} />
      </form></div></div>
      <div className="two-col">
        <div className="card"><div className="card-header"><h3><i className="fas fa-scale-balanced" /> Income &amp; Expenditure {d.selected_term && `· ${d.selected_term}`}</h3></div>
          <div className="card-body"><div className="pl">
            <div className="pl-row"><span>Expected (after discounts)</span><span>{naira(d.payable)}</span></div>
            <div className="pl-row"><span>Discounts / waivers</span><span>{naira(d.discounts)}</span></div>
            <div className="pl-row"><span>Collected (income)</span><span className="pos">{naira(d.collected)}</span></div>
            <div className="pl-row"><span>Outstanding</span><span className="neg">{naira(d.outstanding)}</span></div>
            <div className="pl-row"><span>Collection rate</span><span>{d.rate}%</span></div>
            <div className="pl-row"><span>Expenditure</span><span className="neg">− {naira(d.expenses)}</span></div>
            <div className="pl-row total"><span>Net cash position</span><span className={d.net >= 0 ? 'pos' : 'neg'}>{naira(d.net)}</span></div>
          </div></div></div>
        <div className="card"><div className="card-header"><h3><i className="fas fa-layer-group" /> Expected income by fee</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            {d.item_breakdown.length ? (
              <table className="data-table no-mobile-scroll" style={{ width: '100%' }}><tbody>
                {d.item_breakdown.map((it, i) => <tr key={i}><td>{it.name}</td><td className="text-right">{naira(it.amount)}</td></tr>)}</tbody></table>
            ) : <Empty icon="fa-layer-group" title="" style={{ padding: '1.2rem' }}><p>No fee structure set</p></Empty>}
          </div></div>
      </div>
      <div className="card mb-3"><div className="card-header"><h3><i className="fas fa-school" /> Collection by class</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.class_rows.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Class</th><th className="text-right">Students</th><th className="text-right">Expected</th><th className="text-right">Collected</th><th className="text-right">Outstanding</th><th className="text-right">Rate</th></tr></thead>
              <tbody>{d.class_rows.map((r, i) => (
                <tr key={i}><td data-label="Class"><strong>{r.name}</strong></td><td data-label="Students" className="text-right">{r.students}</td>
                  <td data-label="Expected" className="text-right">{naira(r.expected)}</td><td data-label="Collected" className="text-right">{naira(r.collected)}</td>
                  <td data-label="Outstanding" className="text-right">{naira(r.outstanding)}</td>
                  <td data-label="Rate" className="text-right"><span className={rateBadge(r.rate)}>{r.rate}%</span></td></tr>))}</tbody>
            </table></div>
          ) : <Empty icon="fa-school" title="" style={{ padding: '1.2rem' }}><p>No data for this term</p></Empty>}
        </div></div>
      <div className="card"><div className="card-header"><h3><i className="fas fa-wallet" /> Payments by method</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.method_rows.length ? (
            <table className="data-table table-stack no-mobile-scroll"><thead><tr><th>Method</th><th className="text-right">Count</th><th className="text-right">Amount</th></tr></thead>
              <tbody>{d.method_rows.map((m, i) => <tr key={i}><td data-label="Method"><span className="badge badge-info">{m.method}</span></td><td data-label="Count" className="text-right">{m.count}</td><td data-label="Amount" className="text-right">{naira(m.amount)}</td></tr>)}</tbody></table>
          ) : <Empty icon="fa-wallet" title="" style={{ padding: '1.2rem' }}><p>No payments yet</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Edit payment ----------------------------------------------------------
function EditPayment({ d, notify }) {
  const nav = useNav();
  const p = d.payment;
  const [f, setF] = useState({ amount: String(p.amount), payment_date: p.payment_date, method: p.method, reference: p.reference, received_by: p.received_by, notes: p.notes });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    const amt = parseFloat(f.amount);
    if (!amt || amt <= 0) { notify('error', 'Enter a positive amount.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const del = async () => {
    if (!window.confirm(`Delete receipt ${p.receipt_no} (${naira(p.amount)})?`)) return;
    const r = await submitJson(d.delete_url, {});
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <div className="page-header"><h1>Edit Payment</h1></div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body"><div className="d-flex justify-between flex-wrap gap-2">
        <div><strong>{p.student}</strong> <span className="text-muted">({p.student_id_label})</span><div className="text-muted text-sm">{p.term} · Receipt {p.receipt_no}</div></div>
        {d.bill && <div className="text-right"><div className="text-muted text-sm">Current balance</div><strong style={{ color: balColor(d.bill.balance) }}>{naira(d.bill.balance)}</strong></div>}
      </div></div></div>
      <div className="card"><div className="card-header"><h3>Payment Details</h3></div><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-group"><label className="form-label">Amount (₦) <span className="required">*</span></label>
            <input type="number" className="form-control" inputMode="decimal" min="0" step="50" required value={f.amount} onChange={(e) => set('amount', e.target.value)} /></div>
          <div className="pay-fields two">
            <div className="form-group mb-0"><label className="form-label">Date</label><input type="date" className="form-control" value={f.payment_date} onChange={(e) => set('payment_date', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Method</label><select className="form-control" value={f.method} onChange={(e) => set('method', e.target.value)}>{d.methods.map((m) => <option key={m} value={m}>{m}</option>)}</select></div>
          </div>
          <div className="pay-fields two mt-3">
            <div className="form-group mb-0"><label className="form-label">Reference / Teller No.</label><input type="text" className="form-control" value={f.reference} onChange={(e) => set('reference', e.target.value)} /></div>
            <div className="form-group mb-0"><label className="form-label">Received by</label><input type="text" className="form-control" value={f.received_by} onChange={(e) => set('received_by', e.target.value)} /></div>
          </div>
          <div className="form-group mt-3"><label className="form-label">Notes</label><textarea className="form-control" rows="2" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></div>
          <div className="page-header-actions">
            <button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> Save Changes</button>
            <a href={d.receipt_url} className="btn btn-secondary" data-native>Cancel</a>
            {d.is_admin && <button type="button" className="btn btn-danger" style={{ marginLeft: 'auto' }} onClick={del}><i className="fas fa-trash" /> Delete</button>}
          </div>
        </form>
      </div></div>
    </>
  );
}

const SCREENS = { dashboard: Dashboard, collections: Collections, items: Items, structure: Structure,
  payments: Payments, record_payment: RecordPayment, statement: Statement, defaulters: Defaulters,
  expenses: Expenses, reports: Reports, edit_payment: EditPayment };

export default function FinanceApp({ data }) {
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
