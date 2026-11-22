import React, { useState, useMemo } from 'react';
import { submitJson } from '../lib/forms';
import { Modal } from '../components/ui';
import { copyText } from '../lib/clipboard';

// The columns an update can change, grouped as they appear in the picker. Each
// carries the exact heading the server recognises, a sample value and, where it
// matters, a rule for the AI so its output parses cleanly.
const FIELD_GROUPS = [
  { label: 'Personal', fields: [
    { h: 'Middle Name', ex: 'Ada' },
    { h: 'Gender', ex: 'Male', rule: 'Gender is Male or Female.' },
    { h: 'Date of Birth', ex: '14/03/2010', rule: 'Date of Birth as DD/MM/YYYY.' },
    { h: 'Religion', ex: 'Christianity', rule: 'Religion is one of: Christianity, Islam, Traditional, Others.' },
    { h: 'Home Address', ex: '"12 Aba Road, Benin"' },
    { h: 'Hobbies', ex: 'Football' },
  ] },
  { label: 'Parents', fields: [
    { h: 'Father Name', ex: 'Mr Emeka Okafor' },
    { h: 'Father Phone', ex: '08011112222', rule: 'Phone numbers are exactly 11 digits (e.g. 08011112222), no spaces or +234.' },
    { h: 'Mother Name', ex: 'Mrs Ngozi Okafor' },
    { h: 'Mother Phone', ex: '08033334444', rule: 'Phone numbers are exactly 11 digits (e.g. 08011112222), no spaces or +234.' },
  ] },
  { label: 'Exam numbers', fields: [
    { h: 'NIN', ex: '12345678901', rule: 'NIN is 11 digits.' },
    { h: 'WAEC Reg Number', ex: '4250101001' },
    { h: 'WAEC Serial Number', ex: 'WRN123456' },
    { h: 'WAEC e-PIN', ex: '123456789012' },
    { h: 'NECO Reg Number', ex: '2611532868CC' },
    { h: 'NECO Token', ex: 'AB12CD34' },
    { h: 'JAMB Reg Number', ex: '202612345678AB' },
    { h: 'JAMB Profile Code', ex: '1234567890' },
  ] },
  { label: 'Name corrections', fields: [
    { h: 'Surname', ex: 'Okafor', fix: true },
    { h: 'First Name', ex: 'Chidi', fix: true },
  ] },
];
const ALL_FIELDS = FIELD_GROUPS.flatMap((g) => g.fields);
const MATCH = {
  id: { cols: ['Student ID'], ex: ['STU00012'], say: 'Identify each student by "Student ID" exactly as written on the sheet.' },
  name: { cols: ['Surname', 'First Name'], ex: ['Okafor', 'Chidi'], say: 'Identify each student by "Surname" and "First Name" exactly as written (the app matches them within the class chosen).' },
  both: { cols: ['Student ID', 'Surname', 'First Name'], ex: ['STU00012', 'Okafor', 'Chidi'], say: 'Identify each student by "Student ID" when the sheet shows one, plus "Surname" and "First Name".' },
};
const PREF_KEY = 'stuUpdateFields';

function loadPrefs() {
  try { const v = JSON.parse(localStorage.getItem(PREF_KEY) || 'null'); if (v && Array.isArray(v.fields)) return v; } catch (_) { /* private mode */ }
  return { fields: ['Religion', 'Father Phone', 'Mother Phone'], match: 'name' };
}

// The heading row, an example row and the AI prompt for the chosen columns.
export function buildUpdateTemplate(chosen, match) {
  const m = MATCH[match] || MATCH.name;
  const picked = ALL_FIELDS.filter((f) => chosen.includes(f.h));
  // Name corrections only work when the row is matched by Student ID.
  const fixing = picked.some((f) => f.fix);
  const idCols = fixing ? ['Student ID'] : m.cols;
  const idEx = fixing ? ['STU00012'] : m.ex;
  const cols = [...idCols, ...picked.filter((f) => !idCols.includes(f.h)).map((f) => f.h)];
  const exRow = [...idEx, ...picked.filter((f) => !idCols.includes(f.h)).map((f) => f.ex)];
  const head = cols.join(', ');
  const sample = `${head}\n${exRow.join(', ')}`;
  const rules = [...new Set(picked.map((f) => f.rule).filter(Boolean))];
  const prompt = `Read this class list / register. Output the rows as comma-separated values (CSV):
- The first line must be exactly these column headings, in this order:
${head}
- Then one line per student, in the same column order.
- ${fixing ? 'Identify each student by "Student ID" exactly as written (it is needed because names are being corrected).' : m.say}
- Fill only the columns listed above. If a value is missing or unreadable for a student, leave that cell BLANK (it keeps what is already saved). Never guess a value.
${rules.map((r) => `- ${r}\n`).join('')}- If a value contains a comma, wrap it in double quotes.
- One student per line. No numbering, no totals, no extra text, no code block.

Example:
${sample}`;
  return { head, sample, prompt, cols };
}

