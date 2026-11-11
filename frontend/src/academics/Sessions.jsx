// Academic sessions — the school year at a glance. The current session is a
// hero card (year progress, its three terms, students and classes); a "start
// next session" card creates next year — and optionally its three terms with
// this year's dates moved on — in one tap; every other session is a compact
// row with in-place edit and make-current.
import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useNav } from '../lib/section';
import { confirm } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Sheet, Blank, Menu } from '../subjects/results';
import { A, Field, Toggle, Pill, plural } from '../components/appkit';

const STATE = {
  running: ['good', 'In progress'], upcoming: ['info', 'Upcoming'], ended: ['', 'Ended'], nodates: ['mid', 'No dates'],
};
const reload = () => { window.location.href = window.location.pathname; };

async function makeCurrent(s, notify) {
  const ok = await confirm({ title: `Make ${s.name} the current session?`,
    message: 'The whole school switches to this session. Its running (or latest) term becomes the active term.', confirmText: 'Make current' });
  if (!ok) return;
  const r = await submitJson(s.activate_url, {});
  if (r.ok) reload(); else notify('error', r.error || 'Could not switch the session.');
}

function SessionSheet({ d, edit, preset, onClose, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ name: edit ? edit.name : (preset ? preset.name : ''),
    start_date: edit ? edit.start_iso : (preset ? preset.start_date : ''), end_date: edit ? edit.end_iso : (preset ? preset.end_date : '') });
  const [withTerms, setWithTerms] = useState(!edit);
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const bad = f.start_date && f.end_date && f.end_date <= f.start_date;
  const save = async () => {
    if (!f.name.trim()) { notify('error', 'Give the session a name, like 2026/2027.'); return; }
    if (bad) { notify('error', 'The end date must be after the start date.'); return; }
    setBusy(true);
    const r = await submitJson(edit ? edit.edit_url : d.add_url,
      { ...f, ...(edit ? {} : { is_active: active ? 'on' : '', with_terms: withTerms ? 'on' : '' }) });
    setBusy(false);
    if (!r.ok) { notify('error', r.error || 'Could not save.'); return; }
    if (active) { reload(); return; }
    notify('success', r.message || 'Saved.'); onClose(); nav.refresh();
  };
  return (
    <Sheet title={edit ? `Edit ${edit.name}` : 'New academic session'} onClose={onClose}>
      <div className="su-form">
        <Field label="Name" hint="Usually the two years it spans"><input type="text" placeholder="e.g. 2026/2027" value={f.name} autoFocus={!edit}
          onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <div className="cm-row2">
          <Field label="Starts" grow><input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
          <Field label="Ends" grow><input type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
        </div>
        {bad ? <p className="su-err">The end date must be after the start date.</p>
          : <small className="cm-mute">Optional — without dates the session follows its terms’ dates.</small>}
        {!edit && <>
          <Toggle title="Also add First, Second and Third Term" sub={preset && preset.terms.some((t) => t.start_date)
            ? 'Uses this year’s term dates, moved on a year — adjust them later' : 'You can set their dates afterwards'}
                  on={withTerms} onChange={setWithTerms} />
          {withTerms && preset && preset.terms.some((t) => t.start_date) && (
            <div className="ss-preview">{preset.terms.map((t) => (
              <span key={t.number}><b>{t.name}</b>{t.start_date ? `${t.start_date} – ${t.end_date}` : 'No dates'}</span>))}</div>)}
          <Toggle title="Make it the current session now" sub="Only when the new school year has started" on={active} onChange={setActive} />
        </>}
        <div className="su-form-f">
          <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy || bad} onClick={save}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : edit ? 'fa-check' : 'fa-plus')} aria-hidden="true" /> {edit ? 'Save' : 'Create session'}</button>
        </div>
      </div>
    </Sheet>
  );
}

const TermDots = ({ terms }) => (
  <div className="ss-terms">{[1, 2, 3].map((n) => {
    const t = terms.find((x) => x.number === n);
    return (
      <span key={n} className={'ss-t ' + (t ? t.state : 'none') + (t && t.is_active ? ' active' : '')}
            title={t ? `${t.name}: ${t.start_date ? `${t.start_date} – ${t.end_date}` : 'no dates'}` : 'Not created'}>
        <b>{['', '1st', '2nd', '3rd'][n]}</b><small>{t ? (t.is_active ? 'Active' : STATE[t.state][1]) : 'Not added'}</small>
      </span>);
  })}</div>
);

