import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

// Shared building blocks for the attendance screens, so every screen picks a
// class, steps a date/week, shows numbers and lists people the same way — on a
// laptop as a workspace, on a phone as a native-feeling app.

export function useMedia(query) {
  const get = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false);
  const [m, setM] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const on = () => setM(mq.matches);
    on();
    if (mq.addEventListener) mq.addEventListener('change', on); else mq.addListener(on);
    return () => { if (mq.removeEventListener) mq.removeEventListener('change', on); else mq.removeListener(on); };
  }, [query]);
  return m;
}
export const usePhone = () => useMedia('(max-width: 759px)');

// Local YYYY-MM-DD (no UTC shift).
export const ymd = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
// Step a date by ±1 school day (skips Saturday and Sunday).
export function stepDay(iso, dir) {
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d)) return iso;
  do { d.setDate(d.getDate() + dir); } while (d.getDay() === 0 || d.getDay() === 6);
  return ymd(d);
}
export const prettyDate = (iso, long) => {
  const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
  if (isNaN(d)) return iso;
  return d.toLocaleDateString(undefined, long
    ? { weekday: 'long', day: 'numeric', month: 'long' }
    : { weekday: 'short', day: 'numeric', month: 'short' });
};
export const initialsOf = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';
// Attendance percentages: whole numbers as-is ("96%"), otherwise 2 dp ("96.43%").
export const fmtNum = (v) => {
  if (v == null || v === '' || Number.isNaN(Number(v))) return '—';
  const r = Math.round(Number(v) * 100) / 100;
  return Number.isInteger(r) ? String(r) : r.toFixed(2);
};
export const fmtPct = (v) => (v == null || v === '' || Number.isNaN(Number(v)) ? '—' : fmtNum(v) + '%');
export const pctTone = (p) => (p == null ? '' : p >= 75 ? 'good' : p >= 50 ? 'warn' : 'bad');
export const pctColor = (p) => (p >= 75 ? 'var(--success)' : p >= 50 ? 'var(--warning)' : 'var(--danger)');

// The class / date / week picker card at the top of a screen.
export function Picker({ children }) {
  return <section className="md-pick">{children}</section>;
}

// Classes as tap chips (wrap on laptops, swipe on phones; a dropdown is added
// on laptops once there are many classes).
export function ClassChips({ classes, value, onChange, label = 'Class' }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current && ref.current.querySelector('.on');
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [value]);
  return (
    <>
      <div className="md-pick-row">
        <span className="md-pick-l">{label}</span>
        {classes.length > 8 && (
          <select className="md-select" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
            <option value="">Choose a class</option>
            {classes.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
          </select>
        )}
      </div>
      {classes.length === 0 ? <p className="md-none">No classes available for this term.</p> : (
        <div className="md-classes" ref={ref} role="radiogroup" aria-label={label}>
          {classes.map((c) => (
            <button key={c.id} type="button" role="radio" aria-checked={String(c.id) === String(value)}
                    className={String(c.id) === String(value) ? 'on' : ''} onClick={() => onChange(String(c.id))}>
              {c.name}</button>
          ))}
        </div>
      )}
    </>
  );
}

export function DateStepper({ date, setDate, today }) {
  return (
    <div className="md-date">
      <button type="button" className="md-step" onClick={() => setDate(stepDay(date, -1))} aria-label="Previous school day"><i className="fas fa-chevron-left" aria-hidden="true" /></button>
      <label className="md-date-box">
        <i className="fas fa-calendar-day" aria-hidden="true" />
        <span>{prettyDate(date)}</span>
        <input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} aria-label="Date" />
      </label>
      <button type="button" className="md-step" onClick={() => setDate(stepDay(date, 1))} aria-label="Next school day"><i className="fas fa-chevron-right" aria-hidden="true" /></button>
      {today && date !== today && <button type="button" className="md-today" onClick={() => setDate(today)}>Today</button>}
    </div>
  );
}

