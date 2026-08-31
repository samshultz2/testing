// Thin fetch wrapper: same-origin cookie auth + CSRF + X-Requested-With (so a
// denied call returns JSON 403, not an HTML redirect), and JSON parsing.
// Errors carry `.status` so callers can tell transient (network/5xx) from
// permanent (4xx) failures.
export function csrfToken() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}

async function request(url, opts = {}) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    ...opts,
    headers: {
      'X-CSRFToken': csrfToken(),
      'X-Requested-With': 'fetch',
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).error || ''; } catch (_) {}
    const e = new Error(detail || 'HTTP ' + res.status);
    e.status = res.status;
    throw e;
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

export const apiGet = (url) => request(url);
export const apiPost = (url, body) =>
  request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export const isPermanent = (err) => !!err && err.status >= 400 && err.status < 500;
