// App kit — small shared pieces for the section apps built on the results
// kit (Library, Events, Reports). Styles live in static/css/app-kit.css (cm-*).
import React, { useState, useRef } from 'react';
import { useNav } from '../lib/section';
import { initials } from '../subjects/results';

export const plural = (n, w, p) => `${n} ${n === 1 ? w : (p || w + 's')}`;

// In-app link: soft navigation unless `native` (downloads, other apps).
export function A({ to, className, children, title, native, ...rest }) {
  const nav = useNav();
  if (native) return <a href={to} className={className} title={title} data-native {...rest}>{children}</a>;
  return <a href={to} title={title} className={className} onClick={(e) => { e.preventDefault(); nav.go(to); }} {...rest}>{children}</a>;
}

// Section nav. items: [key, icon, label, url, {x: true → pushed right}]
export function SecNav({ items, active, label }) {
  return (
    <nav className="sl-nav cm-nav" aria-label={label}>
      {items.filter((it) => it[3]).map(([k, ic, l, url, opt]) => (
        <A key={k} to={url} className={(opt && opt.x ? 'cm-nav-x' : '') + (active === k ? ' on' : '')} aria-current={active === k ? 'page' : undefined}>
          <i className={'fas ' + ic} aria-hidden="true" /><span>{l}</span></A>))}
    </nav>
  );
}

export const Field = ({ label, hint, children, grow }) => (
  <label className={'cm-f' + (grow ? ' grow' : '')}><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
);

export function Switch({ on, onChange, disabled, label }) {
  return (
    <button type="button" role="switch" aria-checked={!!on} aria-label={label} disabled={disabled}
            className={'cm-sw' + (on ? ' on' : '')} onClick={() => onChange(!on)}><i /></button>
  );
}

export function Toggle({ title, sub, on, onChange, disabled }) {
  return (
    <div className="cm-sched"><span><b>{title}</b>{sub && <small>{sub}</small>}</span>
      <Switch on={on} onChange={onChange} disabled={disabled} label={title} /></div>
  );
}

export const Pill = ({ tone, children, icon }) => (
  <span className={'cm-pill' + (tone ? ' ' + tone : '')}>{icon && <i className={'fas ' + icon} aria-hidden="true" />}{children}</span>
);

export function SearchBox({ value, onChange, placeholder, grow = true }) {
  return (
    <div className={'cm-search' + (grow ? ' grow' : '')}><i className="fas fa-magnifying-glass" aria-hidden="true" />
      <input type="search" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} aria-label={placeholder} /></div>
  );
}

// Type-ahead against an endpoint returning [{id, label|name}]. `picked`
// shows the chosen item as a removable chip in place of the input.
export function Lookup({ url, placeholder, onPick, picked, onClear, autoFocus, icon = 'fa-magnifying-glass' }) {
  const [text, setText] = useState('');
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [act, setAct] = useState(0);
  const tRef = useRef();
  const onInput = (v) => {
    setText(v); clearTimeout(tRef.current);
    if (v.trim().length < 2) { setList([]); setOpen(false); return; }
    tRef.current = setTimeout(async () => {
      try {
        const r = await fetch(url + '?q=' + encodeURIComponent(v.trim()), { credentials: 'same-origin' });
        const rows = await r.json();
        const ok = Array.isArray(rows) ? rows : [];
        setList(ok); setOpen(ok.length > 0); setAct(0);
      } catch (_) { /* ignore */ }
    }, 220);
  };
  const pick = (o) => { onPick({ id: o.id, label: o.label || o.name }); setText(''); setList([]); setOpen(false); };
  if (picked) {
    return (
      <div className="cm-picked"><span className="rs-av sm" aria-hidden="true">{initials(picked.label)}</span>
        <b>{picked.label}</b>
        {onClear && <button type="button" className="cm-ib" onClick={onClear} aria-label="Change"><i className="fas fa-xmark" aria-hidden="true" /></button>}</div>
    );
  }
  return (
    <div className="cm-search">
      <i className={'fas ' + icon} aria-hidden="true" />
      <input type="search" placeholder={placeholder} autoComplete="off" autoFocus={autoFocus} value={text} aria-label={placeholder}
             onChange={(e) => onInput(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)}
             onKeyDown={(e) => {
               if (!open || !list.length) return;
               if (e.key === 'ArrowDown') { e.preventDefault(); setAct((i) => (i + 1) % list.length); }
               else if (e.key === 'ArrowUp') { e.preventDefault(); setAct((i) => (i - 1 + list.length) % list.length); }
               else if (e.key === 'Enter') { e.preventDefault(); pick(list[act]); }
             }} />
      {open && <div className="cm-ac" role="listbox">{list.map((o, i) => (
        <button type="button" role="option" aria-selected={i === act} className={i === act ? 'on' : ''} key={o.id}
                onMouseDown={(e) => { e.preventDefault(); pick(o); }}>
          <span className="rs-av sm" aria-hidden="true">{initials(o.name || o.label)}</span><span>{o.label || o.name}</span></button>))}</div>}
    </div>
  );
}
