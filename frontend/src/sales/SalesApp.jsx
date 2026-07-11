import React, { useState, useEffect } from 'react';
import { submitJson } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { Banner, PageHeader, Empty, SectionShell, Table, Modal, Button } from '../components/ui';

const EmptyState = ({ icon, title, children }) => <Empty icon={icon} title={title}>{children && <p>{children}</p>}</Empty>;

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const u = d.urls;
  return (
    <>
      <PageHeader icon="fa-cart-shopping" title="Sales & Inventory" actions={<>
        <a href={u.new_sale} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> New Sale</a>
        <a href={u.products} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-boxes-stacked" /> Products</a>
        {u.movements && <a href={u.movements} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-right-left" /> Movements</a>}
        {u.analytics && <a href={u.analytics} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-chart-pie" /> Analytics</a>}
      </>} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
        {[[naira(d.today_total), 'Sold today'], [d.today_count, 'Sales today'],
          [d.product_count, 'Products'],
          [d.inventory_value != null ? naira(d.inventory_value) : '—', 'Inventory value']].map(([v, l]) => (
          <div className="card" key={l}><div className="card-body">
            <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{v}</div>
            <div className="text-muted text-sm">{l}</div></div></div>
        ))}
        <div className="card"><div className="card-body">
          <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: d.low_stock.length ? '#e74a3b' : 'inherit' }}>{d.low_stock.length}</div>
          <div className="text-muted text-sm">Low stock</div></div></div>
        <div className="card"><div className="card-body">
          <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: d.out_of_stock_count ? '#e74a3b' : 'inherit' }}>{d.out_of_stock_count || 0}</div>
          <div className="text-muted text-sm">Out of stock</div></div></div>
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

// ---- Product form (add / edit) ---------------------------------------------
const PF_NUM = ['cost_price', 'unit_price', 'discount_price', 'wholesale_price',
  'student_price', 'staff_price', 'parent_price', 'stock_qty', 'reorder_level',
  'max_stock', 'reorder_qty', 'vat_rate'];

function Field({ label, children, wide }) {
  return <label className="form-group" style={{ margin: 0, gridColumn: wide ? '1 / -1' : undefined }}>
    <span className="form-label">{label}</span>{children}</label>;
}
function Num({ v, on, step }) {
  return <input type="number" step={step || '1'} className="form-control" value={v ?? ''} onChange={(e) => on(e.target.value)} />;
}

