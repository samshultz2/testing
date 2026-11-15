// Subject Combination — pick subjects (e.g. Physics + Chemistry + Biology),
// stack conditions ("all-subject average ≥ 50 AND exam average ≥ 67 across
// the chosen subjects") and see who qualifies, ready to export or split into
// balanced groups. Results-kit screen: same class picker as the Explorer
// (bottom sheet on phones), subjects as chips, conditions as plain sentences,
// a sortable table on laptops and cards on phones, export in a sheet.
import React, { useState, useMemo, useRef } from 'react';
import { useNav, navParams } from '../lib/section';
import { usePhone, fmtNum, tone, Head, Menu, Tiles, Sheet, Blank, Avatar, Bar } from './results';
import { ScopeList } from './explore';

const BASES = [
  ['combo_average', 'Chosen subjects · average'], ['combo_total', 'Chosen subjects · total'],
  ['all_average', 'All subjects · average'], ['all_total', 'All subjects · total'],
];
const OPS = [['gte', 'at least'], ['lte', 'at most'], ['eq', 'exactly']];
const COLS = [['sn', 'S/N'], ['student', 'Student'], ['class', 'Class'], ['arm', 'Arm'], ['subjects', 'Each subject'],
  ['total', 'Combined total'], ['average', 'Combined average'], ['missing', 'Missing count']];
const FORMATS = [['pdf', 'PDF', 'fa-file-pdf', 'pdf'], ['image', 'Image', 'fa-file-image', 'img'], ['excel', 'Excel', 'fa-file-excel', 'xls'],
  ['word', 'Word', 'fa-file-word', 'doc'], ['csv', 'CSV', 'fa-file-csv', 'csv']];

