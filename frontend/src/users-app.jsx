import React from 'react';
import { createRoot } from 'react-dom/client';
import UsersApp from './users/UsersApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('users-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('users-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <UsersApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
