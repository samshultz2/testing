import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './attendance/App';

const mount = document.getElementById('attendance-spa');
if (mount) createRoot(mount).render(<App />);
