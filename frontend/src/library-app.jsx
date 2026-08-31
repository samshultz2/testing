import React from 'react';
import { createRoot } from 'react-dom/client';
import LibraryApp from './library/LibraryApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('library-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('library-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <LibraryApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
