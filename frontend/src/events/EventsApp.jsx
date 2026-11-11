// Events & calendar — month calendar with a day panel, agenda, add/edit in a
// sheet, calendar-file import with review. Built on the results kit + app kit
// so it feels native on phones (day dots, bottom sheets, pinned actions) and
// on laptops (big month grid beside the selected day). Endpoints unchanged.
import React, { useState, useMemo, useRef } from 'react';
import { submitJson, postFile } from '../lib/forms';
import { useSection, NavCtx, useNav } from '../lib/section';
import { confirm, promptDialog, SectionShell, Toast } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Seg, Chips, Sheet, Menu, Blank, Bar, usePhone } from '../subjects/results';
import { A, SecNav, Field, Toggle, Pill, SearchBox, plural } from '../components/appkit';

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const CAT_IC = { Holiday: 'fa-umbrella-beach', Exam: 'fa-pen-to-square', Meeting: 'fa-people-group', Activity: 'fa-star', Sport: 'fa-futbol', General: 'fa-calendar-day' };
const fmtDay = (iso) => { const t = new Date(iso + 'T00:00:00'); return `${DOW[t.getDay()]}, ${t.getDate()} ${MONTHS[t.getMonth()].slice(0, 3)}`; };
const relDay = (iso, today) => {
  const diff = Math.round((new Date(iso + 'T00:00:00') - new Date(today + 'T00:00:00')) / 864e5);
  return diff === 0 ? 'Today' : diff === 1 ? 'Tomorrow' : diff > 1 && diff < 7 ? `In ${diff} days` : diff === -1 ? 'Yesterday' : '';
};

function ENav({ d, active }) {
  const u = d.urls || {};
  return <SecNav label="Events" active={active} items={[
    ['calendar', 'fa-calendar', 'Calendar', u.calendar || u.self],
    ['agenda', 'fa-list', 'Agenda', u.agenda],
    ['import', 'fa-file-import', 'Import', canWrite(d, 'import') ? u.import : null],
  ]} />;
}

