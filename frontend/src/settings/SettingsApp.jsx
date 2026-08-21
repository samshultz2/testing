import React, { useState } from 'react';
import { submitJson, postFile, useSave } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty, FileUpload } from '../components/ui';

// Small helpers ---------------------------------------------------------------
function Actions({ children }) {
  return <div className="page-header-actions">{children}</div>;
}

// ---- Settings home ----------------------------------------------------------
function Index({ d }) {
  const nav = useNav();
  const card = (url, icon, title, sub) => (
    <a key={title} href={url} onClick={(e) => { e.preventDefault(); nav.go(url); }}
       className="data-card" style={{ textDecoration: 'none', color: 'inherit' }}>
      <div className="data-card-header"><div className="data-card-title"><i aria-hidden="true" className={`fas ${icon}`} /> {title}</div></div>
      <div className="data-card-row">{sub}</div>
    </a>
  );
  // Classic (non-SPA) pages — full navigation, no nav.go interception.
  const cardExt = (url, icon, title, sub) => (
    <a key={title} href={url} className="data-card" style={{ textDecoration: 'none', color: 'inherit' }}>
      <div className="data-card-header"><div className="data-card-title"><i aria-hidden="true" className={`fas ${icon}`} /> {title}</div></div>
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
        {d.is_central && card(u.audit, 'fa-clipboard-list', 'Audit Log', 'Who changed what, and when')}
        {card(u.ocr, 'fa-robot', 'AI Vision OCR', 'Optional Claude key for reading result images')}
        {u.exam_subjects && cardExt(u.exam_subjects, 'fa-file-signature', 'Exam Subjects', 'WAEC/JAMB catalogue, general & per-stream compulsories')}
        {u.notifications && cardExt(u.notifications, 'fa-bell', 'Notifications', 'Choose which channels you receive alerts on')}
        {d.is_central && u.performance && cardExt(u.performance, 'fa-gauge-high', 'Performance', 'Recent slow requests and SQL queries')}
        {d.is_central && u.admissions && cardExt(u.admissions, 'fa-graduation-cap', 'Admissions data', 'Universities, courses & JAMB cut-offs')}
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
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    await save(d.submit_url, f, () => nav.refresh());
    setSaving(false);
  };

  const [logoUrl, setLogoUrl] = useState(d.logo_url || '');
  const [busy, setBusy] = useState(false);
  const pickLogo = async (file) => {
    setBusy(true);
    const r = await postFile(d.logo_upload_url, file);
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Logo updated.'); nav.refresh(); }
    else notify('error', r.error || 'Could not upload that image.');
  };
  const removeLogo = async () => {
    if (!await confirm('Remove the school logo? Printouts will fall back to the app logo.')) return;
    setBusy(true);
    const r = await submitJson(d.logo_remove_url, {});
    setBusy(false);
    if (r.ok) { setLogoUrl(''); notify('success', r.message || 'Logo removed.'); nav.refresh(); }
    else notify('error', r.error || 'Could not remove the logo.');
  };

  return (
    <>
      <div className="page-header"><h1>School Information</h1></div>
      <div className="card"><div className="card-body">
        <FileUpload
          label={logoUrl ? 'Replace logo' : 'Upload logo'}
          accept="image/png,image/jpeg,image/webp"
          onPick={pickLogo} busy={busy} currentUrl={logoUrl} onClear={removeLogo}
          hint="PNG, JPG or WEBP. Shown in place of the app name/logo when signed in, and on report cards, Mock-WAEC results, broadsheets and timetables." />
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
            <button type="submit" className={'btn btn-primary' + (saving ? ' is-loading' : '')} disabled={saving} aria-busy={saving || undefined}>
              <i aria-hidden="true" className={'fas ' + (saving ? 'fa-spinner fa-spin' : 'fa-save')} /> {saving ? 'Saving…' : 'Save'}
            </button>
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
    student_id_prefix: s.student_id_prefix || 'STU',
    student_id_digits: s.student_id_digits || '5',
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
              <small className="text-muted">Letters/digits, up to 10 (e.g. PIO). Blank = STU.</small></div>
            <div className="form-group"><label className="form-label">Minimum Digits</label>
              <input type="number" className="form-control" value={f.student_id_digits} onChange={set('student_id_digits')} min="3" max="12" />
              <small className="text-muted">Zero-padded width — e.g. 6 → {(f.student_id_prefix || 'STU')}{'000001'}. Numbers grow past this if needed.</small></div>
          </div>
          <p className="text-muted" style={{ fontSize: '.82rem', marginTop: '-.4rem' }}>
            Next new ID will look like <strong>{(f.student_id_prefix || 'STU')}{'1'.padStart(Math.max(3, Math.min(parseInt(f.student_id_digits, 10) || 5, 12)), '0')}</strong>. Existing IDs are never changed.
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
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save</button>
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
                  <td><button type="button" className="btn btn-danger btn-sm" onClick={() => del(i)}><i aria-hidden="true" className="fas fa-times" /></button></td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <Actions>
            <button type="button" className="btn btn-secondary" onClick={add}><i aria-hidden="true" className="fas fa-plus" /> Add Grade</button>
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save</button>
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
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save traits</button>{' '}
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
                  <td><button type="button" className="btn btn-danger btn-sm" onClick={() => del(i)}><i aria-hidden="true" className="fas fa-times" /></button></td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <Actions>
            <button type="button" className="btn btn-secondary" onClick={add}><i aria-hidden="true" className="fas fa-plus" /> Add</button>
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save</button>
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
      'is_break[]': breaks,
    }, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header"><h1>Timetable Slots</h1>
        <button type="button" className="btn btn-secondary" onClick={generate}><i aria-hidden="true" className="fas fa-sync" /> Auto-Generate</button></div>
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
              <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Changes</button>
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
  const onRestore = async (e) => {
    e.preventDefault();   // hold the native submit until the user confirms
    const form = e.currentTarget;
    if (await confirm({ title: 'Restore database', message: 'Are you sure? This will replace all current data!', confirmText: 'Restore', tone: 'danger' }))
      form.submit();      // native submit (does not re-trigger onSubmit)
  };
  return (
    <>
      <div className="page-header"><h1>Backup & Restore</h1></div>
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-database" /></div><div className="stat-content"><h3>{kb(d.db_size).toFixed(2)} KB</h3><p>Database Size</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-users" /></div><div className="stat-content"><h3>{d.counts.students}</h3><p>Students</p></div></div>
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-calendar" /></div><div className="stat-content"><h3>{d.counts.sessions}</h3><p>Sessions</p></div></div>
        <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-user-shield" /></div><div className="stat-content"><h3>{d.counts.users}</h3><p>Users</p></div></div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-download" /> Download Backup</h3></div>
        <div className="card-body">
          <p>Download a complete backup of your database. Keep this file safe!</p>
          <Actions>
            <a href={d.download_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-download" /> Download Database (.db)</a>
            <a href={d.export_json_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-code" /> Export JSON</a>
            <button type="button" className="btn btn-secondary" onClick={createSnap}><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Create snapshot now</button>
          </Actions>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-box-archive" /> Stored backups</h3></div>
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
                    <td className="actions"><a href={b.download_url} className="btn btn-secondary btn-sm" aria-label="Download"><i aria-hidden="true" className="fas fa-download" /></a></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : (
            <Empty icon="fa-box-archive" title="No snapshots yet"><p>They appear after the app runs or when you create one.</p></Empty>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-upload" /> Restore Backup</h3></div>
        <div className="card-body">
          <div className="flash-message flash-warning mb-3">
            <i aria-hidden="true" className="fas fa-exclamation-triangle" />
            <span><strong>Warning:</strong> Restoring will replace ALL current data. A backup of current data will be created automatically.</span>
          </div>
          <form method="POST" action={d.restore_url} encType="multipart/form-data" onSubmit={onRestore}>
            <input type="hidden" name="_csrf_token" value={csrfToken()} />
            <div className="form-group">
              <label className="form-label">Select Backup File (.db or .sql)</label>
              <input type="file" name="file" className="form-control" accept=".db,.sql" required />
            </div>
            <div className="form-group">
              <label className="form-label">Type <code>RESTORE</code> to confirm you want to replace all current data</label>
              <input type="text" name="confirm" className="form-control" autoComplete="off"
                     placeholder="RESTORE" pattern="RESTORE" required />
            </div>
            <button type="submit" className="btn btn-danger"><i aria-hidden="true" className="fas fa-upload" /> Restore Backup</button>
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
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-code-branch" /> Branches</h1></div>
      <p className="text-muted text-sm" style={{ marginBottom: '1rem' }}>
        <i aria-hidden="true" className="fas fa-info-circle" /> Central users (Director of Studies, Exams &amp; Standards, IT) see every branch.
        Branch users only see their own. The <strong>default</strong> branch is where new and existing unassigned records belong.
      </p>
      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Add branch</h3></div>
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
            <div className="form-group" style={{ alignSelf: 'flex-end' }}><button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
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
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save</button>
            <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back</a>
          </Actions>
        </form>
      </div></div>
    </>
  );
}

// ---- Audit log --------------------------------------------------------------
function Audit({ d }) {
  const nav = useNav();
  const [f, setF] = useState({ ...d.filters });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  // Build the query params for the current filter state (+ optional overrides
  // like page). Empty filters are dropped so the URL stays clean.
  const params = (extra = {}) => {
    const p = {};
    ['q', 'action', 'user', 'from', 'to'].forEach((k) => { if (f[k]) p[k] = f[k]; });
    return { ...p, ...extra };
  };
  const submit = (e) => { e.preventDefault(); navParams(nav.go, d.base_url, params()); };
  const goPage = (page) => navParams(nav.go, d.base_url, params({ page }));
  const reset = () => { setF({ q: '', action: '', user: '', from: '', to: '' }); nav.go(d.base_url); };
  const pg = d.pagination || { page: 1, pages: 1, total: 0 };
  return (
    <>
      <div className="page-header"><h1>Audit Log</h1>
        <a href={d.back_url} onClick={(e) => { e.preventDefault(); nav.go(d.back_url); }} className="btn btn-secondary">Back</a>
      </div>
      <p className="text-muted text-sm" style={{ marginBottom: '1rem' }}>
        <i aria-hidden="true" className="fas fa-shield-halved" /> Append-only record of sensitive actions — who did what, to what, when, and from where. Entries can never be edited or deleted.
      </p>

      <div className="card mb-3"><div className="card-body">
        <form onSubmit={submit} className="filter-form" style={{ flexWrap: 'wrap', gap: '.75rem', alignItems: 'flex-end' }}>
          <div className="form-group"><label className="form-label">Search</label>
            <input type="text" className="form-control" value={f.q} onChange={set('q')} placeholder="action, detail, name…" /></div>
          <div className="form-group"><label className="form-label">Action</label>
            <select className="form-control" value={f.action} onChange={set('action')}>
              <option value="">All actions</option>
              {d.actions.map((a) => <option key={a} value={a}>{a}</option>)}
            </select></div>
          <div className="form-group"><label className="form-label">User</label>
            <input type="text" className="form-control" value={f.user} onChange={set('user')} placeholder="name" /></div>
          <div className="form-group"><label className="form-label">From</label>
            <input type="date" className="form-control" value={f.from} onChange={set('from')} /></div>
          <div className="form-group"><label className="form-label">To</label>
            <input type="date" className="form-control" value={f.to} onChange={set('to')} /></div>
          <div className="form-group">
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-filter" /> Filter</button>{' '}
            <button type="button" className="btn btn-secondary" onClick={reset}>Reset</button>
          </div>
        </form>
      </div></div>

      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.logs.length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Target</th><th>Branch</th><th>Detail</th><th>IP</th><th>Device</th></tr></thead>
            <tbody>
              {d.logs.map((l) => (
                <tr key={l.id}>
                  <td data-label="When">{l.created_at}</td>
                  <td data-label="Who">{l.user}{l.role && <div className="text-muted text-sm">{l.role}</div>}</td>
                  <td data-label="Action"><span className="badge badge-info">{l.action}</span></td>
                  <td data-label="Target">{l.target_label || '—'}{l.target_type && <div className="text-muted text-sm">{l.target_type}</div>}</td>
                  <td data-label="Branch">{l.branch || '—'}</td>
                  <td data-label="Detail" style={{ whiteSpace: 'pre-wrap', maxWidth: 300 }}>{l.detail || '—'}</td>
                  <td data-label="IP">{l.ip_address || '—'}</td>
                  <td data-label="Device"><span title={l.user_agent}
                    style={{ display: 'inline-block', maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' }}>{l.user_agent || '—'}</span></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        ) : (
          <Empty icon="fa-clipboard-list" title="No audit entries">Nothing matches these filters yet.</Empty>
        )}
      </div></div>

      {pg.pages > 1 && (
        <div style={{ display: 'flex', gap: '.75rem', alignItems: 'center', justifyContent: 'center', marginTop: '1rem' }}>
          <button type="button" className="btn btn-secondary btn-sm" disabled={!pg.has_prev} onClick={() => goPage(pg.prev_page)}><i aria-hidden="true" className="fas fa-chevron-left" /> Previous</button>
          <span className="text-muted text-sm">Page {pg.page} of {pg.pages} · {pg.total} entries</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={!pg.has_next} onClick={() => goPage(pg.next_page)}>Next <i aria-hidden="true" className="fas fa-chevron-right" /></button>
        </div>
      )}
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
