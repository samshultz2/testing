import React, { useState } from 'react';
import { submitJson, postFile, useSave } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty, FileUpload } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Index, Branches, Backup, Audit, School, Academic, Grades, Traits, Assessments, TimetableSlots } from './Hub';

// Small helpers ---------------------------------------------------------------
function Actions({ children }) {
  return <div className="page-header-actions">{children}</div>;
}

// ---- AI Vision OCR settings -------------------------------------------------
function Ocr({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [f, setF] = useState({
    enabled: !!d.enabled, model: d.model || 'claude-haiku-4-5', api_key: '', clear_key: false,
    engine: d.engine || 'auto',
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const toggle = (k) => (e) => setF({ ...f, [k]: e.target.checked });
  const submit = (e) => {
    e.preventDefault();
    save(d.submit_url, {
      enabled: f.enabled ? '1' : '0', model: f.model, engine: f.engine,
      api_key: f.clear_key ? '' : f.api_key, clear_key: f.clear_key ? '1' : '0',
    }, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>AI Vision OCR</h1></div>

      {/* Live status */}
      <div className="card mb-3"><div className="card-body">
        {d.active
          ? <p style={{ margin: 0, color: '#137333', fontWeight: 600 }}><i aria-hidden="true" className="fas fa-circle-check" /> Active — WAEC/JAMB scans will use Claude vision (with Tesseract as fallback).</p>
          : <p style={{ margin: 0, color: '#b06000', fontWeight: 600 }}><i aria-hidden="true" className="fas fa-circle-info" /> Not active — scans use the free Tesseract engine.</p>}
        {!d.anthropic_installed && (
          <p className="text-muted" style={{ marginTop: '.4rem', fontSize: 'var(--text-sm)' }}>
            The <code>anthropic</code> library isn't installed on the server. Run <code>pip install anthropic</code> and restart, then it can be turned on here.
          </p>)}
        <p className="text-muted" style={{ marginTop: '.4rem', fontSize: 'var(--text-sm)' }}>
          Reads result images with Claude (more accurate than Tesseract, handles handwriting). It bills your Anthropic account — about $0.003 per image on Haiku. Sign up at <strong>console.anthropic.com</strong> → Billing → API Keys.
        </p>
        <p style={{ marginTop: '.3rem', fontSize: 'var(--text-sm)', color: '#b06000' }}>
          <i aria-hidden="true" className="fas fa-circle-info" /> A Claude <strong>Pro/Max subscription does NOT include API access</strong> — the API is billed separately. If scans fail with "credit balance too low", add API credit at console.anthropic.com → Billing, or use Tesseract.
        </p>
      </div></div>

      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-group"><label className="form-label">Score-sheet OCR engine</label>
            <select className="form-control" value={f.engine} onChange={set('engine')}>
              <option value="auto">Auto — Claude if configured, else Tesseract</option>
              <option value="claude">Claude vision (handwriting; needs API key)</option>
              <option value="tesseract">Tesseract (printed text; free, on-server)</option>
            </select>
            <span className="form-hint d-block">The chosen engine is tried first; the others act as fallback. Availability on this server:</span>
            <ul style={{ margin: '.35rem 0 0', paddingLeft: '1.1rem', fontSize: 'var(--text-sm)' }}>
              {(d.engine_status || []).map((s) => (
                <li key={s.id} style={{ color: s.available ? '#137333' : 'var(--text-muted)' }}>
                  <i aria-hidden="true" className={'fas ' + (s.available ? 'fa-circle-check' : 'fa-circle-xmark')} /> {s.label}
                  {!s.available && s.hint ? <span className="text-muted"> — {s.hint}</span> : null}
                </li>
              ))}
            </ul>
          </div>

          <div className="form-group">
            <label className="form-check" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
              <input type="checkbox" checked={f.enabled} onChange={toggle('enabled')} />
              <span>Use Claude Vision OCR for WAEC/JAMB scans</span>
            </label>
            <span className="form-hint d-block">When off, scans use Tesseract only (free).</span>
          </div>

          <div className="form-group"><label className="form-label">Model</label>
            <select className="form-control" value={f.model} onChange={set('model')}>
              {(d.models || ['claude-haiku-4-5']).map((m) => (
                <option key={m} value={m}>{m}{m === 'claude-haiku-4-5' ? ' — cheapest, recommended' : ''}</option>
              ))}
            </select>
            <span className="form-hint d-block">Haiku is plenty for reading result slips and ~5× cheaper than Opus.</span></div>

          <div className="form-group"><label className="form-label">Anthropic API key</label>
            <input type="password" className="form-control" autoComplete="off" value={f.api_key}
                   onChange={set('api_key')} disabled={f.clear_key}
                   placeholder={d.has_key ? `Saved${d.key_masked ? ': ' + d.key_masked : ''} (${d.key_source === 'env' ? 'from environment' : 'in settings'}) — leave blank to keep` : 'sk-ant-…'} />
            <span className="form-hint d-block">Stored encrypted at rest. The full key is never shown again after saving.</span>
            {d.has_key && d.key_source === 'settings' && (
              <label className="form-check" style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginTop: '.4rem' }}>
                <input type="checkbox" checked={f.clear_key} onChange={toggle('clear_key')} />
                <span>Remove the saved key</span>
              </label>)}
          </div>

          <Actions>
            {canWrite(d, 'ocr_manage') && <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save</button>}
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
}


const SCREENS = {
  index: Index, school: School, academic: Academic, grades: Grades, traits: Traits,
  assessments: Assessments, timetable_slots: TimetableSlots, backup: Backup,
  branches: Branches,
  audit: Audit, ocr: Ocr,
};

export default function SettingsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
