import React, { useState, useMemo } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, PageHeader, Empty, SectionShell, SuccessBanner } from '../components/ui';
import { canWrite } from '../lib/perms';


// ---- Index -----------------------------------------------------------------
function Index({ d }) {
  const links = [
    ['rules', 'fa-list-alt', 'Promotion Rules', 'Configure promotion criteria and streams'],
    ['process', 'fa-user-graduate', 'Process Promotions', 'Review and promote students'],
    ['graduates', 'fa-graduation-cap', 'Graduates', 'View graduated students with WAEC/JAMB results'],
    ['history', 'fa-history', 'Promotion History', 'View past promotion records'],
  ];
  return (
    <>
      <PageHeader title="Student Promotion" />
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-cog" /></div>
          <div className="stat-content"><h3>{d.rules_count}</h3><p>Promotion Rules</p></div></div>
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-calendar" /></div>
          <div className="stat-content"><h3>{d.active_session || '-'}</h3><p>Active Session</p></div></div>
      </div>
      <div className="data-cards" style={{ padding: 0 }}>
        {links.map(([key, icon, title, desc]) => (
          <a key={key} href={d.urls[key]} className="data-card" style={{ textDecoration: 'none', color: 'inherit' }}>
            <div className="data-card-header"><div className="data-card-title"><i aria-hidden="true" className={'fas ' + icon} /> {title}</div></div>
            <div className="data-card-row">{desc}</div>
          </a>
        ))}
      </div>
      {d.recent.length > 0 && (
        <div className="card mt-3"><div className="card-header"><h3>Recent Promotions</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="data-cards" style={{ padding: '1rem' }}>
            {d.recent.map((p, i) => (
              <div className="data-card" key={i}>
                <div className="data-card-header"><div className="data-card-title">{p.name}</div>
                  <span className={'badge ' + p.status_badge}>{p.status}</span></div>
                <div className="data-card-row"><span className="data-card-label">From</span><span>{p.from_class}</span></div>
                <div className="data-card-row"><span className="data-card-label">To</span><span>{p.to_class}</span></div>
                {p.stream && <div className="data-card-row"><span className="data-card-label">Stream</span><span>{p.stream}</span></div>}
              </div>
            ))}
          </div></div></div>
      )}
    </>
  );
}

