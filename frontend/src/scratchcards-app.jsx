import React from 'react';
import { createRoot } from 'react-dom/client';
import ScratchcardsApp from './scratchcards/ScratchcardsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('sc-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('sc-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <ScratchcardsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
