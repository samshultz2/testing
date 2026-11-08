// Shared pieces for the redesigned sales & inventory screens: the section tab
// bar (with sub-tabs for Stock / Buying / Insights) and a list that is a table
// on laptops and tappable cards on phones, built from one column definition.
import React from 'react';
import { usePhone } from '../subjects/results';

const GROUPS = [
  { key: 'home', label: 'Overview', icon: 'fa-gauge-high', pages: ['dashboard'], href: 'dashboard' },
  { key: 'sell', label: 'Sell', icon: 'fa-cash-register', pages: ['new_sale'], href: 'new_sale' },
  { key: 'sales', label: 'Sales', icon: 'fa-receipt', pages: ['history'], href: 'history' },
  { key: 'products', label: 'Products', icon: 'fa-boxes-stacked', pages: ['products'], href: 'products' },
  { key: 'stock', label: 'Stock', icon: 'fa-warehouse', pages: ['movements', 'batches', 'audits', 'audit_detail'], href: 'movements',
    subs: [['movements', 'Movements'], ['batches', 'Batches & expiry'], ['audits', 'Stock counts']] },
  { key: 'buy', label: 'Buying', icon: 'fa-truck-field', pages: ['purchases', 'purchase_detail', 'suppliers', 'supplier_detail'], href: 'purchases',
    subs: [['purchases', 'Purchase orders'], ['suppliers', 'Suppliers']] },
  { key: 'insights', label: 'Insights', icon: 'fa-chart-pie', pages: ['analytics', 'reports', 'promos'], href: 'analytics',
    subs: [['analytics', 'Analytics'], ['reports', 'Reports'], ['promos', 'Promo codes']] },
];
const SUB_OF = { audit_detail: 'audits', purchase_detail: 'purchases', supplier_detail: 'suppliers' };

export function SalesNav({ d }) {
  const u = d.salesnav || {};
  const page = d.page;
  const g = GROUPS.find((x) => x.pages.includes(page));
  const sub = SUB_OF[page] || page;
  return (
    <>
      <nav className="sl-nav" aria-label="Sales sections">
        {GROUPS.map((x) => (
          <a key={x.key} href={u[x.href]} className={g && g.key === x.key ? 'on' : ''} aria-current={g && g.key === x.key ? 'page' : undefined}>
            <i className={'fas ' + x.icon} aria-hidden="true" /><span>{x.label}</span></a>
        ))}
        {u.assets && <a href={u.assets} className={'sl-nav-x' + (page === 'assets' ? ' on' : '')} aria-current={page === 'assets' ? 'page' : undefined}><i className="fas fa-building-columns" aria-hidden="true" /><span>Assets</span></a>}
      </nav>
      {g && g.subs && (
        <nav className="sl-sub" aria-label={`${g.label} pages`}>
          {g.subs.map(([k, l]) => <a key={k} href={u[k]} className={sub === k ? 'on' : ''}>{l}</a>)}
        </nav>
      )}
    </>
  );
}

// cols: [{ key, label, render(row), align:'right', main, sub, value, hideSm, width }]
// On phones: `main` is the title, `sub` the line under it, `value` the big
// figure on the right, and the rest become small "label value" pairs.
export function DataList({ rows, cols, rowKey = (r, i) => r.id ?? i, onRow, empty, foot, className = '' }) {
  const phone = usePhone();
  const val = (c, r) => (c.render ? c.render(r) : r[c.key]);
  if (!rows.length) return empty || null;
  if (phone) {
    const main = cols.find((c) => c.main) || cols[0];
    const subs = cols.filter((c) => c.sub);
    const value = cols.find((c) => c.value);
    const rest = cols.filter((c) => c !== main && !c.sub && c !== value && !c.hideSm && c.label);
    return (
      <div className={'sl-cards ' + className}>
        {rows.map((r, i) => {
          const Tag = onRow ? 'button' : 'div';
          return (
            <Tag key={rowKey(r, i)} type={onRow ? 'button' : undefined} className={'sl-crd' + (onRow ? ' click' : '')} onClick={onRow ? () => onRow(r) : undefined}>
              <div className="sl-crd-top">
                <div className="sl-crd-t"><b>{val(main, r)}</b>{subs.map((c) => <small key={c.key}>{val(c, r)}</small>)}</div>
                {value && <span className="sl-crd-v">{val(value, r)}</span>}
              </div>
              {rest.length > 0 && <div className="sl-crd-m">{rest.map((c) => {
                const v = val(c, r);
                return v === '' || v == null || v === '—' ? null : <span key={c.key}><em>{c.label}</em> {v}</span>;
              })}</div>}
            </Tag>
          );
        })}
        {foot && <div className="sl-crd foot">{foot.phone || null}</div>}
      </div>
    );
  }
  return (
    <div className={'sl-tbl-wrap ' + className}>
      <table className="sl-tbl">
        <thead><tr>{cols.map((c) => <th key={c.key} className={c.align === 'right' ? 'r' : c.align === 'center' ? 'c' : ''} style={c.width ? { width: c.width } : undefined}>{c.label}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={rowKey(r, i)} className={onRow ? 'click' : ''} onClick={onRow ? () => onRow(r) : undefined}>
            {cols.map((c) => <td key={c.key} className={(c.align === 'right' ? 'r' : c.align === 'center' ? 'c' : '') + (c.main ? ' main' : '')}>{val(c, r)}</td>)}
          </tr>
        ))}</tbody>
        {foot && foot.table && <tfoot>{foot.table}</tfoot>}
      </table>
    </div>
  );
}

