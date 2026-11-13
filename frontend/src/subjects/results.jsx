// Results flow (workflow → scores → broadsheet → comments → behaviour), redesigned
// mobile-first: one header, one class picker, one step bar and one save bar
// shared by every screen, so a form teacher moves along the flow without
// re-picking the class and never hunts for the Save button.
import React, { useState, useEffect, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { submitJson } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useNav, navParams } from '../lib/section';
import { confirm } from '../components/ui';
import { canWrite } from '../lib/perms';

// ── helpers ────────────────────────────────────────────────────────────────
export function useMedia(query) {
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
export const usePhone = () => useMedia('(max-width: 759px)');

export function fmtNum(v) {
  if (v == null || v === '') return v;
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
export const initials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const ordinal = (n) => { const s = ['th', 'st', 'nd', 'rd']; const v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
// Score tone relative to the school's pass mark.
export const tone = (v, pm = 50) => (v == null ? '' : v < pm ? 'bad' : v >= 70 ? 'good' : 'mid');

// Recently-used classes (shared with the other results screens).
const RECENT_KEY = 'results:recentClasses';
function readRecent() {
  try { const a = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); return Array.isArray(a) ? a : []; } catch (e) { return []; }
}
function pushRecent(termId, asgId, label) {
  if (!asgId || !label) return;
  try {
    const list = readRecent().filter((r) => String(r.id) !== String(asgId));
    list.unshift({ id: String(asgId), term: String(termId || ''), label });
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 6)));
  } catch (e) { /* storage unavailable */ }
}

// Warn before leaving the page with unsaved edits.
function useUnsavedGuard(dirty) {
  useEffect(() => {
    if (!dirty) return undefined;
    const h = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [dirty]);
}

// ── kit ────────────────────────────────────────────────────────────────────
export function Sheet({ title, onClose, children }) {
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', esc);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', esc); document.body.style.overflow = prev; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return createPortal(
    <div className="rs-sheet-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="rs-sheet" role="dialog" aria-modal="true" aria-label={title}>
        <div className="rs-grip" aria-hidden="true" />
        <div className="rs-sheet-h"><strong>{title}</strong>
          <button type="button" className="rs-x" onClick={onClose} aria-label="Close"><i className="fas fa-xmark" aria-hidden="true" /></button></div>
        {children}
      </div>
    </div>, document.body);
}

// Overflow actions: a dropdown on laptops, a bottom sheet on phones.
// items: [{icon,label,href,native,target,download,onClick,danger}] (falsy skipped)
export function Menu({ items, label = 'More' }) {
  const phone = usePhone();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const list = items.filter(Boolean);
  useEffect(() => {
    if (!open || phone) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open, phone]);
  if (!list.length) return null;
  const body = (
    <div className="rs-menu-list" role="menu">
      {list.map((it, i) => (it.heading
        ? <div key={i} className="rs-menu-hd">{it.heading}</div>
        : it.href
          ? <a key={i} role="menuitem" href={it.href} data-native={it.native ? '' : undefined} target={it.target} download={it.download ? '' : undefined}
               rel={it.target ? 'noopener' : undefined} className={it.danger ? 'danger' : ''} onClick={() => setOpen(false)}>
              <i className={'fas ' + it.icon} aria-hidden="true" /><span>{it.label}</span></a>
          : <button key={i} type="button" role="menuitem" className={it.danger ? 'danger' : ''} onClick={() => { setOpen(false); it.onClick(); }}>
              <i className={'fas ' + it.icon} aria-hidden="true" /><span>{it.label}</span></button>))}
    </div>
  );
  return (
    <div className="rs-menu" ref={ref}>
      <button type="button" className="rs-btn ghost" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <i className="fas fa-ellipsis" aria-hidden="true" /><span className="rs-hide-sm">{label}</span></button>
      {open && (phone ? <Sheet title={label} onClose={() => setOpen(false)}>{body}</Sheet> : <div className="rs-menu-pop">{body}</div>)}
    </div>
  );
}

export function Head({ icon, title, sub, children }) {
  return (
    <header className="rs-head">
      <span className="rs-head-ic"><i className={'fas ' + icon} aria-hidden="true" /></span>
      <div className="rs-head-t"><h1>{title}</h1>{sub && <p>{sub}</p>}</div>
      {children && <div className="rs-head-a">{children}</div>}
    </header>
  );
}

// Term + class picker with one-tap recent classes. `extra` renders more
// pickers (subject, assessment) inside the same card.
export function Picker({ d, go, extra, termBlank }) {
  const label = d.selected_label || (d.assignments.find((a) => String(a.id) === String(d.assignment_id)) || {}).display_name;
  useEffect(() => { if (d.assignment_id && label) pushRecent(d.term_id, d.assignment_id, label); }, [d.assignment_id, label]); // eslint-disable-line
  const recent = readRecent().filter((r) => String(r.id) !== String(d.assignment_id || ''));
  return (
    <section className="rs-pick">
      <div className="rs-pick-row">
        <label className="rs-sel"><span>Term</span>
          <select value={d.term_id} onChange={(e) => go({ term_id: e.target.value, assignment_id: '' })}>
            {termBlank && <option value="">Select term</option>}
            {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
        <label className="rs-sel grow"><span>Class</span>
          <select value={d.assignment_id} onChange={(e) => go({ assignment_id: e.target.value })}>
            <option value="">Choose a class…</option>
            {d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}</select></label>
      </div>
      {recent.length > 0 && (
        <div className="rs-recent"><span><i className="fas fa-clock-rotate-left" aria-hidden="true" /> Recent</span>
          {recent.map((r) => <button type="button" key={r.id} className="rs-chip" onClick={() => go({ term_id: r.term || d.term_id, assignment_id: r.id })}>{r.label}</button>)}
        </div>
      )}
      {extra}
    </section>
  );
}

const FLOW = [
  { key: 'workflow', label: 'Overview', icon: 'fa-list-check' },
  { key: 'scores', label: 'Scores', icon: 'fa-pen-to-square' },
  { key: 'broadsheet', label: 'Broadsheet', icon: 'fa-table' },
  { key: 'comments', label: 'Comments', icon: 'fa-comment-dots' },
  { key: 'affective', label: 'Behaviour', icon: 'fa-star-half-stroke' },
];
// The step bar shared by every results screen.
export function Flow({ d, current }) {
  const f = (d.nav && d.nav.flow) || {};
  return (
    <nav className="rs-flow" aria-label="Results steps">
      {FLOW.map((s, i) => (
        <a key={s.key} href={f[s.key] || '#'} className={s.key === current ? 'on' : ''} aria-current={s.key === current ? 'page' : undefined}>
          <b>{i + 1}</b><i className={'fas ' + s.icon} aria-hidden="true" /><span>{s.label}</span></a>
      ))}
    </nav>
  );
}

// Save bar: sticky under the content on laptops, fixed at the bottom on phones.
export function Bar({ children }) {
  const phone = usePhone();
  const anchor = useRef(null);
  // On phones the bar is portalled to <body> so it can stay fixed — which
  // takes its buttons out of the <form>, and a type="submit" button outside a
  // form does nothing. Re-route those clicks to the form the bar belongs to
  // (requestSubmit keeps native validation and the form's onSubmit handler).
  const onClickCapture = (e) => {
    const b = e.target.closest && e.target.closest('button');
    if (!b || b.disabled || b.form || (b.getAttribute('type') || 'submit') !== 'submit') return;
    const form = anchor.current && anchor.current.closest('form');
    if (!form) return;
    e.preventDefault();
    if (form.requestSubmit) form.requestSubmit(); else form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  };
  if (!phone) return <div className="rs-bar">{children}</div>;
  return <>
    <span ref={anchor} hidden />
    {createPortal(<div className="rs-bar fixed" onClickCapture={onClickCapture}>{children}</div>, document.body)}
  </>;
}

export function Tiles({ items }) {
  return (
    <div className="rs-tiles">
      {items.filter(Boolean).map((t, i) => (
        <div key={i} className={'rs-tile' + (t.tone ? ' ' + t.tone : '')}>
          <span className="l">{t.label}</span>
          <span className="v">{t.value}{t.unit && <small>{t.unit}</small>}</span>
          {t.sub && <span className="s">{t.sub}</span>}
        </div>
      ))}
    </div>
  );
}

export function Seg({ options, value, onChange, label }) {
  return (
    <div className="rs-seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} className={o.value === value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.icon && <i className={'fas ' + o.icon} aria-hidden="true" />}<span>{o.label}</span>
          {o.count != null && <em>{o.count}</em>}
        </button>
      ))}
    </div>
  );
}

