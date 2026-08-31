import React from 'react';
import { createRoot } from 'react-dom/client';
import MockJambApp from './mock_jamb/MockJambApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('mj-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('mj-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <MockJambApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
