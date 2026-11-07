/* Reusable, accessible form-field primitives. They render the app's existing
   .form-group/.form-label/.form-control markup (so they match the theme) and
   wire up label association, required state, hints and inline errors with the
   right aria attributes. Reused by the student add/edit form and available to
   any future React form. */
import React, { useId } from 'react';

function useIds(error, hint) {
  const base = useId();
  return {
    id: base,
    errId: error ? base + '-err' : undefined,
    hintId: hint ? base + '-hint' : undefined,
  };
}

function describedBy(hintId, errId) {
  return [hintId, errId].filter(Boolean).join(' ') || undefined;
}

function Label({ id, label, required }) {
  if (!label) return null;
  return (
    <label className="form-label" htmlFor={id}>
      {label}{required && <span className="required" aria-hidden="true" style={{ color: 'var(--danger, var(--danger))' }}> *</span>}
    </label>
  );
}

function Hint({ hintId, hint, errId, error }) {
  return (
    <>
      {hint && <span className="form-hint" id={hintId}
                     style={{ display: 'block', fontSize: 'var(--text-xs)', color: 'var(--text-muted, var(--text-muted))', marginTop: 3 }}>{hint}</span>}
      {error && (
        <span className="form-error" id={errId} role="alert"
              style={{ color: 'var(--danger, var(--danger))', fontSize: 'var(--text-xs)', display: 'block', marginTop: 3 }}>
          {error}
        </span>
      )}
    </>
  );
}

export function TextField({ label, value, onChange, required, hint, error, type = 'text', ...rest }) {
  const { id, errId, hintId } = useIds(error, hint);
  return (
    <div className="form-group">
      <Label id={id} label={label} required={required} />
      <input id={id} type={type} className="form-control" value={value}
             onChange={(e) => onChange(e.target.value)} required={required}
             aria-required={required || undefined} aria-invalid={error ? true : undefined}
             aria-describedby={describedBy(hintId, errId)} {...rest} />
      <Hint hintId={hintId} hint={hint} errId={errId} error={error} />
    </div>
  );
}

export function TextAreaField({ label, value, onChange, required, hint, error, rows = 3, ...rest }) {
  const { id, errId, hintId } = useIds(error, hint);
  return (
    <div className="form-group">
      <Label id={id} label={label} required={required} />
      <textarea id={id} className="form-control" rows={rows} value={value}
                onChange={(e) => onChange(e.target.value)} required={required}
                aria-required={required || undefined} aria-invalid={error ? true : undefined}
                aria-describedby={describedBy(hintId, errId)} {...rest} />
      <Hint hintId={hintId} hint={hint} errId={errId} error={error} />
    </div>
  );
}

export function SelectField({ label, value, onChange, options, placeholder, required, hint, error, ...rest }) {
  const { id, errId, hintId } = useIds(error, hint);
  return (
    <div className="form-group">
      <Label id={id} label={label} required={required} />
      <select id={id} className="form-control" value={value == null ? '' : value}
              onChange={(e) => onChange(e.target.value)} required={required}
              aria-required={required || undefined} aria-invalid={error ? true : undefined}
              aria-describedby={describedBy(hintId, errId)} {...rest}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => {
          const val = typeof o === 'string' ? o : o.value;
          const lbl = typeof o === 'string' ? o : o.label;
          return <option key={val} value={val}>{lbl}</option>;
        })}
      </select>
      <Hint hintId={hintId} hint={hint} errId={errId} error={error} />
    </div>
  );
}

