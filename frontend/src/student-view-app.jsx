import React from 'react';
import { createRoot } from 'react-dom/client';
import ViewApp from './students/ViewApp';

function initial() {
  const el = document.getElementById('student-data');
  if (!el) return {};
  try { return JSON.parse(el.textContent); } catch (e) { return {}; }
}

const mount = document.getElementById('student-view-app');
if (mount) createRoot(mount).render(<ViewApp initial={initial()} />);
