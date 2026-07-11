import React, { useState, useEffect } from 'react';
import { submitJson } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { Banner, PageHeader, Empty, SectionShell, Table } from '../components/ui';

const EmptyState = ({ icon, title, children }) => <Empty icon={icon} title={title}>{children && <p>{children}</p>}</Empty>;

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const u = d.urls;
  return (
    <>
      <PageHeader icon="fa-cart-shopping" title="Sales & Inventory" actions={<>
        <a href={u.new_sale} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> New Sale</a>
        <a href={u.products} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-boxes-stacked" /> Products</a>
        {u.analytics && <a href={u.analytics} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-chart-pie" /> Analytics</a>}
      </>} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: '.75rem', marginBottom: '1rem' }}>
        {[[naira(d.today_total), 'Sold today'], [d.today_count, 'Sales today'],
          [d.product_count, 'Products']].map(([v, l]) => (
          <div className="card" key={l}><div className="card-body">
            <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{v}</div>
            <div className="text-muted text-sm">{l}</div></div></div>
        ))}
        <div className="card"><div className="card-body">
          <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: d.low_stock.length ? '#e74a3b' : 'inherit' }}>{d.low_stock.length}</div>
          <div className="text-muted text-sm">Low stock</div></div></div>
      </div>

      {d.low_stock.length > 0 && (
        <div className="card mb-3" style={{ borderColor: '#f6c23e' }}>
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Low stock</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <Table rowKey={(p, i) => i} rows={d.low_stock} columns={[
              { key: 'name', label: 'Product', render: (p) => p.name },
              { key: 'category', label: 'Category', render: (p) => p.category },
              { key: 'stock', label: 'In stock', align: 'right', render: (p) => <strong style={{ color: 'var(--danger)' }}>{p.stock_qty}</strong> },
              { key: 'reorder', label: 'Reorder at', align: 'right', render: (p) => p.reorder_level },
            ]} />
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header"><h3>Recent sales</h3><a href={u.history} className="btn btn-sm btn-secondary">All</a></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.recent.length ? <SalesTable rows={d.recent} /> : <EmptyState icon="fa-receipt" title="No sales yet">Record your first sale.</EmptyState>}
        </div>
      </div>
    </>
  );
}

function SalesTable({ rows, withItems, paged }) {
  const cols = [
    { key: 'receipt', label: 'Receipt', render: (s) => <a href={s.receipt_url}>{s.receipt_no}</a> },
    { key: 'buyer', label: 'Buyer', sortable: paged, sortValue: (s) => s.buyer, render: (s) => s.buyer },
    withItems && { key: 'items', label: 'Items', render: (s) => s.item_count },
    { key: 'method', label: 'Method', render: (s) => <span className="badge badge-info">{s.payment_method}</span> },
    { key: 'total', label: 'Total', align: 'right', sortable: paged, sortValue: (s) => Number(s.total) || 0, render: (s) => <strong>{naira(s.total)}</strong> },
    { key: 'when', label: 'When', sortable: paged, sortValue: (s) => s.when, render: (s) => s.when },
  ].filter(Boolean);
  return <Table rowKey={(s) => s.id} rows={rows} columns={cols}
                pageSize={paged ? 25 : undefined} sticky={paged} maxHeight={paged ? '65vh' : undefined} />;
}