// A card with an icon header — matches the Jinja .card/.card-header pattern.
// `collapsible` makes the header toggle the body (default state via `defaultOpen`),
// so optional sections can be tucked away to keep a form's core fields up front.
export function FormCard({ icon, title, note, children, collapsible, defaultOpen = true }) {
  const [open, setOpen] = React.useState(collapsible ? defaultOpen : true);
  const head = (
    <h3 style={{ display: 'flex', alignItems: 'center', gap: '.5rem', width: '100%' }}>
      {icon && <i className={'fas ' + icon} aria-hidden="true" />} {title}
      {note && <span className="text-muted" style={{ fontWeight: 400, fontSize: 'var(--text-sm)' }}> {note}</span>}
      {collapsible && <i className={'fas fa-chevron-down'} aria-hidden="true"
        style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', opacity: 0.6, transition: 'transform .15s',
                 transform: open ? 'none' : 'rotate(-90deg)' }} />}
    </h3>
  );
  return (
    <div className="card mb-3">
      {collapsible ? (
        <button type="button" className="card-header" aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          style={{ width: '100%', border: 'none', background: 'var(--gray-50)', cursor: 'pointer', textAlign: 'left' }}>
          {head}
        </button>
      ) : (
        <div className="card-header">{head}</div>
      )}
      {open && <div className="card-body">{children}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------------- *
 * Date of birth: Day / Month / Year pickers (native lists — one flick on a
 * phone, type-ahead on a keyboard) plus a "type or paste" box that reads
 * 12/03/2012, 12-3-2012, 12.03.12, 12 March 2012, March 12 2012, 2012-03-12
 * or 12032012. Shows the age so a wrong year is obvious. Value stays ISO
 * (YYYY-MM-DD); '' when cleared or incomplete.
 * ------------------------------------------------------------------------- */
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                'September', 'October', 'November', 'December'];

function daysIn(y, m) {
  if (!m) return 31;
  return new Date(y || 2000, m, 0).getDate();    // 2000 is a leap year → Feb 29 allowed until a year is picked
}

function splitIso(v) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || '');
  return m ? { y: +m[1], m: +m[2], d: +m[3] } : { y: '', m: '', d: '' };
}

const pad = (n) => String(n).padStart(2, '0');

export function parseLooseDate(text, today = new Date()) {
  const t = (text || '').trim().toLowerCase().replace(/(\d)(st|nd|rd|th)\b/g, '$1').replace(/,/g, ' ');
  if (!t) return null;
  const monthIdx = (w) => {
    const i = MONTHS.findIndex((mn) => mn.toLowerCase().startsWith(w.slice(0, 3)));
    return i >= 0 && w.length >= 3 ? i + 1 : 0;
  };
  const fixYear = (y) => {
    if (y >= 100) return y;
    const cur = today.getFullYear() % 100;
    return y <= cur ? 2000 + y : 1900 + y;          // "12" → 2012, "98" → 1998
  };
  let y, m, d, mm;
  if ((mm = /^(\d{4})[-/.\s](\d{1,2})[-/.\s](\d{1,2})$/.exec(t))) { [y, m, d] = [+mm[1], +mm[2], +mm[3]]; }
  else if ((mm = /^(\d{1,2})[-/.\s](\d{1,2})[-/.\s](\d{2}|\d{4})$/.exec(t))) { [d, m, y] = [+mm[1], +mm[2], fixYear(+mm[3])]; }   // day first (Nigeria)
  else if ((mm = /^(\d{2})(\d{2})(\d{4})$/.exec(t))) { [d, m, y] = [+mm[1], +mm[2], +mm[3]]; }
  else if ((mm = /^(\d{1,2})\s*([a-z]+)\.?\s*(\d{2}|\d{4})$/.exec(t))) { [d, m, y] = [+mm[1], monthIdx(mm[2]), fixYear(+mm[3])]; }
  else if ((mm = /^([a-z]+)\.?\s*(\d{1,2})\s+(\d{2}|\d{4})$/.exec(t))) { [m, d, y] = [monthIdx(mm[1]), +mm[2], fixYear(+mm[3])]; }
  else return null;
  if (!m || m > 12 || !d || d > daysIn(y, m) || y < 1900 || y > today.getFullYear()) return null;
  return `${y}-${pad(m)}-${pad(d)}`;
}

function ageText(iso, today = new Date()) {
  const p = splitIso(iso);
  if (!p.y) return '';
  let years = today.getFullYear() - p.y;
  let months = today.getMonth() + 1 - p.m;
  if (today.getDate() < p.d) months -= 1;
  if (months < 0) { years -= 1; months += 12; }
  if (years < 0) return 'That date is in the future';
  return `${years} year${years === 1 ? '' : 's'}${months ? `, ${months} month${months === 1 ? '' : 's'}` : ''} old`;
}

