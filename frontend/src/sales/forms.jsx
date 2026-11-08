import React, { useState, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira } from '../lib/format';
import { Modal, Button, promptDialog } from '../components/ui';
import { canWrite } from '../lib/perms';

// Add/edit forms and dialogs used by the sales screens (moved unchanged from
// SalesApp.jsx so the screens can live in their own module).
export function Field({ label, children, wide }) {
  return <label className="form-group" style={{ margin: 0, gridColumn: wide ? '1 / -1' : undefined }}>
    <span className="form-label">{label}</span>{children}</label>;
}
export function Num({ v, on, step }) {
  return <input type="number" step={step || '1'} className="form-control" value={v ?? ''} onChange={(e) => on(e.target.value)} />;
}

export function ProductForm({ d, product, onClose, onSaved }) {
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
                  {canWrite(d, 'stock_adjust') && <button type="button" className="btn btn-sm btn-primary" onClick={() => restockDupe(p)}><i aria-hidden="true" className="fas fa-plus" /> Add stock to this</button>}
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

export function AdjustModal({ d, product, onClose, onSaved }) {
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

export function ConvertAssetModal({ d, product, onClose, onSaved, notify }) {
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

export function BuyerPicker({ d, pay, setP }) {
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

export function SupplierForm({ supplier, addUrl, onClose, onSaved }) {
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

export function PurchaseForm({ d, onClose, onSaved }) {
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