// ---- event detail + form (sheets) -------------------------------------------
function EventDetail({ d, ev, onClose, onEdit, notify }) {
  const nav = useNav();
  const del = async () => {
    if (!await confirm({ title: 'Delete event?', message: `“${ev.title}” will be removed from the calendar.`, tone: 'danger', confirmText: 'Delete' })) return;
    const r = await submitJson(ev.delete_url, {});
    if (r.ok) { onClose(); notify('success', 'Event deleted.'); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  const dup = async () => {
    const day = await promptDialog({ title: 'Copy event', label: 'New start date', inputType: 'date', defaultValue: ev.start_date });
    if (!day) return;
    const r = await submitJson(ev.duplicate_url, { start_date: day });
    if (r.ok) { onClose(); notify('success', 'Event copied.'); nav.go(r.redirect); } else notify('error', r.error || 'Could not copy.');
  };
  return (
    <Sheet title="Event" onClose={onClose}>
      <div className="cm-sheet ev-detail" style={{ '--c': ev.color }}>
        <div className="ev-d-h"><span className="ev-ic"><i className={'fas ' + (CAT_IC[ev.category] || 'fa-calendar-day')} aria-hidden="true" /></span>
          <div><h3>{ev.title}</h3><Pill>{ev.category}</Pill></div></div>
        <ul className="ev-facts">
          <li><i className="fas fa-calendar" aria-hidden="true" /><span>{ev.date_label}{relDay(ev.start_date, d.today) && <em> · {relDay(ev.start_date, d.today)}</em>}</span></li>
          <li><i className="fas fa-clock" aria-hidden="true" /><span>{ev.time_label || 'All day'}</span></li>
          {ev.location && <li><i className="fas fa-location-dot" aria-hidden="true" /><span>{ev.location}</span></li>}
          <li><i className="fas fa-users" aria-hidden="true" /><span>For {ev.audience === 'All' ? 'everyone' : ev.audience.toLowerCase()}</span></li>
        </ul>
        {ev.description && <p className="ev-desc">{ev.description}</p>}
        {ev.created_by && <small className="cm-mute">Added by {ev.created_by}</small>}
        <div className="cm-sheet-f">
          {canWrite(d, 'delete') && <button type="button" className="rs-btn ghost danger" onClick={del}><i className="fas fa-trash" aria-hidden="true" /><span className="rs-hide-sm"> Delete</span></button>}
          {canWrite(d, 'create') && <button type="button" className="rs-btn ghost" onClick={dup}><i className="fas fa-copy" aria-hidden="true" /> Copy</button>}
          {canWrite(d, 'edit') && <button type="button" className="rs-btn primary" onClick={onEdit}><i className="fas fa-pen" aria-hidden="true" /> Edit</button>}
        </div>
      </div>
    </Sheet>
  );
}

function EventForm({ d, ev, preset, notify, onDone, onCancel, inSheet }) {
  const [f, setF] = useState({
    title: ev ? ev.title : '', category: ev ? ev.category : 'General', audience: ev ? ev.audience : 'All',
    start_date: ev ? ev.start_date : (preset || d.today), end_date: ev ? ev.end_date : '',
    all_day: ev ? !!ev.all_day : true, start_time: ev ? ev.start_time : '', end_time: ev ? ev.end_time : '',
    location: ev ? ev.location : '', term_id: ev && ev.term_id ? String(ev.term_id) : '', description: ev ? ev.description : '',
  });
  const [multi, setMulti] = useState(!!(ev && ev.end_date));
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Give the event a name.'); return; }
    if (!f.start_date) { notify('error', 'Pick a date.'); return; }
    setBusy(true);
    const r = await submitJson(ev ? ev.edit_url : d.add_url, { ...f, end_date: multi ? f.end_date : '', all_day: f.all_day ? 'on' : '' });
    setBusy(false);
    if (r.ok) onDone(r); else notify('error', r.error || 'Could not save the event.');
  };
  const colors = d.category_colors || {};
  return (
    <form className={inSheet ? 'cm-sheet' : 'cm-stack'} onSubmit={submit}>
      <Field label="Event"><input value={f.title} onChange={(e) => set('title', e.target.value)} placeholder="e.g. Inter-house sports" autoFocus={inSheet} /></Field>
      <div className="cm-f"><span>Type</span>
        <div className="ev-cats" role="radiogroup" aria-label="Type">{(d.categories || []).map((c) => (
          <button type="button" role="radio" aria-checked={f.category === c} key={c} className={f.category === c ? 'on' : ''}
                  style={{ '--c': colors[c] }} onClick={() => set('category', c)}>
            <i className={'fas ' + (CAT_IC[c] || 'fa-calendar-day')} aria-hidden="true" />{c}</button>))}</div></div>
      <div className="cm-row2">
        <Field label={multi ? 'Starts' : 'Date'} grow><input type="date" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></Field>
        {multi && <Field label="Ends" grow><input type="date" value={f.end_date} min={f.start_date} onChange={(e) => set('end_date', e.target.value)} /></Field>}
      </div>
      <div className="cm-toggles">
        <Toggle title="Runs over several days" sub="e.g. exams week, mid-term break" on={multi} onChange={setMulti} />
        <Toggle title="All day" on={f.all_day} onChange={(v) => set('all_day', v)} />
      </div>
      {!f.all_day && (
        <div className="cm-row2">
          <Field label="From" grow><input type="time" value={f.start_time} onChange={(e) => set('start_time', e.target.value)} /></Field>
          <Field label="To" grow><input type="time" value={f.end_time} onChange={(e) => set('end_time', e.target.value)} /></Field>
        </div>)}
      <div className="cm-row2">
        <Field label="Where" grow><input value={f.location} onChange={(e) => set('location', e.target.value)} placeholder="e.g. School field" /></Field>
        {(d.terms || []).length > 0 && (
          <Field label="Term" grow><select value={f.term_id} onChange={(e) => set('term_id', e.target.value)}>
            <option value="">—</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></Field>)}
      </div>
      <div className="cm-f"><span>Who it’s for</span>
        <Chips label="Audience" value={f.audience} onChange={(v) => set('audience', v)}
               items={(d.audiences || ['All']).map((x) => ({ value: x, label: x === 'All' ? 'Everyone' : x }))} /></div>
      <Field label="Details"><textarea rows={3} value={f.description} onChange={(e) => set('description', e.target.value)} placeholder="Anything people should know" /></Field>
      <div className="cm-sheet-f">
        <button type="button" className="rs-btn ghost" onClick={onCancel}>Cancel</button>
        <button className="rs-btn primary" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {ev ? 'Save changes' : 'Add event'}</button>
      </div>
    </form>
  );
}

// Detail + edit + new, shared by calendar and agenda.
function useEventSheets(d, notify) {
  const nav = useNav();
  const [view, setView] = useState(null);      // event being viewed
  const [edit, setEdit] = useState(null);      // {ev?, preset?}
  const sheets = (
    <>
      {view && <EventDetail d={d} ev={view} notify={notify} onClose={() => setView(null)} onEdit={() => { setEdit({ ev: view }); setView(null); }} />}
      {edit && (
        <Sheet title={edit.ev ? 'Edit event' : 'New event'} onClose={() => setEdit(null)}>
          <EventForm d={d} ev={edit.ev} preset={edit.preset} notify={notify} inSheet onCancel={() => setEdit(null)}
                     onDone={(r) => { setEdit(null); notify('success', r.message || 'Saved.'); nav.go(r.redirect || location.href); }} />
        </Sheet>)}
    </>
  );
  return { open: setView, add: (preset) => setEdit({ preset }), sheets };
}

function EvRow({ e, today, onOpen }) {
  const t = new Date(e.start_date + 'T00:00:00');
  const rel = relDay(e.start_date, today);
  return (
    <button type="button" className="ev-row" style={{ '--c': e.color }} onClick={() => onOpen(e)}>
      <span className="ev-tile"><small>{DOW[t.getDay()]}</small><b>{t.getDate()}</b><small>{MONTHS[t.getMonth()].slice(0, 3)}</small></span>
      <span className="ev-row-t"><b>{e.title}</b>
        <small>{[rel, e.end_date && e.end_date !== e.start_date ? `until ${fmtDay(e.end_date)}` : '', e.time_label || 'All day', e.location].filter(Boolean).join(' · ')}</small></span>
      <span className="ev-cat"><i className={'fas ' + (CAT_IC[e.category] || 'fa-calendar-day')} aria-hidden="true" />{e.category}</span>
    </button>
  );
}

// ============================================================================
// Calendar
// ============================================================================
function Calendar({ d, notify }) {
  const phone = usePhone();
  const { open, add, sheets } = useEventSheets(d, notify);
  const [cat, setCat] = useState('');
  const todayCell = d.weeks.flat().find((x) => x.is_today);
  const [sel, setSel] = useState(todayCell ? todayCell.iso : (d.weeks.flat().find((x) => x.in_month) || {}).iso);
  const days = d.weeks.flat();
  const show = (evs) => evs.filter((e) => !cat || e.category === cat);
  const selDay = days.find((x) => x.iso === sel);
  const monthEvents = useMemo(() => {
    const seen = new Map();
    days.filter((x) => x.in_month).forEach((x) => x.events.forEach((e) => seen.set(e.id, e)));
    return [...seen.values()];
  }, [d.weeks]); // eslint-disable-line react-hooks/exhaustive-deps
  const cats = d.categories.filter((c) => monthEvents.some((e) => e.category === c));
  const shownIds = new Set(selDay ? selDay.events.map((e) => e.id) : []);
  const upcoming = show(d.upcoming || []).filter((e) => !shownIds.has(e.id));
  const canAdd = canWrite(d, 'create');
  const maxPills = phone ? 0 : 3;

  return (
    <div className="rs cm ev">
      <ENav d={d} active="calendar" />
      <Head icon="fa-calendar" title="Calendar" sub={`${plural(monthEvents.length, 'event')} in ${d.month_name}`}>
        {canAdd && <button type="button" className="rs-btn primary" onClick={() => add(sel)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> New event</span></button>}
        <Menu items={[
          { icon: 'fa-list', label: 'Agenda list', href: d.urls.agenda },
          canWrite(d, 'import') && { icon: 'fa-file-import', label: 'Import a calendar file', href: d.urls.import },
          d.ics_url && { icon: 'fa-calendar-plus', label: 'Add to my phone / Google calendar', href: d.ics_url, native: true, download: true },
        ]} />
      </Head>

      <div className="ev-layout">
        <section className="rs-card ev-month">
          <div className="ev-mh">
            <A to={d.nav.prev_url} className="cm-ib" aria-label="Previous month"><i className="fas fa-chevron-left" aria-hidden="true" /></A>
            <h2>{d.month_name} <span>{d.year}</span></h2>
            <A to={d.nav.next_url} className="cm-ib" aria-label="Next month"><i className="fas fa-chevron-right" aria-hidden="true" /></A>
            {!(todayCell) && <A to={d.nav.today_url} className="rs-btn ghost sm ev-today">Today</A>}
          </div>
          {cats.length > 1 && (
            <div className="ev-filter"><Chips label="Type" value={cat} onChange={setCat}
              items={[{ value: '', label: 'All' }, ...cats.map((c) => ({ value: c, label: c }))]} /></div>)}
          <div className="ev-grid" role="grid" aria-label={`${d.month_name} ${d.year}`}>
            {DOW.map((x) => <div className="ev-dow" key={x} role="columnheader">{phone ? x[0] : x}</div>)}
            {days.map((day) => {
              const evs = show(day.events);
              return (
                <div key={day.iso} role="gridcell" tabIndex={0} aria-selected={sel === day.iso}
                     className={'ev-cell' + (day.in_month ? '' : ' out') + (day.is_today ? ' today' : '') + (sel === day.iso ? ' sel' : '')}
                     onClick={() => setSel(day.iso)} onDoubleClick={() => canAdd && add(day.iso)}
                     onKeyDown={(e) => { if (e.key === 'Enter') setSel(day.iso); }}>
                  <span className="ev-n">{day.day}</span>
                  {maxPills > 0 ? (
                    <>
                      {evs.slice(0, maxPills).map((e) => (
                        <button type="button" key={e.id} className="ev-pill" style={{ '--c': e.color }} title={e.title}
                                onClick={(x) => { x.stopPropagation(); open(e); }}>
                          {e.start_time && !e.all_day && <em>{e.start_time}</em>}{e.title}</button>))}
                      {evs.length > maxPills && <span className="ev-more">+{evs.length - maxPills} more</span>}
                    </>
                  ) : evs.length > 0 && <span className="ev-dots">{evs.slice(0, 3).map((e) => <i key={e.id} style={{ background: e.color }} />)}</span>}
                </div>);
            })}
          </div>
        </section>

        <aside className="ev-side">
          <section className="rs-card">
            <div className="rs-card-h"><h3>{selDay ? (selDay.is_today ? 'Today' : fmtDay(selDay.iso)) : 'Pick a day'}</h3>
              {canAdd && selDay && <button type="button" className="cm-ib" onClick={() => add(selDay.iso)} aria-label="Add an event on this day"><i className="fas fa-plus" aria-hidden="true" /></button>}</div>
            {selDay && show(selDay.events).length ? (
              <div className="ev-list">{show(selDay.events).map((e) => <EvRow key={e.id} e={e} today={d.today} onOpen={open} />)}</div>
            ) : <p className="cm-mute ev-none">Nothing on this day.{canAdd && <> <button type="button" className="cm-link-b" onClick={() => add(sel)}>Add an event</button></>}</p>}
          </section>
          <section className="rs-card">
            <div className="rs-card-h"><h3><i className="fas fa-forward" aria-hidden="true" /> Coming up</h3><A to={d.urls.agenda} className="cm-link">All</A></div>
            {upcoming.length ? <div className="ev-list">{upcoming.map((e) => <EvRow key={e.id} e={e} today={d.today} onOpen={open} />)}</div>
              : <p className="cm-mute ev-none">No upcoming events.</p>}
          </section>
          <div className="ev-legend">{d.categories.map((c) => <span key={c}><i style={{ background: d.category_colors[c] }} />{c}</span>)}</div>
        </aside>
      </div>
      {sheets}
    </div>
  );
}

// ============================================================================
// Agenda
// ============================================================================
function Agenda({ d, notify }) {
  const nav = useNav();
  const { open, add, sheets } = useEventSheets(d, notify);
  const [q, setQ] = useState('');
  const go = (params) => nav.go(d.urls.self + '?' + new URLSearchParams(params).toString());
  const list = d.events.filter((e) => !q || (e.title + ' ' + e.location + ' ' + e.description).toLowerCase().includes(q.toLowerCase()));
  const groups = useMemo(() => {
    const g = [];
    list.forEach((e) => {
      const t = new Date(e.start_date + 'T00:00:00'); const k = `${MONTHS[t.getMonth()]} ${t.getFullYear()}`;
      if (!g.length || g[g.length - 1].k !== k) g.push({ k, items: [] });
      g[g.length - 1].items.push(e);
    });
    return g;
  }, [list]);
  return (
    <div className="rs cm ev">
      <ENav d={d} active="agenda" />
      <Head icon="fa-list" title="Agenda" sub={d.upcoming === '1' ? 'Everything coming up' : 'All events'}>
        {canWrite(d, 'create') && <button type="button" className="rs-btn primary" onClick={() => add()}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> New event</span></button>}
        {d.ics_url && <Menu items={[{ icon: 'fa-calendar-plus', label: 'Add to my phone / Google calendar', href: d.ics_url, native: true, download: true }]} />}
      </Head>
      <div className="cm-filters">
        <SearchBox value={q} onChange={setQ} placeholder="Search events" />
        <Seg label="Show" value={d.upcoming} onChange={(v) => go({ category: d.category, upcoming: v })}
             options={[{ value: '1', label: 'Upcoming' }, { value: '0', label: 'All' }]} />
      </div>
      <Chips label="Type" value={d.category} onChange={(v) => go({ category: v, upcoming: d.upcoming })}
             items={[{ value: '', label: 'All types' }, ...d.categories.map((c) => ({ value: c, label: c }))]} />
      {groups.length ? groups.map((g) => (
        <section className="rs-card" key={g.k}>
          <div className="rs-card-h"><h3>{g.k}</h3><small>{plural(g.items.length, 'event')}</small></div>
          <div className="ev-list">{g.items.map((e) => <EvRow key={e.id} e={e} today={d.today} onOpen={open} />)}</div>
        </section>
      )) : (
        <Blank icon="fa-calendar-day" title={q ? 'No events match' : 'No events here'}>
          <p>Add holidays, exams, meetings and activities so everyone knows what’s coming.</p>
          {canWrite(d, 'create') && <button type="button" className="rs-btn primary" onClick={() => add()}><i className="fas fa-plus" aria-hidden="true" /> New event</button>}
        </Blank>)}
      {sheets}
    </div>
  );
}

// ============================================================================
// Add / edit page (direct links)
// ============================================================================
function EventPage({ d, notify }) {
  const nav = useNav();
  const ev = d.event ? { ...d.event, edit_url: d.submit_url } : null;
  const del = async () => {
    if (!await confirm({ title: 'Delete event?', message: 'It will be removed from the calendar.', tone: 'danger', confirmText: 'Delete' })) return;
    const r = await submitJson(d.delete_url, {});
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not delete.');
  };
  return (
    <div className="rs cm ev">
      <ENav d={d} active="calendar" />
      <Head icon={ev ? 'fa-pen' : 'fa-calendar-plus'} title={ev ? 'Edit event' : 'New event'}>
        {ev && canWrite(d, 'delete') && <button type="button" className="rs-btn ghost danger" onClick={del}><i className="fas fa-trash" aria-hidden="true" /> Delete</button>}
      </Head>
      <section className="rs-card ev-formcard">
        <EventForm d={{ ...d, add_url: d.submit_url }} ev={ev} preset={d.preset} notify={notify}
                   onCancel={() => nav.go(d.urls.calendar)} onDone={(r) => nav.go(r.redirect)} />
      </section>
    </div>
  );
}

// ============================================================================
// Import
// ============================================================================
function Import({ d, notify }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [review, setReview] = useState(null);
  const [drag, setDrag] = useState(false);
  const ref = useRef();
  const scan = async (f) => {
    const fl = f || file;
    if (!fl) { notify('error', 'Choose a file to scan.'); return; }
    setBusy(true);
    const r = await postFile(d.upload_url, fl);
    setBusy(false);
    if (r.ok) setReview({ rows: r.rows.map((x) => ({ ...x, include: true })), terms: r.terms, categories: r.categories, save_url: r.save_url });
    else notify('error', r.error || 'Could not read that file.');
  };
  const pick = (fl) => { if (fl) { setFile(fl); scan(fl); } };
  if (review) return <ImportReview review={review} setReview={setReview} d={d} notify={notify} />;
  return (
    <div className="rs cm ev">
      <ENav d={d} active="import" />
      <Head icon="fa-file-import" title="Import a calendar" sub="Turn the school’s term calendar into events — no typing." />
      <section className={'rs-card ev-drop' + (drag ? ' drag' : '')}
               onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
               onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}>
        <span className="ev-drop-ic"><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles')} aria-hidden="true" /></span>
        <h3>{busy ? `Reading ${file ? file.name : 'the file'}…` : 'Drop the calendar here'}</h3>
        <p>A Word document (.docx), a PDF, or a clear photo of the printed calendar. You’ll check every date before anything is added.</p>
        <button type="button" className="rs-btn primary" disabled={busy} onClick={() => ref.current && ref.current.click()}>
          <i className="fas fa-folder-open" aria-hidden="true" /> Choose a file</button>
        <input ref={ref} type="file" hidden accept=".docx,image/*,.pdf" onChange={(e) => pick(e.target.files[0])} />
        <small className="cm-mute">Best results: a Word table of Week / Activity / Dates, or a straight, well-lit photo.</small>
      </section>
    </div>
  );
}

function ImportReview({ review, setReview, d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const [termId, setTermId] = useState('');
  const rows = review.rows;
  const setRow = (i, k, v) => setReview((r) => ({ ...r, rows: r.rows.map((row, j) => (j === i ? { ...row, [k]: v } : row)) }));
  const selAll = (v) => setReview((r) => ({ ...r, rows: r.rows.map((row) => ({ ...row, include: v })) }));
  const n = rows.filter((r) => r.include).length;
  const save = async () => {
    setBusy(true);
    const fields = { row_count: rows.length, term_id: termId };
    rows.forEach((r, i) => {
      if (r.include) fields[`include_${i}`] = '1';
      fields[`title_${i}`] = r.title; fields[`start_${i}`] = r.start_date;
      fields[`end_${i}`] = r.end_date; fields[`category_${i}`] = r.category;
    });
    const res = await submitJson(review.save_url, fields);
    setBusy(false);
    if (res.ok) nav.go(res.redirect); else notify('error', res.error || 'Could not import.');
  };
  return (
    <div className="rs cm ev">
      <ENav d={d} active="import" />
      <Head icon="fa-list-check" title="Check the events" sub={`${plural(rows.length, 'activity', 'activities')} found — fix anything wrong, untick what you don’t want.`}>
        <button type="button" className="rs-btn ghost" onClick={() => setReview(null)}><i className="fas fa-rotate-left" aria-hidden="true" /> Scan another</button>
      </Head>
      <div className="cm-filters">
        <button type="button" className="rs-btn ghost sm" onClick={() => selAll(n < rows.length)}>{n < rows.length ? 'Tick all' : 'Untick all'}</button>
        <label className="ev-term"><span>Add to term</span>
          <select className="cm-sel" value={termId} onChange={(e) => setTermId(e.target.value)}>
            <option value="">No term</option>{review.terms.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></label>
      </div>
      <section className="rs-card">
        <div className="ev-rv">{rows.map((r, i) => (
          <div key={i} className={'ev-rv-r' + (r.include ? '' : ' off')} style={{ '--c': (d.category_colors || {})[r.category] }}>
            <input type="checkbox" checked={r.include} onChange={(e) => setRow(i, 'include', e.target.checked)} aria-label={'Include ' + r.title} />
            <input className="ev-rv-t" value={r.title} onChange={(e) => setRow(i, 'title', e.target.value)} aria-label="Activity" />
            <input type="date" value={r.start_date} onChange={(e) => setRow(i, 'start_date', e.target.value)} aria-label="Start" />
            <input type="date" value={r.end_date} onChange={(e) => setRow(i, 'end_date', e.target.value)} aria-label="End" />
            <select value={r.category} onChange={(e) => setRow(i, 'category', e.target.value)} aria-label="Type">
              {review.categories.map((c) => <option key={c}>{c}</option>)}</select>
          </div>))}</div>
      </section>
      <Bar>
        <span className="rs-bar-t"><b>{plural(n, 'event')} ticked</b><small>of {rows.length} found</small></span>
        <button type="button" className="rs-btn primary" disabled={busy || !n} onClick={save}>
          <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-calendar-plus')} aria-hidden="true" /> Add to calendar</button>
      </Bar>
    </div>
  );
}

const SCREENS = { calendar: Calendar, agenda: Agenda, event_form: EventPage, import: Import };

export default function EventsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [toast, setToast] = useState(null);
  const notify = (tone, text) => setToast({ tone, text, at: Date.now() });
  const Screen = SCREENS[d.page] || Calendar;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        <Screen d={d} notify={notify} />
        {toast && <Toast key={toast.at} tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}
      </SectionShell>
    </NavCtx.Provider>
  );
}
