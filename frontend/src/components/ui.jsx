/* Reusable, accessible UI primitives for the attendance SPA.
   Styling leans on the app's existing .btn/.form-control classes plus a few
   scoped .att-* classes defined in the host template, so it matches the theme. */
import React, { useState, useRef, useEffect, useId, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { useNav } from '../lib/section';

// Elements that can hold keyboard focus — used by the modal focus trap.
const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),' +
  'select:not([disabled]),[tabindex]:not([tabindex="-1"])';

// Catches render/runtime errors in a section so a crash shows a friendly panel
// (with a reload + go-home option) instead of a blank screen, and reports the
// error so it appears in the admin Error Log.
export class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) {
    try {
      if (window.reportClientError) {
        window.reportClientError((error && error.message) || 'React error',
          window.location.href, (error && error.stack) || (info && info.componentStack));
      }
    } catch (e) { /* never throw from the boundary */ }
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card" style={{ margin: '1rem 0' }}>
        <div className="card-body" style={{ textAlign: 'center', padding: '2rem 1rem' }}>
          <i aria-hidden="true" className="fas fa-triangle-exclamation" style={{ fontSize: 32, color: '#dc2626' }} />
          <h3 style={{ marginTop: 12 }}>This section hit an error</h3>
          <p className="text-muted">It’s been logged. Your other work is safe — try reloading this page.</p>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={() => window.location.reload()}>
              <i aria-hidden="true" className="fas fa-rotate" /> Reload
            </button>
            <a className="btn btn-secondary" href="/">Go to Dashboard</a>
          </div>
        </div>
      </div>
    );
  }
}

// Wrap a section's content: intercepts clicks on internal <a href="/…"> links and
// navigates with no reload (go() falls back to a real navigation for downloads /
// cross-section / non-JSON targets). External, target=_blank, download and
// data-native links are left alone, as are links that already handled the click.
export function SectionShell({ go, children }) {
  const ref = useRef();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onClick = (e) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
      const a = e.target.closest('a');
      if (!a || a.target === '_blank' || a.hasAttribute('download') || a.dataset.native) return;
      const href = a.getAttribute('href');
      if (!href || !href.startsWith('/')) return;   // external / tel: / mailto: / #
      e.preventDefault();
      go(href);
    };
    el.addEventListener('click', onClick);
    return () => el.removeEventListener('click', onClick);
  }, [go]);
  return <div ref={ref}><ErrorBoundary>{children}</ErrorBoundary></div>;
}

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
  const [active, setActive] = useState(-1);   // keyboard-highlighted option index
  const tRef = useRef();
  const listId = useId();
  const labelId = useId();

  const onInput = (v) => {
    setText(v); setPicked(false); onPick(''); setActive(-1);
    clearTimeout(tRef.current);
    if (v.trim().length < minChars) { setList([]); setOpen(false); return; }
    tRef.current = setTimeout(async () => {
      try {
        const r = await fetch(url + '?q=' + encodeURIComponent(v.trim()), { credentials: 'same-origin' });
        const rows = await r.json();
        setList(rows); setOpen(rows.length > 0); setActive(rows.length ? 0 : -1);
      } catch (_) { /* ignore */ }
    }, 220);
  };
  const pick = (o) => { setText(o.label); setPicked(true); onPick(o.id); setOpen(false); setActive(-1); };

  const onKeyDown = (e) => {
    if (!open || !list.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % list.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i - 1 + list.length) % list.length); }
    else if (e.key === 'Enter') { if (active >= 0) { e.preventDefault(); pick(list[active]); } }
    else if (e.key === 'Escape') { setOpen(false); setActive(-1); }
  };

  return (
    <div className="form-group ac-wrap">
      <label className="form-label" id={labelId}>{label}{required && <span className="required" aria-hidden="true"> *</span>}</label>
      <input type="text" className={'form-control' + (picked ? ' picked' : '')} value={text} placeholder={placeholder}
             autoComplete="off" role="combobox" aria-expanded={open} aria-controls={listId}
             aria-autocomplete="list" aria-labelledby={labelId} aria-required={required || undefined}
             aria-activedescendant={open && active >= 0 ? listId + '-' + active : undefined}
             onChange={(e) => onInput(e.target.value)} onKeyDown={onKeyDown}
             onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && (
        <div className="ac-list" role="listbox" id={listId} aria-labelledby={labelId}>
          {list.map((o, i) => (
            <div key={o.id} id={listId + '-' + i} role="option" aria-selected={i === active}
                 className={i === active ? 'active' : undefined}
                 onMouseDown={() => pick(o)} onMouseEnter={() => setActive(i)}>
              {o.label}
            </div>
          ))}
        </div>
      )}
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

