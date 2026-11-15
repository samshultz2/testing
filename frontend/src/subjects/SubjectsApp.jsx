import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Workflow, Scores, BulkEntry, Broadsheet, Affective, Comments } from './results';
import { Analytics, Institution, Teacher, SubjectScorecard } from './analytics';
import { List, SubjectForm, BulkAdd, ClassSubjects, Assign, EditClassSubject } from './catalog';
import { Explore } from './explore';

// Whole numbers print without a trailing .0 (34, not 34.0); genuine decimals to
// two places (34.3 -> 34.30). Non-numeric / blank values pass through.
function fmtNum(v) {
  if (v == null || v === '') return v;
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}


// ---- Subject Combination Explorer -----------------------------------------
// Pick any set of subjects; filter students by their COMBINED total/average
// across just those subjects; export the view (with a column picker).
function Combine({ d, notify }) {
  const nav = useNav();
  const rows = d.rows || [];
  const subjects = d.subjects_union || [];

  const [sel, setSel] = useState(() => new Set((d.scopes || []).map(String)));
  const toggleScope = (id) => setSel((s) => { const n = new Set(s); const k = String(id); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleClass = (cls, on) => setSel((s) => { const n = new Set(s); cls.arms.forEach((a) => { on ? n.add(String(a.assignment_id)) : n.delete(String(a.assignment_id)); }); return n; });
  const classAll = (cls) => cls.arms.every((a) => sel.has(String(a.assignment_id)));
  const load = () => navParams(nav.go, d.self_url, { term_id: d.term_id, scopes: [...sel].join(',') });
  const selChanged = [...sel].sort().join(',') !== (d.scopes || []).map(String).sort().join(',');

  // Subject combination
  const [subjSel, setSubjSel] = useState(() => new Set());
  const toggleSubj = (id) => setSubjSel((s) => { const n = new Set(s); const k = String(id); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const chosen = subjects.filter((s) => subjSel.has(String(s.id)));

  // Multi-condition AND filter. Each condition tests a basis (all subjects vs the
  // chosen combination, total vs average) optionally on one assessment component
  // (e.g. Exam) — so you can ask e.g. "all-subject average ≥ 50 AND exam average
  // ≥ 67 across Physics+Chemistry+Biology" to pick who qualifies for a stream.
  const ats = d.assessment_types || [];
  let condId = React.useRef(1);
  const [conds, setConds] = useState(() => [{ id: 0, basis: 'combo_average', component: '', op: 'gte', value: '' }]);
  const addCond = () => setConds((cs) => [...cs, { id: condId.current++, basis: 'combo_average', component: '', op: 'gte', value: '' }]);
  const rmCond = (id) => setConds((cs) => (cs.length > 1 ? cs.filter((c) => c.id !== id) : cs));
  const setCond = (id, k, v) => setConds((cs) => cs.map((c) => (c.id === id ? { ...c, [k]: v } : c)));

  const computed = React.useMemo(() => {
    const n = chosen.length;
    return rows.map((r) => {
      let total = 0;
      chosen.forEach((s) => { const v = r.subjects[String(s.id)]; if (v != null) total += v; });
      total = Math.round(total * 10) / 10;
      const average = n ? Math.round((total / n) * 100) / 100 : 0;
      return { ...r, combo_total: total, combo_average: average };
    });
  }, [rows, subjSel]);

  const condValue = (r, basis, component) => {
    if (basis === 'all_total') return r.total;
    if (basis === 'all_average') return r.average;
    const n = chosen.length;
    if (!n) return null;
    let tot = 0;
    chosen.forEach((s) => {
      const sid = String(s.id);
      let v;
      if (component) v = (r.components && r.components[sid]) ? r.components[sid][String(component)] : undefined;
      else v = r.subjects[sid];
      tot += (v != null ? v : 0);
    });
    tot = Math.round(tot * 10) / 10;
    return basis === 'combo_total' ? tot : Math.round((tot / n) * 100) / 100;
  };
  const activeConds = conds.filter((c) => c.value !== '' && !Number.isNaN(parseFloat(c.value)));
  const active = activeConds.length > 0 && chosen.length > 0;
  const passes = (r, c) => {
    const x = condValue(r, c.basis, c.basis.indexOf('combo') === 0 ? c.component : '');
    if (x == null) return false;
    const v = parseFloat(c.value);
    if (c.op === 'gte') return x >= v;
    if (c.op === 'lte') return x <= v;
    if (c.op === 'eq') return x === v;
    return true;
  };
  const shown = React.useMemo(() => {
    const list = active ? computed.filter((r) => activeConds.every((c) => passes(r, c))) : computed.slice();
    list.sort((a, b) => b.combo_total - a.combo_total);
    return list;
  }, [computed, conds]);

  // Export column picker
  const [showExport, setShowExport] = useState(false);
  const [expTitle, setExpTitle] = useState('');
  const [groupsN, setGroupsN] = useState(1);   // 1 = don't split
  const [cols, setCols] = useState({ sn: true, student: true, class: true, arm: true, subjects: true, total: true, average: true, missing: false });
  const setCol = (k) => setCols((c) => ({ ...c, [k]: !c[k] }));
  const exportUrl = (fmt) => {
    const keys = [];
    if (cols.sn) keys.push('sn');
    if (cols.student) keys.push('student');
    if (cols.class) keys.push('class');
    if (cols.arm) keys.push('arm');
    if (cols.subjects) chosen.forEach((s) => keys.push('subj:' + s.id));
    if (cols.total) keys.push('total');
    if (cols.average) keys.push('average');
    if (cols.missing) keys.push('missing');
    const p = new URLSearchParams();
    p.set('term_id', d.term_id || '');
    p.set('scopes', (d.scopes || []).join(','));
    p.set('subjects', chosen.map((s) => s.id).join(','));
    if (activeConds.length) {
      p.set('conditions', JSON.stringify(activeConds.map((c) => ({
        basis: c.basis, component: c.basis.indexOf('combo') === 0 ? c.component : '',
        op: c.op, value: c.value }))));
    }
    p.set('columns', keys.join(','));
    if (expTitle.trim()) p.set('title', expTitle.trim());
    if (groupsN >= 2) p.set('groups', String(groupsN));
    p.set('format', fmt);
    return `${d.urls.export}?${p.toString()}`;
  };
  const saveBlob = (blob, name) => {
    const u = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = u; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 4000);
  };
  // Images can span several A4 pages; download each page as its own file.
  const downloadImages = async (url) => {
    let page = 1, total = 1;
    do {
      const res = await fetch(url + '&page=' + page, { credentials: 'same-origin' });
      if (!res.ok) { notify('error', 'Could not generate the image.'); return; }
      total = parseInt(res.headers.get('X-Total-Pages') || '1', 10) || 1;
      const blob = await res.blob();
      saveBlob(blob, total > 1 ? `subject_combination_p${page}.png` : 'subject_combination.png');
      page += 1;
    } while (page <= total);
    if (total > 1) notify('success', `Downloaded ${total} image pages.`);
  };
  const doExport = (fmt) => {
    if (!chosen.length) { notify('error', 'Pick at least one subject to combine.'); return; }
    if (fmt === 'image') { downloadImages(exportUrl(fmt)); setShowExport(false); return; }
    window.location.href = exportUrl(fmt);
    setShowExport(false);
  };

  return (
    <>
      <div className="page-header">
        <div><h1>Subject Combination</h1>
          <p className="text-muted text-sm">Pick subjects (e.g. Physics + Chemistry + Biology) and stack conditions — e.g. all-subject average ≥ 50 AND exam average ≥ 67 across the chosen subjects — to find who qualifies (for a stream, an award, etc.).</p></div>
        <div className="page-header-actions">
          {d.urls.explore && <a href={d.urls.explore} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-filter" /> Explorer</a>}
          {d.urls.broadsheet && <a href={d.urls.broadsheet} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-table" /> Broadsheet</a>}
        </div>
      </div>

      {/* Term + scope picker */}
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form" style={{ marginBottom: '.6rem' }}>
          <div className="form-group"><label className="form-label">Term</label>
            <select className="form-control" value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value, scopes: '' })}>
              <option value="">Select Term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
        </div>
        {d.scope_options.length ? (
          <>
            <label className="form-label">Classes &amp; arms to include</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.9rem', margin: '.3rem 0 .7rem' }}>
              {d.scope_options.map((cls) => (
                <div key={cls.class_id} className="card" style={{ padding: '.5rem .7rem', minWidth: 150 }}>
                  <label className="form-check" style={{ fontWeight: 700, display: 'flex', gap: '.4rem', alignItems: 'center' }}>
                    <input type="checkbox" checked={classAll(cls)} onChange={(e) => toggleClass(cls, e.target.checked)} /> {cls.class_name}
                  </label>
                  <div style={{ paddingLeft: '.4rem', marginTop: '.2rem' }}>
                    {cls.arms.map((a) => (
                      <label key={a.assignment_id} className="form-check" style={{ display: 'flex', gap: '.4rem', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                        <input type="checkbox" checked={sel.has(String(a.assignment_id))} onChange={() => toggleScope(a.assignment_id)} /> {a.arm_name || cls.class_name}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <button type="button" className="btn btn-primary btn-sm" onClick={load} disabled={!selChanged && rows.length > 0}>
              <i aria-hidden="true" className="fas fa-rotate" /> Load selected</button>
          </>
        ) : <p className="text-muted text-sm">Pick a term to choose classes and arms.</p>}
      </div></div>

      {rows.length > 0 && (
        <div className="card mb-3"><div className="card-body">
          <label className="form-label">Subjects to combine</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.5rem 1.1rem', margin: '.3rem 0 .8rem' }}>
            {subjects.map((s) => (
              <label key={s.id} className="form-check" style={{ display: 'flex', gap: '.4rem', alignItems: 'center' }}>
                <input type="checkbox" checked={subjSel.has(String(s.id))} onChange={() => toggleSubj(s.id)} /> {s.name}
              </label>
            ))}
          </div>
          {chosen.length > 0 && (
            <div style={{ marginTop: '.3rem' }}>
              <label className="form-label">Conditions <span className="text-muted" style={{ fontWeight: 400 }}>(all must be met)</span></label>
              {conds.map((c) => {
                const isCombo = c.basis.indexOf('combo') === 0;
                return (
                  <div key={c.id} className="filter-form" style={{ alignItems: 'flex-end', marginBottom: '.4rem' }}>
                    <div className="form-group"><label className="form-label">Basis</label>
                      <select className="form-control" value={c.basis} onChange={(e) => setCond(c.id, 'basis', e.target.value)}>
                        <option value="combo_average">Selected subjects · average</option>
                        <option value="combo_total">Selected subjects · total</option>
                        <option value="all_average">All subjects · average</option>
                        <option value="all_total">All subjects · total</option>
                      </select></div>
                    {isCombo && ats.length > 0 && (
                      <div className="form-group"><label className="form-label">Component</label>
                        <select className="form-control" value={c.component} onChange={(e) => setCond(c.id, 'component', e.target.value)}>
                          <option value="">Whole subject</option>
                          {ats.map((at) => <option key={at.id} value={at.id}>{at.name} only</option>)}
                        </select></div>
                    )}
                    <div className="form-group"><label className="form-label">Is</label>
                      <select className="form-control" value={c.op} onChange={(e) => setCond(c.id, 'op', e.target.value)}>
                        <option value="gte">≥ (at least)</option><option value="lte">≤ (at most)</option><option value="eq">= (exactly)</option></select></div>
                    <div className="form-group"><label className="form-label">Value</label>
                      <input type="number" className="form-control" style={{ width: 110 }} value={c.value} onChange={(e) => setCond(c.id, 'value', e.target.value)} placeholder="e.g. 50" /></div>
                    <div className="form-group">
                      <button type="button" className="btn btn-secondary btn-sm" title="Remove condition" disabled={conds.length <= 1} onClick={() => rmCond(c.id)}><i aria-hidden="true" className="fas fa-times" /></button>
                    </div>
                  </div>
                );
              })}
              <div className="d-flex gap-2" style={{ marginTop: '.2rem' }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={addCond}><i aria-hidden="true" className="fas fa-plus" /> Add condition</button>
                <button type="button" className="btn btn-success btn-sm" onClick={() => setShowExport(true)}><i aria-hidden="true" className="fas fa-download" /> Export</button>
              </div>
            </div>
          )}
          {chosen.length > 0 && (
            <p className="text-muted text-sm mb-0" style={{ marginTop: '.5rem' }}>
              Combining <strong>{chosen.map((s) => s.name).join(' + ')}</strong>
              {active ? <> · <strong>{shown.length}</strong> of {rows.length} students meet all {activeConds.length} condition(s)</> : <> · {rows.length} students</>}
              . Averages divide by {chosen.length} chosen subject(s); missing scores count as 0.
            </p>
          )}
        </div></div>
      )}

      {chosen.length > 0 && (
        <div className="card">
          <div className="card-header"><h3>Students ({shown.length})</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container" style={{ maxHeight: '70vh', overflow: 'auto' }}>
            <table className="data-table"><thead><tr>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>#</th>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Student</th>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Class</th>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2 }}>Arm</th>
              {chosen.map((s) => <th key={s.id} title={s.name} style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center', fontSize: 'var(--text-xs)' }}>{s.short}</th>)}
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center' }}>Total</th>
              <th style={{ position: 'sticky', top: 0, background: 'var(--gray-50)', zIndex: 2, textAlign: 'center' }}>Avg</th>
            </tr></thead>
            <tbody>{shown.length ? shown.map((r, i) => (
              <tr key={i}>
                <td style={{ fontWeight: 'bold' }}>{i + 1}</td>
                <td style={{ whiteSpace: 'nowrap' }}>{r.student}</td>
                <td>{r.class_name}</td><td>{r.arm_name}</td>
                {chosen.map((s) => { const v = r.subjects[String(s.id)]; return <td key={s.id} style={{ textAlign: 'center' }}>{v != null ? fmtNum(v) : '-'}</td>; })}
                <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{fmtNum(r.combo_total)}</td>
                <td style={{ textAlign: 'center', fontWeight: 'bold' }}>{fmtNum(r.combo_average)}</td>
              </tr>
            )) : <tr><td colSpan={6 + chosen.length} style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)' }}>No students match this condition.</td></tr>}</tbody>
            </table>
          </div></div>
        </div>
      )}

      {showExport && (
        <div className="modal-backdrop" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setShowExport(false)}>
          <div className="card" style={{ maxWidth: 460, width: '92%' }} onClick={(e) => e.stopPropagation()}>
            <div className="card-header"><h3><i aria-hidden="true" className="fas fa-download" /> Export combination</h3></div>
            <div className="card-body">
              <p className="text-muted text-sm">Choose the columns to include, then pick a format.</p>
              <label className="form-label" style={{ fontWeight: 600 }}>Heading <span className="text-muted" style={{ fontWeight: 400 }}>(optional)</span></label>
              <input type="text" className="form-control" style={{ marginBottom: '.8rem' }} maxLength={120}
                     placeholder="e.g. SSS2 SCIENCE CLASS MERIT LIST" value={expTitle}
                     onChange={(e) => setExpTitle(e.target.value)} />
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.4rem 1.1rem', marginBottom: '.8rem' }}>
                {[['sn', 'S/N'], ['student', 'Student'], ['class', 'Class'], ['arm', 'Arm'], ['subjects', 'Each subject'], ['total', 'Combined total'], ['average', 'Combined average'], ['missing', 'Missing count']].map(([k, label]) => (
                  <label key={k} className="form-check" style={{ display: 'flex', gap: '.4rem', alignItems: 'center' }}>
                    <input type="checkbox" checked={!!cols[k]} onChange={() => setCol(k)} /> {label}
                  </label>
                ))}
              </div>
              <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '.7rem', marginBottom: '.8rem' }}>
                <label className="form-label" style={{ fontWeight: 600 }}>Split into balanced groups</label>
                <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center' }}>
                  <select className="form-control" style={{ width: 'auto' }} value={groupsN}
                          onChange={(e) => setGroupsN(parseInt(e.target.value, 10) || 1)}>
                    <option value={1}>Don't split — one list</option>
                    {[2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n} groups</option>)}
                  </select>
                  <span className="text-muted text-sm">Group A, B, … balanced by average</span>
                </div>
                {groupsN >= 2 && <p className="text-muted text-sm" style={{ margin: '.4rem 0 0' }}>
                  Students are shared evenly across {groupsN} groups by their combined average, so each group has a similar mix of abilities and roughly the same size.</p>}
              </div>
              <div className="page-header-actions">
                <button type="button" className="btn btn-danger btn-sm" onClick={() => doExport('pdf')}><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</button>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => doExport('image')}><i aria-hidden="true" className="fas fa-file-image" /> Image</button>
                <button type="button" className="btn btn-success btn-sm" onClick={() => doExport('excel')}><i aria-hidden="true" className="fas fa-file-excel" /> Excel</button>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => doExport('word')}><i aria-hidden="true" className="fas fa-file-word" /> Word</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => doExport('csv')}>CSV</button>
                <button type="button" className="btn btn-link btn-sm" onClick={() => setShowExport(false)}>Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const SCREENS = { list: List, add: SubjectForm, edit: SubjectForm, bulk_add: BulkAdd,
  class_subjects: ClassSubjects, assign: Assign, edit_class_subject: EditClassSubject,
  scores: Scores, workflow: Workflow, bulk_entry: BulkEntry, broadsheet: Broadsheet,
  affective: Affective, comments: Comments, analytics: Analytics, institution: Institution,
  teacher: Teacher, subject: SubjectScorecard, explore: Explore, combine: Combine };

export default function SubjectsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || List;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