// ‹ Week 4 › with the week's dates; a native select sits under the label so
// any week can be jumped to.
export function WeekStepper({ weeks, value, onChange, current }) {
  const i = weeks.findIndex((w) => String(w.id) === String(value));
  const w = weeks[i];
  const fmt = (s) => (s ? new Date(String(s).slice(0, 10) + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '');
  if (!weeks.length) return <p className="md-none">No weeks set up for this term.</p>;
  return (
    <div className="md-date">
      <button type="button" className="md-step" disabled={i <= 0} onClick={() => onChange(String(weeks[i - 1].id))} aria-label="Previous week"><i className="fas fa-chevron-left" aria-hidden="true" /></button>
      <label className="md-date-box">
        <i className="fas fa-calendar-week" aria-hidden="true" />
        <span>{w ? `Week ${w.number}` : 'Choose a week'}{w && (w.start_date || w.start) ? <small className="ak-dim"> · {fmt(w.start_date || w.start)}{(w.end_date || w.end) ? ' – ' + fmt(w.end_date || w.end) : ''}</small> : null}</span>
        <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Week">
          {weeks.map((x) => <option key={x.id} value={String(x.id)}>Week {x.number}</option>)}
        </select>
      </label>
      <button type="button" className="md-step" disabled={i < 0 || i >= weeks.length - 1} onClick={() => onChange(String(weeks[i + 1].id))} aria-label="Next week"><i className="fas fa-chevron-right" aria-hidden="true" /></button>
      {current && String(current) !== String(value) && <button type="button" className="md-today" onClick={() => onChange(String(current))}>This week</button>}
    </div>
  );
}

// Segmented control: [{value, label, icon}]
export function Seg({ options, value, onChange, label }) {
  return (
    <div className="ak-seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value}
                className={o.value === value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.icon && <i className={'fas ' + o.icon} aria-hidden="true" />}{o.label}
          {o.count != null && <span className="ak-seg-n">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

// KPI tiles: [{label, value, sub, tone, onClick}]
export function Tiles({ items }) {
  return (
    <div className="ak-tiles">
      {items.filter(Boolean).map((t, i) => {
        const Tag = t.onClick ? 'button' : 'div';
        return (
          <Tag key={i} type={t.onClick ? 'button' : undefined} onClick={t.onClick}
               className={'ak-tile' + (t.tone ? ' ' + t.tone : '') + (t.onClick ? ' click' : '')}>
            <span className="l">{t.label}</span>
            <span className="v">{t.value}{t.unit && <small>{t.unit}</small>}</span>
            {t.sub && <span className="s">{t.sub}</span>}
          </Tag>
        );
      })}
    </div>
  );
}

export function Card({ icon, title, sub, action, children, className = '', flush }) {
  return (
    <section className={'ak-card ' + className}>
      {(title || action) && (
        <header className="ak-card-h">
          {icon && <span className="ak-card-ic"><i className={'fas ' + icon} aria-hidden="true" /></span>}
          <div className="ak-card-t"><h3>{title}</h3>{sub && <small>{sub}</small>}</div>
          {action && <div className="ak-card-a">{action}</div>}
        </header>
      )}
      <div className={'ak-card-b' + (flush ? ' flush' : '')}>{children}</div>
    </section>
  );
}

export function Ring({ pct, label = 'Rate', size = 96 }) {
  const raw = Math.max(0, Math.min(100, Number(pct) || 0));
  const p = Math.round(raw);
  return (
    <div className="ak-ring" style={{ '--p': p, '--c': pctColor(p), width: size, height: size }} role="img" aria-label={`${label} ${fmtPct(raw)}`}>
      <div><b>{fmtPct(raw)}</b><small>{label}</small></div>
    </div>
  );
}

// A thin labelled progress bar.
export function Meter({ label, value, max, pct, tone }) {
  const p = pct != null ? pct : (max ? (value / max) * 100 : 0);
  return (
    <div className="ak-meter">
      <span className="ak-meter-l">{label}</span>
      <div className="ak-track"><i style={{ width: Math.max(0, Math.min(100, p)) + '%', background: tone || pctColor(p) }} /></div>
      <b>{max != null ? `${value}/${max}` : fmtPct(p)}</b>
    </div>
  );
}

// One person row: avatar, name + sub line, anything on the right.
export function Person({ name, sub, gender, href, right, tone, onClick }) {
  const body = (
    <>
      <span className="att-av" data-g={gender || ''} aria-hidden="true">{initialsOf(name)}</span>
      <span className="ak-pname">{name}{sub && <small>{sub}</small>}</span>
    </>
  );
  return (
    <li className={'ak-person' + (tone ? ' ' + tone : '')}>
      {href ? <a className="ak-pmain" href={href}>{body}</a>
        : onClick ? <button type="button" className="ak-pmain" onClick={onClick}>{body}</button>
        : <span className="ak-pmain">{body}</span>}
      {right && <span className="ak-pright">{right}</span>}
    </li>
  );
}

export function GroupHead({ label, count }) {
  return <li className="md-ghead">{label}{count != null && <span>{count}</span>}</li>;
}

// Upward "more actions" menu (used in the sticky bar).
export function MoreMenu({ items, up = true, label = 'More actions' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close); document.addEventListener('touchstart', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('touchstart', close); };
  }, [open]);
  return (
    <div className="md-more" ref={ref}>
      <button type="button" className="md-btn ghost" aria-haspopup="true" aria-expanded={open} aria-label={label} title={label} onClick={() => setOpen((v) => !v)}>
        <i className="fas fa-ellipsis" aria-hidden="true" /></button>
      {open && (
        <div className={'md-more-pop' + (up ? '' : ' down')} role="menu">
          {items.filter(Boolean).map((it, i) => (it.href
            ? <a key={i} role="menuitem" href={it.href} target={it.target} rel={it.target ? 'noopener' : undefined} onClick={() => setOpen(false)}>
                <i className={'fas ' + it.icon} aria-hidden="true" /> {it.label}</a>
            : <button key={i} type="button" role="menuitem" disabled={it.disabled} title={it.title}
                      onClick={() => { setOpen(false); it.onClick(); }}>
                <i className={'fas ' + it.icon} aria-hidden="true" /> {it.label}</button>))}
        </div>
      )}
    </div>
  );
}

// The save/action bar: sticky at the bottom of its card on laptops, fixed
// over the bottom nav on phones (portalled so it sits above it).
export function ActionBar({ children, phone }) {
  const bar = <div className={'md-bar' + (phone ? ' fixed' : '')}>{children}</div>;
  return phone ? createPortal(bar, document.body) : bar;
}

// Bottom sheet on phones, centred dialog on laptops.
export function Sheet({ title, onClose, children }) {
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', esc);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', esc); document.body.style.overflow = prev; };
  }, []);
  return createPortal(
    <div className="ak-sheet-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ak-sheet" role="dialog" aria-modal="true" aria-label={title}>
        <div className="ak-grip" aria-hidden="true" />
        <div className="ak-sheet-h"><strong>{title}</strong>
          <button type="button" className="ak-x" onClick={onClose} aria-label="Close"><i className="fas fa-xmark" aria-hidden="true" /></button></div>
        {children}
      </div>
    </div>, document.body);
}

