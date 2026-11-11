import React, { useState } from 'react';
import { submitJson, postFile, useSave } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty, FileUpload } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Index, Branches, Backup, Audit, School } from './Hub';

// Small helpers ---------------------------------------------------------------
function Actions({ children }) {
  return <div className="page-header-actions">{children}</div>;
}

// "2025/2026" -> "2526" (last 2 digits of each year), mirroring
// models/models/student.py::_session_short_code. null if not that shape.
function sessionShortCode(name) {
  const m = /^(\d{4})\/(\d{4})$/.exec((name || '').trim());
  return m ? m[1].slice(2) + m[2].slice(2) : null;
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
    student_id_prefix: s.student_id_prefix || 'STU',
    student_id_digits: s.student_id_digits || '5',
    student_id_include_session: (s.student_id_include_session ?? 'false') !== 'false' ? '1' : '0',
    uses_class_arms: (s.uses_class_arms ?? 'true') !== 'false' ? '1' : '0',
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const toggle = (k) => (e) => setF({ ...f, [k]: e.target.checked ? '1' : '0' });
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
          <h4 style={{ margin: '1.5rem 0 1rem', color: 'var(--text-secondary)' }}>Student ID Format</h4>
          <div className="form-row">
            <div className="form-group"><label className="form-label">ID Prefix</label>
              <input type="text" className="form-control" value={f.student_id_prefix}
                     onChange={(e) => setF({ ...f, student_id_prefix: e.target.value.toUpperCase() })}
                     maxLength={10} placeholder="e.g. PIO" />
              <small className="text-muted">Default prefix, letters/digits up to 10 (e.g. PIO). Blank = STU. A
                branch with its own Code (Settings → Branches) uses that instead — e.g. a "New Benin" branch
                coded NB and a "Jemila" branch coded JM get NB##### / JM##### ids automatically.</small></div>
            <div className="form-group"><label className="form-label">Minimum Digits</label>
              <input type="number" className="form-control" value={f.student_id_digits} onChange={set('student_id_digits')} min="3" max="12" />
              <small className="text-muted">Zero-padded width — e.g. 6 → {(f.student_id_prefix || 'STU')}{'000001'}. Numbers grow past this if needed.</small></div>
          </div>
          <div className="form-group">
            <label className="form-check" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
              <input type="checkbox" checked={f.student_id_include_session === '1'} onChange={toggle('student_id_include_session')} />
              <span>Include the academic session in new student IDs</span>
            </label>
            <small className="text-muted d-block">
              {d.active_session_name && sessionShortCode(d.active_session_name)
                ? <>e.g. the {d.active_session_name} session inserts <strong>{sessionShortCode(d.active_session_name)}</strong> right
                    after the prefix (a later session, e.g. 2026/2027, inserts 2627 instead) — each session then starts its own
                    numbering from 1.</>
                : <>e.g. a 2025/2026 session inserts <strong>2526</strong> right after the prefix (2026/2027 inserts 2627 instead)
                    — each session then starts its own numbering from 1. No active session is set right now, so this can't take
                    effect until one is.</>}
            </small>
          </div>
          <p className="text-muted" style={{ fontSize: '.82rem', marginTop: '-.4rem' }}>
            Next new ID (default prefix, no branch override) will look like <strong>{(f.student_id_prefix || 'STU')}
            {(f.student_id_include_session === '1' && d.active_session_name && sessionShortCode(d.active_session_name)) || ''}
            {'1'.padStart(Math.max(3, Math.min(parseInt(f.student_id_digits, 10) || 5, 12)), '0')}</strong>. Existing IDs are never changed.
          </p>

          <h4 style={{ margin: '1.5rem 0 1rem', color: 'var(--text-secondary)' }}>Class Structure</h4>
          <div className="form-group">
            <label className="form-check" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
              <input type="checkbox" checked={f.uses_class_arms === '1'} onChange={toggle('uses_class_arms')} />
              <span>This school streams classes into arms (e.g. SSS1 A, SSS1 B)</span>
            </label>
            <small className="text-muted d-block">Turn off if your classes are just SSS1, SSS2… with no arms — then set them up under Academics → Class Setup.</small>
          </div>
          <Actions>
            {canWrite(d, 'academic_config') && <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save</button>}
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
                  <td>{canWrite(d, 'grades_edit') && <button type="button" className="btn btn-danger btn-sm" onClick={() => del(i)}><i aria-hidden="true" className="fas fa-times" /></button>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <Actions>
            {canWrite(d, 'grades_edit') && <button type="button" className="btn btn-secondary" onClick={add}><i aria-hidden="true" className="fas fa-plus" /> Add Grade</button>}
            {canWrite(d, 'grades_edit') && <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save</button>}
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
            {canWrite(d, 'traits_edit') && <>
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save traits</button>{' '}
            </>}
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
                  <td>{canWrite(d, 'assessments_edit') && <button type="button" className="btn btn-danger btn-sm" onClick={() => del(i)}><i aria-hidden="true" className="fas fa-times" /></button>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <Actions>
            {canWrite(d, 'assessments_edit') && <button type="button" className="btn btn-secondary" onClick={add}><i aria-hidden="true" className="fas fa-plus" /> Add</button>}
            {canWrite(d, 'assessments_edit') && <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save</button>}
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
    if (!await confirm('This will regenerate all slots based on current settings. Continue?')) return;
    await save(d.generate_url, {}, () => nav.refresh());
  };
  const submit = (e) => {
    e.preventDefault();
    const breaks = rows.map((r, i) => (r.is_break ? String(i) : null)).filter((x) => x !== null);
    save(d.save_url, {
      'slot_id[]': rows.map((r) => r.id), 'name[]': rows.map((r) => r.name),
      'start_time[]': rows.map((r) => r.start_time), 'end_time[]': rows.map((r) => r.end_time),
      'is_break[]': breaks, 'after_period[]': rows.map((r) => r.after_period ?? ''),
    }, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>Timetable Slots</h1>
        {canWrite(d, 'slots_generate') && <button type="button" className="btn btn-secondary" onClick={generate}><i aria-hidden="true" className="fas fa-sync" /> Auto-Generate</button>}</div>
      <div className="card mb-3"><div className="card-body">
        <p className="text-muted">School hours: {s.school_day_start || '08:20'} - {s.school_day_end || '14:10'} | Period: {s.period_duration || '40'} mins | Break: {s.break_duration || '30'} mins</p>
      </div></div>
      <div className="card"><div className="card-body">
        {rows.length ? (
          <form onSubmit={submit}>
            <div className="table-container"><table className="data-table">
              <thead><tr><th>Name</th><th>Start</th><th>End</th><th>Break?</th><th>After period</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={r.is_break ? 'table-info' : ''}>
                    <td><input type="text" className="form-control" value={r.name} onChange={set(i, 'name')} /></td>
                    <td><input type="time" className="form-control" value={r.start_time} onChange={set(i, 'start_time')} style={{ width: 120 }} /></td>
                    <td><input type="time" className="form-control" value={r.end_time} onChange={set(i, 'end_time')} style={{ width: 120 }} /></td>
                    <td><input type="checkbox" checked={!!r.is_break} onChange={toggle(i)} /></td>
                    <td>
                      {r.is_break ? (
                        <input type="number" min="0" className="form-control" style={{ width: 90 }}
                          value={r.after_period ?? ''} onChange={set(i, 'after_period')}
                          title="This break belongs immediately after teaching period N" placeholder="N" />
                      ) : <span className="text-muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <p className="form-hint mb-3">"After period" is the definitive rule used to position each break —
              e.g. a break with "After period" set to 9 will always be placed right after Period 9, even if the
              stored times drift. Only applies to break rows.</p>
            <Actions>
              {canWrite(d, 'slots_edit') && <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Changes</button>}
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

// ---- Users ------------------------------------------------------------------
function Users({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const del = async (u) => {
    if (!await confirm(`Delete user ${u.username}?`)) return;
    save(u.delete_url, {}, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>User Management</h1>
        <a href={d.add_url} onClick={(e) => { e.preventDefault(); nav.go(d.add_url); }} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add User</a></div>
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
                  <a href={u.edit_url} onClick={(e) => { e.preventDefault(); nav.go(u.edit_url); }} className="btn btn-secondary btn-sm" style={{ flex: 1 }}><i aria-hidden="true" className="fas fa-edit" /> Edit</a>
                  <button type="button" className="btn btn-danger btn-sm" style={{ flex: 1 }} onClick={() => del(u)}><i aria-hidden="true" className="fas fa-trash" /> Delete</button>
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
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Create User</button>
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
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Changes</button>
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Cancel</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
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
  branches: Branches, users: Users, add_user: AddUser, edit_user: EditUser,
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
