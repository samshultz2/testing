import React, { useState, useEffect, useRef } from 'react';
import { chartPalette } from '../lib/hooks';
import { submitJson } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, promptDialog, Banner, SectionShell, SectionTabs, Empty, Autocomplete } from '../components/ui';

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'], ['compose', 'fa-paper-plane', 'Compose'],
  ['inbox', 'fa-comments', 'Inbox'],
  ['announcements', 'fa-bullhorn', 'Announcements'], ['messages', 'fa-clock-rotate-left', 'History'],
  ['reports', 'fa-chart-line', 'Reports'],
  ['templates', 'fa-file-lines', 'Templates'], ['contacts', 'fa-address-book', 'Contacts'],
  ['settings', 'fa-gear', 'Settings'],
];
// A few pages map onto a tab that isn't their own page key.
const TAB_FOR = { message_detail: 'messages' };

function Tabs({ d }) {
  const nav = useNav();
  return <SectionTabs tabs={TABS} urls={d.nav} active={TAB_FOR[d.page] || d.page} go={nav.go} />;
}

// Multipart upload of a single file to a comms attachment endpoint.
async function uploadAttachment(url, file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(url, { method: 'POST', credentials: 'same-origin',
    headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrfToken() }, body: fd });
  try { return await res.json(); } catch (_) { return { ok: false, error: 'Upload failed.' }; }
}

// A file input + attached-file chip. Calls back with the attachment (or null).
function AttachField({ url, value, onChange, notify }) {
  const ref = useRef();
  const pick = async (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const r = await uploadAttachment(url, f);
    if (r.ok) onChange(r.attachment); else notify && notify('error', r.error || 'Upload failed.');
    if (ref.current) ref.current.value = '';
  };
  return (
    <div className="attach-field">
      {value ? (
        <span className="attach-chip"><i aria-hidden="true" className="fas fa-paperclip" /> {value.name}{value.size ? ` · ${value.size}` : ''}
          <button type="button" onClick={() => onChange(null)} aria-label="Remove attachment">×</button></span>
      ) : (
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => ref.current && ref.current.click()}><i aria-hidden="true" className="fas fa-paperclip" /> Attach file</button>
          <input ref={ref} type="file" style={{ display: 'none' }} onChange={pick} />
        </>
      )}
    </div>
  );
}

const channelBadge = (ch) => 'badge ' + (ch === 'WhatsApp' ? 'badge-success' : ch === 'Email' ? 'badge-warning' : 'badge-info');
const statusBadge = (s) => 'badge ' + (s === 'Sent' || s === 'Posted' ? 'badge-success' : s === 'Failed' ? 'badge-danger' : s === 'Scheduled' ? 'badge-info' : 'badge-warning');

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const ref = useRef();
  useEffect(() => {
    if (!ref.current || !window.Chart || !d.channel_chart.length) return;
    const cs = getComputedStyle(document.body);
    window.Chart.defaults.color = cs.getPropertyValue('--text-secondary') || '#666';
    const chart = new window.Chart(ref.current, {
      type: 'doughnut',
      data: { labels: d.channel_chart.map((x) => x.channel),
        datasets: [{ data: d.channel_chart.map((x) => x.count),
          backgroundColor: chartPalette().categorical, borderWidth: 0 }] },
      options: { maintainAspectRatio: false, cutout: '58%',
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } } },
    });
    return () => chart.destroy();
  }, [d.channel_chart]);

  const s = d.stats || {};
  const quick = [
    [d.urls.compose_sms || d.nav.compose, 'fa-comment-sms', 'Send SMS', 'btn-primary'],
    [d.urls.compose_email || d.nav.compose, 'fa-envelope', 'Send Email', 'btn-secondary'],
    [d.nav.announcements, 'fa-bullhorn', 'Announcement', 'btn-secondary'],
    [d.nav.templates, 'fa-file-lines', 'Templates', 'btn-secondary'],
    [d.nav.messages, 'fa-clock-rotate-left', 'History', 'btn-secondary'],
  ];
  const kpis = [
    ['blue', 'fa-paper-plane', s.sent_today != null ? s.sent_today : 0, 'Sent today', d.nav.messages],
    ['teal', 'fa-comment-sms', s.sms_today != null ? s.sms_today : 0, 'SMS today', null],
    ['green', 'fa-envelope', s.email_today != null ? s.email_today : 0, 'Emails today', null],
    ['amber', 'fa-clock', s.scheduled != null ? s.scheduled : 0, 'Scheduled', d.nav.messages],
    ['blue', 'fa-file-pen', s.drafts != null ? s.drafts : 0, 'Drafts', d.nav.messages],
    ['red', 'fa-triangle-exclamation', s.failed != null ? s.failed : 0, 'Failed', d.nav.messages],
    ['green', 'fa-circle-check', s.success_rate == null ? '—' : s.success_rate + '%', 'Delivery rate', null],
    ['amber', 'fa-address-book', d.cov.pct + '%', 'Contact coverage', d.urls.contacts_missing],
  ];

  return (
    <>
      <div className="page-header"><h1>Communication Center</h1>
        <div className="page-header-actions"><a href={d.nav.compose} className="btn btn-primary"><i aria-hidden="true" className="fas fa-paper-plane" /> New Message</a></div>
      </div>
      <Tabs d={d} />
      <div className="cm-quick d-flex gap-2 flex-wrap mb-3">{quick.map(([href, ic, label, cls]) => (
        <a href={href} className={'btn ' + cls + ' btn-sm'} key={label}><i aria-hidden="true" className={'fas ' + ic} /> {label}</a>))}
      </div>
      <div className="kpi-row">{kpis.map(([c, ic, v, l, href]) => {
        const inner = (<><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div>
          <div><div className="v">{v}</div><div className="l">{l}</div></div></>);
        return href ? <a className="kpi" key={l} href={href} style={{ textDecoration: 'none', color: 'inherit' }}>{inner}</a>
          : <div className="kpi" key={l}>{inner}</div>;
      })}
      </div>

      <div className="card mb-3"><div className="card-body">
        <div className="d-flex justify-between text-sm flex-wrap gap-1">
          <span><strong>{d.cov.with_contact}</strong> of {d.cov.total} students have a parent phone number</span>
          {d.cov.without_contact > 0 && <a href={d.urls.contacts_missing} className="text-sm">{d.cov.without_contact} missing — review</a>}
        </div>
        <div className="progress-wrap"><div className="bar" style={{ width: d.cov.pct + '%' }} /></div>
      </div></div>

      <div className="cm-grid split">
        <div className="widget"><div className="wh"><h3><i aria-hidden="true" className="fas fa-comment-dots" /> By channel</h3></div>
          <div className="wb"><div className="chart-box">{d.channel_chart.length
            ? <canvas ref={ref} /> : <Empty icon="fa-comment-dots" title="No messages yet" />}</div></div></div>
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Recent campaigns</h3><a href={d.nav.messages} className="text-sm">View all</a></div>
          <div className="wb" style={{ padding: 0 }}>
            {d.recent.length ? (
              <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
                <thead><tr><th>Date</th><th>Title</th><th>Audience</th><th>Channel</th><th>Status</th><th className="text-right">Sent</th></tr></thead>
                <tbody>{d.recent.map((m) => (
                  <tr key={m.id}><td data-label="Date">{m.date}</td>
                    <td data-label="Title"><a href={m.url}>{m.title}</a></td>
                    <td data-label="Audience" className="text-muted text-sm">{m.audience_label}</td>
                    <td data-label="Channel"><span className={channelBadge(m.channel)}>{m.channel}</span></td>
                    <td data-label="Status"><span className={statusBadge(m.status)}>{m.status}</span></td>
                    <td data-label="Sent" className="text-right">{m.sent_count}/{m.recipient_count}</td></tr>))}
                </tbody></table></div>
            ) : <Empty icon="fa-paper-plane" title="No campaigns yet"><a href={d.nav.compose} className="btn btn-primary btn-sm mt-2">Send your first message</a></Empty>}
          </div></div>
      </div>

      <div className="card"><div className="card-body d-flex gap-2 flex-wrap align-center">
        <i aria-hidden="true" className="fas fa-lightbulb" style={{ color: 'var(--warning)', fontSize: 'var(--text-lg)' }} />
        <div style={{ flex: 1, minWidth: 200 }}><strong>{d.template_count} message template(s)</strong>
          <div className="text-muted text-sm">Reusable messages with placeholders like {'{first_name}'}, {'{class}'} and {'{balance}'}.</div></div>
        <a href={d.nav.templates} className="btn btn-secondary btn-sm">Manage templates</a>
      </div></div>
    </>
  );
}

