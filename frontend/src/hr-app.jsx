import React from 'react';
import { createRoot } from 'react-dom/client';
import HrApp from './hr/HrApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('hr-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('hr-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <HrApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
