import React, { useState, useEffect, useRef } from 'react';
import { chartPalette } from '../lib/hooks';
import { submitJson } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { Banner, PageHeader, Empty, SectionShell, Table, Modal, Button, confirm, promptDialog } from '../components/ui';

const EmptyState = ({ icon, title, children }) => <Empty icon={icon} title={title}>{children && <p>{children}</p>}</Empty>;

// A compact metric tile; optionally a link and danger-coloured when non-zero.
function Tile({ n, label, danger, href }) {
  const body = (
    <div className="card-body">
      <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: danger ? '#e74a3b' : 'inherit' }}>{n}</div>
      <div className="text-muted text-sm">{label}</div>
    </div>
  );
  return href ? <a className="card" href={href} style={{ textDecoration: 'none', color: 'inherit' }}>{body}</a>
    : <div className="card">{body}</div>;
}

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const u = d.urls;
  return (
    <>
      <PageHeader icon="fa-cart-shopping" title="Sales & Inventory" actions={<>
        <a href={u.new_sale} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> New Sale</a>
        <a href={u.products} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-boxes-stacked" /> Products</a>
        {u.movements && <a href={u.movements} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-right-left" /> Movements</a>}
        {u.purchases && <a href={u.purchases} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-invoice" /> Purchases</a>}
        {u.suppliers && <a href={u.suppliers} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-truck-field" /> Suppliers</a>}
        {u.analytics && <a href={u.analytics} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-chart-pie" /> Analytics</a>}
        {u.reports && <a href={u.reports} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-lines" /> Reports</a>}
        {u.promos && <a href={u.promos} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-tags" /> Promos</a>}
        {u.audits && <a href={u.audits} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-clipboard-check" /> Stock Count</a>}
        {u.assets && <a href={u.assets} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-building-columns" /> Assets</a>}
      </>} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
        {[[naira(d.today_total), 'Sold today'],
          [d.week_total != null ? naira(d.week_total) : '—', 'This week'],
          [d.month_total != null ? naira(d.month_total) : '—', 'This month'],
          [d.month_profit != null ? naira(d.month_profit) : '—', 'Profit (30d)'],
          [d.inventory_value != null ? naira(d.inventory_value) : '—', 'Inventory value']].map(([v, l]) => (
          <div className="card" key={l}><div className="card-body">
            <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{v}</div>
            <div className="text-muted text-sm">{l}</div></div></div>
        ))}
        <Tile n={d.low_stock.length} label="Low stock" danger={d.low_stock.length} href={u.products + '?stock=low'} />
        <Tile n={d.out_of_stock_count || 0} label="Out of stock" danger={d.out_of_stock_count} href={u.products + '?stock=out'} />
        {u.purchases && <Tile n={d.awaiting_delivery || 0} label="Awaiting delivery" href={u.purchases} />}
        {d.expiring_soon > 0 && <Tile n={d.expiring_soon} label="Expiring / expired" danger href={u.reports ? u.reports + '?kind=expiry' : undefined} />}
      </div>

      {(d.trend || []).length > 0 && (
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-line" /> Sales trend (30 days)</h3>
          {u.analytics && <a href={u.analytics} className="btn btn-sm btn-secondary">Analytics</a>}</div>
          <div className="card-body"><TrendBars rows={d.trend} /></div></div>
      )}

      {(d.top_products || []).length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <div className="card"><div className="card-header"><h3>Top products (30d)</h3></div><div className="card-body">
            <BarList rows={d.top_products} labelKey="name" color="#4e73df" sub={(r) => `${r.units} units`} /></div></div>
          <div className="card"><div className="card-header"><h3>By category</h3></div><div className="card-body">
            <BarList rows={d.by_category || []} color={chartPalette().green} /></div></div>
          <div className="card"><div className="card-header"><h3>By payment method</h3></div><div className="card-body">
            <BarList rows={d.by_method || []} color={chartPalette().amber} /></div></div>
          <div className="card"><div className="card-header"><h3>By cashier</h3></div><div className="card-body">
            <BarList rows={d.by_cashier || []} color={chartPalette().indigo} /></div></div>
        </div>
      )}

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
    expiry_date: '', is_active: true, batch_tracked: false, ...(product || {}) };
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));

  // ── ISBN / barcode auto-fill (for books sold in the shop) ─────────────────
  const [looking, setLooking] = useState(false);
  const [lookMsg, setLookMsg] = useState(null);
  const [dupes, setDupes] = useState([]);
  const fileRef = useRef(null);
  const scanSupported = typeof window !== 'undefined' && 'BarcodeDetector' in window;
  const applyMeta = (m) => setF((s) => {
    const next = { ...s };
    ['name', 'brand', 'description'].forEach((k) => { if (m[k] && !String(next[k] || '').trim()) next[k] = m[k]; });
    if (m.category && (!next.category || next.category === (d.categories[0] || 'Other'))) next.category = m.category;
    next.barcode = m.barcode || s.barcode;
    return next;
  });
  const doLookup = async (isbnArg) => {
    const isbn = (isbnArg != null ? isbnArg : f.barcode) || '';
    if (!isbn.trim()) { setLookMsg({ tone: 'warn', text: 'Enter or scan an ISBN/barcode.' }); return; }
    setLooking(true); setLookMsg(null); setDupes([]);
    try {
      const res = await apiGet(`${d.isbn_lookup_url}?isbn=${encodeURIComponent(isbn)}`);
      setDupes(res.existing || []);
      if (res.found) { applyMeta(res.product); setLookMsg({ tone: 'success', text: 'Details filled in — set your prices and save.' }); }
      else { set('barcode', res.isbn || isbn); setLookMsg({ tone: 'warn', text: 'Not in the online catalogues (common for locally-published Nigerian books). Barcode saved — just type the name and details.' }); }
    } catch (e2) { setLookMsg({ tone: 'error', text: 'Lookup failed — type the details instead.' }); }
    finally { setLooking(false); }
  };
  const onScanFile = async (e) => {
    const file = e.target.files && e.target.files[0]; e.target.value = '';
    if (!file) return;
    if (!scanSupported) { setLookMsg({ tone: 'warn', text: 'Scanning isn’t supported here — type the ISBN.' }); return; }
    setLookMsg({ tone: 'info', text: 'Reading barcode…' });
    try {
      const bitmap = await createImageBitmap(file);
      // eslint-disable-next-line no-undef
      const detector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'code_128'] });
      const codes = await detector.detect(bitmap);
      if (codes && codes.length) { set('barcode', codes[0].rawValue); doLookup(codes[0].rawValue); }
      else setLookMsg({ tone: 'warn', text: 'Couldn’t read a barcode — try a clearer photo.' });
    } catch (e2) { setLookMsg({ tone: 'error', text: 'Could not read the image.' }); }
  };
  const restockDupe = async (dp) => {
    const n = Number(await promptDialog({ title: 'Add stock',
      label: `Add how many units to "${dp.name}"?`, inputType: 'number', defaultValue: '1' }));
    if (!n || n <= 0) return;
    const r = await submitJson(dp.restock_url, { qty: n });
    if (r.ok) { onSaved(); onClose(); } else setErr(r.error || 'Could not add stock.');
  };

  const save = async () => {
    if (!f.name.trim()) { setErr('Product name is required.'); return; }
    setBusy(true); setErr(null);
    const payload = { ...f, taxable: f.taxable ? 'on' : '', is_active: f.is_active ? 'on' : '', batch_tracked: f.batch_tracked ? 'on' : '' };
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

      {!editing && d.isbn_lookup_url && (
        <div style={{ border: '1px solid var(--primary)', borderRadius: 'var(--radius-md)', padding: '.6rem .75rem', marginBottom: '.8rem' }}>
          <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <label className="form-group" style={{ margin: 0, flex: 1, minWidth: 180 }}>
              <span className="form-label"><i aria-hidden="true" className="fas fa-barcode" /> Book? Add by ISBN / barcode</span>
              <input type="text" className="form-control" placeholder="Type or scan the ISBN" value={f.barcode}
                     onChange={(e) => set('barcode', e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); doLookup(); } }} />
            </label>
            <button type="button" className="btn btn-primary" onClick={() => doLookup()} disabled={looking}>{looking ? 'Looking…' : 'Look up'}</button>
            <button type="button" className="btn btn-secondary" onClick={() => fileRef.current && fileRef.current.click()} title={scanSupported ? 'Photo of the barcode' : 'Not supported here'}><i aria-hidden="true" className="fas fa-camera" /> Scan</button>
            <input ref={fileRef} type="file" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={onScanFile} />
          </div>
          {lookMsg && <div className={'alert alert-' + ({ success: 'success', error: 'danger', warn: 'warning', info: 'info' }[lookMsg.tone] || 'info')} role="status" style={{ margin: '.5rem 0 0' }}>{lookMsg.text}</div>}
          {dupes.length > 0 && (
            <div className="alert alert-warning" role="status" style={{ margin: '.5rem 0 0' }}>
              <strong>Already stocked?</strong>
              {dupes.map((p) => (
                <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '.5rem', alignItems: 'center', marginTop: '.4rem', flexWrap: 'wrap' }}>
                  <span>{p.name} <span className="text-muted text-sm">({p.stock_qty} in stock)</span></span>
                  <button type="button" className="btn btn-sm btn-primary" onClick={() => restockDupe(p)}><i aria-hidden="true" className="fas fa-plus" /> Add stock to this</button>
                </div>
              ))}
              <div className="text-muted text-sm" style={{ marginTop: '.3rem' }}>Or fill the form to add it as a new product.</div>
            </div>
          )}
        </div>
      )}

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
        <Field label="Batch/lot tracking"><label style={{ display: 'flex', alignItems: 'center', gap: 6, height: 38 }}><input type="checkbox" checked={f.batch_tracked} onChange={(e) => set('batch_tracked', e.target.checked)} /> Track lots + FEFO</label></Field>
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
  const [copies, setCopies] = useState(1);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);   // product being edited, or {} for add
  const [adjusting, setAdjusting] = useState(null);   // product being adjusted
  const [converting, setConverting] = useState(null);   // product being converted to an asset

  const openLabels = () => {
    const p = new URLSearchParams();
    if (cat) p.set('category', cat);
    if (stock) p.set('stock', stock);
    p.set('copies', String(copies || 1));
    window.open(`${d.labels_url}?${p.toString()}`, '_blank', 'noopener');
  };
  const genBarcodes = async () => {
    const r = await submitJson(d.generate_barcodes_url, cat ? { category: cat } : {});
    if (r.ok) { notify('success', r.message || 'Barcodes assigned.'); nav.refresh(); }
    else notify('error', r.error || 'Could not assign barcodes.');
  };

  const restock = async (p, qty, extra = {}) => {
    if (!qty) return;
    setBusy(true);
    const r = await submitJson(p.restock_url, { qty, ...extra });
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
        {d.urls.batches && <a href={d.urls.batches} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-layer-group" /> Batches</a>}
        {d.labels_url && <button type="button" className="btn btn-secondary" onClick={openLabels}><i aria-hidden="true" className="fas fa-tags" /> Print labels</button>}
        {d.generate_barcodes_url && <button type="button" className="btn btn-secondary" onClick={genBarcodes} title="Give products without a barcode a scannable internal code"><i aria-hidden="true" className="fas fa-barcode" /> Barcodes</button>}
        <a href={d.urls.new_sale} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-cart-plus" /> New Sale</a>
      </>} />

      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <input type="search" className="form-control" placeholder="Search name / SKU / barcode" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
        <select className="form-control" value={cat} onChange={(e) => setCat(e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">All categories</option>{d.categories.map((c) => <option key={c}>{c}</option>)}</select>
        <select className="form-control" value={stock} onChange={(e) => setStock(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="">All stock</option><option value="low">Low stock</option><option value="out">Out of stock</option></select>
        {d.labels_url && <label className="text-muted text-sm" style={{ display: 'flex', alignItems: 'center', gap: '.3rem' }}>Label copies
          <input type="number" min="1" max="50" className="form-control" style={{ width: 70 }} value={copies} onChange={(e) => setCopies(Math.max(1, Math.min(50, Number(e.target.value) || 1)))} /></label>}
        <span className="text-muted text-sm" style={{ marginLeft: 'auto' }}>Inventory value: <strong>{naira(invValue)}</strong></span>
      </div></div>

      <div className="card">
        <div className="card-header"><h3>Products ({shown.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {shown.length ? (
            <div className="table-container">
              <table className="data-table table-stack no-mobile-scroll">
                <thead><tr><th>Name</th><th>Category</th><th className="text-right">Price</th><th className="text-right">Stock</th><th>Restock</th><th /></tr></thead>
                <tbody>{shown.map((p) => <ProductRow key={p.id} p={p} onRestock={restock} onEdit={() => setEditing(p)} onAdjust={() => setAdjusting(p)} onConvert={d.urls.assets ? () => setConverting(p) : null} busy={busy} />)}</tbody>
              </table>
            </div>
          ) : <EmptyState icon="fa-boxes-stacked" title="No products match" />}
        </div>
      </div>

      {editing && <ProductForm d={d} product={editing.id ? editing : null}
                               onClose={() => setEditing(null)} onSaved={() => nav.refresh()} />}
      {adjusting && <AdjustModal d={d} product={adjusting}
                                 onClose={() => setAdjusting(null)} onSaved={() => nav.refresh()} />}
      {converting && <ConvertAssetModal d={d} product={converting} notify={notify}
                                        onClose={() => setConverting(null)}
                                        onSaved={(r) => { setConverting(null); if (r.redirect) nav.go(r.redirect); else nav.refresh(); }} />}
    </>
  );
}

function ConvertAssetModal({ d, product, onClose, onSaved, notify }) {
  const [f, setF] = useState({ quantity: 1, name: product.name, category: 'ICT Equipment',
    asset_tag: '', serial_number: '', custodian: '', useful_life_years: '', salvage_value: '',
    acquisition_cost: '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    if (!(Number(f.quantity) > 0)) { notify('error', 'Enter a quantity.'); return; }
    const r = await submitJson(product.convert_url, f);
    if (r.ok) onSaved(r); else notify('error', r.error || 'Could not convert.');
  };
  return (
    <Modal title={`Convert "${product.name}" to a fixed asset`} icon="fa-building-columns" size="lg" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
             <Button variant="primary" onClick={save}>Convert</Button></>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>Draws units out of stock ({product.stock_qty} on hand) and registers them in the asset register. No profit/loss impact — inventory value becomes asset value.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="Units to convert *"><input type="number" min="1" max={product.stock_qty} className="form-control" value={f.quantity} onChange={(e) => set('quantity', e.target.value)} /></Field>
        <Field label="Asset name"><input className="form-control" value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label="Category"><select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>{(d.asset_categories || []).map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="Asset tag"><input className="form-control" value={f.asset_tag} onChange={(e) => set('asset_tag', e.target.value)} placeholder="e.g. ICT-001" /></Field>
        <Field label="Serial number"><input className="form-control" value={f.serial_number} onChange={(e) => set('serial_number', e.target.value)} /></Field>
        <Field label="Custodian"><input className="form-control" value={f.custodian} onChange={(e) => set('custodian', e.target.value)} /></Field>
        <Field label="Acquisition cost (₦)"><input type="number" className="form-control" value={f.acquisition_cost} onChange={(e) => set('acquisition_cost', e.target.value)} placeholder={`stock cost ×${f.quantity}`} /></Field>
        <Field label="Useful life (yrs)"><input type="number" className="form-control" value={f.useful_life_years} onChange={(e) => set('useful_life_years', e.target.value)} placeholder="for depreciation" /></Field>
        <Field label="Salvage value (₦)"><input type="number" className="form-control" value={f.salvage_value} onChange={(e) => set('salvage_value', e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

function ProductRow({ p, onRestock, onEdit, onAdjust, onConvert, busy }) {
  const [qty, setQty] = useState('');
  const [batch, setBatch] = useState({ batch_no: '', expiry_date: '' });
  const badge = p.out_of_stock ? <span className="badge badge-danger">Out</span>
    : p.low_stock ? <span className="badge badge-warning">Low</span> : null;
  return (
    <tr>
      <td data-label="Name">{p.name}{p.sku && <span className="text-muted text-sm"> ({p.sku})</span>}{p.brand && <span className="text-muted text-sm"> · {p.brand}</span>}</td>
      <td data-label="Category">{p.category}</td>
      <td data-label="Price" className="text-right">{naira(p.unit_price)}</td>
      <td data-label="Stock" className="text-right"><strong style={p.low_stock ? { color: '#e74a3b' } : undefined}>{p.stock_qty}</strong> {badge}</td>
      <td data-label="Restock">
        <form onSubmit={(e) => { e.preventDefault(); onRestock(p, Number(qty) || 0, p.batch_tracked ? batch : {}); setQty(''); }} style={{ display: 'flex', gap: '.3rem', flexWrap: 'wrap' }}>
          <input type="number" className="form-control" style={{ width: 80 }} placeholder="+qty" value={qty} onChange={(e) => setQty(e.target.value)} />
          {p.batch_tracked && <>
            <input className="form-control" style={{ width: 90 }} placeholder="Batch no" value={batch.batch_no} onChange={(e) => setBatch((s) => ({ ...s, batch_no: e.target.value }))} />
            <input type="date" className="form-control" style={{ width: 140 }} title="Expiry" value={batch.expiry_date} onChange={(e) => setBatch((s) => ({ ...s, expiry_date: e.target.value }))} />
          </>}
          <button className="btn btn-sm btn-secondary" disabled={busy}>Add</button>
        </form>
      </td>
      <td data-label="">
        <div style={{ display: 'flex', gap: '.3rem' }}>
          {p.batch_tracked && <span className="badge badge-info" title="Batch/lot tracked">lot</span>}
          <button type="button" className="btn btn-sm btn-light" onClick={onAdjust} title="Record a stock movement or count"><i aria-hidden="true" className="fas fa-right-left" /> Adjust</button>
          {onConvert && p.stock_qty > 0 && <button type="button" className="btn btn-sm btn-light" onClick={onConvert} title="Convert units into a fixed asset"><i aria-hidden="true" className="fas fa-building-columns" /></button>}
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
  const [pay, setPay] = useState({ student_id: '', customer_name: '', customer_type: 'Student', payment_method: d.methods[0] || 'Cash', amount_paid: '', promo_code: '', discount_amount: '' });
  const [busy, setBusy] = useState(false);
  const [promoInfo, setPromoInfo] = useState(null);
  const setP = (k, v) => setPay((s) => ({ ...s, [k]: v }));
  // Price a product for the current buyer type, honouring tier prices.
  const priceOf = (p) => {
    const bt = (pay.customer_type || '').toLowerCase();
    const tier = bt === 'student' ? p.student_price : bt === 'staff' ? p.staff_price : bt === 'parent' ? p.parent_price : null;
    return tier && tier > 0 ? tier : (p.unit_price || 0);
  };
  const subtotal = d.products.reduce((t, p) => t + priceOf(p) * (Number(qty[p.id]) || 0), 0);
  const manual = Math.max(Number(pay.discount_amount) || 0, 0);
  const promoDisc = promoInfo && promoInfo.ok ? (promoInfo.discount || 0) : 0;
  const discount = Math.min(subtotal, promoDisc + manual);
  const total = Math.max(0, subtotal - discount);

  const applyPromo = async () => {
    const code = (pay.promo_code || '').trim();
    if (!code) { setPromoInfo(null); return; }
    try {
      const res = await apiGet(`${d.promo_check_url}?code=${encodeURIComponent(code)}&subtotal=${subtotal}`);
      setPromoInfo(res);
      if (!res.ok) notify('error', res.error || 'Invalid promo code.');
    } catch (e) { setPromoInfo({ ok: false, error: 'Could not check code.' }); }
  };
  // Re-price a % promo when the cart changes.
  useEffect(() => { if (promoInfo && promoInfo.ok && (pay.promo_code || '').trim()) applyPromo(); }, [subtotal]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e) => {
    e.preventDefault();
    const ids = [], qs = [];
    d.products.forEach((p) => { const n = Number(qty[p.id]) || 0; if (n > 0) { ids.push(p.id); qs.push(n); } });
    if (!ids.length) { notify('error', 'Add at least one item with a quantity.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { product_id: ids, quantity: qs, ...pay,
      promo_code: promoInfo && promoInfo.ok ? pay.promo_code : '' });
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

              {d.promo_check_url && <div className="form-group"><label className="form-label">Promo code</label>
                <div style={{ display: 'flex', gap: '.4rem' }}>
                  <input type="text" className="form-control" placeholder="Optional" value={pay.promo_code}
                         onChange={(e) => { setP('promo_code', e.target.value); setPromoInfo(null); }}
                         onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applyPromo(); } }} />
                  <button type="button" className="btn btn-secondary" onClick={applyPromo}>Apply</button>
                </div>
                {promoInfo && promoInfo.ok && <div className="text-sm" style={{ color: 'var(--success)', marginTop: 4 }}><i aria-hidden="true" className="fas fa-check" /> {promoInfo.code} — {promoInfo.description || 'discount applied'}</div>}
              </div>}
              <div className="form-group"><label className="form-label">Manual discount (₦)</label>
                <input type="number" step="0.01" min="0" className="form-control" placeholder="0" value={pay.discount_amount} onChange={(e) => setP('discount_amount', e.target.value)} /></div>

              {discount > 0 && (
                <div style={{ background: 'var(--bg-muted, rgba(0,0,0,.03))', borderRadius: 'var(--radius-md)', padding: '.6rem .8rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}><span className="text-muted">Subtotal</span><span>{naira(subtotal)}</span></div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--success)' }}><span>Discount</span><span>−{naira(discount)}</span></div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, marginTop: 2 }}><span>Total</span><span>{naira(total)}</span></div>
                </div>
              )}
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
          <BarList rows={d.top_products || []} labelKey="name" color={chartPalette().indigo} sub={(r) => `${r.units} units`} /></div></div>
        <div className="card"><div className="card-header"><h3>By category</h3></div><div className="card-body">
          <BarList rows={d.by_category || []} color={chartPalette().green} sub={(r) => `${r.units} units`} /></div></div>
        <div className="card"><div className="card-header"><h3>By payment method</h3></div><div className="card-body">
          <BarList rows={d.by_method || []} color={chartPalette().amber} sub={(r) => `${r.count} sales`} /></div></div>
        <div className="card"><div className="card-header"><h3>By cashier</h3></div><div className="card-body">
          <BarList rows={d.by_cashier || []} color={chartPalette().indigo} sub={(r) => `${r.count} sales`} /></div></div>
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

// ---- Suppliers -------------------------------------------------------------
function SupplierForm({ supplier, addUrl, onClose, onSaved }) {
  const editing = !!supplier;
  const [f, setF] = useState({ company_name: '', contact_person: '', phone: '', email: '',
    address: '', tax_id: '', bank_details: '', products_supplied: '', notes: '', ...(supplier || {}) });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(null);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    if (!f.company_name.trim()) { setErr('Company name is required.'); return; }
    setBusy(true); setErr(null);
    const r = await submitJson(editing ? supplier.edit_url : addUrl, f);
    setBusy(false);
    if (r.ok) { onSaved(); onClose(); } else setErr(r.error || 'Could not save supplier.');
  };
  const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: '.6rem' };
  return (
    <Modal title={editing ? 'Edit supplier' : 'Add supplier'} icon="fa-truck-field" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
             <Button variant="primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button></>}>
      {err && <div className="alert alert-danger" role="alert">{err}</div>}
      <div style={grid}>
        <Field label="Company name *" wide><input className="form-control" value={f.company_name} onChange={(e) => set('company_name', e.target.value)} /></Field>
        <Field label="Contact person"><input className="form-control" value={f.contact_person} onChange={(e) => set('contact_person', e.target.value)} /></Field>
        <Field label="Phone"><input className="form-control" value={f.phone} onChange={(e) => set('phone', e.target.value)} /></Field>
        <Field label="Email"><input className="form-control" value={f.email} onChange={(e) => set('email', e.target.value)} /></Field>
        <Field label="Tax ID"><input className="form-control" value={f.tax_id} onChange={(e) => set('tax_id', e.target.value)} /></Field>
        <Field label="Address" wide><input className="form-control" value={f.address} onChange={(e) => set('address', e.target.value)} /></Field>
        <Field label="Bank details" wide><input className="form-control" value={f.bank_details} onChange={(e) => set('bank_details', e.target.value)} /></Field>
        <Field label="Products supplied" wide><input className="form-control" value={f.products_supplied} onChange={(e) => set('products_supplied', e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

function Suppliers({ d }) {
  const nav = useNav();
  const [editing, setEditing] = useState(null);
  return (
    <>
      <PageHeader icon="fa-truck-field" title="Suppliers" actions={<>
        <button type="button" className="btn btn-primary" onClick={() => setEditing({})}><i aria-hidden="true" className="fas fa-plus" /> Add supplier</button>
        <a href={d.urls.purchases} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-invoice" /> Purchases</a>
      </>} />
      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        {d.suppliers.length ? (
          <table className="data-table"><thead><tr><th>Supplier</th><th>Contact</th><th className="text-right">Orders</th><th className="text-right">Received</th><th className="text-right">Paid</th><th className="text-right">Outstanding</th><th /></tr></thead>
            <tbody>{d.suppliers.map((s) => (
              <tr key={s.id}>
                <td><a href={s.url}>{s.company_name}</a>{s.phone && <div className="text-muted text-sm">{s.phone}</div>}</td>
                <td>{s.contact_person || '—'}</td>
                <td className="text-right">{s.orders}</td>
                <td className="text-right">{naira(s.received_value)}</td>
                <td className="text-right">{naira(s.paid)}</td>
                <td className="text-right"><strong style={s.outstanding > 0 ? { color: '#e74a3b' } : undefined}>{naira(s.outstanding)}</strong></td>
                <td><button type="button" className="btn btn-sm btn-light" onClick={() => setEditing(s)}><i aria-hidden="true" className="fas fa-pen" /></button></td>
              </tr>
            ))}</tbody></table>
        ) : <EmptyState icon="fa-truck-field" title="No suppliers yet">Add your first supplier.</EmptyState>}
      </div></div>
      {editing && <SupplierForm supplier={editing.id ? editing : null} addUrl={d.add_url}
                                onClose={() => setEditing(null)} onSaved={() => nav.refresh()} />}
    </>
  );
}

function SupplierDetail({ d, notify }) {
  const nav = useNav();
  const s = d.supplier; const st = d.stats || {};
  const [pay, setPay] = useState({ amount: '', method: (d.methods || ['Cash'])[0], reference: '', note: '' });
  const setP = (k, v) => setPay((x) => ({ ...x, [k]: v }));
  const doPay = async () => {
    if (!(Number(pay.amount) > 0)) { notify('error', 'Enter an amount.'); return; }
    const r = await submitJson(d.pay_url, pay);
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not record payment.');
  };
  const tiles = [[st.orders, 'Orders'], [naira(st.received_value), 'Received value'],
    [naira(st.paid), 'Paid'], [naira(st.outstanding), 'Outstanding']];
  return (
    <>
      <PageHeader icon="fa-truck-field" title={s.company_name} actions={
        <a href={d.urls.suppliers} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Suppliers</a>} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.6rem', marginBottom: '1rem' }}>
        {tiles.map(([v, l]) => <div className="card" key={l}><div className="card-body"><div style={{ fontSize: 'var(--text-lg)', fontWeight: 700 }}>{v}</div><div className="text-muted text-sm">{l}</div></div></div>)}
      </div>
      <div className="card mb-3"><div className="card-header"><h3>Record payment</h3></div>
        <div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <input type="number" className="form-control" style={{ maxWidth: 140 }} placeholder="Amount" value={pay.amount} onChange={(e) => setP('amount', e.target.value)} />
          <select className="form-control" style={{ maxWidth: 150 }} value={pay.method} onChange={(e) => setP('method', e.target.value)}>{(d.methods || []).map((m) => <option key={m}>{m}</option>)}</select>
          <input type="text" className="form-control" style={{ maxWidth: 160 }} placeholder="Reference" value={pay.reference} onChange={(e) => setP('reference', e.target.value)} />
          <button type="button" className="btn btn-primary" onClick={doPay}><i aria-hidden="true" className="fas fa-money-bill" /> Pay</button>
        </div></div>
      <div className="card mb-3"><div className="card-header"><h3>Purchase orders</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.orders.length ? <table className="data-table"><thead><tr><th>PO</th><th>Status</th><th className="text-right">Total</th><th>When</th></tr></thead>
            <tbody>{d.orders.map((po) => <tr key={po.id}><td><a href={po.url}>{po.po_number}</a></td><td>{po.status}</td><td className="text-right">{naira(po.total)}</td><td className="text-muted text-sm">{po.created_at}</td></tr>)}</tbody></table>
            : <EmptyState icon="fa-file-invoice" title="No purchase orders" />}
        </div></div>
      <div className="card"><div className="card-header"><h3>Payments</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.payments.length ? <table className="data-table"><thead><tr><th>When</th><th>Method</th><th>Ref</th><th className="text-right">Amount</th></tr></thead>
            <tbody>{d.payments.map((p) => <tr key={p.id}><td className="text-muted text-sm">{p.when}</td><td>{p.method}</td><td>{p.reference || '—'}</td><td className="text-right">{naira(p.amount)}</td></tr>)}</tbody></table>
            : <EmptyState icon="fa-money-bill" title="No payments yet" />}
        </div></div>
    </>
  );
}

// ---- Purchase orders -------------------------------------------------------
function PurchaseForm({ d, onClose, onSaved }) {
  const [supplierId, setSupplierId] = useState('');
  const [expected, setExpected] = useState('');
  const [notes, setNotes] = useState('');
  const [rows, setRows] = useState([{ product_id: '', description: '', quantity: '', unit_cost: '' }]);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(null);
  const setRow = (i, k, v) => setRows((rs) => rs.map((r, j) => {
    if (j !== i) return r;
    const nr = { ...r, [k]: v };
    if (k === 'product_id' && v) { const p = (d.products || []).find((x) => String(x.id) === String(v)); if (p) { nr.description = p.name; if (!nr.unit_cost) nr.unit_cost = p.cost_price; } }
    return nr;
  }));
  const total = rows.reduce((t, r) => t + (Number(r.quantity) || 0) * (Number(r.unit_cost) || 0), 0);
  const submit = async (mode) => {
    if (!supplierId) { setErr('Choose a supplier.'); return; }
    const items = rows.filter((r) => (Number(r.quantity) || 0) > 0 && (r.description || r.product_id));
    if (!items.length) { setErr('Add at least one item.'); return; }
    setBusy(true); setErr(null);
    const r = await submitJson(d.new_url, { supplier_id: supplierId, expected_date: expected, notes, submit: mode, items });
    setBusy(false);
    if (r.ok) { onSaved(r); onClose(); } else setErr(r.error || 'Could not create order.');
  };
  return (
    <Modal title="New purchase order" icon="fa-file-invoice" size="lg" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
             <Button variant="light" onClick={() => submit('draft')} disabled={busy}>Save draft</Button>
             <Button variant="primary" onClick={() => submit('submit')} disabled={busy}>Submit for approval</Button></>}>
      {err && <div className="alert alert-danger" role="alert">{err}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: '.6rem', marginBottom: '.8rem' }}>
        <Field label="Supplier *"><select className="form-control" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}><option value="">Select…</option>{(d.suppliers || []).map((s) => <option key={s.id} value={s.id}>{s.company_name}</option>)}</select></Field>
        <Field label="Expected delivery"><input type="date" className="form-control" value={expected} onChange={(e) => setExpected(e.target.value)} /></Field>
        <Field label="Notes" wide><input className="form-control" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      </div>
      <table className="data-table"><thead><tr><th>Product</th><th>Description</th><th style={{ width: 80 }}>Qty</th><th style={{ width: 110 }}>Unit cost</th><th /></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}>
            <td><select className="form-control" value={r.product_id} onChange={(e) => setRow(i, 'product_id', e.target.value)}><option value="">— New / free —</option>{(d.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></td>
            <td><input className="form-control" value={r.description} onChange={(e) => setRow(i, 'description', e.target.value)} /></td>
            <td><input type="number" min="1" className="form-control" value={r.quantity} onChange={(e) => setRow(i, 'quantity', e.target.value)} /></td>
            <td><input type="number" step="0.01" className="form-control" value={r.unit_cost} onChange={(e) => setRow(i, 'unit_cost', e.target.value)} /></td>
            <td>{rows.length > 1 && <button type="button" className="btn btn-sm btn-light" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>×</button>}</td>
          </tr>
        ))}</tbody></table>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '.5rem' }}>
        <button type="button" className="btn btn-sm btn-light" onClick={() => setRows((rs) => [...rs, { product_id: '', description: '', quantity: '', unit_cost: '' }])}><i aria-hidden="true" className="fas fa-plus" /> Add line</button>
        <strong>Total: {naira(total)}</strong>
      </div>
    </Modal>
  );
}

function Purchases({ d }) {
  const nav = useNav();
  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState((d.applied || {}).status || '');
  const apply = (st) => { setStatus(st); navParams(nav.go, d.self_url, { status: st, supplier_id: (d.applied || {}).supplier_id || '' }); };
  return (
    <>
      <PageHeader icon="fa-file-invoice" title="Purchase Orders" actions={<>
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}><i aria-hidden="true" className="fas fa-plus" /> New PO</button>
        <a href={d.urls.suppliers} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-truck-field" /> Suppliers</a>
      </>} />
      {d.awaiting_delivery > 0 && <div className="alert alert-info"><i aria-hidden="true" className="fas fa-truck" /> {d.awaiting_delivery} order(s) awaiting delivery.</div>}
      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', alignItems: 'flex-end' }}>
        <select className="form-control" style={{ maxWidth: 220 }} value={status} onChange={(e) => apply(e.target.value)}>
          <option value="">All statuses</option>{(d.statuses || []).map((st) => <option key={st}>{st}</option>)}</select>
      </div></div>
      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        {d.orders.length ? <table className="data-table"><thead><tr><th>PO</th><th>Supplier</th><th>Status</th><th className="text-right">Total</th><th>Expected</th><th>Created</th></tr></thead>
          <tbody>{d.orders.map((po) => <tr key={po.id}><td><a href={po.url}>{po.po_number}</a></td><td>{po.supplier}</td><td><StatusBadge s={po.status} /></td><td className="text-right">{naira(po.total)}</td><td className="text-muted text-sm">{po.expected_date || '—'}</td><td className="text-muted text-sm">{po.created_at}</td></tr>)}</tbody></table>
          : <EmptyState icon="fa-file-invoice" title="No purchase orders" />}
      </div></div>
      {creating && <PurchaseForm d={d} onClose={() => setCreating(false)} onSaved={(r) => { if (r.redirect) nav.go(r.redirect); else nav.refresh(); }} />}
    </>
  );
}

function StatusBadge({ s }) {
  const tone = s === 'Received' ? 'badge-success' : s === 'Cancelled' ? 'badge-danger'
    : s === 'Partially Received' ? 'badge-info' : s === 'Approved' || s === 'Ordered' ? 'badge-primary' : 'badge-warning';
  return <span className={'badge ' + tone}>{s}</span>;
}

function PurchaseDetail({ d, notify }) {
  const nav = useNav();
  const po = d.po; const u = d.urls;
  const [recv, setRecv] = useState({});
  const [invoice, setInvoice] = useState(po.invoice_number || '');
  const act = async (url, body) => { const r = await submitJson(url, body || {}); if (r.ok) nav.refresh(); else notify('error', r.error || 'Action failed.'); };
  const doReceive = () => {
    const items = d.items.filter((it) => Number(recv[it.id]) > 0).map((it) => ({ item_id: it.id, receive_qty: Number(recv[it.id]) }));
    if (!items.length) { notify('error', 'Enter quantities to receive.'); return; }
    act(u.receive, { invoice_number: invoice, items });
  };
  const canApprove = (po.status === 'Draft' || po.status === 'Pending Approval') && d.can_approve !== false;
  const canReceive = ['Approved', 'Ordered', 'Partially Received'].includes(po.status);
  return (
    <>
      <PageHeader icon="fa-file-invoice" title={po.po_number} actions={<>
        <a href={u.supplier} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-truck-field" /> Supplier</a>
        <a href={u.purchases} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> All POs</a>
      </>} />
      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <StatusBadge s={po.status} />
        <span className="text-muted text-sm">Supplier: <strong>{po.supplier}</strong></span>
        <span className="text-muted text-sm">Total: <strong>{naira(po.total)}</strong></span>
        {po.expected_date && <span className="text-muted text-sm">Expected: {po.expected_date}</span>}
        {po.approved_by && <span className="text-muted text-sm">Approved by {po.approved_by}</span>}
        <span style={{ marginLeft: 'auto', display: 'flex', gap: '.4rem' }}>
          {canApprove && <button type="button" className="btn btn-success btn-sm" onClick={() => act(u.approve)}><i aria-hidden="true" className="fas fa-check" /> Approve</button>}
          {po.is_open && <button type="button" className="btn btn-danger btn-sm" onClick={() => act(u.cancel)}><i aria-hidden="true" className="fas fa-ban" /> Cancel</button>}
        </span>
      </div></div>
      <div className="card"><div className="card-header"><h3>Items</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table"><thead><tr><th>Item</th><th className="text-right">Ordered</th><th className="text-right">Received</th><th className="text-right">Outstanding</th><th className="text-right">Unit cost</th>{canReceive && <th style={{ width: 110 }}>Receive</th>}</tr></thead>
            <tbody>{d.items.map((it) => (
              <tr key={it.id}>
                <td>{it.description}</td><td className="text-right">{it.quantity}</td>
                <td className="text-right">{it.quantity_received}</td><td className="text-right">{it.outstanding}</td>
                <td className="text-right">{naira(it.unit_cost)}</td>
                {canReceive && <td>{it.outstanding > 0 ? <input type="number" min="0" max={it.outstanding} className="form-control" value={recv[it.id] || ''} onChange={(e) => setRecv((s) => ({ ...s, [it.id]: e.target.value }))} /> : <span className="text-muted text-sm">done</span>}</td>}
              </tr>
            ))}</tbody></table>
        </div>
        {canReceive && <div className="card-body" style={{ display: 'flex', gap: '.5rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label className="form-group" style={{ margin: 0 }}><span className="form-label">Invoice no. (optional)</span><input className="form-control" value={invoice} onChange={(e) => setInvoice(e.target.value)} /></label>
          <button type="button" className="btn btn-primary" onClick={doReceive}><i aria-hidden="true" className="fas fa-truck-ramp-box" /> Receive goods</button>
        </div>}
      </div>
    </>
  );
}

// ---- Reports ---------------------------------------------------------------
function Reports({ d }) {
  const nav = useNav();
  const r = d.report || { columns: [], rows: [] };
  const [from, setFrom] = useState(d.from || '');
  const [to, setTo] = useState(d.to || '');
  const [category, setCategory] = useState(d.category || '');
  const go = (extra) => navParams(nav.go, d.self_url, { kind: d.kind, from, to, category, ...extra });
  const pick = (kind) => navParams(nav.go, d.self_url, { kind, from, to, category });
  const cell = (row, col) => {
    const v = row[col.key];
    return col.money ? naira(v || 0) : (v === '' || v == null ? '—' : v);
  };
  const exportUrl = (fmt) => {
    const p = new URLSearchParams({ kind: d.kind, format: fmt });
    if (from) p.set('from', from); if (to) p.set('to', to); if (category) p.set('category', category);
    return `${d.export_url}?${p.toString()}`;
  };
  return (
    <>
      <PageHeader icon="fa-file-lines" title="Reports" actions={<>
        <a className="btn btn-secondary btn-sm" href={exportUrl('csv')}><i aria-hidden="true" className="fas fa-file-csv" /> CSV</a>
        <a className="btn btn-secondary btn-sm" href={exportUrl('excel')}><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => window.print()}><i aria-hidden="true" className="fas fa-print" /> Print</button>
        <a href={d.urls.dashboard} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>
      </>} />

      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
        {(d.report_kinds || []).map((k) => (
          <button type="button" key={k.key} className={'btn btn-sm ' + (k.key === d.kind ? 'btn-primary' : 'btn-light')} onClick={() => pick(k.key)}>{k.label}</button>
        ))}
      </div></div>

      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        {d.is_period && <>
          <label className="form-group" style={{ margin: 0 }}><span className="form-label">From</span><input type="date" className="form-control" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label className="form-group" style={{ margin: 0 }}><span className="form-label">To</span><input type="date" className="form-control" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        </>}
        <label className="form-group" style={{ margin: 0 }}><span className="form-label">Category</span>
          <select className="form-control" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All</option>{(d.categories || []).map((c) => <option key={c}>{c}</option>)}</select></label>
        <button type="button" className="btn btn-primary" onClick={() => go()}><i aria-hidden="true" className="fas fa-filter" /> Apply</button>
      </div></div>

      <div className="card"><div className="card-header"><h3>{r.title} ({r.rows.length})</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          {r.rows.length ? (
            <table className="data-table">
              <thead><tr>{r.columns.map((c) => <th key={c.key} className={c.align === 'right' ? 'text-right' : undefined}>{c.label}</th>)}</tr></thead>
              <tbody>{r.rows.map((row, i) => (
                <tr key={i}>{r.columns.map((c) => <td key={c.key} className={c.align === 'right' ? 'text-right' : undefined}>{cell(row, c)}</td>)}</tr>
              ))}</tbody>
              {r.totals && <tfoot><tr>{r.columns.map((c, i) => (
                <td key={c.key} className={c.align === 'right' ? 'text-right' : undefined}>
                  {i === 0 ? <strong>Total</strong> : (r.totals[c.key] != null ? <strong>{c.money ? naira(r.totals[c.key]) : r.totals[c.key]}</strong> : '')}
                </td>
              ))}</tr></tfoot>}
            </table>
          ) : <EmptyState icon="fa-file-lines" title="Nothing to report for this selection" />}
        </div></div>
    </>
  );
}

// ---- Promo codes -----------------------------------------------------------
function Promos({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ code: '', description: '', kind: 'percent', value: '',
    min_purchase: '', category: '', expires_on: '', usage_limit: '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const add = async () => {
    if (!f.code.trim()) { notify('error', 'Enter a code.'); return; }
    const r = await submitJson(d.add_url, f);
    if (r.ok) { setF({ code: '', description: '', kind: 'percent', value: '', min_purchase: '', category: '', expires_on: '', usage_limit: '' }); nav.refresh(); }
    else notify('error', r.error || 'Could not add code.');
  };
  const toggle = async (p) => { const r = await submitJson(p.toggle_url, {}); if (r.ok) nav.refresh(); else notify('error', r.error || 'Failed.'); };
  return (
    <>
      <PageHeader icon="fa-tags" title="Discounts & Promo Codes" actions={
        <a href={d.urls.dashboard} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>} />
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> New promo code</h3></div>
        <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.6rem', alignItems: 'flex-end' }}>
          <Field label="Code *"><input className="form-control" value={f.code} onChange={(e) => set('code', e.target.value.toUpperCase())} /></Field>
          <Field label="Type"><select className="form-control" value={f.kind} onChange={(e) => set('kind', e.target.value)}><option value="percent">Percent %</option><option value="fixed">Fixed ₦</option></select></Field>
          <Field label={f.kind === 'percent' ? 'Percent' : 'Amount (₦)'}><input type="number" className="form-control" value={f.value} onChange={(e) => set('value', e.target.value)} /></Field>
          <Field label="Min purchase (₦)"><input type="number" className="form-control" value={f.min_purchase} onChange={(e) => set('min_purchase', e.target.value)} /></Field>
          <Field label="Category (optional)"><select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}><option value="">Any</option>{(d.categories || []).map((c) => <option key={c}>{c}</option>)}</select></Field>
          <Field label="Expires"><input type="date" className="form-control" value={f.expires_on} onChange={(e) => set('expires_on', e.target.value)} /></Field>
          <Field label="Usage limit"><input type="number" className="form-control" placeholder="∞" value={f.usage_limit} onChange={(e) => set('usage_limit', e.target.value)} /></Field>
          <Field label="Description"><input className="form-control" value={f.description} onChange={(e) => set('description', e.target.value)} /></Field>
          <button type="button" className="btn btn-primary" onClick={add}>Add</button>
        </div></div>
      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        {d.promos.length ? (
          <table className="data-table"><thead><tr><th>Code</th><th>Discount</th><th>Rules</th><th className="text-right">Used</th><th>Status</th><th /></tr></thead>
            <tbody>{d.promos.map((p) => (
              <tr key={p.id}>
                <td><strong>{p.code}</strong>{p.description && <div className="text-muted text-sm">{p.description}</div>}</td>
                <td>{p.kind === 'percent' ? `${p.value}%` : naira(p.value)}</td>
                <td className="text-muted text-sm">{p.min_purchase > 0 ? `min ${naira(p.min_purchase)} · ` : ''}{p.category || 'any category'}{p.expires_on ? ` · till ${p.expires_on}` : ''}{p.usage_limit != null ? ` · limit ${p.usage_limit}` : ''}</td>
                <td className="text-right">{p.used_count}</td>
                <td><span className={'badge ' + (p.is_active ? 'badge-success' : 'badge-secondary')}>{p.is_active ? 'Active' : 'Off'}</span></td>
                <td><button type="button" className="btn btn-sm btn-light" onClick={() => toggle(p)}>{p.is_active ? 'Deactivate' : 'Activate'}</button></td>
              </tr>
            ))}</tbody></table>
        ) : <EmptyState icon="fa-tags" title="No promo codes yet">Create one above.</EmptyState>}
      </div></div>
    </>
  );
}

// ---- Stock audits (physical count) -----------------------------------------
function Audits({ d, notify }) {
  const nav = useNav();
  const [scope, setScope] = useState({ category: '', location: '', note: '' });
  const set = (k, v) => setScope((s) => ({ ...s, [k]: v }));
  const start = async () => {
    const r = await submitJson(d.new_url, scope);
    if (r.ok) { if (r.redirect) nav.go(r.redirect); else nav.refresh(); }
    else notify('error', r.error || 'Could not start a count.');
  };
  return (
    <>
      <PageHeader icon="fa-clipboard-check" title="Stock Counts" actions={
        <a href={d.urls.dashboard} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>} />
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> New stock count</h3></div>
        <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: '.6rem', alignItems: 'flex-end' }}>
          <Field label="Category (optional)"><select className="form-control" value={scope.category} onChange={(e) => set('category', e.target.value)}><option value="">All categories</option>{(d.categories || []).map((c) => <option key={c}>{c}</option>)}</select></Field>
          <Field label="Location (optional)"><select className="form-control" value={scope.location} onChange={(e) => set('location', e.target.value)}><option value="">All locations</option>{(d.locations || []).map((l) => <option key={l}>{l}</option>)}</select></Field>
          <Field label="Note"><input className="form-control" value={scope.note} onChange={(e) => set('note', e.target.value)} placeholder="e.g. End-of-term count" /></Field>
          <button type="button" className="btn btn-primary" onClick={start}><i aria-hidden="true" className="fas fa-clipboard-list" /> Start count</button>
        </div></div>
      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        {d.audits.length ? (
          <table className="data-table"><thead><tr><th>Ref</th><th>Scope</th><th>Status</th><th className="text-right">Counted</th><th className="text-right">Variance</th><th>By</th><th>Date</th></tr></thead>
            <tbody>{d.audits.map((a) => (
              <tr key={a.id}>
                <td><a href={a.url}>{a.reference}</a>{a.note && <div className="text-muted text-sm">{a.note}</div>}</td>
                <td>{a.scope}</td>
                <td><AuditBadge s={a.status} /></td>
                <td className="text-right">{a.counted}/{a.items}</td>
                <td className={'text-right ' + (a.variance_value < 0 ? 'text-danger' : a.variance_value > 0 ? 'text-success' : '')}>{a.status === 'Completed' ? naira(a.variance_value) : '—'}</td>
                <td className="text-muted text-sm">{a.approved_by || a.started_by}</td>
                <td className="text-muted text-sm">{a.when}</td>
              </tr>
            ))}</tbody></table>
        ) : <EmptyState icon="fa-clipboard-check" title="No stock counts yet">Start one above to reconcile physical stock against the system.</EmptyState>}
      </div></div>
    </>
  );
}

