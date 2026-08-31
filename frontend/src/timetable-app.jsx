import React from 'react';
import { createRoot } from 'react-dom/client';
import TimetableApp from './timetable/TimetableApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('tt-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('tt-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <TimetableApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
