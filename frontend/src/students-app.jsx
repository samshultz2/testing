import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './students/App';

// First page is hydrated inline by the server (scoped + filtered); subsequent
// filter/page changes fetch /api/students.
function initial() {
  const el = document.getElementById('students-data');
  if (!el) return {};
  try { return JSON.parse(el.textContent); } catch (e) { return {}; }
}

const mount = document.getElementById('students-app');
if (mount) createRoot(mount).render(<App initial={initial()} />);
