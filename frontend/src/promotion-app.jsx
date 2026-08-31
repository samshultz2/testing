import React from 'react';
import { createRoot } from 'react-dom/client';
import PromotionApp from './promotion/PromotionApp';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('promo-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('promo-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <PromotionApp data={data} /> : <ErrorState title="Couldn’t load this page" detail="Please refresh." />
  );
}
