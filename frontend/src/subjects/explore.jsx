// Results Explorer — compare results within a class arm, across arms and
// across classes. Built from the results kit like the broadsheet: one header
// with an Actions menu, a class picker (chips on laptops, a bottom sheet on
// phones) that loads as soon as you're done, one-tap filters, summary tiles,
// arm comparison cards (tap one to focus it) and the student list (a sortable
// table on laptops, tappable cards on phones).
import React, { useState, useMemo } from 'react';
import { useNav, navParams } from '../lib/section';
import { usePhone, fmtNum, tone, Head, Menu, Tiles, Sheet, Blank, Avatar, Meter } from './results';

const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
// A student with no scores entered yet: shown as '–', never ranked or counted as failing.
const hasScores = (r) => r.total > 0 || Object.keys(r.subjects || {}).length > 0;
const mean = (arr) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null);
const r1 = (x) => (x == null ? null : Math.round(x * 10) / 10);
const OPS = [['gte', 'at least'], ['lte', 'at most'], ['between', 'between'], ['eq', 'exactly']];
const OP_SIGN = { gte: '≥', lte: '≤', eq: '=', between: '' };

// Class → arm checklist, shared by the laptop card and the phone sheet.
export function ScopeList({ options, sel, toggle, toggleClass }) {
  return (
    <div className="ex-scopes">
      {options.map((cls) => {
        const ids = cls.arms.map((a) => String(a.assignment_id));
        const on = ids.filter((i) => sel.has(i)).length;
        const all = on === ids.length;
        return (
          <div key={cls.class_id} className={'ex-cls' + (on ? ' some' : '')}>
            <button type="button" className={'ex-cls-h' + (all ? ' on' : '')} aria-pressed={all} onClick={() => toggleClass(cls, !all)}>
              <i className={'fas ' + (all ? 'fa-square-check' : on ? 'fa-square-minus' : 'fa-square')} aria-hidden="true" />
              <b>{cls.class_name}</b><small>{cls.arms.length > 1 ? `${on}/${cls.arms.length}` : ''}</small>
            </button>
            {cls.arms.length > 1 && (
              <div className="ex-arms">
                {cls.arms.map((a) => {
                  const k = String(a.assignment_id);
                  return (
                    <button key={k} type="button" className={'rs-chip' + (sel.has(k) ? ' on' : '')} aria-pressed={sel.has(k)} onClick={() => toggle(k)}>
                      {a.arm_name || cls.class_name}</button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function Explore({ d }) {
  const nav = useNav();
  const phone = usePhone();
  const rows = d.rows || [];
  const subjects = d.subjects_union || [];
  const scopes = d.scope_meta || [];
  const pm = Number(d.pass_mark) || 50;
  const u = d.urls || {};
  const termName = (d.terms.find((t) => String(t.id) === String(d.term_id)) || {}).full_name || '';

  // ---- Which classes/arms ------------------------------------------------
  const loaded = (d.scopes || []).map(String);
  const [sel, setSel] = useState(() => new Set(loaded));
  const [picking, setPicking] = useState(false);
  const toggle = (k) => setSel((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleClass = (cls, on) => setSel((s) => {
    const n = new Set(s); cls.arms.forEach((a) => { const k = String(a.assignment_id); on ? n.add(k) : n.delete(k); }); return n;
  });
  const changed = [...sel].sort().join(',') !== loaded.slice().sort().join(',');
  const load = (ids) => navParams(nav.go, d.self_url, { term_id: d.term_id, scopes: [...(ids || sel)].join(',') });
  const allIds = (d.scope_options || []).flatMap((c) => c.arms.map((a) => String(a.assignment_id)));
  const scopeSummary = scopes.length
    ? (scopes.length <= 3 ? scopes.map((s) => s.label).join(', ') : `${scopes.slice(0, 2).map((s) => s.label).join(', ')} +${scopes.length - 2} more`)
    : 'No classes chosen';

  // ---- Filter --------------------------------------------------------------
  // Quick filters cover the everyday questions; "Custom" is any field + condition.
  const [quick, setQuick] = useState('all');           // all | pass | fail | dist | custom
  const [field, setField] = useState('average');
  const [op, setOp] = useState('gte');
  const [v1, setV1] = useState('');
  const [v2, setV2] = useState('');
  const [focus, setFocus] = useState(null);             // assignment_id to narrow to
  const [q, setQ] = useState('');
  const [showCustom, setShowCustom] = useState(false);
  const n1 = parseFloat(v1), n2 = parseFloat(v2);
  const customOn = quick === 'custom' && (op === 'between' ? !Number.isNaN(n1) && !Number.isNaN(n2) : !Number.isNaN(n1));
  const fieldVal = (r, f = field) => (f === 'average' ? r.average : f === 'total' ? r.total : r.subjects[String(f)]);
  const fieldName = (f = field) => (f === 'average' ? 'Average' : f === 'total' ? 'Total'
    : (subjects.find((s) => String(s.id) === String(f)) || {}).name || 'Subject');
  const passes = (r) => {
    if (quick === 'pass') return hasScores(r) && r.average >= pm;
    if (quick === 'fail') return hasScores(r) && r.average < pm;
    if (quick === 'dist') return hasScores(r) && r.average >= 70;
    if (!customOn) return true;
    const x = fieldVal(r);
    if (x == null) return false;
    if (op === 'gte') return x >= n1;
    if (op === 'lte') return x <= n1;
    if (op === 'eq') return x === n1;
    return x >= Math.min(n1, n2) && x <= Math.max(n1, n2);
  };
  const customLabel = customOn ? `${fieldName()} ${op === 'between' ? `${Math.min(n1, n2)}–${Math.max(n1, n2)}` : `${OP_SIGN[op]} ${n1}`}` : 'Custom';
  // What the server export should filter by (it understands field/op/value).
  const exportFilter = quick === 'pass' ? { field: 'average', op: 'gte', v1: pm }
    : quick === 'fail' ? { field: 'average', op: 'lte', v1: pm - 0.01 }
      : quick === 'dist' ? { field: 'average', op: 'gte', v1: 70 }
        : customOn ? { field, op, v1, ...(op === 'between' ? { v2 } : {}) } : null;
  const exportUrl = (fmt) => {
    const p = new URLSearchParams({ term_id: d.term_id || '', scopes: loaded.join(','), format: fmt });
    if (exportFilter) Object.entries(exportFilter).forEach(([k, v]) => p.set(k, v));
    return `${u.export}?${p.toString()}`;
  };

  // ---- Sort ----------------------------------------------------------------
  const [sortKey, setSortKey] = useState('average');
  const [sortDir, setSortDir] = useState('desc');
  const sortVal = (r) => (sortKey === 'name' ? r.student : fieldVal(r, sortKey) ?? -1);
  const clickSort = (k) => { if (sortKey === k) setSortDir((x) => (x === 'desc' ? 'asc' : 'desc')); else { setSortKey(k); setSortDir(k === 'name' ? 'asc' : 'desc'); } };
  const arrow = (k) => (sortKey === k ? <i className={'fas fa-arrow-' + (sortDir === 'desc' ? 'down' : 'up')} aria-hidden="true" /> : null);

  const term = q.trim().toLowerCase();
  const filtered = rows.filter((r) => passes(r));
  const shown = useMemo(() => {
    const list = filtered.filter((r) => (focus == null || r.assignment_id === focus) && (!term || r.student.toLowerCase().includes(term)));
    list.sort((a, b) => {
      if (hasScores(a) !== hasScores(b)) return hasScores(a) ? -1 : 1;   // no scores yet: always last
      const x = sortVal(a), y = sortVal(b);
      const c = typeof x === 'string' ? x.localeCompare(y) : x - y;
      return sortDir === 'desc' ? -c : c;
    });
    return list;
  }, [rows, quick, field, op, v1, v2, focus, term, sortKey, sortDir]); // eslint-disable-line react-hooks/exhaustive-deps
  // Rank = place by average across everyone loaded (not the filtered view).
  const rank = useMemo(() => {
    const m = new Map(); rows.filter(hasScores).sort((a, b) => b.average - a.average).forEach((r, i) => m.set(r, i + 1)); return m;
  }, [rows]);

  // ---- Stats ---------------------------------------------------------------
  const stat = (list) => {
    const sc = list.filter((r) => r.total > 0);
    return { n: list.length, avg: mean(sc.map((r) => r.average)), pass: pct(sc.filter((r) => r.average >= pm).length, sc.length),
      passN: sc.filter((r) => r.average >= pm).length, scored: sc.length, match: list.filter(passes).length };
  };
  const all = stat(rows);
  const byScope = scopes.map((sc) => ({ sc, st: stat(rows.filter((r) => r.assignment_id === sc.assignment_id)) }));
  const best = byScope.filter((x) => x.st.avg != null).sort((a, b) => b.st.avg - a.st.avg)[0];
  const top = rows.slice().sort((a, b) => b.average - a.average)[0];
  const subjAvg = subjects.map((s) => ({ ...s, avg: mean(rows.map((r) => r.subjects[String(s.id)]).filter((x) => x != null)) })).filter((s) => s.avg != null);
  const weakest = subjAvg.slice().sort((a, b) => a.avg - b.avg)[0];
  const filtering = quick !== 'all' && (quick !== 'custom' || customOn);

  const exportCsv = () => {
    const head = ['Rank', 'Student', 'Class', 'Arm', ...subjects.map((s) => s.name), 'Total', 'Average', 'Passed', 'Failed'];
    const lines = [head, ...shown.map((r) => [rank.get(r), r.student, r.class_name, r.arm_name,
      ...subjects.map((s) => r.subjects[String(s.id)] ?? ''), r.total, r.average, r.passed, r.failed])]
      .map((cells) => cells.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
    a.download = 'results_explorer.csv'; a.click(); URL.revokeObjectURL(a.href);
  };
  const menu = [
    rows.length > 0 && { heading: filtering ? `Download (${filtered.length} filtered)` : 'Download' },
    rows.length > 0 && u.export && { icon: 'fa-file-excel', label: 'Excel', href: exportUrl('excel'), native: true, download: true },
    rows.length > 0 && u.export && { icon: 'fa-file-pdf', label: 'PDF', href: exportUrl('pdf'), native: true, download: true },
    rows.length > 0 && u.export && { icon: 'fa-print', label: 'Print', href: exportUrl('pdf'), native: true, target: '_blank' },
    rows.length > 0 && { icon: 'fa-file-csv', label: 'CSV (this view)', onClick: exportCsv },
    { heading: 'More' },
    u.combine && { icon: 'fa-layer-group', label: 'Combine subjects', href: u.combine },
    u.broadsheet && { icon: 'fa-table', label: 'Class broadsheet', href: u.broadsheet },
  ];

  const quickChips = [
    { k: 'all', label: 'Everyone', n: rows.length },
    { k: 'pass', label: `Passing (${pm}+)`, n: rows.filter((r) => hasScores(r) && r.average >= pm).length },
    { k: 'fail', label: `Below ${pm}`, n: rows.filter((r) => hasScores(r) && r.average < pm).length },
    { k: 'dist', label: 'Distinction (70+)', n: rows.filter((r) => hasScores(r) && r.average >= 70).length },
  ];

  const custom = (
    <div className="rs-filter ex-custom">
      <span>Show students whose</span>
      <select value={field} onChange={(e) => setField(e.target.value)} aria-label="Field">
        <option value="average">Average</option><option value="total">Total</option>
        {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
      <span>is</span>
      <select value={op} onChange={(e) => setOp(e.target.value)} aria-label="Condition">
        {OPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
      <input type="number" inputMode="decimal" value={v1} step="0.1" placeholder={String(pm)} onChange={(e) => setV1(e.target.value)} aria-label={op === 'between' ? 'From' : 'Value'} />
      {op === 'between' && <><span>and</span>
        <input type="number" inputMode="decimal" value={v2} step="0.1" placeholder="100" onChange={(e) => setV2(e.target.value)} aria-label="To" /></>}
      {(v1 || v2) && <button type="button" className="rs-link" onClick={() => { setV1(''); setV2(''); }}>Clear</button>}
    </div>
  );

  const pickerBody = d.scope_options.length ? (
    <>
      <ScopeList options={d.scope_options} sel={sel} toggle={toggle} toggleClass={toggleClass} />
      <div className="ex-pick-a">
        <button type="button" className="rs-link" onClick={() => setSel(new Set(sel.size === allIds.length ? [] : allIds))}>
          {sel.size === allIds.length ? 'Clear all' : 'Select all'}</button>
        <span className="rs-muted">{sel.size} arm{sel.size === 1 ? '' : 's'} selected</span>
        <button type="button" className="rs-btn primary" disabled={!sel.size || !changed} onClick={() => { setPicking(false); load(); }}>
          <i className="fas fa-check" aria-hidden="true" /> Show results</button>
      </div>
    </>
  ) : <p className="rs-muted">Choose a term to see its classes.</p>;

  return (
    <div className="rs ex">
      <Head icon="fa-filter" title="Results Explorer" sub={[termName, scopes.length ? `${scopes.length} class arm${scopes.length === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · ') || 'Compare results across arms and classes'}>
        <Menu items={menu} label="Actions" />
      </Head>

      {/* Term + classes */}
      <section className="rs-pick">
        <div className="rs-pick-row">
          <label className="rs-sel"><span>Term</span>
            <select value={d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value, scopes: '' })}>
              <option value="">Select term</option>
              {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
          {phone && (
            <div className="rs-sel grow"><span>Classes</span>
              <button type="button" className="ex-scope-btn" onClick={() => setPicking(true)} disabled={!d.term_id}>
                <b>{scopeSummary}</b><i className="fas fa-chevron-down" aria-hidden="true" /></button></div>
          )}
        </div>
        {!phone && pickerBody}
      </section>
      {phone && picking && <Sheet title="Classes & arms" onClose={() => { setPicking(false); setSel(new Set(loaded)); }}>{pickerBody}</Sheet>}

      {rows.length ? (<>
        <Tiles items={[
          { label: 'Students', value: all.n, sub: `${scopes.length} arm${scopes.length === 1 ? '' : 's'} · ${all.scored} with scores` },
          all.avg != null && { label: 'Average', value: fmtNum(r1(all.avg)), unit: '%', tone: tone(all.avg, pm) },
          { label: 'Passing', value: all.pass, unit: '%', sub: `${all.passN} of ${all.scored} at ${pm}+`, tone: all.pass >= 50 ? 'good' : 'bad' },
          !phone && top && top.total > 0 && { label: 'Top student', value: fmtNum(top.average), unit: '%', sub: `${top.student} · ${top.scope_label}` },
          !phone && scopes.length > 1 && best && { label: 'Best arm', value: fmtNum(r1(best.st.avg)), unit: '%', sub: best.sc.label, tone: tone(best.st.avg, pm) },
          scopes.length <= 1 && weakest && { label: 'Weakest subject', value: fmtNum(r1(weakest.avg)), sub: weakest.name, tone: tone(weakest.avg, pm) },
        ]} />

        {/* Compare arms — tap one to narrow the list to it */}
        {scopes.length > 1 && (
          <section className="ex-cmp" aria-label="Compare class arms">
            {byScope.map(({ sc, st }) => {
              const on = focus === sc.assignment_id;
              return (
                <button key={sc.assignment_id} type="button" className={'ex-arm' + (on ? ' on' : '')} aria-pressed={on}
                        onClick={() => setFocus(on ? null : sc.assignment_id)}>
                  <span className="ex-arm-h"><b>{sc.label}</b><small>{st.n} students</small></span>
                  <span className="ex-arm-row"><span>Average</span><b className={tone(st.avg, pm)}>{st.avg == null ? '–' : fmtNum(r1(st.avg))}</b></span>
                  <Meter value={st.avg || 0} max={100} tone={tone(st.avg, pm)} />
                  <span className="ex-arm-row"><span>Passing</span><b>{st.pass}%</b></span>
                  <Meter value={st.pass} max={100} tone={st.pass >= 50 ? 'good' : 'bad'} />
                  {filtering && <span className="ex-arm-m">{st.match} match</span>}
                </button>
              );
            })}
          </section>
        )}

        {/* One-tap filters + search */}
        <div className="ex-filters">
          <div className="rs-chips ex-quick" role="radiogroup" aria-label="Show">
            {quickChips.map((c) => (
              <button key={c.k} type="button" role="radio" aria-checked={quick === c.k} className={'rs-chip' + (quick === c.k ? ' on' : '')}
                      onClick={() => { setQuick(c.k); setShowCustom(false); }}>{c.label}<small>{c.n}</small></button>
            ))}
            <button type="button" role="radio" aria-checked={quick === 'custom'} className={'rs-chip' + (quick === 'custom' ? ' on' : '')}
                    onClick={() => { setQuick('custom'); setShowCustom(true); }}>
              <i className="fas fa-sliders" aria-hidden="true" /> {customLabel}</button>
          </div>
          {quick === 'custom' && (showCustom || !customOn) && custom}
          {focus != null && (
            <div className="ex-focus"><span className="rs-muted">Showing only</span>
              <button type="button" className="rs-chip on" onClick={() => setFocus(null)}>
                {(scopes.find((s) => s.assignment_id === focus) || {}).label} <i className="fas fa-xmark" aria-hidden="true" /></button></div>
          )}
          <div className="rs-toolbar">
            <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" placeholder="Find a student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student" /></label>
            {phone && (
              <label className="rs-sel ex-sort"><span>Sort</span>
                <select value={sortKey + '|' + sortDir} onChange={(e) => { const [k, dd] = e.target.value.split('|'); setSortKey(k); setSortDir(dd); }}>
                  <option value="average|desc">Highest average</option><option value="average|asc">Lowest average</option>
                  <option value="name|asc">Name A–Z</option>
                  {subjects.map((s) => <option key={s.id} value={s.id + '|desc'}>{s.name} (highest)</option>)}</select></label>
            )}
            <span className="rs-count">{shown.length === rows.length ? `${rows.length} students` : `${shown.length} of ${rows.length}`}</span>
          </div>
        </div>

        {phone ? (
          <div className="rs-bs-cards">
            {shown.map((r) => <ExCard key={r.student_id + '-' + r.assignment_id} r={r} rank={rank.get(r)} subjects={subjects} pm={pm}
                                      hi={quick === 'custom' && customOn ? String(field) : null} multi={scopes.length > 1} />)}
            {!shown.length && <p className="rs-muted rs-pad">No students match.</p>}
          </div>
        ) : (
          <div className="rs-card flush rs-bs-wrap">
            <table className="rs-bs ex-tbl">
              <thead><tr>
                <th className="pos">#</th>
                <th className="nm"><button type="button" className="ex-th" onClick={() => clickSort('name')}>Student {arrow('name')}</button></th>
                {scopes.length > 1 && <th className="cl">Class</th>}
                {subjects.map((s) => (
                  <th key={s.id} title={s.name} className={quick === 'custom' && customOn && String(field) === String(s.id) ? 'hi' : ''}>
                    <button type="button" className="ex-th" onClick={() => clickSort(String(s.id))}>{s.short} {arrow(String(s.id))}</button></th>
                ))}
                <th className="sum"><button type="button" className="ex-th" onClick={() => clickSort('total')}>Total {arrow('total')}</button></th>
                <th className="sum"><button type="button" className="ex-th" onClick={() => clickSort('average')}>Avg {arrow('average')}</button></th>
                <th className="sum">Pass / fail</th>
              </tr></thead>
              <tbody>{shown.length ? shown.map((r) => (
                <tr key={r.student_id + '-' + r.assignment_id}>
                  <td className="pos">{rank.has(r) ? <span className={'rs-pos ' + (rank.get(r) <= 3 ? ['', 'gold', 'silver', 'bronze'][rank.get(r)] : '')}>{rank.get(r)}</span> : <span className="rs-muted">–</span>}</td>
                  <td className="nm"><span className="ex-who"><Avatar name={r.student} gender={r.gender} />{r.student}</span></td>
                  {scopes.length > 1 && <td className="cl">{r.scope_label}</td>}
                  {subjects.map((s) => { const v = r.subjects[String(s.id)];
                    const hi = quick === 'custom' && customOn && String(field) === String(s.id);
                    return <td key={s.id} className={'sc ' + tone(v, pm) + (hi ? ' hi' : '')}>{v != null ? fmtNum(v) : '–'}</td>; })}
                  {hasScores(r) ? <>
                    <td className="sum">{fmtNum(r.total)}</td>
                    <td className={'sum avg ' + tone(r.average, pm)}>{fmtNum(r.average)}</td>
                    <td className="sum"><span className="rs-pf good">{r.passed}</span><span className={'rs-pf ' + (r.failed ? 'bad' : '')}>{r.failed}</span></td>
                  </> : <td className="sum rs-muted ex-none" colSpan={3}>No scores yet</td>}
                </tr>)) : (
                <tr><td colSpan={subjects.length + (scopes.length > 1 ? 6 : 5)} className="rs-muted rs-pad">No students match.</td></tr>)}
              </tbody>
            </table>
          </div>
        )}
        <p className="rs-legend">
          <span><i className="good" /> 70 and above</span><span><i className="mid" /> {pm}–69</span><span><i className="bad" /> below {pm}</span>
          {!phone && <span className="rs-legend-k">{subjects.map((s) => `${s.short} = ${s.name}`).join(' · ')}</span>}
        </p>
      </>) : loaded.length ? (
        <Blank icon="fa-table" title="No scores yet"><p>No scores have been entered for the chosen class arm{loaded.length === 1 ? '' : 's'} this term.</p></Blank>
      ) : (
        <Blank icon="fa-hand-pointer" title="Pick classes to compare">
          <p>{d.term_id ? (phone ? 'Tap Classes above and choose the arms to compare.' : 'Tick the classes and arms above, then Show results.') : 'Choose a term first.'}</p>
          {phone && d.term_id && <button type="button" className="rs-btn primary" onClick={() => setPicking(true)}><i className="fas fa-layer-group" aria-hidden="true" /> Choose classes</button>}
        </Blank>
      )}
    </div>
  );
}

function ExCard({ r, rank, subjects, pm, hi, multi }) {
  const [open, setOpen] = useState(false);
  const medal = rank && rank <= 3 ? ['', 'gold', 'silver', 'bronze'][rank] : '';
  const none = !hasScores(r);
  return (
    <div className={'rs-bs-card' + (open ? ' open' : '')}>
      <button type="button" className="rs-bs-top" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className={'rs-pos ' + medal}>{rank || '–'}</span>
        <span className="rs-bs-n"><b>{r.student}</b>
          <small>{multi ? r.scope_label + ' · ' : ''}{none ? 'No scores yet' : `${r.passed} passed${r.failed ? ` · ${r.failed} failed` : ''}`}
            {hi && r.subjects[hi] != null ? ` · ${(subjects.find((s) => String(s.id) === hi) || {}).short} ${fmtNum(r.subjects[hi])}` : ''}</small></span>
        <span className={'rs-bs-avg ' + (none ? '' : tone(r.average, pm))}>{none ? '–' : fmtNum(r.average)}</span>
        <i className="fas fa-chevron-down" aria-hidden="true" />
      </button>
      {open && (
        <div className="rs-bs-more">
          <div className="rs-bs-subj">
            {subjects.filter((s) => r.subjects[String(s.id)] != null).map((s) => { const v = r.subjects[String(s.id)]; return (
              <span key={s.id} className={tone(v, pm) + (hi === String(s.id) ? ' hi' : '')}><small>{s.name}</small><b>{fmtNum(v)}</b></span>); })}
          </div>
          <p className="rs-muted ex-tot">Total {fmtNum(r.total)} · Average {fmtNum(r.average)}%</p>
        </div>
      )}
    </div>
  );
}
