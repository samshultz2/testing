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
