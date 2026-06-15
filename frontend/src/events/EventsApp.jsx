import React, { useState } from 'react';
import { submitJson, postFile } from '../lib/forms';
import { useSection, NavCtx, useNav } from '../lib/section';
import { Banner, PageHeader, Empty, SectionShell } from '../components/ui';

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// ---- Calendar --------------------------------------------------------------
function Calendar({ d }) {
  return (
    <>
      <PageHeader title="Calendar" actions={<>
        <a href={d.urls.import} className="btn btn-secondary"><i className="fas fa-file-import" /> Import</a>
        <a href={d.urls.agenda} className="btn btn-secondary"><i className="fas fa-list" /> Agenda</a>
        <a href={d.urls.add_event} className="btn btn-primary"><i className="fas fa-plus" /> Add Event</a>
      </>} />
      <div className="card"><div className="card-body">
        <div className="cal-head">
          <h2 style={{ margin: 0, fontSize: '1.2rem' }}>{d.month_name} {d.year}</h2>
          <div className="cal-nav">
            <a href={d.nav.prev_url} className="btn btn-secondary btn-sm"><i className="fas fa-chevron-left" /></a>
            <a href={d.nav.today_url} className="btn btn-secondary btn-sm">Today</a>
            <a href={d.nav.next_url} className="btn btn-secondary btn-sm"><i className="fas fa-chevron-right" /></a>
          </div>
        </div>
        <div className="cal-grid">
          {DOW.map((x) => <div className="cal-dow" key={x}>{x}</div>)}
          {d.weeks.map((week, wi) => week.map((day) => (
            <div key={day.iso} className={'cal-cell' + (day.in_month ? '' : ' out') + (day.is_today ? ' today' : '')}>
              <div className="cal-daynum"><span>{day.day}</span><a href={day.add_url} title="Add event">+</a></div>
              {day.events.map((e) => (
                <a key={e.id} className="ev" href={e.edit_url} style={{ background: e.color }}
                   title={e.title + (e.start_time ? ' ' + e.start_time : '')}>
                  {e.start_time && !e.all_day ? e.start_time + ' ' : ''}{e.title}
                </a>
              ))}
            </div>
          )))}
        </div>
        <div className="legend">
          {d.categories.map((c) => <span key={c}><i style={{ background: d.category_colors[c] }} />{c}</span>)}
        </div>
      </div></div>
    </>
  );
}

// ---- Agenda ----------------------------------------------------------------
function Agenda({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const go = (params) => { nav.go(d.urls.self + '?' + new URLSearchParams(params).toString()); };
  const del = async (e) => {
    if (!window.confirm(`Delete ${e.title}?`)) return;
    setBusy(true);
    const r = await submitJson(e.delete_url, {});
    setBusy(false);
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not delete.');
  };
  return (
    <>
      <PageHeader title="Events" actions={<>
        <a href={d.urls.calendar} className="btn btn-secondary"><i className="fas fa-calendar" /> Calendar</a>
        <a href={d.urls.add_event} className="btn btn-primary"><i className="fas fa-plus" /> Add Event</a>
      </>} />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form">
          <div className="form-group"><label className="form-label">Category</label>
            <select className="form-control" value={d.category} onChange={(e) => go({ category: e.target.value, upcoming: d.upcoming })}>
              <option value="">All</option>{d.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}>
            <label className="form-check"><input type="checkbox" checked={d.upcoming === '1'}
              onChange={(e) => go({ category: d.category, upcoming: e.target.checked ? '1' : '0' })} /> Upcoming only</label></div>
        </div>
      </div></div>
      <div className="card">
        <div className="card-header"><h3>{d.events.length} event(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.events.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Date</th><th>Event</th><th>Category</th><th>Audience</th><th>Location</th><th /></tr></thead>
              <tbody>{d.events.map((e) => (
                <tr key={e.id}>
                  <td data-label="Date">{e.date_label}{e.time_label && <div className="text-muted text-sm">{e.time_label}</div>}</td>
                  <td data-label="Event"><strong>{e.title}</strong>{e.description && <div className="text-muted text-sm">{e.description.slice(0, 80)}</div>}</td>
                  <td data-label="Category"><span className="badge" style={{ background: e.color, color: '#fff' }}>{e.category}</span></td>
                  <td data-label="Audience">{e.audience}</td>
                  <td data-label="Location">{e.location || '—'}</td>
                  <td className="actions"><div className="d-flex gap-1 justify-end">
                    <a href={e.edit_url} className="btn btn-secondary btn-sm"><i className="fas fa-edit" /></a>
                    <button type="button" className="btn btn-danger btn-sm" disabled={busy} onClick={() => del(e)}><i className="fas fa-trash" /></button>
                  </div></td>
                </tr>
              ))}</tbody></table></div>
          ) : <Empty icon="fa-calendar-day" title="No events"><p>Add school events, holidays and exams to the calendar.</p><a href={d.urls.add_event} className="btn btn-primary mt-2">Add Event</a></Empty>}
        </div>
      </div>
    </>
  );
}

