import React from 'react';
import { createRoot } from 'react-dom/client';
import SettingsApp from './settings/SettingsApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('settings-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('settings-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <SettingsApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
