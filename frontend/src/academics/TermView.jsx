// One term's calendar. Header with progress and a term switcher; every week
// is a row of Mon–Fri dots (register taken by all / some classes, missed,
// holiday, upcoming) so gaps in attendance jump out; holidays are grouped
// into breaks; dates, weeks and holidays are managed in sheets.
import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useNav } from '../lib/section';
import { confirm } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Sheet, Blank, Menu, Tiles } from '../subjects/results';
import { A, Field, Pill, plural } from '../components/appkit';
import { DatesSheet } from './TermSetup';

const DOT = {
  full: ['Register taken', 'fa-check'], part: ['Some classes took the register', 'fa-minus'],
  missed: ['No register taken', 'fa-xmark'], holiday: ['Holiday', 'fa-umbrella-beach'], future: ['Upcoming', ''],
};
const TYPES = ['Public Holiday', 'Mid-term Break', 'Other'];

function useAct(notify) {
  const nav = useNav();
  return async (url, fields, ask) => {
    if (ask && !await confirm(ask)) return false;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); return true; }
    notify('error', r.error || 'That didn’t work.'); return false;
  };
}

function HolidaySheet({ d, onClose, notify }) {
  const act = useAct(notify);
  const [f, setF] = useState({ date: '', end_date: '', holiday_type: 'Public Holiday', reason: '' });
  const [busy, setBusy] = useState(false);
  const days = (() => {
    if (!f.date) return 0;
    const a = new Date(f.date), b = new Date(f.end_date || f.date);
    let n = 0; for (let x = new Date(Math.min(a, b)); x <= Math.max(a, b); x.setDate(x.getDate() + 1)) if (x.getDay() % 6) n += 1;
    return n;
  })();
  const save = async () => {
    if (!f.date || !f.reason.trim()) { notify('error', 'Pick a date and say what it’s for.'); return; }
    setBusy(true); const ok = await act(d.urls.add_holiday, f); setBusy(false);
    if (ok) onClose();
  };
  return (
    <Sheet title="Add a holiday or break" onClose={onClose}>
      <div className="su-form">
        <div className="tm-pick" role="radiogroup" aria-label="Type">{TYPES.map((t) => (
          <button key={t} type="button" role="radio" aria-checked={f.holiday_type === t} className={f.holiday_type === t ? 'on' : ''}
                  onClick={() => setF({ ...f, holiday_type: t, reason: f.reason || (t === 'Mid-term Break' ? 'Mid-term break' : '') })}>
            <b>{t === 'Public Holiday' ? 'Public holiday' : t === 'Mid-term Break' ? 'Mid-term break' : 'Other'}</b>
            <small>{t === 'Mid-term Break' ? 'Usually a week' : t === 'Public Holiday' ? 'One or two days' : 'School closure'}</small></button>))}</div>
        <div className="cm-row2">
          <Field label="From" grow><input type="date" min={d.term.start_iso || undefined} max={d.term.end_iso || undefined} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          <Field label="To (optional)" grow><input type="date" min={f.date || undefined} max={d.term.end_iso || undefined} value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
        </div>
        <Field label="What for"><input type="text" placeholder="e.g. Independence Day" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
        <small className="cm-mute">{days ? `${plural(days, 'school day')} will be marked — weekends are skipped. Holidays don’t count as absences.` : 'Weekends are skipped automatically.'}</small>
        <div className="su-form-f">
          <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={save}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-plus')} aria-hidden="true" /> Add</button>
        </div>
      </div>
    </Sheet>
  );
}

