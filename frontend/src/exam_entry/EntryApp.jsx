// Fast SSS3 external-exam result entry — JAMB (score /100 per subject, total
// /400) and WAEC / NECO (grade A1…F9 per subject). Many students: a keyboard
// grid on laptops, tap-a-student sheets on phones. One student: a searchable
// picker and a single card. Saves as JSON to the page's own URL.
import React, { useState, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { Banner } from '../components/ui';
import { Seg, Sheet, Bar, Avatar, Blank, usePhone, useUnsavedGuard } from '../subjects/results';

// ---- exam rules --------------------------------------------------------------
const GRADE_NUM = { A1: 1, B2: 2, B3: 3, C4: 4, C5: 5, C6: 6, D7: 7, E8: 8, F9: 9 };
const NUM_GRADE = ['', 'A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9'];
const gTone = (g) => (!g ? '' : GRADE_NUM[g] <= 3 ? 'a' : GRADE_NUM[g] <= 6 ? 'c' : GRADE_NUM[g] <= 8 ? 'd' : 'f');
const jTone = (t) => (t >= 250 ? 'a' : t >= 200 ? 'c' : t >= 180 ? 'd' : 'f');
const sTone = (v) => (v >= 70 ? 'a' : v >= 50 ? 'c' : v >= 40 ? 'd' : 'f');
const SHORT = { 'English Language': 'English', 'Mathematics': 'Maths', 'General Mathematics': 'Maths', 'Christian Religious Studies': 'CRS',
  'Islamic Religious Studies': 'IRS', 'Literature in English': 'Literature', 'Agricultural Science': 'Agric', 'Further Mathematics': 'F. Maths',
  'Civic Education': 'Civic', 'Computer Studies': 'Computer', 'Data Processing': 'Data Proc.', 'Technical Drawing': 'Tech. Drawing',
  'Food and Nutrition': 'Food & Nut.', 'Digital Technologies': 'Digital Tech', 'Livestock Farming': 'Livestock', 'Financial Accounting': 'Accounting',
  // JSS3 BECE / Common Entrance
  'English Studies': 'English', 'Basic Science': 'Basic Sci.', 'Basic Technology': 'Basic Tech.', 'National Values Education': 'NVE',
  'Pre-Vocational Studies': 'PVS', 'Cultural and Creative Arts': 'CCA', 'Islamic Studies': 'IRS', 'Business Studies': 'Business',
  'Basic Digital Literacy': 'Digital Lit.', 'Physical and Health Education': 'PHE', 'Security Education': 'Security Ed.',
  'Home Economics': 'Home Econ.', 'Social Studies': 'Social St.', 'Basic Science and Technology': 'BST',
  'Quantitative Reasoning': 'Quant.', 'Verbal Reasoning': 'Verbal', 'General Paper': 'Gen. Paper',
  'Religion and National Values': 'RNV', 'Nigerian Language': 'Nig. Lang.' };
const short = (n) => {
  if (!n) return 'Pick subject';
  if (SHORT[n]) return SHORT[n];
  if (n.length <= 12) return n;
  const caps = n.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).map((w) => w[0]).join('');
  return caps.length >= 2 ? caps : n.slice(0, 11) + '…';
};
const isEnglish = (n) => /english/i.test(n || '');
const isMaths = (n) => /math/i.test(n || '') && !/further/i.test(n || '');

// JSS3 BECE / Common Entrance: the board's own grade bands (A/B/C/P/F …),
// or a score out of max that maps to a band.
const KIND_TONE = { distinction: 'a', credit: 'c', pass: 'd', fail: 'f' };
const bandOf = (d, g) => (d.bands || []).find((b) => b.grade === g);
const gradeFromScore = (d, v) => {
  if (v === '' || v == null || !d.bands) return '';
  const pct = Math.max(0, Math.min(100, (+v / (d.max_subject || 100)) * 100));
  const b = d.bands.find((x) => pct + 1e-9 >= +x.min);
  return b ? b.grade : d.bands[d.bands.length - 1].grade;
};
const schoolTone = (d, g) => { const b = bandOf(d, g); return b ? KIND_TONE[b.kind] || '' : ''; };
const isCredit = (d, g) => { const b = bandOf(d, g); return !!b && (b.kind === 'distinction' || b.kind === 'credit'); };

