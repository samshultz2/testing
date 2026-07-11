import React from 'react';
import { Counter } from '../components/ui';

// ── currency formatting (mirrors the server's naira / naira_short filters) ──
export function naira(v) {
  return '₦' + (Number(v) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
export function nairaShort(v) {
  const n = Number(v) || 0;
  const sign = n < 0 ? '-' : '';
  const a = Math.abs(n);
  if (a >= 1e6) return `${sign}₦${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${sign}₦${(a / 1e3).toFixed(1)}k`;
  return `${sign}₦${Math.round(a).toLocaleString()}`;
}

// ── reusable presentational pieces (match the classic dashboard CSS) ──
// `delta`: { dir: 'up'|'down'|'flat', text, tone? } renders a small trend chip
// under the value so a KPI reads as movement, not an isolated number. `tone`
// overrides the colour when up isn't necessarily "good" (e.g. absentees).
export function Kpi({ tone = 'blue', icon, value, label, title, delta }) {
  return (
    <div className="kpi">
      <div className={'ic ' + tone}><i className={'fas ' + icon} aria-hidden="true" /></div>
      <div>
        <div className="v" title={title}><Counter value={value} /></div>
        <div className="l">{label}</div>
        {delta && <KpiDelta {...delta} />}
      </div>
    </div>
  );
}

function KpiDelta({ dir = 'flat', text, tone }) {
  const arrow = dir === 'up' ? 'fa-arrow-trend-up' : dir === 'down' ? 'fa-arrow-trend-down' : 'fa-minus';
  const color = tone || (dir === 'up' ? 'var(--success)' : dir === 'down' ? 'var(--danger)' : 'var(--text-secondary)');
  return (
    <div className="kpi-delta" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-xs)', color, fontWeight: 600, marginTop: 2 }}>
      <i className={'fas ' + arrow} aria-hidden="true" /><span>{text}</span>
    </div>
  );
}

export function Widget({ icon, title, action, children, bodyStyle, bodyClass = 'wb' }) {
  return (
    <div className="widget">
      <div className="wh">
        <h3><i className={'fas ' + icon} aria-hidden="true" /> {title}</h3>
        {action}
      </div>
      <div className={bodyClass} style={bodyStyle}>{children}</div>
    </div>
  );
}

export function Empty({ icon, children }) {
  return (
    <div className="empty-state">
      <i className={'fas ' + icon} aria-hidden="true" />
      <p>{children}</p>
    </div>
  );
}

export function ChartBox({ height, children }) {
  return <div className="chart-box" style={height ? { height } : undefined}>{children}</div>;
}