export function Chips({ items, value, onChange, label }) {
  return (
    <div className="rs-chips" role="radiogroup" aria-label={label}>
      {items.map((it) => (
        <button key={it.value} type="button" role="radio" aria-checked={String(it.value) === String(value)}
                className={'rs-chip' + (String(it.value) === String(value) ? ' on' : '')} onClick={() => onChange(it.value)}>
          {it.label}{it.sub != null && <small>{it.sub}</small>}
        </button>
      ))}
    </div>
  );
}

export function Ring({ value, size = 104, label }) {
  const p = Math.max(0, Math.min(100, Math.round(value || 0)));
  const c = p >= 100 ? 'var(--success)' : p >= 50 ? 'var(--primary)' : 'var(--warning)';
  return (
    <div className="rs-ring" style={{ '--p': p, '--c': c, width: size, height: size }} role="img" aria-label={`${label || 'Done'} ${p}%`}>
      <div><b>{p}%</b>{label && <small>{label}</small>}</div>
    </div>
  );
}

export function Meter({ value, max, tone: t }) {
  const p = max ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return <span className={'rs-meter ' + (t || (p >= 100 ? 'good' : p >= 50 ? 'mid' : 'bad'))}><i style={{ width: p + '%' }} /></span>;
}

export function Blank({ icon, title, children }) {
  return (
    <div className="rs-blank"><span><i className={'fas ' + icon} aria-hidden="true" /></span>
      <h3>{title}</h3>{children}</div>
  );
}

export function Avatar({ name, gender }) {
  return <span className={'rs-av ' + (gender === 'Male' ? 'm' : gender === 'Female' ? 'f' : '')} aria-hidden="true">{initials(name)}</span>;
}

export const subLine = (d) => {
  const term = (d.terms.find((t) => String(t.id) === String(d.term_id)) || {}).full_name || d.term_label || '';
  const cls = d.selected_label || (d.assignments.find((a) => String(a.id) === String(d.assignment_id)) || {}).display_name;
  return cls ? `${cls} · ${term}` : term;
};

