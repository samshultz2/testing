import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav } from '../lib/section';
import { Banner, SectionShell, Empty } from '../components/ui';

// Small helpers ---------------------------------------------------------------
function Actions({ children }) {
  return <div className="page-header-actions">{children}</div>;
}

function useSave(notify) {
  // POST a form-encoded action; on success run `after`, else surface the error.
  return async (url, fields, after, okMsg) => {
    const r = await submitJson(url, fields);
    if (r.ok) { notify('success', okMsg || r.message); after && after(r); }
    else notify('error', r.error || 'Something went wrong.');
    return r;
  };
}

// ---- Settings home ----------------------------------------------------------
function Index({ d }) {
  const nav = useNav();
  const card = (url, icon, title, sub) => (
    <a key={title} href={url} onClick={(e) => { e.preventDefault(); nav.go(url); }}
       className="data-card" style={{ textDecoration: 'none', color: 'inherit' }}>
      <div className="data-card-header"><div className="data-card-title"><i className={`fas ${icon}`} /> {title}</div></div>
      <div className="data-card-row">{sub}</div>
    </a>
  );
  const u = d.urls;
  return (
    <>
      <div className="page-header"><h1>Settings</h1></div>
      <div className="data-cards" style={{ padding: 0 }}>
        {card(u.school, 'fa-school', 'School Info', 'Configure school name, address, contact')}
        {card(u.academic, 'fa-clock', 'Academic', 'School hours, periods, promotion threshold')}
        {card(u.grades, 'fa-star', 'Grade Scale', 'Configure A+, A, B, C, F grades')}
        {card(u.traits, 'fa-star-half-stroke', 'Behavioural Traits', 'Affective domain traits on report cards')}
        {card(u.assessments, 'fa-tasks', 'Assessments', 'CA components, exams, max scores')}
        {card(u.timetable_slots, 'fa-calendar-alt', 'Timetable Slots', 'Period times and breaks')}
        {d.is_central && card(u.branches, 'fa-code-branch', 'Branches', 'Manage school branches')}
        {d.is_central && card(u.users, 'fa-users-cog', 'Users', 'Manage admin and teacher accounts')}
        {card(u.backup, 'fa-database', 'Backup & Restore', 'Download backup, restore data')}
      </div>
    </>
  );
}

