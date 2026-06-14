import React, { useState } from 'react';
import { apiPost } from '../lib/api';

// In-SPA dashboard customisation: toggle which widgets show. Widgets the user
// has no module access to are listed but disabled (parity with the classic
// page, minus the dead toggles). Saving reloads so the page re-hydrates.
export default function Customize({ catalog, onClose }) {
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
      window.location.reload();
    } catch (e) {
      setErr(e.message || 'Could not save'); setBusy(false);
    }
  };

  return (
    <div role="dialog" aria-modal="true" aria-label="Customize dashboard"
         onClick={onClose}
         style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
                  display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '5vh 1rem', overflowY: 'auto' }}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ background: 'var(--bg-card, #fff)', borderRadius: 12, width: '100%', maxWidth: 560,
                    boxShadow: '0 20px 60px rgba(0,0,0,.3)', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '1rem 1.25rem', borderBottom: '1px solid var(--border-color, #e5e7eb)' }}>
          <h3 style={{ margin: 0, fontSize: '1.05rem' }}><i className="fas fa-sliders" aria-hidden="true" /> Customize dashboard</h3>
          <button type="button" aria-label="Close" onClick={onClose}
                  style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', color: 'inherit', opacity: .6 }}>×</button>
        </div>

        <div style={{ padding: '1rem 1.25rem', maxHeight: '60vh', overflowY: 'auto' }}>
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>Choose which widgets appear on your dashboard.</p>
          {groups.map((g) => (
            <div key={g.name} style={{ marginBottom: '1rem' }}>
              <h4 style={{ margin: '0 0 .5rem', fontSize: '.85rem', color: 'var(--text-secondary, #475569)' }}>{g.name}</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: '.4rem' }}>
                {g.items.map((w) => (
                  <label key={w.key}
                         title={w.permitted ? '' : 'You don’t have access to this module'}
                         style={{ display: 'flex', gap: '.6rem', alignItems: 'center', padding: '.5rem',
                                  border: '1px solid var(--border-color, #e5e7eb)', borderRadius: 8,
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
          {err && <div className="alert alert-danger" style={{ marginTop: 8 }}>{err}</div>}
        </div>

        <div style={{ display: 'flex', gap: '.6rem', padding: '1rem 1.25rem', borderTop: '1px solid var(--border-color, #e5e7eb)' }}>
          <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>
            <i className="fas fa-save" aria-hidden="true" /> {busy ? 'Saving…' : 'Save dashboard'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