// ── 1. Overview (workflow) ─────────────────────────────────────────────────
export function Workflow({ d, notify }) {
  const nav = useNav();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, ...extra });
  const s = d.steps;
  const [busy, setBusy] = useState(false);
  const [showDone, setShowDone] = useState(false);
  const compute = async () => {
    setBusy(true);
    const r = await submitJson(d.urls.compute, { term_id: d.term_id, assignment_id: d.assignment_id });
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not compute.');
  };
  const steps = s ? [
    { key: 'subjects', icon: 'fa-book', title: 'Subjects set up', done: s.subjects > 0 ? 1 : 0, total: 1,
      text: s.subjects ? `${s.subjects} subjects on this class` : 'No subjects assigned to this class yet', todo: 'Add subjects to this class', href: d.urls.class_subjects, action: 'Manage', native: true },
    { key: 'students', icon: 'fa-users', title: 'Students enrolled', done: s.students > 0 ? 1 : 0, total: 1,
      text: s.students ? `${s.students} students in this class` : 'No students enrolled yet', todo: 'Enrol students into this class', href: d.urls.enrol, action: 'Enrol', native: true },
    { key: 'scores', icon: 'fa-pen-to-square', title: 'Scores entered', done: s.scores_entered, total: s.scores_expected,
      text: `${s.scores_entered} of ${s.scores_expected} score boxes filled`, todo: `${Math.max(0, s.scores_expected - s.scores_entered)} scores still to enter`, href: d.urls.scores || d.urls.bulk_entry, action: 'Enter scores' },
    { key: 'positions', icon: 'fa-ranking-star', title: 'Results & positions', done: s.positions, total: s.students,
      text: `${s.positions} of ${s.students} students ranked`, todo: 'Work out results and class positions', href: d.urls.broadsheet, action: 'Broadsheet' },
    { key: 'comments', icon: 'fa-comment-dots', title: 'Report comments', done: s.comments, total: s.students,
      text: `${s.comments} of ${s.students} have a form-teacher comment`, todo: `${Math.max(0, s.students - s.comments)} report comments to write`, href: d.urls.comments, action: 'Write' },
    { key: 'behaviour', icon: 'fa-star-half-stroke', title: 'Behaviour ratings', done: s.behaviour, total: s.students,
      text: `${s.behaviour} of ${s.students} rated`, todo: `${Math.max(0, s.students - s.behaviour)} students to rate for behaviour`, href: d.urls.affective, action: 'Rate' },
  ] : [];
  const frac = (st) => (st.total ? Math.min(1, st.done / st.total) : 0);
  const overall = steps.length ? (steps.reduce((a, st) => a + frac(st), 0) / steps.length) * 100 : 0;
  const doneCount = steps.filter((st) => frac(st) >= 1).length;
  const next = steps.find((st) => frac(st) < 1);
  const sp = (s && s.subjects_progress) || [];
  const behind = sp.filter((x) => x.entered < x.expected);
  const complete = sp.length - behind.length;
  const scoresPct = s ? pct(s.scores_entered, s.scores_expected) : 0;

  return (
    <div className="rs">
      <Head icon="fa-list-check" title="Results" sub={s ? subLine(d) : 'Pick a class to see where its results stand'} />
      <Picker d={d} go={go} />
      <Flow d={d} current="workflow" />
      {!s ? (
        <Blank icon="fa-hand-pointer" title="Choose a class"><p>Pick a term and class above to see its results checklist, which subjects are still missing scores, and to release results.</p></Blank>
      ) : (
        <div className="rs-split">
          <div className="rs-main">
            <section className="rs-card rs-hero">
              <Ring value={overall} label="ready" />
              <div className="rs-hero-t">
                <h2>{doneCount === steps.length ? 'Ready to print and release' : `${doneCount} of ${steps.length} steps done`}</h2>
                {next ? (
                  <p><span className="rs-next-k">Next step</span> {next.todo}.</p>
                ) : <p>Every step is complete for {d.selected_label}.</p>}
                {next && next.href && <a className="rs-btn primary" href={next.href} data-native={next.native ? '' : undefined}>{next.action} <i className="fas fa-arrow-right" aria-hidden="true" /></a>}
              </div>
            </section>

            <section className="rs-card flush">
              {steps.map((st, i) => {
                const ok = frac(st) >= 1;
                return (
                  <div key={st.key} className={'rs-step' + (ok ? ' ok' : '') + (next && next.key === st.key ? ' next' : '')}>
                    <span className="rs-step-ic"><i className={'fas ' + (ok ? 'fa-check' : st.icon)} aria-hidden="true" /></span>
                    <div className="rs-step-t">
                      <strong><em>{i + 1}</em> {st.title}</strong>
                      <small>{st.text}</small>
                      {st.total > 1 && <Meter value={st.done} max={st.total} />}
                    </div>
                    <a className={'rs-btn sm ' + (next && next.key === st.key ? 'primary' : 'ghost')} href={st.href} data-native={st.native ? '' : undefined}>{st.action}</a>
                  </div>
                );
              })}
            </section>

            {sp.length > 0 && (
              <section className="rs-card">
                <header className="rs-card-h"><h3><i className="fas fa-hourglass-half" aria-hidden="true" /> Scores by subject</h3>
                  <small>{behind.length ? `${behind.length} subject${behind.length === 1 ? '' : 's'} still missing scores` : 'All subjects complete'}</small></header>
                {behind.length === 0 && <p className="rs-ok-line"><i className="fas fa-circle-check" aria-hidden="true" /> Every subject has all its scores in.</p>}
                <div className="rs-subj">
                  {(showDone ? sp : behind).map((x) => {
                    const p = pct(x.entered, x.expected);
                    return (
                      <a key={x.id} href={x.url} className="rs-subj-row">
                        <span className="n"><b>{x.name}</b><small>{x.teacher || 'No teacher assigned'}</small></span>
                        <Meter value={x.entered} max={x.expected} />
                        <span className={'p ' + (p >= 100 ? 'good' : p >= 50 ? 'mid' : 'bad')}>{p}%</span>
                        <i className="fas fa-chevron-right" aria-hidden="true" />
                      </a>
                    );
                  })}
                </div>
                {complete > 0 && behind.length > 0 && (
                  <button type="button" className="rs-link" onClick={() => setShowDone((v) => !v)}>
                    {showDone ? 'Hide complete subjects' : `Show ${complete} complete subject${complete === 1 ? '' : 's'}`}</button>
                )}
              </section>
            )}
          </div>

          <aside className="rs-rail">
            <section className="rs-card">
              <header className="rs-card-h"><h3><i className="fas fa-flag-checkered" aria-hidden="true" /> Finish up</h3></header>
              {scoresPct < 100 && (
                <p className="rs-warn"><i className="fas fa-triangle-exclamation" aria-hidden="true" /> {100 - scoresPct}% of scores are still missing. Positions worked out now will change as scores come in.</p>
              )}
              <div className="rs-fin">
                {canWrite(d, 'scores_tools') && (
                  <button type="button" className="rs-btn primary wide" onClick={compute} disabled={busy}>
                    <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-ranking-star')} aria-hidden="true" /> Work out results &amp; positions</button>
                )}
                {canWrite(d, 'reportcard_batch') && canWrite(d, 'cards') && (
                  <a href={d.urls.print_all} className="rs-btn ghost wide" data-native><i className="fas fa-print" aria-hidden="true" /> Print all report cards</a>
                )}
              </div>
            </section>
            {canWrite(d, 'cards') && d.urls.publish && (
              <section className={'rs-card rs-release' + (d.published ? ' on' : '')}>
                <div className="rs-release-h">
                  <span className="rs-release-ic"><i className={'fas ' + (d.published ? 'fa-eye' : 'fa-eye-slash')} aria-hidden="true" /></span>
                  <div><strong>{d.published ? 'Released' : 'Not released'}</strong>
                    <small>{d.published ? 'Parents and the result checker can see this term’s results.' : 'Parents can’t see this term’s results yet.'}</small></div>
                </div>
                <form method="POST" action={d.urls.publish}>
                  <input type="hidden" name="_csrf_token" value={csrfToken()} />
                  <input type="hidden" name="next" value={d.self_url + '?term_id=' + d.term_id + '&assignment_id=' + d.assignment_id} />
                  {!d.published && <label className="rs-check"><input type="checkbox" name="notify" /> Notify parents</label>}
                  <button type="submit" className={'rs-btn wide ' + (d.published ? 'danger' : 'success')}>{d.published ? 'Hide results' : 'Release results'}</button>
                </form>
                <small className="rs-note">Applies to every class for this term.</small>
              </section>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

// ── 2a. Score entry ────────────────────────────────────────────────────────
function StudentEntry({ d, notify }) {
  const phone = usePhone();
  const roster = d.roster || [];
  const [q, setQ] = useState('');
  const [studentId, setStudentId] = useState('');
  const [rows, setRows] = useState(null);
  const [vals, setVals] = useState({});
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? roster.filter((s) => s.full_name.toLowerCase().includes(t)) : roster;
  }, [q, roster]);
  const load = React.useCallback(async (sid) => {
    if (!sid || !d.class_subject_id) { setRows(null); return; }
    setLoading(true);
    try {
      const p = new URLSearchParams({ term_id: d.term_id || '', assignment_id: d.assignment_id || '', class_subject_id: d.class_subject_id || '', student_id: sid });
      const res = await fetch(`${d.student_scores_api}?${p.toString()}`, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      const body = await res.json();
      if (!res.ok) { notify('error', body.error || 'Could not load scores.'); setRows(null); }
      else { setRows(body.rows); const m = {}; body.rows.forEach((r) => { m[r.assessment_type_id] = r.score === '' ? '' : String(r.score); }); setVals(m); }
    } catch (e) { notify('error', 'Network error loading scores.'); setRows(null); }
    finally { setLoading(false); }
  }, [d.term_id, d.assignment_id, d.class_subject_id, d.student_scores_api, notify]);
  const pick = (sid) => { setStudentId(String(sid)); load(sid); };
  useEffect(() => { if (studentId) load(studentId); }, [d.class_subject_id]); // eslint-disable-line
  const idx = roster.findIndex((s) => String(s.id) === String(studentId));
  const save = async (advance) => {
    if (!studentId || !rows) return;
    setBusy(true);
    const r = await submitJson(d.save_student_url, { term_id: d.term_id, assignment_id: d.assignment_id, class_subject_id: d.class_subject_id,
      student_id: studentId, 'assessment_type_id[]': rows.map((x) => x.assessment_type_id), 'score[]': rows.map((x) => vals[x.assessment_type_id] ?? '') });
    setBusy(false);
    if (r.ok) {
      notify('success', r.message);
      if (advance && idx >= 0 && idx < roster.length - 1) pick(roster[idx + 1].id); else load(studentId);
    } else notify('error', r.error || 'Could not save.');
  };
  if (!d.assignment_id || !d.class_subject_id) {
    return <Blank icon="fa-hand-pointer" title="Pick a subject"><p>Choose a class and subject above, then a student, to enter all their scores for that subject at once.</p></Blank>;
  }
  const picked = roster[idx];
  const invalid = (r) => { const raw = vals[r.assessment_type_id]; if (raw === '' || raw == null) return false; const n = Number(raw); return !Number.isFinite(n) || n < 0 || n > r.max_score; };
  const total = rows ? rows.reduce((a, r) => a + (Number(vals[r.assessment_type_id]) || 0), 0) : 0;
  const maxTotal = rows ? rows.reduce((a, r) => a + (Number(r.max_score) || 0), 0) : 0;
  return (
    <div className="rs-two">
      {!(phone && picked) && (
        <section className="rs-card rs-roster">
          <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
            <input type="search" placeholder="Find a student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student" /></label>
          <div className="rs-roster-list">
            {filtered.map((s) => (
              <button type="button" key={s.id} onClick={() => pick(s.id)} className={String(s.id) === String(studentId) ? 'on' : ''}>
                <Avatar name={s.full_name} gender={s.gender} /><span>{s.full_name}</span><i className="fas fa-chevron-right" aria-hidden="true" /></button>
            ))}
            {!filtered.length && <p className="rs-muted">No students match.</p>}
          </div>
        </section>
      )}
      {(picked || !phone) && (
        <section className="rs-card">
          {!picked ? <Blank icon="fa-user" title="Pick a student"><p>Choose a student to enter their {d.selected_subject || 'subject'} scores.</p></Blank> : (
            <>
              <header className="rs-stu-h">
                {phone && <button type="button" className="rs-icon-btn" onClick={() => setStudentId('')} aria-label="Back to students"><i className="fas fa-arrow-left" aria-hidden="true" /></button>}
                <Avatar name={picked.full_name} gender={picked.gender} />
                <div><strong>{picked.full_name}</strong><small>{d.selected_subject} · student {idx + 1} of {roster.length}</small></div>
              </header>
              {loading ? <p className="rs-muted"><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Loading…</p> : rows && rows.length ? (
                <form onSubmit={(e) => { e.preventDefault(); save(true); }}>
                  <div className="rs-assess">
                    {rows.map((r) => (
                      <label key={r.assessment_type_id} className={'rs-assess-row' + (invalid(r) ? ' bad' : '')}>
                        <span><b>{r.name}</b><small>out of {r.max_score}</small></span>
                        <input type="number" inputMode="decimal" min="0" max={r.max_score} step="0.5" value={vals[r.assessment_type_id] ?? ''}
                               onChange={(e) => setVals((m) => ({ ...m, [r.assessment_type_id]: e.target.value }))} />
                      </label>
                    ))}
                    <div className="rs-assess-total"><span>Total</span><b>{fmtNum(total)}<small> / {maxTotal}</small></b></div>
                  </div>
                  {canWrite(d, 'scores_enter') && (
                    <Bar>
                      <span className="rs-bar-t"><b>{picked.full_name}</b><small>{d.selected_subject}</small></span>
                      <button type="button" className="rs-btn ghost" disabled={busy} onClick={() => save(false)}><i className="fas fa-floppy-disk" aria-hidden="true" /><span className="rs-hide-sm">Save</span></button>
                      <button type="submit" className="rs-btn primary" disabled={busy}>{idx < roster.length - 1 ? <>Save &amp; next <i className="fas fa-arrow-right" aria-hidden="true" /></> : 'Save'}</button>
                    </Bar>
                  )}
                </form>
              ) : <Blank icon="fa-list" title="No assessments"><p>No assessment types are set up.</p></Blank>}
            </>
          )}
        </section>
      )}
    </div>
  );
}

export function Scores({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [mode, setMode] = useState('assessment');
  const base = () => { const m = {}; d.students_data.forEach((s) => { m[s.id] = s.score === '' ? '' : String(s.score); }); return m; };
  const [scores, setScores] = useState(base);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState({});
  const [fillValue, setFillValue] = useState('');
  const [fillOpen, setFillOpen] = useState(false);
  const baseline = useRef({});
  useEffect(() => { const m = base(); setScores(m); setSelected({}); baseline.current = { ...m }; }, [d.students_data]); // eslint-disable-line
  const isInvalid = (raw) => { if (raw === '' || raw == null) return false; const n = Number(raw); return !Number.isFinite(n) || n < 0 || n > d.max_score; };
  const stats = useMemo(() => {
    let entered = 0, invalid = 0;
    d.students_data.forEach((s) => { const raw = scores[s.id]; if (raw === '' || raw == null) return; entered += 1; if (isInvalid(raw)) invalid += 1; });
    return { entered, invalid, missing: d.students_data.length - entered, total: d.students_data.length };
  }, [scores, d.students_data, d.max_score]); // eslint-disable-line
  const changed = useMemo(() => d.students_data.filter((s) => String(scores[s.id] ?? '') !== String(baseline.current[s.id] ?? '')).length, [scores, d.students_data]);
  useUnsavedGuard(changed > 0);
  const onPaste = (startIndex) => (e) => {
    const text = (e.clipboardData && e.clipboardData.getData('text')) || '';
    if (!/[\n\t]/.test(text)) return;
    e.preventDefault();
    const values = text.replace(/\r/g, '').split('\n').map((line) => line.split('\t')[0].trim());
    if (values.length && values[values.length - 1] === '') values.pop();
    setScores((m) => { const n = { ...m }; values.forEach((v, k) => { const st = d.students_data[startIndex + k]; if (st) n[st.id] = v; }); return n; });
    notify('success', `Pasted ${Math.min(values.length, d.students_data.length - startIndex)} score(s).`);
  };
  const selectedIds = d.students_data.filter((s) => selected[s.id]).map((s) => s.id);
  const allSelected = d.students_data.length > 0 && d.students_data.every((s) => selected[s.id]);
  const toggleAll = (on) => { const m = {}; if (on) d.students_data.forEach((s) => { m[s.id] = true; }); setSelected(m); };
  const applyFill = () => { if (!selectedIds.length) return; setScores((m) => { const n = { ...m }; selectedIds.forEach((id) => { n[id] = fillValue; }); return n; }); };
  const set = (params) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, class_subject_id: d.class_subject_id, assessment_type_id: d.assessment_type_id, ...params });
  // Resume the last class on a fresh visit.
  useEffect(() => {
    try {
      if (d.assignment_id) { localStorage.setItem('scores:last', JSON.stringify({ term_id: d.term_id, assignment_id: String(d.assignment_id) })); return; }
      const last = JSON.parse(localStorage.getItem('scores:last') || 'null');
      if (last && last.assignment_id && (d.assignments || []).some((a) => String(a.id) === String(last.assignment_id))) set({ term_id: last.term_id || d.term_id, assignment_id: last.assignment_id });
    } catch (e) { /* storage unavailable */ }
  }, [d.assignment_id]); // eslint-disable-line
  const onScoreKey = (e) => {
    if (e.key !== 'Enter' && e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const inputs = Array.prototype.slice.call(e.currentTarget.closest('.rs-rows').querySelectorAll('input.score-input'));
    const i = inputs.indexOf(e.currentTarget);
    const nx = e.key === 'ArrowUp' ? inputs[i - 1] : inputs[i + 1];
    if (nx) { nx.focus(); nx.select(); }
  };
  const subjList = d.class_subjects || [];
  const curIdx = subjList.findIndex((cs) => String(cs.id) === String(d.class_subject_id));
  const nextSubject = (curIdx >= 0 && curIdx < subjList.length - 1) ? subjList[curIdx + 1] : null;
  const save = async (e, advance) => {
    if (e) e.preventDefault();
    if (stats.invalid && !await confirm(`${stats.invalid} score(s) are outside 0–${d.max_score} and will be skipped. Save the rest?`)) return;
    setBusy(true);
    const r = await submitJson(d.save_url, { term_id: d.term_id, assignment_id: d.assignment_id, class_subject_id: d.class_subject_id, assessment_type_id: d.assessment_type_id,
      'student_id[]': d.students_data.map((s) => s.id), 'score[]': d.students_data.map((s) => scores[s.id] ?? '') });
    setBusy(false);
    if (r.ok) { notify('success', r.message); if (advance && nextSubject) set({ class_subject_id: nextSubject.id }); else nav.refresh(); }
    else notify('error', r.error || 'Could not save.');
  };
  const u = d.urls || {};
  const tools = canWrite(d, 'scores_bulk_import');
  const menu = [
    d.assignment_id && { icon: 'fa-table-cells', label: 'Whole-class grid (all subjects)', href: d.nav && d.nav.flow && d.nav.flow.bulk_entry },
    tools && u.subject_sheet_import && { icon: 'fa-file-import', label: 'Import subject sheet', href: u.subject_sheet_import, native: true },
    tools && u.broadsheet_import && { icon: 'fa-table', label: 'Import broadsheet', href: u.broadsheet_import, native: true },
    tools && u.scan && { icon: 'fa-camera', label: 'Scan a photo of a score sheet', href: u.scan, native: true },
    canWrite(d, 'scores_tools') && u.blank_sheet && { icon: 'fa-file-lines', label: 'Print blank score sheet', href: u.blank_sheet, native: true, target: '_blank' },
  ];
  const selectors = d.assignment_id ? (
    <div className="rs-pick-more">
      <div className="rs-pick-l"><span>Subject</span>
        {subjList.length ? <Chips label="Subject" value={d.class_subject_id} onChange={(v) => set({ class_subject_id: v })}
              items={subjList.map((cs) => ({ value: cs.id, label: cs.subject_name }))} />
          : <span className="rs-muted">No subjects you can enter for this class.</span>}</div>
      {mode === 'assessment' && (
        <div className="rs-pick-l"><span>Assessment</span>
          <Chips label="Assessment" value={d.assessment_type_id} onChange={(v) => set({ assessment_type_id: v })}
                 items={d.assessment_types.map((at) => ({ value: at.id, label: at.name, sub: at.max_score }))} /></div>
      )}
    </div>
  ) : null;

  return (
    <div className={'rs' + (phone ? ' has-bar' : '')}>
      <Head icon="fa-pen-to-square" title="Score entry" sub={subLine(d) || 'Enter CA and exam scores'}><Menu items={menu} label="Tools" /></Head>
      <Picker d={d} go={(p) => set({ class_subject_id: '', assessment_type_id: '', ...p })} termBlank extra={selectors} />
      <Flow d={d} current="scores" />
      {d.assignment_id && (
        <Seg label="Entry mode" value={mode} onChange={setMode} options={[
          { value: 'assessment', label: phone ? 'Whole class' : 'Whole class · one assessment', icon: 'fa-users' },
          { value: 'student', label: phone ? 'One student' : 'One student · every assessment', icon: 'fa-user-graduate' }]} />
      )}
      {mode === 'student' ? <StudentEntry d={d} notify={notify} /> : d.students_data.length ? (
        <form onSubmit={(e) => save(e, false)} className="rs-card flush">
          <header className="rs-entry-h">
            <div><strong>{d.selected_subject}</strong><small>{d.selected_assessment} · out of {d.max_score}</small></div>
            <div className="rs-entry-stats">
              <span className="good"><b>{stats.entered}</b> entered</span>
              <span className={stats.missing ? 'mid' : ''}><b>{stats.missing}</b> missing</span>
              {stats.invalid > 0 && <span className="bad"><b>{stats.invalid}</b> out of range</span>}
            </div>
            <Meter value={stats.entered} max={stats.total} />
          </header>
          <div className="rs-fillbar">
            <label className="rs-check"><input type="checkbox" checked={allSelected} onChange={(e) => toggleAll(e.target.checked)} /> Select all</label>
            {selectedIds.length > 0 || fillOpen ? (
              <span className="rs-fill">
                <span>Give {selectedIds.length || 'selected'} the score</span>
                <input type="number" inputMode="decimal" min="0" max={d.max_score} step="0.5" value={fillValue} placeholder="e.g. 5" aria-label="Score for selected students"
                       onChange={(e) => setFillValue(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applyFill(); } }} />
                <button type="button" className="rs-btn sm primary" onClick={applyFill} disabled={!selectedIds.length}>Apply</button>
                {selectedIds.length > 0 && <button type="button" className="rs-link" onClick={() => setSelected({})}>Clear</button>}
              </span>
            ) : (
              <button type="button" className="rs-link" onClick={() => setFillOpen(true)}><i className="fas fa-fill-drip" aria-hidden="true" /> Give several students the same score</button>
            )}
            <span className="rs-hint rs-hide-sm"><kbd>Enter</kbd> next · paste a column from Excel</span>
          </div>
          <div className="rs-rows">
            {d.students_data.map((s, i) => {
              const bad = isInvalid(scores[s.id]);
              const dirty = String(scores[s.id] ?? '') !== String(baseline.current[s.id] ?? '');
              return (
                <div key={s.id} className={'rs-row' + (selected[s.id] ? ' sel' : '') + (bad ? ' bad' : '')}>
                  <input type="checkbox" checked={!!selected[s.id]} aria-label={'Select ' + s.full_name} onChange={(e) => setSelected((m) => ({ ...m, [s.id]: e.target.checked }))} />
                  <span className="rs-row-n">{i + 1}</span>
                  <Avatar name={s.full_name} gender={s.gender} />
                  <span className="rs-row-name">{s.full_name}{dirty && <i className="rs-dirty" title="Not saved yet" />}</span>
                  <input type="number" inputMode="decimal" className="score-input" min="0" max={d.max_score} step="0.5" aria-label={'Score for ' + s.full_name}
                         aria-invalid={bad ? 'true' : undefined} value={scores[s.id] ?? ''} placeholder="–"
                         onKeyDown={onScoreKey} onPaste={onPaste(i)} onFocus={(e) => e.target.select()}
                         onChange={(e) => setScores((m) => ({ ...m, [s.id]: e.target.value }))} />
                </div>
              );
            })}
          </div>
          {canWrite(d, 'scores_enter') && (
            <Bar>
              <span className="rs-bar-t"><b>{changed ? `${changed} unsaved` : 'All saved'}</b><small>{stats.entered}/{stats.total} entered</small></span>
              <button type="submit" className={'rs-btn ' + (nextSubject ? 'ghost' : 'primary')} disabled={busy}><i className="fas fa-floppy-disk" aria-hidden="true" /><span className={nextSubject ? 'rs-hide-sm' : ''}>Save</span></button>
              {nextSubject && <button type="button" className="rs-btn primary" disabled={busy} onClick={() => save(null, true)} title={`Save and go to ${nextSubject.subject_name}`}>
                <span>Save &amp; next<span className="rs-hide-sm">: {nextSubject.subject_name}</span></span> <i className="fas fa-arrow-right" aria-hidden="true" /></button>}
            </Bar>
          )}
        </form>
      ) : d.has_selection ? (
        <Blank icon="fa-users" title="No students"><p>No students are enrolled in this class.</p></Blank>
      ) : (
        <Blank icon="fa-hand-pointer" title={!d.assignment_id ? 'Choose a class' : !d.class_subject_id ? 'Choose a subject' : 'Choose an assessment'}>
          <p>{!d.assignment_id ? 'Pick a term and class above to start entering scores.' : !d.class_subject_id ? 'Tap the subject you want to enter.' : `Tap the assessment (e.g. ${(d.assessment_types[0] || {}).name || 'CA 1'}) you’re entering for ${d.selected_subject}.`}</p></Blank>
      )}
    </div>
  );
}

// ── 2b. Whole-class grid (bulk entry) ──────────────────────────────────────
export function BulkEntry({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, ...extra });
  const [cells, setCells] = useState(d.scores);
  const [busy, setBusy] = useState(false);
  const [only, setOnly] = useState('');
  useEffect(() => setCells(d.scores), [d.scores]);
  useEffect(() => { if (phone && !only && d.class_subjects.length) setOnly(String(d.class_subjects[0].id)); }, [phone, d.class_subjects]); // eslint-disable-line
  const key = (sid, csid, atid) => `${sid}_${csid}_${atid}`;
  const changed = useMemo(() => Object.keys({ ...d.scores, ...cells }).filter((k) => String(cells[k] ?? '') !== String(d.scores[k] ?? '')).length, [cells, d.scores]);
  useUnsavedGuard(changed > 0);
  const atMax = (at) => Number(at.max_score) || 100;
  const bad = (v, at) => v !== '' && v != null && (Number(v) < 0 || Number(v) > atMax(at) || !Number.isFinite(Number(v)));
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id };
    d.students.forEach((st) => d.class_subjects.forEach((cs) => d.assessment_types.forEach((at) => {
      fields['s_' + key(st.id, cs.id, at.id)] = cells[key(st.id, cs.id, at.id)] ?? '';
    })));
    const r = await submitJson(d.submit_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const shown = only ? d.class_subjects.filter((cs) => String(cs.id) === String(only)) : d.class_subjects;
  const filled = (cs) => d.students.reduce((a, st) => a + d.assessment_types.filter((at) => (cells[key(st.id, cs.id, at.id)] ?? '') !== '').length, 0);
  const per = d.students.length * d.assessment_types.length;
  return (
    <div className={'rs' + (phone ? ' has-bar' : '')}>
      <Head icon="fa-table-cells" title="Whole-class grid" sub={subLine(d) || 'Every subject for a class on one screen'}>
        {d.assignment_id && <a href={d.nav && d.nav.flow && d.nav.flow.scores} className="rs-btn ghost"><i className="fas fa-pen" aria-hidden="true" /><span className="rs-hide-sm">One subject at a time</span></a>}
      </Head>
      <Picker d={d} go={go} />
      <Flow d={d} current="scores" />
      {d.has_grid ? (
        <form onSubmit={save}>
          <Chips label="Subjects shown" value={only} onChange={setOnly}
                 items={[...(phone ? [] : [{ value: '', label: 'All subjects' }]), ...d.class_subjects.map((cs) => ({ value: String(cs.id), label: cs.subject_name, sub: `${pct(filled(cs), per)}%` }))]} />
          <div className="rs-card flush rs-grid-wrap">
            <table className="rs-grid">
              <thead>
                <tr><th className="nm" rowSpan={2}>Student</th>
                  {shown.map((cs) => <th className="subj" colSpan={d.assessment_types.length + 1} key={cs.id}>{cs.subject_name}</th>)}</tr>
                <tr>{shown.map((cs) => [...d.assessment_types.map((at, i) => (
                  <th key={cs.id + '_' + at.id} className={i === 0 ? 'first' : ''} title={`${at.name} (out of ${at.max_score})`}>{at.short_name}<small>/{at.max_score}</small></th>)),
                  <th key={cs.id + '_t'} className="tot">Total</th>])}</tr>
              </thead>
              <tbody>{d.students.map((st) => (
                <tr key={st.id}><td className="nm">{st.full_name}</td>
                  {shown.map((cs) => {
                    let t = 0; let any = false;
                    const tds = d.assessment_types.map((at, i) => {
                      const k = key(st.id, cs.id, at.id); const v = cells[k] ?? '';
                      if (v !== '' && Number.isFinite(Number(v))) { t += Number(v); any = true; }
                      return <td key={k} className={i === 0 ? 'first' : ''}>
                        <input type="number" inputMode="decimal" step="0.5" min="0" max={at.max_score} value={v} aria-label={`${st.full_name} ${cs.subject_name} ${at.name}`}
                               className={bad(v, at) ? 'bad' : ''} onFocus={(e) => e.target.select()} onChange={(e) => setCells((m) => ({ ...m, [k]: e.target.value }))} /></td>;
                    });
                    return [...tds, <td key={cs.id + '_t'} className={'tot ' + (any ? tone(t, d.pass_mark || 50) : '')}>{any ? fmtNum(t) : '–'}</td>];
                  })}</tr>))}</tbody>
            </table>
          </div>
          {canWrite(d, 'scores_enter') && (
            <Bar>
              <span className="rs-bar-t"><b>{changed ? `${changed} unsaved change${changed === 1 ? '' : 's'}` : 'All saved'}</b><small>Blank clears a score · positions update on save</small></span>
              <button type="submit" className="rs-btn primary" disabled={busy}><i className="fas fa-floppy-disk" aria-hidden="true" /> Save all</button>
            </Bar>
          )}
        </form>
      ) : d.assignment_id ? (
        <Blank icon="fa-circle-info" title="Nothing to enter"><p>This class has no subjects you can enter, or no enrolled students yet.</p></Blank>
      ) : (
        <Blank icon="fa-hand-pointer" title="Choose a class"><p>Pick a term and class to enter every subject’s scores on one grid.</p></Blank>
      )}
    </div>
  );
}

// ── 3. Broadsheet ──────────────────────────────────────────────────────────
export function Broadsheet({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, ...extra });
  const pm = Number(d.pass_mark) || 50;
  const [field, setField] = useState('average');
  const [minScore, setMinScore] = useState('');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(null);
  const [showFilter, setShowFilter] = useState(false);
  const compute = async () => {
    if (!await confirm("Work out and save term results and class positions for this class? This updates each student's report card.")) return;
    const r = await submitJson(d.urls.compute, { term_id: d.term_id, assignment_id: d.assignment_id });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not compute.');
  };
  const minVal = parseFloat(minScore);
  const hasFilter = !Number.isNaN(minVal);
  const valueFor = (r) => (field === 'average' ? r.average : field === 'total' ? r.total : r.subjects[String(field)]);
  const term = q.trim().toLowerCase();
  const rows = d.rows.filter((r) => (!hasFilter || (valueFor(r) != null && valueFor(r) >= minVal)) && (!term || r.student.toLowerCase().includes(term)));
  const fieldLabel = field === 'average' ? 'Average' : field === 'total' ? 'Total' : (d.class_subjects.find((cs) => String(cs.id) === String(field)) || {}).name || 'Subject';
  // Class snapshot for decisions.
  const n = d.rows.length;
  const scored = d.rows.filter((r) => r.total > 0);
  const avg = scored.length ? scored.reduce((a, r) => a + r.average, 0) / scored.length : 0;
  const passing = scored.filter((r) => r.average >= pm).length;
  const top = d.rows[0];
  const subjAvg = d.class_subjects.map((cs) => {
    const v = d.rows.map((r) => r.subjects[String(cs.id)]).filter((x) => x != null);
    return { ...cs, avg: v.length ? v.reduce((a, x) => a + x, 0) / v.length : null, n: v.length };
  }).filter((x) => x.avg != null);
  const weakest = subjAvg.slice().sort((a, b) => a.avg - b.avg)[0];
  const u = d.urls || {};
  const withParams = (href) => {
    if (!href || !hasFilter) return href;
    return href + (href.includes('?') ? '&' : '?') + `min_score=${encodeURIComponent(minVal)}&filter_field=${encodeURIComponent(field)}`;
  };
  const menu = [
    canWrite(d, 'scores_tools') && { icon: 'fa-ranking-star', label: 'Work out results & positions', onClick: compute },
    { heading: hasFilter ? `Download (${rows.length} filtered)` : 'Download' },
    u.export && { icon: 'fa-file-excel', label: 'Excel', href: withParams(u.export), native: true, download: true },
    u.export_pdf && { icon: 'fa-file-pdf', label: 'PDF', href: withParams(u.export_pdf), native: true, download: true },
    u.export_word && { icon: 'fa-file-word', label: 'Word', href: withParams(u.export_word), native: true, download: true },
    u.export_image && { icon: 'fa-file-image', label: 'HD image', href: withParams(u.export_image), native: true, download: true },
    { heading: 'More' },
    canWrite(d, 'scores_tools') && u.blank_sheet && { icon: 'fa-file-lines', label: 'Print blank score sheet', href: u.blank_sheet, native: true, target: '_blank' },
    u.analytics && { icon: 'fa-chart-column', label: 'Class analytics', href: u.analytics },
    u.explore && { icon: 'fa-filter', label: 'Explore / compare classes', href: u.explore },
  ];
  const medal = (p) => (p === 1 ? 'gold' : p === 2 ? 'silver' : p === 3 ? 'bronze' : '');

  return (
    <div className="rs">
      <Head icon="fa-table" title="Broadsheet" sub={subLine(d) || 'Every subject and position for a class'}>
        {n > 0 && <Menu items={menu} label="Actions" />}
      </Head>
      <Picker d={d} go={go} termBlank />
      <Flow d={d} current="broadsheet" />
      {n ? (<>
        <Tiles items={[
          { label: 'Students', value: n, sub: `${scored.length} with scores` },
          { label: 'Class average', value: fmtNum(Math.round(avg * 10) / 10), unit: '%', tone: tone(avg, pm) },
          { label: 'Passing', value: pct(passing, scored.length), unit: '%', sub: `${passing} of ${scored.length} at ${pm}+`, tone: pct(passing, scored.length) >= 50 ? 'good' : 'bad' },
          top && top.total > 0 && { label: 'Top student', value: fmtNum(top.average), unit: '%', sub: top.student },
          weakest && { label: 'Weakest subject', value: fmtNum(Math.round(weakest.avg * 10) / 10), sub: weakest.name, tone: tone(weakest.avg, pm) },
        ]} />

        <div className="rs-toolbar">
          <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
            <input type="search" placeholder="Find a student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student" /></label>
          <button type="button" className={'rs-btn ghost' + (hasFilter ? ' on' : '')} onClick={() => setShowFilter((v) => !v)}>
            <i className="fas fa-sliders" aria-hidden="true" /><span>{hasFilter ? `${fieldLabel} ≥ ${minVal}` : 'Filter'}</span></button>
          <span className="rs-count">{rows.length === n ? `${n} students` : `${rows.length} of ${n}`}</span>
        </div>
        {(showFilter || hasFilter) && (
          <div className="rs-filter">
            <span>Show students whose</span>
            <select value={field} onChange={(e) => setField(e.target.value)} aria-label="Filter by">
              <option value="average">Average</option><option value="total">Total</option>
              {d.class_subjects.map((cs) => <option key={cs.id} value={cs.id}>{cs.name}</option>)}</select>
            <span>is at least</span>
            <input type="number" inputMode="decimal" value={minScore} min="0" step="0.1" placeholder={String(pm)} onChange={(e) => setMinScore(e.target.value)} aria-label="Minimum score" />
            {hasFilter && <button type="button" className="rs-link" onClick={() => setMinScore('')}>Clear</button>}
          </div>
        )}

        {phone ? (
          <div className="rs-bs-cards">
            {rows.map((r) => (
              <div key={r.student_id} className={'rs-bs-card' + (open === r.student_id ? ' open' : '')}>
                <button type="button" className="rs-bs-top" onClick={() => setOpen(open === r.student_id ? null : r.student_id)} aria-expanded={open === r.student_id}>
                  <span className={'rs-pos ' + medal(r.position)}>{r.position}</span>
                  <span className="rs-bs-n"><b>{r.student}</b><small>Total {fmtNum(r.total)} · {r.passed} passed{r.failed ? ` · ${r.failed} failed` : ''}</small></span>
                  <span className={'rs-bs-avg ' + tone(r.average, pm)}>{fmtNum(r.average)}</span>
                  <i className="fas fa-chevron-down" aria-hidden="true" />
                </button>
                {open === r.student_id && (
                  <div className="rs-bs-more">
                    <div className="rs-bs-subj">
                      {d.class_subjects.map((cs) => { const v = r.subjects[String(cs.id)]; return (
                        <span key={cs.id} className={tone(v, pm)}><small>{cs.name}</small><b>{v != null ? fmtNum(v) : '–'}</b></span>); })}
                    </div>
                    {r.card_url && <a className="rs-btn ghost sm" href={r.card_url} data-native><i className="fas fa-id-card" aria-hidden="true" /> Report card</a>}
                  </div>
                )}
              </div>
            ))}
            {!rows.length && <p className="rs-muted rs-pad">No students match.</p>}
          </div>
        ) : (
          <div className="rs-card flush rs-bs-wrap">
            <table className="rs-bs">
              <thead><tr>
                <th className="pos">Pos</th><th className="nm">Student</th>
                {d.class_subjects.map((cs) => <th key={cs.id} title={cs.name}>{cs.short}</th>)}
                <th className="sum">Total</th><th className="sum">Avg</th><th className="sum">Pass / fail</th>
              </tr></thead>
              <tbody>{rows.length ? rows.map((r) => (
                <tr key={r.student_id}>
                  <td className="pos"><span className={'rs-pos ' + medal(r.position)}>{r.position}</span></td>
                  <td className="nm">{r.card_url ? <a href={r.card_url} data-native title="Open report card">{r.student}</a> : r.student}</td>
                  {d.class_subjects.map((cs) => { const v = r.subjects[String(cs.id)]; return <td key={cs.id} className={'sc ' + tone(v, pm)}>{v != null ? fmtNum(v) : '–'}</td>; })}
                  <td className="sum">{fmtNum(r.total)}</td>
                  <td className={'sum avg ' + tone(r.average, pm)}>{fmtNum(r.average)}</td>
                  <td className="sum"><span className="rs-pf good">{r.passed}</span><span className={'rs-pf ' + (r.failed ? 'bad' : '')}>{r.failed}</span></td>
                </tr>)) : (
                <tr><td colSpan={d.class_subjects.length + 5} className="rs-muted rs-pad">No students match.</td></tr>)}
              </tbody>
              {subjAvg.length > 0 && !hasFilter && !term && (
                <tfoot><tr><td className="pos" /><td className="nm">Subject average</td>
                  {d.class_subjects.map((cs) => { const x = subjAvg.find((s) => s.id === cs.id); return <td key={cs.id} className={'sc ' + (x ? tone(x.avg, pm) : '')}>{x ? fmtNum(Math.round(x.avg * 10) / 10) : '–'}</td>; })}
                  <td className="sum" /><td className={'sum avg ' + tone(avg, pm)}>{fmtNum(Math.round(avg * 10) / 10)}</td><td className="sum" /></tr></tfoot>
              )}
            </table>
          </div>
        )}
        <p className="rs-legend">
          <span><i className="good" /> 70 and above</span><span><i className="mid" /> {pm}–69</span><span><i className="bad" /> below {pm} (fail)</span>
          {!phone && <span className="rs-legend-k">{d.class_subjects.map((cs) => `${cs.short} = ${cs.name}`).join(' · ')}</span>}
        </p>
      </>) : d.has_selection ? (
        <Blank icon="fa-table" title="No scores yet"><p>No scores have been entered for this class yet.</p>
          {canWrite(d, 'scores_enter') && <a href={u.scores} className="rs-btn primary"><i className="fas fa-pen" aria-hidden="true" /> Enter scores</a>}</Blank>
      ) : (
        <Blank icon="fa-hand-pointer" title="Choose a class"><p>Pick a term and class to see its broadsheet.</p></Blank>
      )}
    </div>
  );
}

// ── 4. Report comments ─────────────────────────────────────────────────────
const PHRASES = [
  { min: 70, text: 'An excellent result. Keep it up!' },
  { min: 60, text: 'A very good performance. Keep working hard.' },
  { min: 50, text: 'A good result, but there is room to do better.' },
  { min: 40, text: 'A fair result. More effort is needed next term.' },
  { min: 0, text: 'A weak result. Needs to work much harder and seek help.' },
];
const EXTRAS = ['Hardworking and well-behaved.', 'Pays attention in class.', 'Should be more punctual.', 'Needs to improve in Mathematics.', 'Should read more at home.'];
const suggestFor = (avg) => (avg == null ? '' : (PHRASES.find((p) => avg >= p.min) || PHRASES[PHRASES.length - 1]).text);

export function Comments({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, ...extra });
  const pm = Number(d.pass_mark) || 50;
  const init = () => { const m = {}; d.students.forEach((s) => { m['t_' + s.id] = s.teacher_comment || ''; m['p_' + s.id] = s.principal_comment || ''; }); return m; };
  const [vals, setVals] = useState(init);
  const base = useRef(init());
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState('all');
  const [q, setQ] = useState('');
  useEffect(() => { const m = init(); setVals(m); base.current = { ...m }; }, [d.students]); // eslint-disable-line
  const changed = Object.keys(vals).filter((k) => (vals[k] || '') !== (base.current[k] || '')).length;
  useUnsavedGuard(changed > 0);
  const tDone = d.students.filter((s) => (vals['t_' + s.id] || '').trim()).length;
  const pDone = d.students.filter((s) => (vals['p_' + s.id] || '').trim()).length;
  const setV = (k, v) => setVals((m) => ({ ...m, [k]: v }));
  const append = (k, txt) => setVals((m) => { const cur = (m[k] || '').trim(); return { ...m, [k]: cur ? (cur.endsWith('.') || cur.endsWith('!') ? cur + ' ' : cur + '. ') + txt : txt }; });
  const fillSuggested = (which) => setVals((m) => {
    const n = { ...m }; let c = 0;
    d.students.forEach((s) => { const k = which + '_' + s.id; if (!(n[k] || '').trim() && s.average != null) { n[k] = suggestFor(s.average); c += 1; } });
    notify(c ? 'success' : 'info', c ? `Suggested comments added for ${c} student(s) — review them, then save.` : 'Every student with results already has a comment.');
    return n;
  });
  const save = async (e) => {
    if (e) e.preventDefault();
    setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id };
    d.students.forEach((s) => { fields['t_' + s.id] = vals['t_' + s.id] ?? ''; fields['p_' + s.id] = vals['p_' + s.id] ?? ''; });
    const r = await submitJson(d.submit_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const term = q.trim().toLowerCase();
  const list = d.students.filter((s) => (!term || s.full_name.toLowerCase().includes(term))
    // Filter on the SAVED comment so a card doesn't vanish while it's being typed.
    && (show === 'all' || (show === 't' && !(base.current['t_' + s.id] || '').trim()) || (show === 'p' && !(base.current['p_' + s.id] || '').trim())));
  const savedT = d.students.filter((s) => (base.current['t_' + s.id] || '').trim()).length;
  const savedP = d.students.filter((s) => (base.current['p_' + s.id] || '').trim()).length;
  const n = d.students.length;
  return (
    <div className={'rs' + (phone ? ' has-bar' : '')}>
      <Head icon="fa-comment-dots" title="Report comments" sub={subLine(d) || 'Form teacher and principal comments'}>
        {d.has_students && <Menu label="Quick fill" items={[
          { icon: 'fa-wand-magic-sparkles', label: 'Suggest form-teacher comments for empty boxes', onClick: () => fillSuggested('t') },
          { icon: 'fa-wand-magic-sparkles', label: 'Suggest principal comments for empty boxes', onClick: () => fillSuggested('p') },
        ]} />}
      </Head>
      <Picker d={d} go={go} />
      <Flow d={d} current="comments" />
      {d.has_students ? (
        <form onSubmit={save}>
          <Tiles items={[
            { label: 'Form teacher', value: `${tDone}/${n}`, sub: tDone === n ? 'All written' : `${n - tDone} to write`, tone: tDone === n ? 'good' : '' },
            { label: 'Principal', value: `${pDone}/${n}`, sub: pDone === n ? 'All written' : `${n - pDone} to write`, tone: pDone === n ? 'good' : '' },
          ]} />
          <div className="rs-toolbar">
            <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" placeholder="Find a student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a student" /></label>
            <Seg label="Show" value={show} onChange={setShow} options={[
              { value: 'all', label: 'All', count: n }, { value: 't', label: phone ? 'No teacher' : 'Missing teacher', count: n - savedT }, { value: 'p', label: phone ? 'No principal' : 'Missing principal', count: n - savedP }]} />
          </div>
          <div className="rs-cm-list">
            {list.map((s) => {
              const sug = suggestFor(s.average);
              return (
                <section key={s.id} className="rs-cm">
                  <header>
                    <Avatar name={s.full_name} gender={s.gender} />
                    <div><strong>{s.full_name}</strong>
                      <small>{s.average != null ? <>Average <b className={tone(s.average, pm)}>{fmtNum(s.average)}</b>{s.position ? ` · ${ordinal(s.position)} in class` : ''}</> : 'No results worked out yet'}</small></div>
                    {(vals['t_' + s.id] || '').trim() && (vals['p_' + s.id] || '').trim() && <i className="fas fa-circle-check rs-ok" aria-label="Both comments written" />}
                  </header>
                  <div className="rs-cm-grid">
                    {[['t', 'Form teacher'], ['p', 'Principal']].map(([w, lbl]) => (
                      <label key={w} className="rs-cm-f"><span>{lbl}</span>
                        <textarea rows={phone ? 2 : 2} value={vals[w + '_' + s.id] ?? ''} placeholder={sug ? `e.g. ${sug}` : 'Write a comment…'}
                                  onChange={(e) => setV(w + '_' + s.id, e.target.value)} />
                        <span className="rs-cm-chips">
                          {sug && !(vals[w + '_' + s.id] || '').trim() && <button type="button" className="rs-chip sug" onClick={() => setV(w + '_' + s.id, sug)}><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Use suggestion</button>}
                          {w === 't' && EXTRAS.slice(0, phone ? 2 : 5).map((x) => <button type="button" key={x} className="rs-chip" onClick={() => append(w + '_' + s.id, x)}>+ {x.replace(/\.$/, '')}</button>)}
                        </span>
                      </label>
                    ))}
                  </div>
                </section>
              );
            })}
            {!list.length && <p className="rs-muted rs-pad">{show === 'all' ? 'No students match.' : 'Nothing missing here — well done.'}</p>}
          </div>
          {canWrite(d, 'scores_enter') && (
            <Bar>
              <span className="rs-bar-t"><b>{changed ? `${changed} unsaved` : 'All saved'}</b><small>{tDone}/{n} teacher · {pDone}/{n} principal</small></span>
              <button type="submit" className="rs-btn primary" disabled={busy}><i className="fas fa-floppy-disk" aria-hidden="true" /> Save comments</button>
            </Bar>
          )}
        </form>
      ) : d.selected ? (
        <Blank icon="fa-users" title="No students"><p>No students are enrolled in this class for the term.</p></Blank>
      ) : (
        <Blank icon="fa-hand-pointer" title="Choose a class"><p>Pick a term and class to write report comments.</p></Blank>
      )}
    </div>
  );
}

// ── 5. Behaviour ratings ───────────────────────────────────────────────────
const RATINGS = [{ v: 5, l: 'Excellent' }, { v: 4, l: 'Very good' }, { v: 3, l: 'Good' }, { v: 2, l: 'Fair' }, { v: 1, l: 'Poor' }];
const rLabel = (v) => (RATINGS.find((r) => String(r.v) === String(v)) || {}).l || '';

export function Affective({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, ...extra });
  const k = (sid, t) => `${sid}_${t}`;
  const init = () => { const m = {}; d.students.forEach((s) => d.traits.forEach((t) => { m[k(s.id, t.key)] = s.ratings[t.key] != null ? String(s.ratings[t.key]) : ''; })); return m; };
  const [vals, setVals] = useState(init);
  const base = useRef(init());
  const [busy, setBusy] = useState(false);
  const [cur, setCur] = useState(0);
  useEffect(() => { const m = init(); setVals(m); base.current = { ...m }; setCur(0); }, [d.students]); // eslint-disable-line
  const changed = Object.keys(vals).filter((x) => (vals[x] || '') !== (base.current[x] || '')).length;
  useUnsavedGuard(changed > 0);
  const ratedCount = (s) => d.traits.filter((t) => vals[k(s.id, t.key)]).length;
  const fullyRated = d.students.filter((s) => ratedCount(s) === d.traits.length).length;
  const setOne = (sid, t, v) => setVals((m) => ({ ...m, [k(sid, t)]: String(v) }));
  const setRow = (sid, v) => setVals((m) => { const n = { ...m }; d.traits.forEach((t) => { n[k(sid, t.key)] = String(v); }); return n; });
  const setCol = (t, v, onlyEmpty) => setVals((m) => { const n = { ...m }; d.students.forEach((s) => { if (!onlyEmpty || !n[k(s.id, t)]) n[k(s.id, t)] = String(v); }); return n; });
  const fillEmpty = (v) => setVals((m) => { const n = { ...m }; Object.keys(n).forEach((x) => { if (!n[x]) n[x] = String(v); }); return n; });
  const save = async (e) => {
    if (e) e.preventDefault();
    setBusy(true);
    const fields = { term_id: d.term_id, assignment_id: d.assignment_id };
    d.students.forEach((s) => d.traits.forEach((t) => { fields[`r_${s.id}_${t.key}`] = vals[k(s.id, t.key)] ?? ''; }));
    const r = await submitJson(d.submit_url, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const n = d.students.length;
  const st = d.students[Math.min(cur, n - 1)];
  return (
    <div className={'rs' + (phone ? ' has-bar' : '')}>
      <Head icon="fa-star-half-stroke" title="Behaviour ratings" sub={subLine(d) || 'Rate each student’s conduct'}>
        {d.has_students && <Menu label="Quick fill" items={[
          ...RATINGS.slice(0, 3).map((r) => ({ icon: 'fa-fill-drip', label: `Fill every empty box with ${r.v} (${r.l})`, onClick: () => fillEmpty(r.v) })),
        ]} />}
      </Head>
      <Picker d={d} go={go} />
      <Flow d={d} current="affective" />
      {d.has_students ? (
        <form onSubmit={save}>
          <div className="rs-af-top">
            <span><b>{fullyRated}</b> of {n} students fully rated</span><Meter value={fullyRated} max={n} />
            <span className="rs-af-scale rs-hide-sm">{RATINGS.map((r) => <span key={r.v}><b className={'r' + r.v}>{r.v}</b> {r.l}</span>)}</span>
          </div>
          {phone ? (
            <section className="rs-card rs-af-one">
              <header className="rs-af-who">
                <button type="button" className="rs-icon-btn" disabled={cur === 0} onClick={() => setCur((c) => c - 1)} aria-label="Previous student"><i className="fas fa-chevron-left" aria-hidden="true" /></button>
                <div><Avatar name={st.full_name} /><span><strong>{st.full_name}</strong><small>Student {cur + 1} of {n} · {ratedCount(st)}/{d.traits.length} rated</small></span></div>
                <button type="button" className="rs-icon-btn" disabled={cur >= n - 1} onClick={() => setCur((c) => c + 1)} aria-label="Next student"><i className="fas fa-chevron-right" aria-hidden="true" /></button>
              </header>
              <div className="rs-af-all"><span>Rate all traits</span>
                {RATINGS.map((r) => <button type="button" key={r.v} className={'r' + r.v} onClick={() => setRow(st.id, r.v)}>{r.v}</button>)}</div>
              {d.traits.map((t) => {
                const v = vals[k(st.id, t.key)];
                return (
                  <div key={t.key} className="rs-af-trait">
                    <span>{t.label}<small>{rLabel(v) || 'Not rated'}</small></span>
                    <div className="rs-af-btns" role="radiogroup" aria-label={t.label}>
                      {[1, 2, 3, 4, 5].map((x) => <button type="button" key={x} role="radio" aria-checked={String(v) === String(x)}
                        className={String(v) === String(x) ? 'on r' + x : ''} onClick={() => setOne(st.id, t.key, x)}>{x}</button>)}
                    </div>
                  </div>
                );
              })}
              {cur < n - 1 && <button type="button" className="rs-btn ghost wide" onClick={() => { setCur((c) => c + 1); window.scrollTo(0, 0); }}>Next student <i className="fas fa-arrow-right" aria-hidden="true" /></button>}
            </section>
          ) : (
            <div className="rs-card flush rs-af-wrap">
              <table className="rs-af">
                <thead><tr><th className="nm">Student</th>
                  {d.traits.map((t) => (
                    <th key={t.key}><span className="rs-af-th" title={t.label}>{t.label}</span>
                      <select className="rs-af-col" value="" onChange={(e) => { if (e.target.value) setCol(t.key, e.target.value, false); }} aria-label={`Set everyone's ${t.label}`}>
                        <option value="">All…</option>{RATINGS.map((r) => <option key={r.v} value={r.v}>{r.v} · {r.l}</option>)}</select></th>
                  ))}
                  <th className="row">Whole row</th></tr></thead>
                <tbody>{d.students.map((s) => (
                  <tr key={s.id}><td className="nm">{s.full_name}<small>{ratedCount(s)}/{d.traits.length}</small></td>
                    {d.traits.map((t) => {
                      const v = vals[k(s.id, t.key)] ?? '';
                      return (
                        <td key={t.key}>
                          <select className={'rs-af-cell' + (v ? ' r' + v : '')} value={v} title={rLabel(v)} aria-label={`${s.full_name} ${t.label}`}
                                  onChange={(e) => setVals((m) => ({ ...m, [k(s.id, t.key)]: e.target.value }))}>
                            <option value="">–</option>{[5, 4, 3, 2, 1].map((x) => <option key={x} value={x}>{x}</option>)}</select></td>
                      );
                    })}
                    <td className="row">
                      <select className="rs-af-col" value="" onChange={(e) => { if (e.target.value) setRow(s.id, e.target.value); }} aria-label={`Set all of ${s.full_name}'s ratings`}>
                        <option value="">All…</option>{RATINGS.map((r) => <option key={r.v} value={r.v}>{r.v} · {r.l}</option>)}</select></td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
          {canWrite(d, 'scores_enter') && (
            <Bar>
              <span className="rs-bar-t"><b>{changed ? `${changed} unsaved` : 'All saved'}</b><small>{fullyRated}/{n} fully rated</small></span>
              <button type="submit" className="rs-btn primary" disabled={busy}><i className="fas fa-floppy-disk" aria-hidden="true" /> Save ratings</button>
            </Bar>
          )}
        </form>
      ) : d.selected ? (
        <Blank icon="fa-users" title="No students"><p>No students are enrolled in this class for the term.</p></Blank>
      ) : (
        <Blank icon="fa-hand-pointer" title="Choose a class"><p>Pick a term and class to rate behaviour.</p></Blank>
      )}
    </div>
  );
}