export default function Sessions({ d, notify }) {
  const [sheet, setSheet] = useState(null);
  const canAdd = canWrite(d, 'structure_create');
  const canEdit = canWrite(d, 'structure_edit');
  const cur = d.sessions.find((s) => s.is_active);
  const others = d.sessions.filter((s) => s !== cur);
  const byId = Object.fromEntries(d.sessions.map((s) => [s.id, s]));
  const u = d.urls;
  return (
    <div className="rs cm su tm ss">
      <Head icon="fa-calendar" title="Academic sessions" sub={cur ? `${cur.name} is the current session` : 'No current session'}>
        <A to={u.terms} className="rs-btn ghost"><i className="fas fa-calendar-week" aria-hidden="true" /><span className="rs-hide-sm"> Terms</span></A>
        {canAdd && <button type="button" className="rs-btn primary" onClick={() => setSheet({ preset: d.next })}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> New session</span></button>}
      </Head>

      {!d.sessions.length ? (
        <Blank icon="fa-calendar-plus" title="Start your first school year">
          <p>Create the academic session (e.g. 2025/2026) and its three terms in one go.</p>
          {canAdd && <button type="button" className="rs-btn primary" onClick={() => setSheet({})}><i className="fas fa-plus" aria-hidden="true" /> New session</button>}
        </Blank>
      ) : (
        <>
          {d.alerts.length > 0 && (
            <section className="rs-card rp-attn"><span className="k">Needs attention</span>
              <div className="tm-alerts">{d.alerts.map((a, i) => (
                <div key={i} className={'cm-attn-i ' + a.tone}><i className={'fas ' + a.icon} aria-hidden="true" /><span>{a.text}</span>
                  {a.link && <A to={a.link} className="rs-btn sm primary">{a.link_label}</A>}
                  {a.activate && canEdit && <button type="button" className="rs-btn sm primary" onClick={() => makeCurrent(byId[a.activate], notify)}>Make current</button>}
                </div>))}</div>
            </section>)}

          <div className="ss-top">
            {cur && (
              <section className="rs-card ss-hero">
                <div className="ss-hero-h">
                  <div><span className="k">Current session</span><h2>{cur.name}</h2>
                    <small>{cur.start_date ? `${cur.start_date} – ${cur.end_date}${cur.dates_from_terms ? ' (from term dates)' : ''}` : 'No dates yet'}</small></div>
                  {canEdit && <button type="button" className="rs-btn ghost sm" onClick={() => setSheet({ edit: cur })}><i className="fas fa-pen" aria-hidden="true" /> Edit</button>}
                </div>
                {cur.progress != null && (
                  <div className="tm-prog"><div className="su-track"><i style={{ width: cur.progress + '%' }} /></div>
                    <span>{cur.state === 'running' ? `${cur.progress}% through the year · ${plural(cur.days_left, 'day')} left` : 'The school year has ended'}</span></div>)}
                <TermDots terms={cur.terms} />
                <div className="tm-stats ss-stats">
                  <span><b>{cur.terms.length}</b>terms</span><span><b>{cur.classes}</b>classes</span><span><b>{cur.students}</b>students</span>
                </div>
                <div className="tm-acts">
                  <A to={u.terms} className="rs-btn ghost sm"><i className="fas fa-calendar-week" aria-hidden="true" /> Terms</A>
                  <A to={u.setup} className="rs-btn ghost sm"><i className="fas fa-list-check" aria-hidden="true" /> Term setup</A>
                </div>
              </section>)}

            {d.next && canAdd && (
              <section className={'rs-card ss-next' + (d.next.urgent ? ' urgent' : '')}>
                <span className="ss-next-ic"><i className="fas fa-forward" aria-hidden="true" /></span>
                <span className="k">{d.next.urgent ? 'Time to plan next year' : 'Next school year'}</span>
                <h3>{d.next.name}</h3>
                <p>Create it with its three terms — this year’s term dates are moved on a year so you only fine-tune them.</p>
                <button type="button" className="rs-btn primary su-block" onClick={() => setSheet({ preset: d.next })}>
                  <i className="fas fa-plus" aria-hidden="true" /> Set up {d.next.name}</button>
                <div className="ss-next-l">
                  {u.promotion && <A to={u.promotion} className="cm-link">Promote students <i className="fas fa-arrow-right" aria-hidden="true" /></A>}
                  <A to={u.copy} className="cm-link">Copy class setup <i className="fas fa-arrow-right" aria-hidden="true" /></A>
                </div>
              </section>)}
          </div>

          {others.length > 0 && (
            <section className="rs-card ss-list">
              <div className="su-group-h"><h3><i className="fas fa-clock-rotate-left" aria-hidden="true" /> {cur ? 'Other sessions' : 'All sessions'}</h3>
                <span className="su-count">{others.length}</span></div>
              {others.map((s) => {
                const [tone, label] = STATE[s.state];
                return (
                  <div key={s.id} className="ss-row">
                    <div className="ss-row-t"><b>{s.name}</b>
                      <small>{s.start_date ? `${s.start_date} – ${s.end_date}` : 'No dates'}</small></div>
                    <Pill tone={tone}>{label}</Pill>
                    <TermDots terms={s.terms} />
                    <span className="ss-row-n"><b>{s.students}</b> students</span>
                    <div className="ss-row-a">
                      {canEdit && <Menu label={`More for ${s.name}`} items={[
                        { icon: 'fa-pen', label: 'Edit', onClick: () => setSheet({ edit: s }) },
                        { icon: 'fa-bolt', label: 'Make current', onClick: () => makeCurrent(s, notify) },
                      ]} />}
                    </div>
                  </div>);
              })}
            </section>)}
        </>
      )}
      {sheet && <SessionSheet d={d} edit={sheet.edit} preset={sheet.preset} notify={notify} onClose={() => setSheet(null)} />}
    </div>
  );
}