function AuditBadge({ s }) {
  const tone = s === 'Completed' ? 'badge-success' : s === 'Cancelled' ? 'badge-danger' : 'badge-warning';
  return <span className={'badge ' + tone}>{s}</span>;
}

function AuditDetail({ d, notify }) {
  const nav = useNav();
  const open = d.status === 'Counting';
  // Local edits to counted quantities, keyed by item id.
  const [counts, setCounts] = useState(() => {
    const m = {};
    d.items.forEach((i) => { m[i.id] = i.counted_qty == null ? '' : String(i.counted_qty); });
    return m;
  });
  const setCount = (id, v) => setCounts((s) => ({ ...s, [id]: v.replace(/[^0-9]/g, '') }));
  const payload = () => d.items.map((i) => ({ item_id: i.id, counted_qty: counts[i.id] === '' ? null : Number(counts[i.id]) }));
  // Live variance preview from the currently entered numbers.
  const preview = d.items.reduce((acc, i) => {
    const c = counts[i.id];
    if (c === '' || c == null) return acc;
    return acc + (Number(c) - i.system_qty) * (i.unit_cost || 0);
  }, 0);
  const countedN = d.items.filter((i) => counts[i.id] !== '' && counts[i.id] != null).length;
  const save = async () => {
    const r = await submitJson(d.save_url, { counts: payload() });
    if (r.ok) notify('success', 'Counts saved.'); else notify('error', r.error || 'Save failed.');
  };
  const complete = async () => {
    if (!await confirm({ title: 'Sign off count', tone: 'primary', confirmText: 'Sign off',
      message: 'Sign off this count? Stock will be corrected to the counted quantities and the net variance posted to Finance.' })) return;
    const r = await submitJson(d.complete_url, { counts: payload() });
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not complete.');
  };
  const cancel = async () => {
    if (!await confirm({ title: 'Cancel count', tone: 'danger', confirmText: 'Cancel count',
      cancelText: 'Keep', message: 'Cancel this count? No stock will change.' })) return;
    const r = await submitJson(d.cancel_url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not cancel.');
  };
  return (
    <>
      <PageHeader icon="fa-clipboard-check" title={d.reference} actions={<>
        <a className="btn btn-secondary btn-sm" href={d.export_url}><i aria-hidden="true" className="fas fa-file-excel" /> Export</a>
        <a href={d.urls.audits} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> All counts</a>
      </>} />
      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <AuditBadge s={d.status} />
        <span className="text-muted text-sm">Scope: <strong>{d.scope}</strong></span>
        <span className="text-muted text-sm">Started by {d.started_by}</span>
        {d.approved_by && <span className="text-muted text-sm">Signed off by {d.approved_by}</span>}
        <span style={{ marginLeft: 'auto' }} className="text-sm">
          {open ? <>Preview net variance: <strong className={preview < 0 ? 'text-danger' : preview > 0 ? 'text-success' : ''}>{naira(preview)}</strong> · {countedN}/{d.items.length} counted</>
            : <>Net variance: <strong className={d.variance_value < 0 ? 'text-danger' : d.variance_value > 0 ? 'text-success' : ''}>{naira(d.variance_value)}</strong></>}
        </span>
      </div></div>
      {open && <div className="alert alert-info"><i aria-hidden="true" className="fas fa-circle-info" /> Enter the physical count for each item, then Save (to continue later) or Sign off (to apply corrections). Blank = not counted yet.</div>}
      <div className="card"><div className="card-header"><h3>Items ({d.items.length})</h3>
        {open && <span style={{ display: 'flex', gap: '.4rem' }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={save}><i aria-hidden="true" className="fas fa-floppy-disk" /> Save</button>
          {d.can_signoff !== false && <button type="button" className="btn btn-success btn-sm" onClick={complete}><i aria-hidden="true" className="fas fa-check-double" /> Sign off</button>}
          <button type="button" className="btn btn-danger btn-sm" onClick={cancel}><i aria-hidden="true" className="fas fa-ban" /> Cancel</button>
        </span>}</div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table"><thead><tr><th>Product</th><th>Category</th><th className="text-right">System</th><th style={{ width: 110 }} className="text-right">Counted</th><th className="text-right">Variance</th><th className="text-right">Value</th></tr></thead>
            <tbody>{d.items.map((i) => {
              const c = counts[i.id];
              const has = c !== '' && c != null;
              const vq = has ? Number(c) - i.system_qty : null;
              const vv = has ? vq * (i.unit_cost || 0) : null;
              return (
                <tr key={i.id}>
                  <td>{i.product}</td>
                  <td className="text-muted text-sm">{i.category}</td>
                  <td className="text-right">{i.system_qty}</td>
                  <td className="text-right">{open
                    ? <input type="text" inputMode="numeric" className="form-control" style={{ textAlign: 'right' }} value={c} onChange={(e) => setCount(i.id, e.target.value)} />
                    : (i.counted_qty == null ? '—' : i.counted_qty)}</td>
                  <td className={'text-right ' + (vq < 0 ? 'text-danger' : vq > 0 ? 'text-success' : '')}>{vq == null ? '—' : (vq > 0 ? '+' : '') + vq}</td>
                  <td className={'text-right ' + (vv < 0 ? 'text-danger' : vv > 0 ? 'text-success' : '')}>{vv == null ? '—' : naira(vv)}</td>
                </tr>
              );
            })}</tbody></table>
        </div>
      </div>
    </>
  );
}

// ---- Fixed assets ----------------------------------------------------------
function Assets({ d, notify }) {
  const nav = useNav();
  const s = d.summary || {};
  const [q, setQ] = useState(d.q || '');
  const [cat, setCat] = useState(d.category || '');
  const [status, setStatus] = useState(d.status || '');
  const [editing, setEditing] = useState(null);   // asset being edited, or {} for add
  const [disposing, setDisposing] = useState(null);
  const shown = d.assets.filter((a) => {
    if (q && !(`${a.name} ${a.asset_tag} ${a.serial_number}`.toLowerCase().includes(q.toLowerCase()))) return false;
    if (cat && a.category !== cat) return false;
    if (status && a.status !== status) return false;
    return true;
  });
  const badge = (st) => {
    const tone = st === 'In Use' ? 'badge-success' : st === 'Disposed' ? 'badge-secondary'
      : st === 'Under Repair' ? 'badge-warning' : st === 'Lost' ? 'badge-danger' : 'badge-info';
    return <span className={'badge ' + tone}>{st}</span>;
  };
  return (
    <>
      <PageHeader icon="fa-building-columns" title="Fixed Assets" actions={<>
        <button type="button" className="btn btn-primary" onClick={() => setEditing({})}><i aria-hidden="true" className="fas fa-plus" /> Register asset</button>
        <a className="btn btn-secondary" href={d.export_url}><i aria-hidden="true" className="fas fa-file-excel" /> Export</a>
        <a href={d.urls.products} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-boxes-stacked" /> Products</a>
      </>} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
        <Tile n={s.count || 0} label="Active assets" />
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{naira(s.total_cost || 0)}</div><div className="text-muted text-sm">Acquisition cost</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{naira(s.total_book || 0)}</div><div className="text-muted text-sm">Net book value</div></div></div>
        <Tile n={s.disposed || 0} label="Disposed" />
      </div>
      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <input type="search" className="form-control" placeholder="Search name / tag / serial" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
        <select className="form-control" value={cat} onChange={(e) => setCat(e.target.value)} style={{ maxWidth: 200 }}><option value="">All categories</option>{d.categories.map((c) => <option key={c}>{c}</option>)}</select>
        <select className="form-control" value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 160 }}><option value="">All statuses</option>{d.statuses.map((st) => <option key={st}>{st}</option>)}</select>
      </div></div>
      <div className="card"><div className="card-header"><h3>Assets ({shown.length})</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          {shown.length ? (
            <table className="data-table"><thead><tr><th>Asset</th><th>Category</th><th className="text-right">Cost</th><th className="text-right">Book value</th><th>Custodian</th><th>Status</th><th /></tr></thead>
              <tbody>{shown.map((a) => (
                <tr key={a.id}>
                  <td><strong>{a.name}</strong>{a.asset_tag && <span className="text-muted text-sm"> · {a.asset_tag}</span>}{a.from_product && <span className="badge badge-light" title="Converted from inventory" style={{ marginLeft: 4 }}>stock</span>}{a.serial_number && <div className="text-muted text-sm">SN {a.serial_number}</div>}</td>
                  <td>{a.category}</td>
                  <td className="text-right">{naira(a.acquisition_cost)}</td>
                  <td className="text-right">{naira(a.book_value)}{a.annual_depreciation > 0 && <div className="text-muted text-sm">−{naira(a.annual_depreciation)}/yr</div>}</td>
                  <td className="text-muted text-sm">{a.custodian || '—'}{a.location && <div>{a.location}</div>}</td>
                  <td>{badge(a.status)}</td>
                  <td><div style={{ display: 'flex', gap: '.3rem' }}>
                    <button type="button" className="btn btn-sm btn-light" onClick={() => setEditing(a)}><i aria-hidden="true" className="fas fa-pen" /></button>
                    {!a.is_disposed && <button type="button" className="btn btn-sm btn-light" onClick={() => setDisposing(a)} title="Dispose / retire"><i aria-hidden="true" className="fas fa-box-archive" /></button>}
                  </div></td>
                </tr>
              ))}</tbody></table>
          ) : <EmptyState icon="fa-building-columns" title="No assets registered">Register one, or convert stock from the Products screen.</EmptyState>}
        </div></div>
      {editing && <AssetForm d={d} asset={editing.id ? editing : null} notify={notify}
                             onClose={() => setEditing(null)} onSaved={() => { setEditing(null); nav.refresh(); }} />}
      {disposing && <DisposeModal asset={disposing} notify={notify}
                                  onClose={() => setDisposing(null)} onSaved={() => { setDisposing(null); nav.refresh(); }} />}
    </>
  );
}

