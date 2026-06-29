import React, { useState } from 'react';
import { apiPost } from '../lib/api';
import { Modal, Button } from '../components/ui';

// In-SPA dashboard customisation: toggle which widgets show. Widgets the user
// has no module access to are listed but disabled (parity with the classic
// page, minus the dead toggles). Saving reloads so the page re-hydrates.
export default function Customize({ catalog, onSaved, onClose }) {
  const initial = {};
  (catalog || []).forEach((w) => { initial[w.key] = !!w.enabled; });
  const [checked, setChecked] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  // Preserve registry order, grouped by category.
  const groups = [];
  (catalog || []).forEach((w) => {
    let g = groups.find((x) => x.name === w.group);
    if (!g) { g = { name: w.group, items: [] }; groups.push(g); }
    g.items.push(w);
  });

  const toggle = (k) => setChecked((c) => ({ ...c, [k]: !c[k] }));

  const save = async () => {
    setBusy(true); setErr(null);
    const widgets = (catalog || []).filter((w) => w.permitted && checked[w.key]).map((w) => w.key);
    try {
      await apiPost('/api/dashboard/widgets', { widgets });
      if (onSaved) await onSaved();   // refresh data in place — no full reload
      onClose();
    } catch (e) {
      setErr(e.message || 'Could not save'); setBusy(false);
    }
  };

  return (
    <Modal title="Customize dashboard" icon="fa-sliders" size="md" onClose={onClose}
           footer={<>
             <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
             <Button variant="primary" onClick={save} disabled={busy}>
               <i className="fas fa-save" aria-hidden="true" /> {busy ? 'Saving…' : 'Save dashboard'}
             </Button>
           </>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>Choose which widgets appear on your dashboard.</p>
      {groups.map((g) => (
        <div key={g.name} style={{ marginBottom: '1rem' }}>
          <h4 style={{ margin: '0 0 .5rem', fontSize: '.85rem', color: 'var(--text-secondary, var(--text-secondary))' }}>{g.name}</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: '.4rem' }}>
            {g.items.map((w) => (
              <label key={w.key}
                     title={w.permitted ? '' : 'You don’t have access to this module'}
                     style={{ display: 'flex', gap: '.6rem', alignItems: 'center', padding: '.5rem',
                              border: '1px solid var(--border-color, var(--border-color))', borderRadius: 8,
                              opacity: w.permitted ? 1 : .5, cursor: w.permitted ? 'pointer' : 'not-allowed' }}>
                <input type="checkbox" disabled={!w.permitted}
                       checked={!!checked[w.key]} onChange={() => toggle(w.key)} />
                <span>{w.label}</span>
                {!w.permitted && <i className="fas fa-lock text-muted" style={{ marginLeft: 'auto', fontSize: 12 }} aria-hidden="true" />}
              </label>
            ))}
          </div>
        </div>
      ))}
      {err && <div className="alert alert-danger" role="alert" style={{ marginTop: 8 }}>{err}</div>}
    </Modal>
  );
}
