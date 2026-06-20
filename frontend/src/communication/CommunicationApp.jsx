import React, { useState, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, SectionTabs, Empty, Autocomplete } from '../components/ui';

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'], ['compose', 'fa-paper-plane', 'Compose'],
  ['announcements', 'fa-bullhorn', 'Announcements'], ['messages', 'fa-clock-rotate-left', 'History'],
  ['templates', 'fa-file-lines', 'Templates'], ['contacts', 'fa-address-book', 'Contacts'],
  ['settings', 'fa-gear', 'Settings'],
];
// A few pages map onto a tab that isn't their own page key.
const TAB_FOR = { message_detail: 'messages' };

function Tabs({ d }) {
  const nav = useNav();
  return <SectionTabs tabs={TABS} urls={d.nav} active={TAB_FOR[d.page] || d.page} go={nav.go} />;
}

const channelBadge = (ch) => 'badge ' + (ch === 'WhatsApp' ? 'badge-success' : 'badge-info');

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
          backgroundColor: ['#25D366', '#4e73df', '#f6c23e', '#7e6cf0'], borderWidth: 0 }] },
      options: { maintainAspectRatio: false, cutout: '58%',
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } } },
    });
    return () => chart.destroy();
  }, [d.channel_chart]);

  const kpis = [['blue', 'fa-bullhorn', d.total_campaigns, 'Campaigns'],
    ['teal', 'fa-users', d.total_recipients, 'Recipients'],
    ['green', 'fa-paper-plane', d.total_sent, 'Marked sent'],
    ['amber', 'fa-address-book', d.cov.pct + '%', 'Contact coverage']];

  return (
    <>
      <div className="page-header"><h1>Parent Communication</h1>
        <div className="page-header-actions"><a href={d.nav.compose} className="btn btn-primary"><i aria-hidden="true" className="fas fa-paper-plane" /> New Message</a></div>
      </div>
      <Tabs d={d} />
      <div className="kpi-row">{kpis.map(([c, ic, v, l]) => (
        <div className="kpi" key={l}><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div>
          <div><div className="v">{v}</div><div className="l">{l}</div></div></div>))}
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
                <thead><tr><th>Date</th><th>Title</th><th>Audience</th><th>Channel</th><th className="text-right">Sent</th></tr></thead>
                <tbody>{d.recent.map((m) => (
                  <tr key={m.id}><td data-label="Date">{m.date}</td>
                    <td data-label="Title"><a href={m.url}>{m.title}</a></td>
                    <td data-label="Audience" className="text-muted text-sm">{m.audience_label}</td>
                    <td data-label="Channel"><span className={channelBadge(m.channel)}>{m.channel}</span></td>
                    <td data-label="Sent" className="text-right">{m.sent_count}/{m.recipient_count}</td></tr>))}
                </tbody></table></div>
            ) : <Empty icon="fa-paper-plane" title="No campaigns yet"><a href={d.nav.compose} className="btn btn-primary btn-sm mt-2">Send your first message</a></Empty>}
          </div></div>
      </div>

      <div className="card"><div className="card-body d-flex gap-2 flex-wrap align-center">
        <i aria-hidden="true" className="fas fa-lightbulb" style={{ color: 'var(--warning)', fontSize: '1.3rem' }} />
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
  const [f, setF] = useState({ title: '', body: '', category: 'Info', audience: 'All', starts_on: '', ends_on: '', is_pinned: false });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Title is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.add_url, { ...f, is_pinned: f.is_pinned ? 'on' : '' });
    setBusy(false);
    if (r.ok) { setF({ title: '', body: '', category: 'Info', audience: 'All', starts_on: '', ends_on: '', is_pinned: false }); nav.refresh(); }
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
          </div>
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
                  {!a.is_active && <span className="badge badge-secondary">Inactive</span>}</div>
                <button className="btn btn-danger btn-sm" onClick={() => del(a.delete_url)}><i aria-hidden="true" className="fas fa-trash" /></button>
              </div>
              {a.body && <div className="text-secondary text-sm mt-1">{a.body}</div>}
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
  const [f, setF] = useState({ name: '', category: '', body: '' });
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
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

      <div className="card"><div className="card-header"><h3>Templates ({d.templates.length})</h3></div>
        <div className="card-body">
          {d.templates.length ? d.templates.map((t) => (
            <div className="tpl-card" key={t.id}>
              <div className="d-flex justify-between align-center flex-wrap gap-1">
                <div><strong>{t.name}</strong> {t.category && <span className="badge badge-secondary">{t.category}</span>} {!t.is_active && <span className="badge badge-warning">Inactive</span>}</div>
                <div className="d-flex gap-1">
                  <a href={t.use_url} className="btn btn-primary btn-sm" title="Use"><i aria-hidden="true" className="fas fa-paper-plane" /></a>
                  <button className="btn btn-secondary btn-sm" title="Edit" onClick={() => setEditing(editing === t.id ? null : t.id)}><i aria-hidden="true" className="fas fa-edit" /></button>
                  <button className="btn btn-danger btn-sm" onClick={() => del(t.delete_url, t.name)}><i aria-hidden="true" className="fas fa-trash" /></button>
                </div>
              </div>
              <div className="body">{t.body}</div>
              {editing === t.id && <EditTemplate t={t} notify={notify} onDone={() => { setEditing(null); nav.refresh(); }} />}
            </div>
          )) : <Empty icon="fa-file-lines" title="No templates"><p>Create reusable messages with placeholders.</p></Empty>}
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

