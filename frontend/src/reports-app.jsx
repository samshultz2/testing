import React from 'react';
import { createRoot } from 'react-dom/client';
import ReportsApp from './reports/ReportsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('reports-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('reports-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <ReportsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
