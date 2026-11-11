// Copy term setup — start a term from another one. Pick From → To (sensible
// defaults: last term with classes → the active term), choose what to bring
// (classes & arms, students, subjects & teachers, fees), see a live
// class-by-class preview, then copy in one tap. Copying students across
// sessions is flagged: that keeps them in the same class — use Promotion.
import React, { useState, useEffect } from 'react';
import { submitJson } from '../lib/forms';
import { useNav } from '../lib/section';
import { confirm } from '../components/ui';
import { Head, Blank } from '../subjects/results';
import { A, SecNav, Toggle, Pill, plural } from '../components/appkit';

function TermCard({ label, t, terms, value, onChange, other }) {
  return (
    <div className={'cp-term' + (t ? '' : ' none')}>
      <span className="k">{label}</span>
      <select className="cm-sel" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        <option value="">Choose a term…</option>
        {terms.map((x) => <option key={x.id} value={x.id} disabled={String(x.id) === String(other)}>{x.full_name}{x.is_active ? ' · active' : ''}</option>)}</select>
      {t && <div className="cp-stats">
        <span><b>{t.classes}</b>classes</span><span><b>{t.students}</b>students</span>
        <span><b>{t.subjects}</b>subjects</span>{t.fees != null && <span><b>{t.fees}</b>fees</span>}</div>}
    </div>
  );
}

