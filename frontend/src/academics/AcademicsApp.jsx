import React, { useState, useMemo, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';
import { canWrite } from '../lib/perms';
import TermSetup from './TermSetup';

// ---- Sessions list ---------------------------------------------------------
function Sessions({ d, notify }) {
  const nav = useNav();
  const activate = async (url) => {
    const r = await submitJson(url, {});
    // Activating a session switches the whole platform's active session/term, so
    // force a full reload (like the "view session" dropdown does) — every cached
    // SPA section and the time-travel bar re-render against the new session.
    if (r.ok) window.location.href = r.redirect || window.location.href;
    else notify('error', r.error || 'Failed.');
  };
  return (
    <>
      <div className="page-header"><h1>Academic Sessions</h1>
        <div className="page-header-actions">{canWrite(d, 'structure_create') && <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}</div>
      </div>
      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.sessions.length ? (
          <div className="data-cards" style={{ padding: '1rem' }}>{d.sessions.map((s) => (
            <div className="data-card" key={s.id}>
              <div className="data-card-header"><div className="data-card-title">{s.name}</div>{s.is_active && <span className="badge badge-success">Active</span>}</div>
              <div className="data-card-row"><span className="data-card-label">Start</span><span>{s.start_date || '-'}</span></div>
              <div className="data-card-row"><span className="data-card-label">End</span><span>{s.end_date || '-'}</span></div>
              <div className="data-card-row"><span className="data-card-label">Terms</span><span>{s.terms}</span></div>
              {canWrite(d, 'structure_edit') && <div className="data-card-actions">
                <a href={s.edit_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-edit" /> Edit</a>
                {!s.is_active && <button type="button" className="btn btn-success btn-sm w-100" style={{ flex: 1 }} onClick={() => activate(s.activate_url)}><i aria-hidden="true" className="fas fa-check" /> Activate</button>}
              </div>}
            </div>))}</div>
        ) : <Empty icon="fa-calendar" title="No Sessions"><p>Create your first academic session</p></Empty>}
      </div></div>
    </>
  );
}

// ---- Session form (add / edit) --------------------------------------------
function SessionForm({ d, notify }) {
  const nav = useNav();
  const init = d.session || { name: '', start_date: '', end_date: '' };
  const [f, setF] = useState({ name: init.name, start_date: init.start_date, end_date: init.end_date, is_active: false });
  const [busy, setBusy] = useState(false);
  const isEdit = d.page === 'edit_session';
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify('error', 'Session name is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, is_active: f.is_active ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>{isEdit ? `Edit Session: ${d.session.name}` : 'Add Session'}</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Session Name <span className="required">*</span></label>
          <input type="text" className="form-control" required placeholder="e.g., 2024/2025" value={f.name} onChange={(e) => set('name', e.target.value)} /></div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Start Date</label><input type="date" className="form-control" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">End Date</label><input type="date" className="form-control" value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
        </div>
        {!isEdit && <div className="form-check mb-3"><input type="checkbox" id="is_active" checked={f.is_active} onChange={(e) => set('is_active', e.target.checked)} /><label htmlFor="is_active"> Set as Active</label></div>}
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> {isEdit ? 'Save Changes' : 'Create'}</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Terms list ------------------------------------------------------------
function Terms({ d, notify }) {
  const nav = useNav();
  const activate = async (url) => {
    const r = await submitJson(url, {});
    // Full reload so the new active term propagates across the whole platform
    // (mirrors the "view session" dropdown), not just this section.
    if (r.ok) window.location.href = r.redirect || window.location.href;
    else notify('error', r.error || 'Failed.');
  };
  return (
    <>
      <div className="page-header"><h1>Terms</h1>
        <div className="page-header-actions">
          <a href={d.urls.setup} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-list-check" /> Term setup</a>
          {canWrite(d, 'structure_create') && <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}
        </div>
      </div>
      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.terms.length ? (
          <div className="data-cards" style={{ padding: '1rem' }}>{d.terms.map((t) => (
            <div className="data-card" key={t.id}>
              <div className="data-card-header"><div className="data-card-title">{t.name}</div>{t.is_active && <span className="badge badge-success">Active</span>}</div>
              <div className="data-card-row"><span className="data-card-label">Session</span><span>{t.session}</span></div>
              <div className="data-card-row"><span className="data-card-label">Start</span><span>{t.start_date || '-'}</span></div>
              <div className="data-card-row"><span className="data-card-label">End</span><span>{t.end_date || '-'}</span></div>
              <div className="data-card-row"><span className="data-card-label">Weeks</span><span>{t.weeks}</span></div>
              <div className="data-card-actions">
                <a href={t.view_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-eye" /> View</a>
                <a href={t.edit_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-edit" /> Edit</a>
                {!t.is_active && <button type="button" className="btn btn-success btn-sm w-100" style={{ flex: 1 }} onClick={() => activate(t.activate_url)}><i aria-hidden="true" className="fas fa-check" /></button>}
              </div>
            </div>))}</div>
        ) : <Empty icon="fa-clock" title="No Terms"><p>Create terms for your sessions</p></Empty>}
      </div></div>
    </>
  );
}

// ---- Add term --------------------------------------------------------------
function AddTerm({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ session_id: '', term_number: '', start_date: '', end_date: '', is_active: false });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.session_id || !f.term_number) { notify('error', 'Session and term number are required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, is_active: f.is_active ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Add Term</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Session <span className="required">*</span></label>
          <select className="form-control" required value={f.session_id} onChange={(e) => set('session_id', e.target.value)}>
            <option value="">Select</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Term <span className="required">*</span></label>
          <select className="form-control" required value={f.term_number} onChange={(e) => set('term_number', e.target.value)}>
            <option value="">Select</option><option value="1">First Term</option><option value="2">Second Term</option><option value="3">Third Term</option></select></div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Start Date</label><input type="date" className="form-control" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">End Date</label><input type="date" className="form-control" value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
        </div>
        <div className="form-check mb-3"><input type="checkbox" id="is_active" checked={f.is_active} onChange={(e) => set('is_active', e.target.checked)} /><label htmlFor="is_active"> Set as Active</label></div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Create</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Edit term -------------------------------------------------------------
function EditTerm({ d, notify }) {
  const nav = useNav();
  const t = d.term;
  const [f, setF] = useState({ start_date: t.start_date, end_date: t.end_date, regenerate_weeks: false });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, regenerate_weeks: f.regenerate_weeks ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Edit Term: {t.full_name}</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Session</label><input type="text" className="form-control" value={t.session} disabled /></div>
        <div className="form-group"><label className="form-label">Term</label><input type="text" className="form-control" value={t.name} disabled /></div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Start Date</label><input type="date" className="form-control" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">End Date</label><input type="date" className="form-control" value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
        </div>
        <div className="form-check mb-3"><input type="checkbox" id="regen" checked={f.regenerate_weeks} onChange={(e) => set('regenerate_weeks', e.target.checked)} />
          <label htmlFor="regen"> Regenerate weeks based on new dates</label>
          <small className="text-muted d-block">Warning: This will delete existing weeks and attendance records for this term</small></div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Changes</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Term setup checklist --------------------------------------------------
// ---- View term (weeks + holidays) ------------------------------------------
function ViewTerm({ d, notify }) {
  const nav = useNav();
  const t = d.term;
  const [hf, setHf] = useState({ date: '', end_date: '', holiday_type: 'Public Holiday', reason: '' });
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const addHoliday = async (e) => {
    e.preventDefault();
    if (!hf.date || !hf.reason.trim()) { notify('error', 'Date and reason are required.'); return; }
    const r = await submitJson(d.urls.add_holiday, hf);
    if (r.ok) { setHf({ date: '', end_date: '', holiday_type: 'Public Holiday', reason: '' }); notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Could not add.');
  };
  return (
    <>
      <div className="page-header">
        <div><h1>{t.full_name}</h1>{t.is_active && <span className="badge badge-success">Active</span>}</div>
        <div className="page-header-actions">{canWrite(d, 'structure_edit') && <a href={d.urls.edit} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-edit" /> Edit Dates</a>}</div>
      </div>
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Start Date</label><div className="form-control" style={{ background: 'var(--bg-secondary)' }}>{t.start_date || 'Not set'}</div></div>
        <div className="form-group"><label className="form-label">End Date</label><div className="form-control" style={{ background: 'var(--bg-secondary)' }}>{t.end_date || 'Not set'}</div></div>
      </div></div></div>

      <div className="card mb-3">
        <div className="card-header"><h3>Weeks ({d.weeks.length})</h3>
          {(canWrite(d, 'structure_create') || canWrite(d, 'structure_bulk')) && <div style={{ display: 'flex', gap: '0.5rem' }}>
            {canWrite(d, 'structure_create') && <button type="button" className="btn btn-primary btn-sm" onClick={() => act(d.urls.add_week, {})}><i aria-hidden="true" className="fas fa-plus" /> Add Week</button>}
            {canWrite(d, 'structure_bulk') && d.weeks.length === 0 && t.has_start && <button type="button" className="btn btn-secondary btn-sm" onClick={() => act(d.urls.generate_weeks, {})}><i aria-hidden="true" className="fas fa-sync" /> Generate All</button>}
          </div>}
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.weeks.length ? (
            <div className="data-cards" style={{ padding: '1rem' }}>{d.weeks.map((w) => (
              <div className="data-card" key={w.id}>
                <div className="data-card-header"><div className="data-card-title">Week {w.week_number}</div></div>
                <div className="data-card-row"><span className="data-card-label">Start</span><span>{w.start_date}</span></div>
                <div className="data-card-row"><span className="data-card-label">End</span><span>{w.end_date}</span></div>
                {canWrite(d, 'structure_delete') && w.is_last && <div className="data-card-actions"><button type="button" className="btn btn-danger btn-sm w-100" onClick={() => act(w.delete_url, {}, `Delete Week ${w.week_number}? This will also delete attendance records for this week.`)}><i aria-hidden="true" className="fas fa-times" /> Remove</button></div>}
              </div>))}</div>
          ) : <Empty icon="fa-calendar" title=""><p>No weeks added yet. Click "Add Week" to add Week 1.</p></Empty>}
        </div>
      </div>

      <div className="card"><div className="card-header"><h3>Holidays ({d.holidays.length})</h3></div>
        <div className="card-body">
          {canWrite(d, 'holidays_create') && <form onSubmit={addHoliday} className="filter-form mb-3">
            <div className="form-group"><label className="form-label">From</label><input type="date" className="form-control" required value={hf.date} onChange={(e) => setHf((s) => ({ ...s, date: e.target.value }))} /></div>
            <div className="form-group"><label className="form-label">To <span className="text-muted">(optional)</span></label><input type="date" className="form-control" title="Leave blank for a single day" value={hf.end_date} onChange={(e) => setHf((s) => ({ ...s, end_date: e.target.value }))} /></div>
            <div className="form-group"><label className="form-label">Type</label>
              <select className="form-control" value={hf.holiday_type} onChange={(e) => setHf((s) => ({ ...s, holiday_type: e.target.value }))}>
                <option>Public Holiday</option><option>Mid-term Break</option><option>Other</option></select></div>
            <div className="form-group"><label className="form-label">Reason</label><input type="text" className="form-control" placeholder="e.g., Eid el-Kabir" required value={hf.reason} onChange={(e) => setHf((s) => ({ ...s, reason: e.target.value }))} /></div>
            <div className="filter-actions"><button type="submit" className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
          </form>}
          {canWrite(d, 'holidays_create') && <p className="text-muted text-sm" style={{ margin: '-0.5rem 0 1rem' }}>For a multi-day break, set From and To — each weekday in the range is marked at once. Weekends are skipped automatically.</p>}
          {d.holidays.length > 0 && (
            <div className="data-cards">{d.holidays.map((h) => (
              <div className="data-card" key={h.id}>
                <div className="data-card-header"><div className="data-card-title">{h.date}</div>{h.holiday_type && <span className="badge badge-info">{h.holiday_type}</span>}</div>
                <div className="data-card-row"><span className="data-card-label">Reason</span><span>{h.reason}</span></div>
                {canWrite(d, 'holidays_delete') && <div className="data-card-actions"><button type="button" className="btn btn-danger btn-sm w-100" onClick={() => act(h.delete_url, {})}><i aria-hidden="true" className="fas fa-times" /> Remove</button></div>}
              </div>))}</div>
          )}
        </div></div>
    </>
  );
}

// ---- Classes ---------------------------------------------------------------
function Classes({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ name: '', level: '', description: '' });
  const add = async (e) => {
    e.preventDefault();
    if (!f.name.trim() || !f.level) { notify('error', 'Class name and level are required.'); return; }
    const r = await submitJson(d.add_url, f);
    if (r.ok) { setF({ name: '', level: '', description: '' }); notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not add.');
  };
  const del = async (url, name) => {
    if (!await confirm(`Delete ${name}? Existing rosters/timetables keep it, but it won't be offered for new assignments.`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <div className="page-header"><h1>School Classes</h1></div>
      {canWrite(d, 'structure_create') && <div className="card mb-3"><div className="card-header"><h3>Add New Class</h3></div>
        <div className="card-body"><form onSubmit={add}>
          <div className="form-group"><label className="form-label">Class Name</label><input type="text" className="form-control" placeholder="e.g., JSS1" required value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
          <div className="form-group"><label className="form-label">Level</label><input type="number" className="form-control" min="1" max="20" required placeholder="Order number" value={f.level} onChange={(e) => setF((s) => ({ ...s, level: e.target.value }))} /></div>
          <div className="form-group"><label className="form-label">Description</label><input type="text" className="form-control" placeholder="Optional" value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Class</button>
        </form></div></div>}
      <div className="card"><div className="card-header"><h3>Existing Classes</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.classes.length ? (
            <div className="data-cards" style={{ padding: '1rem' }}>{d.classes.map((c) => (
              <div className="data-card" key={c.id}>
                <div className="data-card-header"><div className="data-card-title">{c.name}</div><span className="badge badge-info">Level {c.level}</span></div>
                <div className="data-card-row"><span className="data-card-label">Description</span><span>{c.description || '-'}</span></div>
                {(canWrite(d, 'structure_edit') || canWrite(d, 'structure_delete')) && <div className="data-card-actions">
                  {canWrite(d, 'structure_edit') && <a href={c.edit_url} className="btn btn-secondary btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>}
                  {canWrite(d, 'structure_delete') && <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(c.delete_url, c.name)}><i aria-hidden="true" className="fas fa-trash" /></button>}
                </div>}
              </div>))}</div>
          ) : <Empty icon="fa-school" title=""><p>No classes added yet</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Edit class --------------------------------------------------------
function ClassForm({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ name: d.school_class.name, level: d.school_class.level, description: d.school_class.description });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim() || !f.level) { notify('error', 'Class name and level are required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Edit Class</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Class Name <span className="required">*</span></label>
          <input type="text" className="form-control" placeholder="e.g., JSS1" required value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
        <div className="form-group"><label className="form-label">Level <span className="required">*</span></label>
          <input type="number" className="form-control" min="1" max="20" required placeholder="Order number" value={f.level} onChange={(e) => setF((s) => ({ ...s, level: e.target.value }))} /></div>
        <div className="form-group"><label className="form-label">Description</label>
          <input type="text" className="form-control" placeholder="Optional" value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Arms ------------------------------------------------------------------
function Arms({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ name: '', description: '' });
  const add = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify('error', 'Arm name is required.'); return; }
    const r = await submitJson(d.add_url, f);
    if (r.ok) { setF({ name: '', description: '' }); notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not add.');
  };
  const del = async (url, name) => {
    if (!await confirm(`Delete ${name}? Existing rosters/timetables keep it, but it won't be offered for new assignments.`)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <div className="page-header"><h1>Class Arms</h1></div>
      {canWrite(d, 'structure_create') && <div className="card mb-3"><div className="card-header"><h3>Add New Arm</h3></div>
        <div className="card-body"><form onSubmit={add}>
          <div className="form-group"><label className="form-label">Arm Name</label><input type="text" className="form-control" placeholder="e.g., Rose, Lily" required value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
          <div className="form-group"><label className="form-label">Description</label><input type="text" className="form-control" placeholder="Optional" value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Arm</button>
        </form></div></div>}
      <div className="card"><div className="card-header"><h3>Existing Arms</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.arms.length ? (
            <div className="data-cards" style={{ padding: '1rem' }}>{d.arms.map((a) => (
              <div className="data-card" key={a.id}>
                <div className="data-card-header"><div className="data-card-title">{a.name}</div></div>
                <div className="data-card-row"><span className="data-card-label">Description</span><span>{a.description || '-'}</span></div>
                {(canWrite(d, 'structure_edit') || canWrite(d, 'structure_delete')) && <div className="data-card-actions">
                  {canWrite(d, 'structure_edit') && <a href={a.edit_url} className="btn btn-secondary btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>}
                  {canWrite(d, 'structure_delete') && <button type="button" className="btn btn-danger btn-sm w-100" style={{ flex: 1 }} onClick={() => del(a.delete_url, a.name)}><i aria-hidden="true" className="fas fa-trash" /></button>}
                </div>}
              </div>))}</div>
          ) : <Empty icon="fa-layer-group" title=""><p>No arms added yet</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Edit arm ----------------------------------------------------------
function ArmForm({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ name: d.arm.name, description: d.arm.description });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify('error', 'Arm name is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Edit Arm</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Arm Name <span className="required">*</span></label>
          <input type="text" className="form-control" placeholder="e.g., Rose, Lily" required value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
        <div className="form-group"><label className="form-label">Description</label>
          <input type="text" className="form-control" placeholder="Optional" value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Shared bits for the class setup / roster screens -----------------------
function useMedia(query) {
  const get = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false);
  const [m, setM] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const on = () => setM(mq.matches);
    on();
    if (mq.addEventListener) mq.addEventListener('change', on); else mq.addListener(on);
    return () => { if (mq.removeEventListener) mq.removeEventListener('change', on); else mq.removeListener(on); };
  }, [query]);
  return m;
}

// Bottom sheet on phones, centred dialog on laptops; portalled above the bottom nav.
function Sheet({ title, onClose, children, wide }) {
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', esc);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', esc); document.body.style.overflow = prev; };
  }, []);
  return createPortal(
    <div className="ac-sheet-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={'ac-sheet' + (wide ? ' wide' : '')} role="dialog" aria-modal="true" aria-label={title}>
        <div className="ac-grip" aria-hidden="true" />
        <div className="ac-sheet-head"><strong>{title}</strong>
          <button type="button" className="ac-x" onClick={onClose} aria-label="Close"><i aria-hidden="true" className="fas fa-xmark" /></button></div>
        {children}
      </div>
    </div>, document.body);
}

const HUES = ['#0f766e', '#2563eb', '#7c3aed', '#c2410c', '#be185d', '#0891b2', '#4d7c0f', '#b45309'];
const hueFor = (t) => { let h = 0; for (let i = 0; i < (t || '').length; i++) h = (h * 31 + t.charCodeAt(i)) >>> 0; return HUES[h % HUES.length]; };

// Boys / girls split bar.
function GenderBar({ boys, girls, total }) {
  const t = total || (boys + girls) || 0;
  if (!t) return <div className="ac-gbar empty" />;
  return (
    <div className="ac-gwrap">
      <div className="ac-gbar" role="img" aria-label={`${boys} boys, ${girls} girls`}>
        <span className="b" style={{ width: (boys / t * 100) + '%' }} />
        <span className="g" style={{ width: (girls / t * 100) + '%' }} />
      </div>
      <div className="ac-glegend"><span><i className="b" />{boys} boys</span><span><i className="g" />{girls} girls</span></div>
    </div>
  );
}

// ---- Assignments (class setup): one tab per class, its arms inside ---------
function Assignments({ d, notify }) {
  const nav = useNav();
  const phone = useMedia('(max-width: 759px)');
  const usesArms = d.uses_arms;
  const byClass = useMemo(() => {
    const m = {};
    (d.assignments || []).forEach((a) => { (m[a.class_id] = m[a.class_id] || []).push(a); });
    Object.values(m).forEach((l) => l.sort((x, y) => (x.arm || '').localeCompare(y.arm || '')));
    return m;
  }, [d.assignments]);
  const classes = d.classes || [];
  const firstSet = classes.find((c) => byClass[c.id]);
  const [tab, setTabState] = useState(() => {
    const h = (window.location.hash || '').match(/^#class-(\d+)$/);
    const id = h ? Number(h[1]) : null;
    if (id && classes.some((c) => c.id === id)) return id;
    return (firstSet || classes[0] || {}).id;
  });
  const setTab = (id) => { setTabState(id); try { window.history.replaceState(null, '', '#class-' + id); } catch (e) { /* ignore */ } };
  const tabsRef = React.useRef(null);
  useEffect(() => {
    const el = tabsRef.current && tabsRef.current.querySelector('.on');
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [tab]);
  const [adding, setAdding] = useState(false);
  const cls = classes.find((c) => c.id === tab);
  const arms = byClass[tab] || [];
  const canAdd = canWrite(d, 'structure_create');
  const totals = (d.assignments || []).reduce((t, a) => ({ s: t.s + a.students, b: t.b + a.boys, g: t.g + a.girls,
    noT: t.noT + (a.form_teacher ? 0 : 1) }), { s: 0, b: 0, g: 0, noT: 0 });
  const classTotal = arms.reduce((t, a) => ({ s: t.s + a.students, b: t.b + a.boys, g: t.g + a.girls }), { s: 0, b: 0, g: 0 });
  const missing = classes.filter((c) => !byClass[c.id]).length;

  const toggleArms = async (on) => {
    const r = await submitJson(d.toggle_url, { uses_arms: on ? '1' : '0' });
    if (r.ok) { notify('success', on ? 'Arms enabled.' : 'Arms turned off — classes won\'t need arms.'); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const setupAll = async () => {
    const r = await submitJson(d.setup_url, { term_id: d.term_id });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not set up.');
  };
  const addClassNoArms = async () => {
    const r = await submitJson(d.add_url, { class_id: tab, form_teacher: '', arm_ids: [], term_id: d.term_id });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not add.');
  };

  return (
    <div className="ac">
      <header className="ac-head">
        <div className="ac-head-t">
          <span className="ac-kicker">Class setup</span>
          <h1>{d.selected_term ? d.selected_term.name : 'Choose a term'}</h1>
        </div>
        <div className="ac-head-acts">
          <label className="ac-select"><i aria-hidden="true" className="fas fa-calendar" />
            <select value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value })} aria-label="Term">
              <option value="">Select term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select>
          </label>
          {canWrite(d, 'structure_edit') && (
            <label className="ac-switch" title="Does the school stream classes into arms (e.g. SSS1 A, SSS1 B)?">
              <input type="checkbox" checked={usesArms} onChange={(e) => toggleArms(e.target.checked)} />
              <span className="ac-switch-ui" aria-hidden="true" /><span>Uses arms</span>
            </label>
          )}
        </div>
      </header>

      {!d.selected_term ? (
        <Empty icon="fa-calendar" title="Pick a term"><p>Choose the term whose classes you want to set up.</p></Empty>
      ) : (<>
        <div className="ac-stats">
          <div><span>Classes set up</span><b>{classes.length - missing}<small>/{classes.length}</small></b></div>
          {usesArms && <div><span>Arms</span><b>{(d.assignments || []).length}</b></div>}
          <div><span>Students</span><b>{totals.s}</b></div>
          <div className={totals.noT ? 'warn' : ''}><span>No class teacher</span><b>{totals.noT}</b></div>
        </div>

        {!usesArms && missing > 0 && canWrite(d, 'structure_bulk') && (
          <div className="ac-callout">
            <i aria-hidden="true" className="fas fa-wand-magic-sparkles" />
            <span><strong>{missing} class{missing === 1 ? '' : 'es'} not set up for this term.</strong> Add them all at once to start enrolling.</span>
            <button type="button" className="btn btn-primary btn-sm" onClick={setupAll}>Set up all</button>
          </div>
        )}

        <nav className="ac-tabs" ref={tabsRef} role="tablist" aria-label="Classes">
          {classes.map((c) => {
            const l = byClass[c.id] || [];
            const n = l.reduce((t, a) => t + a.students, 0);
            return (
              <button key={c.id} type="button" role="tab" aria-selected={tab === c.id}
                      className={(tab === c.id ? 'on' : '') + (l.length ? '' : ' unset')} onClick={() => setTab(c.id)}>
                <strong>{c.name}</strong>
                <small>{l.length ? (usesArms ? `${l.length} arm${l.length === 1 ? '' : 's'} · ${n}` : `${n} students`) : 'Not set up'}</small>
              </button>
            );
          })}
        </nav>

        {cls && (
          <section className="ac-panel" role="tabpanel">
            <div className="ac-panel-head">
              <div>
                <h2>{cls.name}</h2>
                <p>{arms.length
                  ? <>{usesArms ? `${arms.length} arm${arms.length === 1 ? '' : 's'} · ` : ''}{classTotal.s} student{classTotal.s === 1 ? '' : 's'}</>
                  : 'Not set up for this term yet'}</p>
              </div>
              {arms.length > 0 && <div className="ac-panel-g"><GenderBar boys={classTotal.b} girls={classTotal.g} total={classTotal.s} /></div>}
              {canAdd && usesArms && <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
                <i aria-hidden="true" className="fas fa-plus" /> {phone ? 'Arm' : 'Add arms'}</button>}
            </div>

            {arms.length ? (
              <div className="ac-arms">
                {arms.map((a) => <ArmCard key={a.id} a={a} usesArms={usesArms} notify={notify} canEdit={canWrite(d, 'structure_edit')} />)}
              </div>
            ) : (
              <div className="ac-empty">
                <span className="ac-empty-ic"><i aria-hidden="true" className="fas fa-chalkboard" /></span>
                <p><strong>{cls.name}</strong> has no {usesArms ? 'arms' : 'class'} set up for {d.selected_term.name}.</p>
                {canAdd && (usesArms
                  ? <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}><i aria-hidden="true" className="fas fa-plus" /> Add arms to {cls.name}</button>
                  : <button type="button" className="btn btn-primary" onClick={addClassNoArms}><i aria-hidden="true" className="fas fa-plus" /> Add {cls.name} to this term</button>)}
              </div>
            )}
          </section>
        )}
      </>)}

      {adding && cls && (
        <Sheet title={`Add arms to ${cls.name}`} onClose={() => setAdding(false)}>
          <AddArmsForm d={d} cls={cls} existing={arms.map((a) => a.arm_id)} notify={notify}
                       onDone={() => { setAdding(false); nav.refresh(); }} />
        </Sheet>
      )}
    </div>
  );
}

function AddArmsForm({ d, cls, existing, notify, onDone }) {
  const free = (d.arms || []).filter((a) => !existing.includes(a.id));
  const [ids, setIds] = useState([]);
  const [teacher, setTeacher] = useState('');
  const [busy, setBusy] = useState(false);
  const toggle = (id) => setIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const submit = async (e) => {
    e.preventDefault();
    if (!ids.length) { notify('error', 'Pick at least one arm.'); return; }
    setBusy(true);
    const r = await submitJson(d.add_url, { class_id: cls.id, form_teacher: teacher, arm_ids: ids, term_id: d.term_id });
    setBusy(false);
    if (r.ok) { notify('success', r.message); onDone(); } else notify('error', r.error || 'Could not add.');
  };
  if (!free.length) return <p className="text-muted">Every arm is already set up for {cls.name}. Create a new arm under Class Arms first.</p>;
  return (
    <form onSubmit={submit}>
      <div className="ac-row"><span className="form-label" style={{ margin: 0 }}>Arms</span>
        <button type="button" className="ac-linkbtn" onClick={() => setIds(ids.length === free.length ? [] : free.map((a) => a.id))}>
          {ids.length === free.length ? 'Clear' : 'Select all'}</button></div>
      <div className="ac-armpick">
        {free.map((a) => (
          <label key={a.id} className={ids.includes(a.id) ? 'on' : ''}>
            <input type="checkbox" checked={ids.includes(a.id)} onChange={() => toggle(a.id)} />
            <span className="ac-armdot" style={{ background: hueFor(a.name) }}>{a.name[0]}</span>{a.name}
          </label>
        ))}
      </div>
      <div className="form-group" style={{ marginTop: '1rem' }}>
        <label className="form-label">Class teacher <span className="text-muted">(optional — same for every arm picked)</span></label>
        <input type="text" className="form-control" placeholder="Teacher's name" value={teacher} onChange={(e) => setTeacher(e.target.value)} />
      </div>
      <button type="submit" className="btn btn-primary ac-go" disabled={busy || !ids.length}>
        <i aria-hidden="true" className="fas fa-plus" /> Add {ids.length || ''} arm{ids.length === 1 ? '' : 's'} to {cls.name}</button>
    </form>
  );
}

// ---- One class-arm card, with inline "edit class teacher" -------------------
function ArmCard({ a, usesArms, notify, canEdit }) {
  const nav = useNav();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(a.form_teacher || '');
  const [phoneNo, setPhoneNo] = useState(a.form_teacher_phone || '');
  const save = async (e) => {
    e.preventDefault();
    const r = await submitJson(a.edit_teacher_url, { form_teacher: name, form_teacher_phone: phoneNo });
    if (r.ok) { notify('success', r.message || 'Teacher updated.'); setEditing(false); nav.refresh(); }
    else notify('error', r.error || 'Could not update.');
  };
  const label = a.arm || a.name;
  return (
    <div className="ac-arm">
      <a href={a.view_url} className="ac-arm-top">
        <span className="ac-armav" style={{ background: hueFor(label) }}>{usesArms && a.arm ? a.arm.slice(0, 2) : <i aria-hidden="true" className="fas fa-chalkboard" />}</span>
        <span className="ac-arm-t"><strong>{a.name}</strong><small>{a.students} student{a.students === 1 ? '' : 's'}</small></span>
        <i aria-hidden="true" className="fas fa-chevron-right ac-chev" />
      </a>
      <GenderBar boys={a.boys} girls={a.girls} total={a.students} />
      {editing ? (
        <form className="ac-teach-edit" onSubmit={save}>
          <input type="text" className="form-control" value={name} placeholder="Teacher name" autoFocus onChange={(e) => setName(e.target.value)} aria-label="Teacher name" />
          <input type="tel" className="form-control" value={phoneNo} placeholder="Phone (optional)" onChange={(e) => setPhoneNo(e.target.value)} aria-label="Teacher phone" />
          <div><button type="submit" className="btn btn-primary btn-sm">Save</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setEditing(false); setName(a.form_teacher || ''); setPhoneNo(a.form_teacher_phone || ''); }}>Cancel</button></div>
        </form>
      ) : (
        <div className="ac-teach">
          <i aria-hidden="true" className="fas fa-chalkboard-user" />
          <span className={a.form_teacher ? '' : 'none'}>{a.form_teacher || 'No class teacher'}</span>
          {a.form_teacher_phone && <a href={'tel:' + a.form_teacher_phone} className="ac-mini" aria-label="Call class teacher"><i aria-hidden="true" className="fas fa-phone" /></a>}
          {canEdit && <button type="button" className="ac-mini" onClick={() => setEditing(true)} aria-label="Edit class teacher" title="Edit class teacher"><i aria-hidden="true" className="fas fa-pen" /></button>}
        </div>
      )}
      <a href={a.view_url} className="sp-btn sp-btn-sm sp-btn-primary ac-open"><i aria-hidden="true" className="fas fa-users" /> Open roster</a>
    </div>
  );
}

// ---- View assignment (roster + enroll + move) -------------------------------
const ORDER_KEY = 'roster-order';
const bySurname = (x, y) => (x.surname || '').localeCompare(y.surname || '', undefined, { sensitivity: 'base' })
  || (x.first_name || '').localeCompare(y.first_name || '', undefined, { sensitivity: 'base' })
  || (x.middle_name || '').localeCompare(y.middle_name || '', undefined, { sensitivity: 'base' });
const GENDER_GROUPS = [['Male', 'Boys'], ['Female', 'Girls'], ['', 'Gender not set']];

function ViewAssignment({ d, notify }) {
  const nav = useNav();
  const phone = useMedia('(max-width: 899px)');
  const a = d.assignment;
  const canMove = canWrite(d, 'enrollment_edit');
  const canRemove = canWrite(d, 'enrollment_delete');
  const canEnroll = canWrite(d, 'enrollment_create');
  const [order, setOrderState] = useState(() => { try { return localStorage.getItem(ORDER_KEY) || 'surname'; } catch (e) { return 'surname'; } });
  const setOrder = (o) => { setOrderState(o); try { localStorage.setItem(ORDER_KEY, o); } catch (e) { /* ignore */ } };
  const [q, setQ] = useState('');
  const [selMode, setSelMode] = useState(false);
  const [moveSel, setMoveSel] = useState(() => new Set());
  const [sheet, setSheet] = useState(null);           // 'add' | 'move' | 'teacher'
  const enr = d.enrollments || [];
  const boys = enr.filter((e) => e.gender === 'Male').length;
  const girls = enr.filter((e) => e.gender === 'Female').length;

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return enr.filter((e) => !t || `${e.full_name} ${e.student_no}`.toLowerCase().includes(t)).slice().sort(bySurname);
  }, [enr, q]);
  const groups = order === 'gender'
    ? GENDER_GROUPS.map(([g, label]) => ({ label, key: g || 'x',
        rows: shown.filter((e) => (g ? e.gender === g : (e.gender !== 'Male' && e.gender !== 'Female'))) })).filter((g) => g.rows.length)
    : [{ label: null, key: 'all', rows: shown }];

  const toggleMove = (id) => setMoveSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allSel = shown.length > 0 && shown.every((e) => moveSel.has(e.student_id));
  const remove = async (e) => {
    if (!await confirm(`Remove ${e.full_name} from ${a.display_name}?`)) return;
    const r = await submitJson(e.remove_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Failed.');
  };
  const exitSel = () => { setSelMode(false); setMoveSel(new Set()); };
  const fmtName = (e) => (
    <><strong className="ac-sn">{e.surname || e.full_name}</strong>{e.surname && <span>{[e.first_name, e.middle_name].filter(Boolean).join(' ')}</span>}</>
  );

  const addPanel = canEnroll ? (
    <AddStudents d={d} notify={notify} onDone={() => { setSheet(null); nav.refresh(); }} />
  ) : null;

  return (
    <div className="ac ac-roster">
      <header className="ac-rhead">
        <a href={d.back_url} className="ac-back" aria-label="Back to class setup"><i aria-hidden="true" className="fas fa-arrow-left" /></a>
        <span className="ac-armav big" style={{ background: hueFor(a.arm || a.display_name) }}>{a.arm ? a.arm.slice(0, 2) : <i aria-hidden="true" className="fas fa-chalkboard" />}</span>
        <div className="ac-rhead-t">
          <span className="ac-kicker">{a.term}</span>
          <h1>{a.display_name}</h1>
          <div className="ac-teach inline">
            <i aria-hidden="true" className="fas fa-chalkboard-user" />
            <span className={a.form_teacher ? '' : 'none'}>{a.form_teacher || 'No class teacher'}</span>
            {a.form_teacher_phone && <a href={'tel:' + a.form_teacher_phone} className="ac-mini" aria-label="Call class teacher"><i aria-hidden="true" className="fas fa-phone" /></a>}
            {canWrite(d, 'structure_edit') && <button type="button" className="ac-mini" onClick={() => setSheet('teacher')} aria-label="Edit class teacher"><i aria-hidden="true" className="fas fa-pen" /></button>}
          </div>
        </div>
        <div className="ac-rstats">
          <div><b>{enr.length}</b><span>Students</span></div>
          <div className="b"><b>{boys}</b><span>Boys</span></div>
          <div className="g"><b>{girls}</b><span>Girls</span></div>
        </div>
      </header>

      {(d.siblings || []).length > 1 && (
        <nav className="ac-tabs ac-sibs" aria-label="Other arms of this class">
          {d.siblings.map((x) => (
            <a key={x.id} href={x.url} className={x.id === a.id ? 'on' : ''} aria-current={x.id === a.id ? 'page' : undefined}>
              <strong>{x.name}</strong></a>
          ))}
        </nav>
      )}

      <div className={'ac-rcols' + (addPanel && !phone ? '' : ' one')}>
        <section className="ac-panel ac-roll">
          <div className="ac-toolbar">
            <div className="ac-search"><i aria-hidden="true" className="fas fa-search" />
              <input type="search" placeholder="Search this class…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search students in this class" /></div>
            <div className="ac-seg" role="radiogroup" aria-label="Order students">
              <button type="button" role="radio" aria-checked={order === 'surname'} className={order === 'surname' ? 'on' : ''} onClick={() => setOrder('surname')}>
                <i aria-hidden="true" className="fas fa-arrow-down-a-z" /> Surname A–Z</button>
              <button type="button" role="radio" aria-checked={order === 'gender'} className={order === 'gender' ? 'on' : ''} onClick={() => setOrder('gender')}>
                <i aria-hidden="true" className="fas fa-venus-mars" /> By gender</button>
            </div>
            {canMove && enr.length > 0 && (selMode
              ? <button type="button" className="sp-btn sp-btn-sm" onClick={exitSel}>Done</button>
              : <button type="button" className="sp-btn sp-btn-sm" onClick={() => setSelMode(true)}><i aria-hidden="true" className="fas fa-check-square" /> Select</button>)}
          </div>

          {selMode && (
            <div className="ac-selbar">
              <label><input type="checkbox" checked={allSel} onChange={() => setMoveSel(allSel ? new Set() : new Set(shown.map((e) => e.student_id)))} /> {moveSel.size ? `${moveSel.size} selected` : 'Select all'}</label>
              <button type="button" className="btn btn-primary btn-sm" disabled={!moveSel.size} onClick={() => setSheet('move')}>
                <i aria-hidden="true" className="fas fa-right-left" /> Move to another class</button>
            </div>
          )}

          {enr.length === 0 ? (
            <div className="ac-empty">
              <span className="ac-empty-ic"><i aria-hidden="true" className="fas fa-user-group" /></span>
              <p>No students in {a.display_name} yet.</p>
              {canEnroll && phone && <button type="button" className="btn btn-primary" onClick={() => setSheet('add')}><i aria-hidden="true" className="fas fa-plus" /> Add students</button>}
            </div>
          ) : shown.length === 0 ? <p className="ac-none">No student matches “{q}”.</p> : (
            groups.map((g) => (
              <div key={g.key} className="ac-group">
                {g.label && <div className={'ac-ghead ' + (g.key === 'Male' ? 'b' : g.key === 'Female' ? 'g' : '')}>
                  <i aria-hidden="true" className={'fas ' + (g.key === 'Male' ? 'fa-mars' : g.key === 'Female' ? 'fa-venus' : 'fa-circle-question')} />
                  {g.label}<span>{g.rows.length}</span></div>}
                <ol className="ac-people">
                  {g.rows.map((e, i) => (
                    <li key={e.id} className={moveSel.has(e.student_id) ? 'sel' : ''}>
                      {selMode
                        ? <input type="checkbox" checked={moveSel.has(e.student_id)} onChange={() => toggleMove(e.student_id)} aria-label={`Select ${e.full_name}`} />
                        : <span className="ac-no">{i + 1}</span>}
                      <span className={'ac-pav ' + (e.gender === 'Male' ? 'b' : e.gender === 'Female' ? 'g' : '')} aria-hidden="true">
                        {((e.surname || e.full_name || '?')[0] + ((e.first_name || '')[0] || '')).toUpperCase()}</span>
                      <a href={e.view_url} className="ac-pname" onClick={(ev) => { if (selMode) { ev.preventDefault(); toggleMove(e.student_id); } }}>
                        <span className="ac-nm">{fmtName(e)}</span>
                        <small>{e.student_no}{order !== 'gender' && e.gender ? ` · ${e.gender}` : ''}</small>
                      </a>
                      {canRemove && !selMode && (
                        <button type="button" className="ac-rm" onClick={() => remove(e)} aria-label={`Remove ${e.full_name}`} title="Remove from class">
                          <i aria-hidden="true" className="fas fa-user-minus" /></button>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            ))
          )}
        </section>

        {addPanel && !phone && (
          <aside className="ac-panel ac-addrail">
            <div className="ac-addhead"><i aria-hidden="true" className="fas fa-user-plus" /><strong>Add students</strong></div>
            {addPanel}
          </aside>
        )}
      </div>

      {addPanel && phone && !selMode && createPortal(
        <button type="button" className="ac-fab" onClick={() => setSheet('add')} aria-label="Add students">
          <i aria-hidden="true" className="fas fa-user-plus" /></button>, document.body)}

      {sheet === 'add' && <Sheet title={`Add students to ${a.display_name}`} onClose={() => setSheet(null)} wide>{addPanel}</Sheet>}
      {sheet === 'move' && (
        <Sheet title={`Move ${moveSel.size} student${moveSel.size === 1 ? '' : 's'}`} onClose={() => setSheet(null)}>
          <MoveForm d={d} ids={[...moveSel]} notify={notify} onDone={() => { setSheet(null); exitSel(); nav.refresh(); }} />
        </Sheet>
      )}
      {sheet === 'teacher' && (
        <Sheet title="Class teacher" onClose={() => setSheet(null)}>
          <TeacherForm a={a} notify={notify} onDone={() => { setSheet(null); nav.refresh(); }} />
        </Sheet>
      )}
    </div>
  );
}

function TeacherForm({ a, notify, onDone }) {
  const [name, setName] = useState(a.form_teacher || '');
  const [ph, setPh] = useState(a.form_teacher_phone || '');
  const save = async (e) => {
    e.preventDefault();
    const r = await submitJson(a.edit_teacher_url, { form_teacher: name, form_teacher_phone: ph });
    if (r.ok) { notify('success', r.message || 'Teacher updated.'); onDone(); } else notify('error', r.error || 'Could not update.');
  };
  return (
    <form onSubmit={save}>
      <div className="form-group"><label className="form-label">Name</label><input className="form-control" value={name} onChange={(e) => setName(e.target.value)} placeholder="Teacher's name" autoFocus /></div>
      <div className="form-group"><label className="form-label">Phone</label><input type="tel" className="form-control" value={ph} onChange={(e) => setPh(e.target.value)} placeholder="Optional" /></div>
      <button type="submit" className="btn btn-primary ac-go">Save</button>
    </form>
  );
}

function MoveForm({ d, ids, notify, onDone }) {
  const a = d.assignment;
  const [to, setTo] = useState({ session_id: a.session_id ? String(a.session_id) : '', class_id: '', arm_id: '' });
  const [busy, setBusy] = useState(false);
  const go = async (e) => {
    e.preventDefault();
    if (!to.session_id || !to.class_id || !to.arm_id) { notify('error', 'Select the destination session, class, and arm.'); return; }
    if (!await confirm(`Move ${ids.length} student(s) to the selected class?`)) return;
    setBusy(true);
    const r = await submitJson(d.reassign_url, { 'student_ids[]': ids, to_session_id: to.session_id, to_class_id: to.class_id, to_arm_id: to.arm_id });
    setBusy(false);
    if (r.ok) { notify('success', r.message); onDone(); } else notify('error', r.error || 'Could not move students.');
  };
  const set = (k) => (e) => setTo((s) => ({ ...s, [k]: e.target.value }));
  return (
    <form onSubmit={go}>
      <p className="text-muted" style={{ marginTop: 0, fontSize: '.86rem' }}>Pick where they're going — any session, class and arm. Uses that session's First Term; within this session they're removed from {a.display_name} automatically.</p>
      <div className="form-group"><label className="form-label">To session</label>
        <select className="form-control" value={to.session_id} onChange={set('session_id')}><option value="">Select session</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
      <div className="ac-two">
        <div className="form-group"><label className="form-label">To class</label>
          <select className="form-control" value={to.class_id} onChange={set('class_id')}><option value="">Class</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">To arm</label>
          <select className="form-control" value={to.arm_id} onChange={set('arm_id')}><option value="">Arm</option>{d.arms.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
      </div>
      <button type="submit" className="btn btn-primary ac-go" disabled={busy}><i aria-hidden="true" className="fas fa-right-left" /> Move {ids.length} student{ids.length === 1 ? '' : 's'}</button>
    </form>
  );
}

function AddStudents({ d, notify, onDone }) {
  const [search, setSearch] = useState('');
  const [picked, setPicked] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  // '' = everyone, 'none' = never enrolled (new students), else a session id.
  const [sessFilter, setSessFilter] = useState('');
  const all = d.available_students || [];
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return all.filter((s) => {
      if (q && !(`${s.full_name} ${s.student_id}`).toLowerCase().includes(q)) return false;
      const cls = s.classes || {};
      if (sessFilter === 'none') return Object.keys(cls).length === 0;
      if (sessFilter) return !!cls[sessFilter];
      return true;
    });
  }, [search, sessFilter, all]);
  const toggle = (id) => setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const enroll = async (e) => {
    e.preventDefault();
    if (!picked.size) return;
    setBusy(true);
    const r = await submitJson(d.enroll_url, { 'student_ids[]': [...picked] });
    setBusy(false);
    if (r.ok) { notify('success', r.message); setPicked(new Set()); onDone(); } else notify('error', r.error || 'Could not enroll.');
  };
  if (!all.length) return <p className="ac-none">Every active student is already in a class this term. Remove a student from their class to reassign them.</p>;
  const allPicked = filtered.length > 0 && filtered.every((s) => picked.has(s.id));
  return (
    <form onSubmit={enroll} className="ac-add">
      <div className="ac-search"><i aria-hidden="true" className="fas fa-search" />
        <input type="search" placeholder="Search name or ID…" autoComplete="off" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search students to add" /></div>
      <select className="form-control" value={sessFilter} onChange={(e) => setSessFilter(e.target.value)} aria-label="Filter by academic session">
        <option value="">All unassigned students</option>
        {d.sessions.map((x) => <option key={x.id} value={String(x.id)}>Were in a class in {x.name}</option>)}
        <option value="none">Never enrolled (new students)</option>
      </select>
      <div className="ac-row"><small className="text-muted">{filtered.length} of {all.length} not in any class this term</small>
        <button type="button" className="ac-linkbtn" onClick={() => setPicked(allPicked ? new Set() : new Set(filtered.map((s) => s.id)))}>{allPicked ? 'Clear' : 'Select all'}</button></div>
      <div className="ac-pick">
        {filtered.map((s) => (
          <label className={picked.has(s.id) ? 'on' : ''} key={s.id}>
            <input type="checkbox" checked={picked.has(s.id)} onChange={() => toggle(s.id)} />
            <span className="ac-pick-t"><strong>{s.full_name}</strong>
              <small>{s.student_id}{sessFilter && sessFilter !== 'none' && s.classes && s.classes[sessFilter] ? ` · was in ${s.classes[sessFilter]}` : ''}</small></span>
          </label>))}
        {filtered.length === 0 && <p className="ac-none">No students match{sessFilter ? ' this filter' : ''}.</p>}
      </div>
      <button type="submit" className="btn btn-primary ac-go" disabled={busy || !picked.size}>
        <i aria-hidden="true" className="fas fa-plus" /> Add {picked.size || ''} student{picked.size === 1 ? '' : 's'}</button>
    </form>
  );
}

// ---- Copy term setup -------------------------------------------------------
function CopyTermSetup({ d, notify }) {
  const nav = useNav();
  const active = d.terms.find((t) => t.is_active);
  const [f, setF] = useState({ from_term_id: '', to_term_id: active ? String(active.id) : '', copy_enrollments: true });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!f.from_term_id || !f.to_term_id) { notify('error', 'Select both source and destination terms.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { from_term_id: f.from_term_id, to_term_id: f.to_term_id, copy_enrollments: f.copy_enrollments ? 'on' : '' });
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not copy.');
  };
  return (
    <>
      <div className="page-header"><h1>Copy Term Setup</h1></div>
      <div className="card"><div className="card-header"><h3>Copy Class Assignments &amp; Enrollments</h3></div>
        <div className="card-body">
          <p className="text-muted mb-3">Copy class arm assignments (and optionally student enrollments) from one term to another. This saves time when setting up a new term.</p>
          <form onSubmit={submit}>
            <div className="form-row">
              <div className="form-group"><label className="form-label">From Term (Source) <span className="required">*</span></label>
                <select className="form-control" required value={f.from_term_id} onChange={(e) => setF((s) => ({ ...s, from_term_id: e.target.value }))}>
                  <option value="">Select Source Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
              <div className="form-group"><label className="form-label">To Term (Destination) <span className="required">*</span></label>
                <select className="form-control" required value={f.to_term_id} onChange={(e) => setF((s) => ({ ...s, to_term_id: e.target.value }))}>
                  <option value="">Select Destination Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
            </div>
            <div className="form-group"><label className="checkbox-label"><input type="checkbox" checked={f.copy_enrollments} onChange={(e) => setF((s) => ({ ...s, copy_enrollments: e.target.checked }))} /> <span>Also copy student enrollments</span></label>
              <small className="text-muted">If checked, students enrolled in source term classes will be enrolled in destination term classes too.</small></div>
            <div className="page-header-actions">
              <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-copy" /> Copy Setup</button>
              <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
            </div>
          </form>
        </div></div>
      <div className="card mt-3"><div className="card-header"><h3>What Gets Copied</h3></div>
        <div className="card-body">
          <ul>
            <li><strong>Class Arm Assignments:</strong> Which classes and arms are set up (e.g., JSS1 Iris, SSS2 Rose)</li>
            <li><strong>Student Enrollments:</strong> Which students are in which class (optional)</li>
          </ul>
          <p className="text-muted"><strong>Note:</strong> Attendance, scores, and other term-specific data are NOT copied.</p>
        </div></div>
    </>
  );
}

const SCREENS = { sessions: Sessions, add_session: SessionForm, edit_session: SessionForm,
  terms: Terms, add_term: AddTerm, edit_term: EditTerm, setup: TermSetup, view_term: ViewTerm,
  classes: Classes, edit_class: ClassForm, arms: Arms, edit_arm: ArmForm, assignments: Assignments, view_assignment: ViewAssignment,
  copy_term_setup: CopyTermSetup };

export default function AcademicsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Sessions;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