// ---- Products --------------------------------------------------------------
function Products({ d, notify }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q || '');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: '', category: (d.categories[0] || 'Other'), unit_price: '0', stock_qty: '0', reorder_level: '0' });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submitAdd = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { notify('error', 'Product name is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.add_url, form);
    setBusy(false);
    if (r.ok) nav.refresh();
    else notify('error', r.error || 'Could not add product.');
  };

  const restock = async (p, qty) => {
    if (!qty) return;
    setBusy(true);
    const r = await submitJson(p.restock_url, { qty });
    setBusy(false);
    if (r.ok) nav.refresh();
    else notify('error', r.error || 'Could not restock.');
  };

  // Client-side search over the loaded products (parity: classic reloaded on change).
  const shown = q ? d.products.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())) : d.products;

  return (
    <>
      <PageHeader icon="fa-boxes-stacked" title="Products & Stock" actions={
        <a href={d.urls.new_sale} className="btn btn-primary"><i aria-hidden="true" className="fas fa-cart-plus" /> New Sale</a>} />

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Add product</h3></div>
        <div className="card-body">
          <form onSubmit={submitAdd} className="filter-form" style={{ flexWrap: 'wrap', gap: '1rem' }}>
            <div className="form-group"><label className="form-label">Name <span className="text-danger">*</span></label>
              <input type="text" className="form-control" value={form.name} onChange={(e) => set('name', e.target.value)} required /></div>
            <div className="form-group"><label className="form-label">Category</label>
              <select className="form-control" value={form.category} onChange={(e) => set('category', e.target.value)}>
                {d.categories.map((c) => <option key={c}>{c}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Price (₦)</label>
              <input type="number" step="0.01" className="form-control" value={form.unit_price} onChange={(e) => set('unit_price', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Opening stock</label>
              <input type="number" className="form-control" value={form.stock_qty} onChange={(e) => set('stock_qty', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Reorder at</label>
              <input type="number" className="form-control" value={form.reorder_level} onChange={(e) => set('reorder_level', e.target.value)} /></div>
            <div className="form-group" style={{ alignSelf: 'flex-end' }}>
              <button className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
          </form>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3>Products ({shown.length})</h3>
          <input type="text" className="form-control" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 220 }} />
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {shown.length ? (
            <div className="table-container">
              <table className="data-table table-stack no-mobile-scroll">
                <thead><tr><th>Name</th><th>Category</th><th className="text-right">Price</th><th className="text-right">Stock</th><th>Restock</th></tr></thead>
                <tbody>{shown.map((p) => <ProductRow key={p.id} p={p} onRestock={restock} busy={busy} />)}</tbody>
              </table>
            </div>
          ) : <EmptyState icon="fa-boxes-stacked" title="No products">Add your first product above.</EmptyState>}
        </div>
      </div>
    </>
  );
}

function ProductRow({ p, onRestock, busy }) {
  const [qty, setQty] = useState('');
  return (
    <tr>
      <td data-label="Name">{p.name}{p.sku && <span className="text-muted text-sm"> ({p.sku})</span>}</td>
      <td data-label="Category">{p.category}</td>
      <td data-label="Price" className="text-right">{naira(p.unit_price)}</td>
      <td data-label="Stock" className="text-right"><strong style={p.low_stock ? { color: '#e74a3b' } : undefined}>{p.stock_qty}</strong></td>
      <td data-label="Restock">
        <form onSubmit={(e) => { e.preventDefault(); onRestock(p, Number(qty) || 0); }} style={{ display: 'flex', gap: '.3rem' }}>
          <input type="number" className="form-control" style={{ width: 80 }} placeholder="+qty" value={qty} onChange={(e) => setQty(e.target.value)} />
          <button className="btn btn-sm btn-secondary" disabled={busy}>Add</button>
        </form>
      </td>
    </tr>
  );
}

// ---- Buyer picker ----------------------------------------------------------
// Records who's buying without a giant student dropdown: pick a class (+ optional
// arm), then search within it. Non-students fall back to a free-text name.
function BuyerPicker({ d, pay, setP }) {
  const [mode, setMode] = useState('student');   // 'student' | 'other'
  const [classId, setClassId] = useState('');
  const [armId, setArmId] = useState('');
  const [q, setQ] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [chosen, setChosen] = useState(null);

  // Debounced lookup whenever the class / arm / query changes.
  useEffect(() => {
    if (mode !== 'student' || !classId) { setRows([]); return undefined; }
    let live = true;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const p = new URLSearchParams({ class_id: classId });
        if (armId) p.set('arm_id', armId);
        if (q.trim()) p.set('q', q.trim());
        const res = await apiGet(`${d.student_search_url}?${p.toString()}`);
        if (live) setRows(res.students || []);
      } catch (_) { if (live) setRows([]); }
      finally { if (live) setLoading(false); }
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [mode, classId, armId, q, d.student_search_url]);

  const pick = (s) => { setChosen(s); setP('student_id', s.id); setP('customer_name', ''); };
  const clearPick = () => { setChosen(null); setP('student_id', ''); };
  const chooseMode = (m) => {
    setMode(m);
    if (m === 'other') { clearPick(); } else { setP('customer_name', ''); }
  };

  return (
    <div className="form-group">
      <label className="form-label">Buyer</label>
      <div className="btn-group" role="tablist" style={{ display: 'flex', gap: '.4rem', marginBottom: '.6rem' }}>
        <button type="button" role="tab" aria-selected={mode === 'student'}
                className={'btn btn-sm ' + (mode === 'student' ? 'btn-primary' : 'btn-secondary')}
                onClick={() => chooseMode('student')}><i aria-hidden="true" className="fas fa-user-graduate" /> Student</button>
        <button type="button" role="tab" aria-selected={mode === 'other'}
                className={'btn btn-sm ' + (mode === 'other' ? 'btn-primary' : 'btn-secondary')}
                onClick={() => chooseMode('other')}><i aria-hidden="true" className="fas fa-user" /> Staff / Parent / Walk-in</button>
      </div>

      {mode === 'other' && (
        <input type="text" className="form-control" placeholder="Customer name (optional)"
               value={pay.customer_name} onChange={(e) => setP('customer_name', e.target.value)} />
      )}

      {mode === 'student' && (chosen ? (
        <div className="d-flex" style={{ alignItems: 'center', justifyContent: 'space-between', gap: '.5rem',
             border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', padding: '.55rem .75rem' }}>
          <span><i aria-hidden="true" className="fas fa-user-check" style={{ color: 'var(--success)' }} /> <strong>{chosen.label}</strong></span>
          <button type="button" className="btn btn-sm btn-secondary" onClick={clearPick}>Change</button>
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.5rem', marginBottom: '.5rem' }}>
            <select className="form-control" value={classId} aria-label="Class"
                    onChange={(e) => { setClassId(e.target.value); }}>
              <option value="">Select class…</option>
              {(d.classes || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select className="form-control" value={armId} aria-label="Arm (optional)"
                    onChange={(e) => setArmId(e.target.value)} disabled={!classId}>
              <option value="">All arms</option>
              {(d.arms || []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          {classId ? (
            <>
              <input type="search" className="form-control" placeholder="Search name or ID…"
                     value={q} onChange={(e) => setQ(e.target.value)} style={{ marginBottom: '.5rem' }} />
              <div style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>
                {loading && <div className="text-muted text-sm" style={{ padding: '.6rem .75rem' }}>Searching…</div>}
                {!loading && !rows.length && <div className="text-muted text-sm" style={{ padding: '.6rem .75rem' }}>No students match.</div>}
                {!loading && rows.map((s) => (
                  <button type="button" key={s.id} onClick={() => pick(s)}
                          style={{ display: 'block', width: '100%', textAlign: 'left', background: 'none',
                                   border: 'none', borderBottom: '1px solid var(--border-color)', padding: '.5rem .75rem',
                                   cursor: 'pointer', color: 'inherit' }}>{s.label}</button>
                ))}
              </div>
            </>
          ) : <p className="text-muted text-sm" style={{ margin: 0 }}>Choose a class to find the student.</p>}
        </>
      ))}
    </div>
  );
}

// ---- New sale --------------------------------------------------------------
function NewSale({ d, notify }) {
  const nav = useNav();
  const [qty, setQty] = useState({});       // product_id -> qty
  const [pay, setPay] = useState({ student_id: '', customer_name: '', payment_method: d.methods[0] || 'Cash', amount_paid: '' });
  const [busy, setBusy] = useState(false);
  const setP = (k, v) => setPay((s) => ({ ...s, [k]: v }));
  const total = d.products.reduce((t, p) => t + (p.unit_price || 0) * (Number(qty[p.id]) || 0), 0);

  const submit = async (e) => {
    e.preventDefault();
    const ids = [], qs = [];
    d.products.forEach((p) => { const n = Number(qty[p.id]) || 0; if (n > 0) { ids.push(p.id); qs.push(n); } });
    if (!ids.length) { notify('error', 'Add at least one item with a quantity.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { product_id: ids, quantity: qs, ...pay });
    setBusy(false);
    if (r.ok) nav.go(r.redirect);
    else notify('error', r.error || 'Could not record the sale.');
  };

  return (
    <>
      <PageHeader icon="fa-cart-plus" title="New Sale" />
      <form onSubmit={submit}>
        <div className="card mb-3">
          <div className="card-header"><h3>Items</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <table className="data-table no-mobile-scroll">
              <thead><tr><th>Product</th><th className="text-right">Price</th><th>In stock</th><th style={{ width: 120 }}>Qty</th></tr></thead>
              <tbody>{d.products.map((p) => (
                <tr key={p.id}>
                  <td>{p.name} <span className="text-muted text-sm">· {p.category}</span></td>
                  <td className="text-right">{naira(p.unit_price)}</td>
                  <td>{p.stock_qty}</td>
                  <td><input type="number" className="form-control" min="0" max={p.stock_qty}
                             value={qty[p.id] || ''} onChange={(e) => setQty((s) => ({ ...s, [p.id]: e.target.value }))} /></td>
                </tr>
              ))}</tbody>
            </table>
            {!d.products.length && <Empty icon="fa-box-open" title="No products in stock"><a href={d.urls.products}>Add some</a></Empty>}
          </div>
        </div>

        <div className="card mb-3">
          <div className="card-header"><h3>Payment</h3> <strong>{naira(total)}</strong></div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}>
              <BuyerPicker d={d} pay={pay} setP={setP} />
              <div className="form-group"><label className="form-label">Method</label>
                <select className="form-control" value={pay.payment_method} onChange={(e) => setP('payment_method', e.target.value)}>
                  {d.methods.map((m) => <option key={m}>{m}</option>)}</select></div>
              <div className="form-group"><label className="form-label">Amount paid (blank = exact)</label>
                <input type="number" step="0.01" className="form-control" value={pay.amount_paid} onChange={(e) => setP('amount_paid', e.target.value)} /></div>
            </div>
          </div>
        </div>

        <div className="d-flex gap-2">
          <button type="submit" className="btn btn-primary btn-lg" disabled={busy}><i aria-hidden="true" className="fas fa-receipt" /> Complete Sale</button>
          <a href={d.urls.dashboard} className="btn btn-secondary btn-lg">Cancel</a>
        </div>
      </form>
    </>
  );
}

// ---- History ---------------------------------------------------------------
function History({ d }) {
  return (
    <>
      <div className="page-header">
        <h1><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Sales History</h1>
        <span className="badge badge-success">{naira(d.total)}</span>
      </div>
      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.sales.length ? <SalesTable rows={d.sales} withItems paged /> : <EmptyState icon="fa-receipt" title="No sales yet" />}
      </div></div>
    </>
  );
}

// ---- Analytics -------------------------------------------------------------
// Horizontal bar list: each row a labelled bar sized to the max, plus a value.
function BarList({ rows, labelKey = 'label', valueKey = 'revenue', fmt = naira, color = '#4e73df', sub }) {
  if (!rows.length) return <p className="text-muted text-sm" style={{ margin: '.5rem 0' }}>No data for this range.</p>;
  const max = Math.max(1, ...rows.map((r) => Number(r[valueKey]) || 0));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '.45rem' }}>
      {rows.map((r, i) => (
        <div key={i}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.85rem', marginBottom: 2 }}>
            <span>{r[labelKey]}{sub ? <span className="text-muted"> · {sub(r)}</span> : null}</span>
            <strong>{fmt(r[valueKey])}</strong>
          </div>
          <span aria-hidden="true" style={{ display: 'block', height: 6, background: 'var(--border-color)', borderRadius: 3, overflow: 'hidden' }}>
            <span style={{ display: 'block', height: '100%', width: ((Number(r[valueKey]) || 0) / max * 100) + '%', background: color }} />
          </span>
        </div>
      ))}
    </div>
  );
}

function TrendBars({ rows }) {
  if (!rows.length) return <p className="text-muted text-sm">No sales in this range.</p>;
  const max = Math.max(1, ...rows.map((r) => r.revenue));
  return (
    <div role="img" aria-label={'Sales trend: ' + rows.map((r) => `${r.label} ${Math.round(r.revenue)}`).join(', ')}
         style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 120, overflowX: 'auto', paddingTop: 8 }}>
      {rows.map((r, i) => (
        <div key={i} title={`${r.label}: ${naira(r.revenue)}`} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 16, flex: 1 }}>
          <span style={{ width: '70%', minWidth: 8, height: Math.max(2, (r.revenue / max) * 100) + '%', background: '#11998e', borderRadius: '3px 3px 0 0' }} />
          <span className="text-muted" style={{ fontSize: '.6rem', marginTop: 2, whiteSpace: 'nowrap', transform: 'rotate(0)' }}>{rows.length <= 16 ? r.label.split(' ')[0] : ''}</span>
        </div>
      ))}
    </div>
  );
}

function Analytics({ d }) {
  const nav = useNav();
  const [from, setFrom] = useState(d.from || '');
  const [to, setTo] = useState(d.to || '');
  const s = d.summary || {};
  const apply = (extra = {}) => navParams(nav.go, d.self_url, { from, to, product_id: d.product_id || '', ...extra });
  const pickProduct = (pid) => navParams(nav.go, d.self_url, { from, to, product_id: pid });

  const KPIS = [
    [naira(s.revenue), 'Revenue'], [naira(s.profit), 'Gross profit'],
    [s.count, 'Sales'], [s.units, 'Units sold'], [naira(s.avg_sale), 'Avg sale'],
  ];
  return (
    <>
      <PageHeader icon="fa-chart-pie" title="Sales Analytics" actions={
        <a href={d.urls.dashboard} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>} />

      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.6rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="form-group" style={{ margin: 0 }}><label className="form-label">From</label>
          <input type="date" className="form-control" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
        <div className="form-group" style={{ margin: 0 }}><label className="form-label">To</label>
          <input type="date" className="form-control" value={to} onChange={(e) => setTo(e.target.value)} /></div>
        <button type="button" className="btn btn-primary" onClick={() => apply()}><i aria-hidden="true" className="fas fa-filter" /> Apply</button>
      </div></div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
        {KPIS.map(([v, l]) => (
          <div className="card" key={l}><div className="card-body">
            <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{v}</div>
            <div className="text-muted text-sm">{l}</div></div></div>
        ))}
      </div>

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-line" /> Sales trend</h3></div>
        <div className="card-body"><TrendBars rows={d.trend || []} /></div></div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
        <div className="card"><div className="card-header"><h3>Top products</h3></div><div className="card-body">
          <BarList rows={d.top_products || []} labelKey="name" color="#4e73df" sub={(r) => `${r.units} units`} /></div></div>
        <div className="card"><div className="card-header"><h3>By category</h3></div><div className="card-body">
          <BarList rows={d.by_category || []} color="#11998e" sub={(r) => `${r.units} units`} /></div></div>
        <div className="card"><div className="card-header"><h3>By payment method</h3></div><div className="card-body">
          <BarList rows={d.by_method || []} color="#f6c23e" sub={(r) => `${r.count} sales`} /></div></div>
        <div className="card"><div className="card-header"><h3>By cashier</h3></div><div className="card-body">
          <BarList rows={d.by_cashier || []} color="#667eea" sub={(r) => `${r.count} sales`} /></div></div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-magnifying-glass-chart" /> Who bought a product</h3></div>
        <div className="card-body">
          <div className="form-group">
            <label className="form-label">Product</label>
            <select className="form-control" value={d.product_id || ''} onChange={(e) => pickProduct(e.target.value)}>
              <option value="">Select a product to see buyers by class…</option>
              {(d.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          {d.drill && (
            <>
              <div className="text-muted text-sm" style={{ margin: '.25rem 0 .75rem' }}>
                <strong>{d.drill.total_students}</strong> student(s) bought this · <strong>{d.drill.total_units}</strong> units total
                {d.drill.non_student_units ? ` · ${d.drill.non_student_units} units to staff / walk-in` : ''}
              </div>
              {d.drill.rows.length ? (
                <table className="data-table">
                  <thead><tr><th>Class / Arm</th><th className="text-right">Students</th><th className="text-right">Units</th><th className="text-right">Revenue</th></tr></thead>
                  <tbody>{d.drill.rows.map((r, i) => (
                    <tr key={i}><td>{r.label}</td><td className="text-right">{r.students}</td>
                      <td className="text-right">{r.units}</td><td className="text-right">{naira(r.revenue)}</td></tr>
                  ))}</tbody>
                </table>
              ) : <EmptyState icon="fa-users" title="No student buyers in this range" />}
            </>
          )}
        </div>
      </div>
    </>
  );
}

const SCREENS = { dashboard: Dashboard, products: Products, new_sale: NewSale, history: History, analytics: Analytics };

export default function SalesApp({ data }) {
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