export default function CopySetup({ d, notify }) {
  const nav = useNav();
  const [from, setFrom] = useState(String(d.default_from || ''));
  const [to, setTo] = useState(String(d.default_to || ''));
  const [opt, setOpt] = useState({ students: true, subjects: d.can.subjects, fees: false });
  const [pv, setPv] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const T = Object.fromEntries(d.terms.map((t) => [String(t.id), t]));
  const ft = T[from], tt = T[to];
  const crossSession = ft && tt && ft.session_id !== tt.session_id;
  useEffect(() => { if (crossSession) setOpt((o) => ({ ...o, students: false })); }, [from, to]); // eslint-disable-line
  useEffect(() => {
    setPv(null); setDone(null);
    if (!from || !to || from === to) return;
    let off = false;
    fetch(`${d.preview_url}?from_term_id=${from}&to_term_id=${to}`, { credentials: 'same-origin' })
      .then((r) => r.json()).then((j) => { if (!off) setPv(j); }).catch(() => {});
    return () => { off = true; };
  }, [from, to]); // eslint-disable-line
  const swap = () => { setFrom(to); setTo(from); };
  const nothing = pv && !pv.rows.length;
  const work = pv && ((pv.totals.classes_new > 0) || (opt.students && pv.totals.students_new > 0)
    || (opt.subjects && ft && ft.subjects > 0) || (opt.fees && ft && ft.fees > 0));
  const run = async () => {
    const parts = [`${pv.totals.classes_new} new ${pv.totals.classes_new === 1 ? 'class' : 'classes'}`,
      opt.students && `${pv.totals.students_new} students placed`, opt.subjects && 'subjects', opt.fees && 'fees'].filter(Boolean);
    if (!await confirm({ title: `Copy into ${tt.full_name}?`, confirmText: 'Copy',
      message: `${parts.join(', ')} from ${ft.full_name}. Nothing already in ${tt.full_name} is changed or removed.` })) return;
    setBusy(true);
    const out = [];
    const r = await submitJson(d.submit_url, { from_term_id: from, to_term_id: to, copy_enrollments: opt.students ? 'on' : '' });
    out.push({ k: 'Classes', ok: r.ok, msg: r.ok ? r.message : r.error });
    if (r.ok && opt.subjects && d.urls.subjects) {
      const s = await submitJson(d.urls.subjects, { from_term_id: from, to_term_id: to });
      out.push({ k: 'Subjects', ok: s.ok, msg: s.ok ? s.message : s.error });
    }
    if (r.ok && opt.fees && d.urls.fees) {
      const f = await submitJson(d.urls.fees, { from_term_id: from, to_term_id: to });
      out.push({ k: 'Fees', ok: f.ok, msg: f.ok ? f.message : f.error });
    }
    setBusy(false); setDone(out);
    if (out.every((x) => x.ok)) notify('success', 'Copied.'); else notify('error', 'Some parts could not be copied — see below.');
    nav.refresh();
  };
  return (
    <div className="rs cm su tm st cp">
      <SecNav label="School structure" active="copy" items={[
        ['classes', 'fa-school', 'Classes', d.urls.classes], ['arms', 'fa-code-branch', 'Arms', d.urls.arms],
        ['assignments', 'fa-sitemap', 'Class setup', d.urls.assignments], ['copy', 'fa-copy', 'Copy a term', location.pathname]]} />
      <Head icon="fa-copy" title="Copy a term’s setup" sub="Start a term from another one — then adjust what changed." />

      {d.terms.length < 2 ? <Blank icon="fa-calendar-plus" title="You need two terms"><p>Create the new term first, then copy into it.</p></Blank> : (<>
        <section className="rs-card cp-pick">
          <TermCard label="Copy from" t={ft} terms={d.terms} value={from} onChange={setFrom} other={to} />
          <button type="button" className="cp-swap" onClick={swap} aria-label="Swap terms" title="Swap"><i className="fas fa-arrow-right" aria-hidden="true" /></button>
          <TermCard label="Into" t={tt} terms={d.terms} value={to} onChange={setTo} other={from} />
        </section>

        {ft && tt && (
          <div className="cp-wrap">
            <section className="rs-card cp-opts">
              <span className="k">What to copy</span>
              <Toggle title="Classes & arms" sub="Always — the classes and arms opened in the term" on onChange={() => {}} disabled />
              <Toggle title="Students" sub={crossSession ? 'New school year: this would keep everyone in the SAME class' : 'Put each student back in their class'}
                      on={opt.students} onChange={(v) => setOpt({ ...opt, students: v })} />
              {crossSession && (
                <div className="cm-attn-i mid cp-warn"><i className="fas fa-triangle-exclamation" aria-hidden="true" />
                  <span>{ft.full_name} and {tt.full_name} are in different sessions. To move students up a class, use Promotion instead.</span>
                  {d.urls.promotion && <A to={d.urls.promotion} className="rs-btn sm ghost">Promotion</A>}</div>)}
              {d.can.subjects && <Toggle title="Subjects & subject teachers" sub={`${ft.subjects} class subjects in ${ft.full_name}`} on={opt.subjects && ft.subjects > 0} disabled={!ft.subjects} onChange={(v) => setOpt({ ...opt, subjects: v })} />}
              {d.can.fees && <Toggle title="School fees" sub={`${ft.fees} fee lines — adjust amounts afterwards`} on={opt.fees && ft.fees > 0} disabled={!ft.fees} onChange={(v) => setOpt({ ...opt, fees: v })} />}
              <p className="cm-mute cp-note"><i className="fas fa-shield-halved" aria-hidden="true" /> Nothing in {tt.full_name} is changed or removed. Attendance and scores are never copied. Students who left the school, or already have a class in {tt.full_name}, are skipped.</p>
              <button type="button" className="rs-btn primary su-block" disabled={busy || !pv || nothing || !work} onClick={run}>
                <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-copy')} aria-hidden="true" /> {busy ? 'Copying…' : `Copy into ${tt.full_name}`}</button>
              {pv && !nothing && !work && !done && <small className="cm-mute">Nothing new to copy — {tt.full_name} already has everything selected.</small>}
              {done && <div className="cp-done">{done.map((x) => (
                <div key={x.k} className={'cm-attn-i ' + (x.ok ? 'good' : 'bad')}><i className={'fas ' + (x.ok ? 'fa-circle-check' : 'fa-circle-xmark')} aria-hidden="true" /><span><b>{x.k}:</b> {x.msg}</span></div>))}
                <A to={`${d.urls.assignments}?term_id=${to}`} className="rs-btn ghost su-block">Open class setup for {tt.full_name} <i className="fas fa-arrow-right" aria-hidden="true" /></A></div>}
            </section>

            <section className="rs-card su-group cp-prev">
              <div className="su-group-h"><h3><i className="fas fa-eye" aria-hidden="true" /> Preview</h3>
                {pv && pv.rows.length > 0 && <span className="cm-mute">{plural(pv.totals.classes_new, 'new class', 'new classes')}{opt.students ? ` · ${plural(pv.totals.students_new, 'student')}` : ''}</span>}</div>
              {!pv ? <p className="cm-mute tv-empty">Working it out…</p> : nothing ? (
                <p className="cm-mute tv-empty">{ft.full_name} has no classes to copy.</p>
              ) : pv.rows.map((r) => (
                <div key={r.name} className="cp-row">
                  <span className="cp-row-t"><b>{r.name}</b>
                    {r.exists ? <Pill>Already open</Pill> : <Pill tone="good" icon="fa-plus">New</Pill>}</span>
                  {opt.students && <span className="cp-row-n">
                    {r.new > 0 && <b>+{r.new}</b>}{r.skip > 0 && <small>{r.skip} skipped</small>}{!r.new && !r.skip && <small>no students</small>}</span>}
                </div>))}
            </section>
          </div>)}
      </>)}
    </div>
  );
}
