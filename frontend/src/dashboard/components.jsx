import React from 'react';
import { Counter } from '../components/ui';
import Sparkline from './Sparkline';

// Sparkline/accent colour per tone — matches the icon-tile gradients below.
export const TONE_HEX = {
  blue: '#4f7cf7', green: '#16a34a', teal: '#0d9488', purple: '#8b5cf6',
  orange: '#f59e0b', amber: '#f59e0b', red: '#ef4444', indigo: '#6366f1',
  rose: '#f43f5e', slate: '#64748b',
};

// Redesigned headline KPI card: icon tile + trend badge on top, a big animated
// number, a label and sub-label, and a sparkline of the recent trend along the
// bottom. `delta` is { dir:'up'|'down'|'flat', pct }.
export function KpiCard({ tone = 'blue', icon, value, label, sub, title, delta, deltaLabel, series }) {
  return (
    <div className={'kpicard ' + tone}>
      <div className="kc-top">
        <div className={'kc-ic ' + tone}><i className={'fas ' + icon} aria-hidden="true" /></div>
        {(delta || deltaLabel) && (
          <div className="kc-trend">
            {delta && <TrendBadge dir={delta.dir} pct={delta.pct} />}
            {deltaLabel && <div className="kc-trendlabel">{deltaLabel}</div>}
          </div>
        )}
      </div>
      <div className="kc-value" title={title}><Counter value={value} /></div>
      <div className="kc-label">{label}</div>
      {sub && <div className="kc-sub">{sub}</div>}
      <div className="kc-spark"><Sparkline series={series} color={TONE_HEX[tone] || TONE_HEX.blue} /></div>
    </div>
  );
}

function TrendBadge({ dir = 'flat', pct }) {
  const arrow = dir === 'up' ? 'fa-arrow-up' : dir === 'down' ? 'fa-arrow-down' : 'fa-minus';
  return (
    <span className={'kc-badge ' + dir}>
      <i className={'fas ' + arrow} aria-hidden="true" /> {pct}%
    </span>
  );
}

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
