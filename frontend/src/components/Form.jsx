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
