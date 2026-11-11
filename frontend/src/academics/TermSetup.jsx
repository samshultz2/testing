// Term setup — "is this term ready?" A grouped checklist (calendar, classes,
// subjects, fees) where every step says what it is, why it matters and offers
// a one-tap fix; most fixes run in place (activate, set dates, generate weeks,
// copy last term). A side panel shows readiness, the next step, where the term
// is in its calendar and which parts of the school app are unlocked.
import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useNav, navParams } from '../lib/section';
import { confirm } from '../components/ui';
import { Head, Ring, Sheet, Blank } from '../subjects/results';
import { A, Field, Toggle, Pill, plural } from '../components/appkit';

function useRun(notify) {
  const nav = useNav();
  const [busy, setBusy] = useState(null);
  const run = async (key, url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm({ title: 'Are you sure?', message: confirmMsg, confirmText: 'Yes, continue' })) return;
    setBusy(key);
    const r = await submitJson(url, fields || {});
    setBusy(null);
    if (r.ok) { notify('success', r.message || 'Done.'); nav.refresh(); }
    else notify('error', r.error || 'That didn’t work — please try again.');
  };
  return { run, busy };
}

function ActionBtn({ step, primary, run, busy, onDates, block }) {
  const a = step.action;
  if (!a) return null;
  const cls = 'rs-btn ' + (primary ? 'primary' : 'ghost') + (block ? ' su-block' : '');
  if (a.kind === 'link') return <A to={a.url} className={cls}>{a.label} <i className="fas fa-arrow-right" aria-hidden="true" /></A>;
  if (a.kind === 'dates') return <button type="button" className={cls} onClick={onDates}><i className="fas fa-calendar-days" aria-hidden="true" /> {a.label}</button>;
  const b = busy === step.key;
  return (
    <button type="button" className={cls} disabled={!!busy} onClick={() => run(step.key, a.url, a.fields, a.confirm)}>
      <i className={'fas ' + (b ? 'fa-spinner fa-spin' : (a.icon || 'fa-check'))} aria-hidden="true" /> {a.label}
    </button>
  );
}

function DatesSheet({ d, step, onClose, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ start_date: d.term_dates.start_date, end_date: d.term_dates.end_date });
  const [rebuild, setRebuild] = useState(!d.info.weeks);
  const [busy, setBusy] = useState(false);
  const bad = f.start_date && f.end_date && f.end_date <= f.start_date;
  const weeks = f.start_date && f.end_date && !bad
    ? Math.ceil(((new Date(f.end_date) - new Date(f.start_date)) / 864e5 + 1) / 7) : 0;
  const save = async () => {
    if (!f.start_date || !f.end_date || bad) { notify('error', 'Pick a start date and a later end date.'); return; }
    setBusy(true);
    const r = await submitJson(step.action.url, { ...f, ...(rebuild ? { regenerate_weeks: 'on' } : {}) });
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Dates saved.'); onClose(); nav.refresh(); }
    else notify('error', r.error || 'Could not save the dates.');
  };
  return (
    <Sheet title={`${d.term.full_name} dates`} onClose={onClose}>
      <div className="su-form">
        <div className="cm-row2">
          <Field label="First day" grow><input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
          <Field label="Last day" grow><input type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
        </div>
        {bad ? <p className="su-err"><i className="fas fa-circle-exclamation" aria-hidden="true" /> The last day must be after the first day.</p>
          : weeks > 0 && <p className="cm-mute">About {plural(weeks, 'week')} of school.</p>}
        <Toggle title="Rebuild the weeks from these dates" sub={d.info.weeks ? `Replaces the ${d.info.weeks} weeks already set up` : 'Creates Monday–Friday school weeks'}
                on={rebuild} onChange={setRebuild} />
        <div className="su-form-f">
          <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy || bad} onClick={save}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> Save dates</button>
        </div>
      </div>
    </Sheet>
  );
}

function StepRow({ s, n, run, busy, onDates, isNext }) {
  const state = s.done ? (s.warn ? 'warn' : 'done') : (s.optional ? 'opt' : 'todo');
  return (
    <div className={'su-step ' + state + (isNext ? ' next' : '')}>
      <span className="su-dot" aria-hidden="true">
        {s.done ? <i className={'fas ' + (s.warn ? 'fa-exclamation' : 'fa-check')} /> : <i className={'fas ' + s.icon} />}
      </span>
      <div className="su-body">
        <div className="su-t"><b>{s.title}</b>{s.optional && <Pill>Recommended</Pill>}
          {isNext && <Pill tone="info" icon="fa-arrow-right">Next</Pill>}
          <span className="sr-only">{s.done ? 'done' : 'not done'}</span></div>
        <span className="su-d">{s.detail}</span>
        {s.note && <span className="su-n"><i className="fas fa-circle-info" aria-hidden="true" /> {s.note}</span>}
        {!s.done && <span className="su-why">{s.why}</span>}
      </div>
      <div className="su-act"><ActionBtn step={s} primary={!s.done && !s.optional} run={run} busy={busy} onDates={onDates} /></div>
    </div>
  );
}

