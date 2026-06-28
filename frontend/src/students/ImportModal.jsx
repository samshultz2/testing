import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { Modal } from '../components/ui';

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

// A ready-made prompt the user can hand to any chatbot, together with a photo of
// a class list / admission register, to get rows in exactly the format this field
// parses — then they paste the answer straight into the box below.
const AI_PROMPT = `Read this class list / admission register. Output the students as comma-separated values (CSV):
- First line = the column headings, then one line per student.
- Use ONLY these headings, and only for columns that actually appear in the source: Surname, First Name, Middle Name, Gender, Date of Birth, Religion, Home Address, Hobbies, Stream, JAMB Target, Student ID, WAEC Subjects, JAMB Subjects, Parent Phone, Parent Name, Relationship.
- Dates as YYYY-MM-DD. Gender as Male or Female. WAEC/JAMB subjects separated by semicolons.
- One student per line. No numbering, no totals, no extra text, no code block.

Example:
Surname, First Name, Gender, Date of Birth
Okafor, Chidi, Male, 2008-05-12
Bello, Aisha, Female, 2009-01-30`;

// Paste-to-import: paste a heading row + students, preview what was parsed,
// then commit. Only some columns need be present; extra columns are ignored.
export default function ImportModal({ importUrl, enrolment, onClose, onDone }) {
  const [text, setText] = useState('');
  const [caa, setCaa] = useState((enrolment && enrolment.default_id) || '');
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);

  const copyPrompt = () => {
    navigator.clipboard.writeText(AI_PROMPT).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

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
      const messages = (r.messages || []);
      const attempted = (preview && preview.valid) || r.created;
      setResult({ created: r.created, attempted, messages });
    } else setErr(r.error || 'Import failed.');
  };

  // One number that explains the gap between "rows ready" and "created".
  const skippedCount = result
    ? (() => {
        const m = (result.messages || []).find((x) => /skipped as duplicates/.test(x));
        return m ? parseInt(m, 10) || 0 : Math.max(result.attempted - result.created, 0);
      })()
    : 0;

  return (
    <Modal title="Import students from pasted text" icon="fa-paste" size="lg" onClose={onClose}>
      {err && <div className="alert alert-danger" role="alert">{err}</div>}

          {result ? (
            <>
              <div className="d-flex gap-2 flex-wrap mb-2">
                <span className="badge badge-success">{result.created} imported</span>
                {skippedCount > 0 && <span className="badge badge-warning">{skippedCount} already existed (skipped)</span>}
              </div>
              <p className="text-sm">
                {result.created} student(s) were added.
                {skippedCount > 0 && ` ${skippedCount} row(s) were skipped because a student with that name is already on record (same name + date of birth, or same name + address when no DOB is given) — those students are already in your list, nothing was lost.`}
              </p>
              {result.messages.length > 0 && (
                <details open style={{ marginTop: '0.5rem' }}>
                  <summary className="text-sm text-muted" style={{ cursor: 'pointer' }}>Details ({result.messages.length})</summary>
                  <ul className="text-xs text-muted" style={{ marginTop: '0.4rem', maxHeight: 220, overflow: 'auto', paddingLeft: '1.1rem' }}>
                    {result.messages.map((m, i) => <li key={i}>{m}</li>)}
                  </ul>
                </details>
              )}
              <div className="d-flex gap-2 mt-3" style={{ justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-primary" onClick={() => onDone(`Imported ${result.created} student(s).`)}>Done — view students</button>
              </div>
            </>
          ) : !preview ? (
            <>
              <p className="text-muted text-sm" style={{ marginTop: 0 }}>
                Copy rows from a spreadsheet or type them in. The <strong>first line is the headings</strong> (e.g.
                {' '}<code>Surname, First Name, Gender</code>). Only include the columns you have — anything else is
                optional, and unknown columns are ignored. Comma- or tab-separated both work.
              </p>
              <details style={{ marginBottom: '0.6rem' }}>
                <summary className="text-sm" style={{ cursor: 'pointer', fontWeight: 500 }}>
                  <i aria-hidden="true" className="fas fa-robot" /> No spreadsheet? Get the rows from a photo with an AI
                </summary>
                <p className="text-xs text-muted" style={{ margin: '0.4rem 0' }}>
                  Upload a photo of a class list / register to any chatbot (Claude, Gemini, ChatGPT…) with this prompt,
                  then paste its answer below.
                </p>
                <pre style={{ whiteSpace: 'pre-wrap', background: 'var(--bg-muted, var(--gray-50))', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.6rem', fontSize: '0.78rem', margin: 0 }}>{AI_PROMPT}</pre>
                <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: '0.4rem' }} onClick={copyPrompt}>
                  <i aria-hidden="true" className={copied ? 'fas fa-check' : 'fas fa-copy'} /> {copied ? 'Copied' : 'Copy prompt'}
                </button>
              </details>
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
                  {busy ? 'Reading…' : <><i aria-hidden="true" className="fas fa-eye" /> Preview</>}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="d-flex gap-2 flex-wrap mb-2">
                <span className="badge badge-success">{preview.valid} ready</span>
                {preview.rows.some((r) => r.error) && (
                  <span className="badge badge-warning">{preview.rows.filter((r) => r.error).length} need a missing name</span>
                )}
                {preview.rows.some((r) => r.warn) && (
                  <span className="badge badge-warning">{preview.rows.filter((r) => r.warn).length} may be misaligned</span>
                )}
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
                      <tr key={r.row} style={(r.error || r.warn) ? { background: 'rgba(255,193,7,0.10)' } : undefined}>
                        <td>{r.row}</td>
                        <td>{r.name || <span className="text-muted">—</span>}
                          {(r.error || r.warn) && <span title={r.error || r.warn}><i aria-hidden="true" className="fas fa-triangle-exclamation text-warning" style={{ marginLeft: 4 }} /></span>}</td>
                        <td className="text-muted">{summarise(r)}</td>
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
                <button type="button" className="btn btn-light" onClick={() => setPreview(null)}><i aria-hidden="true" className="fas fa-arrow-left" /> Back to edit</button>
                <button type="button" className="btn btn-primary" disabled={busy || preview.valid === 0} onClick={doImport}>
                  {busy ? 'Importing…' : <><i aria-hidden="true" className="fas fa-file-import" /> Import {preview.valid} student(s)</>}
                </button>
              </div>
            </>
          )}
    </Modal>
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
