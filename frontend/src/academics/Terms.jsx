// Terms — every session as a three-term timeline. The active term is pinned
// at the top with its progress; each term shows its dates, weeks, classes and
// students, with in-place actions (set dates, make active, open setup). Missing
// terms appear as "add" slots, and an attention strip flags decisions:
// next term not created, overlapping dates, no active term.
import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useNav } from '../lib/section';
import { confirm } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Sheet, Blank, Menu } from '../subjects/results';
import { A, Field, Toggle, Pill, plural } from '../components/appkit';
import { DatesSheet } from './TermSetup';

const NAMES = { 1: 'First Term', 2: 'Second Term', 3: 'Third Term' };
const STATE = {
  running: ['good', 'fa-circle-play', 'In progress'], upcoming: ['info', 'fa-hourglass-start', 'Upcoming'],
  ended: ['', 'fa-flag-checkered', 'Ended'], nodates: ['mid', 'fa-calendar-xmark', 'No dates'],
};

async function activate(t) {
  const ok = await confirm({ title: `Make ${t.name} ${t.session} active?`,
    message: 'Everyone’s attendance, score entry and CBT will switch to this term.', confirmText: 'Make active' });
  if (!ok) return null;
  const r = await submitJson(t.activate_url, {});
  // Full reload so the new active term reaches every section (header badge, pickers).
  if (r.ok) window.location.href = window.location.pathname;
  return r;
}

function AddSheet({ d, init, onClose, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ session_id: String(init.session_id || (d.sessions.find((s) => s.is_active) || d.sessions[0] || {}).id || ''),
    term_number: String(init.term_number || ''), start_date: '', end_date: '' });
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const sess = d.sessions.find((s) => String(s.id) === f.session_id);
  const taken = new Set((sess ? sess.terms : []).map((t) => t.number));
  const bad = f.start_date && f.end_date && f.end_date <= f.start_date;
  const save = async () => {
    if (!f.session_id || !f.term_number) { notify('error', 'Choose the session and which term.'); return; }
    if (bad) { notify('error', 'The last day must be after the first day.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.add, { ...f, is_active: active ? 'on' : '' });
    setBusy(false);
    if (!r.ok) { notify('error', r.error || 'Could not add the term.'); return; }
    if (active) { window.location.href = window.location.pathname; return; }
    notify('success', r.message || 'Term added.'); onClose(); nav.refresh();
  };
  return (
    <Sheet title="Add a term" onClose={onClose}>
      <div className="su-form">
        <Field label="Session"><select value={f.session_id} onChange={(e) => setF({ ...f, session_id: e.target.value, term_number: '' })}>
          {d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_active ? ' (current)' : ''}</option>)}</select></Field>
        <div className="tm-pick" role="radiogroup" aria-label="Term">
          {[1, 2, 3].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={f.term_number === String(n)} disabled={taken.has(n)}
                    className={f.term_number === String(n) ? 'on' : ''} onClick={() => setF({ ...f, term_number: String(n) })}>
              <b>{NAMES[n]}</b><small>{taken.has(n) ? 'Already added' : 'Available'}</small></button>))}
        </div>
        <div className="cm-row2">
          <Field label="First day" grow><input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
          <Field label="Last day" grow><input type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
        </div>
        {bad ? <p className="su-err">The last day must be after the first day.</p>
          : <small className="cm-mute">Optional now — with dates, the school weeks are created for you.</small>}
        <Toggle title="Make it the active term" sub="Switches attendance, scores and CBT to this term" on={active} onChange={setActive} />
        <div className="su-form-f">
          <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy || !f.term_number || bad} onClick={save}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-plus')} aria-hidden="true" /> Add term</button>
        </div>
      </div>
    </Sheet>
  );
}

function TermCard({ t, canEdit, onDates, notify, past }) {
  const [tone, ic, label] = STATE[t.state];
  const act = async () => { const r = await activate(t); if (r && !r.ok) notify('error', r.error || 'Could not activate.'); };
  return (
    <article className={'tm-card ' + t.state + (t.is_active ? ' active' : '')}>
      <div className="tm-card-h">
        <span className="tm-num">{t.number}</span>
        <div className="tm-card-t"><b>{t.name}</b>
          <small>{t.start_date ? `${t.start_date} – ${t.end_date}` : 'Dates not set'}</small></div>
        {t.is_active ? <Pill tone="good" icon="fa-bolt">Active</Pill> : <Pill tone={tone} icon={ic}>{label}</Pill>}
      </div>
      {t.state === 'running' && (
        <div className="tm-prog"><div className="su-track"><i style={{ width: t.progress + '%' }} /></div>
          <span>{t.week ? `Week ${t.week}${t.weeks ? ` of ${t.weeks}` : ''}` : `${t.progress}%`} · {plural(t.days, 'day')} left</span></div>)}
      {t.state === 'upcoming' && <div className="tm-prog"><span>Starts in {plural(t.days, 'day')}</span></div>}
      <div className="tm-stats">
        <span><b>{t.weeks}</b>weeks</span><span><b>{t.holidays}</b>holidays</span>
        <span><b>{t.classes}</b>classes</span><span><b>{t.students}</b>students</span>
      </div>
      <div className="tm-acts">
        <A to={t.setup_url} className="rs-btn ghost sm"><i className="fas fa-list-check" aria-hidden="true" /> Setup</A>
        <A to={t.view_url} className="rs-btn ghost sm"><i className="fas fa-table-columns" aria-hidden="true" /> Weeks</A>
        {canEdit && !past && !t.is_active && t.state !== 'ended' && <button type="button" className="rs-btn primary sm" onClick={act}><i className="fas fa-bolt" aria-hidden="true" /> Make active</button>}
        {canEdit && <Menu label={`More for ${t.name}`} items={[
          { icon: 'fa-calendar-days', label: t.start_date ? 'Change dates' : 'Set dates', onClick: () => onDates(t) },
          !t.is_active && (past || t.state === 'ended') && { icon: 'fa-bolt', label: 'Make active', onClick: act },
        ]} />}
      </div>
    </article>
  );
}