function rulesFor(d, smode) {
  if (d.exam === 'school' && smode === 'grade') {
    const gs = d.grades || [];
    return {
      kind: 'grade', school: true,
      hint: `Type the grade letter (${gs.join(', ')}) — the cursor moves on by itself.`,
      clean: (v) => { const t = v.toUpperCase().replace(/[^A-Z]/g, ''); const last = t.slice(-1); return gs.includes(last) ? last : ''; },
      full: (v) => gs.includes(v),
      bad: (x) => (x.value !== '' && !gs.includes(x.value)) || (x.value !== '' && !x.name),
      label: () => '',
      tone: (v) => schoolTone(d, v),
    };
  }
  if (d.exam === 'school') {
    const mx = d.max_subject || 100;
    return {
      kind: 'score', school: true,
      hint: `Type each subject’s score out of ${mx} — the grade is worked out and the cursor moves on by itself.`,
      clean: (v) => v.replace(/[^0-9]/g, '').slice(0, String(mx).length),
      full: (v) => v.length >= String(mx).length || (v.length === String(mx).length - 1 && +v * 10 > mx),
      bad: (x) => x.value !== '' && (+x.value > mx || !x.name),
      label: () => '/' + mx,
      tone: (v) => (v === '' ? '' : schoolTone(d, gradeFromScore(d, v))),
    };
  }
  if (d.exam === 'jamb') {
    return {
      kind: 'score',
      hint: 'Type each subject’s UTME score out of 100 — the cursor moves on by itself and the total adds up.',
      clean: (v) => v.replace(/[^0-9]/g, '').slice(0, 3),
      full: (v) => v.length >= 3 || (v.length === 2 && +v > 10),
      bad: (x) => x.value !== '' && (+x.value > 100 || (!x.name)),
      label: () => '/100',
      tone: (v) => (v === '' ? '' : sTone(+v)),
    };
  }
  return {
    kind: 'grade',
    hint: 'Type the grade’s number — 1 = A1, 2 = B2, 3 = B3 … 9 = F9 — or the grade itself. The cursor moves on by itself.',
    clean: (v, prev) => {
      const t = v.toUpperCase().replace(/[^A-F0-9]/g, '');
      if (!t) return '';
      const last = t[t.length - 1];
      if (/[1-9]/.test(last) && (t.length === 1 || !/[A-F]/.test(t[t.length - 2]))) return NUM_GRADE[+last];
      const m = t.match(/([A-F])([1-9])$/);
      if (m && GRADE_NUM[m[1] + m[2]]) return m[1] + m[2];
      if (/[A-F]$/.test(t)) return t.slice(-1);       // a letter waiting for its number
      return prev || '';
    },
    full: (v) => !!GRADE_NUM[v],
    bad: (x) => (x.value !== '' && !GRADE_NUM[x.value]) || (x.value !== '' && !x.name),
    label: () => '',
    tone: (v) => gTone(v),
  };
}

function summary(d, subs, smode) {
  if (d.exam === 'school') {
    const eff = subs.filter((x) => x.name).map((x) => ({ name: x.name, g: smode === 'score' ? (x.value !== '' ? gradeFromScore(d, x.value) : x.grade) : x.value }))
      .filter((x) => x.g);
    if (!eff.length) return null;
    const cr = eff.filter((x) => isCredit(d, x.g));
    const five = cr.length >= (d.benchmark || 5) && cr.some((x) => isEnglish(x.name)) && cr.some((x) => isMaths(x.name));
    const total = smode === 'score' ? subs.reduce((t, x) => t + (x.value !== '' ? +x.value : 0), 0) : null;
    return { n: eff.length, credits: cr.length, five, total };
  }
  if (d.exam === 'jamb') {
    const typed = subs.filter((x) => x.value !== '');
    return typed.length ? typed.reduce((t, x) => t + (+x.value || 0), 0) : null;
  }
  const gs = subs.filter((x) => GRADE_NUM[x.value]);
  if (!gs.length) return null;
  const credits = gs.filter((x) => GRADE_NUM[x.value] <= 6);
  const five = credits.length >= 5 && credits.some((x) => isEnglish(x.name)) && credits.some((x) => isMaths(x.name));
  return { n: gs.length, credits: credits.length, five };
}

