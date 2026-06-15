import React, { useState } from 'react';
import { postForm } from '../lib/forms';
import { naira } from '../lib/format';
import { Banner } from '../components/ui';

function PageHeader({ icon, title, actions }) {
  return (
    <div className="page-header">
      <h1><i className={'fas ' + icon} /> {title}</h1>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}

function EmptyState({ icon, title, children }) {
  return (
    <div className="empty-state">
      <i className={'fas ' + icon} /><h3>{title}</h3>{children && <p>{children}</p>}
    </div>
  );
}

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const u = d.urls;
  return (
    <>
      <PageHeader icon="fa-cart-shopping" title="Sales & Inventory" actions={<>
        <a href={u.new_sale} className="btn btn-primary"><i className="fas fa-plus" /> New Sale</a>
        <a href={u.products} className="btn btn-secondary"><i className="fas fa-boxes-stacked" /> Products</a>
      </>} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: '.75rem', marginBottom: '1rem' }}>
        {[[naira(d.today_total), 'Sold today'], [d.today_count, 'Sales today'],
          [d.product_count, 'Products']].map(([v, l]) => (
          <div className="card" key={l}><div className="card-body">
            <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{v}</div>
            <div className="text-muted text-sm">{l}</div></div></div>
        ))}
        <div className="card"><div className="card-body">
          <div style={{ fontSize: '1.4rem', fontWeight: 700, color: d.low_stock.length ? '#e74a3b' : 'inherit' }}>{d.low_stock.length}</div>
          <div className="text-muted text-sm">Low stock</div></div></div>
      </div>

      {d.low_stock.length > 0 && (
        <div className="card mb-3" style={{ borderColor: '#f6c23e' }}>
          <div className="card-header"><h3><i className="fas fa-triangle-exclamation" /> Low stock</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Product</th><th>Category</th><th className="text-right">In stock</th><th className="text-right">Reorder at</th></tr></thead>
              <tbody>{d.low_stock.map((p, i) => (
                <tr key={i}><td data-label="Product">{p.name}</td><td data-label="Category">{p.category}</td>
                  <td data-label="In stock" className="text-right"><strong style={{ color: '#e74a3b' }}>{p.stock_qty}</strong></td>
                  <td data-label="Reorder at" className="text-right">{p.reorder_level}</td></tr>
              ))}</tbody>
            </table>
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

function SalesTable({ rows, withItems }) {
  return (
    <table className="data-table table-stack no-mobile-scroll">
      <thead><tr><th>Receipt</th><th>Buyer</th>{withItems && <th>Items</th>}<th>Method</th><th className="text-right">Total</th><th>When</th></tr></thead>
      <tbody>{rows.map((s) => (
        <tr key={s.id}>
          <td data-label="Receipt"><a href={s.receipt_url}>{s.receipt_no}</a></td>
          <td data-label="Buyer">{s.buyer}</td>
          {withItems && <td data-label="Items">{s.item_count}</td>}
          <td data-label="Method"><span className="badge badge-info">{s.payment_method}</span></td>
          <td data-label="Total" className="text-right"><strong>{naira(s.total)}</strong></td>
          <td data-label="When">{s.when}</td>
        </tr>
      ))}</tbody>
    </table>
  );
}

// ---- Products --------------------------------------------------------------
function Products({ d, notify }) {
  const [q, setQ] = useState(d.q || '');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: '', category: (d.categories[0] || 'Other'), unit_price: '0', stock_qty: '0', reorder_level: '0' });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submitAdd = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { notify('error', 'Product name is required.'); return; }
    setBusy(true);
    const res = await postForm(d.add_url, form);
    const body = await res.json().catch(() => ({}));
    setBusy(false);
    if (res.ok && body.ok) window.location.reload();
    else notify('error', body.error || 'Could not add product.');
  };

  const restock = async (p, qty) => {
    if (!qty) return;
    setBusy(true);
    const res = await postForm(p.restock_url, { qty });
    const body = await res.json().catch(() => ({}));
    setBusy(false);
    if (res.ok && body.ok) window.location.reload();
    else notify('error', body.error || 'Could not restock.');
  };

  // Client-side search over the loaded products (parity: classic reloaded on change).
  const shown = q ? d.products.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())) : d.products;

  return (
    <>
      <PageHeader icon="fa-boxes-stacked" title="Products & Stock" actions={
        <a href={d.urls.new_sale} className="btn btn-primary"><i className="fas fa-cart-plus" /> New Sale</a>} />

      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-plus" /> Add product</h3></div>
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
              <button className="btn btn-primary" disabled={busy}><i className="fas fa-plus" /> Add</button></div>
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

// ---- New sale --------------------------------------------------------------
function NewSale({ d, notify }) {
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
    const res = await postForm(d.submit_url, { product_id: ids, quantity: qs, ...pay });
    const body = await res.json().catch(() => ({}));
    setBusy(false);
    if (res.ok && body.ok) window.location = body.redirect;
    else notify('error', body.error || 'Could not record the sale.');
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
            {!d.products.length && <div className="empty-state" style={{ padding: '1.2rem' }}>
              <p>No products in stock. <a href={d.urls.products}>Add some</a>.</p></div>}
          </div>
        </div>

        <div className="card mb-3">
          <div className="card-header"><h3>Payment</h3> <strong>{naira(total)}</strong></div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}>
              <div className="form-group"><label className="form-label">Student (optional)</label>
                <select className="form-control" value={pay.student_id} onChange={(e) => setP('student_id', e.target.value)}>
                  <option value="">— Walk-in / staff —</option>
                  {d.students.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </select></div>
              <div className="form-group"><label className="form-label">Customer name (if not a student)</label>
                <input type="text" className="form-control" value={pay.customer_name} onChange={(e) => setP('customer_name', e.target.value)} /></div>
              <div className="form-group"><label className="form-label">Method</label>
                <select className="form-control" value={pay.payment_method} onChange={(e) => setP('payment_method', e.target.value)}>
                  {d.methods.map((m) => <option key={m}>{m}</option>)}</select></div>
              <div className="form-group"><label className="form-label">Amount paid (blank = exact)</label>
                <input type="number" step="0.01" className="form-control" value={pay.amount_paid} onChange={(e) => setP('amount_paid', e.target.value)} /></div>
            </div>
          </div>
        </div>

        <div className="d-flex gap-2">
          <button type="submit" className="btn btn-primary btn-lg" disabled={busy}><i className="fas fa-receipt" /> Complete Sale</button>
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
        <h1><i className="fas fa-clock-rotate-left" /> Sales History</h1>
        <span className="badge badge-success">{naira(d.total)}</span>
      </div>
      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.sales.length ? <SalesTable rows={d.sales} withItems /> : <EmptyState icon="fa-receipt" title="No sales yet" />}
      </div></div>
    </>
  );
}

const SCREENS = { dashboard: Dashboard, products: Products, new_sale: NewSale, history: History };

export default function SalesApp({ data }) {
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[data.page] || Dashboard;
  return (
    <div>
      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      <Screen d={data} notify={notify} />
    </div>
  );
}
