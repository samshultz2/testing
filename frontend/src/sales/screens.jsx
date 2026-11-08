// Redesigned sales & inventory screens (mobile-first, decision-led). Forms and
// dialogs live in ./forms (unchanged); the shared look comes from the results
// kit (rs-*) plus the sales kit (sl-*).
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira, nairaShort } from '../lib/format';
import { useNav, navParams } from '../lib/section';
import { confirm } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Menu, Sheet, Blank, Bar, Meter, Chips, Avatar, usePhone } from '../subjects/results';
import { SalesNav, DataList, Pill, PO_TONE, AUDIT_TONE, Bars, Trend, rangeFor, rangeKey } from './kit';
import { ProductForm, AdjustModal, ConvertAssetModal, BuyerPicker, SupplierForm, PurchaseForm } from './forms';

const short = (v) => (typeof nairaShort === 'function' ? nairaShort(v) : naira(v));
const Link = ({ href, className, children, title }) => <a href={href} className={className} title={title}>{children}</a>;

// Shared date-range bar: quick chips + custom from/to.
function RangeBar({ from, to, onApply }) {
  const [f, setF] = useState(from || ''); const [t, setT] = useState(to || '');
  const [custom, setCustom] = useState(rangeKey(from, to) === 'custom');
  const key = rangeKey(from, to);
  const pick = (k) => { if (k === 'custom') { setCustom(true); return; } setCustom(false); const r = rangeFor(k); onApply(r.from, r.to); };
  return (
    <div className="sl-range">
      <Seg label="Period" value={custom ? 'custom' : key} onChange={pick} options={[
        { value: 'all', label: 'All time' }, { value: 'today', label: 'Today' }, { value: '7d', label: '7 days' }, { value: '30d', label: '30 days' },
        { value: 'month', label: 'This month' }, { value: 'custom', label: 'Custom' }]} />
      {custom && (
        <span className="sl-range-c">
          <input type="date" value={f} onChange={(e) => setF(e.target.value)} aria-label="From" />
          <span>to</span>
          <input type="date" value={t} onChange={(e) => setT(e.target.value)} aria-label="To" />
          <button type="button" className="rs-btn sm primary" onClick={() => onApply(f, t)}>Apply</button>
        </span>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Overview
// ═══════════════════════════════════════════════════════════════════════════
export function Dashboard({ d }) {
  const u = d.urls || {};
  const [brk, setBrk] = useState('products');
  const margin = d.month_total ? Math.round((d.month_profit / d.month_total) * 100) : null;
  const alerts = [
    d.out_of_stock_count > 0 && { tone: 'bad', icon: 'fa-box-open', n: d.out_of_stock_count, label: d.out_of_stock_count === 1 ? 'product out of stock' : 'products out of stock', href: u.products + '?stock=out' },
    d.low_stock.length > 0 && { tone: 'mid', icon: 'fa-arrow-trend-down', n: d.low_stock.length, label: d.low_stock.length === 1 ? 'product running low' : 'products running low', href: u.products + '?stock=low' },
    d.expiring_soon > 0 && { tone: 'bad', icon: 'fa-hourglass-end', n: d.expiring_soon, label: d.expiring_soon === 1 ? 'item expiring or expired' : 'items expiring or expired', href: u.reports ? u.reports + '?kind=expiry' : (d.section || {}).batches },
    d.awaiting_delivery > 0 && { tone: 'info', icon: 'fa-truck', n: d.awaiting_delivery, label: d.awaiting_delivery === 1 ? 'order awaiting delivery' : 'orders awaiting delivery', href: u.purchases },
    d.supplier_payables > 0 && { tone: 'mid', icon: 'fa-file-invoice-dollar', n: short(d.supplier_payables), label: 'owed to suppliers', href: u.suppliers },
  ].filter(Boolean);
  const brkRows = { products: d.top_products || [], category: d.by_category || [], method: d.by_method || [], cashier: d.by_cashier || [] }[brk];
  return (
    <div className="rs sl">
      <Head icon="fa-cart-shopping" title="Sales & Inventory" sub={`${d.product_count} products · ${naira(d.inventory_value)} in stock`}>
        {canWrite(d, 'pos_sell') && <a href={u.new_sale} className="rs-btn primary"><i className="fas fa-cash-register" aria-hidden="true" /><span className="rs-hide-sm">New sale</span></a>}
      </Head>
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'Today', value: short(d.today_total), sub: `${d.today_count || 0} sale${d.today_count === 1 ? '' : 's'}`, tone: 'good' },
        { label: 'This week', value: short(d.week_total) },
        { label: 'Last 30 days', value: short(d.month_total) },
        { label: 'Profit (30 days)', value: short(d.month_profit), sub: margin != null ? `${margin}% margin` : '', tone: d.month_profit >= 0 ? '' : 'bad' },
      ]} />
      {alerts.length > 0 ? (
        <div className="sl-alerts">
          {alerts.map((a, i) => (
            <a key={i} href={a.href} className={'sl-alert ' + a.tone}>
              <i className={'fas ' + a.icon} aria-hidden="true" /><span><b>{a.n}</b> {a.label}</span><i className="fas fa-chevron-right sl-go" aria-hidden="true" /></a>
          ))}
        </div>
      ) : <p className="rs-ok-line"><i className="fas fa-circle-check" aria-hidden="true" /> Stock levels, expiry dates and deliveries all look fine.</p>}

      <div className="rs-split">
        <div className="rs-main">
          <section className="rs-card">
            <header className="rs-card-h"><h3><i className="fas fa-chart-column" aria-hidden="true" /> Sales, last 30 days</h3>
              {u.analytics && <a href={u.analytics} className="rs-link">Analytics</a>}</header>
            <Trend rows={d.trend || []} fmt={naira} />
          </section>
          <section className="rs-card">
            <header className="rs-card-h"><h3><i className="fas fa-ranking-star" aria-hidden="true" /> What’s selling (30 days)</h3></header>
            <Seg label="Breakdown" value={brk} onChange={setBrk} options={[{ value: 'products', label: 'Products' }, { value: 'category', label: 'Category' }, { value: 'method', label: 'Payment' }, { value: 'cashier', label: 'Cashier' }]} />
            <div style={{ marginTop: '.8rem' }}>
              <Bars rows={brkRows} label={(r) => r.name || r.label} fmt={naira} sub={brk === 'products' ? (r) => `${r.units} sold` : undefined} />
            </div>
          </section>
          <section className="rs-card flush">
            <header className="rs-card-h pad"><h3><i className="fas fa-receipt" aria-hidden="true" /> Recent sales</h3><a href={u.history} className="rs-link">All sales</a></header>
            <SaleList rows={d.recent} empty={<Blank icon="fa-receipt" title="No sales yet"><p>Record your first sale.</p></Blank>} />
          </section>
        </div>
        <aside className="rs-rail">
          <section className={'rs-card' + (d.low_stock.length ? ' sl-warn' : '')}>
            <header className="rs-card-h"><h3><i className="fas fa-arrow-trend-down" aria-hidden="true" /> Restock soon</h3>
              {d.low_stock.length > 0 && <a href={u.products + '?stock=low'} className="rs-link">See all</a>}</header>
            {d.low_stock.length ? (
              <div className="sl-low">
                {d.low_stock.slice(0, 8).map((p, i) => (
                  <div key={i} className="sl-low-r">
                    <span className="n"><b>{p.name}</b><small>{p.category} · reorder at {p.reorder_level}</small></span>
                    <Meter value={p.stock_qty} max={Math.max(p.reorder_level, 1) * 2} tone={p.stock_qty <= 0 ? 'bad' : 'mid'} />
                    <b className={'q ' + (p.stock_qty <= 0 ? 'bad' : 'mid')}>{p.stock_qty}</b>
                  </div>
                ))}
              </div>
            ) : <p className="rs-muted">Nothing is below its reorder level.</p>}
            {d.low_stock.length > 0 && u.purchases && <a href={u.purchases} className="rs-btn ghost wide" style={{ marginTop: '.7rem' }}><i className="fas fa-file-invoice" aria-hidden="true" /> Order more</a>}
          </section>
          <section className="rs-card">
            <header className="rs-card-h"><h3><i className="fas fa-bolt" aria-hidden="true" /> Quick actions</h3></header>
            <div className="sl-quick">
              {canWrite(d, 'pos_sell') && <a href={u.new_sale}><i className="fas fa-cash-register" aria-hidden="true" />New sale</a>}
              <a href={u.products}><i className="fas fa-box" aria-hidden="true" />Products</a>
              {u.purchases && <a href={u.purchases}><i className="fas fa-truck-ramp-box" aria-hidden="true" />Purchases</a>}
              {u.audits && <a href={u.audits}><i className="fas fa-clipboard-check" aria-hidden="true" />Stock count</a>}
              {u.reports && <a href={u.reports}><i className="fas fa-file-lines" aria-hidden="true" />Reports</a>}
              {u.promos && <a href={u.promos}><i className="fas fa-tags" aria-hidden="true" />Promo codes</a>}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function SaleList({ rows, empty }) {
  return (
    <DataList rows={rows} empty={empty} cols={[
      { key: 'receipt', label: 'Receipt', main: true, render: (s) => <a href={s.receipt_url} data-native>{s.receipt_no}</a> },
      { key: 'buyer', label: 'Buyer', sub: true, render: (s) => s.buyer },
      { key: 'items', label: 'Items', align: 'right', render: (s) => s.item_count },
      { key: 'method', label: 'Paid by', render: (s) => <Pill>{s.payment_method}</Pill> },
      { key: 'when', label: 'When', render: (s) => <span className="rs-muted">{s.when}</span> },
      { key: 'total', label: 'Total', align: 'right', value: true, render: (s) => <b>{naira(s.total)}</b> },
    ]} />
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Sell (point of sale)
// ═══════════════════════════════════════════════════════════════════════════
export function NewSale({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [qty, setQty] = useState({});
  const [pay, setPay] = useState({ student_id: '', customer_name: '', customer_type: 'Student', payment_method: d.methods[0] || 'Cash', amount_paid: '', promo_code: '', discount_amount: '' });
  const [busy, setBusy] = useState(false);
  const [promoInfo, setPromoInfo] = useState(null);
  const [q, setQ] = useState('');
  const [cat, setCat] = useState('');
  const [cartOpen, setCartOpen] = useState(false);
  const [showDisc, setShowDisc] = useState(false);
  const searchRef = useRef(null);
  const setP = (k, v) => setPay((s) => ({ ...s, [k]: v }));
  const priceOf = (p) => {
    const bt = (pay.customer_type || '').toLowerCase();
    const tier = bt === 'student' ? p.student_price : bt === 'staff' ? p.staff_price : bt === 'parent' ? p.parent_price : null;
    return tier && tier > 0 ? tier : (p.unit_price || 0);
  };
  const byId = useMemo(() => { const m = {}; d.products.forEach((p) => { m[p.id] = p; }); return m; }, [d.products]);
  const lines = Object.keys(qty).filter((id) => Number(qty[id]) > 0 && byId[id]).map((id) => ({ p: byId[id], n: Number(qty[id]) }));
  const count = lines.reduce((a, l) => a + l.n, 0);
  const subtotal = lines.reduce((t, l) => t + priceOf(l.p) * l.n, 0);
  const manual = Math.max(Number(pay.discount_amount) || 0, 0);
  const promoDisc = promoInfo && promoInfo.ok ? (promoInfo.discount || 0) : 0;
  const discount = Math.min(subtotal, promoDisc + manual);
  const total = Math.max(0, subtotal - discount);
  const paid = pay.amount_paid === '' ? total : Number(pay.amount_paid) || 0;
  const change = paid - total;
  const add = (p, n = 1) => setQty((s) => { const cur = Number(s[p.id]) || 0; const nx = Math.max(0, Math.min(p.stock_qty, cur + n)); return { ...s, [p.id]: nx }; });
  const setN = (p, v) => setQty((s) => ({ ...s, [p.id]: Math.max(0, Math.min(p.stock_qty, Number(v) || 0)) }));
  const cats = useMemo(() => Array.from(new Set(d.products.map((p) => p.category))).filter(Boolean), [d.products]);
  const shown = d.products.filter((p) => (!cat || p.category === cat)
    && (!q || `${p.name} ${p.sku || ''} ${p.barcode || ''}`.toLowerCase().includes(q.trim().toLowerCase())));
  const onSearchKey = (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const t = q.trim().toLowerCase(); if (!t) return;
    const hit = d.products.find((p) => (p.barcode && p.barcode.toLowerCase() === t) || (p.sku && p.sku.toLowerCase() === t)) || (shown.length === 1 ? shown[0] : null);
    if (hit) { add(hit); setQ(''); } else notify('error', `No product matches “${q}”.`);
  };
  const applyPromo = async () => {
    const code = (pay.promo_code || '').trim();
    if (!code) { setPromoInfo(null); return; }
    try {
      const res = await apiGet(`${d.promo_check_url}?code=${encodeURIComponent(code)}&subtotal=${subtotal}`);
      setPromoInfo(res);
      if (!res.ok) notify('error', res.error || 'Invalid promo code.');
    } catch (e) { setPromoInfo({ ok: false, error: 'Could not check code.' }); }
  };
  useEffect(() => { if (promoInfo && promoInfo.ok && (pay.promo_code || '').trim()) applyPromo(); }, [subtotal]); // eslint-disable-line
  const submit = async (e) => {
    if (e) e.preventDefault();
    if (!lines.length) { notify('error', 'Add at least one item.'); return; }
    if (pay.amount_paid !== '' && change < 0 && !await confirm({ title: 'Part payment', message: `${naira(-change)} will be left owing on this sale. Continue?`, confirmText: 'Record sale' })) return;
    setBusy(true);
    const r = await submitJson(d.submit_url, { product_id: lines.map((l) => l.p.id), quantity: lines.map((l) => l.n), ...pay,
      promo_code: promoInfo && promoInfo.ok ? pay.promo_code : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not record the sale.');
  };
  const clear = () => { setQty({}); setPromoInfo(null); setPay((s) => ({ ...s, promo_code: '', discount_amount: '', amount_paid: '' })); };

  const cart = (
    <div className="sl-cart">
      <BuyerPicker d={d} pay={pay} setP={setP} />
      <div className="sl-lines">
        {lines.length ? lines.map(({ p, n }) => (
          <div key={p.id} className="sl-line">
            <span className="n"><b>{p.name}</b><small>{naira(priceOf(p))} each{n >= p.stock_qty ? ' · last in stock' : ''}</small></span>
            <span className="sl-step">
              <button type="button" onClick={() => add(p, -1)} aria-label={`One less ${p.name}`}><i className={'fas ' + (n === 1 ? 'fa-trash' : 'fa-minus')} aria-hidden="true" /></button>
              <input type="number" inputMode="numeric" min="0" max={p.stock_qty} value={n} onChange={(e) => setN(p, e.target.value)} aria-label={`Quantity of ${p.name}`} />
              <button type="button" onClick={() => add(p, 1)} disabled={n >= p.stock_qty} aria-label={`One more ${p.name}`}><i className="fas fa-plus" aria-hidden="true" /></button>
            </span>
            <b className="t">{naira(priceOf(p) * n)}</b>
          </div>
        )) : <p className="sl-empty-cart"><i className="fas fa-basket-shopping" aria-hidden="true" /> Tap products to add them, or scan a barcode.</p>}
      </div>
      {lines.length > 0 && (<>
        {!showDisc && !discount ? (
          <button type="button" className="rs-link" onClick={() => setShowDisc(true)}><i className="fas fa-tag" aria-hidden="true" /> Add promo code or discount</button>
        ) : (
          <div className="sl-disc">
            {d.promo_check_url && (
              <label className="sl-f"><span>Promo code</span>
                <span className="sl-inline"><input type="text" value={pay.promo_code} placeholder="Code" onChange={(e) => { setP('promo_code', e.target.value.toUpperCase()); setPromoInfo(null); }}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applyPromo(); } }} />
                <button type="button" className="rs-btn sm ghost" onClick={applyPromo}>Apply</button></span>
                {promoInfo && promoInfo.ok && <small className="good"><i className="fas fa-check" aria-hidden="true" /> {promoInfo.code} — {promoInfo.description || 'discount applied'}</small>}
              </label>
            )}
            <label className="sl-f"><span>Discount (₦)</span>
              <input type="number" inputMode="decimal" min="0" step="0.01" value={pay.discount_amount} placeholder="0" onChange={(e) => setP('discount_amount', e.target.value)} /></label>
          </div>
        )}
        <div className="sl-f"><span>Payment</span>
          <Chips label="Payment method" value={pay.payment_method} onChange={(v) => setP('payment_method', v)} items={d.methods.map((m) => ({ value: m, label: m }))} /></div>
        <label className="sl-f"><span>Amount paid</span>
          <input type="number" inputMode="decimal" step="0.01" value={pay.amount_paid} placeholder={`${total.toFixed(2)} (exact)`} onChange={(e) => setP('amount_paid', e.target.value)} />
          {pay.amount_paid !== '' && <small className={change >= 0 ? 'good' : 'bad'}>{change >= 0 ? `Change to give: ${naira(change)}` : `Still owing: ${naira(-change)}`}</small>}</label>
        <div className="sl-sum">
          <span><em>Subtotal ({count} item{count === 1 ? '' : 's'})</em><b>{naira(subtotal)}</b></span>
          {discount > 0 && <span className="good"><em>Discount</em><b>−{naira(discount)}</b></span>}
          <span className="tot"><em>Total</em><b>{naira(total)}</b></span>
        </div>
        <div className="sl-cart-a">
          <button type="button" className="rs-btn ghost" onClick={clear}>Clear</button>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={submit}><i className="fas fa-receipt" aria-hidden="true" /> {busy ? 'Saving…' : `Complete sale · ${naira(total)}`}</button>
        </div>
      </>)}
    </div>
  );

  return (
    <div className={'rs sl' + (phone ? ' has-bar' : '')}>
      <Head icon="fa-cash-register" title="New sale" sub={`${d.products.length} products in stock`} />
      <SalesNav d={d} />
      <div className="sl-pos">
        <div className="sl-shelf">
          <div className="sl-find">
            <label className="rs-search"><i className="fas fa-barcode" aria-hidden="true" />
              <input ref={searchRef} type="search" placeholder="Search or scan a barcode, then Enter" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onSearchKey} aria-label="Search products" autoFocus={!phone} /></label>
          </div>
          {cats.length > 1 && <Chips label="Category" value={cat} onChange={setCat} items={[{ value: '', label: 'All' }, ...cats.map((c) => ({ value: c, label: c }))]} />}
          {shown.length ? (
            <div className="sl-grid">
              {shown.map((p) => {
                const n = Number(qty[p.id]) || 0; const low = p.stock_qty <= 3; const full = n >= p.stock_qty;
                return (
                  <button type="button" key={p.id} className={'sl-prod' + (n ? ' in' : '') + (full ? ' full' : '')} onClick={() => add(p)} disabled={full} aria-label={`Add ${p.name}, ${naira(priceOf(p))}`}>
                    {n > 0 && <span className="sl-badge">{n}</span>}
                    <b>{p.name}</b>
                    <small>{p.category}</small>
                    <span className="sl-prod-f"><strong>{naira(priceOf(p))}</strong>
                      {priceOf(p) !== (p.unit_price || 0) && <s>{naira(p.unit_price)}</s>}
                      <em className={low ? 'low' : ''}>{p.stock_qty - n} left</em></span>
                  </button>
                );
              })}
            </div>
          ) : d.products.length ? <Blank icon="fa-magnifying-glass" title="No match"><p>Nothing in stock matches “{q}”.</p></Blank>
            : <Blank icon="fa-box-open" title="No products in stock"><p>Add products or restock before selling.</p><a href={d.urls.products} className="rs-btn primary">Go to products</a></Blank>}
        </div>
        {!phone && <aside className="sl-cart-col"><section className="rs-card"><header className="rs-card-h"><h3><i className="fas fa-basket-shopping" aria-hidden="true" /> Cart</h3>{count > 0 && <small>{count} item{count === 1 ? '' : 's'}</small>}</header>{cart}</section></aside>}
      </div>
      {phone && (
        <Bar>
          <span className="rs-bar-t"><b>{naira(total)}</b><small>{count ? `${count} item${count === 1 ? '' : 's'} in cart` : 'Cart is empty'}</small></span>
          <button type="button" className="rs-btn primary" onClick={() => setCartOpen(true)} disabled={!count}><i className="fas fa-basket-shopping" aria-hidden="true" /> Checkout</button>
        </Bar>
      )}
      {phone && cartOpen && <Sheet title="Cart" onClose={() => setCartOpen(false)}>{cart}</Sheet>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Sales history
// ═══════════════════════════════════════════════════════════════════════════
export function History({ d }) {
  const nav = useNav();
  const a = d.applied || {};
  const o = d.options || {};
  const blank = { from: '', to: '', method: '', cashier: '', buyer_type: '', product_id: '', category: '', q: '' };
  const [f, setF] = useState({ ...blank, ...Object.fromEntries(Object.keys(blank).map((k) => [k, a[k] || ''])) });
  const [more, setMore] = useState(false);
  const [open, setOpen] = useState(null);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const apply = (over = {}) => { const nf = { ...f, ...over }; setF(nf); navParams(nav.go, d.self_url, nf); };
  const exportUrl = (fmt) => { const p = new URLSearchParams(); Object.entries(f).forEach(([k, v]) => { if (v) p.set(k, v); }); p.set('format', fmt); return `${d.export_url}?${p.toString()}`; };
  const s = d.summary || {};
  const extra = ['method', 'cashier', 'buyer_type', 'product_id', 'category'].filter((k) => f[k]).length;
  const owing = d.sales.filter((r) => r.balance > 0);
  return (
    <div className="rs sl">
      <Head icon="fa-receipt" title="Sales" sub="Every sale, with what was bought">
        <Menu label="Export" items={[
          canWrite(d, 'reports_export') && { icon: 'fa-file-csv', label: 'Download CSV', href: exportUrl('csv'), native: true },
          canWrite(d, 'reports_export') && { icon: 'fa-file-excel', label: 'Download Excel', href: exportUrl('excel'), native: true },
          { icon: 'fa-print', label: 'Print', onClick: () => window.print() },
        ]} />
      </Head>
      <SalesNav d={d} />
      <RangeBar from={f.from} to={f.to} onApply={(from, to) => apply({ from, to })} />
      <Tiles items={[
        { label: 'Revenue', value: short(s.revenue || 0), tone: 'good' },
        { label: 'Sales', value: s.count || 0, sub: s.count ? `avg ${short((s.revenue || 0) / s.count)}` : '' },
        { label: 'Units sold', value: s.units || 0 },
        owing.length > 0 && { label: 'Unpaid balances', value: short(owing.reduce((t, r) => t + r.balance, 0)), sub: `${owing.length} sale${owing.length === 1 ? '' : 's'}`, tone: 'bad' },
      ]} />
      <div className="rs-toolbar">
        <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Receipt number or buyer — Enter to search" value={f.q} onChange={(e) => set('q', e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') apply(); }} aria-label="Search sales" /></label>
        <button type="button" className={'rs-btn ghost' + (extra ? ' on' : '')} onClick={() => setMore(true)}><i className="fas fa-sliders" aria-hidden="true" /><span>Filters{extra ? ` (${extra})` : ''}</span></button>
        {(extra > 0 || f.q || f.from || f.to) && <button type="button" className="rs-link" onClick={() => { setF(blank); navParams(nav.go, d.self_url, blank); }}>Clear all</button>}
      </div>
      {d.sales.length ? (
        <section className="rs-card flush">
          <div className="sl-sales">
            {d.sales.map((r) => (
              <div key={r.id} className={'sl-sale' + (open === r.id ? ' open' : '')}>
                <button type="button" className="sl-sale-top" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                  <Avatar name={r.buyer} />
                  <span className="n"><b>{r.buyer}</b><small>{[r.buyer_type, r.class_arm, r.when].filter(Boolean).join(' · ')}</small></span>
                  <span className="m rs-hide-sm"><small>{r.receipt_no}</small><small>{r.payment_method} · {r.cashier}</small></span>
                  <span className="v"><b>{naira(r.total)}</b>{r.balance > 0 ? <small className="bad">owes {naira(r.balance)}</small> : <small>{r.item_count} item{r.item_count === 1 ? '' : 's'}</small>}</span>
                  <i className="fas fa-chevron-down" aria-hidden="true" />
                </button>
                {open === r.id && (
                  <div className="sl-sale-more">
                    {r.items.map((it, i) => <div key={i} className="sl-item"><span>{it.quantity} × {it.name}</span><small>{naira(it.unit_price)}</small><b>{naira(it.line_total)}</b></div>)}
                    <div className="sl-sale-f"><small>{r.receipt_no} · {r.payment_method} · sold by {r.cashier}</small><a href={r.receipt_url} className="rs-btn sm ghost" data-native><i className="fas fa-receipt" aria-hidden="true" /> Receipt</a></div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      ) : <Blank icon="fa-receipt" title="No sales found"><p>No sales match this period and filters.</p></Blank>}
      {more && (
        <Sheet title="Filter sales" onClose={() => setMore(false)}>
          <div className="sl-form">
            <label className="sl-f"><span>Buyer</span><select value={f.buyer_type} onChange={(e) => set('buyer_type', e.target.value)}><option value="">Everyone</option><option value="student">Students</option><option value="other">Staff, parents & walk-ins</option></select></label>
            <label className="sl-f"><span>Payment method</span><select value={f.method} onChange={(e) => set('method', e.target.value)}><option value="">Any</option>{(o.methods || []).map((m) => <option key={m}>{m}</option>)}</select></label>
            <label className="sl-f"><span>Cashier</span><select value={f.cashier} onChange={(e) => set('cashier', e.target.value)}><option value="">Anyone</option>{(o.cashiers || []).map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="sl-f"><span>Category</span><select value={f.category} onChange={(e) => set('category', e.target.value)}><option value="">Any</option>{(o.categories || []).map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="sl-f"><span>Product</span><select value={f.product_id} onChange={(e) => set('product_id', e.target.value)}><option value="">Any</option>{(o.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            <button type="button" className="rs-btn primary wide" onClick={() => { setMore(false); apply(); }}>Show sales</button>
          </div>
        </Sheet>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Products & stock
// ═══════════════════════════════════════════════════════════════════════════
function RestockSheet({ p, onClose, onDone, notify }) {
  const [n, setN] = useState('');
  const [b, setB] = useState({ batch_no: '', expiry_date: '' });
  const [busy, setBusy] = useState(false);
  const go = async (e) => {
    e.preventDefault();
    if (!(Number(n) > 0)) return;
    setBusy(true);
    const r = await submitJson(p.restock_url, { qty: Number(n), ...(p.batch_tracked ? b : {}) });
    setBusy(false);
    if (r.ok) { onClose(); onDone(); } else notify('error', r.error || 'Could not restock.');
  };
  return (
    <Sheet title={`Restock ${p.name}`} onClose={onClose}>
      <form onSubmit={go} className="sl-form">
        <p className="rs-muted">On hand: <b>{p.stock_qty}</b>{p.reorder_qty ? ` · usual order ${p.reorder_qty}` : ''}</p>
        <label className="sl-f"><span>Units received</span><input type="number" inputMode="numeric" min="1" value={n} onChange={(e) => setN(e.target.value)} autoFocus />
          <span className="rs-chips">{[5, 10, 20, 50].concat(p.reorder_qty ? [p.reorder_qty] : []).filter((x, i, arr) => arr.indexOf(x) === i).map((x) => <button type="button" key={x} className="rs-chip" onClick={() => setN(String(x))}>+{x}</button>)}</span></label>
        {p.batch_tracked && (<>
          <label className="sl-f"><span>Batch / lot number</span><input value={b.batch_no} onChange={(e) => setB((s) => ({ ...s, batch_no: e.target.value }))} /></label>
          <label className="sl-f"><span>Expiry date</span><input type="date" value={b.expiry_date} onChange={(e) => setB((s) => ({ ...s, expiry_date: e.target.value }))} /></label>
        </>)}
        <button type="submit" className="rs-btn primary wide" disabled={busy || !(Number(n) > 0)}><i className="fas fa-plus" aria-hidden="true" /> Add {Number(n) > 0 ? n : ''} to stock</button>
      </form>
    </Sheet>
  );
}

export function Products({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [q, setQ] = useState(d.q || '');
  const [cat, setCat] = useState(d.category || '');
  const [copies, setCopies] = useState(1);
  const [labels, setLabels] = useState(false);
  const [editing, setEditing] = useState(null);
  const [adjusting, setAdjusting] = useState(null);
  const [converting, setConverting] = useState(null);
  const [restocking, setRestocking] = useState(null);
  const stock = d.stock || '';
  const goStock = (v) => navParams(nav.go, d.self_url || (d.section || {}).products, { stock: v });
  const openLabels = () => {
    const p = new URLSearchParams(); if (cat) p.set('category', cat); if (stock) p.set('stock', stock); p.set('copies', String(copies || 1));
    window.open(`${d.labels_url}?${p.toString()}`, '_blank', 'noopener'); setLabels(false);
  };
  const genBarcodes = async () => {
    const r = await submitJson(d.generate_barcodes_url, cat ? { category: cat } : {});
    if (r.ok) { notify('success', r.message || 'Barcodes assigned.'); nav.refresh(); } else notify('error', r.error || 'Could not assign barcodes.');
  };
  const t = q.trim().toLowerCase();
  const shown = d.products.filter((p) => (!t || `${p.name} ${p.sku || ''} ${p.barcode || ''} ${p.brand || ''}`.toLowerCase().includes(t)) && (!cat || p.category === cat));
  const invValue = d.products.reduce((a, p) => a + (p.stock_value || 0), 0);
  const low = d.products.filter((p) => p.low_stock && !p.out_of_stock).length;
  const out = d.products.filter((p) => p.out_of_stock).length;
  const canAdjust = canWrite(d, 'stock_adjust');
  const usedCats = Array.from(new Set(d.products.map((p) => p.category))).filter(Boolean);
  const stockTone = (p) => (p.out_of_stock ? 'bad' : p.low_stock ? 'mid' : 'good');
  const rowMenu = (p) => [
    canAdjust && { icon: 'fa-right-left', label: 'Adjust or count stock', onClick: () => setAdjusting(p) },
    canWrite(d, 'catalogue_edit') && { icon: 'fa-pen', label: 'Edit product', onClick: () => setEditing(p) },
    d.urls.assets && p.stock_qty > 0 && canWrite(d, 'assets_create') && { icon: 'fa-building-columns', label: 'Convert to fixed asset', onClick: () => setConverting(p) },
  ];
  return (
    <div className="rs sl">
      <Head icon="fa-boxes-stacked" title="Products" sub={`${d.products.length} products · ${naira(invValue)} at cost`}>
        {canWrite(d, 'catalogue_create') && <button type="button" className="rs-btn primary" onClick={() => setEditing({})}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Add product</span></button>}
        <Menu label="More" items={[
          d.labels_url && canWrite(d, 'catalogue_labels') && { icon: 'fa-tags', label: 'Print price labels', onClick: () => setLabels(true) },
          d.generate_barcodes_url && canWrite(d, 'catalogue_labels') && { icon: 'fa-barcode', label: 'Give missing barcodes', onClick: genBarcodes },
          { icon: 'fa-right-left', label: 'Stock movements', href: (d.section || {}).movements },
          { icon: 'fa-layer-group', label: 'Batches & expiry', href: (d.section || {}).batches },
        ]} />
      </Head>
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'Stock value', value: short(invValue), sub: 'at cost price' },
        { label: 'Products', value: d.products.length },
        { label: 'Running low', value: low, tone: low ? 'mid' : '' },
        { label: 'Out of stock', value: out, tone: out ? 'bad' : '' },
      ]} />
      <div className="rs-toolbar">
        <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Name, SKU, brand or barcode" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search products" /></label>
        <select className="sl-select" value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category">
          <option value="">All categories</option>{usedCats.map((c) => <option key={c}>{c}</option>)}</select>
        <Seg label="Stock" value={stock} onChange={goStock} options={[{ value: '', label: 'All' }, { value: 'low', label: 'Low' }, { value: 'out', label: 'Out' }]} />
      </div>
      {shown.length ? (
        <section className="rs-card flush">
          <div className="sl-prods">
            {shown.map((p) => (
              <div key={p.id} className={'sl-prow ' + stockTone(p)}>
                <span className="n"><b>{p.name}</b><small>{[p.category, p.brand, p.sku].filter(Boolean).join(' · ')}{p.batch_tracked ? ' · lot tracked' : ''}</small></span>
                <span className="p"><b>{naira(p.unit_price)}</b><small>{p.margin_pct != null ? `${Math.round(p.margin_pct)}% margin` : `cost ${naira(p.cost_price)}`}</small></span>
                <span className="s"><b className={stockTone(p)}>{p.stock_qty}</b><small>{p.out_of_stock ? 'out of stock' : p.low_stock ? `low · reorder at ${p.reorder_level}` : 'in stock'}</small></span>
                <span className="a">
                  {canAdjust && <button type="button" className="rs-btn sm ghost" onClick={() => setRestocking(p)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Restock</span></button>}
                  <Menu label={phone ? 'More' : ''} items={rowMenu(p)} />
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : <Blank icon="fa-boxes-stacked" title="No products found"><p>{d.products.length ? 'Nothing matches your search.' : 'Add your first product to start selling.'}</p></Blank>}
      {labels && (
        <Sheet title="Print price labels" onClose={() => setLabels(false)}>
          <div className="sl-form">
            <p className="rs-muted">Prints labels for {cat || 'all categories'}{stock ? ` (${stock} stock only)` : ''}.</p>
            <label className="sl-f"><span>Copies of each label</span><input type="number" min="1" max="50" value={copies} onChange={(e) => setCopies(Math.max(1, Math.min(50, Number(e.target.value) || 1)))} /></label>
            <button type="button" className="rs-btn primary wide" onClick={openLabels}><i className="fas fa-print" aria-hidden="true" /> Open printable labels</button>
          </div>
        </Sheet>
      )}
      {restocking && <RestockSheet p={restocking} notify={notify} onClose={() => setRestocking(null)} onDone={() => nav.refresh()} />}
      {editing && <ProductForm d={d} product={editing.id ? editing : null} onClose={() => setEditing(null)} onSaved={() => nav.refresh()} />}
      {adjusting && <AdjustModal d={d} product={adjusting} onClose={() => setAdjusting(null)} onSaved={() => nav.refresh()} />}
      {converting && <ConvertAssetModal d={d} product={converting} notify={notify} onClose={() => setConverting(null)}
        onSaved={(r) => { setConverting(null); if (r.redirect) nav.go(r.redirect); else nav.refresh(); }} />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Stock: movements, batches, counts
// ═══════════════════════════════════════════════════════════════════════════
export function Movements({ d }) {
  const nav = useNav();
  const a = d.applied || {};
  const o = d.options || {};
  const [f, setF] = useState({ product_id: a.product_id || '', direction: a.direction || '', reason: a.reason || '', from: a.from || '', to: a.to || '' });
  const apply = (over = {}) => { const nf = { ...f, ...over }; setF(nf); navParams(nav.go, d.self_url, nf); };
  const s = d.summary || {};
  return (
    <div className="rs sl">
      <Head icon="fa-right-left" title="Stock movements" sub="Every unit in and out, with the reason" />
      <SalesNav d={d} />
      <RangeBar from={f.from} to={f.to} onApply={(from, to) => apply({ from, to })} />
      <Tiles items={[
        { label: 'Movements', value: s.count || 0 },
        { label: 'Units in', value: `+${s.total_in || 0}`, tone: 'good' },
        { label: 'Units out', value: `−${s.total_out || 0}`, tone: 'bad' },
      ]} />
      <div className="rs-toolbar">
        <select className="sl-select" value={f.product_id} onChange={(e) => apply({ product_id: e.target.value })} aria-label="Product">
          <option value="">All products</option>{(o.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <select className="sl-select" value={f.reason} onChange={(e) => apply({ reason: e.target.value })} aria-label="Reason">
          <option value="">All reasons</option>{(o.reasons || []).map((r) => <option key={r}>{r}</option>)}</select>
        <Seg label="Direction" value={f.direction} onChange={(v) => apply({ direction: v })} options={[{ value: '', label: 'In & out' }, { value: 'in', label: 'In' }, { value: 'out', label: 'Out' }]} />
      </div>
      <section className="rs-card flush">
        <DataList rows={d.movements} empty={<Blank icon="fa-right-left" title="No movements"><p>Nothing matches these filters.</p></Blank>} cols={[
          { key: 'product', label: 'Product', main: true, render: (m) => m.product },
          { key: 'reason', label: 'Reason', sub: true, render: (m) => <>{m.reason}{m.note ? ` — ${m.note}` : ''}</> },
          { key: 'qty', label: 'Qty', align: 'right', value: true, render: (m) => <b className={m.direction === 'in' ? 'good' : 'bad'}>{m.direction === 'in' ? '+' : '−'}{m.quantity}</b> },
          { key: 'after', label: 'Left', align: 'right', render: (m) => m.qty_after },
          { key: 'ref', label: 'Ref', render: (m) => m.reference || '—' },
          { key: 'by', label: 'By', render: (m) => m.by },
          { key: 'when', label: 'When', render: (m) => <span className="rs-muted">{m.when}</span> },
        ]} />
      </section>
    </div>
  );
}

export function Batches({ d }) {
  const nav = useNav();
  const a = d.applied || {};
  const [productId, setProductId] = useState(a.product_id || '');
  const [showEmpty, setShowEmpty] = useState(!!a.empty);
  const [st, setSt] = useState('');
  const apply = (pid, emp) => navParams(nav.go, d.self_url, { product_id: pid, empty: emp ? '1' : '' });
  const counts = { expired: 0, expiring: 0, ok: 0 };
  d.batches.forEach((b) => { if (counts[b.status] != null) counts[b.status] += 1; });
  const rows = st ? d.batches.filter((b) => b.status === st) : d.batches;
  const TONE = { expired: ['bad', 'Expired'], expiring: ['mid', 'Expiring soon'], empty: ['', 'Empty'], ok: ['good', 'OK'] };
  return (
    <div className="rs sl">
      <Head icon="fa-layer-group" title="Batches & expiry" sub="Lot-tracked stock sells first-expiry-first-out" />
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'Expired', value: counts.expired, tone: counts.expired ? 'bad' : '', sub: 'remove from shelf' },
        { label: 'Expiring soon', value: counts.expiring, tone: counts.expiring ? 'mid' : '', sub: 'sell or discount first' },
        { label: 'Healthy lots', value: counts.ok, tone: 'good' },
      ]} />
      <div className="rs-toolbar">
        <select className="sl-select" value={productId} onChange={(e) => { setProductId(e.target.value); apply(e.target.value, showEmpty); }} aria-label="Product">
          <option value="">All lot-tracked products</option>{(d.options.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <Seg label="Status" value={st} onChange={setSt} options={[{ value: '', label: 'All' }, { value: 'expired', label: 'Expired' }, { value: 'expiring', label: 'Expiring' }, { value: 'ok', label: 'OK' }]} />
        <label className="rs-check"><input type="checkbox" checked={showEmpty} onChange={(e) => { setShowEmpty(e.target.checked); apply(productId, e.target.checked); }} /> Show emptied lots</label>
      </div>
      <section className="rs-card flush">
        <DataList rows={rows} empty={<Blank icon="fa-layer-group" title="No lots here"><p>Turn on “Track lots” in a product’s edit form, then restock it to open its first lot.</p></Blank>} cols={[
          { key: 'product', label: 'Product', main: true, render: (b) => b.product },
          { key: 'batch', label: 'Batch', sub: true, render: (b) => <>{b.batch_no || 'No batch no.'}{b.serial_number ? ` · SN ${b.serial_number}` : ''}</> },
          { key: 'qty', label: 'Left', align: 'right', value: true, render: (b) => <span><b>{b.quantity}</b>{b.original_qty > 0 && <small className="rs-muted"> / {b.original_qty}</small>}</span> },
          { key: 'expiry', label: 'Expires', render: (b) => <span className={(TONE[b.status] || [])[0]}>{b.expiry_date || '—'}</span> },
          { key: 'received', label: 'Received', render: (b) => [b.received_on, b.supplier].filter(Boolean).join(' · ') || '—' },
          { key: 'ref', label: 'Ref', render: (b) => b.reference || '—' },
          { key: 'status', label: 'Status', render: (b) => <Pill tone={(TONE[b.status] || [''])[0]}>{(TONE[b.status] || ['', b.status])[1]}</Pill> },
        ]} />
      </section>
    </div>
  );
}

export function Audits({ d, notify }) {
  const nav = useNav();
  const [start, setStart] = useState(false);
  const [scope, setScope] = useState({ category: '', location: '', note: '' });
  const set = (k, v) => setScope((s) => ({ ...s, [k]: v }));
  const go = async () => {
    const r = await submitJson(d.new_url, scope);
    if (r.ok) { setStart(false); if (r.redirect) nav.go(r.redirect); else nav.refresh(); } else notify('error', r.error || 'Could not start a count.');
  };
  const open = d.audits.filter((a) => a.status === 'Counting');
  const last = d.audits.find((a) => a.status === 'Completed');
  return (
    <div className="rs sl">
      <Head icon="fa-clipboard-check" title="Stock counts" sub="Check shelves against the system and correct differences">
        {canWrite(d, 'counts_create') && <button type="button" className="rs-btn primary" onClick={() => setStart(true)}><i className="fas fa-clipboard-list" aria-hidden="true" /><span className="rs-hide-sm">Start a count</span></button>}
      </Head>
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'In progress', value: open.length, tone: open.length ? 'mid' : '' },
        { label: 'Completed', value: d.audits.filter((a) => a.status === 'Completed').length },
        last && { label: 'Last count variance', value: short(last.variance_value), sub: last.when, tone: last.variance_value < 0 ? 'bad' : 'good' },
      ]} />
      {open.length > 0 && (
        <div className="sl-alerts">{open.map((a) => (
          <a key={a.id} href={a.url} className="sl-alert mid"><i className="fas fa-clipboard-list" aria-hidden="true" /><span><b>{a.reference}</b> — {a.counted} of {a.items} counted, carry on</span><i className="fas fa-chevron-right sl-go" aria-hidden="true" /></a>))}</div>
      )}
      <section className="rs-card flush">
        <DataList rows={d.audits} onRow={(a) => nav.go(a.url)} empty={<Blank icon="fa-clipboard-check" title="No counts yet"><p>Start a count to reconcile what’s on the shelves with the system.</p></Blank>} cols={[
          { key: 'ref', label: 'Count', main: true, render: (a) => a.reference },
          { key: 'scope', label: 'Scope', sub: true, render: (a) => `${a.scope}${a.note ? ` — ${a.note}` : ''}` },
          { key: 'status', label: 'Status', render: (a) => <Pill tone={AUDIT_TONE[a.status]}>{a.status}</Pill> },
          { key: 'counted', label: 'Counted', align: 'right', render: (a) => `${a.counted}/${a.items}` },
          { key: 'var', label: 'Variance', align: 'right', value: true, render: (a) => (a.status === 'Completed' ? <b className={a.variance_value < 0 ? 'bad' : a.variance_value > 0 ? 'good' : ''}>{naira(a.variance_value)}</b> : <span className="rs-muted">—</span>) },
          { key: 'by', label: 'By', render: (a) => a.approved_by || a.started_by },
          { key: 'when', label: 'Date', render: (a) => <span className="rs-muted">{a.when}</span> },
        ]} />
      </section>
      {start && (
        <Sheet title="Start a stock count" onClose={() => setStart(false)}>
          <div className="sl-form">
            <p className="rs-muted">The count lists every product in scope with its system quantity. Nothing changes until you sign it off.</p>
            <label className="sl-f"><span>Category</span><select value={scope.category} onChange={(e) => set('category', e.target.value)}><option value="">All categories</option>{(d.categories || []).map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="sl-f"><span>Location</span><select value={scope.location} onChange={(e) => set('location', e.target.value)}><option value="">All locations</option>{(d.locations || []).map((l) => <option key={l}>{l}</option>)}</select></label>
            <label className="sl-f"><span>Note</span><input value={scope.note} onChange={(e) => set('note', e.target.value)} placeholder="e.g. End-of-term count" /></label>
            <button type="button" className="rs-btn primary wide" onClick={go}><i className="fas fa-clipboard-list" aria-hidden="true" /> Start counting</button>
          </div>
        </Sheet>
      )}
    </div>
  );
}

export function AuditDetail({ d, notify }) {
  const nav = useNav();
  const open = d.status === 'Counting';
  const [counts, setCounts] = useState(() => { const m = {}; d.items.forEach((i) => { m[i.id] = i.counted_qty == null ? '' : String(i.counted_qty); }); return m; });
  const [show, setShow] = useState('all');
  const [q, setQ] = useState('');
  const setCount = (id, v) => setCounts((s) => ({ ...s, [id]: v.replace(/[^0-9]/g, '') }));
  const payload = () => d.items.map((i) => ({ item_id: i.id, counted_qty: counts[i.id] === '' ? null : Number(counts[i.id]) }));
  const has = (i) => counts[i.id] !== '' && counts[i.id] != null;
  const vq = (i) => (has(i) ? Number(counts[i.id]) - i.system_qty : null);
  const preview = d.items.reduce((acc, i) => acc + (has(i) ? vq(i) * (i.unit_cost || 0) : 0), 0);
  const countedN = d.items.filter(has).length;
  const diffN = d.items.filter((i) => has(i) && vq(i) !== 0).length;
  const save = async () => { const r = await submitJson(d.save_url, { counts: payload() }); if (r.ok) notify('success', 'Counts saved.'); else notify('error', r.error || 'Save failed.'); };
  const complete = async () => {
    if (!await confirm({ title: 'Sign off count', tone: 'primary', confirmText: 'Sign off', message: `Sign off this count? Stock will be corrected to the counted quantities${countedN < d.items.length ? ` (${d.items.length - countedN} uncounted item(s) stay as they are)` : ''} and the net variance of ${naira(preview)} posted to Finance.` })) return;
    const r = await submitJson(d.complete_url, { counts: payload() }); if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not complete.');
  };
  const cancel = async () => {
    if (!await confirm({ title: 'Cancel count', tone: 'danger', confirmText: 'Cancel count', cancelText: 'Keep', message: 'Cancel this count? No stock will change.' })) return;
    const r = await submitJson(d.cancel_url, {}); if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not cancel.');
  };
  const t = q.trim().toLowerCase();
  const rows = d.items.filter((i) => (!t || `${i.product} ${i.category}`.toLowerCase().includes(t))
    && (show === 'all' || (show === 'todo' && !has(i)) || (show === 'diff' && has(i) && vq(i) !== 0)));
  const variance = open ? preview : d.variance_value;
  return (
    <div className={'rs sl' + (open ? ' has-bar' : '')}>
      <Head icon="fa-clipboard-check" title={d.reference} sub={`${d.scope} · started by ${d.started_by}${d.approved_by ? ` · signed off by ${d.approved_by}` : ''}`}>
        <Menu label="More" items={[
          canWrite(d, 'counts_export') && { icon: 'fa-file-excel', label: 'Export count sheet', href: d.export_url, native: true },
          open && canWrite(d, 'counts_cancel') && { icon: 'fa-ban', label: 'Cancel this count', onClick: cancel, danger: true },
        ]} />
      </Head>
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'Status', value: d.status, tone: AUDIT_TONE[d.status] },
        { label: 'Counted', value: `${countedN}/${d.items.length}`, sub: open ? `${d.items.length - countedN} to go` : '' },
        { label: 'Differences', value: diffN, tone: diffN ? 'mid' : '' },
        { label: open ? 'Variance so far' : 'Net variance', value: short(variance), tone: variance < 0 ? 'bad' : variance > 0 ? 'good' : '' },
      ]} />
      <div className="rs-toolbar">
        <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" /><input type="search" placeholder="Find a product" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a product" /></label>
        <Seg label="Show" value={show} onChange={setShow} options={[{ value: 'all', label: 'All' }, { value: 'todo', label: 'Not counted', count: d.items.length - countedN }, { value: 'diff', label: 'Differences', count: diffN }]} />
      </div>
      <section className="rs-card flush">
        <div className="sl-count">
          {rows.map((i) => {
            const v = vq(i);
            return (
              <div key={i.id} className={'sl-cnt' + (v ? ' diff' : '') + (has(i) ? ' done' : '')}>
                <span className="n"><b>{i.product}</b><small>{i.category} · system {i.system_qty}</small></span>
                {open ? <input type="text" inputMode="numeric" value={counts[i.id]} placeholder="–" onChange={(e) => setCount(i.id, e.target.value)} onFocus={(e) => e.target.select()} aria-label={`Counted ${i.product}`} />
                  : <b className="c">{i.counted_qty == null ? '—' : i.counted_qty}</b>}
                <span className={'v ' + (v < 0 ? 'bad' : v > 0 ? 'good' : '')}>{v == null ? <small className="rs-muted">not counted</small> : v === 0 ? <small className="good"><i className="fas fa-check" aria-hidden="true" /> matches</small>
                  : <><b>{v > 0 ? '+' : ''}{v}</b><small>{naira(v * (i.unit_cost || 0))}</small></>}</span>
              </div>
            );
          })}
          {!rows.length && <p className="rs-muted rs-pad">Nothing to show here.</p>}
        </div>
        {open && (
          <Bar>
            <span className="rs-bar-t"><b>{countedN} of {d.items.length} counted</b><small>Variance {naira(preview)}</small></span>
            {canWrite(d, 'counts_create') && <button type="button" className="rs-btn ghost" onClick={save}><i className="fas fa-floppy-disk" aria-hidden="true" /><span className="rs-hide-sm">Save</span></button>}
            {d.can_signoff !== false && canWrite(d, 'counts_signoff') && <button type="button" className="rs-btn primary" onClick={complete}><i className="fas fa-check-double" aria-hidden="true" /> Sign off</button>}
          </Bar>
        )}
      </section>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Buying: purchase orders + suppliers
// ═══════════════════════════════════════════════════════════════════════════
export function Purchases({ d }) {
  const nav = useNav();
  const [creating, setCreating] = useState(false);
  const status = (d.applied || {}).status || '';
  const apply = (st) => navParams(nav.go, d.self_url, { status: st, supplier_id: (d.applied || {}).supplier_id || '' });
  const open = d.orders.filter((o) => ['Approved', 'Ordered', 'Partially Received'].includes(o.status));
  const pending = d.orders.filter((o) => ['Draft', 'Pending Approval'].includes(o.status));
  return (
    <div className="rs sl">
      <Head icon="fa-file-invoice" title="Purchase orders" sub="Order stock from suppliers and receive it in">
        {canWrite(d, 'purchasing_create') && <button type="button" className="rs-btn primary" onClick={() => setCreating(true)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">New order</span></button>}
      </Head>
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'Awaiting delivery', value: d.awaiting_delivery || 0, tone: d.awaiting_delivery ? 'mid' : '' },
        { label: 'Waiting for approval', value: pending.length, tone: pending.length ? 'mid' : '' },
        { label: 'Value on order', value: short(open.reduce((t, o) => t + (o.total || 0), 0)) },
      ]} />
      <Chips label="Status" value={status} onChange={apply} items={[{ value: '', label: 'All' }, ...(d.statuses || []).map((s) => ({ value: s, label: s }))]} />
      <section className="rs-card flush">
        <DataList rows={d.orders} onRow={(po) => nav.go(po.url)} empty={<Blank icon="fa-file-invoice" title="No purchase orders"><p>Create an order when you need to restock from a supplier.</p></Blank>} cols={[
          { key: 'po', label: 'Order', main: true, render: (po) => po.po_number },
          { key: 'supplier', label: 'Supplier', sub: true, render: (po) => po.supplier },
          { key: 'status', label: 'Status', render: (po) => <Pill tone={PO_TONE[po.status]}>{po.status}</Pill> },
          { key: 'expected', label: 'Expected', render: (po) => po.expected_date || '—' },
          { key: 'created', label: 'Created', render: (po) => <span className="rs-muted">{po.created_at}</span> },
          { key: 'total', label: 'Total', align: 'right', value: true, render: (po) => <b>{naira(po.total)}</b> },
        ]} />
      </section>
      {creating && <PurchaseForm d={d} onClose={() => setCreating(false)} onSaved={(r) => { if (r.redirect) nav.go(r.redirect); else nav.refresh(); }} />}
    </div>
  );
}

export function PurchaseDetail({ d, notify }) {
  const nav = useNav();
  const po = d.po; const u = d.urls;
  const [recv, setRecv] = useState({});
  const [invoice, setInvoice] = useState(po.invoice_number || '');
  const act = async (url, body) => { const r = await submitJson(url, body || {}); if (r.ok) nav.refresh(); else notify('error', r.error || 'Action failed.'); };
  const canApprove = (po.status === 'Draft' || po.status === 'Pending Approval') && d.can_approve !== false;
  const canReceive = ['Approved', 'Ordered', 'Partially Received'].includes(po.status) && canWrite(d, 'purchasing_receive');
  const canCancel = canWrite(d, 'purchasing_cancel') && po.is_open;
  const toReceive = d.items.filter((it) => Number(recv[it.id]) > 0);
  const doReceive = () => {
    if (!toReceive.length) { notify('error', 'Enter the quantities that arrived.'); return; }
    act(u.receive, { invoice_number: invoice, items: toReceive.map((it) => ({ item_id: it.id, receive_qty: Number(recv[it.id]) })) });
  };
  const allIn = () => { const m = {}; d.items.forEach((it) => { if (it.outstanding > 0) m[it.id] = String(it.outstanding); }); setRecv(m); };
  const ordered = d.items.reduce((t, it) => t + it.quantity, 0);
  const received = d.items.reduce((t, it) => t + it.quantity_received, 0);
  const STEPS = ['Draft', 'Approved', 'Received'];
  const stepIdx = po.status === 'Received' ? 2 : ['Approved', 'Ordered', 'Partially Received'].includes(po.status) ? 1 : 0;
  return (
    <div className={'rs sl' + (canReceive ? ' has-bar' : '')}>
      <Head icon="fa-file-invoice" title={po.po_number} sub={`${po.supplier} · ${naira(po.total)}`}>
        {canApprove && <button type="button" className="rs-btn success" onClick={() => act(u.approve)}><i className="fas fa-check" aria-hidden="true" /><span className="rs-hide-sm">Approve</span></button>}
        <Menu label="More" items={[
          { icon: 'fa-truck-field', label: 'Supplier', href: u.supplier },
          canCancel && { icon: 'fa-ban', label: 'Cancel order', onClick: () => act(u.cancel), danger: true },
        ]} />
      </Head>
      <SalesNav d={d} />
      {po.status === 'Cancelled' ? <div className="sc-alert bad"><i className="fas fa-ban" aria-hidden="true" /><span>This order was cancelled.</span></div> : (
        <div className="sl-steps">{STEPS.map((s, i) => <span key={s} className={i < stepIdx ? 'done' : i === stepIdx ? 'on' : ''}><b>{i < stepIdx ? <i className="fas fa-check" aria-hidden="true" /> : i + 1}</b>{i === 1 && po.status === 'Partially Received' ? 'Part received' : s}</span>)}</div>
      )}
      <Tiles items={[
        { label: 'Status', value: po.status, tone: PO_TONE[po.status] },
        { label: 'Received', value: `${received}/${ordered}`, sub: 'units' },
        { label: 'Expected', value: po.expected_date || '—', sub: po.approved_by ? `approved by ${po.approved_by}` : '' },
      ]} />
      <section className="rs-card flush">
        <header className="rs-card-h pad"><h3><i className="fas fa-list" aria-hidden="true" /> Items</h3>
          {canReceive && <button type="button" className="rs-link" onClick={allIn}>Everything arrived</button>}</header>
        <div className="sl-count">
          {d.items.map((it) => (
            <div key={it.id} className={'sl-cnt' + (it.outstanding === 0 ? ' done' : '')}>
              <span className="n"><b>{it.description}</b><small>{it.quantity} ordered · {naira(it.unit_cost)} each · {it.quantity_received} received</small></span>
              {canReceive && it.outstanding > 0 ? <input type="number" inputMode="numeric" min="0" max={it.outstanding} value={recv[it.id] || ''} placeholder={`of ${it.outstanding}`}
                onChange={(e) => setRecv((s) => ({ ...s, [it.id]: e.target.value }))} aria-label={`Receive ${it.description}`} />
                : <b className="c">{it.outstanding > 0 ? it.outstanding : ''}</b>}
              <span className="v">{it.outstanding === 0 ? <small className="good"><i className="fas fa-check" aria-hidden="true" /> all in</small> : <small className="rs-muted">{it.outstanding} to come</small>}</span>
            </div>
          ))}
        </div>
        {canReceive && (
          <Bar>
            <label className="sl-inv"><span>Invoice no.</span><input value={invoice} onChange={(e) => setInvoice(e.target.value)} placeholder="Invoice no. (optional)" /></label>
            <button type="button" className="rs-btn primary" onClick={doReceive} disabled={!toReceive.length}><i className="fas fa-truck-ramp-box" aria-hidden="true" /> Receive{toReceive.length ? ` ${toReceive.length}` : ''}</button>
          </Bar>
        )}
      </section>
    </div>
  );
}

export function Suppliers({ d }) {
  const nav = useNav();
  const [editing, setEditing] = useState(null);
  const owed = d.suppliers.reduce((t, s) => t + (s.outstanding || 0), 0);
  return (
    <div className="rs sl">
      <Head icon="fa-truck-field" title="Suppliers" sub="Who you buy from and what you owe them">
        {canWrite(d, 'purchasing_create') && <button type="button" className="rs-btn primary" onClick={() => setEditing({})}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Add supplier</span></button>}
      </Head>
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'Suppliers', value: d.suppliers.length },
        { label: 'You owe', value: short(owed), tone: owed > 0 ? 'bad' : 'good' },
        { label: 'Received (all time)', value: short(d.suppliers.reduce((t, s) => t + (s.received_value || 0), 0)) },
      ]} />
      <section className="rs-card flush">
        <DataList rows={d.suppliers} onRow={(s) => nav.go(s.url)} empty={<Blank icon="fa-truck-field" title="No suppliers yet"><p>Add the companies you buy stock from.</p></Blank>} cols={[
          { key: 'name', label: 'Supplier', main: true, render: (s) => s.company_name },
          { key: 'contact', label: 'Contact', sub: true, render: (s) => [s.contact_person, s.phone].filter(Boolean).join(' · ') || '—' },
          { key: 'orders', label: 'Orders', align: 'right', render: (s) => s.orders },
          { key: 'recv', label: 'Received', align: 'right', render: (s) => naira(s.received_value) },
          { key: 'paid', label: 'Paid', align: 'right', render: (s) => naira(s.paid) },
          { key: 'owe', label: 'Owed', align: 'right', value: true, render: (s) => <b className={s.outstanding > 0 ? 'bad' : ''}>{naira(s.outstanding)}</b> },
          { key: 'edit', label: '', hideSm: true, render: (s) => canWrite(d, 'purchasing_edit') && <button type="button" className="rs-icon-btn" onClick={(e) => { e.stopPropagation(); setEditing(s); }} aria-label={`Edit ${s.company_name}`}><i className="fas fa-pen" aria-hidden="true" /></button> },
        ]} />
      </section>
      {editing && <SupplierForm supplier={editing.id ? editing : null} addUrl={d.add_url} onClose={() => setEditing(null)} onSaved={() => nav.refresh()} />}
    </div>
  );
}

export function SupplierDetail({ d, notify }) {
  const nav = useNav();
  const s = d.supplier; const st = d.stats || {};
  const [pay, setPay] = useState({ amount: '', method: (d.methods || ['Cash'])[0], reference: '', note: '' });
  const [paying, setPaying] = useState(false);
  const setP = (k, v) => setPay((x) => ({ ...x, [k]: v }));
  const doPay = async () => {
    if (!(Number(pay.amount) > 0)) { notify('error', 'Enter an amount.'); return; }
    const r = await submitJson(d.pay_url, pay);
    if (r.ok) { setPaying(false); nav.refresh(); } else notify('error', r.error || 'Could not record payment.');
  };
  return (
    <div className="rs sl">
      <Head icon="fa-truck-field" title={s.company_name} sub={[s.contact_person, s.phone, s.email].filter(Boolean).join(' · ') || 'Supplier'}>
        {canWrite(d, 'purchasing_pay') && st.outstanding > 0 && <button type="button" className="rs-btn primary" onClick={() => { setPay((x) => ({ ...x, amount: String(st.outstanding) })); setPaying(true); }}><i className="fas fa-money-bill" aria-hidden="true" /><span className="rs-hide-sm">Record payment</span></button>}
      </Head>
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'You owe', value: short(st.outstanding), tone: st.outstanding > 0 ? 'bad' : 'good' },
        { label: 'Received value', value: short(st.received_value) },
        { label: 'Paid', value: short(st.paid) },
        { label: 'Orders', value: st.orders },
      ]} />
      <div className="an-grid two">
        <section className="rs-card flush">
          <header className="rs-card-h pad"><h3><i className="fas fa-file-invoice" aria-hidden="true" /> Orders</h3></header>
          <DataList rows={d.orders} onRow={(po) => nav.go(po.url)} empty={<p className="rs-muted rs-pad">No orders yet.</p>} cols={[
            { key: 'po', label: 'Order', main: true, render: (po) => po.po_number },
            { key: 'when', label: 'Date', sub: true, render: (po) => po.created_at },
            { key: 'status', label: 'Status', render: (po) => <Pill tone={PO_TONE[po.status]}>{po.status}</Pill> },
            { key: 'total', label: 'Total', align: 'right', value: true, render: (po) => <b>{naira(po.total)}</b> },
          ]} />
        </section>
        <section className="rs-card flush">
          <header className="rs-card-h pad"><h3><i className="fas fa-money-bill" aria-hidden="true" /> Payments</h3></header>
          <DataList rows={d.payments} empty={<p className="rs-muted rs-pad">No payments yet.</p>} cols={[
            { key: 'when', label: 'Date', main: true, render: (p) => p.when },
            { key: 'method', label: 'Method', sub: true, render: (p) => [p.method, p.reference].filter(Boolean).join(' · ') },
            { key: 'amt', label: 'Amount', align: 'right', value: true, render: (p) => <b>{naira(p.amount)}</b> },
          ]} />
        </section>
      </div>
      {paying && (
        <Sheet title={`Pay ${s.company_name}`} onClose={() => setPaying(false)}>
          <div className="sl-form">
            <p className="rs-muted">Outstanding: <b>{naira(st.outstanding)}</b></p>
            <label className="sl-f"><span>Amount (₦)</span><input type="number" inputMode="decimal" value={pay.amount} onChange={(e) => setP('amount', e.target.value)} /></label>
            <div className="sl-f"><span>Method</span><Chips label="Method" value={pay.method} onChange={(v) => setP('method', v)} items={(d.methods || []).map((m) => ({ value: m, label: m }))} /></div>
            <label className="sl-f"><span>Reference</span><input value={pay.reference} onChange={(e) => setP('reference', e.target.value)} placeholder="Transfer ref, cheque no…" /></label>
            <button type="button" className="rs-btn primary wide" onClick={doPay}><i className="fas fa-check" aria-hidden="true" /> Record payment</button>
          </div>
        </Sheet>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Insights: analytics, reports, promo codes
// ═══════════════════════════════════════════════════════════════════════════
export function Analytics({ d }) {
  const nav = useNav();
  const s = d.summary || {};
  const [brk, setBrk] = useState('products');
  const go = (extra) => navParams(nav.go, d.self_url, { from: d.from, to: d.to, product_id: d.product_id || '', ...extra });
  const margin = s.revenue ? Math.round((s.profit / s.revenue) * 100) : null;
  const rows = { products: d.top_products || [], category: d.by_category || [], method: d.by_method || [], cashier: d.by_cashier || [] }[brk];
  const bestDay = (d.trend || []).reduce((b, r) => (r.revenue > (b ? b.revenue : -1) ? r : b), null);
  return (
    <div className="rs sl">
      <Head icon="fa-chart-pie" title="Sales analytics" sub={`${d.from} to ${d.to}`} />
      <SalesNav d={d} />
      <RangeBar from={d.from} to={d.to} onApply={(from, to) => go({ from, to })} />
      <Tiles items={[
        { label: 'Revenue', value: short(s.revenue), tone: 'good' },
        { label: 'Gross profit', value: short(s.profit), sub: margin != null ? `${margin}% margin` : '' },
        { label: 'Sales', value: s.count, sub: `avg ${short(s.avg_sale)}` },
        { label: 'Units sold', value: s.units },
        bestDay && bestDay.revenue > 0 && { label: 'Best day', value: short(bestDay.revenue), sub: bestDay.label },
      ]} />
      <section className="rs-card">
        <header className="rs-card-h"><h3><i className="fas fa-chart-column" aria-hidden="true" /> Sales by day</h3></header>
        <Trend rows={d.trend || []} fmt={naira} />
      </section>
      <div className="an-grid two">
        <section className="rs-card">
          <header className="rs-card-h"><h3><i className="fas fa-ranking-star" aria-hidden="true" /> Breakdown</h3></header>
          <Seg label="Breakdown" value={brk} onChange={setBrk} options={[{ value: 'products', label: 'Products' }, { value: 'category', label: 'Category' }, { value: 'method', label: 'Payment' }, { value: 'cashier', label: 'Cashier' }]} />
          <div style={{ marginTop: '.8rem' }}>
            <Bars rows={rows} label={(r) => r.name || r.label} fmt={naira} sub={(r) => (r.units != null ? `${r.units} units` : r.count != null ? `${r.count} sales` : '')} />
          </div>
        </section>
        <section className="rs-card">
          <header className="rs-card-h"><h3><i className="fas fa-users" aria-hidden="true" /> Who bought a product</h3></header>
          <select className="sl-select wide" value={d.product_id || ''} onChange={(e) => go({ product_id: e.target.value })} aria-label="Product">
            <option value="">Choose a product…</option>{(d.products || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          {d.drill ? (<>
            <p className="rs-muted" style={{ margin: '.7rem 0' }}><b>{d.drill.total_students}</b> students bought <b>{d.drill.total_units}</b> units{d.drill.non_student_units ? ` · ${d.drill.non_student_units} to staff and walk-ins` : ''}</p>
            <Bars rows={d.drill.rows} label={(r) => r.label} value={(r) => r.units} fmt={(v) => `${v} units`} sub={(r) => `${r.students} students · ${naira(r.revenue)}`} empty="No students bought this in the period." />
          </>) : <p className="rs-muted" style={{ marginTop: '.7rem' }}>See which classes bought it — useful for textbooks and uniforms.</p>}
        </section>
      </div>
    </div>
  );
}

export function Reports({ d }) {
  const nav = useNav();
  const r = d.report || { columns: [], rows: [] };
  const [from, setFrom] = useState(d.from || '');
  const [to, setTo] = useState(d.to || '');
  const [category, setCategory] = useState(d.category || '');
  const go = (extra) => navParams(nav.go, d.self_url, { kind: d.kind, from, to, category, ...extra });
  const cell = (row, col) => { const v = row[col.key]; return col.money ? naira(v || 0) : (v === '' || v == null ? '—' : v); };
  const exportUrl = (fmt) => { const p = new URLSearchParams({ kind: d.kind, format: fmt }); if (from) p.set('from', from); if (to) p.set('to', to); if (category) p.set('category', category); return `${d.export_url}?${p.toString()}`; };
  const moneyCol = r.columns.find((c) => c.money);
  const cols = r.columns.map((c, i) => ({ key: c.key, label: c.label, align: c.align === 'right' ? 'right' : undefined, main: i === 0, sub: i === 1 && !c.money, value: c === moneyCol, render: (row) => cell(row, c) }));
  return (
    <div className="rs sl">
      <Head icon="fa-file-lines" title="Reports" sub={r.title}>
        <Menu label="Export" items={[
          canWrite(d, 'reports_export') && { icon: 'fa-file-csv', label: 'Download CSV', href: exportUrl('csv'), native: true },
          canWrite(d, 'reports_export') && { icon: 'fa-file-excel', label: 'Download Excel', href: exportUrl('excel'), native: true },
          { icon: 'fa-print', label: 'Print', onClick: () => window.print() },
        ]} />
      </Head>
      <SalesNav d={d} />
      <Chips label="Report" value={d.kind} onChange={(k) => go({ kind: k })} items={(d.report_kinds || []).map((k) => ({ value: k.key, label: k.label }))} />
      <div className="rs-toolbar">
        {d.is_period && <span className="sl-range-c"><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" /><span>to</span><input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" /></span>}
        <select className="sl-select" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category"><option value="">All categories</option>{(d.categories || []).map((c) => <option key={c}>{c}</option>)}</select>
        <button type="button" className="rs-btn primary sm" onClick={() => go()}>Update</button>
        <span className="sc-count">{r.rows.length} row{r.rows.length === 1 ? '' : 's'}</span>
      </div>
      {r.totals && (
        <Tiles items={r.columns.filter((c) => r.totals[c.key] != null).slice(0, 4).map((c) => ({ label: `Total ${c.label.toLowerCase()}`, value: c.money ? short(r.totals[c.key]) : r.totals[c.key] }))} />
      )}
      <section className="rs-card flush">
        <DataList rows={r.rows} rowKey={(row, i) => i} cols={cols} empty={<Blank icon="fa-file-lines" title="Nothing to report"><p>No data for this selection.</p></Blank>}
          foot={r.totals ? { table: <tr>{r.columns.map((c, i) => <td key={c.key} className={c.align === 'right' ? 'r' : ''}>{i === 0 ? <b>Total</b> : r.totals[c.key] != null ? <b>{c.money ? naira(r.totals[c.key]) : r.totals[c.key]}</b> : ''}</td>)}</tr> } : null} />
      </section>
    </div>
  );
}

export function Promos({ d, notify }) {
  const nav = useNav();
  const blank = { code: '', description: '', kind: 'percent', value: '', min_purchase: '', category: '', expires_on: '', usage_limit: '' };
  const [f, setF] = useState(blank);
  const [adding, setAdding] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const add = async () => {
    if (!f.code.trim()) { notify('error', 'Enter a code.'); return; }
    const r = await submitJson(d.add_url, f);
    if (r.ok) { setF(blank); setAdding(false); nav.refresh(); } else notify('error', r.error || 'Could not add code.');
  };
  const toggle = async (p) => { const r = await submitJson(p.toggle_url, {}); if (r.ok) nav.refresh(); else notify('error', r.error || 'Failed.'); };
  const active = d.promos.filter((p) => p.is_active).length;
  const manage = canWrite(d, 'promos_manage');
  return (
    <div className="rs sl">
      <Head icon="fa-tags" title="Promo codes" sub="Discounts cashiers can apply at checkout">
        {manage && <button type="button" className="rs-btn primary" onClick={() => setAdding(true)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">New code</span></button>}
      </Head>
      <SalesNav d={d} />
      <Tiles items={[
        { label: 'Active codes', value: active, tone: 'good' },
        { label: 'Times used', value: d.promos.reduce((t, p) => t + (p.used_count || 0), 0) },
      ]} />
      {d.promos.length ? (
        <div className="sl-promos">
          {d.promos.map((p) => (
            <div key={p.id} className={'sl-promo' + (p.is_active ? '' : ' off')}>
              <div className="sl-promo-top">
                <span className="code">{p.code}</span>
                <b className="off-v">{p.kind === 'percent' ? `${p.value}% off` : `${naira(p.value)} off`}</b>
                {manage && <button type="button" role="switch" aria-checked={p.is_active} className={'sc-switch' + (p.is_active ? ' on' : '')} onClick={() => toggle(p)} aria-label={`${p.is_active ? 'Turn off' : 'Turn on'} ${p.code}`}><i /></button>}
              </div>
              {p.description && <p>{p.description}</p>}
              <div className="sl-promo-m">
                <span>{p.category || 'Any category'}</span>
                {p.min_purchase > 0 && <span>min {naira(p.min_purchase)}</span>}
                {p.expires_on && <span>till {p.expires_on}</span>}
                <span>used {p.used_count}{p.usage_limit != null ? `/${p.usage_limit}` : ''}</span>
              </div>
              {p.usage_limit != null && <Meter value={p.used_count} max={p.usage_limit} tone={p.used_count >= p.usage_limit ? 'bad' : 'n'} />}
            </div>
          ))}
        </div>
      ) : <Blank icon="fa-tags" title="No promo codes yet"><p>Create a code for open days, staff discounts or bulk buys.</p></Blank>}
      {adding && (
        <Sheet title="New promo code" onClose={() => setAdding(false)}>
          <div className="sl-form">
            <label className="sl-f"><span>Code</span><input value={f.code} onChange={(e) => set('code', e.target.value.toUpperCase())} placeholder="e.g. OPENDAY10" /></label>
            <div className="sl-f"><span>Discount</span><Seg label="Type" value={f.kind} onChange={(v) => set('kind', v)} options={[{ value: 'percent', label: 'Percent %' }, { value: 'fixed', label: 'Fixed ₦' }]} /></div>
            <label className="sl-f"><span>{f.kind === 'percent' ? 'Percent off' : 'Amount off (₦)'}</span><input type="number" inputMode="decimal" value={f.value} onChange={(e) => set('value', e.target.value)} /></label>
            <label className="sl-f"><span>Only for category</span><select value={f.category} onChange={(e) => set('category', e.target.value)}><option value="">Any category</option>{(d.categories || []).map((c) => <option key={c}>{c}</option>)}</select></label>
            <div className="sl-two">
              <label className="sl-f"><span>Minimum spend (₦)</span><input type="number" value={f.min_purchase} onChange={(e) => set('min_purchase', e.target.value)} /></label>
              <label className="sl-f"><span>Usage limit</span><input type="number" value={f.usage_limit} placeholder="No limit" onChange={(e) => set('usage_limit', e.target.value)} /></label>
            </div>
            <label className="sl-f"><span>Expires on</span><input type="date" value={f.expires_on} onChange={(e) => set('expires_on', e.target.value)} /></label>
            <label className="sl-f"><span>Description</span><input value={f.description} onChange={(e) => set('description', e.target.value)} placeholder="Shown to the cashier" /></label>
            <button type="button" className="rs-btn primary wide" onClick={add}><i className="fas fa-plus" aria-hidden="true" /> Create code</button>
          </div>
        </Sheet>
      )}
    </div>
  );
}

// Re-export so SalesApp can keep its old link helper available if needed.
export { Link };