export default function UpdateImportModal({ updateImportUrl, filters, onClose, onDone }) {
  const [classId, setClassId] = useState('');
  const [armId, setArmId] = useState('');
  const [text, setText] = useState('');
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState('');
  const [prefs, setPrefs] = useState(loadPrefs);
  const savePrefs = (next) => { setPrefs(next); try { localStorage.setItem(PREF_KEY, JSON.stringify(next)); } catch (_) { /* ignore */ } };
  const toggleField = (h) => savePrefs({ ...prefs, fields: prefs.fields.includes(h) ? prefs.fields.filter((x) => x !== h) : [...prefs.fields, h] });
  const tpl = useMemo(() => buildUpdateTemplate(prefs.fields, prefs.match), [prefs]);
  const fixing = prefs.fields.includes('Surname') || prefs.fields.includes('First Name');

  const classes = (filters && filters.classes) || [];
  const arms = (filters && filters.arms) || [];

  const copy = async (what, value) => {
    if (await copyText(value)) {
      setCopied(what);
      setTimeout(() => setCopied(''), 2000);
    } else {
      setErr('Your browser blocked copying. Long-press the prompt text to copy it instead.');
    }
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

          <fieldset className="uf-pick">
            <legend className="form-label">What are you updating?</legend>
            {FIELD_GROUPS.map((g) => (
              <div key={g.label} className="uf-group">
                <span className="uf-gl">{g.label}</span>
                <div className="uf-chips">
                  {g.fields.map((f) => {
                    const on = prefs.fields.includes(f.h);
                    return (
                      <button key={f.h} type="button" className={'uf-chip' + (on ? ' on' : '')} aria-pressed={on} onClick={() => toggleField(f.h)}>
                        <i aria-hidden="true" className={'fas ' + (on ? 'fa-check' : 'fa-plus')} />{f.h}</button>);
                  })}
                </div>
              </div>))}
            <div className="uf-group">
              <span className="uf-gl">Match students by</span>
              <div className="uf-chips" role="radiogroup" aria-label="Match students by">
                {[['name', 'Surname + First Name'], ['id', 'Student ID'], ['both', 'Both']].map(([k, l]) => (
                  <button key={k} type="button" role="radio" aria-checked={prefs.match === k} disabled={fixing && k !== 'id'}
                          className={'uf-chip' + ((fixing ? k === 'id' : prefs.match === k) ? ' on' : '')} onClick={() => savePrefs({ ...prefs, match: k })}>{l}</button>))}
              </div>
            </div>
            {fixing && <p className="text-xs text-muted" style={{ margin: '0.2rem 0 0' }}>Correcting names needs each row matched by Student ID.</p>}
            <div className="uf-head">
              <code>{tpl.head}</code>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => copy('head', tpl.head)}>
                <i aria-hidden="true" className={copied === 'head' ? 'fas fa-check' : 'fas fa-copy'} /> {copied === 'head' ? 'Copied' : 'Copy headings'}</button>
            </div>
          </fieldset>

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
            <p className="text-xs text-muted" style={{ margin: '0 0 0.4rem' }}>
              It asks only for the {tpl.cols.length} column{tpl.cols.length === 1 ? '' : 's'} chosen above{prefs.fields.length ? '' : ' — pick what you are updating first'}.
            </p>
            <pre style={{ whiteSpace: 'pre-wrap', background: 'var(--bg-muted, var(--gray-50))', border: '1px solid var(--border-color)', borderRadius: 8, padding: '0.6rem', fontSize: 'var(--text-xs)', margin: 0 }}>{tpl.prompt}</pre>
            <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: '0.4rem' }} onClick={() => copy('prompt', tpl.prompt)} disabled={!prefs.fields.length}>
              <i aria-hidden="true" className={copied === 'prompt' ? 'fas fa-check' : 'fas fa-copy'} /> {copied === 'prompt' ? 'Copied' : 'Copy prompt'}
            </button>
          </details>
          <textarea className="form-control" rows={10} value={text} spellCheck={false}
                    placeholder={tpl.sample} onChange={(e) => setText(e.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: 'var(--text-sm)' }} />
          <details style={{ marginTop: '0.5rem' }}>
            <summary className="text-sm text-muted" style={{ cursor: 'pointer' }}>Recognised headings</summary>
            <p className="text-xs text-muted" style={{ marginTop: '0.4rem' }}>
              Student ID · Surname · First Name · Middle Name · Gender · Date of Birth (DOB) · Religion ·
              Home Address · Hobbies · Father Name · Father Phone · Mother Name · Mother Phone ·
              Parent Name · Parent Phone · Relationship.
              <br /><strong>Exam numbers:</strong> NIN · WAEC Reg Number · WAEC Serial Number · WAEC e-PIN ·
              NECO Reg Number · NECO Token · JAMB Reg Number · JAMB Profile Code.
              Headings are matched loosely (case/spacing don't matter).
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
