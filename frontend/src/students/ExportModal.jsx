import React, { useState } from 'react';

const FIELDS = [
  ['student_id', 'Student ID'], ['surname', 'Surname'], ['first_name', 'First Name'],
  ['middle_name', 'Middle Name'], ['gender', 'Gender'], ['current_class', 'Class'],
  ['date_of_birth', 'Date of Birth'], ['age', 'Age'], ['religion', 'Religion'],
  ['home_address', 'Home Address'], ['hobbies', 'Hobbies'], ['parent_phone', 'Parent Phone'],
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
    <div className="stu-modal-bg" role="dialog" aria-modal="true" aria-label="Export students" onClick={onClose}>
      <div className="stu-modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 1.25rem', borderBottom: '1px solid var(--border-color)' }}>
          <h3><i className="fas fa-download" /> Export students</h3>
          <button type="button" aria-label="Close" onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', opacity: .6 }}>×</button>
        </div>
        <div className="stu-modal-sec">
          <p className="text-muted text-sm"><i className="fas fa-info-circle" /> Exporting {selectedIds.length ? <strong>{count} selected</strong> : <>all <strong>{count}</strong></>} student(s).</p>
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
              <button key={k} type="button" className={format === k ? 'sel' : ''} onClick={() => setFormat(k)}>
                <i className={'fas ' + icon} style={{ fontSize: 20 }} /><span>{label}</span>
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '.6rem', justifyContent: 'flex-end', padding: '1rem 1.25rem', borderTop: '1px solid var(--border-color)' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={doExport}><i className="fas fa-download" /> Export</button>
        </div>
      </div>
    </div>
  );
}
