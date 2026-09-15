import React, { useState, useMemo } from 'react';
import { submitJson } from '../lib/forms';
import { Modal } from '../components/ui';

const SAMPLE = 'Surname, First Name, Religion, Father Phone\nOkafor, Chidi, Islam, 08011112222';

// A ready-made prompt for the user to hand to any chatbot, together with a photo
// of an updated register, to get rows in exactly the format this field parses.
const AI_PROMPT = `Read this class list / register. Output the rows to UPDATE as comma-separated values (CSV):
- First line = the column headings, then one line per student.
- Only include a column for something that actually needs to change — leave a cell BLANK to leave that field as it already is. Never guess a value just to fill a cell.
- To identify each student, include "Student ID" if the sheet shows one, and/or Surname + First Name (matched within the class/arm chosen in the app).
- For parent contacts, use "Father Phone"/"Father Name" and "Mother Phone"/"Mother Name" as separate columns when both are known — each phone number must be exactly 11 digits (Nigerian mobile format, e.g. 08011112222).
- Use ONLY these headings, and only for columns that actually appear/need changing: Student ID, Surname, First Name, Middle Name, Gender, Date of Birth, Religion, Home Address, Hobbies, Father Name, Father Phone, Mother Name, Mother Phone.
- One student per line. No numbering, no totals, no extra text, no code block.

Example:
Surname, First Name, Religion, Father Phone
Okafor, Chidi, Islam, 08011112222`;