// ---- School settings --------------------------------------------------------
function School({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const s = d.settings || {};
  const [f, setF] = useState({
    school_name: s.school_name || '', school_address: s.school_address || '',
    school_phone: s.school_phone || '', school_email: s.school_email || '',
    school_motto: s.school_motto || '', next_term_fees: s.next_term_fees || '',
    next_term_begins: s.next_term_begins || '', timezone: d.current_tz || '',
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => { e.preventDefault(); save(d.submit_url, f, () => nav.refresh()); };
  return (
    <>
      <div className="page-header"><h1>School Information</h1></div>
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-group"><label className="form-label">School Name</label>
            <input type="text" className="form-control" value={f.school_name} onChange={set('school_name')} placeholder="Enter school name" /></div>
          <div className="form-group"><label className="form-label">Address</label>
            <textarea className="form-control" rows="2" value={f.school_address} onChange={set('school_address')} placeholder="School address" /></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Phone</label>
              <input type="tel" className="form-control" value={f.school_phone} onChange={set('school_phone')} placeholder="Phone number" /></div>
            <div className="form-group"><label className="form-label">Email</label>
              <input type="email" className="form-control" value={f.school_email} onChange={set('school_email')} placeholder="Email address" /></div>
          </div>
          <div className="form-group"><label className="form-label">Motto</label>
            <input type="text" className="form-control" value={f.school_motto} onChange={set('school_motto')} placeholder="School motto" /></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Next Term Fees <span className="text-muted">(shown on report cards)</span></label>
              <input type="text" className="form-control" value={f.next_term_fees} onChange={set('next_term_fees')} placeholder="e.g. 62,000 Naira" /></div>
            <div className="form-group"><label className="form-label">Next Term Begins</label>
              <input type="text" className="form-control" value={f.next_term_begins} onChange={set('next_term_begins')} placeholder="e.g. 27 April 2026" /></div>
          </div>
          <div className="form-group"><label className="form-label">Timezone</label>
            <select className="form-control" value={f.timezone} onChange={set('timezone')}>
              {(d.timezones || []).map((tz) => <option key={tz} value={tz}>{tz}</option>)}
            </select>
            <span className="form-hint d-block">Used for all dates, times, exam windows and timestamps across the site. Default: Africa/Lagos (UTC+1).</span></div>
          <Actions>
            <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Save</button>
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
}

// ---- Academic settings ------------------------------------------------------
function Academic({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const s = d.settings || {};
  const [f, setF] = useState({
    school_day_start: s.school_day_start || '08:20', school_day_end: s.school_day_end || '14:10',
    period_duration: s.period_duration || '40', break_duration: s.break_duration || '30',
    periods_per_day: s.periods_per_day || '8', pass_mark: s.pass_mark || '50',
    promotion_threshold: s.promotion_threshold || '50',
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => { e.preventDefault(); save(d.submit_url, f, () => nav.refresh()); };
  return (
    <>
      <div className="page-header"><h1>Academic Settings</h1></div>
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <h4 style={{ marginBottom: '1rem', color: 'var(--text-secondary)' }}>School Hours</h4>
          <div className="form-row">
            <div className="form-group"><label className="form-label">School Day Start</label>
              <input type="time" className="form-control" value={f.school_day_start} onChange={set('school_day_start')} /></div>
            <div className="form-group"><label className="form-label">School Day End</label>
              <input type="time" className="form-control" value={f.school_day_end} onChange={set('school_day_end')} /></div>
          </div>
          <h4 style={{ margin: '1.5rem 0 1rem', color: 'var(--text-secondary)' }}>Period Configuration</h4>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Period Duration (minutes)</label>
              <input type="number" className="form-control" value={f.period_duration} onChange={set('period_duration')} min="20" max="90" /></div>
            <div className="form-group"><label className="form-label">Break Duration (minutes)</label>
              <input type="number" className="form-control" value={f.break_duration} onChange={set('break_duration')} min="5" max="60" /></div>
            <div className="form-group"><label className="form-label">Periods Per Day</label>
              <input type="number" className="form-control" value={f.periods_per_day} onChange={set('periods_per_day')} min="4" max="12" /></div>
          </div>
          <h4 style={{ margin: '1.5rem 0 1rem', color: 'var(--text-secondary)' }}>Grading & Promotion</h4>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Pass Mark (%)</label>
              <input type="number" className="form-control" value={f.pass_mark} onChange={set('pass_mark')} min="30" max="70" /></div>
            <div className="form-group"><label className="form-label">Promotion Threshold (%)</label>
              <input type="number" className="form-control" value={f.promotion_threshold} onChange={set('promotion_threshold')} min="30" max="70" step="0.1" />
              <small className="text-muted">Minimum average to be promoted</small></div>
          </div>
          <Actions>
            <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Save</button>
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
}

// ---- Grade scale ------------------------------------------------------------
function Grades({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [rows, setRows] = useState(
    (d.grades || []).map((g) => ({ grade: g.grade, min_score: g.min_score, max_score: g.max_score, remark: g.remark || '' })));
  const set = (i, k) => (e) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: e.target.value } : r)));
  const add = () => setRows([...rows, { grade: '', min_score: '', max_score: '', remark: '' }]);
  const del = (i) => setRows(rows.filter((_, j) => j !== i));
  const submit = (e) => {
    e.preventDefault();
    save(d.save_url, {
      'grade[]': rows.map((r) => r.grade), 'min_score[]': rows.map((r) => r.min_score),
      'max_score[]': rows.map((r) => r.max_score), 'remark[]': rows.map((r) => r.remark),
    }, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>Grade Scale</h1></div>
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="table-container"><table className="data-table">
            <thead><tr><th>Grade</th><th>Min Score</th><th>Max Score</th><th>Remark</th><th /></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td><input type="text" className="form-control" value={r.grade} onChange={set(i, 'grade')} style={{ width: 60 }} placeholder="A+" /></td>
                  <td><input type="number" className="form-control" value={r.min_score} onChange={set(i, 'min_score')} style={{ width: 80 }} placeholder="80" /></td>
                  <td><input type="number" className="form-control" value={r.max_score} onChange={set(i, 'max_score')} style={{ width: 80 }} placeholder="100" /></td>
                  <td><input type="text" className="form-control" value={r.remark} onChange={set(i, 'remark')} placeholder="Excellent" /></td>
                  <td><button type="button" className="btn btn-danger btn-sm" onClick={() => del(i)}><i className="fas fa-times" /></button></td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <Actions>
            <button type="button" className="btn btn-secondary" onClick={add}><i className="fas fa-plus" /> Add Grade</button>
            <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Save</button>
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
}

// ---- Behavioural traits -----------------------------------------------------
function Traits({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const blanks = [0, 1, 2].map(() => ({ key: '', label: '', is_active: true }));
  const [rows, setRows] = useState([...(d.traits || []).map((t) => ({ ...t })), ...blanks]);
  const setLabel = (i) => (e) => setRows(rows.map((r, j) => (j === i ? { ...r, label: e.target.value } : r)));
  const toggle = (i) => () => setRows(rows.map((r, j) => (j === i ? { ...r, is_active: !r.is_active } : r)));
  const submit = (e) => {
    e.preventDefault();
    const active = rows.map((r, i) => (r.is_active ? String(i) : null)).filter((x) => x !== null);
    save(d.save_url, {
      'key[]': rows.map((r) => r.key || ''), 'label[]': rows.map((r) => r.label),
      'active[]': active,
    }, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>Behavioural Traits</h1>
        <p className="text-muted text-sm">Affective domain traits rated on report cards. Unchecked = hidden (ratings kept).</p></div>
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <table className="data-table">
            <thead><tr><th>Trait</th><th style={{ width: 90, textAlign: 'center' }}>Active</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td><input type="text" className="form-control" value={r.label} onChange={setLabel(i)} placeholder="New trait…" /></td>
                  <td style={{ textAlign: 'center' }}><input type="checkbox" checked={!!r.is_active} onChange={toggle(i)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3">
            <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Save traits</button>{' '}
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back to Settings</a>
          </div>
        </form>
      </div></div>
    </>
  );
}

// ---- Assessment types -------------------------------------------------------
function Assessments({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [rows, setRows] = useState((d.assessments || []).map((a) => ({ name: a.name, short_name: a.short_name || '', max_score: a.max_score })));
  const set = (i, k) => (e) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: e.target.value } : r)));
  const add = () => setRows([...rows, { name: '', short_name: '', max_score: '' }]);
  const del = (i) => setRows(rows.filter((_, j) => j !== i));
  const total = rows.reduce((sum, r) => sum + (parseInt(r.max_score, 10) || 0), 0);
  const submit = (e) => {
    e.preventDefault();
    save(d.save_url, {
      'name[]': rows.map((r) => r.name), 'short_name[]': rows.map((r) => r.short_name),
      'max_score[]': rows.map((r) => r.max_score),
    }, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>Assessment Types</h1></div>
      <div className="card mb-3"><div className="card-body">
        <p><strong>Total Maximum Score:</strong> <span className={`badge ${total === 100 ? 'badge-success' : 'badge-warning'}`}>{total}</span></p>
        <small className="text-muted">The sum of all max scores should equal 100 for standard percentage grading.</small>
      </div></div>
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="table-container"><table className="data-table">
            <thead><tr><th>Name</th><th>Short</th><th>Max Score</th><th /></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td><input type="text" className="form-control" value={r.name} onChange={set(i, 'name')} placeholder="Assessment Name" /></td>
                  <td><input type="text" className="form-control" value={r.short_name} onChange={set(i, 'short_name')} style={{ width: 80 }} placeholder="CA1" /></td>
                  <td><input type="number" className="form-control" value={r.max_score} onChange={set(i, 'max_score')} style={{ width: 80 }} min="1" max="100" placeholder="10" /></td>
                  <td><button type="button" className="btn btn-danger btn-sm" onClick={() => del(i)}><i className="fas fa-times" /></button></td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <Actions>
            <button type="button" className="btn btn-secondary" onClick={add}><i className="fas fa-plus" /> Add</button>
            <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Save</button>
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
}

// ---- Timetable slots --------------------------------------------------------
function TimetableSlots({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [rows, setRows] = useState((d.slots || []).map((s) => ({ ...s })));
  const set = (i, k) => (e) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: e.target.value } : r)));
  const toggle = (i) => () => setRows(rows.map((r, j) => (j === i ? { ...r, is_break: !r.is_break } : r)));
  const s = d.settings || {};
  const generate = async () => {
    if (!window.confirm('This will regenerate all slots based on current settings. Continue?')) return;
    await save(d.generate_url, {}, () => nav.refresh());
  };
  const submit = (e) => {
    e.preventDefault();
    const breaks = rows.map((r, i) => (r.is_break ? String(i) : null)).filter((x) => x !== null);
    save(d.save_url, {
      'slot_id[]': rows.map((r) => r.id), 'name[]': rows.map((r) => r.name),
      'start_time[]': rows.map((r) => r.start_time), 'end_time[]': rows.map((r) => r.end_time),
      'is_break[]': breaks,
    }, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>Timetable Slots</h1>
        <button type="button" className="btn btn-secondary" onClick={generate}><i className="fas fa-sync" /> Auto-Generate</button></div>
      <div className="card mb-3"><div className="card-body">
        <p className="text-muted">School hours: {s.school_day_start || '08:20'} - {s.school_day_end || '14:10'} | Period: {s.period_duration || '40'} mins | Break: {s.break_duration || '30'} mins</p>
      </div></div>
      <div className="card"><div className="card-body">
        {rows.length ? (
          <form onSubmit={submit}>
            <div className="table-container"><table className="data-table">
              <thead><tr><th>Name</th><th>Start</th><th>End</th><th>Break?</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={r.is_break ? 'table-info' : ''}>
                    <td><input type="text" className="form-control" value={r.name} onChange={set(i, 'name')} /></td>
                    <td><input type="time" className="form-control" value={r.start_time} onChange={set(i, 'start_time')} style={{ width: 120 }} /></td>
                    <td><input type="time" className="form-control" value={r.end_time} onChange={set(i, 'end_time')} style={{ width: 120 }} /></td>
                    <td><input type="checkbox" checked={!!r.is_break} onChange={toggle(i)} /></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <Actions>
              <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Save Changes</button>
              <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back</a>
            </Actions>
          </form>
        ) : (
          <Empty icon="fa-clock" title="No Slots Defined">Click "Auto-Generate" to create slots based on your settings</Empty>
        )}
      </div></div>
    </>
  );
}

// ---- Backup & restore -------------------------------------------------------
function Backup({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const kb = (n) => (n / 1024);
  const createSnap = () => save(d.create_url, {}, () => nav.refresh());
  const onRestore = (e) => {
    if (!window.confirm('Are you sure? This will replace all current data!')) e.preventDefault();
  };
  return (
    <>
      <div className="page-header"><h1>Backup & Restore</h1></div>
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon primary"><i className="fas fa-database" /></div><div className="stat-content"><h3>{kb(d.db_size).toFixed(2)} KB</h3><p>Database Size</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i className="fas fa-users" /></div><div className="stat-content"><h3>{d.counts.students}</h3><p>Students</p></div></div>
        <div className="stat-card"><div className="stat-icon success"><i className="fas fa-calendar" /></div><div className="stat-content"><h3>{d.counts.sessions}</h3><p>Sessions</p></div></div>
        <div className="stat-card"><div className="stat-icon secondary"><i className="fas fa-user-shield" /></div><div className="stat-content"><h3>{d.counts.users}</h3><p>Users</p></div></div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-download" /> Download Backup</h3></div>
        <div className="card-body">
          <p>Download a complete backup of your database. Keep this file safe!</p>
          <Actions>
            <a href={d.download_url} className="btn btn-primary"><i className="fas fa-download" /> Download Database (.db)</a>
            <a href={d.export_json_url} className="btn btn-secondary"><i className="fas fa-file-code" /> Export JSON</a>
            <button type="button" className="btn btn-secondary" onClick={createSnap}><i className="fas fa-clock-rotate-left" /> Create snapshot now</button>
          </Actions>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-box-archive" /> Stored backups</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <p className="text-muted text-sm" style={{ padding: '.8rem 1rem 0' }}>Automatic daily snapshots are kept on the server (the latest few). Download any to keep off-device.</p>
          {d.backups.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>File</th><th>Date</th><th className="text-right">Size</th><th /></tr></thead>
              <tbody>
                {d.backups.map((b) => (
                  <tr key={b.name}>
                    <td data-label="File">{b.name}</td>
                    <td data-label="Date">{b.modified}</td>
                    <td data-label="Size" className="text-right">{kb(b.size).toFixed(0)} KB</td>
                    <td className="actions"><a href={b.download_url} className="btn btn-secondary btn-sm"><i className="fas fa-download" /></a></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : (
            <div className="empty-state" style={{ padding: '1.2rem' }}><i className="fas fa-box-archive" /><p>No snapshots yet — they appear after the app runs or when you create one.</p></div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3><i className="fas fa-upload" /> Restore Backup</h3></div>
        <div className="card-body">
          <div className="flash-message flash-warning mb-3">
            <i className="fas fa-exclamation-triangle" />
            <span><strong>Warning:</strong> Restoring will replace ALL current data. A backup of current data will be created automatically.</span>
          </div>
          <form method="POST" action={d.restore_url} encType="multipart/form-data" onSubmit={onRestore}>
            <input type="hidden" name="_csrf_token" value={csrfToken()} />
            <div className="form-group">
              <label className="form-label">Select Backup File (.db or .sql)</label>
              <input type="file" name="file" className="form-control" accept=".db,.sql" required />
            </div>
            <button type="submit" className="btn btn-danger"><i className="fas fa-upload" /> Restore Backup</button>
          </form>
        </div>
      </div>
    </>
  );
}

// ---- Branches ---------------------------------------------------------------
function BranchEdit({ b, save, refresh }) {
  const [f, setF] = useState({ name: b.name, code: b.code || '', phone: b.phone || '', address: b.address || '', is_active: b.is_active, make_default: false });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => {
    e.preventDefault();
    const fields = { name: f.name, code: f.code, phone: f.phone, address: f.address };
    if (f.is_active) fields.is_active = 'on';
    if (f.make_default) fields.make_default = 'on';
    save(b.edit_url, fields, () => refresh());
  };
  return (
    <details>
      <summary className="btn btn-sm btn-secondary" style={{ listStyle: 'none', cursor: 'pointer' }}>Edit</summary>
      <form onSubmit={submit} style={{ marginTop: '.5rem', display: 'grid', gap: '.4rem', minWidth: 220 }}>
        <input type="text" className="form-control" value={f.name} onChange={set('name')} />
        <input type="text" className="form-control" value={f.code} onChange={set('code')} placeholder="Code" />
        <input type="text" className="form-control" value={f.phone} onChange={set('phone')} placeholder="Phone" />
        <input type="text" className="form-control" value={f.address} onChange={set('address')} placeholder="Address" />
        <label className="text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Active</label>
        {!b.is_default && <label className="text-sm"><input type="checkbox" checked={f.make_default} onChange={(e) => setF({ ...f, make_default: e.target.checked })} /> Make default</label>}
        <button type="submit" className="btn btn-sm btn-primary">Save</button>
      </form>
    </details>
  );
}

function Branches({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [f, setF] = useState({ name: '', code: '', phone: '', address: '' });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const add = (e) => {
    e.preventDefault();
    save(d.add_url, f, () => { setF({ name: '', code: '', phone: '', address: '' }); nav.refresh(); });
  };
  return (
    <>
      <div className="page-header"><h1><i className="fas fa-code-branch" /> Branches</h1></div>
      <p className="text-muted text-sm" style={{ marginBottom: '1rem' }}>
        <i className="fas fa-info-circle" /> Central users (Director of Studies, Exams &amp; Standards, IT) see every branch.
        Branch users only see their own. The <strong>default</strong> branch is where new and existing unassigned records belong.
      </p>
      <div className="card mb-3">
        <div className="card-header"><h3><i className="fas fa-plus" /> Add branch</h3></div>
        <div className="card-body">
          <form onSubmit={add} className="filter-form" style={{ flexWrap: 'wrap', gap: '1rem' }}>
            <div className="form-group"><label className="form-label">Name <span className="text-danger">*</span></label>
              <input type="text" className="form-control" value={f.name} onChange={set('name')} placeholder="e.g. Jemila" required /></div>
            <div className="form-group"><label className="form-label">Code</label>
              <input type="text" className="form-control" value={f.code} onChange={set('code')} placeholder="e.g. JEM" /></div>
            <div className="form-group"><label className="form-label">Phone</label>
              <input type="text" className="form-control" value={f.phone} onChange={set('phone')} /></div>
            <div className="form-group" style={{ flex: '1 1 220px' }}><label className="form-label">Address</label>
              <input type="text" className="form-control" value={f.address} onChange={set('address')} /></div>
            <div className="form-group" style={{ alignSelf: 'flex-end' }}><button type="submit" className="btn btn-primary"><i className="fas fa-plus" /> Add</button></div>
          </form>
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h3>Branches ({d.branches.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.branches.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Name</th><th>Code</th><th>Phone</th><th>Status</th><th /></tr></thead>
              <tbody>
                {d.branches.map((b) => (
                  <tr key={b.id}>
                    <td data-label="Name"><strong>{b.name}</strong>{b.is_default && <span className="badge badge-success"> Default</span>}</td>
                    <td data-label="Code">{b.code || '—'}</td>
                    <td data-label="Phone">{b.phone || '—'}</td>
                    <td data-label="Status">{b.is_active ? <span className="badge badge-info">Active</span> : <span className="badge badge-secondary">Inactive</span>}</td>
                    <td data-label=""><BranchEdit b={b} save={save} refresh={nav.refresh} /></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : (
            <Empty icon="fa-code-branch" title="No branches yet">Add your first branch above.</Empty>
          )}
        </div>
      </div>
    </>
  );
}

// ---- Users ------------------------------------------------------------------
function Users({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const del = (u) => {
    if (!window.confirm(`Delete user ${u.username}?`)) return;
    save(u.delete_url, {}, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>User Management</h1>
        <a href={d.add_url} onClick={(e) => { e.preventDefault(); nav.go(d.add_url); }} className="btn btn-primary"><i className="fas fa-plus" /> Add User</a></div>
      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.users.length ? (
          <div className="data-cards" style={{ padding: '1rem' }}>
            {d.users.map((u) => (
              <div className="data-card" key={u.id}>
                <div className="data-card-header">
                  <div className="data-card-title">{u.full_name || u.username}</div>
                  <span className={`badge ${u.role === 'admin' ? 'badge-danger' : 'badge-info'}`}>{u.role}</span>
                </div>
                <div className="data-card-row"><span className="data-card-label">Username</span><span>{u.username}</span></div>
                <div className="data-card-row"><span className="data-card-label">Email</span><span>{u.email || '-'}</span></div>
                <div className="data-card-row"><span className="data-card-label">Status</span><span className={`badge ${u.is_active ? 'badge-success' : 'badge-secondary'}`}>{u.is_active ? 'Active' : 'Inactive'}</span></div>
                <div className="data-card-actions">
                  <a href={u.edit_url} onClick={(e) => { e.preventDefault(); nav.go(u.edit_url); }} className="btn btn-secondary btn-sm"><i className="fas fa-edit" /> Edit</a>
                  <button type="button" className="btn btn-danger btn-sm" style={{ flex: 1 }} onClick={() => del(u)}><i className="fas fa-trash" /></button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty icon="fa-users" title="No Users">Add your first user</Empty>
        )}
      </div></div>
    </>
  );
}

// ---- Add / edit user --------------------------------------------------------
function AddUser({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [f, setF] = useState({ username: '', full_name: '', email: '', role: 'teacher', password: '' });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => { e.preventDefault(); save(d.submit_url, f, (r) => nav.go(r.redirect || d.back_url)); };
  return (
    <>
      <div className="page-header"><h1>Add User</h1></div>
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Username <span className="required">*</span></label>
              <input type="text" className="form-control" value={f.username} onChange={set('username')} required placeholder="username" /></div>
            <div className="form-group"><label className="form-label">Full Name</label>
              <input type="text" className="form-control" value={f.full_name} onChange={set('full_name')} placeholder="John Doe" /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Email</label>
              <input type="email" className="form-control" value={f.email} onChange={set('email')} placeholder="user@school.com" /></div>
            <div className="form-group"><label className="form-label">Role</label>
              <select className="form-control" value={f.role} onChange={set('role')}>
                <option value="teacher">Teacher</option><option value="admin">Admin</option><option value="readonly">Read Only</option>
              </select></div>
          </div>
          <div className="form-group"><label className="form-label">Password <span className="required">*</span></label>
            <input type="password" className="form-control" value={f.password} onChange={set('password')} required placeholder="Enter password" /></div>
          <Actions>
            <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Create User</button>
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Cancel</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
}

function EditUser({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const u = d.user;
  const [f, setF] = useState({ full_name: u.full_name || '', email: u.email || '', role: u.role, password: '', is_active: u.is_active });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => {
    e.preventDefault();
    const fields = { full_name: f.full_name, email: f.email, role: f.role, password: f.password };
    if (f.is_active) fields.is_active = 'on';
    save(d.submit_url, fields, (r) => nav.go(r.redirect || d.back_url));
  };
  return (
    <>
      <div className="page-header"><h1>Edit User: {u.username}</h1></div>
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Username</label>
              <input type="text" className="form-control" value={u.username} disabled /></div>
            <div className="form-group"><label className="form-label">Full Name</label>
              <input type="text" className="form-control" value={f.full_name} onChange={set('full_name')} /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Email</label>
              <input type="email" className="form-control" value={f.email} onChange={set('email')} /></div>
            <div className="form-group"><label className="form-label">Role</label>
              <select className="form-control" value={f.role} onChange={set('role')}>
                <option value="teacher">Teacher</option><option value="admin">Admin</option><option value="readonly">Read Only</option>
              </select></div>
          </div>
          <div className="form-group"><label className="form-label">New Password</label>
            <input type="password" className="form-control" value={f.password} onChange={set('password')} placeholder="Leave blank to keep current" /></div>
          <div className="form-check mb-3">
            <input type="checkbox" id="is_active" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />{' '}
            <label htmlFor="is_active">Active</label></div>
          <Actions>
            <button type="submit" className="btn btn-primary"><i className="fas fa-save" /> Save Changes</button>
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Cancel</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
}

const SCREENS = {
  index: Index, school: School, academic: Academic, grades: Grades, traits: Traits,
  assessments: Assessments, timetable_slots: TimetableSlots, backup: Backup,
  branches: Branches, users: Users, add_user: AddUser, edit_user: EditUser,
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
