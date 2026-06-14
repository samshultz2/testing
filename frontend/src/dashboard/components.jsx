import React from 'react';

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
export function Kpi({ tone = 'blue', icon, value, label, title }) {
  return (
    <div className="kpi">
      <div className={'ic ' + tone}><i className={'fas ' + icon} aria-hidden="true" /></div>
      <div>
        <div className="v" title={title}>{value}</div>
        <div className="l">{label}</div>
      </div>
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
