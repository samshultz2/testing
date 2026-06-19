import React from 'react';
import { createRoot } from 'react-dom/client';
import ContributionsApp from './contributions/ContributionsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('contrib-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('contrib-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <ContributionsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