function ProductForm({ d, product, onClose, onSaved }) {
  const editing = !!product;
  const init = { name: '', category: d.categories[0] || 'Other', sku: '', barcode: '', brand: '',
    unit: '', pack_size: '', storage_location: '', preferred_supplier: '', warranty_period: '',
    description: '', image_url: '', cost_price: '', unit_price: '', discount_price: '',
    wholesale_price: '', student_price: '', staff_price: '', parent_price: '', stock_qty: '0',
    reorder_level: '0', max_stock: '', reorder_qty: '', vat_rate: '', taxable: false,
    expiry_date: '', is_active: true, ...(product || {}) };
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));

  const save = async () => {
    if (!f.name.trim()) { setErr('Product name is required.'); return; }
    setBusy(true); setErr(null);
    const payload = { ...f, taxable: f.taxable ? 'on' : '', is_active: f.is_active ? 'on' : '' };
    if (editing) delete payload.stock_qty;   // stock changes go through Restock / adjustments
    const r = await submitJson(editing ? product.edit_url : d.add_url, payload);
    setBusy(false);
    if (r.ok) { onSaved(); onClose(); } else setErr(r.error || 'Could not save product.');
  };

  const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' };
  return (
    <Modal title={editing ? 'Edit product' : 'Add product'} icon="fa-box" size="lg" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
             <Button variant="primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button></>}>
      {err && <div className="alert alert-danger" role="alert">{err}</div>}
      <h4 className="text-muted text-sm" style={{ margin: '0 0 .4rem' }}>Basics</h4>
      <div style={grid}>
        <Field label="Name *" wide><input type="text" className="form-control" value={f.name} onChange={(e) => set('name', e.target.value)} required /></Field>
        <Field label="Category"><select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>{d.categories.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="Brand"><input type="text" className="form-control" value={f.brand} onChange={(e) => set('brand', e.target.value)} /></Field>
        <Field label="SKU"><input type="text" className="form-control" value={f.sku} onChange={(e) => set('sku', e.target.value)} /></Field>
        <Field label="Barcode"><input type="text" className="form-control" value={f.barcode} onChange={(e) => set('barcode', e.target.value)} /></Field>
        <Field label="Unit"><select className="form-control" value={f.unit || ''} onChange={(e) => set('unit', e.target.value)}><option value="">—</option>{(d.units || []).map((u) => <option key={u}>{u}</option>)}</select></Field>
        <Field label="Pack size"><input type="text" className="form-control" value={f.pack_size} onChange={(e) => set('pack_size', e.target.value)} /></Field>
      </div>
      <h4 className="text-muted text-sm" style={{ margin: '.9rem 0 .4rem' }}>Pricing (₦) — tier prices are optional; blank uses the selling price</h4>
      <div style={grid}>
        <Field label="Cost price"><Num v={f.cost_price} on={(v) => set('cost_price', v)} step="0.01" /></Field>
        <Field label="Selling price"><Num v={f.unit_price} on={(v) => set('unit_price', v)} step="0.01" /></Field>
        <Field label="Discount price"><Num v={f.discount_price} on={(v) => set('discount_price', v)} step="0.01" /></Field>
        <Field label="Wholesale price"><Num v={f.wholesale_price} on={(v) => set('wholesale_price', v)} step="0.01" /></Field>
        <Field label="Student price"><Num v={f.student_price} on={(v) => set('student_price', v)} step="0.01" /></Field>
        <Field label="Staff price"><Num v={f.staff_price} on={(v) => set('staff_price', v)} step="0.01" /></Field>
        <Field label="Parent price"><Num v={f.parent_price} on={(v) => set('parent_price', v)} step="0.01" /></Field>
      </div>
      <h4 className="text-muted text-sm" style={{ margin: '.9rem 0 .4rem' }}>Stock</h4>
      <div style={grid}>
        {!editing && <Field label="Opening stock"><Num v={f.stock_qty} on={(v) => set('stock_qty', v)} /></Field>}
        <Field label="Reorder / min level"><Num v={f.reorder_level} on={(v) => set('reorder_level', v)} /></Field>
        <Field label="Max level"><Num v={f.max_stock} on={(v) => set('max_stock', v)} /></Field>
        <Field label="Reorder qty"><Num v={f.reorder_qty} on={(v) => set('reorder_qty', v)} /></Field>
        <Field label="Storage location"><input type="text" className="form-control" value={f.storage_location} onChange={(e) => set('storage_location', e.target.value)} /></Field>
      </div>
      <h4 className="text-muted text-sm" style={{ margin: '.9rem 0 .4rem' }}>Tax & other</h4>
      <div style={grid}>
        <Field label="Taxable"><label style={{ display: 'flex', alignItems: 'center', gap: 6, height: 38 }}><input type="checkbox" checked={f.taxable} onChange={(e) => set('taxable', e.target.checked)} /> VAT applies</label></Field>
        <Field label="VAT rate (%)"><Num v={f.vat_rate} on={(v) => set('vat_rate', v)} step="0.1" /></Field>
        <Field label="Preferred supplier"><input type="text" className="form-control" value={f.preferred_supplier} onChange={(e) => set('preferred_supplier', e.target.value)} /></Field>
        <Field label="Expiry date"><input type="date" className="form-control" value={f.expiry_date || ''} onChange={(e) => set('expiry_date', e.target.value)} /></Field>
        <Field label="Warranty"><input type="text" className="form-control" value={f.warranty_period} onChange={(e) => set('warranty_period', e.target.value)} /></Field>
        {editing && <Field label="Status"><label style={{ display: 'flex', alignItems: 'center', gap: 6, height: 38 }}><input type="checkbox" checked={f.is_active} onChange={(e) => set('is_active', e.target.checked)} /> Active</label></Field>}
      </div>
      <Field label="Description" wide><textarea className="form-control" rows={2} value={f.description} onChange={(e) => set('description', e.target.value)} /></Field>
    </Modal>
  );
}