function SubjectPick({ d, value, onChange, locked, need, wide }) {
  return (
    <label className={'xe-subj' + (locked ? ' locked' : '') + (need ? ' need' : '') + (wide ? ' wide' : '')}>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Subject" disabled={locked}>
        <option value="">— none —</option>
        {d.offered && d.offered.length ? (
          <>
            <optgroup label="Offered this session">{d.offered.map((s) => <option key={s} value={s}>{s}</option>)}</optgroup>
            {d.subjects.length > d.offered.length && <optgroup label="Other subjects">{d.subjects.filter((s) => !d.offered.includes(s)).map((s) => <option key={s} value={s}>{s}</option>)}</optgroup>}
          </>
        ) : d.subjects.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <span aria-hidden="true" title={value || undefined}><em>{wide ? (value || 'Pick subject') : short(value)}</em>{!locked && <i className="fas fa-chevron-down" />}</span>
    </label>
  );
}

function ValueBox({ d, R, x, onChange, inputProps, big, label }) {
  const tone = x.value !== '' ? R.tone(x.value) : '';
  const ph = R.school && R.kind === 'score' && x.value === '' && x.grade ? x.grade : '–';
  return (
    <span className={'xe-box' + (big ? ' big' : '') + (R.bad(x) ? ' bad' : '') + (x.value !== '' ? ' on t-' + tone : '')}>
      <input type="text" inputMode={R.kind === 'grade' ? 'text' : 'numeric'} autoComplete="off" autoCapitalize="characters" spellCheck="false"
             enterKeyHint="next" placeholder={ph} aria-label={label} value={x.value}
             onChange={(e) => onChange(R.clean(e.target.value, x.value))} {...inputProps} />
      {R.label() && <small>{R.school && x.value !== '' ? gradeFromScore(d, x.value) : R.label()}</small>}
    </span>
  );
}

// Phone sheet / one-student card.
function Card({ d, R, subs, setSubs, autoFocus, smode, extra }) {
  const refs = useRef([]);
  const rows = useRef([]);
  useEffect(() => { if (autoFocus && R.kind === 'score' && refs.current[0]) setTimeout(() => refs.current[0] && refs.current[0].focus(), 250); }, [autoFocus]); // eslint-disable-line
  const setSub = (i, patch) => setSubs(subs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const next = (i) => {
    if (R.kind === 'score') { if (refs.current[i + 1]) refs.current[i + 1].focus(); return; }
    for (let k = i + 1; k < subs.length; k += 1) {
      const el = rows.current[k];
      if (subs[k].name && el) { el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); return; }
    }
  };
  const sm = summary(d, subs, smode);
  // Grades: show the student's subjects plus one "add a subject" slot; empty
  // slots beyond that stay hidden so there is nothing to tap by mistake.
  const firstBlank = R.kind === 'grade' ? subs.findIndex((x) => !x.name) : -1;
  return (
    <div className="xe-card">
      {subs.map((x, i) => (R.kind === 'grade' && !x.name ? (i === firstBlank && (
        <div key={i} className="xe-line xe-add">
          <i className="fas fa-plus" aria-hidden="true" />
          <SubjectPick d={d} wide value="" onChange={(v) => setSub(i, { name: v })} />
          <small>Add a subject</small>
        </div>)) : (
        <div key={i} className={'xe-line' + (R.kind === 'grade' ? ' g' : '')} ref={(el) => { rows.current[i] = el; }}>
          <SubjectPick d={d} wide value={x.name} need={x.value !== '' && !x.name}
                       locked={d.exam === 'jamb' && i === 0 && x.name === d.compulsory} onChange={(v) => setSub(i, { name: v })} />
          {R.kind === 'score' ? (
            <ValueBox d={d} R={R} x={x} big label={`${x.name || 'Subject'} score out of 100`}
                      inputProps={{ ref: (el) => { refs.current[i] = el; } }}
                      onChange={(v) => { setSub(i, { value: v }); if (R.full(v)) next(i); }} />
          ) : (
            <div className="xe-pad" role="radiogroup" aria-label={`${x.name || 'Subject'} grade`} style={{ gridTemplateColumns: `repeat(${d.grades.length}, minmax(0, 1fr))` }}>
              {d.grades.map((g) => (
                <button type="button" key={g} role="radio" aria-checked={x.value === g} className={'t-' + R.tone(g) + (x.value === g ? ' on' : '')}
                        title={R.school ? (bandOf(d, g) || {}).label : undefined}
                        onClick={() => { setSub(i, { value: x.value === g ? '' : g }); if (x.value !== g) next(i); }}>{g}</button>))}
            </div>
          )}
        </div>
      )))}
      {d.exam === 'school' ? (
        <div className={'xe-total' + (sm ? (sm.five ? ' t-a' : ' t-d') : '')}>
          {sm ? <><span>{sm.n} subject{sm.n === 1 ? '' : 's'}{sm.total != null ? ` · total ${sm.total}` : ''}</span><b>{sm.credits}</b><small>credits{sm.five ? ` · ${d.benchmark}+ incl. English & Maths ✓` : ` · need ${d.benchmark} incl. English & Maths`}</small></>
            : <span>No {smode === 'score' ? 'scores' : 'grades'} yet</span>}
        </div>
      ) : d.exam === 'jamb' ? (
        <div className={'xe-total' + (sm != null ? ' t-' + jTone(sm) : '')}><span>Total</span><b>{sm == null ? '—' : sm}</b><small>/ {d.max_total}</small></div>
      ) : (
        <div className={'xe-total' + (sm ? (sm.five ? ' t-a' : ' t-d') : '')}>
          {sm ? <><span>{sm.n} subject{sm.n === 1 ? '' : 's'}</span><b>{sm.credits}</b><small>credits{sm.five ? ' · 5 incl. English & Maths ✓' : ''}</small></> : <span>No grades yet</span>}
        </div>
      )}
      {extra}
    </div>
  );
}

// Candidate sitting details for JSS3 / Basic 6 exams.
function CandFields({ d, c, set }) {
  const f = (k) => (e) => set({ ...c, [k]: e.target.value });
  return (
    <details className="xe-cand" open={!!(c.exam_number || c.total_score || c.placement || c.remarks)}>
      <summary><i className="fas fa-id-card" aria-hidden="true" />Exam number, total &amp; {d.level === 'basic6' ? 'admission' : 'placement'}</summary>
      <div className="xe-cand-g">
        <label className="rs-sel"><span>Exam number</span><input value={c.exam_number} onChange={f('exam_number')} autoComplete="off" /></label>
        <label className="rs-sel"><span>Total score{d.cutoff ? ` (cut-off ${d.cutoff})` : ''}</span><input inputMode="decimal" value={c.total_score} onChange={f('total_score')} /></label>
        <label className="rs-sel"><span>{d.outcome_label}</span><input value={c.placement} onChange={f('placement')} /></label>
        <label className="rs-sel"><span>Admitted?</span><select value={c.admitted} onChange={f('admitted')}><option value="">Not known</option><option value="yes">Yes</option><option value="no">No</option></select></label>
        <label className="rs-sel xe-cand-w"><span>Remarks</span><input value={c.remarks} onChange={f('remarks')} /></label>
      </div>
    </details>
  );
}

const clone = (subs, d, smode) => subs.map((x) => (d && d.exam === 'school'
  ? { ...x, value: smode === 'score' ? (x.score == null ? '' : String(x.score)) : (x.grade || '') }
  : { ...x }));

export default function EntryApp({ data }) {
  const [d, setD] = useState(data);
  const [smode, setSmode] = useState(() => (data.exam === 'school' && data.students.some((s) => s.subjects.some((x) => x.score != null)) ? 'score' : 'grade'));
  const R = rulesFor(d, smode);
  const phone = usePhone();
  const init = () => { const m = {}; d.students.forEach((s) => { m[s.id] = clone(s.subjects, d, smode); }); return m; };
  const initC = () => { const m = {}; d.students.forEach((s) => { if (s.cand) m[s.id] = { ...s.cand }; }); return m; };
  const [cand, setCand] = useState(initC);
  const [candDirty, setCandDirty] = useState({});
  const setC = (id, v) => { setCand((m) => ({ ...m, [id]: v })); setCandDirty((m) => ({ ...m, [id]: true })); setDirty((m) => ({ ...m, [id]: true })); };
  const initT = () => { const m = {}; d.students.forEach((s) => { m[s.id] = s.total || ''; }); return m; };
  const [rows, setRows] = useState(init);
  const [totals, setTotals] = useState(initT);
  const [dirty, setDirty] = useState({});
  const [saved, setSaved] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState(() => (d.preselect || new URLSearchParams(window.location.search).get('mode') === 'one' ? 'one' : 'many'));
  const [totalOnly, setTotalOnly] = useState(false);
  const [show, setShow] = useState(() => (d.students.some((s) => !s.entered) ? 'todo' : 'all'));
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(null);
  const [sheetErr, setSheetErr] = useState('');
  const [one, setOne] = useState(d.preselect ? String(d.preselect) : '');
  useEffect(() => { setRows(init()); setTotals(initT()); setCand(initC()); setCandDirty({}); setDirty({}); setSaved({}); }, [d, smode]); // eslint-disable-line
  const nDirty = Object.keys(dirty).length;
  useUnsavedGuard(nDirty > 0);
  const notify = (tone, text) => setMsg({ tone, text });
  const isDone = (s) => s.entered || saved[s.id];
  const term = q.trim().toLowerCase();
  const list = d.students.filter((s) => (!term || (s.name + ' ' + s.student_id).toLowerCase().includes(term))
    && (show === 'all' || (show === 'todo' && !isDone(s)) || (show === 'done' && isDone(s))));
  const nDone = d.students.filter(isDone).length;
  const setRow = (id, subs) => { setRows((m) => ({ ...m, [id]: subs })); setDirty((m) => ({ ...m, [id]: true })); };
  const setTotal = (id, v) => { setTotals((m) => ({ ...m, [id]: v.replace(/[^0-9]/g, '').slice(0, 3) })); setDirty((m) => ({ ...m, [id]: true })); };
  const rowBad = (id) => {
    if (d.exam === 'jamb' && totalOnly) return totals[id] !== '' && +totals[id] > d.max_total;
    const subs = rows[id];
    if (subs.some(R.bad)) return true;
    const named = subs.filter((x) => x.name && x.value !== '').map((x) => x.name);
    return new Set(named).size !== named.length;
  };

  const changeYear = async (y) => {
    if (nDirty && !window.confirm('You have unsaved results. Switch session anyway?')) return;
    const url = `${d.self_url}?year=${y}`;
    const r = await fetch(url, { headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' }, credentials: 'same-origin' });
    if (!r.ok) { notify('error', 'Could not load that session.'); return; }
    const nd = await r.json();
    setD(nd); setOpen(null); setOne('');
    try { window.history.replaceState(null, '', url); } catch (e) { /* ignore */ }
  };
  const fieldsFor = (ids) => {
    const f = { bulk: '1', exam_year: d.year, sids: ids.map(String) };
    ids.forEach((id) => {
      if (d.exam === 'school') {
        const subs = rows[id];
        f['subj_' + id] = subs.map((x) => x.name);
        if (smode === 'score') {
          f['score_' + id] = subs.map((x) => (x.name ? x.value : ''));
          f['grade_' + id] = subs.map((x) => (x.name && x.value === '' ? (x.grade || '') : ''));
        } else {
          f['grade_' + id] = subs.map((x) => (x.name ? x.value : ''));
          f['score_' + id] = subs.map((x) => (x.name && x.value && x.value === x.grade && x.score != null ? String(x.score) : ''));
        }
        if (candDirty[id] && cand[id]) {
          f['cand_' + id] = '1';
          Object.entries(cand[id]).forEach(([k, v]) => { f[`${k}_${id}`] = v; });
        }
        return;
      }
      if (d.exam === 'jamb') {
        if (totalOnly) { f['total_' + id] = totals[id]; return; }
        rows[id].forEach((x, i) => { f[`subject${i + 1}_${id}`] = x.name; f[`subject${i + 1}_score_${id}`] = x.value; });
      } else {
        f['subj_' + id] = rows[id].map((x) => x.name);
        f['grade_' + id] = rows[id].map((x) => (x.name ? x.value : ''));
      }
    });
    return f;
  };
  const save = async (ids, quiet) => {
    const bad = ids.filter(rowBad);
    if (bad.length) {
      const t = d.exam === 'jamb' ? 'Fix the red boxes — a score over 100, a score with no subject, or the same subject twice.'
        : d.exam === 'school' ? `Fix the red boxes — ${smode === 'score' ? `a score over ${d.max_subject}` : 'an unknown grade'}, a result with no subject, or the same subject twice.`
        : 'Fix the red boxes — a grade with no subject, or the same subject twice.';
      setSheetErr(t); notify('error', t); return false;
    }
    setBusy(true);
    const r = await submitJson(d.save_url, fieldsFor(ids));
    setBusy(false);
    if (!r.ok) { setSheetErr(r.error || 'Could not save.'); notify('error', r.error || 'Could not save.'); return false; }
    if (r.problems && r.problems.length) { notify('error', r.message); setSheetErr(r.message); return false; }
    if (!quiet) notify('success', r.message);
    setSaved((m) => { const n = { ...m }; ids.forEach((id) => { n[id] = true; }); return n; });
    setDirty((m) => { const n = { ...m }; ids.forEach((id) => { delete n[id]; }); return n; });
    setCandDirty((m) => { const n = { ...m }; ids.forEach((id) => { delete n[id]; }); return n; });
    return true;
  };

  // ---- desktop grid keyboard ----
  const grid = useRef(null);
  const nCols = d.exam === 'jamb' ? (totalOnly ? 1 : 4) : Math.max(...d.students.map((s) => s.subjects.length), d.slots || 9);
  const gridKind = d.exam === 'school' && smode === 'score' ? 'score' : R.kind;
  const focusCell = (r, c) => { const el = grid.current && grid.current.querySelector(`[data-r="${r}"][data-c="${c}"]`); if (el) { el.focus(); el.select && el.select(); } };
  const onKey = (r, c) => (e) => {
    if (e.key === 'Enter' || e.key === 'ArrowDown') { e.preventDefault(); focusCell(r + 1, c); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusCell(r - 1, c); }
    else if (e.key === 'ArrowRight' && e.target.selectionStart === e.target.value.length) { e.preventDefault(); if (c + 1 < nCols) focusCell(r, c + 1); else focusCell(r + 1, 0); }
    else if (e.key === 'ArrowLeft' && e.target.selectionStart === 0) { e.preventDefault(); if (c > 0) focusCell(r, c - 1); else focusCell(r - 1, nCols - 1); }
    else if (e.key === 'Delete') { e.preventDefault(); e.target.value = ''; e.target.dispatchEvent(new Event('input', { bubbles: true })); }
  };
  const advance = (r, c, s) => {
    // Skip empty subject slots so the cursor lands on the next real subject.
    const subs = rows[s.id];
    for (let k = c + 1; k < subs.length; k += 1) { if (subs[k].name || d.exam === 'jamb') { focusCell(r, k); return; } }
    focusCell(r + 1, 0);
  };

  // ---- phone flow ----
  const openIdx = open == null ? -1 : list.findIndex((s) => s.id === open);
  const cur = d.students.find((s) => s.id === open);
  useEffect(() => setSheetErr(''), [open]);
  const nextAfter = (id) => { const i = list.findIndex((s) => s.id === id); const rest = [...list.slice(i + 1), ...list.slice(0, i)]; return (rest.find((s) => !isDone(s) && s.id !== id) || {}).id; };
  const typedFor = (id) => (d.exam === 'jamb' && totalOnly ? totals[id] !== '' : rows[id].some((x) => x.value !== '') || !!candDirty[id]);
  const saveAndNext = async () => {
    const id = cur.id;
    if (typedFor(id) || dirty[id]) { if (!await save([id], true)) return; notify('success', `${cur.name} saved.`); }
    const n = nextAfter(id);
    setOpen(n || null);
  };

  // ---- one student ----
  const oneStu = d.students.find((s) => String(s.id) === String(one));
  const oneMatches = d.students.filter((s) => !term || (s.name + ' ' + s.student_id).toLowerCase().includes(term));
  const saveOne = async (e) => {
    e.preventDefault();
    if (!oneStu) return;
    if (!typedFor(oneStu.id) && !dirty[oneStu.id]) { notify('error', d.exam === 'jamb' ? 'Type at least one score.' : 'Pick at least one grade.'); return; }
    if (await save([oneStu.id], true)) {
      notify('success', `${oneStu.name}: results saved.`);
      const n = nextAfter(oneStu.id);
      setOne(n ? String(n) : ''); setQ('');
    }
  };

  const pct = d.students.length ? Math.round((nDone / d.students.length) * 100) : 0;
  const colsHead = d.exam === 'jamb' ? (totalOnly ? ['Total /400'] : ['English', 'Subject 2', 'Subject 3', 'Subject 4'])
    : Array.from({ length: nCols }, (_, i) => `${i + 1}`);

  return (
    <div className={'xe xe-' + gridKind + (d.exam === 'school' ? ' xe-school' : '') + (phone && mode === 'many' && !open ? ' has-bar' : '')}>
      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      <section className="rs-card xe-top">
        <div className="xe-prog"><b>{nDone} of {d.students.length}</b><span>students have {d.board} results</span>
          <span className="xe-meter"><i style={{ width: pct + '%' }} /></span></div>
        <label className="rs-sel xe-year"><span>Session</span>
          <select value={d.year} onChange={(e) => changeYear(e.target.value)}>
            {d.sessions.map((s) => <option key={s.year} value={s.year}>{s.label === String(s.year) ? `${d.board} ${s.year}` : `${s.label} (${d.board} ${s.year})`}</option>)}</select></label>
        <Seg label="Enter for" value={mode} onChange={setMode} options={[{ value: 'many', label: 'Many students', icon: 'fa-table-cells' }, { value: 'one', label: 'One student', icon: 'fa-user' }]} />
        {d.exam === 'school' && (
          <Seg label="Enter as" value={smode} onChange={(v) => { if (v === smode) return; if (nDirty && !window.confirm('Switching loses what you have not saved. Continue?')) return; setSmode(v); }}
               options={[{ value: 'grade', label: `Grades (${(d.grades || []).join(' ')})`, icon: 'fa-medal' }, { value: 'score', label: `Scores /${d.max_subject}`, icon: 'fa-hashtag' }]} />)}
      </section>

      {!d.students.length ? (
        <Blank icon="fa-users" title={`No ${d.class_label || 'SSS3'} students`}><p>Enrol students in {d.class_label || 'SSS3'} for the active term, then come back.</p></Blank>
      ) : mode === 'one' ? (
        <form className="xe-one" onSubmit={saveOne}>
          <section className="rs-card xe-pick">
            <div className="rs-card-h"><h3><i className="fas fa-user-graduate" aria-hidden="true" />Student</h3>
              <small className="rs-muted">{d.students.length - nDone} still to enter</small></div>
            {oneStu ? (
              <div className="xe-chosen"><Avatar name={oneStu.name} gender={oneStu.gender} />
                <span><b>{oneStu.name}</b><small>{[oneStu.student_id, oneStu.stream].filter(Boolean).join(' · ')}{isDone(oneStu) ? ' · has results' : ''}</small></span>
                <button type="button" className="rs-btn ghost sm" onClick={() => setOne('')}>Change</button></div>
            ) : (
              <>
                <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
                  <input type="search" autoFocus={!phone} placeholder="Type a name or ID" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student"
                         onKeyDown={(e) => { if (e.key === 'Enter' && oneMatches.length) { e.preventDefault(); setOne(String(oneMatches[0].id)); } }} /></label>
                <div className="xe-opts" role="listbox" aria-label="Students">
                  {oneMatches.slice(0, 60).map((s) => (
                    <button type="button" role="option" aria-selected="false" key={s.id} className="xe-opt" onClick={() => setOne(String(s.id))}>
                      <Avatar name={s.name} gender={s.gender} /><span><b>{s.name}</b><small>{s.student_id}{isDone(s) ? ' · has results' : ''}</small></span>
                      {isDone(s) && <i className="fas fa-circle-check xe-ok" aria-label="Has results" />}</button>))}
                  {!oneMatches.length && <p className="rs-muted rs-pad">No student matches.</p>}
                </div>
              </>
            )}
          </section>
          <section className={'rs-card xe-scores' + (oneStu ? '' : ' off')}>
            <div className="rs-card-h"><h3><i className={'fas ' + (R.kind === 'grade' ? 'fa-medal' : 'fa-list-ol')} aria-hidden="true" />{R.kind === 'grade' ? 'Grades' : 'Scores'}</h3>
              <small className="rs-muted">{R.kind === 'grade' ? 'Tap a grade for each subject' : 'Each subject out of 100'}</small></div>
            {oneStu ? <Card key={oneStu.id} d={d} R={R} smode={smode} subs={rows[oneStu.id]} setSubs={(v) => setRow(oneStu.id, v)} autoFocus
              extra={d.exam === 'school' && cand[oneStu.id] && <CandFields d={d} c={cand[oneStu.id]} set={(v) => setC(oneStu.id, v)} />} />
              : <p className="rs-muted rs-pad">Pick a student first.</p>}
            {oneStu && !oneStu.has_profile_subjects && <p className="xe-note"><i className="fas fa-circle-info" aria-hidden="true" />No {d.board} subjects on this student’s profile — the usual subjects are filled in; change any that differ.</p>}
            <div className="xe-acts">
              <a href={d.list_url} className="rs-btn ghost">Done</a>
              <button type="submit" className="rs-btn primary" disabled={busy || !oneStu}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />{busy ? 'Saving…' : 'Save & next student'}</button>
            </div>
          </section>
        </form>
      ) : (
        <>
          <div className="xe-tools">
            <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" placeholder="Find a student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student" /></label>
            <Seg label="Show" value={show} onChange={setShow} options={[
              { value: 'todo', label: 'To enter', count: d.students.length - nDone }, { value: 'done', label: 'Entered', count: nDone }, { value: 'all', label: 'All', count: d.students.length }]} />
            {d.exam === 'jamb' && (
              <label className="rs-check"><input type="checkbox" checked={totalOnly} onChange={(e) => { if (nDirty && !window.confirm('Switching loses what you have not saved. Continue?')) return; setDirty({}); setRows(init()); setTotals(initT()); setTotalOnly(e.target.checked); }} />Total only</label>)}
          </div>
          {!phone && <p className="xe-hint"><i className="fas fa-keyboard" aria-hidden="true" /><span>{d.exam === 'jamb' && totalOnly ? 'Type each student’s total out of 400.' : R.hint} <kbd>Enter</kbd> goes to the next student; arrow keys move around. Click a subject name to change it.</span></p>}
          {!list.length ? (
            <Blank icon={show === 'todo' ? 'fa-circle-check' : 'fa-users'} title={show === 'todo' ? `Everyone has ${d.board} results` : 'No students match'}>
              {show === 'todo' && <button type="button" className="rs-btn" onClick={() => setShow('all')}>Show everyone</button>}</Blank>
          ) : phone ? (
            <div className="rs-card xe-plist">
              {list.map((s) => {
                const sm = d.exam === 'jamb' && totalOnly ? (totals[s.id] || null) : summary(d, rows[s.id], smode);
                return (
                  <button type="button" key={s.id} className={'xe-prow' + (isDone(s) ? ' done' : '')} onClick={() => setOpen(s.id)}>
                    <Avatar name={s.name} gender={s.gender} />
                    <span className="xe-pt"><b>{s.name}</b><small>{[s.student_id, s.stream].filter(Boolean).join(' · ')}</small></span>
                    {sm == null ? <span className="xe-pnone">Enter</span>
                      : d.exam === 'jamb' ? <span className={'xe-ptot t-' + jTone(+sm)}>{sm}</span>
                        : d.exam === 'school' ? <span className={'xe-ptot ' + (sm.five ? 't-a' : 't-d')}>{sm.credits}<small> cr</small></span>
                        : <span className={'xe-ptot ' + (sm.five ? 't-a' : 't-d')}>{sm.credits}<small> cr</small></span>}
                    <i className="fas fa-chevron-right" aria-hidden="true" />
                  </button>);
              })}
            </div>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); const ids = Object.keys(dirty).map(Number); if (ids.length) save(ids); }}>
              <div className={'rs-card xe-grid' + (d.exam === 'jamb' && totalOnly ? ' tot' : '')} ref={grid} role="table" aria-label={`${d.board} results`}
                   style={{ '--xe-cols': nCols }}>
                <div className="xe-gr xe-gh" role="row">
                  <span role="columnheader">Student</span>
                  {colsHead.map((h, i) => <span role="columnheader" key={i}>{h}</span>)}
                  <span role="columnheader">{d.exam === 'jamb' ? (totalOnly ? '' : 'Total') : d.exam === 'school' && smode === 'score' ? 'Credits · total' : 'Credits'}</span>
                </div>
                {list.map((s, r) => {
                  const subs = rows[s.id];
                  const sm = summary(d, subs, smode);
                  return (
                    <div key={s.id} role="row" className={'xe-gr' + (dirty[s.id] ? ' dirty' : '') + (rowBad(s.id) ? ' bad' : '')}>
                      <span className="xe-who" role="cell"><b>{s.name}</b>
                        <small>{s.student_id}{isDone(s) && !dirty[s.id] && <em className="ok"> · saved</em>}{dirty[s.id] && <em> · not saved</em>}</small></span>
                      {d.exam === 'jamb' && totalOnly ? (
                        <span role="cell" className={'xe-box' + (totals[s.id] !== '' ? ' on t-' + jTone(+totals[s.id]) : '') + (rowBad(s.id) ? ' bad' : '')}>
                          <input type="text" inputMode="numeric" value={totals[s.id]} placeholder="–" aria-label={`${s.name} total`} data-r={r} data-c={0}
                                 onKeyDown={onKey(r, 0)} onFocus={(e) => e.target.select()} onChange={(e) => setTotal(s.id, e.target.value)} /><small>/400</small></span>
                      ) : subs.map((x, c) => (
                        <span role="cell" key={c} className={'xe-cell' + (x.name ? '' : ' empty')}>
                          <SubjectPick d={d} value={x.name} need={x.value !== '' && !x.name} locked={d.exam === 'jamb' && c === 0 && x.name === d.compulsory}
                                       onChange={(v) => setRow(s.id, subs.map((y, j) => (j === c ? { ...y, name: v } : y)))} />
                          <ValueBox d={d} R={R} x={x} label={`${s.name} ${x.name || 'subject ' + (c + 1)}`}
                            inputProps={{ 'data-r': r, 'data-c': c, onKeyDown: onKey(r, c), onFocus: (e) => e.target.select() }}
                            onChange={(v) => { setRow(s.id, subs.map((y, j) => (j === c ? { ...y, value: v } : y))); if (R.full(v)) advance(r, c, s); }} />
                        </span>
                      ))}
                      {d.exam === 'jamb' ? (
                        !totalOnly && <span role="cell" className={'xe-sum' + (sm != null ? ' t-' + jTone(sm) : '')}>{sm == null ? '—' : sm}</span>
                      ) : (
                        <span role="cell" className={'xe-sum' + (sm ? (sm.five ? ' t-a' : ' t-d') : '')}
                              title={sm ? `${sm.credits} credit${sm.credits === 1 ? '' : 's'}${sm.five ? ' including English and Maths' : ''}` : ''}>
                          {sm ? <>{sm.credits}{sm.five && <i className="fas fa-check" aria-hidden="true" />}{sm.total != null && <small className="xe-sum-t">{sm.total}</small>}</> : '—'}</span>
                      )}
                    </div>
                  );
                })}
              </div>
              <Bar>
                <span className="rs-bar-t"><b>{nDirty ? `${nDirty} unsaved` : 'All saved'}</b><small>{nDone}/{d.students.length} entered · <a href={d.list_url}>see results</a></small></span>
                <button type="submit" className="rs-btn primary" disabled={busy || !nDirty}><i className="fas fa-floppy-disk" aria-hidden="true" />{busy ? 'Saving…' : 'Save results'}</button>
              </Bar>
            </form>
          )}
        </>
      )}

      {phone && mode === 'many' && cur && (
        <Sheet title={cur.name} onClose={() => setOpen(null)}>
          <div className="xe-sheet">
            <p className="xe-sub">{[cur.student_id, cur.stream].filter(Boolean).join(' · ')}{openIdx >= 0 && ` · ${openIdx + 1} of ${list.length}`}</p>
            {d.exam === 'jamb' && totalOnly ? (
              <div className="xe-card"><div className="xe-line"><span className="xe-subj wide locked"><span>Total score</span></span>
                <span className={'xe-box big' + (totals[cur.id] !== '' ? ' on' : '')}>
                  <input type="text" inputMode="numeric" autoFocus value={totals[cur.id]} placeholder="–" aria-label="Total score" onChange={(e) => setTotal(cur.id, e.target.value)} /><small>/400</small></span></div></div>
            ) : <Card key={cur.id} d={d} R={R} smode={smode} subs={rows[cur.id]} setSubs={(v) => setRow(cur.id, v)} autoFocus
              extra={d.exam === 'school' && cand[cur.id] && <CandFields d={d} c={cand[cur.id]} set={(v) => setC(cur.id, v)} />} />}
            {sheetErr && <p className="xe-err" role="alert"><i className="fas fa-circle-exclamation" aria-hidden="true" />{sheetErr}</p>}
            <div className="xe-acts">
              <button type="button" className="rs-btn" disabled={openIdx <= 0} onClick={() => setOpen(list[openIdx - 1].id)} aria-label="Previous student"><i className="fas fa-chevron-left" aria-hidden="true" /></button>
              <button type="button" className="rs-btn primary" disabled={busy} onClick={saveAndNext}>
                <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />{busy ? 'Saving…' : 'Save & next'}</button>
            </div>
          </div>
        </Sheet>
      )}
    </div>
  );
}
