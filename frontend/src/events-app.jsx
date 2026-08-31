import React from 'react';
import { createRoot } from 'react-dom/client';
import EventsApp from './events/EventsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('events-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('events-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <EventsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