export function Combine({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const rows = d.rows || [];
  const subjects = d.subjects_union || [];
  const scopes = d.scope_meta || [];
  const ats = d.assessment_types || [];
  const pm = Number(d.pass_mark) || 50;
  const u = d.urls || {};
  const termName = (d.terms.find((t) => String(t.id) === String(d.term_id)) || {}).full_name || '';

  // ---- Classes (same picker as the Explorer) -----------------------------
  const loaded = (d.scopes || []).map(String);
  const [sel, setSel] = useState(() => new Set(loaded));
  const [picking, setPicking] = useState(false);
  const toggle = (k) => setSel((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleClass = (cls, on) => setSel((s) => { const n = new Set(s); cls.arms.forEach((a) => { const k = String(a.assignment_id); on ? n.add(k) : n.delete(k); }); return n; });
  const changed = [...sel].sort().join(',') !== loaded.slice().sort().join(',');
  const load = () => navParams(nav.go, d.self_url, { term_id: d.term_id, scopes: [...sel].join(',') });
  const allIds = (d.scope_options || []).flatMap((c) => c.arms.map((a) => String(a.assignment_id)));
  const scopeSummary = scopes.length
    ? (scopes.length <= 3 ? scopes.map((s) => s.label).join(', ') : `${scopes.slice(0, 2).map((s) => s.label).join(', ')} +${scopes.length - 2} more`)
    : 'No classes chosen';

  // ---- Subjects ----------------------------------------------------------
  const [subjSel, setSubjSel] = useState(() => new Set());
  const toggleSubj = (id) => setSubjSel((s) => { const n = new Set(s); const k = String(id); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const chosen = subjects.filter((s) => subjSel.has(String(s.id)));

  // ---- Conditions (all must be met) --------------------------------------
  const condId = useRef(1);
  const [conds, setConds] = useState(() => [{ id: 0, basis: 'combo_average', component: '', op: 'gte', value: '' }]);
  const addCond = () => setConds((cs) => [...cs, { id: condId.current++, basis: 'all_average', component: '', op: 'gte', value: String(pm) }]);
  const rmCond = (id) => setConds((cs) => (cs.length > 1 ? cs.filter((c) => c.id !== id) : cs.map((c) => ({ ...c, value: '' }))));
  const setCond = (id, k, v) => setConds((cs) => cs.map((c) => (c.id === id ? { ...c, [k]: v } : c)));

  const computed = useMemo(() => {
    const n = chosen.length;
    return rows.map((r) => {
      let total = 0, missing = 0;
      chosen.forEach((s) => { const v = r.subjects[String(s.id)]; if (v != null) total += v; else missing += 1; });
      total = Math.round(total * 10) / 10;
      return { ...r, combo_total: total, combo_average: n ? Math.round((total / n) * 100) / 100 : 0, combo_missing: missing };
    });
  }, [rows, subjSel]); // eslint-disable-line react-hooks/exhaustive-deps
  const condValue = (r, basis, component) => {
    if (basis === 'all_total') return r.total;
    if (basis === 'all_average') return r.average;
    const n = chosen.length;
    if (!n) return null;
    let tot = 0;
    chosen.forEach((s) => {
      const sid = String(s.id);
      const v = component ? (r.components && r.components[sid] ? r.components[sid][String(component)] : undefined) : r.subjects[sid];
      tot += v != null ? v : 0;
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
    return c.op === 'gte' ? x >= v : c.op === 'lte' ? x <= v : c.op === 'eq' ? x === v : true;
  };

  // ---- List --------------------------------------------------------------
  const [q, setQ] = useState('');
  const [sortKey, setSortKey] = useState('combo_total');
  const [sortDir, setSortDir] = useState('desc');
  const term = q.trim().toLowerCase();
  const matching = useMemo(() => (active ? computed.filter((r) => activeConds.every((c) => passes(r, c))) : computed),
    [computed, conds]); // eslint-disable-line react-hooks/exhaustive-deps
  const sortVal = (r) => (sortKey === 'name' ? r.student : sortKey.startsWith('s:') ? (r.subjects[sortKey.slice(2)] ?? -1) : r[sortKey]);
  const shown = useMemo(() => {
    const list = matching.filter((r) => !term || r.student.toLowerCase().includes(term));
    list.sort((a, b) => { const x = sortVal(a), y = sortVal(b); const c = typeof x === 'string' ? x.localeCompare(y) : x - y; return sortDir === 'desc' ? -c : c; });
    return list;
  }, [matching, term, sortKey, sortDir]); // eslint-disable-line react-hooks/exhaustive-deps
  const clickSort = (k) => { if (sortKey === k) setSortDir((x) => (x === 'desc' ? 'asc' : 'desc')); else { setSortKey(k); setSortDir(k === 'name' ? 'asc' : 'desc'); } };
  const arrow = (k) => (sortKey === k ? <i className={'fas fa-arrow-' + (sortDir === 'desc' ? 'down' : 'up')} aria-hidden="true" /> : null);
  const avgOf = (list) => (list.length ? list.reduce((a, r) => a + r.combo_average, 0) / list.length : null);
  const best = matching.slice().sort((a, b) => b.combo_average - a.combo_average)[0];

  // ---- Export ------------------------------------------------------------
  const [showExport, setShowExport] = useState(false);
  const [expTitle, setExpTitle] = useState('');
  const [groupsN, setGroupsN] = useState(1);
  const [cols, setCols] = useState({ sn: true, student: true, class: true, arm: true, subjects: true, total: true, average: true, missing: false });
  const [busy, setBusy] = useState(false);
  const exportUrl = (fmt) => {
    const keys = [];
    COLS.forEach(([k]) => { if (!cols[k]) return; if (k === 'subjects') chosen.forEach((s) => keys.push('subj:' + s.id)); else keys.push(k); });
    const p = new URLSearchParams({ term_id: d.term_id || '', scopes: loaded.join(','), subjects: chosen.map((s) => s.id).join(',') });
    if (activeConds.length) p.set('conditions', JSON.stringify(activeConds.map((c) => ({ basis: c.basis, component: c.basis.indexOf('combo') === 0 ? c.component : '', op: c.op, value: c.value }))));
    p.set('columns', keys.join(','));
    if (expTitle.trim()) p.set('title', expTitle.trim());
    if (groupsN >= 2) p.set('groups', String(groupsN));
    p.set('format', fmt);
    return `${u.export}?${p.toString()}`;
  };
  const saveBlob = (blob, name) => {
    const href = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = href; a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(href), 4000);
  };
  const downloadImages = async (url) => {
    let page = 1, total = 1;
    do {
      const res = await fetch(url + '&page=' + page, { credentials: 'same-origin' });
      if (!res.ok) { notify('error', 'Could not make the image.'); return; }
      total = parseInt(res.headers.get('X-Total-Pages') || '1', 10) || 1;
      saveBlob(await res.blob(), total > 1 ? `subject_combination_p${page}.png` : 'subject_combination.png');
      page += 1;
    } while (page <= total);
    if (total > 1) notify('success', `Downloaded ${total} image pages.`);
  };
  const doExport = async (fmt) => {
    if (!chosen.length) { notify('error', 'Pick at least one subject to combine.'); return; }
    if (fmt === 'image') { setBusy(true); try { await downloadImages(exportUrl(fmt)); } finally { setBusy(false); } setShowExport(false); return; }
    window.location.href = exportUrl(fmt);
    setShowExport(false);
  };

  const menu = [
    chosen.length > 0 && { icon: 'fa-download', label: 'Export…', onClick: () => setShowExport(true) },
    { heading: 'More' },
    u.explore && { icon: 'fa-filter', label: 'Results Explorer', href: u.explore },
    u.broadsheet && { icon: 'fa-table', label: 'Class broadsheet', href: u.broadsheet },
  ];

  const pickerBody = d.scope_options.length ? (
    <>
      <ScopeList options={d.scope_options} sel={sel} toggle={toggle} toggleClass={toggleClass} />
      <div className="ex-pick-a">
        <button type="button" className="rs-link" onClick={() => setSel(new Set(sel.size === allIds.length ? [] : allIds))}>{sel.size === allIds.length ? 'Clear all' : 'Select all'}</button>
        <span className="rs-muted">{sel.size} arm{sel.size === 1 ? '' : 's'} selected</span>
        <button type="button" className="rs-btn primary" disabled={!sel.size || !changed} onClick={() => { setPicking(false); load(); }}>
          <i className="fas fa-check" aria-hidden="true" /> Load students</button>
      </div>
    </>
  ) : <p className="rs-muted">Choose a term to see its classes.</p>;

  const exportSheet = showExport && (
    <Sheet title="Export the list" onClose={() => setShowExport(false)}>
      <div className="cb-exp">
        <label className="cb-f"><span>Heading <small>(optional)</small></span>
          <input type="text" maxLength={120} placeholder="e.g. SSS2 SCIENCE CLASS MERIT LIST" value={expTitle} onChange={(e) => setExpTitle(e.target.value)} /></label>
        <div className="cb-f"><span>Columns</span>
          <div className="rs-chips">{COLS.map(([k, l]) => (
            <button key={k} type="button" className={'rs-chip' + (cols[k] ? ' on' : '')} aria-pressed={!!cols[k]} onClick={() => setCols((c) => ({ ...c, [k]: !c[k] }))}>
              {cols[k] && <i className="fas fa-check" aria-hidden="true" />} {l}</button>))}</div></div>
        <div className="cb-f"><span>Split into balanced groups</span>
          <div className="rs-chips">{[1, 2, 3, 4, 5, 6].map((n) => (
            <button key={n} type="button" className={'rs-chip' + (groupsN === n ? ' on' : '')} aria-pressed={groupsN === n} onClick={() => setGroupsN(n)}>{n === 1 ? 'One list' : `${n} groups`}</button>))}</div>
          {groupsN >= 2 && <small className="rs-muted">Students are shared evenly across {groupsN} groups (A, B…) by combined average, so each group has a similar mix and size.</small>}</div>
        <div className="cb-f"><span>Download as</span>
          <div className="cb-fmts">{FORMATS.map(([k, l, ic, c]) => (
            <button key={k} type="button" className="cb-fmt" disabled={busy} onClick={() => doExport(k)}>
              <span className={'cb-fi ' + c}><i className={'fas ' + (busy && k === 'image' ? 'fa-spinner fa-spin' : ic)} aria-hidden="true" /></span>{l}</button>))}</div></div>
      </div>
    </Sheet>
  );

  const condRows = conds.map((c, i) => {
    const isCombo = c.basis.indexOf('combo') === 0;
    return (
      <div key={c.id} className="cb-cond">
        <span className="cb-cond-w">{i === 0 ? 'Where' : 'and'}</span>
        <select value={c.basis} onChange={(e) => setCond(c.id, 'basis', e.target.value)} aria-label="Measure">
          {BASES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        {isCombo && ats.length > 0 && (
          <select value={c.component} onChange={(e) => setCond(c.id, 'component', e.target.value)} aria-label="Part of the score">
            <option value="">Whole score</option>{ats.map((at) => <option key={at.id} value={at.id}>{at.name} only</option>)}</select>)}
        <select value={c.op} onChange={(e) => setCond(c.id, 'op', e.target.value)} aria-label="Condition">
          {OPS.map(([v, l]) => <option key={v} value={v}>is {l}</option>)}</select>
        <input type="number" inputMode="decimal" value={c.value} placeholder={String(pm)} onChange={(e) => setCond(c.id, 'value', e.target.value)} aria-label="Value" />
        <button type="button" className="cb-x" onClick={() => rmCond(c.id)} aria-label="Remove condition" title="Remove"><i className="fas fa-xmark" aria-hidden="true" /></button>
      </div>
    );
  });

  return (
    <div className="rs ex cb">
      <Head icon="fa-layer-group" title="Subject Combination"
            sub={[termName, scopes.length ? `${scopes.length} class arm${scopes.length === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · ') || 'Find who qualifies across a set of subjects'}>
        {!phone && chosen.length > 0 && <button type="button" className="rs-btn primary" onClick={() => setShowExport(true)}><i className="fas fa-download" aria-hidden="true" /> Export</button>}
        <Menu items={menu} label="More" />
      </Head>

      {/* 1. Classes */}
      <section className="rs-pick">
        <div className="cb-step"><b>1</b> Choose classes</div>
        <div className="rs-pick-row">
          <label className="rs-sel"><span>Term</span>
            <select value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value, scopes: '' })}>
              <option value="">Select term</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
          {phone && (
            <div className="rs-sel grow"><span>Classes</span>
              <button type="button" className="ex-scope-btn" onClick={() => setPicking(true)} disabled={!d.term_id}>
                <b>{scopeSummary}</b><i className="fas fa-chevron-down" aria-hidden="true" /></button></div>)}
        </div>
        {!phone && pickerBody}
      </section>
      {phone && picking && <Sheet title="Classes & arms" onClose={() => { setPicking(false); setSel(new Set(loaded)); }}>{pickerBody}</Sheet>}

      {rows.length > 0 ? (<>
        {/* 2. Subjects */}
        <section className="rs-card">
          <div className="cb-step"><b>2</b> Pick the subjects to combine
            {chosen.length > 0 && <button type="button" className="rs-link" onClick={() => setSubjSel(new Set())}>Clear</button>}</div>
          <div className="rs-chips cb-subj">
            {subjects.map((s) => { const on = subjSel.has(String(s.id)); return (
              <button key={s.id} type="button" className={'rs-chip' + (on ? ' on' : '')} aria-pressed={on} onClick={() => toggleSubj(s.id)}>
                {on && <i className="fas fa-check" aria-hidden="true" />} {s.name}</button>); })}
          </div>
          {chosen.length > 0 && <p className="rs-muted cb-note"><b>{chosen.map((s) => s.name).join(' + ')}</b> · averages divide by {chosen.length}; a missing score counts as 0.</p>}
        </section>

        {/* 3. Conditions */}
        {chosen.length > 0 && (
          <section className="rs-card">
            <div className="cb-step"><b>3</b> Who qualifies? <small>all conditions must be met</small></div>
            <div className="cb-conds">{condRows}</div>
            <button type="button" className="rs-btn ghost sm cb-add" onClick={addCond}><i className="fas fa-plus" aria-hidden="true" /> Add condition</button>
          </section>
        )}

        {chosen.length > 0 ? (<>
          <Tiles items={[
            { label: active ? 'Qualify' : 'Students', value: matching.length, sub: active ? `of ${rows.length} students` : `${scopes.length} arm${scopes.length === 1 ? '' : 's'}`, tone: active ? (matching.length ? 'good' : 'bad') : '' },
            matching.length > 0 && { label: 'Combined average', value: fmtNum(Math.round(avgOf(matching) * 10) / 10), unit: '%', tone: tone(avgOf(matching), pm) },
            !phone && best && { label: 'Best combined', value: fmtNum(best.combo_average), unit: '%', sub: best.student },
          ]} />
          <div className="rs-toolbar">
            <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" placeholder="Find a student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student" /></label>
            {phone && (
              <label className="rs-sel ex-sort"><span>Sort</span>
                <select value={sortKey + '|' + sortDir} onChange={(e) => { const [k, dd] = e.target.value.split('|'); setSortKey(k); setSortDir(dd); }}>
                  <option value="combo_total|desc">Highest combined</option><option value="combo_total|asc">Lowest combined</option>
                  <option value="average|desc">Highest overall</option><option value="name|asc">Name A–Z</option></select></label>)}
            <span className="rs-count">{shown.length === rows.length ? `${rows.length} students` : `${shown.length} of ${rows.length}`}</span>
          </div>

          {phone ? (
            <div className="rs-bs-cards">
              {shown.map((r, i) => <CbCard key={r.student_id + '-' + r.assignment_id} r={r} i={i + 1} chosen={chosen} pm={pm} multi={scopes.length > 1} />)}
              {!shown.length && <p className="rs-muted rs-pad">No students meet {activeConds.length > 1 ? 'all these conditions' : 'this condition'}.</p>}
            </div>
          ) : (
            <div className="rs-card flush rs-bs-wrap">
              <table className="rs-bs ex-tbl">
                <thead><tr>
                  <th className="pos">#</th>
                  <th className="nm"><button type="button" className="ex-th" onClick={() => clickSort('name')}>Student {arrow('name')}</button></th>
                  {scopes.length > 1 && <th className="cl">Class</th>}
                  {chosen.map((s) => <th key={s.id} title={s.name}><button type="button" className="ex-th" onClick={() => clickSort('s:' + s.id)}>{s.short} {arrow('s:' + s.id)}</button></th>)}
                  <th className="sum"><button type="button" className="ex-th" onClick={() => clickSort('combo_total')}>Total {arrow('combo_total')}</button></th>
                  <th className="sum"><button type="button" className="ex-th" onClick={() => clickSort('combo_average')}>Avg {arrow('combo_average')}</button></th>
                  <th className="sum"><button type="button" className="ex-th" onClick={() => clickSort('average')} title="Average across all subjects">Overall {arrow('average')}</button></th>
                </tr></thead>
                <tbody>{shown.length ? shown.map((r, i) => (
                  <tr key={r.student_id + '-' + r.assignment_id}>
                    <td className="pos"><span className="rs-pos">{i + 1}</span></td>
                    <td className="nm"><span className="ex-who"><Avatar name={r.student} gender={r.gender} />{r.student}</span></td>
                    {scopes.length > 1 && <td className="cl">{r.scope_label}</td>}
                    {chosen.map((s) => { const v = r.subjects[String(s.id)]; return <td key={s.id} className={'sc ' + tone(v, pm)}>{v != null ? fmtNum(v) : '–'}</td>; })}
                    <td className="sum">{fmtNum(r.combo_total)}</td>
                    <td className={'sum avg ' + tone(r.combo_average, pm)}>{fmtNum(r.combo_average)}</td>
                    <td className={'sum ' + tone(r.average, pm)}>{fmtNum(r.average)}</td>
                  </tr>)) : (
                  <tr><td colSpan={chosen.length + (scopes.length > 1 ? 6 : 5)} className="rs-muted rs-pad">No students meet {activeConds.length > 1 ? 'all these conditions' : 'this condition'}.</td></tr>)}
                </tbody>
              </table>
            </div>
          )}
          {phone && <Bar><button type="button" className="rs-btn primary cb-bar-btn" onClick={() => setShowExport(true)}>
            <i className="fas fa-download" aria-hidden="true" /> Export {active ? `${matching.length} qualifying` : 'list'}</button></Bar>}
        </>) : (
          <Blank icon="fa-hand-pointer" title="Pick some subjects"><p>Tap the subjects above to combine them — e.g. Physics, Chemistry and Biology.</p></Blank>
        )}
      </>) : loaded.length ? (
        <Blank icon="fa-table" title="No scores yet"><p>No scores have been entered for the chosen class arm{loaded.length === 1 ? '' : 's'} this term.</p></Blank>
      ) : (
        <Blank icon="fa-layer-group" title="Start with the classes">
          <p>{d.term_id ? (phone ? 'Tap Classes above and choose who to include.' : 'Tick the classes and arms above, then Load students.') : 'Choose a term first.'}</p>
          {phone && d.term_id && <button type="button" className="rs-btn primary" onClick={() => setPicking(true)}><i className="fas fa-layer-group" aria-hidden="true" /> Choose classes</button>}
        </Blank>
      )}
      {exportSheet}
    </div>
  );
}

function CbCard({ r, i, chosen, pm, multi }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={'rs-bs-card' + (open ? ' open' : '')}>
      <button type="button" className="rs-bs-top" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="rs-pos">{i}</span>
        <span className="rs-bs-n"><b>{r.student}</b>
          <small>{multi ? r.scope_label + ' · ' : ''}Total {fmtNum(r.combo_total)} · overall {fmtNum(r.average)}</small></span>
        <span className={'rs-bs-avg ' + tone(r.combo_average, pm)}>{fmtNum(r.combo_average)}</span>
        <i className="fas fa-chevron-down" aria-hidden="true" />
      </button>
      {open && (
        <div className="rs-bs-more"><div className="rs-bs-subj">
          {chosen.map((s) => { const v = r.subjects[String(s.id)]; return (
            <span key={s.id} className={tone(v, pm)}><small>{s.name}</small><b>{v != null ? fmtNum(v) : '–'}</b></span>); })}
        </div></div>
      )}
    </div>
  );
}
