import React from 'react';
import { createRoot } from 'react-dom/client';
import CommunicationApp from './communication/CommunicationApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('comm-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('comm-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <CommunicationApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
