import React, { useState } from 'react';
import { submitJson, useSave } from '../lib/forms';
import { useSection, NavCtx, useNav } from '../lib/section';
import { confirm, Banner, SectionShell, Empty, TableWrap } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Menu, Blank, usePhone } from '../subjects/results';
import { SecNav, Pill, plural } from '../components/appkit';
import { navParams } from '../lib/section';

const A = ({ to, className, children, title, target }) => {
  const nav = useNav();
  if (target === '_blank') return <a href={to} target="_blank" rel="noopener" className={className} title={title}>{children}</a>;
  return <a href={to} className={className} title={title}
    onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};

// ---- Shared timetable pieces ------------------------------------------------
const HUES = ['#0f766e', '#2563eb', '#7c3aed', '#db2777', '#d97706', '#059669', '#4f46e5', '#0891b2', '#b45309', '#be123c', '#4d7c0f', '#6d28d9'];
const hueOf = (id) => HUES[Math.abs(Number(id) || 0) % HUES.length];
const SHORT = { 0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri' };
const nowSlot = (slots, clock) => slots.find((s) => s.m0 != null && clock.minutes >= s.m0 && clock.minutes < s.m1);
const nextSlot = (slots, clock) => slots.find((s) => s.m0 != null && s.m0 > clock.minutes && !s.is_break);
const isSchoolDay = (clock) => clock.weekday <= 4;

// Week grid (laptop): coloured cells, today's column and the current period lit.
function WeekGrid({ d, cell, label }) {
  const today = isSchoolDay(d.clock) ? d.clock.weekday : -1;
  const cur = today >= 0 ? nowSlot(d.slots, d.clock) : null;
  return (
    <div className="tt-wk" role="table" aria-label={label} style={{ '--days': d.days.length }}>
      <div className="tt-wk-h" role="row"><span role="columnheader" />
        {d.days.map(([n, name]) => <span key={n} role="columnheader" className={n === today ? 'today' : ''}>{name}{n === today && <em>Today</em>}</span>)}</div>
      {d.slots.map((s) => (
        <div key={s.id} role="row" className={'tt-wk-r' + (s.is_break ? ' brk' : '') + (cur && cur.id === s.id ? ' now' : '')}>
          <span role="rowheader" className="tt-time"><b>{s.name}</b><small>{s.start}–{s.end}</small></span>
          {s.is_break ? <span className="tt-brk" role="cell" style={{ gridColumn: `span ${d.days.length}` }}><i className="fas fa-mug-hot" aria-hidden="true" /> {s.name || 'Break'}</span>
            : d.days.map(([n]) => {
              const e = d.grid[`${n}_${s.id}`];
              return (
                <span key={n} role="cell" className={'tt-c' + (e ? '' : ' free') + (n === today ? ' today' : '') + (cur && cur.id === s.id && n === today ? ' live' : '')}
                      style={e ? { '--c': hueOf(e.sid) } : undefined} title={e ? e.name : 'Free'}>
                  {e ? cell(e) : <small>—</small>}</span>);
            })}
        </div>))}
    </div>
  );
}

// Day agenda (phone): day tabs, periods as a list, Now / Next markers.
function DayAgenda({ d, cell }) {
  const today = isSchoolDay(d.clock) ? d.clock.weekday : 0;
  const [day, setDay] = useState(today);
  const isToday = isSchoolDay(d.clock) && day === d.clock.weekday;
  const cur = isToday ? nowSlot(d.slots, d.clock) : null;
  const nxt = isToday ? nextSlot(d.slots, d.clock) : null;
  return (
    <div className="tt-ag">
      <div className="tt-days" role="tablist" aria-label="Day">{d.days.map(([n, name]) => {
        const c = d.slots.filter((s) => d.grid[`${n}_${s.id}`]).length;
        return (
          <button key={n} type="button" role="tab" aria-selected={day === n} className={(day === n ? 'on' : '') + (isSchoolDay(d.clock) && n === d.clock.weekday ? ' today' : '')} onClick={() => setDay(n)}>
            <b>{SHORT[n] || name.slice(0, 3)}</b><small>{c}</small></button>);
      })}</div>
      <div className="rs-card tt-list">{d.slots.map((s) => {
        if (s.is_break) return <div key={s.id} className="tt-li brk"><span className="tt-li-t">{s.start}</span><span><i className="fas fa-mug-hot" aria-hidden="true" /> {s.name || 'Break'}</span></div>;
        const e = d.grid[`${day}_${s.id}`];
        const tag = cur && cur.id === s.id ? 'Now' : nxt && nxt.id === s.id ? 'Next' : null;
        return (
          <div key={s.id} className={'tt-li' + (e ? '' : ' free') + (tag === 'Now' ? ' live' : '')} style={e ? { '--c': hueOf(e.sid) } : undefined}>
            <span className="tt-li-t"><b>{s.start}</b><small>{s.end}</small></span>
            <span className="tt-li-b">{e ? cell(e) : <small className="cm-mute">Free</small>}</span>
            {tag && <Pill tone={tag === 'Now' ? 'good' : 'info'}>{tag}</Pill>}
          </div>);
      })}</div>
    </div>
  );
}

// ---- Class timetable ------------------------------------------------------------
function Index({ d }) {
  const nav = useNav();
  const phone = usePhone();
  const go = (term, assignment) => navParams(nav.go, d.urls.self, { term_id: term, assignment_id: assignment });
  const sel = d.selected_assignment;
  const st = d.stats || {};
  const missing = (d.legend || []).filter((l) => !l.periods);
  const maxP = Math.max(1, ...(d.legend || []).map((l) => l.periods));
  const cell = (e) => <><b>{e.subject}</b>{e.teacher && <small>{e.teacher}</small>}</>;
  return (
    <div className="rs cm tt">
      <SecNav label="Timetable" active="index" items={[
        ['index', 'fa-table-cells', 'Class timetable', d.urls.self], ['mine', 'fa-user-clock', 'My timetable', d.mine_url],
        ['designer', 'fa-wand-magic-sparkles', 'Generator', d.urls.designer], ['backups', 'fa-clock-rotate-left', 'Backups', d.urls.backups]]} />
      <Head icon="fa-table-cells" title={sel ? sel.display_name : 'Class timetable'} sub={sel ? `${st.periods} of ${st.slots} periods filled · ${plural(st.teachers || 0, 'teacher')}` : 'Pick a class to see its week.'}>
        <select className="cm-sel" value={d.term_id || ''} aria-label="Term" onChange={(e) => go(e.target.value, '')}>
          <option value="">Term…</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select>
        {sel && <Menu label="Timetable actions" items={[
          canWrite(d, 'class_edit') && { icon: 'fa-pen', label: 'Edit this timetable', onClick: () => nav.go(d.urls.edit) },
          { icon: 'fa-file-pdf', label: 'Download PDF', href: d.urls.pdf, native: true, target: '_blank' },
          { icon: 'fa-file-pdf', label: 'PDF with teachers', href: d.urls.pdf_teachers, native: true, target: '_blank' },
        ]} />}
      </Head>
      {d.assignments.length > 0 && (
        <div className="tt-cls" role="tablist" aria-label="Class">{d.assignments.map((a) => (
          <button key={a.id} type="button" role="tab" aria-selected={String(a.id) === String(d.assignment_id)}
                  className={String(a.id) === String(d.assignment_id) ? 'on' : ''} onClick={() => go(d.term_id, a.id)}>{a.display_name}</button>))}</div>)}
      {!sel ? (
        <Blank icon={d.has_term ? 'fa-hand-pointer' : 'fa-calendar'} title={d.has_term ? (d.assignments.length ? 'Pick a class' : 'No classes this term') : 'Pick a term'}>
          {d.has_term && !d.assignments.length && <p>Open classes in Class setup first.</p>}</Blank>
      ) : (
        <div className="tt-wrap">
          <section className="rs-card tt-main">{phone ? <DayAgenda d={d} cell={cell} /> : <WeekGrid d={d} cell={cell} label={`${sel.display_name} timetable`} />}</section>
          <aside className="tt-side">
            {!d.legend.length && (
              <section className="rs-card rp-attn"><span className="k">Worth checking</span>
                <div className="tm-alerts"><div className="cm-attn-i mid"><i className="fas fa-book" aria-hidden="true" /><span>{sel.display_name} has no subjects set for this term, so there is nothing to timetable yet.</span></div></div>
                {d.urls.class_subjects && <A to={d.urls.class_subjects} className="rs-btn ghost sm">Set class subjects</A>}
              </section>)}
            {d.legend.length > 0 && (st.slots - st.periods > 0 || missing.length > 0) && (
              <section className="rs-card rp-attn"><span className="k">Worth checking</span>
                <div className="tm-alerts">
                  {st.slots - st.periods > 0 && <div className="cm-attn-i info"><i className="fas fa-square" aria-hidden="true" /><span>{plural(st.slots - st.periods, 'free period')} in the week.</span></div>}
                  {missing.length > 0 && <div className="cm-attn-i mid"><i className="fas fa-book" aria-hidden="true" /><span>No periods for {missing.slice(0, 3).map((m) => m.name).join(', ')}{missing.length > 3 ? ` +${missing.length - 3}` : ''}.</span></div>}
                </div>
                {canWrite(d, 'class_edit') && <A to={d.urls.edit} className="rs-btn ghost sm">Edit timetable</A>}
              </section>)}
            {d.legend.length > 0 && (
              <section className="rs-card tt-load">
                <div className="rs-card-h"><h3><i className="fas fa-chart-simple" aria-hidden="true" /> Periods per week</h3></div>
                {d.legend.map((l) => (
                  <div key={l.sid} className={'tt-ld' + (l.periods ? '' : ' none')} style={{ '--c': hueOf(l.sid) }}>
                    <span className="tt-sw" aria-hidden="true" /><span className="tt-ld-t"><b>{l.name}</b>{l.teacher && <small>{l.teacher}</small>}</span>
                    <span className="tt-ld-b"><i style={{ width: l.periods / maxP * 100 + '%' }} /></span><b className="tt-ld-n">{l.periods}</b>
                  </div>))}
              </section>)}
          </aside>
        </div>)}
    </div>
  );
}

// ---- My timetable -------------------------------------------------------------
function Mine({ d }) {
  const nav = useNav();
  const phone = usePhone();
  const today = isSchoolDay(d.clock) ? d.clock.weekday : -1;
  const todays = today >= 0 ? d.slots.filter((s) => d.grid[`${today}_${s.id}`]) : [];
  const cur = today >= 0 ? nowSlot(d.slots, d.clock) : null;
  const curE = cur && d.grid[`${today}_${cur.id}`];
  const nxt = todays.find((s) => s.m0 > d.clock.minutes);
  const nxtE = nxt && d.grid[`${today}_${nxt.id}`];
  const mins = nxt ? nxt.m0 - d.clock.minutes : 0;
  const cell = (e) => <><b>{e.subject}</b><small>{e.klass}</small></>;
  const maxD = Math.max(1, ...Object.values(d.by_day || {}));
  return (
    <div className="rs cm tt">
      <SecNav label="Timetable" active="mine" items={[
        ['index', 'fa-table-cells', 'Class timetable', d.urls.class_view], ['mine', 'fa-user-clock', 'My timetable', d.urls.self]]} />
      <Head icon="fa-user-clock" title="My timetable" sub={d.teacher_name ? `${d.teacher_name} · ${plural(d.period_count, 'period')} a week` : ''}>
        <select className="cm-sel" value={d.term_id || ''} aria-label="Term" onChange={(e) => navParams(nav.go, d.urls.self, { term_id: e.target.value })}>
          {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select>
      </Head>
      {!d.period_count ? (
        <Blank icon="fa-calendar-xmark" title="Nothing on your timetable"><p>{d.empty_message}</p>
          <A to={d.urls.class_view} className="rs-btn ghost">See class timetables</A></Blank>
      ) : (<>
        <div className="tt-top">
          <section className={'rs-card tt-next' + (curE ? ' live' : '')}>
            {curE ? <><span className="k">Teaching now · until {cur.end}</span><h2>{curE.name}</h2><p>{curE.klass}</p></>
              : nxtE ? <><span className="k">Next · {nxt.start}{mins > 0 ? ` (in ${mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins} min`})` : ''}</span><h2>{nxtE.name}</h2><p>{nxtE.klass}</p></>
                : <><span className="k">{today >= 0 ? 'Today' : 'Weekend'}</span><h2>{today >= 0 ? (todays.length ? 'Done for today' : 'No lessons today') : 'Enjoy the weekend'}</h2>
                  <p>{today >= 0 ? `${plural(todays.length, 'lesson')} today` : ''}</p></>}
          </section>
          <section className="rs-card tt-days-load">
            <span className="k">Lessons per day</span>
            <div className="tt-dl">{d.days.map(([n, name]) => {
              const c = (d.by_day || {})[n] || 0;
              return <span key={n} className={n === today ? 'today' : ''}><i style={{ height: Math.max(6, c / maxD * 100) + '%' }} /><b>{c}</b><small>{SHORT[n] || name.slice(0, 3)}</small></span>;
            })}</div>
          </section>
          <section className="rs-card tt-mycls">
            <span className="k">Classes I teach</span>
            <div className="st-chips">{d.classes.map((c) => <span key={c} className="st-chip idle">{c}</span>)}</div>
          </section>
        </div>
        <section className="rs-card tt-main">{phone ? <DayAgenda d={d} cell={cell} /> : <WeekGrid d={d} cell={cell} label="My timetable" />}</section>
      </>)}
    </div>
  );
}

// ---- Edit grid --------------------------------------------------------------
function Edit({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [cells, setCells] = useState(() => {
    const m = {};
    Object.entries(d.entries).forEach(([k, v]) => { m[k] = { subject_id: String(v.subject_id || ''), teacher: v.teacher || '' }; });
    return m;
  });
  const get = (k) => cells[k] || { subject_id: '', teacher: '' };
  const set = (k, field, val) => setCells((c) => ({ ...c, [k]: { ...get(k), [field]: val } }));
  const submit = (e) => {
    e.preventDefault();
    const fields = {};
    d.days.forEach(([day]) => d.slots.forEach((s) => {
      if (s.is_break) return;
      const k = `${day}_${s.id}`;
      const c = get(k);
      fields[`entry_${day}_${s.id}`] = c.subject_id || '';
      fields[`teacher_${day}_${s.id}`] = c.teacher || '';
    }));
    save(d.save_url, fields, (r) => nav.go(r.redirect || d.cancel_url));
  };
  return (
    <>
      <div className="page-header"><h1>Edit: {d.assignment.display_name}</h1></div>
      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        <form onSubmit={submit}>
          <table className="data-table" style={{ minWidth: '100%' }}>
            <thead><tr><th style={{ width: 100 }}>Time</th>
              {d.days.map(([n, name]) => <th key={n} style={{ textAlign: 'center', minWidth: 150 }}>{name}</th>)}</tr></thead>
            <tbody>
              {d.slots.map((s) => (
                <tr key={s.id} className={s.is_break ? 'table-info' : ''}>
                  <td style={{ fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}><strong>{s.name}</strong><br />{s.start} - {s.end}</td>
                  {d.days.map(([day]) => {
                    if (s.is_break) return <td key={day} style={{ textAlign: 'center', padding: '0.5rem' }}><em className="text-muted">Break</em></td>;
                    const k = `${day}_${s.id}`;
                    const c = get(k);
                    return (
                      <td key={day} style={{ textAlign: 'center', padding: '0.5rem' }}>
                        <select className="form-control" style={{ fontSize: 'var(--text-sm)', padding: '0.25rem' }}
                          value={c.subject_id} onChange={(e) => set(k, 'subject_id', e.target.value)}>
                          <option value="">-</option>
                          {d.subjects.map((su) => <option key={su.subject_id} value={su.subject_id}>{su.label}</option>)}
                        </select>
                        <input type="text" className="form-control mt-1" placeholder="Teacher"
                          style={{ fontSize: 'var(--text-xs)', padding: '0.25rem' }}
                          value={c.teacher} onChange={(e) => set(k, 'teacher', e.target.value)} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="card-body"><div className="page-header-actions">
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Timetable</button>
            <A to={d.cancel_url} className="btn btn-secondary">Cancel</A>
          </div></div>
        </form>
      </div></div>
    </>
  );
}

// ---- Backups ----------------------------------------------------------------
function Backups({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [label, setLabel] = useState('');
  const create = (e) => {
    e.preventDefault();
    save(d.create_url, { term_id: d.term_id || '', label }, () => { setLabel(''); nav.refresh(); });
  };
  const restore = async (b) => {
    if (await confirm('Restore this backup? Your current timetable for this term will be backed up first, then replaced with this one.')) save(b.restore_url, {}, () => nav.refresh());
  };
  const del = async (b) => {
    if (await confirm('Delete this backup permanently?')) save(b.delete_url, {}, () => nav.refresh());
  };
  const onTerm = (e) => nav.go(`${d.self_url}?term_id=${e.target.value}`);
  return (
    <>
      <div className="page-header">
        <div>
          <h1><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Timetable Backups &amp; Restore</h1>
          <p className="text-muted text-sm">A snapshot is saved automatically each time a generated timetable is applied. Restore one to bring back a previous timetable.</p>
        </div>
        {d.terms.length > 0 && (
          <div className="filter-form">
            <select className="form-control" value={d.term_id || ''} onChange={onTerm}>
              {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
            </select>
          </div>
        )}
      </div>
      <div className="card mb-3"><div className="card-body">
        <form onSubmit={create} className="filter-form" style={{ gap: '.5rem', alignItems: 'end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: 1, minWidth: 220, margin: 0 }}>
            <label className="form-label">Back up the current timetable now</label>
            <input className="form-control" placeholder="Label (e.g. 'Working timetable — Term 1')" value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          {canWrite(d, 'backups_create') && <button type="submit" className="btn btn-secondary"><i aria-hidden="true" className="fas fa-floppy-disk" /> Back up now</button>}
        </form>
      </div></div>
      <div className="card"><div className="card-body">
        {d.backups.length ? (
          <div className="table-responsive"><table className="table">
            <thead><tr><th>When</th><th>Label</th><th>Entries</th><th className="text-right">Actions</th></tr></thead>
            <tbody>
              {d.backups.map((b) => (
                <tr key={b.id}>
                  <td>{b.when}</td><td>{b.label}</td><td>{b.entry_count}</td>
                  <td className="text-right">
                    {canWrite(d, 'backups_restore') && <button type="button" className="btn btn-primary btn-sm" onClick={() => restore(b)}><i aria-hidden="true" className="fas fa-rotate-left" /> Restore</button>}{' '}
                    {canWrite(d, 'backups_delete') && <button type="button" className="btn btn-danger btn-sm" onClick={() => del(b)}><i aria-hidden="true" className="fas fa-trash" /></button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        ) : (
          <p className="text-muted text-center" style={{ padding: '1.5rem' }}><i aria-hidden="true" className="fas fa-info-circle" /> No backups yet for this term. One is created automatically when you apply a generated timetable, or use “Back up now” above.</p>
        )}
      </div></div>
    </>
  );
}

const SCREENS = { index: Index, mine: Mine, edit: Edit, backups: Backups };

export default function TimetableApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