export default function Terms({ d, notify }) {
  const [add, setAdd] = useState(null);
  const [dates, setDates] = useState(null);
  const [older, setOlder] = useState(false);
  const canAdd = canWrite(d, 'structure_create');
  const canEdit = canWrite(d, 'structure_edit');
  const act = d.terms.find((t) => t.is_active);
  const current = d.sessions.find((s) => s.is_active) || d.sessions[0];
  const earlier = d.sessions.filter((s) => s !== current);
  const shown = older ? d.sessions : [current].filter(Boolean);
  const byId = Object.fromEntries(d.terms.map((t) => [t.id, t]));
  return (
    <div className="rs cm su tm">
      <Head icon="fa-calendar-week" title="Terms" sub={act ? `${act.name} ${act.session} is active` : 'No active term'}>
        <A to={d.urls.setup} className="rs-btn ghost"><i className="fas fa-list-check" aria-hidden="true" /><span className="rs-hide-sm"> Term setup</span></A>
        {canAdd && <button type="button" className="rs-btn primary" onClick={() => setAdd({})}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> Add term</span></button>}
      </Head>

      {!d.terms.length ? (
        <Blank icon="fa-calendar-plus" title="No terms yet">
          <p>{d.sessions.length ? 'Add the first term of the session to start.' : 'Create an academic session first, then add its terms.'}</p>
          {d.sessions.length ? (canAdd && <button type="button" className="rs-btn primary" onClick={() => setAdd({})}><i className="fas fa-plus" aria-hidden="true" /> Add term</button>)
            : <A to={d.urls.sessions} className="rs-btn primary">Go to sessions</A>}
        </Blank>
      ) : (
        <>
          {d.alerts.length > 0 && (
            <section className="rs-card rp-attn"><span className="k">Needs attention</span>
              <div className="tm-alerts">{d.alerts.map((a, i) => (
                <div key={i} className={'cm-attn-i ' + a.tone}><i className={'fas ' + a.icon} aria-hidden="true" /><span>{a.text}</span>
                  {a.add && canAdd && <button type="button" className="rs-btn sm primary" onClick={() => setAdd(a.add)}>Add it</button>}
                  {a.link && canAdd && <A to={a.link} className="rs-btn sm primary">{a.link_label}</A>}
                  {a.activate && canEdit && byId[a.activate] && <button type="button" className="rs-btn sm primary" onClick={() => activate(byId[a.activate])}>Make active</button>}
                  {a.dates && canEdit && byId[a.dates] && <button type="button" className="rs-btn sm primary" onClick={() => setDates(byId[a.dates])}>Set dates</button>}
                </div>))}</div>
            </section>)}

          {shown.map((s) => { const past = current && s !== current && s.name < current.name; return (
            <section key={s.id} className="rs-card tm-sess">
              <div className="tm-sess-h">
                <h3><i className="fas fa-calendar" aria-hidden="true" /> {s.name}</h3>
                {s.is_active ? <Pill tone="good">Current session</Pill> : <Pill>Past session</Pill>}
                <span className="cm-mute">{plural(s.terms.length, 'term')} of 3</span>
              </div>
              <div className="tm-row">
                {[1, 2, 3].map((n) => {
                  const t = s.terms.find((x) => x.number === n);
                  if (t) return <TermCard key={n} t={t} canEdit={canEdit} onDates={setDates} notify={notify} past={past} />;
                  return canAdd && !past ? (
                    <button key={n} type="button" className="tm-slot" onClick={() => setAdd({ session_id: s.id, term_number: n })}>
                      <i className="fas fa-plus" aria-hidden="true" /><b>Add {NAMES[n]}</b><small>{s.name}</small></button>
                  ) : <div key={n} className="tm-slot off"><b>{NAMES[n]}</b><small>Not created</small></div>;
                })}
              </div>
            </section>); })}

          {earlier.length > 0 && (
            <button type="button" className="rs-btn ghost tm-more" onClick={() => setOlder(!older)}>
              <i className={'fas ' + (older ? 'fa-chevron-up' : 'fa-clock-rotate-left')} aria-hidden="true" />
              {older ? ' Hide earlier sessions' : ` Show earlier sessions (${earlier.length})`}</button>)}
        </>
      )}
      {add && <AddSheet d={d} init={add} notify={notify} onClose={() => setAdd(null)} />}
      {dates && <DatesSheet title={`${dates.name} ${dates.session} dates`} url={dates.edit_url} start={dates.start_iso} end={dates.end_iso}
                            weeks={dates.weeks} notify={notify} onClose={() => setDates(null)} />}
    </div>
  );
}
