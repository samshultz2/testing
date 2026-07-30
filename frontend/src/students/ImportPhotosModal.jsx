import React, { useState } from 'react';
import { postFile } from '../lib/forms';
import { Modal } from '../components/ui';

// Bulk passport-photo import: upload a .zip whose files are named by admission
// number (e.g. STU-001.jpg). The server matches each image to a student in the
// caller's scope and stores it; we surface a matched/unmatched summary.
export default function ImportPhotosModal({ importUrl, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!file) { setError('Choose a .zip of photos first.'); return; }
    setBusy(true); setError(''); setResult(null);
    const r = await postFile(importUrl, file, {});
    setBusy(false);
    if (!r.ok) { setError(r.error || 'Import failed.'); return; }
    setResult(r);
    if (r.matched && onDone) onDone(r.message);
  };

  const footer = (
    <div className="d-flex gap-2" style={{ justifyContent: 'flex-end' }}>
      <button type="button" className="btn btn-light" onClick={onClose}>Close</button>
      <button type="button" className="btn btn-primary" disabled={busy || !file} onClick={submit}>
        <i aria-hidden="true" className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-upload')} /> {busy ? 'Importing…' : 'Import photos'}
      </button>
    </div>
  );

  return (
    <Modal title="Import student photos" icon="fa-images" size="md" onClose={onClose} footer={footer}>
      {error && <div className="alert alert-danger" role="alert">{error}</div>}
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>
        Upload a <strong>.zip</strong> of passport photos. Name each file by the
        student's <strong>admission number</strong> — e.g. <code>STU-001.jpg</code>,{' '}
        <code>2024-045.png</code>. Photos are auto-cropped to a passport shape.
        Only students in your scope are matched; a file that matches no admission
        number is skipped and listed.
      </p>
      <input type="file" accept=".zip,application/zip" className="form-control"
             onChange={(e) => { setFile(e.target.files[0] || null); setResult(null); setError(''); }} />
      {result && (
        <div className="alert alert-success" role="status" style={{ marginTop: 12 }}>
          <div><strong>{result.matched}</strong> photo(s) imported
            {result.skipped ? `, ${result.skipped} duplicate(s) skipped` : ''}.</div>
          {result.unmatched_count > 0 && (
            <details style={{ marginTop: 6 }}>
              <summary style={{ cursor: 'pointer' }}>{result.unmatched_count} file(s) matched no admission number</summary>
              <ul className="text-xs" style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                {(result.unmatched || []).map((n) => <li key={n}>{n}</li>)}
              </ul>
            </details>
          )}
          {(result.errors || []).length > 0 && (
            <ul className="text-xs" style={{ margin: '6px 0 0', paddingLeft: 18, color: '#b91c1c' }}>
              {result.errors.map((n) => <li key={n}>{n}</li>)}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
}
