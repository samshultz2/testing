/* Reusable, accessible UI primitives for the attendance SPA.
   Styling leans on the app's existing .btn/.form-control classes plus a few
   scoped .att-* classes defined in the host template, so it matches the theme. */
import React, { useState, useRef } from 'react';
import { useNav } from '../lib/section';

// Context-aware in-section link (no reload) — pulls `go` from NavCtx so callers
// don't thread it. Use for links that target another React page in the same
// section; keep a plain <a> for downloads / cross-section / external links.
export function L(props) {
  const { go } = useNav();
  return <Nav go={go} {...props} />;
}

// In-section link that navigates with no reload (via useSection's `go`), while
// still being a real <a href> (middle-click / ctrl-click open a new tab).
export function Nav({ go, href, className, children, title, style }) {
  return (
    <a href={href} className={className} title={title} style={style}
       onClick={(e) => {
         if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
         e.preventDefault(); go(href);
       }}>
      {children}
    </a>
  );
}

// Standard page header (title + optional icon + right-aligned actions). Mirrors
// the classic .page-header markup so React pages match the Jinja ones.
export function PageHeader({ title, icon, actions }) {
  return (
    <div className="page-header">
      <h1>{icon && <i className={'fas ' + icon} aria-hidden="true" />} {title}</h1>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}

// Classic .empty-state block (icon + heading + optional body), shared by every
// converted list/section page.
export function Empty({ icon = 'fa-inbox', title, children, style }) {
  return (
    <div className="empty-state" style={style}>
      <i className={'fas ' + icon} aria-hidden="true" /><h3>{title}</h3>{children}
    </div>
  );
}

// Section sub-navigation (the .fin-tabs row). `tabs` = [[key, icon, label], …];
// `urls` maps key->href; `active` is the current key (a page may map to a tab).
export function SectionTabs({ tabs, urls, active, go }) {
  return (
    <div className="fin-tabs">
      {tabs.map(([key, icon, label]) => {
        const cls = 'fin-tab' + (active === key ? ' active' : '');
        const inner = <><i className={'fas ' + icon} aria-hidden="true" /> {label}</>;
        return go
          ? <Nav key={key} go={go} href={urls[key]} className={cls}>{inner}</Nav>
          : <a key={key} href={urls[key]} className={cls}>{inner}</a>;
      })}
    </div>
  );
}

// Type-ahead picker backed by a JSON search endpoint that returns
// [{id, label}, …]. Calls onPick(id) ('' when cleared). Reused by issue forms,
// student/parent pickers, etc.
export function Autocomplete({ label, required, url, initialText, onPick, placeholder, minChars = 2 }) {
  const [text, setText] = useState(initialText || '');
  const [picked, setPicked] = useState(!!initialText);
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const tRef = useRef();
  const onInput = (v) => {
    setText(v); setPicked(false); onPick('');
    clearTimeout(tRef.current);
    if (v.trim().length < minChars) { setList([]); setOpen(false); return; }
    tRef.current = setTimeout(async () => {
      try {
        const r = await fetch(url + '?q=' + encodeURIComponent(v.trim()), { credentials: 'same-origin' });
        const rows = await r.json();
        setList(rows); setOpen(rows.length > 0);
      } catch (_) { /* ignore */ }
    }, 220);
  };
  const pick = (o) => { setText(o.label); setPicked(true); onPick(o.id); setOpen(false); };
  return (
    <div className="form-group ac-wrap">
      <label className="form-label">{label}{required && <span className="required"> *</span>}</label>
      <input type="text" className={'form-control' + (picked ? ' picked' : '')} value={text} placeholder={placeholder}
             autoComplete="off" onChange={(e) => onInput(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && <div className="ac-list">{list.map((o) => <div key={o.id} onMouseDown={() => pick(o)}>{o.label}</div>)}</div>}
    </div>
  );
}

export function Spinner({ label = 'Loading…' }) {
  return (
    <div role="status" aria-live="polite" style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#6b7280', padding: '1.25rem' }}>
      <span className="att-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ icon = 'fa-inbox', title, hint, action }) {
  return (
    <div style={{ textAlign: 'center', padding: '2rem 1rem', color: '#6b7280' }}>
      <i className={'fas ' + icon} style={{ fontSize: 30, opacity: 0.45 }} aria-hidden="true" />
      <p style={{ marginTop: 10, fontWeight: 600, color: '#374151' }}>{title}</p>
      {hint && <p style={{ fontSize: 13, maxWidth: 420, margin: '4px auto 0' }}>{hint}</p>}
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}

export function ErrorState({ title = 'Something went wrong', detail, onRetry }) {
  return (
    <div role="alert" style={{ textAlign: 'center', padding: '1.5rem', color: '#991b1b' }}>
      <i className="fas fa-triangle-exclamation" style={{ fontSize: 26 }} aria-hidden="true" />
      <p style={{ marginTop: 8, fontWeight: 600 }}>{title}</p>
      {detail && <p style={{ fontSize: 13, color: '#6b7280' }}>{String(detail)}</p>}
      {onRetry && <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: 10 }} onClick={onRetry}>Try again</button>}
    </div>
  );
}

// Shown when a screen genuinely needs the network (e.g. server-computed reports).
export function OfflineRequired({ what = 'this' }) {
  return (
    <div role="status" style={{ textAlign: 'center', padding: '2rem 1rem', color: '#92400e' }}>
      <i className="fas fa-wifi" style={{ fontSize: 26, opacity: 0.6 }} aria-hidden="true" />
      <p style={{ marginTop: 10, fontWeight: 600 }}>You’re offline</p>
      <p style={{ fontSize: 13, maxWidth: 420, margin: '4px auto 0' }}>
        {what} needs an internet connection. Reconnect and try again — your saved marks
        will sync automatically in the meantime.
      </p>
    </div>
  );
}

export function Banner({ tone = 'info', children, onClose }) {
  const tones = {
    info: ['#eff6ff', '#1e40af', '#bfdbfe'],
    success: ['#f0fdf4', '#166534', '#bbf7d0'],
    warn: ['#fffbeb', '#92400e', '#fde68a'],
    error: ['#fef2f2', '#991b1b', '#fecaca'],
  };
  const [bg, fg, bd] = tones[tone] || tones.info;
  return (
    <div role="status" style={{ background: bg, color: fg, border: '1px solid ' + bd, borderRadius: 8, padding: '.55rem .8rem', display: 'flex', gap: 8, alignItems: 'center', fontSize: 14, margin: '6px 0' }}>
      <span style={{ flex: 1 }}>{children}</span>
      {onClose && <button type="button" aria-label="Dismiss" className="att-x" onClick={onClose}>×</button>}
    </div>
  );
}

export function Pill({ tone = 'gray', children }) {
  const t = {
    green: ['#dcfce7', '#166534'], red: ['#fee2e2', '#991b1b'],
    amber: ['#fef3c7', '#92400e'], gray: ['#f1f5f9', '#475569'],
  }[tone] || ['#f1f5f9', '#475569'];
  return <span style={{ background: t[0], color: t[1], borderRadius: 999, padding: '2px 10px', fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>{children}</span>;
}

export function Field({ label, htmlFor, children, grow }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: grow ? 1 : undefined, minWidth: 180 }}>
      <label htmlFor={htmlFor} style={{ fontSize: 12, fontWeight: 600, color: '#374151' }}>{label}</label>
      {children}
    </div>
  );
}

export function Select({ id, value, onChange, options, placeholder, disabled }) {
  return (
    <select id={id} className="form-control" value={value == null ? '' : value} disabled={disabled}
            onChange={(e) => onChange(e.target.value)}>
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function Toolbar({ children }) {
  return <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12 }}>{children}</div>;
}

export function Button({ variant = 'primary', size, children, ...rest }) {
  const cls = ['btn', 'btn-' + variant, size === 'sm' ? 'btn-sm' : ''].filter(Boolean).join(' ');
  return <button type="button" className={cls} {...rest}>{children}</button>;
}

// Headline stat cards (e.g. attendance rate / students / school days).
export function StatCards({ items }) {
  return (
    <div className="att-stats">
      {items.map((it, i) => (
        <div key={i} className={'att-stat' + (it.primary ? ' is-primary' : '')}>
          <div className="att-stat-value">{it.value}</div>
          <div className="att-stat-label">{it.label}</div>
        </div>
      ))}
    </div>
  );
}

// Compact label/value grid for secondary totals.
export function InfoGrid({ items }) {
  return (
    <div className="att-info">
      {items.map((it, i) => (
        <div key={i} className="att-info-item">
          <span className="k">{it.label}</span>
          <span className="v" style={it.tone === 'primary' ? { color: 'var(--primary, #2563eb)' } : undefined}>{it.value}</span>
        </div>
      ))}
    </div>
  );
}

export function SectionTitle({ icon, children }) {
  return <h3 className="att-section-title">{icon && <i className={'fas ' + icon} aria-hidden="true" />}{children}</h3>;
}

// Performance bands (Excellent / Good / Fair / Poor).
export function PerfBands({ bands }) {
  const tones = {
    excellent: ['rgba(76,175,80,.1)', '#4caf50'],
    good: ['rgba(33,150,243,.1)', '#2196f3'],
    fair: ['rgba(255,193,7,.1)', '#ffc107'],
    poor: ['rgba(244,67,54,.1)', '#f44336'],
  };
  return (
    <div className="att-perf">
      {bands.map((b) => {
        const [bg, bd] = tones[b.tone] || tones.good;
        return (
          <div key={b.tone} className="att-perf-card" style={{ background: bg, borderLeftColor: bd }}>
            <div className="t">{b.title}</div>
            <div className="c">{b.count}</div>
            <div className="r">{b.range}</div>
          </div>
        );
      })}
    </div>
  );
}

// AM/PM tick marks for a single day (✓ present / ✗ absent).
export function AmPm({ am, pm }) {
  return (
    <span className="att-mark" aria-label={`AM ${am ? 'present' : 'absent'}, PM ${pm ? 'present' : 'absent'}`}>
      <span className={am ? 'ok' : 'no'}>{am ? '✓' : '✗'}</span>
      <span className={pm ? 'ok' : 'no'}>{pm ? '✓' : '✗'}</span>
    </span>
  );
}

// Global panel for marks that were permanently rejected by the server.
export function FailedMarks({ items, onRetry, onDiscard }) {
  if (!items || !items.length) return null;
  return (
    <div className="alert alert-danger" role="alert" style={{ marginTop: 12 }}>
      <b>{items.length} saved mark(s) couldn’t sync</b> (the server rejected them):
      <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
        {items.map((f) => (
          <li key={f.id} style={{ fontSize: 13, margin: '4px 0' }}>
            {(f.payload && f.payload.date) || '—'} — {f.reason}
            <button type="button" className="btn btn-light btn-sm" style={{ marginLeft: 8 }} onClick={() => onRetry(f)}>Retry</button>
            <button type="button" className="btn btn-light btn-sm" style={{ marginLeft: 4 }} onClick={() => onDiscard(f)}>Discard</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