// ---- Rules -----------------------------------------------------------------
function Rules({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const del = async (r) => {
    if (!await confirm('Delete this rule?')) return;
    setBusy(true);
    const res = await submitJson(r.delete_url, {});
    setBusy(false);
    if (res.ok) nav.refresh(); else notify('error', res.error || 'Could not delete.');
  };
  return (
    <>
      <PageHeader title="Promotion Rules" actions={canWrite(d) ? <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Rule</a> : null} />
      {d.rules.length ? (
        <div className="card"><div className="card-body" style={{ padding: 0 }}><div className="data-cards" style={{ padding: '1rem' }}>
          {d.rules.map((r) => (
            <div className="data-card" key={r.id}>
              <div className="data-card-header"><div className="data-card-title">{r.from_class} → {r.to_class}</div>
                {r.stream_name && <span className="badge badge-info">{r.stream_name}</span>}</div>
              <div className="data-card-row"><span className="data-card-label">Min Average</span><span>{r.min_average}%</span></div>
              <div className="data-card-row"><span className="data-card-label">Priority</span><span>{r.priority}</span></div>
              {r.required_count > 0 && <div className="data-card-row"><span className="data-card-label">Required Subjects</span><span>{r.required_count} subjects</span></div>}
              {canWrite(d) && <div className="data-card-actions">
                <button type="button" className="btn btn-danger btn-sm w-100" disabled={busy} onClick={() => del(r)}><i aria-hidden="true" className="fas fa-trash" /> Delete</button>
              </div>}
            </div>
          ))}
        </div></div></div>
      ) : (
        <div className="card"><div className="card-body"><Empty icon="fa-list-alt" title="No Rules">
          <p>Add promotion rules to define how students are promoted</p>
          {canWrite(d) && <a href={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Rule</a>}</Empty></div></div>
      )}
      <div className="card mt-3"><div className="card-header"><h3>How Rules Work</h3></div>
        <div className="card-body">
          <p><strong>Basic Promotion:</strong> Students meeting the promotion threshold are promoted to the next class.</p>
          <p><strong>Stream-based (SSS1 → SSS2):</strong> Create rules with different streams (Science, Arts, etc.) and required subjects. Higher priority rules are checked first.</p>
        </div></div>
    </>
  );
}

// ---- Add rule --------------------------------------------------------------
function AddRule({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ from_class_id: '', to_class_id: '', stream_name: '', min_average: '50', priority: '0' });
  const [subjects, setSubjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.from_class_id || !f.to_class_id) { notify('error', 'Select both classes.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, 'required_subjects[]': subjects });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const toggleSubj = (e) => setSubjects(Array.from(e.target.selectedOptions).map((o) => o.value));
  return (
    <>
      <PageHeader title="Add Promotion Rule" />
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-row">
          <div className="form-group"><label className="form-label">From Class <span className="required">*</span></label>
            <select className="form-control" required value={f.from_class_id} onChange={(e) => set('from_class_id', e.target.value)}>
              <option value="">Select</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">To Class <span className="required">*</span></label>
            <select className="form-control" required value={f.to_class_id} onChange={(e) => set('to_class_id', e.target.value)}>
              <option value="">Select</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        </div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Stream Name (optional)</label>
            <input type="text" className="form-control" placeholder="e.g., Science, Arts, Social Science" value={f.stream_name} onChange={(e) => set('stream_name', e.target.value)} />
            <small className="text-muted">Leave blank for basic promotion</small></div>
          <div className="form-group"><label className="form-label">Minimum Average (%)</label>
            <input type="number" className="form-control" min="0" max="100" step="0.5" value={f.min_average} onChange={(e) => set('min_average', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Priority</label>
            <input type="number" className="form-control" min="0" max="10" value={f.priority} onChange={(e) => set('priority', e.target.value)} />
            <small className="text-muted">Higher = checked first</small></div>
        </div>
        <div className="form-group"><label className="form-label">Required Subjects (for stream)</label>
          <select className="form-control" multiple size="8" value={subjects} onChange={toggleSubj}>
            {d.subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          <small className="text-muted">Hold Ctrl/Cmd to select multiple. Average of these subjects must meet minimum.</small></div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Rule</button>
          <a href={d.urls.rules} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Process ---------------------------------------------------------------
// Streams (class arms) available for a destination class, falling back to the
// global stream list when a class has no arms configured yet.
function streamsForClass(d, classId) {
  const byClass = (d.class_streams && d.class_streams[String(classId)]) || [];
  return byClass.length ? byClass : (d.streams || []);
}

function Process({ d, notify }) {
  const nav = useNav();
  const defaultClass = d.classes[0] ? String(d.classes[0].id) : '';
  const [rows, setRows] = useState(() => d.students.map((s) => ({
    id: s.id, action: s.recommendation.status === 'graduated' ? 'graduated'
      : (s.recommendation.status === 'promote' ? 'promoted' : (s.recommendation.status === 'repeat' ? 'repeated' : 'skip')),
    to_class_id: s.recommendation.to_class ? String(s.recommendation.to_class) : defaultClass,
    stream: s.recommendation.stream || '', average: s.average,
    isGrad: s.recommendation.status === 'graduated',
  })));
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);               // milestone summary, shown briefly before the log
  const [sel, setSel] = useState(() => new Set());      // selected student ids
  const [bulk, setBulk] = useState({ action: 'promoted', to_class_id: defaultClass, stream: '' });
  const setRow = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  // Only non-graduating rows can be bulk-promoted to a class/stream.
  const selectableIds = rows.filter((r) => !r.isGrad).map((r) => r.id);
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => sel.has(id));
  const toggleAll = () => setSel(allSelected ? new Set() : new Set(selectableIds));

  const applyBulk = () => {
    if (!sel.size) { notify('error', 'Select at least one student first.'); return; }
    setRows((rs) => rs.map((r) => (sel.has(r.id) && !r.isGrad ? {
      ...r, action: bulk.action,
      to_class_id: bulk.action === 'promoted' ? (bulk.to_class_id || r.to_class_id) : r.to_class_id,
      stream: bulk.action === 'promoted' && bulk.stream !== '' ? bulk.stream : r.stream,
    } : r)));
  };

  const submit = async () => {
    setBusy(true);
    const fields = { from_session_id: d.from_session_id, to_session_id: d.to_session_id,
      class_id: d.class_id,
      'student_id[]': rows.map((r) => r.id), 'average[]': rows.map((r) => r.average ?? ''),
      'action[]': rows.map((r) => r.action), 'to_class_id[]': rows.map((r) => r.to_class_id || ''),
      'stream[]': rows.map((r) => r.stream) };
    const res = await submitJson(d.execute_url, fields);
    if (res.ok) {
      // Celebrate the milestone with a summary of what just happened, then
      // continue to the promotion log. Keep `busy` so the button stays locked.
      const c = rows.reduce((a, r) => { a[r.action] = (a[r.action] || 0) + 1; return a; }, {});
      const parts = [];
      if (c.promoted) parts.push(`${c.promoted} promoted`);
      if (c.repeated) parts.push(`${c.repeated} repeating`);
      if (c.graduated) parts.push(`${c.graduated} graduating`);
      if (c.skip) parts.push(`${c.skip} skipped`);
      setDone(parts.join(' · ') || `${rows.length} students processed`);
      setTimeout(() => nav.go(res.redirect), 1700);
    } else { setBusy(false); notify('error', res.error || 'Could not save promotions.'); }
  };

  const bulkStreams = streamsForClass(d, bulk.to_class_id);

  return (
    <>
      {done && <SuccessBanner title="Promotions saved" summary={`${done} — opening the promotion log…`} />}
      <PageHeader title="Process Promotions" />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">From Session</label>
          <select className="form-control" value={d.from_session_id} onChange={(e) => navParams(nav.go, d.urls.self, { from_session_id: e.target.value, to_session_id: d.to_session_id, class_id: d.class_id })}>
            <option value="">Select Session</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">To Session</label>
          <select className="form-control" value={d.to_session_id} onChange={(e) => navParams(nav.go, d.urls.self, { from_session_id: d.from_session_id, to_session_id: e.target.value, class_id: d.class_id })}>
            <option value="">Select Session</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Class</label>
          <select className="form-control" value={d.class_id} onChange={(e) => navParams(nav.go, d.urls.self, { from_session_id: d.from_session_id, to_session_id: d.to_session_id, class_id: e.target.value })}>
            <option value="">Select Class</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      </div></div></div>

      {d.students.length ? (<>
        <div className="card mb-3"><div className="card-body">
          <p><strong>Promotion Threshold:</strong> {d.threshold}%</p>
          <p className="text-muted">Rows are pre-filled with the recommended action — just review and <strong>Save Promotions</strong>, or adjust exceptions below.</p>
          {(() => {
            const sum = rows.reduce((a, r) => { a[r.action] = (a[r.action] || 0) + 1; return a; }, {});
            const chip = (n, label, cls) => n ? <span className={'badge ' + cls} style={{ marginRight: '.4rem' }}>{n} {label}</span> : null;
            return <div style={{ marginTop: '.5rem' }}>
              {chip(sum.promoted, 'to promote', 'badge-success')}
              {chip(sum.repeated, 'to repeat', 'badge-warning')}
              {chip(sum.graduated, 'graduating', 'badge-info')}
              {chip(sum.skip, 'skipped', 'badge-secondary')}
            </div>;
          })()}
        </div></div>

        {/* Bulk action bar — apply one action/class/stream to all ticked students. */}
        <div className="card mb-3"><div className="card-body"><div className="filter-form" style={{ alignItems: 'flex-end' }}>
          <div className="form-group"><label className="form-label">With {sel.size} selected</label>
            <select className="form-control" value={bulk.action} onChange={(e) => setBulk((b) => ({ ...b, action: e.target.value }))}>
              <option value="promoted">Promote</option><option value="repeated">Repeat</option><option value="skip">Skip</option>
            </select></div>
          {bulk.action === 'promoted' && (<>
            <div className="form-group"><label className="form-label">Promote to</label>
              <select className="form-control" value={bulk.to_class_id} onChange={(e) => setBulk((b) => ({ ...b, to_class_id: e.target.value, stream: '' }))}>
                {d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Stream</label>
              <select className="form-control" value={bulk.stream} onChange={(e) => setBulk((b) => ({ ...b, stream: e.target.value }))}>
                <option value="">— No change —</option>
                {bulkStreams.map((nm) => <option key={nm} value={nm}>{nm}</option>)}</select></div>
          </>)}
          <div className="form-group"><button type="button" className="btn btn-secondary" onClick={applyBulk}><i aria-hidden="true" className="fas fa-wand-magic-sparkles" /> Apply to selected</button></div>
        </div></div></div>

        <div className="card">
          <div className="card-header"><h3>{d.selected_class_name} Students ({d.students.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container">
            <table className="data-table"><thead><tr>
              <th style={{ width: 32 }}><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all" /></th>
              <th>Student</th><th>Average</th><th>Recommendation</th><th>Action</th><th>Promote To</th><th>Stream</th></tr></thead>
              <tbody>{d.students.map((s, i) => {
                const r = rows[i];
                const isGrad = r.isGrad;
                const rowStreams = streamsForClass(d, r.to_class_id);
                // Keep the current value selectable even if not in the class's list.
                const opts = r.stream && !rowStreams.includes(r.stream) ? [r.stream, ...rowStreams] : rowStreams;
                return (
                  <tr key={s.id}>
                    <td>{isGrad ? null : <input type="checkbox" checked={sel.has(s.id)} onChange={() => toggle(s.id)} aria-label={'Select ' + s.name} />}</td>
                    <td>{s.name}<br /><small className="text-muted">{s.assignment}</small></td>
                    <td>{s.average != null ? <span className={'badge ' + (s.over_threshold ? 'badge-success' : 'badge-warning')}>{s.average}%</span> : <span className="text-muted">No scores</span>}</td>
                    <td>{s.existing_status ? <span className="badge badge-info">{s.existing_status}</span> : s.recommendation.message}</td>
                    <td><select className="form-control" style={{ width: 120 }} value={r.action} onChange={(e) => setRow(i, 'action', e.target.value)}>
                      <option value="skip">Skip</option>
                      {isGrad ? <option value="graduated">Graduate</option> : <><option value="promoted">Promote</option><option value="repeated">Repeat</option></>}
                    </select></td>
                    <td>{isGrad ? <span className="text-muted">N/A</span> : (
                      <select className="form-control" style={{ width: 110 }} value={r.to_class_id} onChange={(e) => setRow(i, 'to_class_id', e.target.value)}>
                        {d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>)}</td>
                    <td>{isGrad ? <span className="text-muted">N/A</span> : (
                      <select className="form-control" style={{ width: 120 }} value={r.stream} onChange={(e) => setRow(i, 'stream', e.target.value)}>
                        <option value="">— None —</option>
                        {opts.map((nm) => <option key={nm} value={nm}>{nm}</option>)}</select>)}</td>
                  </tr>
                );
              })}</tbody></table>
          </div></div>
          {canWrite(d) && <div className="card-body"><div className="page-header-actions">
            <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}><i aria-hidden="true" className="fas fa-save" /> Save Promotions</button>
          </div></div>}
        </div>
      </>) : (d.from_session_id && d.class_id
        ? <div className="card"><div className="card-body"><Empty icon="fa-users" title="No Students"><p>No students found for this class in the selected session's Third Term</p></Empty></div></div>
        : <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select Options"><p>Choose session and class to process promotions</p></Empty></div></div>)}
    </>
  );
}

// ---- Graduates -------------------------------------------------------------
function Graduates({ d }) {
  const nav = useNav();
  const docTypes = d.doc_types || [];
  const [bulkType, setBulkType] = useState(docTypes.length ? docTypes[0].type : '');
  const [q, setQ] = useState('');
  const males = d.graduates.filter((g) => g.gender === 'Male').length;
  const females = d.graduates.filter((g) => g.gender === 'Female').length;
  // Live search over the loaded graduates — matches name, student ID or session.
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return d.graduates;
    return d.graduates.filter((s) => (
      `${s.full_name} ${s.student_id} ${s.graduation_session || ''} ${s.status || ''}`
    ).toLowerCase().includes(t));
  }, [q, d.graduates]);
  const bulkHref = d.bulk_url && bulkType
    ? `${d.bulk_url}?doc_type=${encodeURIComponent(bulkType)}${d.session_id ? `&session_id=${d.session_id}` : ''}${d.status ? `&status=${encodeURIComponent(d.status)}` : ''}`
    : null;
  return (
    <>
      <PageHeader title="Graduates" actions={<>
        {d.alumni_url && <a href={d.alumni_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-address-book" /> Alumni{d.pending_requests > 0 ? <span className="badge badge-warning" style={{ marginLeft: '.4rem' }}>{d.pending_requests}</span> : null}</a>}
        {d.doc_templates_url && <a href={d.doc_templates_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-swatchbook" /> Designs</a>}
        {d.verifications_url && <a href={d.verifications_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-shield-halved" /> Verifications</a>}
        {d.compare_url && <a href={d.compare_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-chart-column" /> Compare with SSS3</a>}
        {canWrite(d) && <a href={d.preview_url} className="btn btn-success"><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate current SSS3</a>}
      </>} />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group" style={{ flex: '1 1 240px' }}><label className="form-label">Search graduates</label>
          <div className="enroll-search"><i aria-hidden="true" className="fas fa-search" />
            <input type="search" className="form-control" placeholder="Name or student ID…" autoComplete="off"
              value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
        <div className="form-group"><label className="form-label">Graduation Session</label>
          <select className="form-control" value={d.session_id} onChange={(e) => navParams(nav.go, window.location.pathname, { session_id: e.target.value, status: d.status || '' })}>
            <option value="">All Sessions</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="form-group"><label className="form-label">Status</label>
          <select className="form-control" value={d.status || ''} onChange={(e) => navParams(nav.go, window.location.pathname, { session_id: d.session_id || '', status: e.target.value })}>
            <option value="">All Statuses</option>{(d.statuses || []).map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
      </div></div></div>
      {d.graduates.length ? (<>
        <div className="stats-grid mb-3">
          <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-graduation-cap" /></div><div className="stat-content"><h3>{d.graduates.length}</h3><p>Total Graduates</p></div></div>
          <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-male" /></div><div className="stat-content"><h3>{males}</h3><p>Male</p></div></div>
          <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-female" /></div><div className="stat-content"><h3>{females}</h3><p>Female</p></div></div>
        </div>
        <div className="card"><div className="card-header"><h3>Graduates ({shown.length}{shown.length !== d.graduates.length ? ` of ${d.graduates.length}` : ''})</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="data-cards" style={{ padding: '1rem' }}>
            {shown.length === 0 && <p className="text-muted text-center" style={{ padding: '1rem', gridColumn: '1 / -1' }}>No graduates match “{q}”.</p>}
            {shown.map((s) => (
              <div className="data-card" key={s.id}>
                <div className="data-card-header"><div className="data-card-title">{s.full_name}</div><span className="badge badge-info">{s.status || 'Graduated'}</span></div>
                <div className="data-card-row"><span className="data-card-label">ID</span><span>{s.student_id}</span></div>
                <div className="data-card-row"><span className="data-card-label">Gender</span><span>{s.gender}</span></div>
                {s.graduation_date && <div className="data-card-row"><span className="data-card-label">Graduated</span><span>{s.graduation_date}</span></div>}
                {s.graduation_session && <div className="data-card-row"><span className="data-card-label">Session</span><span>{s.graduation_session}</span></div>}
                <div className="data-card-row"><span className="data-card-label">Results</span><span>
                  {s.has_waec && <span className="badge badge-info">WAEC</span>} {s.has_jamb && <span className="badge badge-primary">JAMB</span>}</span></div>
                <div className="data-card-actions"><a href={s.profile_url} className="btn btn-primary btn-sm w-100"><i aria-hidden="true" className="fas fa-eye" /> View Profile</a></div>
              </div>
            ))}
          </div></div></div>
      </>) : <div className="card"><div className="card-body"><Empty icon="fa-graduation-cap" title="No Graduates">
        <p>{d.session_id ? 'No graduates found for this session' : 'No students have been marked as graduated yet'}</p></Empty></div></div>}
    </>
  );
}

// ---- Graduate preview ------------------------------------------------------
function GraduatePreview({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const doGraduate = async () => {
    if (!await confirm(`Mark these ${d.students.length} SSS3 student(s) as graduates?`)) return;
    setBusy(true);
    const r = await submitJson(d.confirm_url, {});
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not graduate students.');
  };
  return (
    <>
      <PageHeader title={<><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate SSS3 — Review</>}
        actions={<a href={d.urls.graduates} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</a>} />
      <div className="card"><div className="card-header"><h3>Will be graduated ({d.students.length})</h3></div>
        <div className="card-body">
          {d.students.length ? (<>
            <div className="table-container" style={{ border: 'none' }}><table className="data-table">
              <thead><tr><th>#</th><th>Student ID</th><th>Name</th><th>Gender</th></tr></thead>
              <tbody>{d.students.map((s, i) => <tr key={i}><td>{i + 1}</td><td>{s.student_id}</td><td>{s.full_name}</td><td>{s.gender}</td></tr>)}</tbody>
            </table></div>
            <button type="button" className="btn btn-primary" style={{ marginTop: '1rem' }} disabled={busy} onClick={doGraduate}>
              <i aria-hidden="true" className="fas fa-user-graduate" /> Confirm — graduate {d.students.length} student(s)</button>
          </>) : <Empty icon="fa-circle-check" title=""><p>No new SSS3 students to graduate — they're all already graduated, or no SSS3 class is set up for the active term.</p></Empty>}
          {d.already_count > 0 && <p className="text-muted text-sm" style={{ marginTop: '1rem' }}><i aria-hidden="true" className="fas fa-info-circle" /> {d.already_count} SSS3 student(s) are already graduates and will be skipped.</p>}
        </div></div>
    </>
  );
}

// ---- Graduate profile ------------------------------------------------------
const NGN = (n) => '₦' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
const InfoRow = ({ label, value }) => (value || value === 0)
  ? <div className="info-row"><span className="text-muted">{label}</span><strong>{value}</strong></div> : null;

function GraduateProfile({ d, notify }) {
  const s = d.student;
  const rec = d.record || {};
  const bio = rec.bio || {};
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(d.status || 'Graduated');
  const [reason, setReason] = useState('');
  const [alu, setAlu] = useState(d.alumni || {});
  const [pw, setPw] = useState('');
  const setAluField = (k, v) => setAlu((a) => ({ ...a, [k]: v }));
  const saveAlumni = async () => {
    setBusy(true);
    const r = await submitJson(d.alumni_save_url, alu);
    setBusy(false);
    if (r.ok) notify && notify('success', r.message || 'Alumni details saved.');
    else notify && notify('error', r.error || 'Could not save.');
  };
  const savePassword = async () => {
    if (pw.length < 6) { notify && notify('error', 'Password must be at least 6 characters.'); return; }
    setBusy(true);
    const r = await submitJson(d.set_password_url, { password: pw });
    setBusy(false);
    if (r.ok) { notify && notify('success', r.message || 'Password set.'); setPw(''); }
    else notify && notify('error', r.error || 'Could not set password.');
  };
  const fulfilReq = (req) => { window.open(req.fulfil_url, '_blank'); setTimeout(() => nav.refresh && nav.refresh(), 1500); };
  const declineReq = async (req) => {
    if (!await confirm(`Decline the request for ${req.label}?`)) return;
    const r = await submitJson(req.decline_url, {});
    if (r.ok) { notify && notify('success', r.message || 'Request declined.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not decline.');
  };
  const undoGraduate = async () => {
    if (!await confirm(`Un-graduate ${s.full_name}? They will move back to active students and leave the Graduates list. Their records are kept.`)) return;
    setBusy(true);
    const r = await submitJson(d.urls.ungraduate, {});
    setBusy(false);
    if (r.ok) nav.go(r.redirect);
    else notify && notify('error', r.error || 'Could not un-graduate this student.');
  };
  const saveStatus = async () => {
    if (status === (d.status || 'Graduated')) { notify && notify('error', 'Pick a different status first.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.change_status, { status, reason });
    setBusy(false);
    if (r.ok) { notify && notify('success', r.message || 'Status updated.'); setReason(''); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not update status.');
  };
  const revokeDoc = async (doc) => {
    const verb = doc.revoked ? 'Reinstate' : 'Revoke';
    if (!await confirm(`${verb} ${doc.label}? ` + (doc.revoked
      ? 'It will verify as genuine again.'
      : 'It will verify as INVALID on the public portal.'))) return;
    const r = await submitJson(doc.revoke_url, {});
    if (r.ok) { notify && notify('success', r.message || 'Done.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not update the document.');
  };
  return (
    <>
      <div className="profile-hero">
        <div className="ph-cover" />
        <div className="ph-body">
          <div className="ph-avatar" style={{ background: 'linear-gradient(135deg,var(--primary),var(--primary-hover))' }} aria-hidden="true">
            {(s.full_name || '?').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'}
          </div>
          <div className="ph-id">
            <h1 className="ph-name">{s.full_name}</h1>
            <div className="ph-meta">
              <span className="badge badge-primary">{s.student_id}</span>
              {s.gender && <span className={'badge ' + (s.gender === 'Male' ? 'badge-info' : 'badge-warning')}>{s.gender}</span>}
              <span className="badge badge-success"><i aria-hidden="true" className="fas fa-user-graduate" /> {d.status || 'Graduated'}</span>
              {d.graduation_session && <span className="badge badge-secondary">Class of {d.graduation_session}</span>}
            </div>
          </div>
        </div>
        <div className="ph-actions">
          <a href={d.urls.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>
          <a href={d.urls.full_profile} className="btn btn-primary"><i aria-hidden="true" className="fas fa-user" /> Full Profile</a>
          {d.urls.ungraduate && <button type="button" className="btn btn-danger" disabled={busy} onClick={undoGraduate}>
            <i aria-hidden="true" className="fas fa-rotate-left" /> Un-graduate</button>}
        </div>
      </div>
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-graduation-cap" /> Graduation Info</h3></div>
        <div className="card-body"><div className="info-grid">
          <div className="info-row"><span className="text-muted">Status</span><strong><span className="badge badge-info">{d.status || 'Graduated'}</span></strong></div>
          {d.graduation_date && <div className="info-row"><span className="text-muted">Graduation Date</span><strong>{d.graduation_date}</strong></div>}
          {d.graduation_session && <div className="info-row"><span className="text-muted">Session</span><strong>{d.graduation_session}</strong></div>}
        </div></div></div>

      {d.urls.change_status && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-arrows-turn-right" /> Update Graduate Status</h3></div>
        <div className="card-body">
          <div className="form-row">
            <div className="form-group" style={{ flex: 1, minWidth: '180px' }}><label className="form-label">Status</label>
              <select className="form-control" value={status} onChange={(e) => setStatus(e.target.value)}>
                {(d.statuses || []).map((st) => <option key={st} value={st}>{st}</option>)}</select></div>
            <div className="form-group" style={{ flex: 2, minWidth: '220px' }}><label className="form-label">Reason <span className="text-muted">(recorded in the audit trail)</span></label>
              <input className="form-control" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Certificate collected on 12 Aug" /></div>
          </div>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={saveStatus}><i aria-hidden="true" className="fas fa-save" /> Update status</button>
        </div></div>}

      {(d.status_history && d.status_history.length > 0) && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Status History</h3></div>
        <div className="card-body"><div className="table-container" style={{ border: 'none' }}><table className="data-table table-stack no-mobile-scroll">
          <thead><tr><th>When</th><th>Change</th><th>Reason</th><th>By</th></tr></thead>
          <tbody>{d.status_history.map((h, i) => (
            <tr key={i}><td data-label="When">{h.at}</td><td data-label="Change">{h.old} → <strong>{h.new}</strong></td><td data-label="Reason">{h.reason || '—'}</td><td data-label="By">{h.actor || '—'}</td></tr>))}</tbody>
        </table></div></div></div>}

      {/* ---- Documents ---- */}
      {d.documents && d.documents.length > 0 && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-signature" /> Documents</h3></div>
        <div className="card-body"><div className="data-cards">
          {d.documents.map((doc) => (
            <div className="data-card" key={doc.type}>
              <div className="data-card-header"><div className="data-card-title">{doc.label}</div>
                {doc.revoked ? <span className="badge badge-danger">Revoked</span>
                  : doc.number ? <span className="badge badge-success">Issued</span>
                  : <span className="badge badge-secondary">Not issued</span>}</div>
              {doc.number && <div className="data-card-row"><span className="data-card-label">No.</span><span>{doc.number}</span></div>}
              {doc.reprint_count > 0 && <div className="data-card-row"><span className="data-card-label">Reprints</span><span>{doc.reprint_count}</span></div>}
              {doc.number && <div className="data-card-row"><span className="data-card-label">Verified</span><span>{doc.verify_count > 0 ? <span className="badge badge-info">{doc.verify_count}× checked</span> : <span style={{ color: 'var(--text-muted, #94a3b8)' }}>not yet</span>}</span></div>}
              {doc.verify_url && <div className="data-card-row"><span className="data-card-label">Verify</span><span><a href={doc.verify_url} target="_blank" rel="noopener noreferrer">link</a></span></div>}
              <div className="data-card-actions">
                <a href={doc.download_url} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm w-100">
                  <i aria-hidden="true" className={'fas ' + (doc.number ? 'fa-rotate' : 'fa-download')} /> {doc.number ? 'Re-issue / Download' : 'Generate & Download'}</a>
                {doc.number && doc.revoke_url && <button type="button"
                  className={'btn btn-sm w-100 ' + (doc.revoked ? 'btn-secondary' : 'btn-danger')}
                  style={{ marginTop: '.4rem' }} onClick={() => revokeDoc(doc)}>
                  <i aria-hidden="true" className={'fas ' + (doc.revoked ? 'fa-rotate-left' : 'fa-ban')} /> {doc.revoked ? 'Reinstate' : 'Revoke'}</button>}
              </div>
            </div>))}
        </div>
        <p className="text-muted text-sm" style={{ marginTop: '.6rem', marginBottom: 0 }}>
          <i aria-hidden="true" className="fas fa-qrcode" /> Each PDF carries a QR code + unique number; anyone can confirm it at the public verification page.</p>
        </div></div>}

      {/* ---- Document requests (from the alumni portal) ---- */}
      {d.doc_requests && d.doc_requests.length > 0 && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-inbox" /> Document Requests</h3></div>
        <div className="card-body"><div className="table-container" style={{ border: 'none' }}><table className="data-table table-stack no-mobile-scroll">
          <thead><tr><th>Document</th><th>Requested</th><th>Note</th><th>Status</th><th /></tr></thead>
          <tbody>{d.doc_requests.map((r) => (
            <tr key={r.id}>
              <td data-label="Document">{r.label}</td><td data-label="Requested">{r.requested_at}</td><td data-label="Note">{r.note || '—'}</td>
              <td data-label="Status"><span className={'badge ' + (r.status === 'pending' ? 'badge-warning' : r.status === 'fulfilled' ? 'badge-success' : 'badge-secondary')}>{r.status}</span></td>
              <td className="actions" style={{ whiteSpace: 'nowrap' }}>{r.status === 'pending' ? <>
                <button type="button" className="btn btn-success btn-sm" onClick={() => fulfilReq(r)}><i aria-hidden="true" className="fas fa-file-arrow-down" /> Issue</button>{' '}
                <button type="button" className="btn btn-danger btn-sm" onClick={() => declineReq(r)}><i aria-hidden="true" className="fas fa-xmark" /> Decline</button>
              </> : (r.response_note || '—')}</td>
            </tr>))}</tbody>
        </table></div></div></div>}

      {/* ---- Alumni details ---- */}
      {d.alumni_save_url && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-id-badge" /> Alumni Details</h3>
        {d.alumni && d.alumni.updated_at && <span className="text-muted text-sm">Updated {d.alumni.updated_at}{d.alumni.updated_by ? ` by ${d.alumni.updated_by}` : ''}</span>}</div>
        <div className="card-body">
          <div className="form-row" style={{ flexWrap: 'wrap', gap: '.6rem' }}>
            {[['occupation', 'Occupation'], ['job_title', 'Job title'], ['employer', 'Employer'],
              ['higher_institution', 'Higher institution'], ['course_of_study', 'Course of study'],
              ['phone', 'Phone'], ['email', 'Email'], ['linkedin_url', 'LinkedIn URL'],
              ['city', 'City'], ['country', 'Country']].map(([k, lab]) => (
              <div className="form-group" key={k} style={{ flex: '1 1 200px' }}>
                <label className="form-label">{lab}</label>
                <input className="form-control" value={alu[k] || ''} onChange={(e) => setAluField(k, e.target.value)} />
              </div>))}
          </div>
          <div className="form-group"><label className="form-label">Achievements</label>
            <textarea className="form-control" rows={2} value={alu.achievements || ''} onChange={(e) => setAluField('achievements', e.target.value)} /></div>
          <div className="form-group"><label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
            <input type="checkbox" checked={!!alu.willing_to_mentor} onChange={(e) => setAluField('willing_to_mentor', e.target.checked)} /> Willing to mentor current students</label></div>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={saveAlumni}><i aria-hidden="true" className="fas fa-save" /> Save alumni details</button>
        </div></div>}

      {/* ---- Portal access ---- */}
      {d.set_password_url && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-key" /> Alumni Portal Access</h3></div>
        <div className="card-body">
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>Set a portal password so this graduate can sign in at the alumni portal. They can also log in with a verification code from any document you issued them.</p>
          <div className="form-row" style={{ alignItems: 'flex-end', gap: '.6rem' }}>
            <div className="form-group" style={{ flex: 1, minWidth: '200px' }}><label className="form-label">New portal password</label>
              <input className="form-control" type="text" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="At least 6 characters" /></div>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={savePassword}><i aria-hidden="true" className="fas fa-key" /> Set password</button>
          </div>
          {d.alumni_login_url && <p className="text-muted text-sm" style={{ marginBottom: 0 }}>Portal: <a href={d.alumni_login_url} target="_blank" rel="noopener noreferrer">{d.alumni_login_url}</a></p>}
        </div></div>}

      {/* ---- Permanent record (read-only) ---- */}
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-id-card" /> Biodata</h3></div>
        <div className="card-body" style={{ display: 'flex', gap: '1.2rem', flexWrap: 'wrap' }}>
          {bio.photo_url ? <img src={bio.photo_url} alt="" style={{ width: 96, height: 96, objectFit: 'cover', borderRadius: 12, border: '1px solid var(--border-color)' }} /> : null}
          <div className="info-grid" style={{ flex: 1, minWidth: 240 }}>
            <InfoRow label="Date of Birth" value={bio.date_of_birth} />
            <InfoRow label="Admission Session" value={rec.admission_session} />
            <InfoRow label="House" value={bio.house} />
            <InfoRow label="Boarding" value={bio.boarding_status} />
            <InfoRow label="Stream" value={bio.stream} />
            <InfoRow label="Blood Group" value={bio.blood_group} />
            <InfoRow label="Genotype" value={bio.genotype} />
            <InfoRow label="Allergies" value={bio.allergies} />
            <InfoRow label="Religion" value={bio.religion} />
            <InfoRow label="Address" value={bio.home_address} />
            <InfoRow label="WAEC Subjects" value={bio.waec_subjects} />
            <InfoRow label="JAMB Subjects" value={bio.jamb_subjects} />
            <InfoRow label="JAMB Reg. No." value={bio.jamb_reg_number} />
          </div>
        </div></div>

      {rec.class_history && rec.class_history.length > 0 && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-timeline" /> Class &amp; Arm History</h3></div>
        <div className="card-body"><div className="table-container" style={{ border: 'none' }}><table className="data-table table-stack no-mobile-scroll">
          <thead><tr><th>Session</th><th>Term</th><th>Class</th><th>Arm</th></tr></thead>
          <tbody>{rec.class_history.map((h, i) => <tr key={i}><td data-label="Session">{h.session}</td><td data-label="Term">{h.term}</td><td data-label="Class">{h.klass}</td><td data-label="Arm">{h.arm}</td></tr>)}</tbody>
        </table></div></div></div>}

      {rec.academic && (rec.academic.terms_count > 0) && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-line" /> Academic History</h3>
        {rec.academic.cumulative != null && <span className="badge badge-primary">Cumulative avg: {rec.academic.cumulative}%</span>}</div>
        <div className="card-body">{rec.academic.terms.map((t, i) => (
          <div className="card" style={{ marginBottom: '1rem' }} key={i}>
            <div className="card-header"><span><strong>{t.session}</strong> · {t.term}</span>{t.average != null && <span className="text-muted">Term avg: {t.average}%</span>}</div>
            <div className="card-body" style={{ padding: 0 }}><div className="table-container" style={{ border: 'none' }}><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Subject</th><th>Score</th><th>Grade</th><th>Position</th><th>Remark</th></tr></thead>
              <tbody>{t.subjects.map((sub, j) => <tr key={j}><td data-label="Subject">{sub.subject}</td><td data-label="Score">{sub.score}</td><td data-label="Grade">{sub.grade || '—'}</td><td data-label="Position">{sub.position || '—'}</td><td data-label="Remark">{sub.remark || sub.comment || '—'}</td></tr>)}</tbody>
            </table></div></div>
          </div>))}</div></div>}

      <div className="stats-grid mb-3">
        {rec.attendance && rec.attendance.total > 0 && <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-calendar-check" /></div>
          <div className="stat-content"><h3>{rec.attendance.percent}%</h3><p>Attendance ({rec.attendance.present}/{rec.attendance.total})</p></div></div>}
        {rec.finance && <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-coins" /></div>
          <div className="stat-content"><h3>{NGN(rec.finance.total_paid)}</h3><p>Total fees paid ({rec.finance.count})</p></div></div>}
        {typeof rec.clinic_visits === 'number' && rec.clinic_visits > 0 && <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-notes-medical" /></div>
          <div className="stat-content"><h3>{rec.clinic_visits}</h3><p>Clinic visits</p></div></div>}
      </div>

      {rec.finance && rec.finance.recent && rec.finance.recent.length > 0 && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-receipt" /> Recent Fee Payments</h3></div>
        <div className="card-body"><div className="table-container" style={{ border: 'none' }}><table className="data-table table-stack no-mobile-scroll">
          <thead><tr><th>Date</th><th>Amount</th><th>Method</th><th>Receipt</th></tr></thead>
          <tbody>{rec.finance.recent.map((p, i) => <tr key={i}><td data-label="Date">{p.date}</td><td data-label="Amount">{NGN(p.amount)}</td><td data-label="Method">{p.method || '—'}</td><td data-label="Receipt">{p.receipt || '—'}</td></tr>)}</tbody>
        </table></div></div></div>}

      {rec.discipline && rec.discipline.length > 0 && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-gavel" /> Discipline Records</h3></div>
        <div className="card-body"><div className="table-container" style={{ border: 'none' }}><table className="data-table table-stack no-mobile-scroll">
          <thead><tr><th>Date</th><th>Category</th><th>Severity</th><th>Description</th><th>Action</th></tr></thead>
          <tbody>{rec.discipline.map((r, i) => <tr key={i}><td data-label="Date">{r.date}</td><td data-label="Category">{r.category}</td><td data-label="Severity">{r.severity || '—'}</td><td data-label="Description">{r.description || '—'}</td><td data-label="Action">{r.action || '—'}</td></tr>)}</tbody>
        </table></div></div></div>}

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-alt" /> WAEC Results</h3>
        {canWrite(d) && <a href={d.urls.add_waec} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}</div>
        <div className="card-body">{d.waec_by_year.length ? d.waec_by_year.map((data, i) => (
          <div className="card" style={{ marginBottom: '1rem' }} key={i}>
            <div className="card-header"><span><strong>{data.exam_year}</strong></span>{data.exam_number && <span className="text-muted">Exam No: {data.exam_number}</span>}</div>
            <div className="card-body"><div className="subjects-grid">{data.subjects.map((r, j) => (
              <div className="subject-item" key={j}><span>{r.subject}</span><span className={'grade-badge grade-' + r.grade}>{r.grade}</span></div>))}</div></div>
          </div>
        )) : <Empty icon="fa-file-alt" title=""><p>No WAEC results recorded</p>{canWrite(d) && <a href={d.urls.add_waec} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add WAEC Result</a>}</Empty>}</div></div>

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-contract" /> JAMB Results</h3>
        {canWrite(d) && <a href={d.urls.add_jamb} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}</div>
        <div className="card-body">{d.jamb_results.length ? d.jamb_results.map((j, i) => (
          <div className="card" style={{ marginBottom: '1rem' }} key={i}>
            <div className="card-header"><span><strong>{j.exam_year}</strong></span><span className="badge badge-primary" style={{ fontSize: 'var(--text-md)' }}>{j.total_score}</span></div>
            <div className="card-body">{j.registration_number && <p className="text-muted mb-2">Reg No: {j.registration_number}</p>}
              <div className="jamb-subjects">{j.subjects.map((sub, k) => (
                <div className="subject-item" key={k}><span>{sub.name}</span><strong>{sub.score}</strong></div>))}</div></div>
          </div>
        )) : <Empty icon="fa-file-contract" title=""><p>No JAMB results recorded</p>{canWrite(d) && <a href={d.urls.add_jamb} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add JAMB Result</a>}</Empty>}</div></div>

      {d.contacts.length > 0 && (
        <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-phone" /> Contact Information</h3></div>
          <div className="card-body"><div className="data-cards" style={{ padding: 0 }}>
            {d.contacts.map((c, i) => (
              <div className="data-card" key={i}>
                <div className="data-card-header"><div className="data-card-title">{c.name}</div><span className="badge badge-secondary">{c.relationship}</span></div>
                <div className="data-card-row"><span className="data-card-label">Phone</span><span>{c.phone}</span></div>
              </div>
            ))}
          </div></div></div>
      )}
    </>
  );
}

// ---- History ---------------------------------------------------------------
function History({ d }) {
  const nav = useNav();
  const count = (st) => d.records.filter((r) => r.status === st).length;
  return (
    <>
      <PageHeader title="Promotion History" />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Session</label>
          <select className="form-control" value={d.session_id} onChange={(e) => navParams(nav.go, window.location.pathname, { session_id: e.target.value })}>
            <option value="">Select Session</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
      </div></div></div>
      {d.records.length ? (<>
        <div className="stats-grid mb-3">
          <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-arrow-up" /></div><div className="stat-content"><h3>{count('promoted')}</h3><p>Promoted</p></div></div>
          <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-redo" /></div><div className="stat-content"><h3>{count('repeated')}</h3><p>Repeated</p></div></div>
          <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-graduation-cap" /></div><div className="stat-content"><h3>{count('graduated')}</h3><p>Graduated</p></div></div>
        </div>
        <div className="card"><div className="card-header"><h3>Records ({d.records.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="data-cards" style={{ padding: '1rem' }}>
            {d.records.map((r, i) => (
              <div className="data-card" key={i}>
                <div className="data-card-header"><div className="data-card-title">{r.name}</div><span className={'badge ' + r.status_badge}>{r.status}</span></div>
                <div className="data-card-row"><span className="data-card-label">From</span><span>{r.from_class}</span></div>
                <div className="data-card-row"><span className="data-card-label">To</span><span>{r.to_class}</span></div>
                {r.stream && <div className="data-card-row"><span className="data-card-label">Stream</span><span>{r.stream}</span></div>}
                {r.average != null && <div className="data-card-row"><span className="data-card-label">Average</span><span>{r.average}%</span></div>}
                {r.is_manual && <div className="data-card-row"><span className="data-card-label">Type</span><span className="badge badge-info">Manual</span></div>}
              </div>
            ))}
          </div></div></div>
      </>) : (d.session_id
        ? <div className="card"><div className="card-body"><Empty icon="fa-history" title="No Records"><p>No promotion records for this session</p></Empty></div></div>
        : <div className="card"><div className="card-body"><Empty icon="fa-hand-pointer" title="Select a Session"><p>Choose a session to view promotion history</p></Empty></div></div>)}
    </>
  );
}

// ---- Graduate vs SSS3 comparison -------------------------------------------
// One metric row: a labelled value for each cohort, with the better side hinted.
function CompareRow({ label, g, s, suffix = '', better = 'high', sNote }) {
  const fmt = (v) => (v == null ? '—' : v + suffix);
  let gHi = false, sHi = false;
  if (g != null && s != null && g !== s) {
    const gWins = better === 'high' ? g > s : g < s;
    gHi = gWins; sHi = !gWins;
  }
  const cell = (v, hi) => <td style={{ textAlign: 'right', fontWeight: hi ? 700 : 400, color: hi ? 'var(--success, #2e7d32)' : 'inherit' }}>{fmt(v)}</td>;
  return (
    <tr>
      <td>{label}</td>
      {cell(g, gHi)}
      {s == null && sNote ? <td style={{ textAlign: 'right' }} className="text-muted">{sNote}</td> : cell(s, sHi)}
    </tr>
  );
}

function WaecCompareTable({ g, s }) {
  const sNull = s == null;
  return (
    <table className="data-table">
      <thead><tr><th>Metric</th><th style={{ textAlign: 'right' }}>Graduates</th><th style={{ textAlign: 'right' }}>Current SSS3</th></tr></thead>
      <tbody>
        <CompareRow label="Students with results" g={g ? g.n : 0} s={sNull ? null : s.n} sNote={sNull ? 'no real WAEC yet' : ''} />
        <CompareRow label="Avg credits (C6+)" g={g ? g.avg_credits : null} s={sNull ? null : s.avg_credits} sNote={sNull ? '—' : ''} />
        <CompareRow label="Avg distinctions (B3+)" g={g ? g.avg_distinctions : null} s={sNull ? null : s.avg_distinctions} sNote={sNull ? '—' : ''} />
        <CompareRow label="% with 5+ credits" g={g ? g.pct_5_credits : null} s={sNull ? null : s.pct_5_credits} suffix="%" sNote={sNull ? '—' : ''} />
        <CompareRow label="% with 5 incl. Eng & Maths" g={g ? g.pct_5_incl_core : null} s={sNull ? null : s.pct_5_incl_core} suffix="%" sNote={sNull ? '—' : ''} />
      </tbody>
    </table>
  );
}

function JambCompareTable({ g, s }) {
  const sNull = s == null;
  return (
    <table className="data-table">
      <thead><tr><th>Metric</th><th style={{ textAlign: 'right' }}>Graduates</th><th style={{ textAlign: 'right' }}>Current SSS3</th></tr></thead>
      <tbody>
        <CompareRow label="Students with results" g={g ? g.n : 0} s={sNull ? null : s.n} sNote={sNull ? 'no real JAMB yet' : ''} />
        <CompareRow label="Average score" g={g ? g.avg_score : null} s={sNull ? null : s.avg_score} sNote={sNull ? '—' : ''} />
        <CompareRow label="Highest score" g={g ? g.max_score : null} s={sNull ? null : s.max_score} sNote={sNull ? '—' : ''} />
        <CompareRow label="% scoring 180+" g={g ? g.pct_above_floor : null} s={sNull ? null : s.pct_above_floor} suffix="%" sNote={sNull ? '—' : ''} />
      </tbody>
    </table>
  );
}

function GradeDistRow({ name, g, s, order }) {
  const cells = (dist) => order.map((gr) => <td key={gr} style={{ textAlign: 'center' }}>{dist && dist[gr] ? dist[gr] : '·'}</td>);
  return (<>
    <tr><td colSpan={order.length + 1} style={{ background: 'var(--bg-tertiary)', fontWeight: 600 }}>{name}</td></tr>
    <tr><td className="text-muted">Graduates</td>{cells(g)}</tr>
    {s && <tr><td className="text-muted">Current SSS3</td>{cells(s)}</tr>}
  </>);
}

function GraduateCompare({ d }) {
  const nav = useNav();
  const c = d.comparison;
  const cohorts = c.cohorts;
  const noData = cohorts.graduates.total === 0;
  const dirBadge = (p) => {
    if (!p) return null;
    const cls = p.direction === 'improved' ? 'badge-success' : p.direction === 'declined' ? 'badge-danger' : 'badge-secondary';
    const sign = p.avg_delta > 0 ? '+' : '';
    return <span className={'badge ' + cls}>{p.direction} ({sign}{p.avg_delta})</span>;
  };
  return (
    <>
      <PageHeader title="Graduates vs Current SSS3"
        actions={<a href={d.urls.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>} />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Graduate cohort (session)</label>
          <select className="form-control" value={d.session_id} onChange={(e) => navParams(nav.go, d.urls.self, { session_id: e.target.value })}>
            <option value="">All graduates</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
      </div></div></div>

      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-graduation-cap" /></div>
          <div className="stat-content"><h3>{cohorts.graduates.total}</h3><p>{cohorts.graduates.label}</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-users" /></div>
          <div className="stat-content"><h3>{cohorts.sss3.total}</h3><p>{cohorts.sss3.label}</p></div></div>
      </div>

      {noData ? (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-column" title="No graduates to compare">
          <p>Once a cohort has been graduated (with mock/real results recorded), this page compares them against the current SSS3 class.</p></Empty></div></div>
      ) : (<>
        <div className="card mb-3"><div className="card-body">
          <p className="text-muted" style={{ margin: 0 }}><i aria-hidden="true" className="fas fa-circle-info" /> Real WAEC/JAMB exists only for graduates. The <strong>mock</strong> rows compare both cohorts on the same exams; the graduates' mock→real pattern below projects where the current class may land.</p>
        </div></div>

        {/* WAEC */}
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-alt" /> WAEC — Real</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><WaecCompareTable g={c.real_waec.graduates} s={c.real_waec.sss3} /></div></div></div>
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-alt" /> WAEC — Mock (latest sitting)</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><WaecCompareTable g={c.mock_waec.graduates} s={c.mock_waec.sss3} /></div></div></div>

        {/* Grade spread */}
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-layer-group" /> WAEC grade spread</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><table className="data-table">
            <thead><tr><th>Cohort</th>{c.grade_order.map((g) => <th key={g} style={{ textAlign: 'center' }}>{g}</th>)}</tr></thead>
            <tbody>
              <GradeDistRow name="Real WAEC" order={c.grade_order} g={c.real_waec.graduates && c.real_waec.graduates.grade_distribution} s={null} />
              <GradeDistRow name="Mock WAEC" order={c.grade_order} g={c.mock_waec.graduates && c.mock_waec.graduates.grade_distribution} s={c.mock_waec.sss3 && c.mock_waec.sss3.grade_distribution} />
            </tbody>
          </table></div></div></div>

        {/* JAMB */}
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-contract" /> JAMB — Real</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><JambCompareTable g={c.real_jamb.graduates} s={c.real_jamb.sss3} /></div></div></div>
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-contract" /> JAMB — Mock (best)</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><JambCompareTable g={c.mock_jamb.graduates} s={c.mock_jamb.sss3} /></div></div></div>

        {/* Pattern + projection */}
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-arrow-trend-up" /> Mock → Real pattern (graduates) &amp; projection</h3></div>
          <div className="card-body">
            <div className="info-grid">
              <div className="info-row"><span className="text-muted">WAEC credits: real vs mock</span><strong>{c.pattern.waec_credits ? dirBadge(c.pattern.waec_credits) : <span className="text-muted">not enough paired data</span>}</strong></div>
              {c.pattern.waec_credits && <div className="info-row"><span className="text-muted">Graduates who beat their mock (WAEC)</span><strong>{c.pattern.waec_credits.pct_improved}% of {c.pattern.waec_credits.n}</strong></div>}
              <div className="info-row"><span className="text-muted">JAMB score: real vs mock</span><strong>{c.pattern.jamb_score ? dirBadge(c.pattern.jamb_score) : <span className="text-muted">not enough paired data</span>}</strong></div>
              {c.pattern.jamb_score && <div className="info-row"><span className="text-muted">Graduates who beat their mock (JAMB)</span><strong>{c.pattern.jamb_score.pct_improved}% of {c.pattern.jamb_score.n}</strong></div>}
            </div>
            {(c.projection.waec || c.projection.jamb) && (
              <div className="card mt-3" style={{ background: 'var(--bg-tertiary)' }}><div className="card-body">
                <h4 style={{ marginTop: 0 }}><i aria-hidden="true" className="fas fa-wand-magic-sparkles" /> Projection for current SSS3</h4>
                <p className="text-muted text-sm">Applying the graduates' mock→real shift to the current class's mock averages.</p>
                {c.projection.waec && <p>WAEC credits: mock avg <strong>{c.projection.waec.mock_avg_credits}</strong> → projected real <strong>{c.projection.waec.projected_avg_credits}</strong> <span className="text-muted">(shift {c.projection.waec.shift > 0 ? '+' : ''}{c.projection.waec.shift}, from {c.projection.waec.basis_n} graduates)</span></p>}
                {c.projection.jamb && <p>JAMB score: mock avg <strong>{c.projection.jamb.mock_avg_score}</strong> → projected real <strong>{c.projection.jamb.projected_avg_score}</strong> <span className="text-muted">(shift {c.projection.jamb.shift > 0 ? '+' : ''}{c.projection.jamb.shift}, from {c.projection.jamb.basis_n} graduates)</span></p>}
              </div></div>
            )}
          </div></div>

        {/* Subject pass rates side by side */}
        {(c.mock_waec.graduates.subject_pass_rates.length > 0 || (c.mock_waec.sss3 && c.mock_waec.sss3.subject_pass_rates.length > 0)) && (
          <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-list-check" /> Mock WAEC subject pass rates</h3></div>
            <div className="card-body" style={{ padding: 0 }}><div className="table-container"><table className="data-table">
              <thead><tr><th>Subject</th><th style={{ textAlign: 'right' }}>Graduates</th><th style={{ textAlign: 'right' }}>Current SSS3</th></tr></thead>
              <tbody>{(() => {
                const gMap = {}; c.mock_waec.graduates.subject_pass_rates.forEach((r) => { gMap[r.subject] = r.pass_rate; });
                const sMap = {}; (c.mock_waec.sss3 ? c.mock_waec.sss3.subject_pass_rates : []).forEach((r) => { sMap[r.subject] = r.pass_rate; });
                const subjects = Array.from(new Set([...Object.keys(gMap), ...Object.keys(sMap)])).sort();
                return subjects.map((sub) => <CompareRow key={sub} label={sub} g={gMap[sub] != null ? gMap[sub] : null} s={sMap[sub] != null ? sMap[sub] : null} suffix="%" />);
              })()}</tbody>
            </table></div></div></div>
        )}
      </>)}
    </>
  );
}

// ---- Alumni directory + advanced search + export + bulk email (admin) -----
function _qsFromFilters(f) {
  const p = {};
  ['q', 'occupation', 'employer', 'institution', 'city', 'country'].forEach((k) => { if (f[k]) p[k] = f[k]; });
  if (f.session_id) p.session_id = f.session_id;
  if (f.mentor) p.mentor = '1';
  if (f.career) p.career = '1';
  if (f.has_contact) p.has_contact = '1';
  return p;
}

function Alumni({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState(d.filters || {});
  const [mail, setMail] = useState({ open: false, subject: '', body: '', busy: false });
  const setField = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const applyFilters = () => navParams(nav.go, window.location.pathname, _qsFromFilters(f));
  const clearFilters = () => { setF({}); navParams(nav.go, window.location.pathname, {}); };
  const exportUrl = d.export_url + '?' + new URLSearchParams(_qsFromFilters(f)).toString();

  const fulfilReq = (r) => { window.open(r.fulfil_url, '_blank'); setTimeout(() => nav.refresh && nav.refresh(), 1500); };
  const declineReq = async (r) => {
    if (!await confirm(`Decline ${r.student_name}'s request for ${r.label}?`)) return;
    const res = await submitJson(r.decline_url, {});
    if (res.ok) { notify && notify('success', res.message || 'Declined.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', res.error || 'Could not decline.');
  };
  const sendMail = async () => {
    if (!mail.subject.trim() || !mail.body.trim()) { notify && notify('error', 'Subject and message are required.'); return; }
    if (!await confirm('Send this email to every alumnus in the current filter who has an email address?')) return;
    setMail((m) => ({ ...m, busy: true }));
    const r = await submitJson(d.bulk_email_url, { subject: mail.subject, body: mail.body, ..._qsFromFilters(f) });
    setMail((m) => ({ ...m, busy: false }));
    if (r.ok) { notify && notify('success', r.message || 'Sending.'); setMail({ open: false, subject: '', body: '', busy: false }); }
    else notify && notify('error', r.error || 'Could not send.');
  };

  return (
    <>
      <PageHeader title="Alumni" actions={<>
        <a href={d.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Graduates</a>
        {d.analytics_url && <a href={d.analytics_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-chart-pie" /> Analytics</a>}
        <a href={exportUrl} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-csv" /> Export CSV</a>
        <button type="button" className="btn btn-primary" onClick={() => setMail((m) => ({ ...m, open: !m.open }))}><i aria-hidden="true" className="fas fa-envelope" /> Bulk email</button>
      </>} />
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-user-graduate" /></div><div className="stat-content"><h3>{d.total}</h3><p>Graduates</p></div></div>
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-filter" /></div><div className="stat-content"><h3>{d.shown}</h3><p>Matching filter</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-hands-helping" /></div><div className="stat-content"><h3>{d.mentors}</h3><p>Willing to mentor</p></div></div>
        <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-inbox" /></div><div className="stat-content"><h3>{(d.requests || []).length}</h3><p>Pending requests</p></div></div>
      </div>

      {mail.open && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-envelope" /> Bulk Email — {d.contactable} contactable in this filter</h3></div>
        <div className="card-body">
          {!d.email_configured && <p className="text-warning"><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Email is not configured on this server; sending will fail until SMTP is set up.</p>}
          <div className="form-group"><label className="form-label">Subject</label>
            <input className="form-control" value={mail.subject} onChange={(e) => setMail((m) => ({ ...m, subject: e.target.value }))} /></div>
          <div className="form-group"><label className="form-label">Message</label>
            <textarea className="form-control" rows={5} value={mail.body} onChange={(e) => setMail((m) => ({ ...m, body: e.target.value }))} /></div>
          <button type="button" className="btn btn-primary" disabled={mail.busy || !d.email_configured} onClick={sendMail}><i aria-hidden="true" className="fas fa-paper-plane" /> Send to filtered alumni</button>
        </div></div>}

      {d.requests && d.requests.length > 0 && <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-inbox" /> Pending Document Requests</h3></div>
        <div className="card-body" style={{ padding: 0 }}><div className="table-container" style={{ border: 'none' }}><table className="data-table">
          <thead><tr><th>Graduate</th><th>Document</th><th>Note</th><th>Requested</th><th /></tr></thead>
          <tbody>{d.requests.map((r) => (
            <tr key={r.id}>
              <td><a href={r.profile_url}>{r.student_name}</a><br /><span className="text-muted text-sm">{r.admission_no}</span></td>
              <td>{r.label}</td><td>{r.note || '—'}</td><td>{r.requested_at}</td>
              <td style={{ whiteSpace: 'nowrap' }}>
                <button type="button" className="btn btn-success btn-sm" onClick={() => fulfilReq(r)}><i aria-hidden="true" className="fas fa-file-arrow-down" /> Issue</button>{' '}
                <button type="button" className="btn btn-danger btn-sm" onClick={() => declineReq(r)}><i aria-hidden="true" className="fas fa-xmark" /> Decline</button>
              </td>
            </tr>))}</tbody>
        </table></div></div></div>}

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-magnifying-glass" /> Search &amp; Filter</h3></div>
        <div className="card-body">
          <div className="form-row" style={{ flexWrap: 'wrap', gap: '.6rem' }}>
            <div className="form-group" style={{ flex: '2 1 220px' }}><label className="form-label">Name or Admission No.</label>
              <input className="form-control" value={f.q || ''} onChange={(e) => setField('q', e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') applyFilters(); }} /></div>
            <div className="form-group" style={{ flex: '1 1 160px' }}><label className="form-label">Graduation Session</label>
              <select className="form-control" value={f.session_id || ''} onChange={(e) => setField('session_id', e.target.value)}>
                <option value="">All</option>{(d.sessions || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
            {[['occupation', 'Occupation'], ['employer', 'Employer'], ['institution', 'Institution'], ['city', 'City'], ['country', 'Country']].map(([k, lab]) => (
              <div className="form-group" key={k} style={{ flex: '1 1 150px' }}><label className="form-label">{lab}</label>
                <input className="form-control" value={f[k] || ''} onChange={(e) => setField(k, e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') applyFilters(); }} /></div>))}
          </div>
          <div style={{ display: 'flex', gap: '1.2rem', flexWrap: 'wrap', margin: '.4rem 0 .8rem' }}>
            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
              <input type="checkbox" checked={!!f.mentor} onChange={(e) => setField('mentor', e.target.checked)} /> Mentors only</label>
            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
              <input type="checkbox" checked={!!f.career} onChange={(e) => setField('career', e.target.checked)} /> Has career/education info</label>
            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
              <input type="checkbox" checked={!!f.has_contact} onChange={(e) => setField('has_contact', e.target.checked)} /> Has phone/email</label>
          </div>
          <button type="button" className="btn btn-primary" onClick={applyFilters}><i aria-hidden="true" className="fas fa-magnifying-glass" /> Search</button>{' '}
          <button type="button" className="btn btn-secondary" onClick={clearFilters}><i aria-hidden="true" className="fas fa-rotate-left" /> Clear</button>
        </div></div>

      <div className="card"><div className="card-header"><h3>Alumni Directory ({(d.alumni || []).length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {(d.alumni || []).length ? <div className="table-container" style={{ border: 'none' }}><table className="data-table">
            <thead><tr><th>Name</th><th>Occupation</th><th>Employer / Institution</th><th>Contact</th><th>Mentor</th><th /></tr></thead>
            <tbody>{d.alumni.map((a) => (
              <tr key={a.id}>
                <td><a href={a.profile_url}>{a.full_name}</a><br /><span className="text-muted text-sm">{a.student_id}</span></td>
                <td>{a.occupation || '—'}</td>
                <td>{a.employer || a.higher_institution || '—'}</td>
                <td>{a.phone || a.email || '—'}</td>
                <td>{a.willing_to_mentor ? <span className="badge badge-success">Yes</span> : '—'}</td>
                <td><a href={a.profile_url} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-eye" /> View</a></td>
              </tr>))}</tbody>
          </table></div> : <div style={{ padding: '1rem' }}><Empty icon="fa-address-book" title="No alumni match"><p>No graduates match the current filters.</p></Empty></div>}
        </div></div>
    </>
  );
}

// ---- Alumni analytics -----------------------------------------------------
function BreakdownCard({ title, icon, rows }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return null;
  return (
    <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className={'fas ' + icon} /> {title}</h3></div>
      <div className="card-body">{rows.map((r, i) => (
        <div key={i} style={{ marginBottom: '.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.9rem' }}><span>{r.label}</span><strong>{r.count}</strong></div>
          <div style={{ height: 8, background: 'var(--border-color,#eee)', borderRadius: 6, overflow: 'hidden' }}>
            <div style={{ width: `${(r.count / max) * 100}%`, height: '100%', background: 'var(--primary,#0d6a4e)' }} /></div>
        </div>))}</div></div>
  );
}

function AlumniAnalytics({ d }) {
  const req = d.requests || {};
  return (
    <>
      <PageHeader title="Alumni Analytics" actions={
        <a href={d.alumni_dir} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Directory</a>} />
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-user-graduate" /></div><div className="stat-content"><h3>{d.total}</h3><p>Graduates</p></div></div>
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-id-badge" /></div><div className="stat-content"><h3>{d.with_profile}</h3><p>With alumni profile</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-briefcase" /></div><div className="stat-content"><h3>{d.employed}</h3><p>Employed</p></div></div>
        <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-graduation-cap" /></div><div className="stat-content"><h3>{d.higher_ed}</h3><p>In higher education</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-hands-helping" /></div><div className="stat-content"><h3>{d.mentors}</h3><p>Willing to mentor</p></div></div>
        <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-address-card" /></div><div className="stat-content"><h3>{d.contactable}</h3><p>Contactable</p></div></div>
      </div>
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-file-signature" /></div><div className="stat-content"><h3>{d.docs_total}</h3><p>Documents issued</p></div></div>
        <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-hourglass-half" /></div><div className="stat-content"><h3>{req.pending || 0}</h3><p>Requests pending</p></div></div>
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-check" /></div><div className="stat-content"><h3>{req.fulfilled || 0}</h3><p>Requests fulfilled</p></div></div>
        <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-xmark" /></div><div className="stat-content"><h3>{req.declined || 0}</h3><p>Requests declined</p></div></div>
      </div>
      <BreakdownCard title="By graduation session" icon="fa-calendar" rows={d.by_session || []} />
      <BreakdownCard title="By status" icon="fa-flag" rows={d.by_status || []} />
      <BreakdownCard title="Top employers" icon="fa-building" rows={d.top_employers || []} />
      <BreakdownCard title="Top institutions" icon="fa-university" rows={d.top_institutions || []} />
      <BreakdownCard title="Top occupations" icon="fa-briefcase" rows={d.top_occupations || []} />
      <BreakdownCard title="Top locations" icon="fa-location-dot" rows={d.top_locations || []} />
      <BreakdownCard title="Documents by type" icon="fa-file-lines" rows={d.docs_by_type || []} />
    </>
  );
}

// ---- Document branding studio --------------------------------------------
function BrandingStudio({ d, notify }) {
  const nav = useNav();
  const b = d.branding || {};
  const [primary, setPrimary] = useState(b.primary_color || '');
  const [accent, setAccent] = useState(b.accent_color || '');
  const [secondary, setSecondary] = useState(b.secondary_color || '');
  const [motto, setMotto] = useState(b.motto || '');
  const [verify, setVerify] = useState(b.verify_enabled !== false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const save = async () => {
    setBusy(true);
    const r = await submitJson(d.branding_save_url, {
      primary_color: primary, accent_color: accent, secondary_color: secondary,
      motto, verify_enabled: verify ? '1' : '0',
    });
    setBusy(false);
    if (r.ok) { notify && notify('success', r.message || 'Branding saved.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not save branding.');
  };
  const swatch = (label, val, set) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: '.25rem', fontSize: '.85rem' }}>
      <span className="text-muted">{label}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
        <input type="color" value={val || '#0e3a2f'} onChange={(e) => set(e.target.value)}
          style={{ width: 40, height: 32, padding: 0, border: '1px solid var(--border,#cbd5e1)', borderRadius: 6 }} />
        <input type="text" value={val} placeholder="default" onChange={(e) => set(e.target.value)}
          className="form-control" style={{ width: 100 }} />
        {val && <button type="button" className="btn btn-secondary btn-sm" onClick={() => set('')}>Reset</button>}
      </span>
    </label>
  );
  return (
    <div className="card mb-3"><div className="card-body">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setOpen((o) => !o)}>
        <strong><i aria-hidden="true" className="fas fa-palette" /> Branding studio</strong>
        <span className="text-muted text-sm">Colours &amp; motto override every design · <i className={'fas fa-chevron-' + (open ? 'up' : 'down')} aria-hidden="true" /></span>
      </div>
      {open && <div style={{ marginTop: '.9rem' }}>
        <div style={{ display: 'flex', gap: '1.2rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          {swatch('Primary', primary, setPrimary)}
          {swatch('Accent', accent, setAccent)}
          {swatch('Secondary / gold', secondary, setSecondary)}
          <label style={{ display: 'flex', flexDirection: 'column', gap: '.25rem', fontSize: '.85rem', flex: '1 1 220px' }}>
            <span className="text-muted">Motto</span>
            <input type="text" value={motto} onChange={(e) => setMotto(e.target.value)}
              className="form-control" placeholder="e.g. Knowledge, Integrity, Service" maxLength={160} />
          </label>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem', marginTop: '.8rem', fontSize: '.9rem' }}>
          <input type="checkbox" checked={verify} onChange={(e) => setVerify(e.target.checked)} />
          Show QR verification block on issued documents
        </label>
        <div style={{ marginTop: '.9rem' }}>
          <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={save}>
            <i aria-hidden="true" className="fas fa-save" /> {busy ? 'Saving…' : 'Save branding'}</button>
          <span className="text-muted text-sm" style={{ marginLeft: '.6rem' }}>Previews update after saving.</span>
        </div>
      </div>}
    </div></div>
  );
}

// ---- Document design templates (admin) ------------------------------------
function DocTemplates({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState('');
  const setDefault = async (t) => {
    setBusy(t.key);
    const r = await submitJson(t.set_url, { template_key: t.key });
    setBusy('');
    if (r.ok) { notify && notify('success', r.message || 'Default set.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not set default.');
  };
  const groups = d.doc_types_grouped || [];
  return (
    <>
      <PageHeader title="Document Designs" actions={
        <a href={d.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>} />
      {d.branding_save_url && <BrandingStudio d={d} notify={notify} />}
      {groups.length > 0 ? (
        <div className="mb-3">
          {groups.map((g) => (
            <div key={g.category} style={{ marginBottom: '.6rem' }}>
              <div className="text-muted text-sm" style={{ marginBottom: '.3rem', textTransform: 'uppercase', letterSpacing: '.03em' }}>{g.category}</div>
              <div style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
                {g.items.map((dt) => (
                  <a key={dt.key} href={dt.url} className={'btn btn-sm ' + (dt.key === d.doc_type ? 'btn-primary' : 'btn-secondary')}>{dt.label}</a>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (d.doc_types && d.doc_types.length > 1 && <div className="tabs mb-3" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
        {d.doc_types.map((dt) => (
          <a key={dt.key} href={dt.url} className={'btn btn-sm ' + (dt.key === d.doc_type ? 'btn-primary' : 'btn-secondary')}>{dt.label}</a>
        ))}</div>)}
      <div className="card mb-3"><div className="card-body">
        <p className="text-muted" style={{ margin: 0 }}>
          <i aria-hidden="true" className="fas fa-circle-info" /> Choose the design used when you issue a {d.doc_type_label.toLowerCase()}.
          Every design shows your school's own details — only the layout changes. Previews use sample data.
        </p></div></div>
      <div className="data-cards">
        {(d.templates || []).map((t) => (
          <div className="data-card" key={t.key} style={t.is_default ? { borderColor: 'var(--primary,#0e8a64)', borderWidth: 2 } : null}>
            <div className="data-card-header">
              <div className="data-card-title">{t.name}</div>
              {t.is_default ? <span className="badge badge-success"><i aria-hidden="true" className="fas fa-check" /> Default</span>
                : <span className="badge badge-secondary">Available</span>}
            </div>
            <p className="text-sm text-muted" style={{ minHeight: '2.6em' }}>{t.description}</p>
            <div className="data-card-actions">
              <a href={t.preview_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm w-100">
                <i aria-hidden="true" className="fas fa-eye" /> Preview</a>
              <button type="button" className="btn btn-primary btn-sm w-100" style={{ marginTop: '.4rem' }}
                disabled={t.is_default || busy === t.key} onClick={() => setDefault(t)}>
                <i aria-hidden="true" className="fas fa-star" /> {t.is_default ? 'Current default' : 'Set as default'}</button>
            </div>
          </div>))}
      </div>
    </>
  );
}

// ---- Document verification activity (admin) -------------------------------
const _VBADGE = { valid: 'badge-success', revoked: 'badge-danger', not_found: 'badge-warning' };
const _VLABEL = { valid: 'Valid', revoked: 'Revoked', not_found: 'Unknown code' };

function VerifyRow({ v }) {
  return (
    <tr>
      <td>{v.at}</td>
      <td><span className={'badge ' + (_VBADGE[v.result] || 'badge-secondary')}>{_VLABEL[v.result] || v.result}</span></td>
      <td>{v.doc_label}</td>
      <td>{v.student_url ? <a href={v.student_url}>{v.student}</a> : (v.student || '—')}</td>
      <td><code>{v.code}</code></td>
      <td>{v.source === 'qr' ? <span title="QR link scanned"><i aria-hidden="true" className="fas fa-qrcode" /> Scan</span> : 'Typed'}</td>
    </tr>
  );
}

function DocVerifications({ d }) {
  const nav = useNav();
  const s = d.summary || {};
  const table = (rows) => (
    <div className="table-responsive"><table className="data-table"><thead><tr>
      <th>When</th><th>Result</th><th>Document</th><th>Graduate</th><th>Code</th><th>Via</th>
    </tr></thead><tbody>{rows.map((v) => <VerifyRow key={v.id} v={v} />)}</tbody></table></div>
  );
  return (
    <>
      <PageHeader title="Verification Activity" actions={
        <a href={d.urls.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>} />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Period</label>
          <select className="form-control" value={d.days} onChange={(e) => navParams(nav.go, window.location.pathname, { days: e.target.value })}>
            {[30, 90, 180, 365].map((n) => <option key={n} value={n}>Last {n} days</option>)}</select></div>
      </div></div></div>
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-magnifying-glass" /></div><div className="stat-content"><h3>{s.total || 0}</h3><p>Total checks</p></div></div>
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-circle-check" /></div><div className="stat-content"><h3>{s.valid || 0}</h3><p>Verified genuine</p></div></div>
        <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-ban" /></div><div className="stat-content"><h3>{s.revoked || 0}</h3><p>Revoked-doc checks</p></div></div>
        <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-triangle-exclamation" /></div><div className="stat-content"><h3>{s.not_found || 0}</h3><p>Unknown codes</p></div></div>
      </div>
      <div className="card mb-3"><div className="card-body">
        <p className="text-muted" style={{ margin: 0 }}>
          <i aria-hidden="true" className="fas fa-shield-halved" /> Every public check of one of your documents is logged here — no personal data about the person checking is stored, only a privacy-safe daily fingerprint.
        </p></div></div>
      <div className="card mb-3"><div className="card-header"><h3>Recent checks</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {(d.rows || []).length ? table(d.rows)
            : <div style={{ padding: '1rem' }}><Empty icon="fa-magnifying-glass" title="No checks yet"><p>Nobody has verified one of your documents in this period.</p></Empty></div>}
        </div></div>
      {(d.unknown || []).length > 0 && <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Unknown-code attempts</h3></div>
        <div className="card-body" style={{ padding: 0 }}>{table(d.unknown)}</div></div>}
    </>
  );
}

const SCREENS = { index: Index, rules: Rules, add_rule: AddRule, process: Process,
  graduates: Graduates, graduate_preview: GraduatePreview, graduate_profile: GraduateProfile,
  graduate_compare: GraduateCompare, history: History, alumni: Alumni,
  alumni_analytics: AlumniAnalytics, doc_templates: DocTemplates,
  doc_verifications: DocVerifications };

export default function PromotionApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  // Remount the Process screen whenever its student set changes (new class/
  // session), so row state is re-derived instead of going stale — otherwise
  // rows[i] is undefined for the new list and the render crashes.
  const screenKey = d.page === 'process'
    ? 'process:' + (d.students || []).map((s) => s.id).join('-')
    : d.page;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen key={screenKey} d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