export function Pill({ tone = '', children, icon }) {
  return <span className={'sl-pill ' + tone}>{icon && <i className={'fas ' + icon} aria-hidden="true" />}{children}</span>;
}

export const PO_TONE = { Received: 'good', Cancelled: 'bad', 'Partially Received': 'info', Approved: 'info', Ordered: 'info', Draft: '', 'Pending Approval': 'mid' };
export const AUDIT_TONE = { Completed: 'good', Cancelled: 'bad', Counting: 'mid' };

// Horizontal bars for breakdowns (value formatted by `fmt`).
export function Bars({ rows, label = (r) => r.label, value = (r) => r.revenue, fmt = (v) => v, sub, empty = 'No data for this period.' }) {
  if (!rows.length) return <p className="rs-muted">{empty}</p>;
  const max = Math.max(1, ...rows.map((r) => Number(value(r)) || 0));
  return (
    <div className="sl-bars">
      {rows.map((r, i) => (
        <div key={i} className="sl-bar">
          <span className="l"><b>{label(r)}</b>{sub && <small>{sub(r)}</small>}</span>
          <span className="t"><i style={{ width: `${((Number(value(r)) || 0) / max) * 100}%` }} /></span>
          <strong>{fmt(value(r))}</strong>
        </div>
      ))}
    </div>
  );
}

// Day-by-day revenue columns; the last (today) is highlighted.
export function Trend({ rows, fmt }) {
  if (!rows.length) return <p className="rs-muted">No sales in this period.</p>;
  const max = Math.max(1, ...rows.map((r) => r.revenue));
  const step = rows.length > 20 ? 7 : rows.length > 10 ? 3 : 1;
  return (
    <div className="sl-trend" role="img" aria-label={'Sales by day: ' + rows.map((r) => `${r.label} ${Math.round(r.revenue)}`).join(', ')}>
      {rows.map((r, i) => (
        <div key={i} className={'sl-tcol' + (i === rows.length - 1 ? ' now' : '')} title={`${r.label}: ${fmt(r.revenue)}`}>
          <span><i style={{ height: `${Math.max(r.revenue ? 3 : 0, (r.revenue / max) * 100)}%` }} /></span>
          <small>{(i % step === 0 || i === rows.length - 1) ? r.label.split(' ')[0] : ''}</small>
        </div>
      ))}
    </div>
  );
}

// Quick date ranges → {from, to} (YYYY-MM-DD, local).
const ymd = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
export function rangeFor(key) {
  const t = new Date(); const f = new Date(t);
  if (key === 'today') return { from: ymd(t), to: ymd(t) };
  if (key === '7d') { f.setDate(t.getDate() - 6); return { from: ymd(f), to: ymd(t) }; }
  if (key === '30d') { f.setDate(t.getDate() - 29); return { from: ymd(f), to: ymd(t) }; }
  if (key === 'month') { f.setDate(1); return { from: ymd(f), to: ymd(t) }; }
  return { from: '', to: '' };
}
export function rangeKey(from, to) {
  for (const k of ['today', '7d', '30d', 'month']) { const r = rangeFor(k); if (r.from === from && r.to === to) return k; }
  return from || to ? 'custom' : 'all';
}