// ---- Event form ------------------------------------------------------------
function EventForm({ d, notify }) {
  const nav = useNav();
  const ev = d.event || {};
  const editing = !!d.event;
  const [f, setF] = useState({
    title: ev.title || '', category: ev.category || d.categories[0], audience: ev.audience || d.audiences[0],
    start_date: ev.start_date || d.preset || '', end_date: ev.end_date || '',
    all_day: editing ? !!ev.all_day : true, start_time: ev.start_time || '', end_time: ev.end_time || '',
    location: ev.location || '', term_id: ev.term_id ? String(ev.term_id) : '', description: ev.description || '',
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Title is required.'); return; }
    if (!f.start_date) { notify('error', 'Start date is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, all_day: f.all_day ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save the event.');
  };
  const del = async () => {
    if (!window.confirm('Delete this event?')) return;
    const r = await submitJson(d.delete_url, {});
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not delete.');
  };

  return (
    <>
      <PageHeader title={editing ? 'Edit Event' : 'Add Event'} />
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-group"><label className="form-label">Title <span className="required">*</span></label>
            <input type="text" className="form-control" required value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Category</label>
              <select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>{d.categories.map((c) => <option key={c}>{c}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Audience</label>
              <select className="form-control" value={f.audience} onChange={(e) => set('audience', e.target.value)}>{d.audiences.map((a) => <option key={a}>{a}</option>)}</select></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Start date <span className="required">*</span></label>
              <input type="date" className="form-control" required value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">End date <span className="text-muted text-sm">(optional)</span></label>
              <input type="date" className="form-control" value={f.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
          </div>
          <div className="form-check mb-2"><input type="checkbox" id="allDay" checked={f.all_day} onChange={(e) => set('all_day', e.target.checked)} /> <label htmlFor="allDay">All day</label></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Start time</label>
              <input type="time" className="form-control" value={f.start_time} onChange={(e) => set('start_time', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">End time</label>
              <input type="time" className="form-control" value={f.end_time} onChange={(e) => set('end_time', e.target.value)} /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Location</label>
              <input type="text" className="form-control" value={f.location} onChange={(e) => set('location', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Term</label>
              <select className="form-control" value={f.term_id} onChange={(e) => set('term_id', e.target.value)}>
                <option value="">—</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></div>
          </div>
          <div className="form-group"><label className="form-label">Description</label>
            <textarea className="form-control" rows="3" value={f.description} onChange={(e) => set('description', e.target.value)} /></div>
          <div className="page-header-actions">
            <button type="submit" className="btn btn-primary" disabled={busy}><i className="fas fa-save" /> {editing ? 'Save' : 'Add Event'}</button>
            <a href={d.urls.agenda} className="btn btn-secondary">Cancel</a>
            {editing && <button type="button" className="btn btn-danger" style={{ marginLeft: 'auto' }} onClick={del}><i className="fas fa-trash" /> Delete</button>}
          </div>
        </form>
      </div></div>
    </>
  );
}

// ---- Import (upload -> review) ---------------------------------------------
function Import({ d, notify }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [review, setReview] = useState(null);   // { rows, terms, categories, save_url }

  const scan = async (e) => {
    e.preventDefault();
    if (!file) { notify('error', 'Choose a file to scan.'); return; }
    setBusy(true);
    const r = await postFile(d.upload_url, file);
    setBusy(false);
    if (r.ok) setReview({ rows: r.rows.map((x) => ({ ...x, include: true })), terms: r.terms, categories: r.categories, save_url: r.save_url });
    else notify('error', r.error || 'Could not scan the file.');
  };

  if (review) return <ImportReview review={review} setReview={setReview} d={d} notify={notify} />;

  return (
    <>
      <PageHeader title="Import School Calendar" />
      <div className="card" style={{ maxWidth: 640 }}>
        <div className="card-header"><h3><i className="fas fa-file-import" /> Scan a calendar file</h3></div>
        <div className="card-body">
          <p className="text-muted">Upload your school calendar as a <strong>Word document (.docx)</strong>, an <strong>image</strong> (photo/scan) or a <strong>PDF</strong>. The system reads the dates and activities and shows them for review before adding them to the calendar — no manual typing.</p>
          <form onSubmit={scan}>
            <div className="form-group">
              <label className="form-label">Calendar file <span className="required">*</span></label>
              <input type="file" className="form-control" accept=".docx,image/*,.pdf" onChange={(e) => setFile(e.target.files[0] || null)} required />
              <span className="form-hint d-block">Best results: a Word table of Week / Activity / Dates, or a clear, straight photo.</span>
            </div>
            <button type="submit" className="btn btn-primary" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-magic')} /> {busy ? 'Scanning…' : 'Scan & Review'}</button>
            <a href={d.urls.calendar} className="btn btn-secondary">Cancel</a>
          </form>
        </div>
      </div>
    </>
  );
}

function ImportReview({ review, setReview, d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const [termId, setTermId] = useState('');
  const rows = review.rows;
  const setRow = (i, k, v) => setReview((r) => ({ ...r, rows: r.rows.map((row, j) => (j === i ? { ...row, [k]: v } : row)) }));
  const selAll = (v) => setReview((r) => ({ ...r, rows: r.rows.map((row) => ({ ...row, include: v })) }));

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
    <>
      <PageHeader title="Review Scanned Events" actions={
        <button type="button" className="btn btn-secondary" onClick={() => setReview(null)}><i className="fas fa-redo" /> Scan another</button>} />
      <div className="card mb-3"><div className="card-body">
        <p className="mb-0 text-muted">{rows.length} activities detected. Untick any you don't want, fix dates/titles/categories, then import. Multi-day items have an end date.</p>
      </div></div>
      <div className="card">
        <div className="card-header"><h3>Detected events</h3>
          <div className="d-flex gap-2 align-center">
            <label className="text-sm"><input type="checkbox" checked={rows.every((r) => r.include)} onChange={(e) => selAll(e.target.checked)} /> Select all</label>
            <div className="form-group mb-0"><select className="form-control" style={{ maxWidth: 200 }} value={termId} onChange={(e) => setTermId(e.target.value)}>
              <option value="">No term</option>{review.terms.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></div>
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Use</th><th>Start</th><th>End</th><th>Activity</th><th>Category</th></tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={i}>
                <td data-label="Use"><input type="checkbox" checked={r.include} onChange={(e) => setRow(i, 'include', e.target.checked)} /></td>
                <td data-label="Start"><input type="date" className="form-control" style={{ minWidth: 140 }} value={r.start_date} onChange={(e) => setRow(i, 'start_date', e.target.value)} /></td>
                <td data-label="End"><input type="date" className="form-control" style={{ minWidth: 140 }} value={r.end_date} onChange={(e) => setRow(i, 'end_date', e.target.value)} /></td>
                <td data-label="Activity"><input type="text" className="form-control" value={r.title} onChange={(e) => setRow(i, 'title', e.target.value)} /></td>
                <td data-label="Category"><select className="form-control" value={r.category} onChange={(e) => setRow(i, 'category', e.target.value)}>
                  {review.categories.map((c) => <option key={c}>{c}</option>)}</select></td>
              </tr>
            ))}</tbody>
          </table></div>
        </div>
      </div>
      <div className="page-header-actions mt-3">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={save}><i className="fas fa-calendar-plus" /> Import selected events</button>
        <a href={d.urls.calendar} className="btn btn-secondary">Cancel</a>
      </div>
    </>
  );
}

const SCREENS = { calendar: Calendar, agenda: Agenda, event_form: EventForm, import: Import };

export default function EventsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Calendar;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
