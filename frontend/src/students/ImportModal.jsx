import React, { useState } from 'react';
import { submitJson } from '../lib/forms';

// Friendly labels for the recognised field keys.
const FIELD_LABELS = {
  surname: 'Surname', first_name: 'First name', middle_name: 'Middle name',
  full_name: 'Full name', gender: 'Gender', date_of_birth: 'Date of birth',
  religion: 'Religion', home_address: 'Home address', hobbies: 'Hobbies',
  stream: 'Stream', jamb_target: 'JAMB target', student_id: 'Student ID',
  waec_subjects: 'WAEC subjects', jamb_subjects: 'JAMB subjects',
  phone_number: 'Parent phone', contact_name: 'Parent name', relationship: 'Relationship',
};

const SAMPLE = 'Surname, First Name, Gender\nOkafor, Chidi, Male\nBello, Aisha, Female';

// Paste-to-import: paste a heading row + students, preview what was parsed,
// then commit. Only some columns need be present; extra columns are ignored.
export default function ImportModal({ importUrl, enrolment, onClose, onDone }) {
  const [text, setText] = useState('');
  const [caa, setCaa] = useState((enrolment && enrolment.default_id) || '');
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const doPreview = async () => {
    setErr(null); setBusy(true);
    const r = await submitJson(importUrl, { text });
    setBusy(false);
    if (r.ok) setPreview(r);
    else { setPreview(null); setErr(r.error || 'Could not read that text.'); }
  };

  const doImport = async () => {
    setErr(null); setBusy(true);
    const r = await submitJson(importUrl, { text, commit: '1', class_arm_assignment_id: caa || '' });
    setBusy(false);
    if (r.ok) {
      // Surface the importer's notes (duplicates skipped, gender defaulted, …).
      const notes = (r.messages || []).filter((m) => !/^\d+ student\(s\) enrolled/.test(m));
      onDone(`Imported ${r.created} student(s).` + (notes.length ? ` ${notes[0]}` : ''));
    } else setErr(r.error || 'Import failed.');
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true"
         style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 9999, padding: '1rem', overflowY: 'auto' }}>
      <div className="card" style={{ maxWidth: 760, margin: '1.5rem auto' }}>
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 className="card-title"><i className="fas fa-paste" /> Import students from pasted text</h3>
          <button type="button" className="att-x" onClick={onClose} aria-label="Close"
                  style={{ background: 'none', border: 'none', fontSize: '1.4rem', cursor: 'pointer' }}>×</button>
        </div>
        <div className="card-body">
          {err && <div className="alert alert-danger" role="alert">{err}</div>}

          {!preview ? (
            <>
              <p className="text-muted text-sm" style={{ marginTop: 0 }}>
                Copy rows from a spreadsheet or type them in. The <strong>first line is the headings</strong> (e.g.
                {' '}<code>Surname, First Name, Gender</code>). Only include the columns you have — anything else is
                optional, and unknown columns are ignored. Comma- or tab-separated both work.
              </p>
              <textarea className="form-control" rows={10} value={text} spellCheck={false}
                        placeholder={SAMPLE} onChange={(e) => setText(e.target.value)}
                        style={{ fontFamily: 'monospace', fontSize: '0.85rem' }} />
              <details style={{ marginTop: '0.5rem' }}>
                <summary className="text-sm text-muted" style={{ cursor: 'pointer' }}>Recognised headings</summary>
                <p className="text-xs text-muted" style={{ marginTop: '0.4rem' }}>
                  Surname · First Name · Middle Name · Full Name · Gender · Date of Birth (DOB) · Religion ·
                  Home Address · Hobbies · Stream · JAMB Target · Student ID · WAEC Subjects · JAMB Subjects ·
                  Parent Phone · Parent Name · Relationship. Headings are matched loosely (case/spacing don't matter).
                </p>
              </details>
              <div className="d-flex gap-2 mt-3" style={{ justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
                <button type="button" className="btn btn-primary" disabled={busy || !text.trim()} onClick={doPreview}>
                  {busy ? 'Reading…' : <><i className="fas fa-eye" /> Preview</>}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="d-flex gap-2 flex-wrap mb-2">
                <span className="badge badge-success">{preview.valid} ready</span>
                {preview.invalid > 0 && <span className="badge badge-warning">{preview.invalid} skipped</span>}
                <span className="badge badge-info">{preview.total} rows total</span>
              </div>
              <p className="text-sm" style={{ margin: '0 0 0.5rem' }}>
                <strong>Detected columns:</strong>{' '}
                {preview.recognised.map((f) => FIELD_LABELS[f] || f).join(', ') || '—'}
                {preview.ignored.length > 0 && (
                  <><br /><span className="text-muted">Ignored: {preview.ignored.join(', ')}</span></>
                )}
              </p>

              <div className="table-responsive" style={{ maxHeight: 300, overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)' }}>
                <table className="table" style={{ fontSize: '0.8rem', margin: 0 }}>
                  <thead><tr><th>#</th><th>Name</th><th>Details</th></tr></thead>
                  <tbody>
                    {preview.rows.map((r) => (
                      <tr key={r.row} style={r.error ? { background: 'rgba(220,53,69,0.06)' } : undefined}>
                        <td>{r.row}</td>
                        {r.error
                          ? <td colSpan={2} className="text-danger"><i className="fas fa-triangle-exclamation" /> {r.error}</td>
                          : <>
                              <td>{r.name}</td>
                              <td className="text-muted">{summarise(r)}</td>
                            </>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.truncated && <p className="text-xs text-muted">Showing the first 200 rows; all valid rows will be imported.</p>}

              {enrolment && enrolment.has_classes && (
                <div className="form-group mt-3">
                  <label className="form-label">Enrol all imported students in a class ({enrolment.term_label}) — optional</label>
                  <select className="form-control" value={caa} onChange={(e) => setCaa(e.target.value)}>
                    <option value="">Don't enrol now</option>
                    {enrolment.classes.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                  </select>
                </div>
              )}

              <div className="d-flex gap-2 mt-3" style={{ justifyContent: 'space-between' }}>
                <button type="button" className="btn btn-light" onClick={() => setPreview(null)}><i className="fas fa-arrow-left" /> Back to edit</button>
                <button type="button" className="btn btn-primary" disabled={busy || preview.valid === 0} onClick={doImport}>
                  {busy ? 'Importing…' : <><i className="fas fa-file-import" /> Import {preview.valid} student(s)</>}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// One-line summary of the parsed fields for a previewed (valid) row.
function summarise(r) {
  const a = r.details || {};
  const bits = [];
  if (a.gender) bits.push(a.gender);
  if (a.religion) bits.push(a.religion);
  if (a.date_of_birth) bits.push(`DOB ${a.date_of_birth}`);
  if (a.phone_number) bits.push(`☎ ${a.phone_number}`);
  if (a.address) bits.push(a.address);
  return bits.join(' · ') || '—';
}
