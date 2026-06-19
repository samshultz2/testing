import React from 'react';
import { createRoot } from 'react-dom/client';
import AcademicsApp from './academics/AcademicsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('acad-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('acad-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <AcademicsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