// Floating, auto-dismissing confirmation pinned to the bottom of the viewport —
// so feedback for an action (e.g. Save) is visible right where the button is,
// no scrolling up to find it. Auto-closes after a few seconds.
export function Toast({ tone = 'success', children, onClose, duration = 4000 }) {
  useEffect(() => {
    if (!onClose) return undefined;
    const t = setTimeout(onClose, duration);
    return () => clearTimeout(t);
  }, [onClose, duration]);
  const tones = {
    info: ['#1e40af', '#eff6ff'], success: ['#166534', '#f0fdf4'],
    warn: ['#92400e', '#fffbeb'], error: ['#991b1b', '#fef2f2'],
  };
  const [fg, bg] = tones[tone] || tones.success;
  const icon = { success: 'fa-circle-check', warn: 'fa-triangle-exclamation', error: 'fa-circle-xmark', info: 'fa-circle-info' }[tone] || 'fa-circle-check';
  return (
    <div role="status" aria-live="polite" style={{
      position: 'fixed', left: '50%', bottom: 'max(20px, env(safe-area-inset-bottom))',
      transform: 'translateX(-50%)', zIndex: 3000, background: bg, color: fg,
      border: '1px solid ' + fg + '33', borderRadius: 10, padding: '.7rem 1rem',
      boxShadow: '0 8px 28px rgba(0,0,0,.18)', display: 'flex', gap: 10, alignItems: 'center',
      fontSize: 14, fontWeight: 600, maxWidth: '92vw' }}>
      <i className={'fas ' + icon} aria-hidden="true" />
      <span>{children}</span>
      {onClose && <button type="button" aria-label="Dismiss" onClick={onClose}
        style={{ background: 'none', border: 'none', color: fg, cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>×</button>}
    </div>
  );
}

// Accessible modal dialog. Renders into a portal at <body> so it's never
// clipped by an ancestor's overflow/transform. Handles the things every modal
// needs and which the hand-rolled ones kept getting wrong:
//   • focus is moved into the dialog on open and restored to the trigger on close
//   • Tab/Shift+Tab are trapped inside the dialog
//   • Escape closes; background scroll is locked while open
//   • clicking the backdrop closes (a drag that starts inside the panel does not)
// Props: title, icon, onClose, footer, size ('sm'|'md'|'lg'|'xl'), labelledBy,
// closeOnBackdrop (default true), initialFocusRef (element to focus first).
export function Modal({ title, icon, onClose, children, footer, size = 'md',
                       closeOnBackdrop = true, initialFocusRef, ariaLabel }) {
  const panelRef = useRef(null);
  const titleId = useId();
  // Keep the latest onClose without re-running the mount effect (callers usually
  // pass an inline arrow, which would otherwise steal focus on every render).
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const prevFocus = document.activeElement;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    // Move focus into the dialog (caller's choice, else first focusable, else panel).
    const panel = panelRef.current;
    const first = (initialFocusRef && initialFocusRef.current) ||
      (panel && panel.querySelector(FOCUSABLE)) || panel;
    if (first && first.focus) first.focus();

    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeRef.current && closeRef.current(); return; }
      if (e.key !== 'Tab' || !panelRef.current) return;
      const f = Array.from(panelRef.current.querySelectorAll(FOCUSABLE))
        .filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (!f.length) { e.preventDefault(); return; }
      const lo = f[0], hi = f[f.length - 1];
      if (e.shiftKey && document.activeElement === lo) { e.preventDefault(); hi.focus(); }
      else if (!e.shiftKey && document.activeElement === hi) { e.preventDefault(); lo.focus(); }
    };
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.body.style.overflow = prevOverflow;
      if (prevFocus && prevFocus.focus) prevFocus.focus();   // restore to trigger
    };
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps -- mount/unmount only

  const maxWidth = { sm: 420, md: 560, lg: 760, xl: 960 }[size] || 560;
  // mousedown target check: a click that *starts* on the backdrop closes; a drag
  // that starts inside the panel and releases on the backdrop does not.
  const onBackdrop = (e) => { if (closeOnBackdrop && e.target === e.currentTarget) closeRef.current && closeRef.current(); };

  return createPortal(
    <div role="presentation" onMouseDown={onBackdrop}
         style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 3000,
                  display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
                  padding: '5vh 1rem', overflowY: 'auto' }}>
      <div ref={panelRef} role="dialog" aria-modal="true" tabIndex={-1}
           aria-labelledby={title ? titleId : undefined}
           aria-label={!title ? ariaLabel : undefined}
           style={{ background: 'var(--bg-card, #fff)', color: 'inherit', borderRadius: 12,
                    width: '100%', maxWidth, boxShadow: '0 20px 60px rgba(0,0,0,.3)',
                    overflow: 'hidden', display: 'flex', flexDirection: 'column', maxHeight: '90vh' }}>
        {title && (
          <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                           gap: 12, padding: '1rem 1.25rem', borderBottom: '1px solid var(--border-color, #e5e7eb)' }}>
            <h3 id={titleId} style={{ margin: 0, fontSize: '1.05rem' }}>
              {icon && <i className={'fas ' + icon} aria-hidden="true" />} {title}
            </h3>
            <button type="button" aria-label="Close" onClick={() => closeRef.current && closeRef.current()}
                    style={{ background: 'none', border: 'none', fontSize: 22, lineHeight: 1,
                             cursor: 'pointer', color: 'inherit', opacity: .6 }}>×</button>
          </header>
        )}
        <div style={{ padding: '1.1rem 1.25rem', overflowY: 'auto' }}>{children}</div>
        {footer && (
          <footer style={{ display: 'flex', gap: '.6rem', justifyContent: 'flex-end',
                           padding: '.85rem 1.25rem', borderTop: '1px solid var(--border-color, #e5e7eb)' }}>
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body
  );
}

