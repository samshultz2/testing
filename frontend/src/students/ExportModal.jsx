import React, { useState } from 'react';
import { Modal, Button } from '../components/ui';

const FIELDS = [
  ['student_id', 'Student ID'], ['surname', 'Surname'], ['first_name', 'First Name'],
  ['middle_name', 'Middle Name'], ['gender', 'Gender'], ['current_class', 'Class'],
  ['date_of_birth', 'Date of Birth'], ['age', 'Age'], ['religion', 'Religion'],
  ['home_address', 'Home Address'], ['hobbies', 'Hobbies'], ['parent_phone', 'Parent Phone'],
  ['nin', 'NIN'], ['jamb_profile_code', 'JAMB Profile Code'],
  ['jamb_reg_number', 'JAMB Reg Number'], ['waec_reg_number', 'WAEC Reg Number'],
];
const DEFAULT_ON = new Set(['student_id', 'surname', 'first_name', 'gender', 'current_class']);
const FORMATS = [
  ['excel', 'Excel', 'fa-file-excel'], ['word', 'Word', 'fa-file-word'],
  ['pdf', 'PDF', 'fa-file-pdf'], ['image', 'Image', 'fa-file-image'],
];

// Field + format picker that builds a download URL on the existing export route.
// Exports the selected students, or all rows matching the current filters.
export default function ExportModal({ total, selectedIds, exportUrl, applied, onClose }) {
  const [checked, setChecked] = useState(() => {
    const init = {}; FIELDS.forEach(([k]) => { init[k] = DEFAULT_ON.has(k); }); return init;
  });
  const [format, setFormat] = useState('excel');
  const toggle = (k) => setChecked((c) => ({ ...c, [k]: !c[k] }));

  const doExport = () => {
    const fields = FIELDS.filter(([k]) => checked[k]).map(([k]) => k);
    if (!fields.length) return;
    const p = new URLSearchParams();
    p.set('format', format);
    p.set('fields', JSON.stringify(fields));
    if (selectedIds.length) p.set('student_ids', JSON.stringify(selectedIds));
    else {
      // export all matching the current filters
      Object.entries(applied || {}).forEach(([k, v]) => { if (v) p.set(k, v); });
    }
    window.location.href = `${exportUrl}?${p.toString()}`;
    onClose();
  };

  const count = selectedIds.length || total;
  return (
    <Modal title="Export students" icon="fa-download" size="lg" onClose={onClose}
           footer={<>
             <Button variant="secondary" onClick={onClose}>Cancel</Button>
             <Button variant="primary" onClick={doExport}><i className="fas fa-download" aria-hidden="true" /> Export</Button>
           </>}>
      <p className="text-muted text-sm"><i className="fas fa-info-circle" aria-hidden="true" /> Exporting {selectedIds.length ? <strong>{count} selected</strong> : <>all <strong>{count}</strong></>} student(s).</p>
      <div className="field-section-title" style={{ fontWeight: 600, margin: '.5rem 0' }}>Fields</div>
      <div className="stu-field-grid">
        {FIELDS.map(([k, label]) => (
          <label key={k} className="stu-field">
            <input type="checkbox" checked={!!checked[k]} onChange={() => toggle(k)} /> <span>{label}</span>
          </label>
        ))}
      </div>
      <div className="field-section-title" style={{ fontWeight: 600, margin: '.75rem 0 .5rem' }}>Format</div>
      <div className="stu-fmt">
        {FORMATS.map(([k, label, icon]) => (
          <button key={k} type="button" className={format === k ? 'sel' : ''} onClick={() => setFormat(k)}
                  aria-pressed={format === k}>
            <i className={'fas ' + icon} style={{ fontSize: 'var(--text-lg)' }} aria-hidden="true" /><span>{label}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}
