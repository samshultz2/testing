import React from 'react';
import { createRoot } from 'react-dom/client';
import EntryApp from './exam_entry/EntryApp';
import { ErrorState } from './components/ui';

const el = document.getElementById('xe-data');
let data = null;
try { data = JSON.parse(el.textContent); } catch (e) { data = null; }
const mount = document.getElementById('xe-app');
if (mount) {
  createRoot(mount).render(data ? <EntryApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />);
}