// ---- Announcements ---------------------------------------------------------
function Announcements({ d, notify }) {
  const nav = useNav();
  const blank = { title: '', body: '', category: 'Info', audience: 'All', starts_on: '', ends_on: '', is_pinned: false, needs_ack: false };
  const [f, setF] = useState(blank);
  const [att, setAtt] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Title is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.add_url, { ...f, is_pinned: f.is_pinned ? 'on' : '', needs_ack: f.needs_ack ? 'on' : '',
      attachment_id: att ? att.id : '' });
    setBusy(false);
    if (r.ok) { setF(blank); setAtt(null); nav.refresh(); }
    else notify('error', r.error || 'Could not post.');
  };
  const del = async (url) => {
    if (!await confirm('Delete this announcement?')) return;
    const r = await submitJson(url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not delete.');
  };
  const catBadge = (c) => 'badge ' + (c === 'Important' ? 'badge-danger' : c === 'Event' ? 'badge-warning' : 'badge-info');
  return (
    <>
      <div className="page-header"><h1>Announcements</h1></div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Post an announcement</h3></div>
        <div className="card-body"><form onSubmit={submit}>
          <div className="form-group"><label className="form-label">Title <span className="required">*</span></label>
            <input type="text" className="form-control" required value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Message</label>
            <textarea className="form-control" rows="2" value={f.body} onChange={(e) => set('body', e.target.value)} /></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Category</label>
              <select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}><option>Info</option><option>Important</option><option>Event</option></select></div>
            <div className="form-group"><label className="form-label">Audience</label>
              <select className="form-control" value={f.audience} onChange={(e) => set('audience', e.target.value)}><option>All</option><option>Staff</option><option>Students</option><option>Parents</option></select></div>
            <div className="form-group"><label className="form-label">Show from</label>
              <input type="date" className="form-control" value={f.starts_on} onChange={(e) => set('starts_on', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Until</label>
              <input type="date" className="form-control" value={f.ends_on} onChange={(e) => set('ends_on', e.target.value)} /></div>
            <div className="form-group" style={{ alignSelf: 'center' }}><label className="form-check"><input type="checkbox" checked={f.is_pinned} onChange={(e) => set('is_pinned', e.target.checked)} /> Pin to top</label></div>
            <div className="form-group" style={{ alignSelf: 'center' }}><label className="form-check" title="Staff must click Acknowledge to confirm they've read it"><input type="checkbox" checked={f.needs_ack} onChange={(e) => set('needs_ack', e.target.checked)} /> Require acknowledgement</label></div>
          </div>
          <div className="form-group"><label className="form-label">Attachment</label>
            <AttachField url={d.upload_url} value={att} onChange={setAtt} notify={notify} /></div>
          <button className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-bullhorn" /> Post</button>
        </form></div></div>

      <div className="card"><div className="card-header"><h3>{d.items.length} announcement(s)</h3></div>
        <div className="card-body">
          {d.items.length ? d.items.map((a) => (
            <div className={'ann ' + a.category} key={a.id}>
              <div className="d-flex justify-between gap-2">
                <div><strong>{a.title}</strong> {a.is_pinned && <i aria-hidden="true" className="fas fa-thumbtack text-muted" title="Pinned" />}
                  {' '}<span className={catBadge(a.category)}>{a.category}</span>{' '}
                  <span className="badge badge-secondary">{a.audience}</span>{' '}
                  {a.needs_ack && <span className="badge badge-info" title="Requires acknowledgement"><i aria-hidden="true" className="fas fa-circle-check" /> {a.ack_count} ack{a.ack_count === 1 ? '' : 's'}</span>}{' '}
                  {!a.is_active && <span className="badge badge-secondary">Inactive</span>}</div>
                <button className="btn btn-danger btn-sm" onClick={() => del(a.delete_url)}><i aria-hidden="true" className="fas fa-trash" /></button>
              </div>
              {a.body && <div className="text-secondary text-sm mt-1">{a.body}</div>}
              {a.attachment && <div className="mt-1"><a href={a.attachment.url} className="attach-link" data-native><i aria-hidden="true" className="fas fa-paperclip" /> {a.attachment.name}{a.attachment.size ? ` · ${a.attachment.size}` : ''}</a></div>}
              <div className="text-muted text-sm mt-1">{a.created_at} by {a.created_by}
                {(a.starts_on || a.ends_on) && ` · ${a.starts_on || '…'} – ${a.ends_on || '…'}`}</div>
            </div>
          )) : <Empty icon="fa-bullhorn" title="No announcements"><p>Post a notice to show it on everyone's dashboard.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Templates -------------------------------------------------------------
function Templates({ d, notify }) {
  const nav = useNav();
  const sel = d.sel || {};
  const [f, setF] = useState({ name: '', category: '', body: '' });
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState(sel.q || '');
  const qRef = useRef();
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const reload = (extra) => navParams(nav.go, d.self_url, { q, category: sel.category || '', ...extra });
  useEffect(() => {
    if ((sel.q || '') === q) return undefined;
    clearTimeout(qRef.current); qRef.current = setTimeout(() => reload({}), 400);
    return () => clearTimeout(qRef.current);
    /* eslint-disable-next-line */
  }, [q]);
  const add = async (e) => {
    e.preventDefault();
    if (!f.name.trim() || !f.body.trim()) { notify('error', 'Template name and body are required.'); return; }
    setBusy(true);
    const r = await submitJson(d.add_url, f);
    setBusy(false);
    if (r.ok) { setF({ name: '', category: '', body: '' }); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const del = async (url, name) => {
    if (!await confirm(`Delete template ${name}?`)) return;
    const r = await submitJson(url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not delete.');
  };
  const act = async (url, err) => {
    const r = await submitJson(url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || err);
  };
  return (
    <>
      <div className="page-header"><h1>Message Templates</h1></div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> New Template</h3></div>
        <div className="card-body"><form onSubmit={add}>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Name <span className="required">*</span></label>
              <input type="text" className="form-control" required placeholder="e.g., Fee reminder" value={f.name} onChange={(e) => set('name', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Category</label>
              <input type="text" className="form-control" placeholder="Fees / Attendance / Event…" list="catlist" value={f.category} onChange={(e) => set('category', e.target.value)} />
              <datalist id="catlist"><option>Fees</option><option>Attendance</option><option>General</option><option>Event</option></datalist></div>
          </div>
          <div className="form-group mb-2"><label className="form-label">Body <span className="required">*</span></label>
            <div className="ph-hint">Placeholders: {d.placeholders.map((p) => <code key={p}>{p}</code>)}</div>
            <textarea className="form-control" rows="4" required placeholder="Dear {parent}, …" value={f.body} onChange={(e) => set('body', e.target.value)} /></div>
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Template</button>
        </form></div></div>

      <div className="card"><div className="card-header d-flex justify-between align-center flex-wrap gap-2">
        <h3>Templates ({d.templates.length})</h3>
        <div className="d-flex gap-2 align-center flex-wrap">
          <div className="hf-search" style={{ minWidth: 200 }}><i aria-hidden="true" className="fas fa-magnifying-glass" />
            <input type="search" placeholder="Search templates…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search templates" /></div>
          <select className="form-control" style={{ maxWidth: 180 }} value={sel.category || ''} onChange={(e) => reload({ category: e.target.value })} aria-label="Category">
            <option value="">All categories</option>{(d.categories || []).map((c) => <option key={c} value={c}>{c}</option>)}</select>
        </div></div>
        <div className="card-body">
          {d.templates.length ? d.templates.map((t) => (
            <div className="tpl-card" key={t.id}>
              <div className="d-flex justify-between align-center flex-wrap gap-1">
                <div>
                  <button className="tpl-star" title={t.is_favorite ? 'Unfavourite' : 'Favourite'} onClick={() => act(t.favorite_url, 'Could not update.')}>
                    <i aria-hidden="true" className={(t.is_favorite ? 'fas' : 'far') + ' fa-star' + (t.is_favorite ? ' on' : '')} /></button>
                  {' '}<strong>{t.name}</strong> {t.category && <span className="badge badge-secondary">{t.category}</span>} {!t.is_active && <span className="badge badge-warning">Inactive</span>}</div>
                <div className="d-flex gap-1">
                  <a href={t.use_url} className="btn btn-primary btn-sm" title="Use"><i aria-hidden="true" className="fas fa-paper-plane" /></a>
                  <button className="btn btn-secondary btn-sm" title="Edit" onClick={() => setEditing(editing === t.id ? null : t.id)}><i aria-hidden="true" className="fas fa-edit" /></button>
                  <button className="btn btn-secondary btn-sm" title="Duplicate" onClick={() => act(t.duplicate_url, 'Could not duplicate.')}><i aria-hidden="true" className="fas fa-copy" /></button>
                  <button className="btn btn-danger btn-sm" onClick={() => del(t.delete_url, t.name)}><i aria-hidden="true" className="fas fa-trash" /></button>
                </div>
              </div>
              <div className="body">{t.body}</div>
              {editing === t.id && <EditTemplate t={t} notify={notify} onDone={() => { setEditing(null); nav.refresh(); }} />}
            </div>
          )) : <Empty icon="fa-file-lines" title="No templates"><p>Create reusable messages with placeholders, or adjust your search.</p></Empty>}
        </div></div>
    </>
  );
}

function EditTemplate({ t, notify, onDone }) {
  const [f, setF] = useState({ name: t.name, category: t.category, body: t.body, is_active: t.is_active });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(t.edit_url, { ...f, is_active: f.is_active ? 'on' : '' });
    setBusy(false);
    if (r.ok) onDone(); else notify('error', r.error || 'Could not update.');
  };
  return (
    <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '.6rem' }}>
      <form onSubmit={submit}>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Name</label><input type="text" className="form-control" value={f.name} onChange={(e) => set('name', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Category</label><input type="text" className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)} /></div>
        </div>
        <div className="form-group"><label className="form-label">Body</label><textarea className="form-control" rows="4" value={f.body} onChange={(e) => set('body', e.target.value)} /></div>
        <label className="form-check mb-2"><input type="checkbox" checked={f.is_active} onChange={(e) => set('is_active', e.target.checked)} /> Active</label>
        <div><button type="submit" className="btn btn-primary btn-sm" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Update</button></div>
      </form>
    </div>
  );
}

// ---- Contacts --------------------------------------------------------------
function Contacts({ d }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q);
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, q, missing: d.missing ? 1 : '', ...extra });
  return (
    <>
      <div className="page-header"><h1>Contact Directory</h1></div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <form className="filter-form" onSubmit={(e) => { e.preventDefault(); go(); }}>
          <div className="form-group"><label className="form-label">Term</label>
            <select className="form-control" value={d.term_id} onChange={(e) => go({ term_id: e.target.value })}>
              {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Class</label>
            <select className="form-control" value={d.class_id} onChange={(e) => go({ class_id: e.target.value })}>
              <option value="">All classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Search</label>
            <input type="text" className="form-control" value={q} placeholder="Name or ID" onChange={(e) => setQ(e.target.value)} /></div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}><label className="form-check">
            <input type="checkbox" checked={d.missing} onChange={(e) => go({ missing: e.target.checked ? 1 : '' })} /> Missing contact only</label></div>
        </form>
        <div className="text-muted text-sm mt-2">{d.cov.with_contact}/{d.cov.total} students have a phone number ({d.cov.pct}%). Add or edit contacts from a student's profile.</div>
      </div></div>

      <div className="card"><div className="card-header"><h3>Students ({d.rows.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.rows.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Student</th><th>Parent contacts</th><th /></tr></thead>
              <tbody>{d.rows.map((row) => (
                <tr key={row.student.id}>
                  <td data-label="Student"><strong>{row.student.full_name}</strong><div className="text-muted text-sm">{row.student.student_id}</div></td>
                  <td data-label="Contacts">
                    {row.contacts.length ? row.contacts.map((c, i) => (
                      <div className="con-line" key={i}>
                        <span>{c.name}{c.relationship && <span className="text-muted"> ({c.relationship})</span>} {c.is_primary && <span className="badge badge-info">Primary</span>}</span>
                        <a href={'tel:' + c.phone_number}>{c.phone_number}</a>
                        <a href={'https://wa.me/' + c.wa_intl} target="_blank" rel="noopener" title="WhatsApp"><i aria-hidden="true" className="fab fa-whatsapp wa-ic" /></a>
                      </div>
                    )) : <span className="badge badge-warning">No contact</span>}
                  </td>
                  <td className="actions"><a href={row.student.view_url} className="btn btn-secondary btn-sm" title="Manage"><i aria-hidden="true" className="fas fa-user-pen" /></a></td>
                </tr>))}
              </tbody></table></div>
          ) : <Empty icon="fa-address-book" title="No students found"><p>Adjust the filters above.</p></Empty>}
        </div></div>
    </>
  );
}

// ---- Communication history (unified timeline) ------------------------------
function Messages({ d, notify }) {
  const nav = useNav();
  const s = d.sel || {};
  const [type, setType] = useState(s.type || '');
  const [status, setStatus] = useState(s.status || '');
  const [sender, setSender] = useState(s.sender || '');
  const [q, setQ] = useState(s.q || '');
  const [from, setFrom] = useState(s.from || '');
  const [to, setTo] = useState(s.to || '');
  const qRef = useRef();

  const go = (extra) => navParams(nav.go, d.urls.self,
    { type, status, sender, q, from, to, page: 1, ...extra });
  // debounce free-text search
  useEffect(() => {
    if ((s.q || '') === q) return undefined;
    clearTimeout(qRef.current); qRef.current = setTimeout(() => go({}), 450);
    return () => clearTimeout(qRef.current);
    /* eslint-disable-next-line */
  }, [q]);
  const reset = () => navParams(nav.go, d.urls.self, {});
  const processDue = async () => {
    const r = await submitJson(d.urls.process_scheduled, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Failed.');
  };

  return (
    <>
      <div className="page-header"><h1>Communication History</h1>
        <div className="page-header-actions">
          <a href={d.urls.reports} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-chart-line" /> Reports</a>
          {d.is_admin && <button className="btn btn-secondary" title="Send any scheduled campaigns that are now due" onClick={processDue}><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Process due</button>}
          <a href={d.urls.compose} className="btn btn-primary"><i aria-hidden="true" className="fas fa-paper-plane" /> New Message</a>
        </div>
      </div>
      <Tabs d={d} />

      <div className="hist-filters card mb-3"><div className="card-body">
        <div className="hf-grid">
          <div className="hf-search"><i aria-hidden="true" className="fas fa-magnifying-glass" />
            <input type="search" placeholder="Search title, message or audience…" value={q}
              onChange={(e) => setQ(e.target.value)} aria-label="Search history" /></div>
          <select className="form-control" value={type} onChange={(e) => { setType(e.target.value); go({ type: e.target.value }); }} aria-label="Type">
            <option value="">All types</option>{d.types.map((t) => <option key={t} value={t}>{t}</option>)}</select>
          <select className="form-control" value={status} onChange={(e) => { setStatus(e.target.value); go({ status: e.target.value }); }} aria-label="Status">
            <option value="">Any status</option>{d.statuses.map((t) => <option key={t} value={t}>{t}</option>)}</select>
          <select className="form-control" value={sender} onChange={(e) => { setSender(e.target.value); go({ sender: e.target.value }); }} aria-label="Sender">
            <option value="">Any sender</option>{d.senders.map((t) => <option key={t} value={t}>{t}</option>)}</select>
          <input type="date" className="form-control" value={from} onChange={(e) => { setFrom(e.target.value); go({ from: e.target.value }); }} aria-label="From" />
          <input type="date" className="form-control" value={to} onChange={(e) => { setTo(e.target.value); go({ to: e.target.value }); }} aria-label="To" />
          <button type="button" className="btn btn-link btn-sm" onClick={reset}>Reset</button>
        </div>
      </div></div>

      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.items.length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Date</th><th>Title</th><th>Type</th><th>Audience</th><th>By</th><th>Status</th><th className="text-right">Sent</th><th /></tr></thead>
            <tbody>{d.items.map((m) => (
              <tr key={m.kind + m.id}><td data-label="Date">{m.date}</td>
                <td data-label="Title"><a href={m.url}><strong>{m.title}</strong></a>{m.status === 'Scheduled' && m.scheduled_at && <> <span className="badge badge-warning"><i aria-hidden="true" className="fas fa-clock" /> {m.scheduled_at}</span></>}</td>
                <td data-label="Type"><span className={channelBadge(m.type)}>{m.type}</span></td>
                <td data-label="Audience" className="text-muted text-sm">{m.audience_label}</td>
                <td data-label="By" className="text-muted text-sm">{m.by}</td>
                <td data-label="Status"><span className={statusBadge(m.status)}>{m.status}</span></td>
                <td data-label="Sent" className="text-right">{m.recipient_count === '' ? '—' : `${m.sent_count}/${m.recipient_count}`}</td>
                <td className="actions"><a href={m.url} className="btn btn-secondary btn-sm" aria-label="Open"><i aria-hidden="true" className="fas fa-arrow-right" /></a></td></tr>))}
            </tbody></table></div>
        ) : <Empty icon="fa-inbox" title="Nothing matches these filters"><p>Try a broader search or reset the filters.</p></Empty>}
      </div></div>

      {d.pages > 1 && (
        <div className="hist-pager">
          <button type="button" className="btn btn-secondary btn-sm" disabled={!d.has_prev} onClick={() => go({ page: d.page_no - 1 })}><i aria-hidden="true" className="fas fa-chevron-left" /> Prev</button>
          <span className="text-muted text-sm">Page {d.page_no} of {d.pages} · {d.total} item{d.total === 1 ? '' : 's'}</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={!d.has_next} onClick={() => go({ page: d.page_no + 1 })}>Next <i aria-hidden="true" className="fas fa-chevron-right" /></button>
        </div>)}
    </>
  );
}

// ---- Reports ---------------------------------------------------------------
function Reports({ d }) {
  const nav = useNav();
  const s = d.sel || {};
  const r = d.data || {};
  const [from, setFrom] = useState(s.from || '');
  const [to, setTo] = useState(s.to || '');
  const apply = () => navParams(nav.go, d.urls.self, { from, to });
  const exp = (fmt) => `${fmt === 'xlsx' ? d.urls.export_xlsx : d.urls.export_csv}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
  const tiles = [
    ['blue', 'fa-paper-plane', r.total_campaigns, 'Campaigns'],
    ['teal', 'fa-users', r.recipients, 'Recipients'],
    ['green', 'fa-circle-check', r.sent, 'Delivered'],
    ['red', 'fa-triangle-exclamation', r.failed, 'Failed'],
    ['green', 'fa-percent', r.delivery_rate == null ? '—' : r.delivery_rate + '%', 'Delivery rate'],
    ['green', 'fa-book-open', r.read == null ? 0 : r.read, 'Read'],
    ['amber', 'fa-clock', r.scheduled, 'Scheduled'],
    ['blue', 'fa-file-pen', r.drafts, 'Drafts'],
    ['amber', 'fa-bullhorn', r.announcements, 'Announcements'],
  ];
  return (
    <>
      <div className="page-header"><h1>Communication Reports</h1>
        <div className="page-header-actions">
          <a href={exp('csv')} className="btn btn-secondary" data-native><i aria-hidden="true" className="fas fa-file-csv" /> CSV</a>
          <a href={exp('xlsx')} className="btn btn-secondary" data-native><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
        </div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <div className="d-flex gap-2 align-center flex-wrap">
          <label className="text-sm text-muted">From</label>
          <input type="date" className="form-control" style={{ maxWidth: 170 }} value={from} onChange={(e) => setFrom(e.target.value)} />
          <label className="text-sm text-muted">To</label>
          <input type="date" className="form-control" style={{ maxWidth: 170 }} value={to} onChange={(e) => setTo(e.target.value)} />
          <button type="button" className="btn btn-primary btn-sm" onClick={apply}><i aria-hidden="true" className="fas fa-filter" /> Apply</button>
          <span className="text-muted text-sm">{r.from} → {r.to}</span>
        </div>
      </div></div>
      <div className="kpi-row">{tiles.map(([c, ic, v, l]) => (
        <div className="kpi" key={l}><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div>
          <div><div className="v">{v == null ? 0 : v}</div><div className="l">{l}</div></div></div>))}
      </div>
      <div className="card"><div className="card-header"><h3>By channel</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {(r.by_channel || []).length ? (
            <div className="table-container"><table className="data-table">
              <thead><tr><th>Channel</th><th className="text-right">Campaigns</th><th className="text-right">Recipients</th><th className="text-right">Sent</th></tr></thead>
              <tbody>{r.by_channel.map((c) => (
                <tr key={c.channel}><td><span className={channelBadge(c.channel)}>{c.channel}</span></td>
                  <td className="text-right">{c.campaigns}</td><td className="text-right">{c.recipients}</td><td className="text-right">{c.sent}</td></tr>))}
              </tbody></table></div>
          ) : <Empty icon="fa-chart-line" title="No activity in this period" />}
        </div></div>
    </>
  );
}

// ---- Message detail --------------------------------------------------------
function MessageDetail({ d, notify }) {
  const nav = useNav();
  const m = d.msg;
  const [rows, setRows] = useState(d.rows);
  const [copied, setCopied] = useState(false);

  const markSent = async (row) => {
    if (row.status === 'Sent') return;
    try {
      await fetch(row.sent_url, { method: 'POST', headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrfToken() } });
      setRows((rs) => rs.map((x) => (x.id === row.id ? { ...x, status: 'Sent' } : x)));
    } catch (_) { /* ignore */ }
  };
  const action = async (url, confirmMsg, redirect) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); redirect ? nav.go(r.redirect) : nav.refresh(); }
    else notify('error', r.error || 'Action failed.');
  };
  const copyNumbers = () => {
    navigator.clipboard.writeText(rows.map((r) => r.phone).join(', ')).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1500);
    });
  };
  const linkFor = (r) => m.channel === 'SMS'
    ? `sms:${r.phone}?body=${encodeURIComponent(r.body)}`
    : `https://wa.me/${r.intl}?text=${encodeURIComponent(r.body)}`;

  return (
    <>
      <div className="page-header"><h1>{m.title}</h1>
        <div className="page-header-actions">
          <a href={d.urls.export} className="btn btn-secondary" data-native download><i aria-hidden="true" className="fas fa-file-csv" /> Export CSV</a>
          <a href={d.urls.compose} className="btn btn-primary"><i aria-hidden="true" className="fas fa-paper-plane" /> New</a>
        </div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body">
        <div className="d-flex justify-between flex-wrap gap-2 mb-2">
          <div><span className={channelBadge(m.channel)}>{m.channel}</span> <span className="badge badge-secondary">{m.audience_label}</span>
            {m.status === 'Scheduled' && <> <span className="badge badge-warning"><i aria-hidden="true" className="fas fa-clock" /> Scheduled {m.scheduled_at}</span></>}
            <span className="text-muted text-sm"> · {m.created_at} by {m.created_by}</span></div>
          <div className="text-sm"><strong>{m.sent_count}</strong> / {m.recipient_count} sent{d.failed_count ? <> · <span className="text-danger">{d.failed_count} failed</span></> : ''}{d.pending_count && m.status !== 'Sent' ? ` · ${d.pending_count} pending` : ''}{d.read_count ? <> · <span style={{ color: 'var(--success)' }}>{d.read_count} read</span></> : ''} · {d.segments} SMS segment(s)</div>
        </div>
        <div className="msg-body">{m.body}</div>
        {m.attachment && <div className="mt-2"><a href={m.attachment.url} className="attach-link" data-native><i aria-hidden="true" className="fas fa-paperclip" /> {m.attachment.name}{m.attachment.size ? ` · ${m.attachment.size}` : ''}</a></div>}
        <div className="d-flex gap-2 flex-wrap mt-3 align-center">
          {m.status === 'Scheduled' && <button className="btn btn-secondary btn-sm" onClick={() => action(d.urls.cancel_schedule, 'Cancel the scheduled send?')}><i aria-hidden="true" className="fas fa-clock" /> Cancel schedule</button>}
          {d.gateway_ready && d.pending_count > 0 && <button className="btn btn-primary btn-sm" onClick={() => action(d.urls.send_gateway, `Send ${d.pending_count} pending message(s) now via ${d.gateway_label}?`)}><i aria-hidden="true" className="fas fa-tower-broadcast" /> Send all via {d.gateway_label} ({d.pending_count})</button>}
          <button className="btn btn-secondary btn-sm" onClick={copyNumbers}><i aria-hidden="true" className={'fas ' + (copied ? 'fa-check' : 'fa-copy')} /> {copied ? 'Copied!' : 'Copy all numbers'}</button>
          <button className="btn btn-secondary btn-sm" onClick={() => action(d.urls.mark_all_sent, `Mark all ${m.recipient_count} recipients as sent?`)}><i aria-hidden="true" className="fas fa-check-double" /> Mark all sent</button>
          {d.is_admin && <button className="btn btn-danger btn-sm" style={{ marginLeft: 'auto' }} onClick={() => action(d.urls.delete, 'Delete this campaign and its log?', true)}><i aria-hidden="true" className="fas fa-trash" /> Delete</button>}
        </div>
      </div></div>

      <div className="card"><div className="card-header"><h3>Recipients ({rows.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Parent</th><th>Student</th><th>Phone</th><th>Status</th><th>Send</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>
                <td data-label="Parent">{r.parent_name}</td>
                <td data-label="Student">{r.student_name}</td>
                <td data-label="Phone"><a href={'tel:' + r.phone}>{r.phone}</a></td>
                <td data-label="Status"><span className={statusBadge(r.status)}>{r.status}</span>
                  {r.read && <span className="badge badge-success" style={{ marginLeft: '.3rem' }} title="Opened"><i aria-hidden="true" className="fas fa-book-open" /> Read</span>}
                  {r.status === 'Failed' && r.error && <div className="text-danger text-sm" title={r.error}>{r.error.slice(0, 40)}</div>}</td>
                <td className="actions"><div className="act-links">
                  <a className={'btn btn-sm ' + (m.channel === 'SMS' ? 'btn-secondary' : 'wa-btn')} href={linkFor(r)} target="_blank" rel="noopener" title={m.channel === 'SMS' ? 'Open SMS' : 'Open WhatsApp'} onClick={() => markSent(r)}>
                    <i aria-hidden="true" className={'fa' + (m.channel === 'SMS' ? 's fa-comment-sms' : 'b fa-whatsapp')} /></a>
                  <a className="btn btn-secondary btn-sm" href={'tel:' + r.phone} title="Call"><i aria-hidden="true" className="fas fa-phone" /></a>
                  {r.status !== 'Sent' && <button className="btn btn-secondary btn-sm" title="Mark sent" onClick={() => markSent(r)}><i aria-hidden="true" className="fas fa-check" /></button>}
                </div></td>
              </tr>))}
            </tbody></table></div>
        </div></div>
    </>
  );
}

// ---- Settings --------------------------------------------------------------
function Settings({ d, notify }) {
  const nav = useNav();
  const [cfg, setCfg] = useState(d.cfg);
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setCfg((s) => ({ ...s, [k]: v }));
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.urls.save, cfg);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const test = async (e) => {
    e.preventDefault();
    if (!phone.trim()) { notify('error', 'Enter a phone number to send the test to.'); return; }
    const r = await submitJson(d.urls.test, { phone });
    if (r.ok) notify('success', r.message); else notify('error', r.error || 'Test failed.');
  };
  const [autos, setAutos] = useState(d.automations || []);
  const toggleAuto = (key) => setAutos((a) => a.map((x) => (x.key === key ? { ...x, enabled: !x.enabled } : x)));
  const saveAutos = async () => {
    const fields = {};
    autos.forEach((a) => { if (a.enabled) fields[a.key] = 'on'; });
    const r = await submitJson(d.urls.save_automations, fields);
    if (r.ok) notify('success', r.message); else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>Communication Settings</h1></div>
      <Tabs d={d} />
      {d.configured ? (
        <div className="status-banner ok"><i aria-hidden="true" className="fas fa-circle-check" /><div><strong>SMS sending is active</strong> via {d.provider_label}. Campaigns can now be sent automatically from the server.
          {d.balance_ok ? <><br /><strong>Balance:</strong> {d.balance}</> : <><br /><span className="text-muted">Balance unavailable{d.balance ? ` (${d.balance})` : ''}.</span></>}</div></div>
      ) : (
        <div className="status-banner off"><i aria-hidden="true" className="fas fa-circle-info" /><div><strong>SMS auto-send is off.</strong> Messages currently use manual WhatsApp / SMS links. Add your provider key below and it starts working immediately — no other changes needed.</div></div>
      )}

      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-gear" /> Provider Configuration</h3></div>
        <div className="card-body">
          {!d.is_admin && <p className="text-muted text-sm">Only administrators can change gateway settings.</p>}
          <form onSubmit={save}>
            <fieldset disabled={!d.is_admin} style={{ border: 0, padding: 0, margin: 0 }}>
              <div className="form-group"><label className="form-label">SMS Provider</label>
                <select className="form-control" value={cfg.provider} onChange={(e) => set('provider', e.target.value)}>
                  {d.providers.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select></div>
              <div className="form-group"><label className="form-label">Sender ID / From number</label>
                <input type="text" className="form-control" value={cfg.sender} placeholder="e.g. SchoolName (Termii) or +1415… (Twilio)" onChange={(e) => set('sender', e.target.value)} />
                <span className="form-hint d-block">Termii: your approved alphanumeric sender ID. Twilio: your Twilio phone number in +E.164 format.</span></div>
              {cfg.provider === 'termii' && (
                <div className="form-group"><label className="form-label">Termii API Key</label>
                  <input type="text" name="termii_key" className="form-control" value={cfg.termii_key} placeholder="Paste your Termii API key" autoComplete="off" onChange={(e) => set('termii_key', e.target.value)} /></div>)}
              {cfg.provider === 'twilio' && (
                <div className="form-row">
                  <div className="form-group"><label className="form-label">Twilio Account SID</label><input type="text" className="form-control" value={cfg.twilio_sid} placeholder="ACxxxx…" autoComplete="off" onChange={(e) => set('twilio_sid', e.target.value)} /></div>
                  <div className="form-group"><label className="form-label">Twilio Auth Token</label><input type="password" className="form-control" value={cfg.twilio_token} placeholder="Auth token" autoComplete="off" onChange={(e) => set('twilio_token', e.target.value)} /></div>
                </div>)}
              <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save Settings</button>
            </fieldset>
          </form>
        </div></div>

      <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-vial" /> Send a Test SMS</h3></div>
        <div className="card-body">
          {d.configured ? (
            <form onSubmit={test} className="d-flex gap-2 align-end flex-wrap">
              <div className="form-group mb-0" style={{ flex: 1, minWidth: 200 }}><label className="form-label">Phone number</label>
                <input type="text" className="form-control" placeholder="08031234567" required value={phone} onChange={(e) => setPhone(e.target.value)} /></div>
              <button type="submit" className="btn btn-secondary"><i aria-hidden="true" className="fas fa-paper-plane" /> Send Test</button>
            </form>
          ) : <p className="text-muted mb-0">Save a configured provider above to enable the test.</p>}
        </div></div>

      {d.automations && (
        <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-robot" /> Automated notifications</h3></div>
          <div className="card-body">
            {!d.is_admin && <p className="text-muted text-sm">Only administrators can change automations.</p>}
            <p className="text-muted text-sm">Turn each automatic notification on or off. Disabled ones simply don't fire — everything else keeps working.</p>
            <div className="auto-list">
              {autos.map((a) => (
                <label className={'auto-row' + (a.enabled ? '' : ' off')} key={a.key}>
                  <input type="checkbox" checked={a.enabled} disabled={!d.is_admin} onChange={() => toggleAuto(a.key)} />
                  <span className="auto-body"><span className="auto-title">{a.label} <span className="badge badge-secondary">{a.category}</span></span>
                    <span className="auto-desc text-muted text-sm">{a.description}</span></span>
                </label>))}
            </div>
            {d.is_admin && <button type="button" className="btn btn-primary mt-2" onClick={saveAutos}><i aria-hidden="true" className="fas fa-save" /> Save automations</button>}
          </div></div>)}

      <div className="card mt-3"><div className="card-body">
        <h4 style={{ marginTop: 0 }}><i aria-hidden="true" className="fas fa-circle-question" /> How it works</h4>
        <ul className="text-sm text-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.7 }}>
          <li>With no provider, parents are reached via the one-tap WhatsApp / SMS links on each campaign — nothing else required.</li>
          <li>Pick <strong>Termii</strong> or <strong>Twilio</strong>, paste your key, and a <strong>“Send all via gateway”</strong> button appears on every campaign — messages go out from the server automatically.</li>
          <li>Failed numbers are flagged with the provider's error so you can retry.</li>
          <li>Keys are stored in your own database; switch providers any time.</li>
        </ul>
      </div></div>
    </>
  );
}

// ---- Inbox (internal staff messaging) --------------------------------------
function Inbox({ d, notify }) {
  const nav = useNav();
  const active = d.active;
  const [text, setText] = useState('');
  const [att, setAtt] = useState(null);
  const [starting, setStarting] = useState(false);
  const [picked, setPicked] = useState([]);   // [{id,label}] for a new conversation
  const [groupTitle, setGroupTitle] = useState('');
  const endRef = useRef();
  useEffect(() => { if (endRef.current) endRef.current.scrollIntoView(); }, [active && active.id, active && active.messages.length]);

  const openConv = (id) => nav.go(d.urls.thread + id);
  const send = async (e) => {
    e.preventDefault();
    if (!text.trim() && !att) return;
    const r = await submitJson(active.send_url, { body: text, attachment_id: att ? att.id : '' });
    if (r.ok) { setText(''); setAtt(null); nav.refresh(); } else notify('error', r.error || 'Could not send.');
  };
  const startConv = async () => {
    if (!picked.length) { notify('error', 'Pick at least one person.'); return; }
    const r = await submitJson(d.urls.start, { user_ids: picked.map((p) => p.id), title: groupTitle });
    if (r.ok) { setStarting(false); setPicked([]); setGroupTitle(''); nav.go(r.redirect); }
    else notify('error', r.error || 'Could not start.');
  };

  return (
    <>
      <div className="page-header"><h1>Inbox</h1>
        <div className="page-header-actions"><button className="btn btn-primary" onClick={() => setStarting(true)}><i aria-hidden="true" className="fas fa-pen-to-square" /> New conversation</button></div>
      </div>
      <Tabs d={d} />
      {starting && (
        <div className="card mb-3"><div className="card-header"><h3>New conversation</h3></div>
          <div className="card-body">
            <UserPicker url={d.urls.users} onAdd={(o) => setPicked((p) => (p.some((x) => x.id === o.id) ? p : [...p, o]))} />
            <div className="mb-2">{picked.map((p) => <span className="chip" key={p.id}>{p.label} <button type="button" onClick={() => setPicked((s) => s.filter((x) => x.id !== p.id))}>×</button></span>)}</div>
            {picked.length > 1 && <div className="form-group"><label className="form-label">Group name</label><input className="form-control" value={groupTitle} onChange={(e) => setGroupTitle(e.target.value)} placeholder="e.g. Exams committee" /></div>}
            <button className="btn btn-primary btn-sm" onClick={startConv}><i aria-hidden="true" className="fas fa-paper-plane" /> Start</button>
            <button className="btn btn-link btn-sm" onClick={() => setStarting(false)}>Cancel</button>
          </div></div>)}

      <div className="inbox-grid">
        <div className="inbox-list">
          {(d.conversations || []).length ? d.conversations.map((c) => (
            <button key={c.id} className={'conv-item' + (active && active.id === c.id ? ' on' : '')} onClick={() => openConv(c.id)}>
              <div className="conv-top"><span className="conv-title">{c.kind === 'group' ? <i aria-hidden="true" className="fas fa-users" /> : <i aria-hidden="true" className="fas fa-user" />} {c.title}</span>
                {c.unread > 0 && <span className="badge badge-danger">{c.unread}</span>}</div>
              <div className="conv-last">{c.last || 'No messages yet'}</div>
              <div className="conv-at">{c.last_at}</div>
            </button>
          )) : <Empty icon="fa-comments" title="No conversations"><p>Start one to message a colleague.</p></Empty>}
        </div>
        <div className="inbox-thread">
          {active ? (
            <>
              <div className="thread-head"><strong>{active.title}</strong> {active.kind === 'group' && <span className="badge badge-secondary">Group</span>}</div>
              <div className="thread-body">
                {active.messages.length ? active.messages.map((m) => (
                  <div key={m.id} className={'bub-row' + (m.mine ? ' mine' : '')}>
                    <div className="bub">
                      {!m.mine && active.kind === 'group' && <div className="bub-sender">{m.sender}</div>}
                      {m.body && <div>{m.body}</div>}
                      {m.attachment && <a href={m.attachment.url} className="attach-link" data-native><i aria-hidden="true" className="fas fa-paperclip" /> {m.attachment.name}</a>}
                      <div className="bub-at">{m.at}</div>
                    </div>
                  </div>
                )) : <div className="text-muted text-sm" style={{ padding: '1rem' }}>No messages yet — say hello.</div>}
                <div ref={endRef} />
              </div>
              <form className="thread-compose" onSubmit={send}>
                <AttachField url={d.urls.upload} value={att} onChange={setAtt} notify={notify} />
                <input className="form-control" placeholder="Write a message…" value={text} onChange={(e) => setText(e.target.value)} />
                <button type="submit" className="btn btn-primary" aria-label="Send"><i aria-hidden="true" className="fas fa-paper-plane" /></button>
              </form>
            </>
          ) : <div className="thread-empty"><Empty icon="fa-comment-dots" title="Select a conversation"><p>Or start a new one.</p></Empty></div>}
        </div>
      </div>
    </>
  );
}

// Staff-user type-ahead for starting a conversation.
function UserPicker({ url, onAdd }) {
  const [text, setText] = useState('');
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const tRef = useRef();
  const onInput = (v) => {
    setText(v); clearTimeout(tRef.current);
    if (v.trim().length < 2) { setList([]); setOpen(false); return; }
    tRef.current = setTimeout(async () => {
      try { const r = await fetch(url + '?q=' + encodeURIComponent(v.trim()), { credentials: 'same-origin' });
        const rows = await r.json(); setList(rows); setOpen(rows.length > 0); } catch (_) { /* ignore */ }
    }, 220);
  };
  const pick = (o) => { onAdd({ id: o.id, label: o.label || o.name }); setText(''); setList([]); setOpen(false); };
  return (
    <div className="form-group ac-wrap">
      <label className="form-label">Add people</label>
      <input type="text" className="form-control" placeholder="Search staff by name…" autoComplete="off"
             value={text} onChange={(e) => onInput(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && <div className="ac-list">{list.map((o) => <div key={o.id} onMouseDown={() => pick(o)}>{o.label || o.name}</div>)}</div>}
    </div>
  );
}

const SCREENS = { dashboard: Dashboard, compose: Compose, announcements: Announcements,
  templates: Templates, contacts: Contacts, messages: Messages, message_detail: MessageDetail,
  reports: Reports, settings: Settings, inbox: Inbox };

export default function CommunicationApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Dashboard;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}

// ---- Compose (kept at the bottom; the most complex screen) ------------------
function Compose({ d, notify }) {
  const nav = useNav();
  const canStaff = !!d.is_admin;
  const [to, setTo] = useState(d.pre_to || 'parents');       // parents | staff
  const [pickedStaff, setPickedStaff] = useState(d.pre_staff || []);   // [{id,label}] specific staff
  const [audience, setAudience] = useState(d.pre_audience || 'all');
  const [termId, setTermId] = useState(d.term_id);
  const [classId, setClassId] = useState(d.pre_class || '');
  const [armId, setArmId] = useState('');
  const [picked, setPicked] = useState(d.pre_students || []);   // [{id,label}]
  const [excluded, setExcluded] = useState([]);   // [{id,label}] students to drop
  const [gender, setGender] = useState('');
  const [stream, setStream] = useState('');
  const [staffScope, setStaffScope] = useState('all');
  const [deptId, setDeptId] = useState('');
  const [title, setTitle] = useState('');
  const [channel, setChannel] = useState(d.pre_channel || d.channels[0]);
  const [tpl, setTpl] = useState(d.pre_tpl || '');
  const [body, setBody] = useState(d.pre_body || '');
  const [schedule, setSchedule] = useState(false);
  const [scheduledAt, setScheduledAt] = useState('');
  const [att, setAtt] = useState(null);   // email attachment
  const [preview, setPreview] = useState({ reachable: '—', no_phone: 0, sample: 'Your message preview appears here…' });
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef();
  const ptRef = useRef();

  const isEmail = String(channel).toLowerCase() === 'email';
  const isInapp = String(channel).toLowerCase() === 'in-app';
  // In-app notifications reach staff bells, so force the recipient type to staff.
  useEffect(() => { if (isInapp && to !== 'staff' && canStaff) setTo('staff'); /* eslint-disable-next-line */ }, [isInapp]);
  // The recipient selection as a flat spec — shared by preview and submit.
  const buildSpec = () => {
    const sp = { to };
    if (to === 'staff') {
      if (pickedStaff.length) sp.staff_ids = pickedStaff.map((p) => p.id);
      sp.staff_scope = staffScope;
      if (staffScope === 'department' && deptId) sp.department_id = deptId;
    } else {
      sp.audience = audience;
      if (classId) sp.class_id = classId;
      if (armId) sp.arm_id = armId;
      if (audience === 'students') sp.student_ids = picked.map((p) => p.id);
      if (gender) sp.gender = gender;
      if (stream) sp.stream = stream;
    }
    if (excluded.length) sp.exclude_ids = excluded.map((x) => x.id);
    return sp;
  };
  const runPreview = async () => {
    const body2 = new URLSearchParams();
    body2.set('term_id', termId); body2.set('body', body); body2.set('channel', channel);
    Object.entries(buildSpec()).forEach(([k, v]) => {
      if (Array.isArray(v)) v.forEach((x) => body2.append(k, x));
      else if (v !== '' && v != null) body2.set(k, v);
    });
    try {
      const res = await fetch(d.urls.preview, { method: 'POST', credentials: 'same-origin',
        headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrfToken(), 'Content-Type': 'application/x-www-form-urlencoded' }, body: body2 });
      const j = await res.json();
      setPreview({ reachable: j.reachable, no_phone: j.unreachable != null ? j.unreachable : j.no_phone,
        by_email: j.by_email, sample: j.sample || '(no matching recipients)' });
    } catch (_) { /* ignore */ }
  };
  const schedulePreview = () => { clearTimeout(ptRef.current); ptRef.current = setTimeout(runPreview, 400); };
  useEffect(() => { schedulePreview(); /* eslint-disable-next-line */ },
    [to, audience, termId, classId, armId, picked, excluded, gender, stream, staffScope, deptId, pickedStaff, body, channel]);

  const insertPh = (ph) => {
    const el = bodyRef.current; const s = el ? el.selectionStart : body.length; const e = el ? el.selectionEnd : body.length;
    const next = body.slice(0, s) + ph + body.slice(e);
    setBody(next);
    requestAnimationFrame(() => { if (el) { el.focus(); el.selectionStart = el.selectionEnd = s + ph.length; } });
  };
  const onTpl = (id) => { setTpl(id); const t = d.templates.find((x) => String(x.id) === String(id)); if (t) setBody(t.body); };

  // Saved recipient groups: reload a spec into the builder, or save the current one.
  const [groups, setGroups] = useState(d.groups || []);
  const applySpec = (sp) => {
    sp = sp || {};
    setTo(sp.to || 'parents');
    setAudience(sp.audience || 'all');
    setClassId(sp.class_id || '');
    setArmId(sp.arm_id || '');
    setGender(sp.gender || '');
    setStream(sp.stream || '');
    setStaffScope(sp.staff_scope || 'all');
    setDeptId(sp.department_id || '');
    setPicked((sp.student_ids || []).map((id) => ({ id, label: `#${id}` })));
    setExcluded((sp.exclude_ids || []).map((id) => ({ id, label: `#${id}` })));
  };
  const saveGroup = async () => {
    const name = await promptDialog({ title: 'Save recipient group',
      label: 'Group name', placeholder: 'e.g. SS3 Science parents' });
    if (!name || !name.trim()) return;
    const r = await submitJson(d.urls.save_group, { name: name.trim(), overwrite: 'on', ...buildSpec() });
    if (r.ok) { notify('success', r.message); if (!groups.some((g) => g.name === name.trim())) setGroups((gs) => [...gs, { id: `tmp-${Date.now()}`, name: name.trim(), spec: buildSpec() }]); }
    else notify('error', r.error || 'Could not save group.');
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!body.trim()) { notify('error', 'Message body cannot be empty.'); return; }
    setBusy(true);
    const fields = { term_id: termId, title, channel, body,
      schedule: schedule ? 'on' : '', scheduled_at: scheduledAt,
      attachment_id: (isEmail && att) ? att.id : '', ...buildSpec() };
    const r = await submitJson(d.urls.submit, fields);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not create campaign.');
  };

  const charCount = body.length;
  const segs = charCount ? Math.ceil(charCount / 160) : 0;
  const channelReady = isInapp ? true : (isEmail ? d.email_ready : d.gateway_ready);
  const channelLabel = isInapp ? 'In-app' : (isEmail ? 'Email (SMTP)' : (d.gateway_label || 'SMS gateway'));
  const reachNoun = isInapp ? 'account' : (isEmail ? 'email' : 'phone');
  const audCards = [['all', 'fa-users', 'All parents'], ['class', 'fa-school', 'By class'],
    ['defaulters', 'fa-triangle-exclamation', 'Fee defaulters'], ['students', 'fa-user-check', 'Selected']];

  return (
    <>
      <div className="page-header"><h1>Compose Message</h1></div>
      <Tabs d={d} />
      <form onSubmit={submit}>
        <div className="compose-grid">
          <div>
            <div className="card mb-3"><div className="card-header"><h3>1 · Recipients</h3></div>
              <div className="card-body">
                <div className="rc-groups mb-3">
                  <select className="form-control" defaultValue="" onChange={(e) => { const g = groups.find((x) => String(x.id) === e.target.value); if (g) applySpec(g.spec); e.target.value = ''; }}>
                    <option value="">{groups.length ? 'Load a saved group…' : 'No saved groups yet'}</option>
                    {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={saveGroup} title="Save the current selection as a reusable group"><i aria-hidden="true" className="fas fa-bookmark" /> Save</button>
                </div>
                {canStaff && (
                  <div className="seg-toggle mb-3" role="tablist">
                    {[['parents', 'fa-users', 'Parents'], ['staff', 'fa-user-tie', 'Staff']].map(([v, ic, lab]) => (
                      <button type="button" key={v} role="tab" aria-selected={to === v}
                        className={'seg-btn' + (to === v ? ' on' : '')} onClick={() => setTo(v)}>
                        <i aria-hidden="true" className={'fas ' + ic} /> {lab}</button>))}
                  </div>)}

                {to === 'staff' ? (
                  <>
                    {pickedStaff.length > 0 && (
                      <div className="form-group"><label className="form-label">Specific staff</label>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.35rem' }}>
                          {pickedStaff.map((p) => (
                            <span key={p.id} className="badge" style={{ background: 'var(--primary,#0D6A4E)', color: '#fff', display: 'inline-flex', gap: '.4rem', alignItems: 'center' }}>
                              {p.label}
                              <button type="button" aria-label={`Remove ${p.label}`} onClick={() => setPickedStaff((xs) => xs.filter((x) => x.id !== p.id))}
                                style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: 0 }}>×</button>
                            </span>))}
                        </div>
                        <p className="form-hint">Message goes only to the staff above. Clear them to use a group instead.</p>
                      </div>
                    )}
                    {pickedStaff.length === 0 && (
                    <div className="form-group"><label className="form-label">Staff group</label>
                      <select className="form-control" value={staffScope} onChange={(e) => setStaffScope(e.target.value)}>
                        <option value="all">All staff</option>
                        <option value="teaching">Teaching staff</option>
                        <option value="non-teaching">Non-teaching staff</option>
                        <option value="department">By department</option>
                      </select></div>)}
                    {staffScope === 'department' && (
                      <div className="form-group"><label className="form-label">Department</label>
                        <select className="form-control" value={deptId} onChange={(e) => setDeptId(e.target.value)}>
                          <option value="">All departments</option>
                          {(d.departments || []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>)}
                    <p className="form-hint">Messages go straight to each staff member ({isEmail ? 'email' : 'phone'}).</p>
                  </>
                ) : (
                  <>
                    <div className="form-group"><label className="form-label">Term</label>
                      <select className="form-control" value={termId} onChange={(e) => setTermId(e.target.value)}>
                        {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
                    <div className="aud-cards">{audCards.map(([a, ic, t]) => (
                      <div className={'aud-card' + (audience === a ? ' sel' : '')} key={a} onClick={() => setAudience(a)}>
                        <i aria-hidden="true" className={'fas ' + ic} /><div className="t">{t}</div></div>))}
                    </div>
                    {(audience === 'class' || audience === 'defaulters') && (
                      <div className="form-row mt-3">
                        <div className="form-group"><label className="form-label">Class</label>
                          <select className="form-control" value={classId} onChange={(e) => setClassId(e.target.value)}>
                            <option value="">All classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
                        {audience === 'class' && (
                          <div className="form-group"><label className="form-label">Arm</label>
                            <select className="form-control" value={armId} onChange={(e) => setArmId(e.target.value)}>
                              <option value="">All arms</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>)}
                      </div>)}
                    {audience === 'students' && (
                      <div className="mt-3">
                        <StudentPicker url={d.urls.search} label="Add students" onAdd={(o) => setPicked((p) => (p.some((x) => x.id === o.id) ? p : [...p, o]))} />
                        <div>{picked.map((p) => (
                          <span className="chip" key={p.id}>{p.label} <button type="button" onClick={() => setPicked((s) => s.filter((x) => x.id !== p.id))}>×</button></span>))}</div>
                      </div>)}

                    <details className="rc-more mt-3">
                      <summary>Refine &amp; exclude</summary>
                      <div className="form-row mt-2">
                        <div className="form-group"><label className="form-label">Gender</label>
                          <select className="form-control" value={gender} onChange={(e) => setGender(e.target.value)}>
                            <option value="">Any</option>{(d.genders || []).map((g) => <option key={g} value={g}>{g}</option>)}</select></div>
                        <div className="form-group"><label className="form-label">Stream</label>
                          <select className="form-control" value={stream} onChange={(e) => setStream(e.target.value)}>
                            <option value="">Any</option>{(d.streams || []).map((x) => <option key={x} value={x}>{x}</option>)}</select></div>
                      </div>
                      <StudentPicker url={d.urls.search} label="Exclude students" onAdd={(o) => setExcluded((p) => (p.some((x) => x.id === o.id) ? p : [...p, o]))} />
                      <div>{excluded.map((p) => (
                        <span className="chip chip-danger" key={p.id}>− {p.label} <button type="button" onClick={() => setExcluded((s) => s.filter((x) => x.id !== p.id))}>×</button></span>))}</div>
                    </details>
                  </>
                )}
              </div></div>

            <div className="card"><div className="card-header"><h3>2 · Message</h3></div>
              <div className="card-body">
                <div className="form-row">
                  <div className="form-group"><label className="form-label">{isEmail ? 'Email subject' : 'Title (internal)'}</label><input type="text" className="form-control" placeholder={isEmail ? 'e.g., June fee reminder' : 'e.g., June fee reminder'} value={title} onChange={(e) => setTitle(e.target.value)} /></div>
                  <div className="form-group"><label className="form-label">Channel</label><select className="form-control" value={channel} onChange={(e) => setChannel(e.target.value)}>{d.channels.map((ch) => <option key={ch} value={ch}>{ch}</option>)}</select></div>
                </div>
                <div className="form-group"><label className="form-label">Use a template</label>
                  <select className="form-control" value={tpl} onChange={(e) => onTpl(e.target.value)}>
                    <option value="">— Start from scratch —</option>
                    {d.templates.map((t) => <option key={t.id} value={t.id}>{t.name}{t.category ? ` · ${t.category}` : ''}</option>)}</select></div>
                <div className="form-group mb-0"><label className="form-label">Message body <span className="required">*</span></label>
                  <div className="ph-btns">{d.placeholders.map((p) => <span className="ph-btn" key={p} onClick={() => insertPh(p)}>{p}</span>)}</div>
                  <textarea ref={bodyRef} className="form-control" rows="6" required placeholder="Type your message. Tap a tag above to personalise it." value={body} onChange={(e) => setBody(e.target.value)} />
                  <div className="seg-info"><span>{charCount} character{charCount === 1 ? '' : 's'}</span><span>{isInapp ? 'In-app notice' : (isEmail ? 'Email body' : `${segs} SMS segment${segs === 1 ? '' : 's'}`)}</span></div>
                </div>
                {isEmail && (
                  <div className="form-group mb-0 mt-2"><label className="form-label">Attachment</label>
                    <AttachField url={d.urls.upload} value={att} onChange={setAtt} notify={notify} /></div>)}
              </div></div>
          </div>

          <div>
            <div className="card mb-3" style={{ position: 'sticky', top: '1rem' }}><div className="card-header"><h3>3 · Preview &amp; send</h3></div>
              <div className="card-body">
                <div className="d-flex gap-2 align-center mb-2" style={{ fontSize: 'var(--text-sm)' }}>
                  <span className="badge badge-info">{preview.reachable} recipient{preview.reachable === 1 ? '' : 's'}</span>
                  <span className="text-muted">{preview.no_phone ? `${preview.no_phone} have no ${reachNoun}` : ''}</span>
                </div>
                <div className="text-muted text-sm mb-1">Sample (first recipient):</div>
                <div className="preview-phone mb-3"><div className="bubble">{preview.sample}</div></div>
                <button type="button" className="btn btn-secondary w-100 mb-2" onClick={runPreview}><i aria-hidden="true" className="fas fa-rotate" /> Refresh preview</button>
                {channelReady && !isInapp && (<>
                  <label className="form-check mb-2"><input type="checkbox" checked={schedule} onChange={(e) => setSchedule(e.target.checked)} /> Schedule for later</label>
                  {schedule && <div className="form-group"><label className="form-label">Send at</label>
                    <input type="datetime-local" className="form-control" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
                    <span className="form-hint d-block">The campaign will auto-send via {channelLabel} at this time.</span></div>}
                </>)}
                <button type="submit" className="btn btn-primary w-100" disabled={busy}><i aria-hidden="true" className="fas fa-paper-plane" /> {isInapp ? 'Send notification' : (schedule ? 'Schedule campaign' : 'Create campaign')}</button>
                {isInapp
                  ? <p className="text-muted text-sm mt-2 mb-0"><i aria-hidden="true" className="fas fa-bell" style={{ color: 'var(--success)' }} /> Posts instantly to the notification bell of each staff member with an account.</p>
                  : channelReady
                    ? <p className="text-muted text-sm mt-2 mb-0"><i aria-hidden="true" className="fas fa-tower-broadcast" style={{ color: 'var(--success)' }} /> {channelLabel} active — after creating, send to everyone automatically with one tap.</p>
                    : (isEmail
                      ? <p className="text-muted text-sm mt-2 mb-0"><i aria-hidden="true" className="fas fa-circle-info" /> Email isn't configured yet. You can still create the campaign and review recipients; set up SMTP to send.</p>
                      : <p className="text-muted text-sm mt-2 mb-0"><i aria-hidden="true" className="fas fa-circle-info" /> You'll get a recipient list with one-tap WhatsApp / SMS links and a CSV export. <a href={d.urls.settings}>Add an SMS gateway</a> to auto-send.</p>)}
              </div></div>
          </div>
        </div>
      </form>
    </>
  );
}

// Student type-ahead that returns the picked {id,label} to the caller.
function StudentPicker({ url, onAdd, label = 'Add students' }) {
  const [text, setText] = useState('');
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const tRef = useRef();
  const onInput = (v) => {
    setText(v); clearTimeout(tRef.current);
    if (v.trim().length < 2) { setList([]); setOpen(false); return; }
    tRef.current = setTimeout(async () => {
      try { const r = await fetch(url + '?q=' + encodeURIComponent(v.trim()), { credentials: 'same-origin' });
        const rows = await r.json(); setList(rows); setOpen(rows.length > 0); } catch (_) { /* ignore */ }
    }, 220);
  };
  const pick = (o) => { onAdd({ id: o.id, label: o.label || o.name }); setText(''); setList([]); setOpen(false); };
  return (
    <div className="form-group ac-wrap">
      <label className="form-label">{label}</label>
      <input type="text" className="form-control" placeholder="Search name or ID…" autoComplete="off"
             value={text} onChange={(e) => onInput(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && <div className="ac-list">{list.map((o) => <div key={o.id} onMouseDown={() => pick(o)}>{o.label || `${o.name} (${o.sid})`}</div>)}</div>}
    </div>
  );
}