export default function TermSetup({ d, notify }) {
  const nav = useNav();
  const { run, busy } = useRun(notify);
  const [dates, setDates] = useState(false);
  if (!d.term) {
    return (
      <div className="rs cm su">
        <Head icon="fa-list-check" title="Term setup" sub="Nothing to set up yet." />
        <Blank icon="fa-calendar-plus" title="Create a term first">
          <p>Add an academic session and its terms, then come back here to get the term ready.</p>
          <A to={d.urls.add_term} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /> Add a term</A>
        </Blank>
      </div>
    );
  }
  const steps = d.steps;
  const next = steps.find((s) => !s.done && !s.optional && s.action) || steps.find((s) => !s.done && s.action);
  const allReq = d.done === d.required;
  const pct = d.required ? d.done / d.required * 100 : 0;
  const i = d.info;
  const dateStep = steps.find((s) => s.key === 'dates');
  const onDates = () => setDates(true);
  let n = 0;
  return (
    <div className="rs cm su">
      <Head icon="fa-list-check" title="Term setup" sub={`Get ${d.term.full_name} ready for attendance, results and fees.`}>
        <select className="cm-sel" value={d.term_id} aria-label="Term"
                onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value })}>
          {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}{t.is_active ? ' · active' : ''}</option>)}
        </select>
      </Head>
      {!d.can_write && <p className="su-ro"><i className="fas fa-eye" aria-hidden="true" /> View only — you can see progress but not change the setup.</p>}

      <div className="su-wrap">
        <aside className="su-side">
          <section className={'rs-card su-ready' + (allReq ? ' ok' : '')}>
            <div className="su-ready-top">
              <Ring value={pct} size={88} label="ready" />
              <div>
                <b>{allReq ? 'Ready to go' : `${d.required - d.done} essential${d.required - d.done === 1 ? '' : 's'} left`}</b>
                <small>{d.done} of {d.required} essentials · {d.optional_done} of {d.optional_total} recommended</small>
                {d.term.is_active ? <Pill tone="good" icon="fa-bolt">Active term</Pill> : <Pill icon="fa-moon">Not active</Pill>}
              </div>
            </div>
            {next && (
              <div className="su-next">
                <span className="k">Next step</span>
                <b>{next.title}</b>
                <small>{next.why}</small>
                <ActionBtn step={next} primary run={run} busy={busy} onDates={onDates} block />
              </div>)}
            {!next && allReq && <p className="su-allset"><i className="fas fa-circle-check" aria-hidden="true" /> Everything is set up. Teachers can mark attendance and enter scores.</p>}
          </section>

          {i.start && (
            <section className="rs-card su-time">
              <div className="su-time-h">
                <b>{i.state === 'running' ? (i.week ? `Week ${i.week}${i.weeks ? ` of ${i.weeks}` : ''}` : 'In session')
                  : i.state === 'upcoming' ? `Starts in ${plural(i.days_to_start, 'day')}` : 'Term ended'}</b>
                {i.state === 'running' && <small>{plural(i.days_left, 'day')} left</small>}
              </div>
              <div className="su-track"><i style={{ width: i.progress + '%' }} /></div>
              <div className="su-time-f"><span>{i.start}</span><span>{i.end}</span></div>
            </section>)}

          {d.unlocks.length > 0 && (
            <section className="rs-card su-unlock">
              <span className="k">What’s ready</span>
              {d.unlocks.map((u) => (
                <div key={u.label} className={'su-u' + (u.ready ? ' on' : '')}>
                  <span className="su-u-ic"><i className={'fas ' + u.icon} aria-hidden="true" /></span>
                  <span className="su-u-t"><b>{u.label}</b><small>{u.ready ? 'Ready' : `Needs ${u.needs}`}</small></span>
                  <i className={'fas ' + (u.ready ? 'fa-circle-check' : 'fa-lock')} aria-hidden="true" />
                </div>))}
            </section>)}
        </aside>

        <div className="su-main">
          {d.groups.map((g) => {
            const gs = steps.filter((s) => s.group === g.key);
            const gd = gs.filter((s) => s.done).length;
            return (
              <section key={g.key} className="rs-card su-group">
                <div className="su-group-h">
                  <h3><i className={'fas ' + g.icon} aria-hidden="true" /> {g.label}</h3>
                  <span className={'su-count' + (gd === gs.length ? ' ok' : '')}>{gd}/{gs.length}</span>
                </div>
                {gs.map((s) => { n += 1; return <StepRow key={s.key} s={s} n={n} run={run} busy={busy} onDates={onDates} isNext={next && next.key === s.key} />; })}
              </section>);
          })}
          <div className="su-links">
            <A to={d.urls.terms} className="cm-link">All terms <i className="fas fa-arrow-right" aria-hidden="true" /></A>
            <A to={d.urls.sessions} className="cm-link">Sessions <i className="fas fa-arrow-right" aria-hidden="true" /></A>
            <A to={d.urls.assignments} className="cm-link">Class setup <i className="fas fa-arrow-right" aria-hidden="true" /></A>
          </div>
        </div>
      </div>
      {dates && dateStep && <DatesSheet d={d} step={dateStep} notify={notify} onClose={() => setDates(false)} />}
    </div>
  );
}