// ---- Stock adjustment (movement / physical count) --------------------------
function AdjustModal({ d, product, onClose, onSaved }) {
  const [mode, setMode] = useState('move');       // 'move' | 'count'
  const [direction, setDirection] = useState('in');
  const inReasons = d.in_reasons || [];
  const outReasons = d.out_reasons || [];
  const [reason, setReason] = useState(inReasons[0] || '');
  const [quantity, setQuantity] = useState('');
  const [counted, setCounted] = useState(String(product.stock_qty ?? 0));
  const [note, setNote] = useState('');
  const [reference, setReference] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const setDir = (dir) => { setDirection(dir); setReason((dir === 'in' ? inReasons : outReasons)[0] || ''); };
  const save = async () => {
    setBusy(true); setErr(null);
    const payload = mode === 'count'
      ? { mode: 'count', counted, note, reference }
      : { mode: 'move', direction, reason, quantity, note, reference };
    const r = await submitJson(product.adjust_url, payload);
    setBusy(false);
    if (r.ok) { onSaved(); onClose(); } else setErr(r.error || 'Could not record the movement.');
  };

  return (
    <Modal title={`Adjust stock · ${product.name}`} icon="fa-arrow-right-arrow-left" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
             <Button variant="primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Record'}</Button></>}>
      {err && <div className="alert alert-danger" role="alert">{err}</div>}
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>On hand: <strong>{product.stock_qty}</strong></p>
      <div className="btn-group" style={{ display: 'flex', gap: '.4rem', marginBottom: '.8rem' }}>
        <button type="button" className={'btn btn-sm ' + (mode === 'move' ? 'btn-primary' : 'btn-secondary')} onClick={() => setMode('move')}>Add / remove</button>
        <button type="button" className={'btn btn-sm ' + (mode === 'count' ? 'btn-primary' : 'btn-secondary')} onClick={() => setMode('count')}>Set exact count</button>
      </div>
      {mode === 'move' ? (
        <div style={{ display: 'grid', gap: '.6rem' }}>
          <div className="btn-group" style={{ display: 'flex', gap: '.4rem' }}>
            <button type="button" className={'btn btn-sm ' + (direction === 'in' ? 'btn-success' : 'btn-secondary')} onClick={() => setDir('in')}><i aria-hidden="true" className="fas fa-arrow-down" /> Stock in</button>
            <button type="button" className={'btn btn-sm ' + (direction === 'out' ? 'btn-warning' : 'btn-secondary')} onClick={() => setDir('out')}><i aria-hidden="true" className="fas fa-arrow-up" /> Stock out</button>
          </div>
          <label className="form-group" style={{ margin: 0 }}><span className="form-label">Reason</span>
            <select className="form-control" value={reason} onChange={(e) => setReason(e.target.value)}>
              {(direction === 'in' ? inReasons : outReasons).map((r) => <option key={r}>{r}</option>)}</select></label>
          <label className="form-group" style={{ margin: 0 }}><span className="form-label">Quantity</span>
            <input type="number" min="1" className="form-control" value={quantity} onChange={(e) => setQuantity(e.target.value)} /></label>
        </div>
      ) : (
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">Counted quantity</span>
          <input type="number" min="0" className="form-control" value={counted} onChange={(e) => setCounted(e.target.value)} />
          <span className="text-muted text-sm">The difference is logged as a stock-count correction.</span></label>
      )}
      <label className="form-group" style={{ margin: '.6rem 0 0' }}><span className="form-label">Reference (optional)</span>
        <input type="text" className="form-control" placeholder="Invoice / PO / note ref" value={reference} onChange={(e) => setReference(e.target.value)} /></label>
      <label className="form-group" style={{ margin: '.6rem 0 0' }}><span className="form-label">Note (optional)</span>
        <input type="text" className="form-control" value={note} onChange={(e) => setNote(e.target.value)} /></label>
    </Modal>
  );
}