// Themed, accessible confirmation dialog used imperatively via confirm() below.
function ConfirmDialog({ title = 'Please confirm', message, confirmText = 'Confirm',
                        cancelText = 'Cancel', tone = 'primary', icon, onResolve }) {
  const okRef = useRef(null);
  return (
    <Modal title={title} icon={icon} size="sm" onClose={() => onResolve(false)} initialFocusRef={okRef}
           footer={<>
             <Button variant="light" onClick={() => onResolve(false)}>{cancelText}</Button>
             <Button ref={okRef} variant={tone === 'danger' ? 'danger' : 'primary'}
                     onClick={() => onResolve(true)}>{confirmText}</Button>
           </>}>
      <p style={{ margin: 0, lineHeight: 1.5 }}>{message}</p>
    </Modal>
  );
}

// Promise-based replacement for window.confirm(): themed, accessible, non-blocking.
// Usage:  if (await confirm('Delete this student?')) doDelete();
//   or:   if (await confirm({ title, message, confirmText: 'Delete', tone: 'danger' })) …
// Resolves true on confirm, false on cancel / Escape / backdrop.
export function confirm(opts) {
  const o = typeof opts === 'string' ? { message: opts } : (opts || {});
  return new Promise((resolve) => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    const done = (val) => { root.unmount(); host.remove(); resolve(val); };
    root.render(<ConfirmDialog {...o} onResolve={done} />);
  });
}

// Status badge mapped onto the app's existing .badge-* theme classes, so a tone
// name ('success'/'danger'/…) is the single way to label state across modules.
export function Badge({ tone = 'secondary', icon, children, title }) {
  const cls = { success: 'success', danger: 'danger', error: 'danger', warn: 'warning',
                warning: 'warning', info: 'info', primary: 'primary', secondary: 'secondary',
                gray: 'secondary' }[tone] || 'secondary';
  return (
    <span className={'badge badge-' + cls} title={title}>
      {icon && <i className={'fas ' + icon} aria-hidden="true" />}{icon && children ? ' ' : ''}{children}
    </span>
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

// Horizontal-scroll container for wide tables on narrow screens. Unlike a plain
// overflow:auto <div>, this is a labelled, keyboard-focusable region: keyboard
// users can Tab to it and scroll with the arrow keys, and screen readers
// announce it (WAI-ARIA "scrollable region" pattern). Pass `maxHeight` to also
// cap vertical height with a sticky-friendly scroll area.
export function TableWrap({ label = 'Table', children, maxHeight }) {
  return (
    <div className="table-responsive" role="region" aria-label={label} tabIndex={0}
         style={maxHeight ? { maxHeight, overflow: 'auto' } : undefined}>
      {children}
    </div>
  );
}

export const Button = React.forwardRef(function Button({ variant = 'primary', size, children, ...rest }, ref) {
  const cls = ['btn', 'btn-' + variant, size === 'sm' ? 'btn-sm' : ''].filter(Boolean).join(' ');
  return <button ref={ref} type="button" className={cls} {...rest}>{children}</button>;
});

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