export default function UpdateImportModal({ updateImportUrl, filters, onClose, onDone }) {
  const [classId, setClassId] = useState('');
  const [armId, setArmId] = useState('');
  const [text, setText] = useState('');
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);

  const classes = (filters && filters.classes) || [];
  const arms = (filters && filters.arms) || [];

  const copyPrompt = () => {
    navigator.clipboard.writeText(AI_PROMPT).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const doPreview = async () => {
    setErr(null); setBusy(true);
    const r = await submitJson(updateImportUrl, { text, class_id: classId, arm_id: armId || '' });
    setBusy(false);
    if (r.ok) setPreview(r);
    else { setPreview(null); setErr(r.error || 'Could not read that text.'); }
  };

  const doUpdate = async () => {
    setErr(null); setBusy(true);
    const r = await submitJson(updateImportUrl, { text, class_id: classId, arm_id: armId || '', commit: '1' });
    setBusy(false);
    if (r.ok) setResult({ updated: r.updated, messages: r.messages || [] });
    else setErr(r.error || 'Update failed.');
  };

  const matchedRows = useMemo(() => (preview ? preview.rows.filter((r) => r.matched) : []), [preview]);
  const problemRows = useMemo(() => (preview ? preview.rows.filter((r) => !r.matched) : []), [preview]);
  const changedCount = matchedRows.filter((r) => !r.no_changes).length;

  return (
    <Modal title="Update students from pasted text" icon="fa-pen-to-square" size="lg" onClose={onClose}>
      {err && <div className="alert alert-danger" role="alert">{err}</div>}

      {result ? (
        <>
          <div className="d-flex gap-2 flex-wrap mb-2">
            <span className="badge badge-success">{result.updated} updated</span>
          </div>
          <p className="text-sm">{result.updated} student(s) were updated.</p>
          {result.messages.length > 0 && (
            <details open style={{ marginTop: '0.5rem' }}>
              <summary className="text-sm text-muted" style={{ cursor: 'pointer' }}>Details ({result.messages.length})</summary>
              <ul className="text-xs text-muted" style={{ marginTop: '0.4rem', maxHeight: 220, overflow: 'auto', paddingLeft: '1.1rem' }}>
                {result.messages.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            </details>
          )}
          <div className="d-flex gap-2 mt-3" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-primary" onClick={() => onDone(`Updated ${result.updated} student(s).`)}>Done — view students</button>
          </div>
        </>
      ) : !preview ? (
        <>
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>
            Choose the class (and optionally arm) to search — the update only looks at students
            already enrolled there, so it's fast and can't touch a same-named student elsewhere.
          </p>
          <div className="d-flex gap-2 flex-wrap" style={{ marginBottom: '0.75rem' }}>
            <div className="form-group" style={{ flex: 1, minWidth: 160 }}>
              <label className="form-label">Class</label>
              <select className="form-control" value={classId} onChange={(e) => setClassId(e.target.value)}>
                <option value="">Choose a class…</option>
                {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="form-group" style={{ flex: 1, minWidth: 160 }}>
              <label className="form-label">Arm <span className="text-muted">(optional — narrows to one arm)</span></label>
              <select className="form-control" value={armId} onChange={(e) => setArmId(e.target.value)}>
                <option value="">All arms of this class</option>
                {arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
          </div>

          <p className="text-muted text-sm">
            Copy rows from a spreadsheet or type them in. The <strong>first line is the headings</strong>.
            Only include a column for something you want to change — a <strong>blank cell leaves that field
            as it is</strong>. Match a student by <code>Student ID</code>, or by <code>Surname</code> +{' '}
            <code>First Name</code> (must be unique within the class/arm chosen above). For separate
            parent numbers use <code>Father Phone</code> / <code>Mother Phone</code> (each exactly 11 digits).
          </p>
          <details style={{ marginBottom: '0.6rem' }}>
            <summary className="text-sm" style={{ cursor: 'pointer', fontWeight: 500 }}>
              <i aria-hidden="true" className="fas fa-robot" /> No spreadsheet? Get the rows from a photo with an AI
            </summary>
            <p className="text-xs text-muted" style={{ margin: '0.4rem 0' }}>
              Upload a photo of the updated register to any chatbot (Claude, Gemini, ChatGPT…) with this prompt,
              then paste its answer below.
            </p>
            <pre style={{ whiteSpace: 'pre-wrap', background: 'var(--bg-muted, var(--gray-50))', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.6rem', fontSize: 'var(--text-xs)', margin: 0 }}>{AI_PROMPT}</pre>
            <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: '0.4rem' }} onClick={copyPrompt}>
              <i aria-hidden="true" className={copied ? 'fas fa-check' : 'fas fa-copy'} /> {copied ? 'Copied' : 'Copy prompt'}
            </button>
          </details>
          <textarea className="form-control" rows={10} value={text} spellCheck={false}
                    placeholder={SAMPLE} onChange={(e) => setText(e.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: 'var(--text-sm)' }} />
          <details style={{ marginTop: '0.5rem' }}>
            <summary className="text-sm text-muted" style={{ cursor: 'pointer' }}>Recognised headings</summary>
            <p className="text-xs text-muted" style={{ marginTop: '0.4rem' }}>
              Student ID · Surname · First Name · Middle Name · Gender · Date of Birth (DOB) · Religion ·
              Home Address · Hobbies · Father Name · Father Phone · Mother Name · Mother Phone ·
              Parent Name · Parent Phone · Relationship. Headings are matched loosely (case/spacing don't matter).
            </p>
          </details>
          <div className="d-flex gap-2 mt-3" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="button" className="btn btn-primary" disabled={busy || !text.trim() || !classId} onClick={doPreview}>
              {busy ? 'Reading…' : <><i aria-hidden="true" className="fas fa-eye" /> Preview</>}
            </button>
          </div>
          {!classId && text.trim() && <p className="text-xs text-warning" style={{ marginTop: '0.4rem' }}>Choose a class first.</p>}
        </>
      ) : (
        <>
          <div className="d-flex gap-2 flex-wrap mb-2">
            <span className="badge badge-success">{changedCount} will change</span>
            {matchedRows.length - changedCount > 0 && (
              <span className="badge badge-secondary">{matchedRows.length - changedCount} already up to date</span>
            )}
            {problemRows.length > 0 && (
              <span className="badge badge-warning">{problemRows.length} couldn't be matched</span>
            )}
            <span className="badge badge-info">{preview.total} row(s) total</span>
          </div>
          <p className="text-sm" style={{ margin: '0 0 0.5rem' }}>
            <strong>Detected columns:</strong>{' '}
            {preview.recognised.length ? preview.recognised.join(', ') : '—'}
            {preview.ignored.length > 0 && (
              <><br /><span className="text-muted">Ignored: {preview.ignored.join(', ')}</span></>
            )}
          </p>

          <div className="table-responsive" style={{ maxHeight: 360, overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)' }}>
            <table className="table" style={{ fontSize: 'var(--text-sm)', margin: 0 }}>
              <thead><tr><th>#</th><th>Student</th><th>Changes</th></tr></thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.row} style={(!r.matched || r.warn) ? { background: 'rgba(255,193,7,0.10)' } : undefined}>
                    <td>{r.row}</td>
                    <td>
                      {r.matched ? (
                        <>{r.name} <span className="text-muted">({r.student_code})</span></>
                      ) : (
                        <span className="text-danger"><i aria-hidden="true" className="fas fa-triangle-exclamation" /> {r.error}</span>
                      )}
                    </td>
                    <td className="text-muted">
                      {r.matched && (r.no_changes ? <span>No changes</span> : summariseChanges(r))}
                      {r.warn && <div style={{ color: 'var(--warning, #b45309)' }}><i aria-hidden="true" className="fas fa-triangle-exclamation" /> {r.warn}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="d-flex gap-2 mt-3" style={{ justifyContent: 'space-between' }}>
            <button type="button" className="btn btn-light" onClick={() => setPreview(null)}><i aria-hidden="true" className="fas fa-arrow-left" /> Back to edit</button>
            <button type="button" className="btn btn-primary" disabled={busy || changedCount === 0} onClick={doUpdate}>
              {busy ? 'Updating…' : <><i aria-hidden="true" className="fas fa-check" /> Confirm — update {changedCount} student(s)</>}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}

// One-line summary of a matched row's field + contact changes.
function summariseChanges(r) {
  const bits = [];
  (r.changes || []).forEach((c) => {
    bits.push(`${c.label}: ${fmt(c.old)} → ${fmt(c.new)}`);
  });
  (r.contact_changes || []).forEach((c) => {
    const label = `${c.relationship} phone`;
    bits.push(c.created ? `${label}: ${fmt(null)} → ${c.new_phone}` : `${label}: ${fmt(c.old_phone)} → ${c.new_phone}`);
  });
  return bits.join(' · ');
}

function fmt(v) {
  return (v === null || v === undefined || v === '') ? '(empty)' : v;
}
