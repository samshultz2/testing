import React from 'react';
import { createRoot } from 'react-dom/client';
import StudentForm from './students/StudentForm';
import { ErrorState } from './components/ui';

function initial() {
  const el = document.getElementById('student-form-data');
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}

const mount = document.getElementById('student-form-app');
const data = initial();
if (mount) {
  createRoot(mount).render(
    data ? <StudentForm data={data} />
         : <ErrorState title="Couldn’t load the form" detail="Please refresh the page." />
  );
}
