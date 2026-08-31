import React from 'react';
import { createRoot } from 'react-dom/client';
import ResultsApp from './results/ResultsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('res-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('res-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <ResultsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