// Present/absent dot for read-only reports (null = not marked).
// Classes left out of an analysis because their register has never been taken
// this term ("no data", not 0%). `classes` = list of names or {class, students}.
export function UnmarkedNote({ classes, what = 'these figures' }) {
  if (!classes || !classes.length) return null;
  const names = classes.map((c) => (typeof c === 'string' ? c : c.class));
  const n = names.length;
  return (
    <div className="ak-unmarked" role="note">
      <i className="fas fa-circle-info" aria-hidden="true" />
      <div>
        <b>{n} class{n === 1 ? '' : 'es'} not included in {what}</b>
        <span>No attendance has been marked for {n === 1 ? 'it' : 'them'} this term yet: {names.join(', ')}.</span>
      </div>
      <a className="ak-btn" href="#/mark"><i className="fas fa-user-check" aria-hidden="true" /><span> Mark now</span></a>
    </div>
  );
}

export function Dot({ v, label }) {
  const cls = v == null ? 'na' : v ? 'in' : 'out';
  return <span className={'ak-dot ' + cls} title={label} aria-label={label + ': ' + (v == null ? 'not marked' : v ? 'present' : 'absent')}>
    <i className={'fas ' + (v == null ? 'fa-minus' : v ? 'fa-check' : 'fa-xmark')} aria-hidden="true" /></span>;
}

// Initial class for a screen: deep link → form teacher's class → last used.
export function pickInitialClass(classes, default_class, initial, lastClass) {
  const ids = new Set((classes || []).map((c) => String(c.id)));
  if (initial && initial.assignmentId && ids.has(String(initial.assignmentId))) return String(initial.assignmentId);
  if (default_class && ids.has(String(default_class))) return String(default_class);
  const l = lastClass ? lastClass() : '';
  return l && ids.has(String(l)) ? String(l) : '';
}