export function DateOfBirthField({ label = 'Date of Birth', value, onChange, required, hint, error,
                                   minAge = 1, maxAge = 40 }) {
  const { id, errId, hintId } = useIds(error, hint);
  const today = new Date();
  const init = splitIso(value);
  const [d, setD] = React.useState(init.d);
  const [m, setM] = React.useState(init.m);
  const [y, setY] = React.useState(init.y);
  const [typed, setTyped] = React.useState('');
  const [typedErr, setTypedErr] = React.useState('');
  const [note, setNote] = React.useState('');

  // Follow outside changes (draft restore, server data).
  React.useEffect(() => {
    const p = splitIso(value);
    if (value && (p.y !== y || p.m !== m || p.d !== d)) { setD(p.d); setM(p.m); setY(p.y); }
    if (!value && d && m && y) { setD(''); setM(''); setY(''); }
  }, [value]);   // eslint-disable-line react-hooks/exhaustive-deps

  const emit = (nd, nm, ny) => {
    if (nd && nm && ny) {
      const maxD = daysIn(ny, nm);
      const dd = Math.min(nd, maxD);
      if (dd !== nd) {
        setD(dd);
        setNote(`${nd} ${MONTHS[nm - 1]} ${ny} doesn’t exist, so the day was changed to ${dd}.`);
      } else {
        setNote('');
      }
      onChange(`${ny}-${pad(nm)}-${pad(dd)}`);
    } else if (value) {
      onChange('');
    }
  };
  const pickD = (v) => { const n = v ? +v : ''; setD(n); emit(n, m, y); };
  const pickM = (v) => { const n = v ? +v : ''; setM(n); emit(d, n, y); };
  const pickY = (v) => { const n = v ? +v : ''; setY(n); emit(d, m, n); };

  const applyTyped = () => {
    if (!typed.trim()) { setTypedErr(''); return; }
    const iso = parseLooseDate(typed, today);
    if (!iso) { setTypedErr('Couldn’t read that date — try 12/03/2012 or 12 March 2012.'); return; }
    const p = splitIso(iso);
    setD(p.d); setM(p.m); setY(p.y); setTyped(''); setTypedErr(''); setNote('');
    onChange(iso);
  };

  const thisYear = today.getFullYear();
  const years = [];
  for (let yy = thisYear - minAge; yy >= thisYear - maxAge; yy -= 1) years.push(yy);
  if (y && !years.includes(y)) years.push(y);
  years.sort((a, b) => b - a);
  const nDays = daysIn(y, m);
  const age = value ? ageText(value, today) : '';
  const p = splitIso(value);
  const odd = p.y && (thisYear - p.y < 2 || thisYear - p.y > 30);

  return (
    <div className="form-group dob-field">
      <Label id={id + '-d'} label={label} required={required} />
      <div className="dob-pickers" role="group" aria-label={label} aria-describedby={describedBy(hintId, errId)}>
        <select id={id + '-d'} className="form-control" value={d} onChange={(e) => pickD(e.target.value)}
                aria-label="Day" aria-invalid={error ? true : undefined}>
          <option value="">Day</option>
          {Array.from({ length: nDays }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <select className="form-control" value={m} onChange={(e) => pickM(e.target.value)} aria-label="Month">
          <option value="">Month</option>
          {MONTHS.map((mn, i) => <option key={mn} value={i + 1}>{mn}</option>)}
        </select>
        <select className="form-control" value={y} onChange={(e) => pickY(e.target.value)} aria-label="Year">
          <option value="">Year</option>
          {years.map((yy) => <option key={yy} value={yy}>{yy}</option>)}
        </select>
      </div>
      <div className="dob-typed">
        <input type="text" className="form-control" inputMode="text" autoComplete="off" value={typed}
               placeholder="…or type it: 12/03/2012" aria-label={`${label} (type it)`}
               onChange={(e) => { setTyped(e.target.value); setTypedErr(''); }}
               onBlur={applyTyped}
               onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applyTyped(); } }} />
        {(value || d || m || y) && (
          <button type="button" className="dob-clear" onClick={() => { setD(''); setM(''); setY(''); setTyped(''); setNote(''); setTypedErr(''); onChange(''); }}
                  aria-label="Clear date of birth">Clear</button>
        )}
      </div>
      <div className="dob-status" aria-live="polite">
        {value ? (
          <span className={odd ? 'dob-warn' : 'dob-ok'}>
            <i aria-hidden="true" className={'fas ' + (odd ? 'fa-triangle-exclamation' : 'fa-cake-candles')} />{' '}
            {new Date(p.y, p.m - 1, p.d).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
            {' · '}{age}{odd ? ' — check the year' : ''}
          </span>
        ) : (d || m || y) ? <span className="dob-muted">Pick the {[!d && 'day', !m && 'month', !y && 'year'].filter(Boolean).join(' and ')}</span> : null}
        {note && <span className="dob-muted" style={{ display: 'block' }}>{note}</span>}
        {typedErr && <span className="form-error" role="alert" style={{ display: 'block' }}>{typedErr}</span>}
      </div>
      <Hint hintId={hintId} hint={hint} errId={errId} error={error} />
    </div>
  );
}
