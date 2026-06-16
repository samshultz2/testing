import React from 'react';
import { createRoot } from 'react-dom/client';
import CbtApp from './cbt/CbtApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('cbt-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('cbt-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <CbtApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
