import { useState, useCallback } from 'react';
import { csrfToken } from './api';

// Form-encoded POST to existing server endpoints (which expect form data and
// usually redirect), carrying CSRF. Shared by the student list + view actions.
export async function postForm(url, fields) {
  const body = new URLSearchParams();
  Object.entries(fields || {}).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach((x) => body.append(k, x));
    else if (v !== undefined && v !== null && v !== false) body.append(k, v);
  });
  return fetch(url, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch',
               'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
}

// postForm + JSON parse, normalised. Every React section's actions share this:
// returns { ok, status, redirect, error, message, ... } so callers just branch
// on `ok` and navigate/reload or show `error`.
export async function submitJson(url, fields) {
  let res, body = {};
  try {
    res = await postForm(url, fields);
  } catch (e) {
    return { ok: false, status: 0, error: e.message || 'Network error — please try again.' };
  }
  try { body = await res.json(); } catch (_) { /* redirect/html response */ }
  return { status: res.status, ...body, ok: !!(res.ok && body.ok === true) };
}

// Shared save action: POST form fields, surface success/error via `notify`, run
// `after` on success. Previously copy-pasted into Settings/Finance/Results.
// Returns a function (url, fields, after, okMsg) => Promise<result>.
export function useSave(notify) {
  return useCallback(async (url, fields, after, okMsg) => {
    const r = await submitJson(url, fields);
    if (r.ok) { notify && notify('success', okMsg || r.message); after && after(r); }
    else notify && notify('error', r.error || 'Something went wrong.');
    return r;
  }, [notify]);
}

// Minimal controlled-form helper: kills the repeated
// `const [f,setF]=useState({...}); const set=k=>e=>setF({...f,[k]:e.target.value})`
// boilerplate. `setField(key, value)` takes a bare value; `bind(key)` returns
// {value, onChange} for an <input>/<select>. `validate(rules)` sets field errors.
export function useForm(initial) {
  const [values, setValues] = useState(initial || {});
  const [errors, setErrors] = useState({});
  const setField = useCallback((key, value) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => (e[key] ? { ...e, [key]: undefined } : e));
  }, []);
  const bind = useCallback((key) => ({
    value: values[key] ?? '',
    onChange: (e) => setField(key, e && e.target ? e.target.value : e),
  }), [values, setField]);
  const reset = useCallback((next) => { setValues(next || initial || {}); setErrors({}); },
    [initial]);
  // rules: { field: (value, values) => errorString|falsy }. Returns true if valid.
  const validate = useCallback((rules) => {
    const next = {};
    Object.keys(rules || {}).forEach((k) => {
      const msg = rules[k](values[k], values);
      if (msg) next[k] = msg;
    });
    setErrors(next);
    return Object.keys(next).length === 0;
  }, [values]);
  return { values, setValues, errors, setErrors, setField, bind, reset, validate };
}

// Multipart upload (a single file + optional extra fields), JSON response.
export async function postFile(url, file, extra = {}) {
  const fd = new FormData();
  fd.append('file', file);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  let res, body = {};
  try {
    res = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch' }, body: fd,
    });
  } catch (e) {
    return { ok: false, status: 0, error: e.message || 'Upload failed.' };
  }
  try { body = await res.json(); } catch (_) { /* ignore */ }
  return { status: res.status, ...body, ok: !!(res.ok && body.ok === true) };
}
