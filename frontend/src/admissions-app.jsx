import React from 'react';
import { createRoot } from 'react-dom/client';
import AdmissionsApp from './admissions/AdmissionsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('adm-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('adm-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <AdmissionsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