export default function TermView({ d, notify }) {
  const nav = useNav();
  const act = useAct(notify);
  const [sheet, setSheet] = useState(null);
  const t = d.term, s = d.stats;
  const canEdit = canWrite(d, 'structure_edit');
  const canAddW = canWrite(d, 'structure_create');
  const canBulk = canWrite(d, 'structure_bulk');
  const canDelW = canWrite(d, 'structure_delete');
  const canHol = canWrite(d, 'holidays_create');
  const canHolDel = canWrite(d, 'holidays_delete');
  const cover = s.coverage;
  const mismatch = s.expected_weeks && s.weeks !== s.expected_weeks;
  const missed = d.weeks.flatMap((w) => w.days.filter((x) => x.status === 'missed'));
  const delWeek = (w) => act(w.delete_url, {}, {
    title: `Remove week ${w.week_number}?`, tone: 'danger', confirmText: 'Remove week',
    message: w.attendance ? `${plural(w.attendance, 'attendance record')} in this week will be deleted too. This can’t be undone.` : 'It has no attendance yet.' });
  const rebuild = () => act(d.urls.generate_weeks, {}, s.weeks ? {
    title: 'Rebuild weeks from the term dates?', confirmText: 'Rebuild',
    message: `Weeks will match ${t.start_date} – ${t.end_date}. Attendance already taken is kept and moved to the right week.` } : null);
  const removeBreak = (b) => act(d.urls.remove_holidays, { ids: b.ids.join(',') }, {
    title: `Remove ${b.reason}?`, confirmText: 'Remove', message: `${plural(b.days, 'day')} (${b.label}) will become school days again.` });
  return (
    <div className="rs cm su tm tv">
      <Head icon="fa-calendar-days" title={t.full_name} sub={t.start_date ? `${t.start_date} – ${t.end_date}` : 'Dates not set'}>
        <select className="cm-sel rs-hide-sm" value={t.id} aria-label="Term" onChange={(e) => nav.go(d.terms.find((x) => String(x.id) === e.target.value).url)}>
          {d.terms.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</select>
        {canEdit && <button type="button" className="rs-btn ghost" onClick={() => setSheet('dates')}><i className="fas fa-calendar-days" aria-hidden="true" /><span className="rs-hide-sm"> Dates</span></button>}
        <A to={d.urls.setup} className="rs-btn ghost"><i className="fas fa-list-check" aria-hidden="true" /><span className="rs-hide-sm"> Setup</span></A>
      </Head>

      <section className="rs-card tv-hero">
        <div className="tv-hero-t">
          {t.is_active ? <Pill tone="good" icon="fa-bolt">Active term</Pill> : <Pill>{{ running: 'In progress', upcoming: 'Upcoming', ended: 'Ended', nodates: 'No dates' }[t.state]}</Pill>}
          <b>{t.state === 'running' ? (s.current_week ? `Week ${s.current_week} of ${s.weeks}` : 'In session')
            : t.state === 'upcoming' ? `Starts in ${plural(t.days_to_start, 'day')}` : t.state === 'ended' ? 'Term has ended' : 'Set the dates to plan the term'}</b>
          {t.state === 'running' && <small>{plural(t.days_left, 'day')} left</small>}
          {t.state === 'nodates' && canEdit && <button type="button" className="rs-btn sm primary tv-hero-b" onClick={() => setSheet('dates')}>
            <i className="fas fa-calendar-days" aria-hidden="true" /> Set dates</button>}
        </div>
        {t.progress != null && <div className="su-track"><i style={{ width: t.progress + '%' }} /></div>}
      </section>

      <Tiles items={[
        { label: 'School days', value: s.school_days, sub: `${s.weeks} weeks · ${s.holiday_days} holiday days` },
        { label: 'Registers taken', value: cover == null ? '—' : cover, unit: cover == null ? '' : '%', tone: cover == null ? '' : cover >= 95 ? 'good' : cover >= 80 ? 'mid' : 'bad',
          sub: s.past_days ? `of class registers so far · ${plural(s.past_days - s.taken_days, 'day')} with none` : 'No school days yet' },
        { label: 'Classes with students', value: s.classes, sub: 'should take the register daily' },
      ]} />

      {(mismatch || missed.length > 0 || (!s.weeks && t.has_start)) && (
        <section className="rs-card rp-attn"><span className="k">Worth checking</span>
          <div className="tm-alerts">
            {!s.weeks && t.has_start && <div className="cm-attn-i mid"><i className="fas fa-table-columns" aria-hidden="true" /><span>No weeks yet — attendance can’t be taken.</span>
              {canBulk && <button type="button" className="rs-btn sm primary" onClick={rebuild}>Create weeks</button>}</div>}
            {mismatch && s.weeks > 0 && <div className="cm-attn-i info"><i className="fas fa-ruler-horizontal" aria-hidden="true" />
              <span>{plural(s.weeks, 'week')} set up, but the dates cover {s.expected_weeks}.</span>
              {canBulk && <button type="button" className="rs-btn sm primary" onClick={rebuild}>Rebuild weeks</button>}</div>}
            {missed.length > 0 && <div className="cm-attn-i mid"><i className="fas fa-user-clock" aria-hidden="true" />
              <span>No register on {plural(missed.length, 'school day')} (last: {missed[missed.length - 1].day} {missed[missed.length - 1].n}). If school was closed, mark it as a holiday.</span>
              {d.urls.attendance && <A to={d.urls.attendance} className="rs-btn sm ghost">Attendance</A>}</div>}
          </div>
        </section>)}

      <div className="tv-wrap">
        <section className="rs-card su-group tv-weeks">
          <div className="su-group-h"><h3><i className="fas fa-table-columns" aria-hidden="true" /> Weeks</h3>
            <div className="tv-legend" aria-hidden="true">{['full', 'part', 'missed', 'holiday'].map((k) => <span key={k}><i className={'tv-dot ' + k} />{DOT[k][0].replace('Some classes took the register', 'Partly')}</span>)}</div>
            {(canAddW || canBulk) && <Menu label="Week actions" items={[
              canAddW && { icon: 'fa-plus', label: 'Add the next week', onClick: () => act(d.urls.add_week, {}) },
              canBulk && t.has_start && { icon: 'fa-wand-magic-sparkles', label: s.weeks ? 'Rebuild from dates' : 'Create weeks from dates', onClick: rebuild },
            ]} />}
          </div>
          {d.weeks.length ? d.weeks.map((w) => (
            <div key={w.id} className={'tv-wk' + (w.current ? ' now' : '')}>
              <span className="tv-wk-n"><small>Wk</small>{w.week_number}</span>
              <span className="tv-wk-d">{w.label}{w.current && <Pill tone="info">This week</Pill>}</span>
              <div className="tv-days">{w.days.map((x) => (
                <span key={x.date} className={'tv-day ' + x.status}
                      title={`${x.day} ${x.n}: ${x.status === 'holiday' ? x.reason : x.status === 'part' ? `${plural(x.classes, 'class', 'classes')} of ${s.classes} took the register` : DOT[x.status][0]}`}>
                  <small>{x.day[0]}</small><b>{x.n}</b></span>))}</div>
              <div className="tv-wk-a">{canDelW && w.is_last && (
                <button type="button" className="cm-ib" onClick={() => delWeek(w)} aria-label={`Remove week ${w.week_number}`}><i className="fas fa-trash" aria-hidden="true" /></button>)}</div>
            </div>)) : (
            <Blank icon="fa-table-columns" title="No weeks yet">
              <p>{t.has_start ? 'Create the school weeks from the term dates in one go.' : 'Set the term dates first, then create the weeks.'}</p>
              {t.has_start ? canBulk && <button type="button" className="rs-btn primary" onClick={rebuild}><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Create weeks</button>
                : canEdit && <button type="button" className="rs-btn primary" onClick={() => setSheet('dates')}><i className="fas fa-calendar-days" aria-hidden="true" /> Set dates</button>}
            </Blank>)}
        </section>

        <section className="rs-card su-group tv-hols">
          <div className="su-group-h"><h3><i className="fas fa-umbrella-beach" aria-hidden="true" /> Holidays & breaks</h3>
            {canHol && <button type="button" className="rs-btn sm primary" onClick={() => setSheet('holiday')}><i className="fas fa-plus" aria-hidden="true" /> Add</button>}</div>
          {d.breaks.length ? d.breaks.map((b, i) => (
            <div key={i} className={'tv-brk' + (b.past ? ' past' : '')}>
              <span className="tv-brk-ic"><i className={'fas ' + (b.type === 'Mid-term Break' ? 'fa-mug-hot' : b.type === 'Public Holiday' ? 'fa-flag' : 'fa-door-closed')} aria-hidden="true" /></span>
              <span className="tv-brk-t"><b>{b.reason}</b><small>{b.label} · {plural(b.days, 'day')}</small></span>
              {canHolDel && <button type="button" className="cm-ib" onClick={() => removeBreak(b)} aria-label={`Remove ${b.reason}`}><i className="fas fa-xmark" aria-hidden="true" /></button>}
            </div>)) : <p className="cm-mute tv-empty">No holidays yet. Add public holidays and the mid-term break so they aren’t counted as absences.</p>}
        </section>
      </div>

      {sheet === 'dates' && <DatesSheet title={`${t.full_name} dates`} url={d.urls.edit} start={t.start_iso} end={t.end_iso}
                                        weeks={s.weeks} notify={notify} onClose={() => setSheet(null)} />}
      {sheet === 'holiday' && <HolidaySheet d={d} notify={notify} onClose={() => setSheet(null)} />}
    </div>
  );
}