function AssetForm({ d, asset, onClose, onSaved, notify }) {
  const [f, setF] = useState(() => ({
    name: asset?.name || '', asset_tag: asset?.asset_tag || '',
    category: asset?.category || (d.categories[0] || 'Other'),
    serial_number: asset?.serial_number || '', acquisition_cost: asset?.acquisition_cost ?? '',
    acquisition_date: asset?.acquisition_date || '', supplier: asset?.supplier || '',
    location: asset?.location || '', custodian: asset?.custodian || '',
    status: asset?.status || 'In Use', useful_life_years: asset?.useful_life_years ?? '',
    salvage_value: asset?.salvage_value ?? '',
  }));
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    if (!f.name.trim()) { notify('error', 'Asset name is required.'); return; }
    const r = await submitJson(asset ? asset.edit_url : d.add_url, f);
    if (r.ok) onSaved(); else notify('error', r.error || 'Could not save.');
  };
  return (
    <Modal title={asset ? 'Edit asset' : 'Register asset'} icon="fa-building-columns" size="lg" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save}>Save</Button></>}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="Name *"><input className="form-control" value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label="Asset tag"><input className="form-control" value={f.asset_tag} onChange={(e) => set('asset_tag', e.target.value)} /></Field>
        <Field label="Category"><select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>{d.categories.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="Serial number"><input className="form-control" value={f.serial_number} onChange={(e) => set('serial_number', e.target.value)} /></Field>
        <Field label="Acquisition cost (₦)"><input type="number" className="form-control" value={f.acquisition_cost} onChange={(e) => set('acquisition_cost', e.target.value)} /></Field>
        <Field label="Acquired on"><input type="date" className="form-control" value={f.acquisition_date} onChange={(e) => set('acquisition_date', e.target.value)} /></Field>
        <Field label="Supplier"><input className="form-control" value={f.supplier} onChange={(e) => set('supplier', e.target.value)} /></Field>
        <Field label="Location"><input className="form-control" value={f.location} onChange={(e) => set('location', e.target.value)} /></Field>
        <Field label="Custodian"><input className="form-control" value={f.custodian} onChange={(e) => set('custodian', e.target.value)} /></Field>
        <Field label="Status"><select className="form-control" value={f.status} onChange={(e) => set('status', e.target.value)}>{d.statuses.filter((x) => x !== 'Disposed').map((st) => <option key={st}>{st}</option>)}</select></Field>
        <Field label="Useful life (yrs)"><input type="number" className="form-control" value={f.useful_life_years} onChange={(e) => set('useful_life_years', e.target.value)} placeholder="for depreciation" /></Field>
        <Field label="Salvage value (₦)"><input type="number" className="form-control" value={f.salvage_value} onChange={(e) => set('salvage_value', e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

function DisposeModal({ asset, onClose, onSaved, notify }) {
  const [f, setF] = useState({ disposed_on: '', disposal_amount: '', method: 'Cash', disposal_note: '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    const r = await submitJson(asset.dispose_url, f);
    if (r.ok) onSaved(); else notify('error', r.error || 'Could not dispose.');
  };
  return (
    <Modal title={`Dispose "${asset.name}"`} icon="fa-box-archive" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="danger" onClick={save}>Dispose</Button></>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>Current book value: <strong>{naira(asset.book_value)}</strong>. Any proceeds are posted to Finance as disposal income.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="Disposed on"><input type="date" className="form-control" value={f.disposed_on} onChange={(e) => set('disposed_on', e.target.value)} /></Field>
        <Field label="Proceeds (₦)"><input type="number" className="form-control" value={f.disposal_amount} onChange={(e) => set('disposal_amount', e.target.value)} /></Field>
        <Field label="Method"><select className="form-control" value={f.method} onChange={(e) => set('method', e.target.value)}><option>Cash</option><option>Transfer</option><option>POS</option></select></Field>
        <Field label="Note" wide><input className="form-control" value={f.disposal_note} onChange={(e) => set('disposal_note', e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

// ---- Stock batches / lots --------------------------------------------------
function Batches({ d }) {
  const nav = useNav();
  const a = d.applied || {};
  const [productId, setProductId] = useState(a.product_id || '');
  const [empty, setEmpty] = useState(!!a.empty);
  const apply = (pid, emp) => navParams(nav.go, d.self_url, { product_id: pid, empty: emp ? '1' : '' });
  const badge = (st) => {
    if (st === 'expired') return <span className="badge badge-danger">Expired</span>;
    if (st === 'expiring') return <span className="badge badge-warning">Expiring</span>;
    if (st === 'empty') return <span className="badge badge-secondary">Empty</span>;
    return <span className="badge badge-success">OK</span>;
  };
  return (
    <>
      <PageHeader icon="fa-layer-group" title="Stock Batches / Lots" actions={<>
        <a href={d.urls.movements} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-right-left" /> Movements</a>
        <a href={d.urls.products} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-boxes-stacked" /> Products</a>
      </>} />
      <div className="alert alert-info"><i aria-hidden="true" className="fas fa-circle-info" /> Batch-tracked products receive stock in lots and sell first-expiry-first-out. Turn tracking on for a product in its edit form.</div>
      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <select className="form-control" style={{ maxWidth: 240 }} value={productId} onChange={(e) => { setProductId(e.target.value); apply(e.target.value, empty); }}>
          <option value="">All batch-tracked products</option>{(d.options.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <label className="text-sm" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><input type="checkbox" checked={empty} onChange={(e) => { setEmpty(e.target.checked); apply(productId, e.target.checked); }} /> Show emptied lots</label>
      </div></div>
      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        {d.batches.length ? (
          <table className="data-table"><thead><tr><th>Product</th><th>Batch / Serial</th><th className="text-right">Remaining</th><th>Expiry</th><th>Received</th><th>Ref</th><th>Status</th></tr></thead>
            <tbody>{d.batches.map((b) => (
              <tr key={b.id}>
                <td>{b.product}</td>
                <td>{b.batch_no || '—'}{b.serial_number && <div className="text-muted text-sm">SN {b.serial_number}</div>}</td>
                <td className="text-right"><strong>{b.quantity}</strong>{b.original_qty > 0 && <span className="text-muted text-sm"> / {b.original_qty}</span>}</td>
                <td className={b.status === 'expired' ? 'text-danger' : b.status === 'expiring' ? 'text-warning' : ''}>{b.expiry_date || '—'}</td>
                <td className="text-muted text-sm">{b.received_on || '—'}{b.supplier && <div>{b.supplier}</div>}</td>
                <td className="text-muted text-sm">{b.reference || '—'}</td>
                <td>{badge(b.status)}</td>
              </tr>
            ))}</tbody></table>
        ) : <EmptyState icon="fa-layer-group" title="No stock lots yet">Receive stock for a batch-tracked product to open its first lot.</EmptyState>}
      </div></div>
    </>
  );
}

const SCREENS = { dashboard: Dashboard, products: Products, new_sale: NewSale, history: History,
  analytics: Analytics, movements: Movements, suppliers: Suppliers, supplier_detail: SupplierDetail,
  purchases: Purchases, purchase_detail: PurchaseDetail, reports: Reports, promos: Promos,
  audits: Audits, audit_detail: AuditDetail, assets: Assets, batches: Batches };

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
