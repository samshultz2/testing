import React from 'react';
import { createRoot } from 'react-dom/client';
import SubjectsApp from './subjects/SubjectsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('subj-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('subj-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <SubjectsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