// ---- Message history -------------------------------------------------------
function Messages({ d, notify }) {
  const nav = useNav();
  const processDue = async () => {
    const r = await submitJson(d.urls.process_scheduled, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Failed.');
  };
  return (
    <>
      <div className="page-header"><h1>Message History</h1>
        <div className="page-header-actions">
          {d.is_admin && <button className="btn btn-secondary" title="Send any scheduled campaigns that are now due" onClick={processDue}><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Process due</button>}
          <a href={d.urls.compose} className="btn btn-primary"><i aria-hidden="true" className="fas fa-paper-plane" /> New Message</a>
        </div>
      </div>
      <Tabs d={d} />
      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.messages.length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>Date</th><th>Title</th><th>Audience</th><th>Channel</th><th className="text-right">Recipients</th><th className="text-right">Sent</th><th /></tr></thead>
            <tbody>{d.messages.map((m) => (
              <tr key={m.id}><td data-label="Date">{m.date}</td>
                <td data-label="Title"><a href={m.url}><strong>{m.title}</strong></a>{m.status === 'Scheduled' && m.scheduled_at && <> <span className="badge badge-warning"><i aria-hidden="true" className="fas fa-clock" /> {m.scheduled_at}</span></>}</td>
                <td data-label="Audience" className="text-muted text-sm">{m.audience_label}</td>
                <td data-label="Channel"><span className={channelBadge(m.channel)}>{m.channel}</span></td>
                <td data-label="Recipients" className="text-right">{m.recipient_count}</td>
                <td data-label="Sent" className="text-right">{m.sent_count}</td>
                <td className="actions"><a href={m.url} className="btn btn-secondary btn-sm" aria-label="Open"><i aria-hidden="true" className="fas fa-arrow-right" /></a></td></tr>))}
            </tbody></table></div>
        ) : <Empty icon="fa-paper-plane" title="No messages yet"><p>Compose your first parent broadcast.</p><a href={d.urls.compose} className="btn btn-primary mt-2">Compose</a></Empty>}
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
  const statusBadge = (s) => 'badge ' + (s === 'Sent' ? 'badge-success' : s === 'Failed' ? 'badge-danger' : 'badge-warning');

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
          <div className="text-sm"><strong>{m.sent_count}</strong> / {m.recipient_count} sent{d.failed_count ? <> · <span className="text-danger">{d.failed_count} failed</span></> : ''}{d.pending_count && m.status !== 'Sent' ? ` · ${d.pending_count} pending` : ''} · {d.segments} SMS segment(s)</div>
        </div>
        <div className="msg-body">{m.body}</div>
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
  return (
    <>
      <div className="page-header"><h1>SMS Gateway</h1></div>
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

const SCREENS = { dashboard: Dashboard, compose: Compose, announcements: Announcements,
  templates: Templates, contacts: Contacts, messages: Messages, message_detail: MessageDetail,
  settings: Settings };

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
  const [audience, setAudience] = useState(d.pre_audience || 'all');
  const [termId, setTermId] = useState(d.term_id);
  const [classId, setClassId] = useState(d.pre_class || '');
  const [armId, setArmId] = useState('');
  const [picked, setPicked] = useState([]);   // [{id,label}]
  const [title, setTitle] = useState('');
  const [channel, setChannel] = useState(d.channels[0]);
  const [tpl, setTpl] = useState(d.pre_tpl || '');
  const [body, setBody] = useState(d.pre_body || '');
  const [schedule, setSchedule] = useState(false);
  const [scheduledAt, setScheduledAt] = useState('');
  const [preview, setPreview] = useState({ reachable: '—', no_phone: 0, sample: 'Your message preview appears here…' });
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef();
  const ptRef = useRef();

  const runPreview = async () => {
    const body2 = new URLSearchParams();
    body2.set('term_id', termId); body2.set('audience', audience); body2.set('body', body);
    if (classId) body2.set('class_id', classId);
    if (armId) body2.set('arm_id', armId);
    picked.forEach((p) => body2.append('student_ids', p.id));
    try {
      const res = await fetch(d.urls.preview, { method: 'POST', credentials: 'same-origin',
        headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrfToken(), 'Content-Type': 'application/x-www-form-urlencoded' }, body: body2 });
      const j = await res.json();
      setPreview({ reachable: j.reachable, no_phone: j.no_phone, sample: j.sample || '(no matching recipients)' });
    } catch (_) { /* ignore */ }
  };
  const schedulePreview = () => { clearTimeout(ptRef.current); ptRef.current = setTimeout(runPreview, 400); };
  useEffect(() => { schedulePreview(); /* eslint-disable-next-line */ }, [audience, termId, classId, armId, picked, body]);

  const insertPh = (ph) => {
    const el = bodyRef.current; const s = el ? el.selectionStart : body.length; const e = el ? el.selectionEnd : body.length;
    const next = body.slice(0, s) + ph + body.slice(e);
    setBody(next);
    requestAnimationFrame(() => { if (el) { el.focus(); el.selectionStart = el.selectionEnd = s + ph.length; } });
  };
  const onTpl = (id) => { setTpl(id); const t = d.templates.find((x) => String(x.id) === String(id)); if (t) setBody(t.body); };

  const submit = async (e) => {
    e.preventDefault();
    if (!body.trim()) { notify('error', 'Message body cannot be empty.'); return; }
    setBusy(true);
    const fields = { term_id: termId, audience, title, channel, body,
      class_id: classId || '', arm_id: armId || '',
      student_ids: picked.map((p) => p.id),
      schedule: schedule ? 'on' : '', scheduled_at: scheduledAt };
    const r = await submitJson(d.urls.submit, fields);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not create campaign.');
  };

  const charCount = body.length;
  const segs = charCount ? Math.ceil(charCount / 160) : 0;
  const audCards = [['all', 'fa-users', 'All parents'], ['class', 'fa-school', 'By class'],
    ['defaulters', 'fa-triangle-exclamation', 'Fee defaulters'], ['students', 'fa-user-check', 'Selected']];

  return (
    <>
      <div className="page-header"><h1>Compose Message</h1></div>
      <Tabs d={d} />
      <form onSubmit={submit}>
        <div className="compose-grid">
          <div>
            <div className="card mb-3"><div className="card-header"><h3>1 · Audience</h3></div>
              <div className="card-body">
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
                    <StudentPicker url={d.urls.search} onAdd={(o) => setPicked((p) => (p.some((x) => x.id === o.id) ? p : [...p, o]))} />
                    <div>{picked.map((p) => (
                      <span className="chip" key={p.id}>{p.label} <button type="button" onClick={() => setPicked((s) => s.filter((x) => x.id !== p.id))}>×</button></span>))}</div>
                  </div>)}
              </div></div>

            <div className="card"><div className="card-header"><h3>2 · Message</h3></div>
              <div className="card-body">
                <div className="form-row">
                  <div className="form-group"><label className="form-label">Title (internal)</label><input type="text" className="form-control" placeholder="e.g., June fee reminder" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
                  <div className="form-group"><label className="form-label">Channel</label><select className="form-control" value={channel} onChange={(e) => setChannel(e.target.value)}>{d.channels.map((ch) => <option key={ch} value={ch}>{ch}</option>)}</select></div>
                </div>
                <div className="form-group"><label className="form-label">Use a template</label>
                  <select className="form-control" value={tpl} onChange={(e) => onTpl(e.target.value)}>
                    <option value="">— Start from scratch —</option>
                    {d.templates.map((t) => <option key={t.id} value={t.id}>{t.name}{t.category ? ` · ${t.category}` : ''}</option>)}</select></div>
                <div className="form-group mb-0"><label className="form-label">Message body <span className="required">*</span></label>
                  <div className="ph-btns">{d.placeholders.map((p) => <span className="ph-btn" key={p} onClick={() => insertPh(p)}>{p}</span>)}</div>
                  <textarea ref={bodyRef} className="form-control" rows="6" required placeholder="Type your message. Tap a tag above to personalise it." value={body} onChange={(e) => setBody(e.target.value)} />
                  <div className="seg-info"><span>{charCount} character{charCount === 1 ? '' : 's'}</span><span>{segs} SMS segment{segs === 1 ? '' : 's'}</span></div>
                </div>
              </div></div>
          </div>

          <div>
            <div className="card mb-3" style={{ position: 'sticky', top: '1rem' }}><div className="card-header"><h3>3 · Preview &amp; send</h3></div>
              <div className="card-body">
                <div className="d-flex gap-2 align-center mb-2" style={{ fontSize: '.85rem' }}>
                  <span className="badge badge-info">{preview.reachable} recipient{preview.reachable === 1 ? '' : 's'}</span>
                  <span className="text-muted">{preview.no_phone ? `${preview.no_phone} have no phone` : ''}</span>
                </div>
                <div className="text-muted text-sm mb-1">Sample (first recipient):</div>
                <div className="preview-phone mb-3"><div className="bubble">{preview.sample}</div></div>
                <button type="button" className="btn btn-secondary w-100 mb-2" onClick={runPreview}><i aria-hidden="true" className="fas fa-rotate" /> Refresh preview</button>
                {d.gateway_ready && (<>
                  <label className="form-check mb-2"><input type="checkbox" checked={schedule} onChange={(e) => setSchedule(e.target.checked)} /> Schedule for later</label>
                  {schedule && <div className="form-group"><label className="form-label">Send at</label>
                    <input type="datetime-local" className="form-control" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
                    <span className="form-hint d-block">The campaign will auto-send via {d.gateway_label} at this time.</span></div>}
                </>)}
                <button type="submit" className="btn btn-primary w-100" disabled={busy}><i aria-hidden="true" className="fas fa-paper-plane" /> {schedule ? 'Schedule campaign' : 'Create campaign'}</button>
                {d.gateway_ready
                  ? <p className="text-muted text-sm mt-2 mb-0"><i aria-hidden="true" className="fas fa-tower-broadcast" style={{ color: 'var(--success)' }} /> SMS gateway active ({d.gateway_label}) — after creating, send all automatically with one tap, or use the WhatsApp / SMS links.</p>
                  : <p className="text-muted text-sm mt-2 mb-0"><i aria-hidden="true" className="fas fa-circle-info" /> You'll get a recipient list with one-tap WhatsApp / SMS links and a CSV export. <a href={d.urls.settings}>Add an SMS gateway</a> to auto-send.</p>}
              </div></div>
          </div>
        </div>
      </form>
    </>
  );
}

// Student type-ahead that returns the picked {id,label} to the caller.
function StudentPicker({ url, onAdd }) {
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
      <label className="form-label">Add students</label>
      <input type="text" className="form-control" placeholder="Search name or ID…" autoComplete="off"
             value={text} onChange={(e) => onInput(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && <div className="ac-list">{list.map((o) => <div key={o.id} onMouseDown={() => pick(o)}>{o.label || `${o.name} (${o.sid})`}</div>)}</div>}
    </div>
  );
}