// ---- Movements ledger ------------------------------------------------------
function Movements({ d }) {
  const nav = useNav();
  const a = d.applied || {};
  const o = d.options || {};
  const [f, setF] = useState({ product_id: a.product_id || '', direction: a.direction || '',
    reason: a.reason || '', from: a.from || '', to: a.to || '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const apply = () => navParams(nav.go, d.self_url, f);
  const s = d.summary || {};
  return (
    <>
      <PageHeader icon="fa-right-left" title="Inventory Movements" actions={
        <a href={d.urls.products} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-boxes-stacked" /> Products</a>} />
      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <select className="form-control" style={{ maxWidth: 200 }} value={f.product_id} onChange={(e) => set('product_id', e.target.value)}>
          <option value="">All products</option>{(o.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <select className="form-control" style={{ maxWidth: 140 }} value={f.direction} onChange={(e) => set('direction', e.target.value)}>
          <option value="">In & out</option><option value="in">Stock in</option><option value="out">Stock out</option></select>
        <select className="form-control" style={{ maxWidth: 200 }} value={f.reason} onChange={(e) => set('reason', e.target.value)}>
          <option value="">All reasons</option>{(o.reasons || []).map((r) => <option key={r}>{r}</option>)}</select>
        <input type="date" className="form-control" style={{ maxWidth: 150 }} value={f.from} onChange={(e) => set('from', e.target.value)} />
        <input type="date" className="form-control" style={{ maxWidth: 150 }} value={f.to} onChange={(e) => set('to', e.target.value)} />
        <button type="button" className="btn btn-primary" onClick={apply}><i aria-hidden="true" className="fas fa-filter" /> Apply</button>
      </div></div>
      <div className="text-muted text-sm" style={{ marginBottom: '.6rem' }}>
        <strong>{s.count || 0}</strong> movement(s) · <span style={{ color: 'var(--success)' }}>+{s.total_in || 0} in</span> · <span style={{ color: '#e74a3b' }}>−{s.total_out || 0} out</span>
      </div>
      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        {d.movements.length ? (
          <table className="data-table">
            <thead><tr><th>When</th><th>Product</th><th>Movement</th><th className="text-right">Qty</th><th className="text-right">After</th><th>Ref</th><th>By</th></tr></thead>
            <tbody>{d.movements.map((m) => (
              <tr key={m.id}>
                <td className="text-muted text-sm">{m.when}</td>
                <td>{m.product}</td>
                <td><span className={'badge ' + (m.direction === 'in' ? 'badge-success' : 'badge-warning')}>{m.direction === 'in' ? '▼ in' : '▲ out'}</span> {m.reason}{m.note && <div className="text-muted text-sm">{m.note}</div>}</td>
                <td className="text-right">{m.direction === 'in' ? '+' : '−'}{m.quantity}</td>
                <td className="text-right">{m.qty_after}</td>
                <td className="text-muted text-sm">{m.reference || '—'}</td>
                <td className="text-muted text-sm">{m.by}</td>
              </tr>
            ))}</tbody>
          </table>
        ) : <EmptyState icon="fa-right-left" title="No movements match these filters" />}
      </div></div>
    </>
  );
}

// ---- Products --------------------------------------------------------------
function Products({ d, notify }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q || '');
  const [cat, setCat] = useState(d.category || '');
  const [stock, setStock] = useState(d.stock || '');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);   // product being edited, or {} for add
  const [adjusting, setAdjusting] = useState(null);   // product being adjusted

  const restock = async (p, qty) => {
    if (!qty) return;
    setBusy(true);
    const r = await submitJson(p.restock_url, { qty });
    setBusy(false);
    if (r.ok) nav.refresh();
    else notify('error', r.error || 'Could not restock.');
  };

  const shown = d.products.filter((p) => {
    if (q && !(`${p.name} ${p.sku || ''} ${p.barcode || ''}`.toLowerCase().includes(q.toLowerCase()))) return false;
    if (cat && p.category !== cat) return false;
    if (stock === 'low' && !p.low_stock) return false;
    if (stock === 'out' && !p.out_of_stock) return false;
    return true;
  });
  const invValue = d.products.reduce((t, p) => t + (p.stock_value || 0), 0);

  return (
    <>
      <PageHeader icon="fa-boxes-stacked" title="Products & Stock" actions={<>
        <button type="button" className="btn btn-primary" onClick={() => setEditing({})}><i aria-hidden="true" className="fas fa-plus" /> Add product</button>
        {d.urls.movements && <a href={d.urls.movements} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-right-left" /> Movements</a>}
        <a href={d.urls.new_sale} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-cart-plus" /> New Sale</a>
      </>} />

      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <input type="search" className="form-control" placeholder="Search name / SKU / barcode" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
        <select className="form-control" value={cat} onChange={(e) => setCat(e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">All categories</option>{d.categories.map((c) => <option key={c}>{c}</option>)}</select>
        <select className="form-control" value={stock} onChange={(e) => setStock(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="">All stock</option><option value="low">Low stock</option><option value="out">Out of stock</option></select>
        <span className="text-muted text-sm" style={{ marginLeft: 'auto' }}>Inventory value: <strong>{naira(invValue)}</strong></span>
      </div></div>

      <div className="card">
        <div className="card-header"><h3>Products ({shown.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {shown.length ? (
            <div className="table-container">
              <table className="data-table table-stack no-mobile-scroll">
                <thead><tr><th>Name</th><th>Category</th><th className="text-right">Price</th><th className="text-right">Stock</th><th>Restock</th><th /></tr></thead>
                <tbody>{shown.map((p) => <ProductRow key={p.id} p={p} onRestock={restock} onEdit={() => setEditing(p)} onAdjust={() => setAdjusting(p)} busy={busy} />)}</tbody>
              </table>
            </div>
          ) : <EmptyState icon="fa-boxes-stacked" title="No products match" />}
        </div>
      </div>

      {editing && <ProductForm d={d} product={editing.id ? editing : null}
                               onClose={() => setEditing(null)} onSaved={() => nav.refresh()} />}
      {adjusting && <AdjustModal d={d} product={adjusting}
                                 onClose={() => setAdjusting(null)} onSaved={() => nav.refresh()} />}
    </>
  );
}

function ProductRow({ p, onRestock, onEdit, onAdjust, busy }) {
  const [qty, setQty] = useState('');
  const badge = p.out_of_stock ? <span className="badge badge-danger">Out</span>
    : p.low_stock ? <span className="badge badge-warning">Low</span> : null;
  return (
    <tr>
      <td data-label="Name">{p.name}{p.sku && <span className="text-muted text-sm"> ({p.sku})</span>}{p.brand && <span className="text-muted text-sm"> · {p.brand}</span>}</td>
      <td data-label="Category">{p.category}</td>
      <td data-label="Price" className="text-right">{naira(p.unit_price)}</td>
      <td data-label="Stock" className="text-right"><strong style={p.low_stock ? { color: '#e74a3b' } : undefined}>{p.stock_qty}</strong> {badge}</td>
      <td data-label="Restock">
        <form onSubmit={(e) => { e.preventDefault(); onRestock(p, Number(qty) || 0); }} style={{ display: 'flex', gap: '.3rem' }}>
          <input type="number" className="form-control" style={{ width: 80 }} placeholder="+qty" value={qty} onChange={(e) => setQty(e.target.value)} />
          <button className="btn btn-sm btn-secondary" disabled={busy}>Add</button>
        </form>
      </td>
      <td data-label="">
        <div style={{ display: 'flex', gap: '.3rem' }}>
          <button type="button" className="btn btn-sm btn-light" onClick={onAdjust} title="Record a stock movement or count"><i aria-hidden="true" className="fas fa-right-left" /> Adjust</button>
          <button type="button" className="btn btn-sm btn-light" onClick={onEdit}><i aria-hidden="true" className="fas fa-pen" /> Edit</button>
        </div>
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

  const pick = (s) => { setChosen(s); setP('student_id', s.id); setP('customer_name', ''); setP('customer_type', 'Student'); };
  const clearPick = () => { setChosen(null); setP('student_id', ''); };
  const chooseMode = (m) => {
    setMode(m);
    if (m === 'other') { clearPick(); setP('customer_type', pay.customer_type && pay.customer_type !== 'Student' ? pay.customer_type : 'Walk-in'); }
    else { setP('customer_name', ''); setP('customer_type', 'Student'); }
  };
  const otherTypes = (d.customer_types || ['Staff', 'Parent', 'Visitor', 'Walk-in']).filter((x) => x !== 'Student');

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
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.5rem' }}>
          <select className="form-control" aria-label="Buyer type" value={pay.customer_type || 'Walk-in'}
                  onChange={(e) => setP('customer_type', e.target.value)}>
            {otherTypes.map((tp) => <option key={tp}>{tp}</option>)}
          </select>
          <input type="text" className="form-control" placeholder="Customer name (optional)"
                 value={pay.customer_name} onChange={(e) => setP('customer_name', e.target.value)} />
        </div>
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
  const [pay, setPay] = useState({ student_id: '', customer_name: '', customer_type: 'Student', payment_method: d.methods[0] || 'Cash', amount_paid: '' });
  const [busy, setBusy] = useState(false);
  const setP = (k, v) => setPay((s) => ({ ...s, [k]: v }));
  // Price a product for the current buyer type, honouring tier prices.
  const priceOf = (p) => {
    const bt = (pay.customer_type || '').toLowerCase();
    const tier = bt === 'student' ? p.student_price : bt === 'staff' ? p.staff_price : bt === 'parent' ? p.parent_price : null;
    return tier && tier > 0 ? tier : (p.unit_price || 0);
  };
  const total = d.products.reduce((t, p) => t + priceOf(p) * (Number(qty[p.id]) || 0), 0);

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
                  <td className="text-right">{naira(priceOf(p))}{priceOf(p) !== (p.unit_price || 0) && <span className="text-muted text-sm" style={{ textDecoration: 'line-through', marginLeft: 4 }}>{naira(p.unit_price)}</span>}</td>
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
function HistoryRow({ r }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr>
        <td>
          <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'inherit' }}>
            <i aria-hidden="true" className={'fas fa-chevron-' + (open ? 'down' : 'right')} style={{ marginRight: 6 }} />
            <a href={r.receipt_url}>{r.receipt_no}</a>
          </button>
        </td>
        <td>{r.buyer}{r.class_arm && <span className="text-muted text-sm"> · {r.class_arm}</span>}</td>
        <td><span className="badge badge-secondary">{r.buyer_type}</span></td>
        <td>{r.cashier}</td>
        <td>{r.payment_method}</td>
        <td className="text-right">{r.item_count}</td>
        <td className="text-right"><strong>{naira(r.total)}</strong>{r.balance > 0 && <div className="text-sm" style={{ color: '#e74a3b' }}>owes {naira(r.balance)}</div>}</td>
        <td className="text-muted text-sm">{r.when}</td>
      </tr>
      {open && (
        <tr><td colSpan={8} style={{ background: 'var(--bg-muted, rgba(0,0,0,.02))', padding: 0 }}>
          <table className="data-table" style={{ margin: 0 }}>
            <thead><tr><th>Item</th><th className="text-right">Qty</th><th className="text-right">Unit</th><th className="text-right">Line total</th></tr></thead>
            <tbody>{r.items.map((it, i) => (
              <tr key={i}><td>{it.name}</td><td className="text-right">{it.quantity}</td>
                <td className="text-right">{naira(it.unit_price)}</td><td className="text-right">{naira(it.line_total)}</td></tr>
            ))}</tbody>
          </table>
        </td></tr>
      )}
    </>
  );
}

function History({ d }) {
  const nav = useNav();
  const a = d.applied || {};
  const o = d.options || {};
  const [f, setF] = useState({ from: a.from || '', to: a.to || '', method: a.method || '',
    cashier: a.cashier || '', buyer_type: a.buyer_type || '', product_id: a.product_id || '',
    category: a.category || '', q: a.q || '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const apply = () => navParams(nav.go, d.self_url, f);
  const reset = () => { const empty = { from: '', to: '', method: '', cashier: '', buyer_type: '', product_id: '', category: '', q: '' }; setF(empty); navParams(nav.go, d.self_url, empty); };
  const exportUrl = (fmt) => {
    const p = new URLSearchParams(); Object.entries(f).forEach(([k, v]) => { if (v) p.set(k, v); });
    p.set('format', fmt); return `${d.export_url}?${p.toString()}`;
  };
  const s = d.summary || {};

  return (
    <>
      <div className="page-header">
        <h1><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Sales History</h1>
        <div style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
          <a className="btn btn-secondary btn-sm" href={exportUrl('csv')}><i aria-hidden="true" className="fas fa-file-csv" /> CSV</a>
          <a className="btn btn-secondary btn-sm" href={exportUrl('excel')}><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => window.print()}><i aria-hidden="true" className="fas fa-print" /> Print</button>
        </div>
      </div>

      <div className="card mb-3"><div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem', alignItems: 'flex-end' }}>
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">From</span>
          <input type="date" className="form-control" value={f.from} onChange={(e) => set('from', e.target.value)} /></label>
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">To</span>
          <input type="date" className="form-control" value={f.to} onChange={(e) => set('to', e.target.value)} /></label>
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">Buyer type</span>
          <select className="form-control" value={f.buyer_type} onChange={(e) => set('buyer_type', e.target.value)}>
            <option value="">All buyers</option><option value="student">Students</option><option value="other">Staff / Walk-in</option></select></label>
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">Method</span>
          <select className="form-control" value={f.method} onChange={(e) => set('method', e.target.value)}>
            <option value="">All methods</option>{(o.methods || []).map((m) => <option key={m}>{m}</option>)}</select></label>
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">Cashier</span>
          <select className="form-control" value={f.cashier} onChange={(e) => set('cashier', e.target.value)}>
            <option value="">All cashiers</option>{(o.cashiers || []).map((cn) => <option key={cn}>{cn}</option>)}</select></label>
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">Category</span>
          <select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>
            <option value="">All categories</option>{(o.categories || []).map((cn) => <option key={cn}>{cn}</option>)}</select></label>
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">Product</span>
          <select className="form-control" value={f.product_id} onChange={(e) => set('product_id', e.target.value)}>
            <option value="">All products</option>{(o.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">Search</span>
          <input type="search" className="form-control" placeholder="Receipt or name" value={f.q} onChange={(e) => set('q', e.target.value)} /></label>
        <div style={{ display: 'flex', gap: '.4rem' }}>
          <button type="button" className="btn btn-primary" onClick={apply}><i aria-hidden="true" className="fas fa-filter" /> Apply</button>
          <button type="button" className="btn btn-light" onClick={reset}>Clear</button>
        </div>
      </div></div>

      <div className="text-muted text-sm" style={{ marginBottom: '.6rem' }}>
        <strong>{s.count || 0}</strong> sale(s) · <strong>{naira(s.revenue || 0)}</strong> · {s.units || 0} unit(s)
      </div>

      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        {d.sales.length ? (
          <table className="data-table">
            <thead><tr><th>Receipt</th><th>Buyer</th><th>Type</th><th>Cashier</th><th>Method</th><th className="text-right">Items</th><th className="text-right">Total</th><th>When</th></tr></thead>
            <tbody>{d.sales.map((r) => <HistoryRow key={r.id} r={r} />)}</tbody>
          </table>
        ) : <EmptyState icon="fa-receipt" title="No sales match these filters" />}
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

const SCREENS = { dashboard: Dashboard, products: Products, new_sale: NewSale, history: History, analytics: Analytics, movements: Movements };

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
