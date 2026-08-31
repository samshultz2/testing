import React, { useState } from 'react';
import { postForm } from '../lib/forms';
import { Modal, Button } from '../components/ui';

// Compose a message to the selected students' parents. Builds a DRAFT campaign
// in Communication (never auto-sends) and links there to review + send.
export default function BulkMessageModal({ count, selectedIds, messageUrl, onClose, onDone }) {
  const [title, setTitle] = useState('');
  const [channel, setChannel] = useState('SMS');
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    if (!body.trim()) { setErr('Enter a message.'); return; }
    setBusy(true); setErr(null);
    try {
      const res = await postForm(messageUrl, { title, channel, body, student_ids: selectedIds });
      const j = (res.headers.get('content-type') || '').includes('json') ? await res.json() : {};
      if (!res.ok || j.error) { setErr(j.error || 'Could not draft the message.'); setBusy(false); return; }
      onDone(j);
    } catch (e2) { setErr(e2.message || 'Could not draft the message.'); setBusy(false); }
  };

  return (
    <Modal title={`Message parents of ${count} student(s)`} icon="fa-comment-dots" size="md" onClose={onClose}
           footer={<>
             <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
             <Button variant="primary" onClick={submit} disabled={busy}>
               <i aria-hidden="true" className="fas fa-paper-plane" /> {busy ? 'Drafting…' : 'Draft message'}
             </Button>
           </>}>
      {err && <div className="alert alert-danger" role="alert">{err}</div>}
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>
        <i className="fas fa-info-circle" aria-hidden="true" /> This drafts a campaign in Communication —
        you'll review the recipient list and send it there. Use <code>{'{parent}'}</code>,
        {' '}<code>{'{student}'}</code> and <code>{'{school}'}</code> for personalisation.
      </p>
      <div className="form-group">
        <label className="form-label">Title (optional)</label>
        <input className="form-control" type="text" value={title} maxLength={120}
               placeholder="e.g. PTA meeting" onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div className="form-group">
        <label className="form-label">Channel</label>
        <select className="form-control" value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="SMS">SMS</option>
          <option value="WhatsApp">WhatsApp</option>
          <option value="Email">Email</option>
        </select>
      </div>
      <div className="form-group">
        <label className="form-label">Message</label>
        <textarea className="form-control" rows={5} value={body} required
                  placeholder="Dear {parent}, …" onChange={(e) => setBody(e.target.value)} />
      </div>
    </Modal>
  );
}
