import React, { useState, useMemo } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';

// ---- Sessions list ---------------------------------------------------------
function Sessions({ d, notify }) {
  const nav = useNav();
  const activate = async (url) => {
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Failed.');
  };
  return (
    <>
      <div className="page-header"><h1>Academic Sessions</h1>
        <div className="page-header-actions"><a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</a></div>
      </div>
      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.sessions.length ? (
          <div className="data-cards" style={{ padding: '1rem' }}>{d.sessions.map((s) => (
            <div className="data-card" key={s.id}>
              <div className="data-card-header"><div className="data-card-title">{s.name}</div>{s.is_active && <span className="badge badge-success">Active</span>}</div>
              <div className="data-card-row"><span className="data-card-label">Start</span><span>{s.start_date || '-'}</span></div>
              <div className="data-card-row"><span className="data-card-label">End</span><span>{s.end_date || '-'}</span></div>
              <div className="data-card-row"><span className="data-card-label">Terms</span><span>{s.terms}</span></div>
              <div className="data-card-actions">
                <a href={s.edit_url} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-edit" /> Edit</a>
                {!s.is_active && <button type="button" className="btn btn-success btn-sm w-100" style={{ flex: 1 }} onClick={() => activate(s.activate_url)}><i aria-hidden="true" className="fas fa-check" /> Activate</button>}
              </div>
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
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Failed.');
  };
  return (
    <>
      <div className="page-header"><h1>Terms</h1>
        <div className="page-header-actions">
          <a href={d.urls.setup} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-list-check" /> Term setup</a>
          <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</a>
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
function Setup({ d }) {
  const nav = useNav();
  return (
    <>
      <div className="page-header">
        <div><h1><i aria-hidden="true" className="fas fa-list-check" /> Term Setup</h1><p className="text-muted text-sm">A quick checklist to get a term ready for attendance, results and CBT.</p></div>
        {d.terms.length > 0 && (
          <form className="filter-form"><select className="form-control" value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value })}>
            {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></form>)}
      </div>
      <div className="card"><div className="card-body">
        <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem', marginBottom: '1rem' }}>
          <div style={{ flex: 1, height: 10, background: 'var(--bg-subtle,#eef2f7)', borderRadius: 6, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: (d.required ? d.done / d.required * 100 : 0) + '%', background: '#10b981' }} /></div>
          <strong>{d.done} / {d.required} done</strong>
        </div>
        {!d.can_write && <p className="text-muted text-sm" style={{ margin: '-0.5rem 0 1rem' }}><i aria-hidden="true" className="fas fa-eye" /> View-only — you can see setup progress but not make changes.</p>}
        <div className="data-cards">{d.steps.map((s, i) => {
          const ok = s.done && !s.optional;
          return (
            <div className="data-card" key={i} style={{ borderLeft: `4px solid ${s.done ? '#10b981' : s.optional ? '#94a3b8' : '#f59e0b'}` }}>
              <div className="data-card-header"><div className="data-card-title">
                <i aria-hidden="true" className={'fas ' + (ok ? 'fa-circle-check text-success' : s.optional ? 'fa-circle-dot text-muted' : 'fa-circle-exclamation text-warning')} /> {s.title}{s.optional && <span className="text-muted text-sm"> (optional)</span>}
              </div></div>
              <div className="data-card-row"><span className="data-card-label">Status</span><span>{s.detail}</span></div>
              {d.can_write && <div className="data-card-actions"><a href={s.url} className={'btn btn-' + (ok ? 'secondary' : 'primary') + ' btn-sm w-100'}><i aria-hidden="true" className="fas fa-arrow-right" /> {s.cta}</a></div>}
            </div>);
        })}</div>
        {d.done === d.required && <div className="alert alert-success" style={{ marginTop: '1rem' }}><i aria-hidden="true" className="fas fa-check" /> This term is fully set up. Teachers can mark attendance and enter results.</div>}
      </div></div>
    </>
  );
}

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
        <div className="page-header-actions"><a href={d.urls.edit} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-edit" /> Edit Dates</a></div>
      </div>
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Start Date</label><div className="form-control" style={{ background: 'var(--bg-secondary)' }}>{t.start_date || 'Not set'}</div></div>
        <div className="form-group"><label className="form-label">End Date</label><div className="form-control" style={{ background: 'var(--bg-secondary)' }}>{t.end_date || 'Not set'}</div></div>
      </div></div></div>

      <div className="card mb-3">
        <div className="card-header"><h3>Weeks ({d.weeks.length})</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => act(d.urls.add_week, {})}><i aria-hidden="true" className="fas fa-plus" /> Add Week</button>
            {d.weeks.length === 0 && t.has_start && <button type="button" className="btn btn-secondary btn-sm" onClick={() => act(d.urls.generate_weeks, {})}><i aria-hidden="true" className="fas fa-sync" /> Generate All</button>}
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.weeks.length ? (
            <div className="data-cards" style={{ padding: '1rem' }}>{d.weeks.map((w) => (
              <div className="data-card" key={w.id}>
                <div className="data-card-header"><div className="data-card-title">Week {w.week_number}</div></div>
                <div className="data-card-row"><span className="data-card-label">Start</span><span>{w.start_date}</span></div>
                <div className="data-card-row"><span className="data-card-label">End</span><span>{w.end_date}</span></div>
                {w.is_last && <div className="data-card-actions"><button type="button" className="btn btn-danger btn-sm w-100" onClick={() => act(w.delete_url, {}, `Delete Week ${w.week_number}? This will also delete attendance records for this week.`)}><i aria-hidden="true" className="fas fa-times" /> Remove</button></div>}
              </div>))}</div>
          ) : <Empty icon="fa-calendar" title=""><p>No weeks added yet. Click "Add Week" to add Week 1.</p></Empty>}
        </div>
      </div>

      <div className="card"><div className="card-header"><h3>Holidays ({d.holidays.length})</h3></div>
        <div className="card-body">
          <form onSubmit={addHoliday} className="filter-form mb-3">
            <div className="form-group"><label className="form-label">From</label><input type="date" className="form-control" required value={hf.date} onChange={(e) => setHf((s) => ({ ...s, date: e.target.value }))} /></div>
            <div className="form-group"><label className="form-label">To <span className="text-muted">(optional)</span></label><input type="date" className="form-control" title="Leave blank for a single day" value={hf.end_date} onChange={(e) => setHf((s) => ({ ...s, end_date: e.target.value }))} /></div>
            <div className="form-group"><label className="form-label">Type</label>
              <select className="form-control" value={hf.holiday_type} onChange={(e) => setHf((s) => ({ ...s, holiday_type: e.target.value }))}>
                <option>Public Holiday</option><option>Mid-term Break</option><option>Other</option></select></div>
            <div className="form-group"><label className="form-label">Reason</label><input type="text" className="form-control" placeholder="e.g., Eid el-Kabir" required value={hf.reason} onChange={(e) => setHf((s) => ({ ...s, reason: e.target.value }))} /></div>
            <div className="filter-actions"><button type="submit" className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
          </form>
          <p className="text-muted text-sm" style={{ margin: '-0.5rem 0 1rem' }}>For a multi-day break, set From and To — each weekday in the range is marked at once. Weekends are skipped automatically.</p>
          {d.holidays.length > 0 && (
            <div className="data-cards">{d.holidays.map((h) => (
              <div className="data-card" key={h.id}>
                <div className="data-card-header"><div className="data-card-title">{h.date}</div>{h.holiday_type && <span className="badge badge-info">{h.holiday_type}</span>}</div>
                <div className="data-card-row"><span className="data-card-label">Reason</span><span>{h.reason}</span></div>
                <div className="data-card-actions"><button type="button" className="btn btn-danger btn-sm w-100" onClick={() => act(h.delete_url, {})}><i aria-hidden="true" className="fas fa-times" /> Remove</button></div>
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
  return (
    <>
      <div className="page-header"><h1>School Classes</h1></div>
      <div className="card mb-3"><div className="card-header"><h3>Add New Class</h3></div>
        <div className="card-body"><form onSubmit={add}>
          <div className="form-group"><label className="form-label">Class Name</label><input type="text" className="form-control" placeholder="e.g., JSS1" required value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
          <div className="form-group"><label className="form-label">Level</label><input type="number" className="form-control" min="1" max="20" required placeholder="Order number" value={f.level} onChange={(e) => setF((s) => ({ ...s, level: e.target.value }))} /></div>
          <div className="form-group"><label className="form-label">Description</label><input type="text" className="form-control" placeholder="Optional" value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Class</button>
        </form></div></div>
      <div className="card"><div className="card-header"><h3>Existing Classes</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.classes.length ? (
            <div className="data-cards" style={{ padding: '1rem' }}>{d.classes.map((c) => (
              <div className="data-card" key={c.id}>
                <div className="data-card-header"><div className="data-card-title">{c.name}</div><span className="badge badge-info">Level {c.level}</span></div>
                <div className="data-card-row"><span className="data-card-label">Description</span><span>{c.description || '-'}</span></div>
              </div>))}</div>
          ) : <Empty icon="fa-school" title=""><p>No classes added yet</p></Empty>}
        </div></div>
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
  return (
    <>
      <div className="page-header"><h1>Class Arms</h1></div>
      <div className="card mb-3"><div className="card-header"><h3>Add New Arm</h3></div>
        <div className="card-body"><form onSubmit={add}>
          <div className="form-group"><label className="form-label">Arm Name</label><input type="text" className="form-control" placeholder="e.g., Rose, Lily" required value={f.name} onChange={(e) => setF((s) => ({ ...s, name: e.target.value }))} /></div>
          <div className="form-group"><label className="form-label">Description</label><input type="text" className="form-control" placeholder="Optional" value={f.description} onChange={(e) => setF((s) => ({ ...s, description: e.target.value }))} /></div>
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Arm</button>
        </form></div></div>
      <div className="card"><div className="card-header"><h3>Existing Arms</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.arms.length ? (
            <div className="data-cards" style={{ padding: '1rem' }}>{d.arms.map((a) => (
              <div className="data-card" key={a.id}>
                <div className="data-card-header"><div className="data-card-title">{a.name}</div></div>
                <div className="data-card-row"><span className="data-card-label">Description</span><span>{a.description || '-'}</span></div>
              </div>))}</div>
          ) : <Empty icon="fa-layer-group" title=""><p>No arms added yet</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Assignments (class setup) ---------------------------------------------
function Assignments({ d, notify }) {
  const nav = useNav();
  const usesArms = d.uses_arms;
  const [f, setF] = useState({ class_id: '', arm_id: '', form_teacher: '' });
  const add = async (e) => {
    e.preventDefault();
    if (!f.class_id) { notify('error', 'Pick a class.'); return; }
    if (usesArms && !f.arm_id) { notify('error', 'Class and arm are required.'); return; }
    const r = await submitJson(d.add_url, { ...f, term_id: d.term_id });
    if (r.ok) { setF({ class_id: '', arm_id: '', form_teacher: '' }); notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not add.');
  };
  const toggleArms = async (on) => {
    const r = await submitJson(d.toggle_url, { uses_arms: on ? '1' : '0' });
    if (r.ok) { notify('success', on ? 'Arms enabled.' : 'Arms turned off — classes won\'t need arms.'); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const setupAll = async () => {
    const r = await submitJson(d.setup_url, { term_id: d.term_id });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not set up.');
  };
  return (
    <>
      <div className="page-header"><h1>Class Setup</h1></div>
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form">
          <div className="form-group"><label className="form-label">Select Term</label>
            <select className="form-control" value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value })}>
              <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
        </form>
        <label className="form-check" style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginTop: '.6rem' }}>
          <input type="checkbox" checked={usesArms} onChange={(e) => toggleArms(e.target.checked)} />
          <span>This school streams classes into arms (e.g. SSS1 A, SSS1 B)</span>
        </label>
        {!usesArms && <span className="form-hint d-block">Off: classes are just SSS1, SSS2… — no arm needed.</span>}
      </div></div>

      {d.selected_term && (<>
        <div className="card mb-3"><div className="card-header"><h3>{usesArms ? 'Add Class-Arm' : 'Add Class to Term'}</h3></div>
          <div className="card-body">
            {!usesArms && (
              <p style={{ marginTop: 0 }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={setupAll}><i aria-hidden="true" className="fas fa-wand-magic-sparkles" /> Set up all classes for this term</button>
                <span className="form-hint d-block">Adds every class at once so you can start enrolling students.</span>
              </p>)}
            <form onSubmit={add} className="filter-form">
              <div className="form-group"><label className="form-label">Class</label><select className="form-control" required value={f.class_id} onChange={(e) => setF((s) => ({ ...s, class_id: e.target.value }))}><option value="">Select</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
              {usesArms && (
                <div className="form-group"><label className="form-label">Arm</label><select className="form-control" required value={f.arm_id} onChange={(e) => setF((s) => ({ ...s, arm_id: e.target.value }))}><option value="">Select</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>)}
              <div className="form-group"><label className="form-label">Teacher</label><input type="text" className="form-control" placeholder="Name" value={f.form_teacher} onChange={(e) => setF((s) => ({ ...s, form_teacher: e.target.value }))} /></div>
              <div className="filter-actions"><button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
            </form></div></div>

        <div className="card"><div className="card-header"><h3>{d.selected_term.name} Classes</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            {d.assignments.length ? (
              <div className="data-cards" style={{ padding: '1rem' }}>{d.assignments.map((a) => (
                <div className="data-card" key={a.id}>
                  <div className="data-card-header"><div className="data-card-title">{a.name}</div></div>
                  <div className="data-card-row"><span className="data-card-label">Teacher</span><span>{a.form_teacher || '-'}</span></div>
                  <div className="data-card-row"><span className="data-card-label">Students</span><span>{a.students}</span></div>
                  <div className="data-card-actions"><a href={a.view_url} className="btn btn-secondary btn-sm w-100"><i aria-hidden="true" className="fas fa-users" /> Manage Students</a></div>
                </div>))}</div>
            ) : <Empty icon="fa-chalkboard" title=""><p>No class-arms set up for this term</p></Empty>}
          </div></div>
      </>)}
    </>
  );
}

// ---- View assignment (roster + enroll) -------------------------------------
function ViewAssignment({ d, notify }) {
  const nav = useNav();
  const a = d.assignment;
  const [search, setSearch] = useState('');
  const [picked, setPicked] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return d.available_students.filter((s) => !q || (`${s.full_name} ${s.student_id}`).toLowerCase().includes(q));
  }, [search, d.available_students]);
  const toggle = (id) => setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const remove = async (url) => {
    if (!await confirm('Remove student?')) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Failed.');
  };
  const enroll = async (e) => {
    e.preventDefault();
    if (!picked.size) return;
    setBusy(true);
    const r = await submitJson(d.enroll_url, { 'student_ids[]': [...picked] });
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not enroll.');
  };
  return (
    <>
      <div className="page-header">
        <div><h1>{a.display_name}</h1><p className="text-muted" style={{ fontSize: '0.875rem' }}>{a.term}</p></div>
        <div className="page-header-actions"><a href={d.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a></div>
      </div>
      <div className="card mb-3"><div className="card-header"><h3>Enrolled ({d.enrollments.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.enrollments.length ? (
            <div className="data-cards" style={{ padding: '1rem' }}>{d.enrollments.map((e) => (
              <div className="data-card" key={e.id}>
                <div className="data-card-header"><div className="data-card-title">{e.full_name}</div><span className="badge badge-primary">{e.student_id}</span></div>
                <div className="data-card-row"><span className="data-card-label">Gender</span><span>{e.gender}</span></div>
                <div className="data-card-actions"><button type="button" className="btn btn-danger btn-sm w-100" onClick={() => remove(e.remove_url)}><i aria-hidden="true" className="fas fa-times" /> Remove</button></div>
              </div>))}</div>
          ) : <Empty icon="fa-user-group" title=""><p>No students enrolled</p></Empty>}
        </div></div>

      <div className="card">
        <div className="card-header"><h3>Add Students</h3><span className="text-muted" style={{ fontSize: '0.8rem' }}>Only students not currently in a class for this term are shown.</span></div>
        <div className="card-body">
          {d.available_students.length ? (
            <form onSubmit={enroll}>
              <div className="enroll-toolbar">
                <div className="enroll-search"><i aria-hidden="true" className="fas fa-search" /><input type="text" className="form-control" placeholder="Search name or ID…" autoComplete="off" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
                <div className="enroll-toolbar-actions">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPicked(new Set(filtered.map((s) => s.id)))}><i aria-hidden="true" className="fas fa-check-double" /> Select all</button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPicked(new Set())}><i aria-hidden="true" className="fas fa-eraser" /> Clear</button>
                </div>
              </div>
              <div className="student-picker">
                {filtered.map((s) => (
                  <label className={'student-option' + (picked.has(s.id) ? ' checked' : '')} key={s.id}>
                    <input type="checkbox" checked={picked.has(s.id)} onChange={() => toggle(s.id)} />
                    <span className="student-option-body"><span className="student-option-name">{s.full_name}</span><span className="badge badge-light">{s.student_id}</span></span>
                  </label>))}
                {filtered.length === 0 && <p className="text-muted text-center" style={{ padding: '1rem' }}>No students match your search.</p>}
              </div>
              <div className="enroll-footer"><span className="text-muted">{picked.size} selected</span>
                <button type="submit" className="btn btn-primary" disabled={busy || !picked.size}><i aria-hidden="true" className="fas fa-plus" /> Enroll selected</button></div>
            </form>
          ) : <Empty icon="fa-user-check" title=""><p>Every active student is already assigned to a class this term. Remove a student from their class to reassign them.</p></Empty>}
        </div></div>
    </>
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
  terms: Terms, add_term: AddTerm, edit_term: EditTerm, setup: Setup, view_term: ViewTerm,
  classes: Classes, arms: Arms, assignments: Assignments, view_assignment: ViewAssignment,
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
