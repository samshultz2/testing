import React from 'react';
import { createRoot } from 'react-dom/client';
import TrashApp from './students/TrashApp';

function initial() {
  const el = document.getElementById('student-trash-data');
  try { return JSON.parse(el.textContent); } catch (e) { return { students: [], urls: {} }; }
}

const mount = document.getElementById('student-trash-app');
if (mount) createRoot(mount).render(<TrashApp initial={initial()} />);
