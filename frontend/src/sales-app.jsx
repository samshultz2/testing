import React from 'react';
import { createRoot } from 'react-dom/client';
import SalesApp from './sales/SalesApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('sales-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('sales-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <SalesApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
