// Communication — one React app for the whole section (overview, compose,
// inbox, announcements, history, campaign detail, reports, templates,
// contacts, settings). Built on the shared results kit so it feels like a
// native app on phones (bottom sheets, full-screen chat, pinned send bar) and
// a native desktop app on laptops (two-pane inbox, live preview beside the
// composer, compact lists). Server routes, payloads and permissions are
// unchanged: every action posts to the same endpoints as before.
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, promptDialog, SectionShell, Toast } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Chips, Sheet, Menu, Blank, Bar, Meter, usePhone, initials } from '../subjects/results';

// ---- helpers -----------------------------------------------------------------
const plural = (n, w, p) => `${n} ${n === 1 ? w : (p || w + 's')}`;
const A = ({ to, className, children, title, native, ...rest }) => {
  const nav = useNav();
  if (native) return <a href={to} className={className} title={title} data-native {...rest}>{children}</a>;
  return <a href={to} title={title} className={className} onClick={(e) => { e.preventDefault(); nav.go(to); }} {...rest}>{children}</a>;
};
// channel → [icon classes, tone class]
const CH = {
  SMS: ['fas fa-comment-sms', 'sms'], WhatsApp: ['fab fa-whatsapp', 'wa'], Email: ['fas fa-envelope', 'em'],
  'In-app': ['fas fa-bell', 'app'], Announcement: ['fas fa-bullhorn', 'ann'],
};
const chMeta = (c) => CH[c] || ['fas fa-paper-plane', 'sms'];
const ChIcon = ({ ch, size }) => <span className={'cm-ch ' + chMeta(ch)[1] + (size ? ' ' + size : '')} aria-hidden="true"><i className={chMeta(ch)[0]} /></span>;
const STATUS_TONE = { Sent: 'good', Posted: 'good', Delivered: 'good', Failed: 'bad', Scheduled: 'info', Draft: 'mid', Pending: 'mid', Sending: 'info' };
const Pill = ({ s, children }) => <span className={'cm-pill ' + (STATUS_TONE[s] || '')}>{children || s}</span>;
const Field = ({ label, hint, children, grow }) => (
  <label className={'cm-f' + (grow ? ' grow' : '')}><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
);
function Switch({ on, onChange, disabled, label }) {
  return (
    <button type="button" role="switch" aria-checked={!!on} aria-label={label} disabled={disabled}
            className={'cm-sw' + (on ? ' on' : '')} onClick={() => onChange(!on)}><i /></button>
  );
}

// ---- section navigation --------------------------------------------------------
const NAV = [
  ['dashboard', 'fa-house', 'Overview'],
  ['compose', 'fa-paper-plane', 'Compose'],
  ['inbox', 'fa-comments', 'Inbox'],
  ['announcements', 'fa-bullhorn', 'Notices'],
  ['messages', 'fa-clock-rotate-left', 'History'],
  ['templates', 'fa-file-lines', 'Templates'],
  ['contacts', 'fa-address-book', 'Contacts'],
];
const ACTIVE = { message_detail: 'messages' };
function CNav({ d }) {
  const u = d.nav || {};
  const active = ACTIVE[d.page] || d.page;
  return (
    <nav className="sl-nav cm-nav" aria-label="Communication">
      {NAV.filter(([k]) => u[k]).map(([k, ic, l]) => (
        <A key={k} to={u[k]} className={active === k ? 'on' : ''} aria-current={active === k ? 'page' : undefined}>
          <i className={'fas ' + ic} aria-hidden="true" /><span>{l}</span></A>))}
      {u.reports && <A to={u.reports} className={'cm-nav-x' + (active === 'reports' ? ' on' : '')}><i className="fas fa-chart-line" aria-hidden="true" /><span>Reports</span></A>}
      {u.settings && <A to={u.settings} className={'cm-nav-x' + (active === 'settings' ? ' on' : '')}><i className="fas fa-gear" aria-hidden="true" /><span>Settings</span></A>}
    </nav>
  );
}
const Page = ({ d, children, className }) => (
  <div className={'rs cm ' + (className || '')}><CNav d={d} />{children}</div>
);

// Multipart upload of a single file to a comms attachment endpoint.
async function uploadAttachment(url, file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(url, { method: 'POST', credentials: 'same-origin',
    headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrfToken() }, body: fd });
  try { return await res.json(); } catch (_) { return { ok: false, error: 'Upload failed.' }; }
}
function AttachField({ url, value, onChange, notify, compact }) {
  const ref = useRef();
  const [busy, setBusy] = useState(false);
  const pick = async (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    setBusy(true);
    const r = await uploadAttachment(url, f);
    setBusy(false);
    if (r.ok) onChange(r.attachment); else notify && notify('error', r.error || 'Upload failed.');
    if (ref.current) ref.current.value = '';
  };
  return (
    <span className="cm-attach">
      {value ? (
        <span className="cm-file"><i className="fas fa-paperclip" aria-hidden="true" /><span>{value.name}{value.size ? ` · ${value.size}` : ''}</span>
          <button type="button" onClick={() => onChange(null)} aria-label="Remove attachment"><i className="fas fa-xmark" aria-hidden="true" /></button></span>
      ) : (
        <button type="button" className={compact ? 'cm-ib' : 'rs-btn ghost sm'} disabled={busy} onClick={() => ref.current && ref.current.click()}
                aria-label="Attach a file" title="Attach a file">
          <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-paperclip')} aria-hidden="true" />{!compact && <span>{busy ? 'Uploading…' : 'Attach file'}</span>}</button>
      )}
      <input ref={ref} type="file" hidden onChange={pick} />
    </span>
  );
}
const FileLink = ({ a }) => a ? (
  <a href={a.url} className="cm-file link" data-native><i className="fas fa-paperclip" aria-hidden="true" /><span>{a.name}{a.size ? ` · ${a.size}` : ''}</span></a>
) : null;

// One campaign / history row (overview, history).
function CampRow({ m }) {
  const total = m.recipient_count === '' ? null : Number(m.recipient_count) || 0;
  const sent = Number(m.sent_count) || 0;
  const ch = m.channel || m.type;
  return (
    <A to={m.url} className="cm-row">
      <ChIcon ch={ch} />
      <span className="cm-row-t">
        <b>{m.title}</b>
        <small>{[m.audience_label, m.by, m.date].filter(Boolean).join(' · ')}</small>
      </span>
      {total != null && total > 0 && (
        <span className="cm-row-p"><Meter value={sent} max={total} tone={sent >= total ? 'good' : sent ? 'mid' : 'bad'} />
          <small>{sent}/{total}</small></span>)}
      <span className="cm-row-s">
        <Pill s={m.status} />
        {m.status === 'Scheduled' && m.scheduled_at && <small><i className="fas fa-clock" aria-hidden="true" /> {m.scheduled_at}</small>}
      </span>
      <i className="fas fa-chevron-right cm-row-go" aria-hidden="true" />
    </A>
  );
}

// ============================================================================
// Overview
// ============================================================================
function Dashboard({ d }) {
  const s = d.stats || {};
  const u = d.urls || {};
  const canSend = canWrite(d, 'messages_create');
  const cov = d.cov || { total: 0, with_contact: 0, without_contact: 0, pct: 0 };
  const chTotal = (d.channel_chart || []).reduce((a, x) => a + x.count, 0);
  const qa = [
    canSend && { to: u.compose_sms || d.nav.compose, ic: 'fas fa-comment-sms', tone: 'sms', t: 'Text parents', s: 'SMS to every parent or a class' },
    canSend && { to: (d.nav.compose || '') + '?channel=WhatsApp', ic: 'fab fa-whatsapp', tone: 'wa', t: 'WhatsApp parents', s: 'One-tap chats, no gateway needed' },
    canSend && { to: (d.nav.compose || '') + '?audience=defaulters', ic: 'fas fa-money-bill-wave', tone: 'mid', t: 'Fee reminder', s: 'Parents with an unpaid balance' },
    canSend && u.compose_email && { to: u.compose_email, ic: 'fas fa-envelope', tone: 'em', t: 'Email parents', s: 'With an attachment if you like' },
    canWrite(d, 'announcements_create') && { to: d.nav.announcements, ic: 'fas fa-bullhorn', tone: 'ann', t: 'Post a notice', s: 'Shows on everyone’s dashboard' },
    d.nav.inbox && { to: d.nav.inbox, ic: 'fas fa-comments', tone: 'app', t: 'Message a colleague', s: 'Staff chat and groups' },
  ].filter(Boolean);
  const attn = [
    s.scheduled ? { to: d.nav.messages + '?status=Scheduled', ic: 'fa-clock', tone: 'info', t: plural(s.scheduled, 'scheduled campaign') } : null,
    s.failed ? { to: d.nav.messages + '?status=Failed', ic: 'fa-triangle-exclamation', tone: 'bad', t: plural(s.failed, 'failed delivery', 'failed deliveries') } : null,
    s.drafts ? { to: d.nav.messages + '?status=Draft', ic: 'fa-file-pen', tone: 'mid', t: plural(s.drafts, 'draft') } : null,
  ].filter(Boolean);
  return (
    <Page d={d}>
      <Head icon="fa-comments" title="Communication" sub="Reach parents and staff by SMS, WhatsApp, email or in-app.">
        {canSend && <A to={d.nav.compose} className="rs-btn primary"><i className="fas fa-pen-to-square" aria-hidden="true" /> New message</A>}
      </Head>

      {qa.length > 0 && (
        <div className="cm-qa">{qa.map((q) => (
          <A key={q.t} to={q.to} className="cm-qa-i"><span className={'cm-ch lg ' + q.tone}><i className={q.ic} aria-hidden="true" /></span>
            <span><b>{q.t}</b><small>{q.s}</small></span></A>))}
        </div>)}

      <div className="cm-grid2">
        <section className="rs-card cm-cov">
          <div className="cm-cov-t">
            <span className="k">Parents you can reach</span>
            <strong>{cov.with_contact}<small> of {cov.total}</small></strong>
            <Meter value={cov.with_contact} max={cov.total || 1} tone={cov.pct >= 80 ? 'good' : cov.pct >= 50 ? 'mid' : 'bad'} />
            {cov.without_contact > 0
              ? <A to={u.contacts_missing} className="cm-link">{plural(cov.without_contact, 'student')} without a parent phone <i className="fas fa-arrow-right" aria-hidden="true" /></A>
              : <span className="cm-mute">Every student has a parent phone number.</span>}
          </div>
          {attn.length > 0 && (
            <div className="cm-attn"><span className="k">Needs attention</span>
              {attn.map((a) => <A key={a.t} to={a.to} className={'cm-attn-i ' + a.tone}><i className={'fas ' + a.ic} aria-hidden="true" />{a.t}<i className="fas fa-chevron-right" aria-hidden="true" /></A>)}
            </div>)}
        </section>
        <Tiles items={[
          { label: 'Sent today', value: s.sent_today || 0, sub: `${s.sms_today || 0} SMS/WhatsApp · ${s.email_today || 0} email` },
          { label: 'Delivery rate', value: s.success_rate == null ? '—' : s.success_rate, unit: s.success_rate == null ? '' : '%',
            tone: s.success_rate == null ? '' : s.success_rate >= 90 ? 'good' : s.success_rate >= 60 ? 'mid' : 'bad', sub: 'of attempted deliveries' },
          { label: 'Campaigns', value: d.total_campaigns || 0, sub: `${d.total_sent || 0} of ${d.total_recipients || 0} delivered` },
          { label: 'Templates', value: d.template_count || 0, sub: 'ready to reuse' },
        ]} />
      </div>

      <div className="cm-grid2 wide">
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-clock-rotate-left" aria-hidden="true" /> Recent campaigns</h3>
            <A to={d.nav.messages} className="cm-link">View all</A></div>
          {d.recent && d.recent.length ? <div className="cm-list">{d.recent.map((m) => <CampRow key={m.id} m={m} />)}</div>
            : <Blank icon="fa-paper-plane" title="No campaigns yet">{canSend && <A to={d.nav.compose} className="rs-btn primary">Send your first message</A>}</Blank>}
        </section>
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-chart-simple" aria-hidden="true" /> By channel</h3><small>all campaigns</small></div>
          {chTotal ? (
            <div className="cm-mix">
              <div className="cm-mix-bar">{d.channel_chart.map((c) => <i key={c.channel} className={chMeta(c.channel)[1]} style={{ width: (c.count / chTotal * 100) + '%' }} />)}</div>
              {d.channel_chart.map((c) => (
                <div key={c.channel} className="cm-mix-r"><ChIcon ch={c.channel} size="sm" /><span>{c.channel}</span>
                  <b>{c.count}</b><small>{Math.round(c.count / chTotal * 100)}%</small></div>))}
            </div>
          ) : <Blank icon="fa-chart-simple" title="No messages yet" />}
          <A to={d.nav.templates} className="cm-tip"><i className="fas fa-lightbulb" aria-hidden="true" />
            <span><b>{plural(d.template_count || 0, 'template')}</b> with tags like {'{first_name}'} and {'{balance}'} — personalised for every parent.</span>
            <i className="fas fa-chevron-right" aria-hidden="true" /></A>
        </section>
      </div>
    </Page>
  );
}

// ============================================================================
// Compose
// ============================================================================
function PhonePreview({ channel, title, sample, reach }) {
  const isEmail = channel === 'Email', isApp = channel === 'In-app', isWa = channel === 'WhatsApp';
  return (
    <div className={'cm-phone ' + chMeta(channel)[1]}>
      <div className="cm-phone-top"><ChIcon ch={channel} size="sm" /><b>{isEmail ? 'Inbox' : isApp ? 'Notifications' : isWa ? 'WhatsApp' : 'Messages'}</b>
        <small>{reach}</small></div>
      <div className="cm-phone-body">
        {isEmail ? (
          <div className="cm-mail"><b>{title || 'Subject'}</b><p>{sample}</p></div>
        ) : isApp ? (
          <div className="cm-note"><i className="fas fa-bell" aria-hidden="true" /><div><b>{title || 'Notice'}</b><p>{sample}</p></div></div>
        ) : <div className="cm-bubble">{sample}</div>}
      </div>
    </div>
  );
}

function Compose({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const canStaff = !!d.is_admin;
  const [to, setTo] = useState(d.pre_to || 'parents');
  const [pickedStaff, setPickedStaff] = useState(d.pre_staff || []);
  const [audience, setAudience] = useState(d.pre_audience || 'all');
  const [termId, setTermId] = useState(d.term_id);
  const [classId, setClassId] = useState(d.pre_class || '');
  const [armId, setArmId] = useState('');
  const [picked, setPicked] = useState(d.pre_students || []);
  const [excluded, setExcluded] = useState([]);
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
  const [att, setAtt] = useState(null);
  const [refine, setRefine] = useState(false);
  const [showPrev, setShowPrev] = useState(false);
  const [preview, setPreview] = useState({ reachable: null, no_phone: 0, sample: '' });
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef();
  const ptRef = useRef();

  const isEmail = channel === 'Email';
  const isInapp = channel === 'In-app';
  useEffect(() => { if (isInapp && to !== 'staff' && canStaff) setTo('staff'); /* eslint-disable-next-line */ }, [isInapp]);
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
    const b = new URLSearchParams();
    b.set('term_id', termId); b.set('body', body); b.set('channel', channel);
    Object.entries(buildSpec()).forEach(([k, v]) => {
      if (Array.isArray(v)) v.forEach((x) => b.append(k, x));
      else if (v !== '' && v != null) b.set(k, v);
    });
    try {
      const res = await fetch(d.urls.preview, { method: 'POST', credentials: 'same-origin',
        headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrfToken(), 'Content-Type': 'application/x-www-form-urlencoded' }, body: b });
      const j = await res.json();
      setPreview({ reachable: j.reachable, no_phone: j.unreachable != null ? j.unreachable : j.no_phone, sample: j.sample || '' });
    } catch (_) { /* keep the last preview */ }
  };
  useEffect(() => { clearTimeout(ptRef.current); ptRef.current = setTimeout(runPreview, 350); return () => clearTimeout(ptRef.current); },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [to, audience, termId, classId, armId, picked, excluded, gender, stream, staffScope, deptId, pickedStaff, body, channel]);

  const insertPh = (ph) => {
    const el = bodyRef.current; const s = el ? el.selectionStart : body.length; const e = el ? el.selectionEnd : body.length;
    setBody(body.slice(0, s) + ph + body.slice(e));
    requestAnimationFrame(() => { if (el) { el.focus(); el.selectionStart = el.selectionEnd = s + ph.length; } });
  };
  const onTpl = (id) => { setTpl(id); const t = d.templates.find((x) => String(x.id) === String(id)); if (t) setBody(t.body); };

  const [groups, setGroups] = useState(d.groups || []);
  const applySpec = (sp) => {
    sp = sp || {};
    setTo(sp.to || 'parents'); setAudience(sp.audience || 'all'); setClassId(sp.class_id || ''); setArmId(sp.arm_id || '');
    setGender(sp.gender || ''); setStream(sp.stream || ''); setStaffScope(sp.staff_scope || 'all'); setDeptId(sp.department_id || '');
    setPicked((sp.student_ids || []).map((id) => ({ id, label: `#${id}` })));
    setExcluded((sp.exclude_ids || []).map((id) => ({ id, label: `#${id}` })));
  };
  const saveGroup = async () => {
    const name = await promptDialog({ title: 'Save recipient group', label: 'Group name', placeholder: 'e.g. SS3 Science parents' });
    if (!name || !name.trim()) return;
    const r = await submitJson(d.urls.save_group, { name: name.trim(), overwrite: 'on', ...buildSpec() });
    if (r.ok) { notify('success', r.message); if (!groups.some((g) => g.name === name.trim())) setGroups((gs) => [...gs, { id: `tmp-${Date.now()}`, name: name.trim(), spec: buildSpec() }]); }
    else notify('error', r.error || 'Could not save group.');
  };

  const submit = async (e) => {
    if (e) e.preventDefault();
    if (!body.trim()) { notify('error', 'Write a message first.'); if (bodyRef.current) bodyRef.current.focus(); return; }
    if (schedule && !scheduledAt) { notify('error', 'Pick a date and time to schedule it for.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.submit, { term_id: termId, title, channel, body,
      schedule: schedule ? 'on' : '', scheduled_at: scheduledAt,
      attachment_id: (isEmail && att) ? att.id : '', ...buildSpec() });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not create the campaign.');
  };

  const charCount = body.length;
  const segs = charCount ? Math.ceil(charCount / 160) : 0;
  const channelReady = isInapp ? true : (isEmail ? d.email_ready : d.gateway_ready);
  const channelLabel = isInapp ? 'In-app' : (isEmail ? 'Email (SMTP)' : (d.gateway_label || 'SMS gateway'));
  const reachNoun = isInapp ? 'account' : (isEmail ? 'email' : 'phone');
  const reach = preview.reachable == null ? '…' : preview.reachable;
  const reachText = preview.reachable == null ? 'Counting recipients…' : plural(Number(preview.reachable) || 0, 'recipient');
  const sendLabel = isInapp ? 'Send notification' : schedule ? 'Schedule' : (channelReady ? 'Create & send' : 'Create campaign');
  const audOpts = [
    { value: 'all', icon: 'fa-users', label: 'All parents' }, { value: 'class', icon: 'fa-school', label: 'A class' },
    { value: 'defaulters', icon: 'fa-money-bill-wave', label: 'Owing fees' }, { value: 'students', icon: 'fa-user-check', label: 'Pick students' },
  ];
  const chOpts = d.channels.map((c) => ({ value: c, label: c }));

  const sendHint = isInapp ? 'Posts straight to each staff member’s notification bell.'
    : channelReady ? `${channelLabel} is connected — after creating, send to everyone with one tap.`
      : isEmail ? 'Email isn’t set up yet — you can still create the campaign and review recipients.'
        : 'You’ll get one-tap WhatsApp / SMS links for each parent and a CSV export.';

  const sendBox = (
    <div className="cm-send">
      {channelReady && !isInapp && (
        <div className="cm-sched">
          <span><b>Schedule for later</b><small>Auto-sends via {channelLabel}</small></span>
          <Switch on={schedule} onChange={setSchedule} label="Schedule for later" />
        </div>)}
      {schedule && <Field label="Send at"><input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} /></Field>}
      <button type="submit" className="rs-btn primary block" disabled={busy}>
        <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : schedule ? 'fa-clock' : 'fa-paper-plane')} aria-hidden="true" /> {sendLabel}</button>
      <p className="cm-hint"><i className={'fas ' + (channelReady ? 'fa-circle-check good' : 'fa-circle-info')} aria-hidden="true" /> {sendHint}
        {!channelReady && !isEmail && !isInapp && d.urls.settings && <> <A to={d.urls.settings} className="cm-link">Connect an SMS gateway</A></>}</p>
    </div>
  );

  return (
    <Page d={d} className="cm-compose-page">
      <Head icon="fa-paper-plane" title="New message" sub="Pick who it’s for, write it once — every parent gets their own copy." />
      <form onSubmit={submit} className="cm-compose">
        <div className="cm-steps">
          {/* 1 · recipients */}
          <section className="rs-card cm-step">
            <div className="cm-step-h"><b>1</b><h3>Who should get it?</h3>
              <span className="cm-step-a">
                {groups.length > 0 && (
                  <select className="cm-mini-sel" defaultValue="" aria-label="Load a saved group"
                          onChange={(e) => { const g = groups.find((x) => String(x.id) === e.target.value); if (g) applySpec(g.spec); e.target.value = ''; }}>
                    <option value="">Saved groups…</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select>)}
                <button type="button" className="cm-ib" onClick={saveGroup} title="Save this selection as a group" aria-label="Save this selection as a group"><i className="fas fa-bookmark" aria-hidden="true" /></button>
              </span></div>
            {canStaff && <Seg label="Recipients" value={to} onChange={setTo} options={[{ value: 'parents', icon: 'fa-people-roof', label: 'Parents' }, { value: 'staff', icon: 'fa-user-tie', label: 'Staff' }]} />}
            {to === 'staff' ? (
              <div className="cm-stack">
                {pickedStaff.length > 0 ? (
                  <div><div className="cm-tags">{pickedStaff.map((p) => (
                    <span key={p.id} className="cm-tag">{p.label}<button type="button" aria-label={`Remove ${p.label}`} onClick={() => setPickedStaff((xs) => xs.filter((x) => x.id !== p.id))}><i className="fas fa-xmark" aria-hidden="true" /></button></span>))}</div>
                    <small className="cm-mute">Only these staff get it. Remove them to message a whole group.</small></div>
                ) : (
                  <Chips label="Staff group" value={staffScope} onChange={setStaffScope} items={[
                    { value: 'all', label: 'All staff' }, { value: 'teaching', label: 'Teaching' },
                    { value: 'non-teaching', label: 'Non-teaching' }, { value: 'department', label: 'A department' }]} />)}
                {staffScope === 'department' && !pickedStaff.length && (
                  <Field label="Department"><select value={deptId} onChange={(e) => setDeptId(e.target.value)}>
                    <option value="">All departments</option>{(d.departments || []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>)}
              </div>
            ) : (
              <div className="cm-stack">
                <div className="cm-aud">{audOpts.map((o) => (
                  <button type="button" key={o.value} className={'cm-aud-i' + (audience === o.value ? ' on' : '')} aria-pressed={audience === o.value} onClick={() => setAudience(o.value)}>
                    <i className={'fas ' + o.icon} aria-hidden="true" /><span>{o.label}</span></button>))}
                </div>
                {(audience === 'class' || audience === 'defaulters') && (
                  <div className="cm-row2">
                    <Field label="Class" grow><select value={classId} onChange={(e) => setClassId(e.target.value)}>
                      <option value="">{audience === 'defaulters' ? 'Every class' : 'Choose a class'}</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
                    {audience === 'class' && d.arms.length > 0 && (
                      <Field label="Arm"><select value={armId} onChange={(e) => setArmId(e.target.value)}>
                        <option value="">All arms</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>)}
                  </div>)}
                {audience === 'students' && (
                  <div>
                    <Search url={d.urls.search} placeholder="Search students by name or ID…" onPick={(o) => setPicked((p) => (p.some((x) => x.id === o.id) ? p : [...p, o]))} />
                    {picked.length > 0 && <div className="cm-tags">{picked.map((p) => (
                      <span className="cm-tag" key={p.id}>{p.label}<button type="button" aria-label={`Remove ${p.label}`} onClick={() => setPicked((s) => s.filter((x) => x.id !== p.id))}><i className="fas fa-xmark" aria-hidden="true" /></button></span>))}</div>}
                  </div>)}
                <button type="button" className="cm-more" aria-expanded={refine} onClick={() => setRefine((v) => !v)}>
                  <i className={'fas ' + (refine ? 'fa-chevron-up' : 'fa-sliders')} aria-hidden="true" /> Term, gender, stream &amp; exclusions
                  {(gender || stream || excluded.length > 0) && <em>{[gender, stream, excluded.length ? `−${excluded.length}` : ''].filter(Boolean).join(' · ')}</em>}</button>
                {refine && (
                  <div className="cm-stack cm-refine">
                    <div className="cm-row2">
                      <Field label="Term" grow><select value={termId} onChange={(e) => setTermId(e.target.value)}>
                        {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></Field>
                      <Field label="Gender"><select value={gender} onChange={(e) => setGender(e.target.value)}>
                        <option value="">Any</option>{(d.genders || []).map((g) => <option key={g} value={g}>{g}</option>)}</select></Field>
                      <Field label="Stream"><select value={stream} onChange={(e) => setStream(e.target.value)}>
                        <option value="">Any</option>{(d.streams || []).map((x) => <option key={x} value={x}>{x}</option>)}</select></Field>
                    </div>
                    <Search url={d.urls.search} placeholder="Leave out a student…" onPick={(o) => setExcluded((p) => (p.some((x) => x.id === o.id) ? p : [...p, o]))} />
                    {excluded.length > 0 && <div className="cm-tags">{excluded.map((p) => (
                      <span className="cm-tag bad" key={p.id}>− {p.label}<button type="button" aria-label={`Include ${p.label} again`} onClick={() => setExcluded((s) => s.filter((x) => x.id !== p.id))}><i className="fas fa-xmark" aria-hidden="true" /></button></span>))}</div>}
                  </div>)}
              </div>
            )}
            <div className={'cm-reach' + (preview.no_phone ? ' warn' : '')}>
              <i className="fas fa-users" aria-hidden="true" /><b>{reachText}</b>
              {preview.no_phone ? <span>· {preview.no_phone} have no {reachNoun}</span> : null}
            </div>
          </section>

          {/* 2 · message */}
          <section className="rs-card cm-step">
            <div className="cm-step-h"><b>2</b><h3>Write the message</h3></div>
            <div className="cm-chans" role="radiogroup" aria-label="Channel">
              {chOpts.map((o) => (
                <button type="button" role="radio" aria-checked={channel === o.value} key={o.value}
                        className={'cm-chan ' + chMeta(o.value)[1] + (channel === o.value ? ' on' : '')} onClick={() => setChannel(o.value)}>
                  <i className={chMeta(o.value)[0]} aria-hidden="true" /><span>{o.label}</span></button>))}
            </div>
            <div className="cm-row2">
              <Field label={isEmail ? 'Subject' : 'Title (for your records)'} grow>
                <input type="text" value={title} placeholder="e.g. June fee reminder" onChange={(e) => setTitle(e.target.value)} /></Field>
              {d.templates.length > 0 && (
                <Field label="Start from a template" grow><select value={tpl} onChange={(e) => onTpl(e.target.value)}>
                  <option value="">— Blank —</option>{d.templates.map((t) => <option key={t.id} value={t.id}>{t.name}{t.category ? ` · ${t.category}` : ''}</option>)}</select></Field>)}
            </div>
            <div className="cm-f"><span>Message</span>
              <div className="cm-tagbar" aria-label="Personalise with">{d.placeholders.map((p) => (
                <button type="button" key={p} className="cm-ph" onClick={() => insertPh(p)}>{p.replace(/[{}]/g, '')}</button>))}</div>
              <textarea ref={bodyRef} rows={phone ? 6 : 7} value={body} onChange={(e) => setBody(e.target.value)}
                        placeholder="Type your message. Tap a tag above to personalise it, e.g. Dear {parent}…" />
              <small className="cm-count"><span>{plural(charCount, 'character')}</span>
                <span>{isInapp ? 'In-app notice' : isEmail ? 'Email' : `${plural(segs, 'SMS segment')}`}</span></small>
            </div>
            {isEmail && <AttachField url={d.urls.upload} value={att} onChange={setAtt} notify={notify} />}
            {phone && (
              <button type="button" className="cm-more" aria-expanded={showPrev} onClick={() => setShowPrev((v) => !v)}>
                <i className={'fas ' + (showPrev ? 'fa-chevron-up' : 'fa-eye')} aria-hidden="true" /> {showPrev ? 'Hide preview' : 'Preview how it looks'}</button>)}
            {phone && showPrev && <PhonePreview channel={channel} title={title} sample={preview.sample || body || 'Your message preview appears here…'} reach={reachText} />}
            {phone && <div className="cm-send-inline">{sendBox}</div>}
          </section>
        </div>

        {!phone && (
          <aside className="cm-side">
            <section className="rs-card cm-step">
              <div className="cm-step-h"><b>3</b><h3>Preview &amp; send</h3></div>
              <PhonePreview channel={channel} title={title} sample={preview.sample || body || 'Your message preview appears here…'} reach={reachText} />
              {preview.sample && <small className="cm-mute">Shown as the first recipient will see it.</small>}
              {sendBox}
            </section>
          </aside>)}
      </form>
      {phone && (
        <Bar>
          <span className="rs-bar-t"><b>{reachText}</b><small>{channel}{schedule && scheduledAt ? ` · ${scheduledAt.replace('T', ' ')}` : ''}</small></span>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={() => submit()}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : schedule ? 'fa-clock' : 'fa-paper-plane')} aria-hidden="true" /> {schedule ? 'Schedule' : 'Send'}</button>
        </Bar>)}
    </Page>
  );
}

// Type-ahead (students for compose, staff for the inbox).
function Search({ url, placeholder, onPick, autoFocus }) {
  const [text, setText] = useState('');
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const tRef = useRef();
  const onInput = (v) => {
    setText(v); clearTimeout(tRef.current);
    if (v.trim().length < 2) { setList([]); setOpen(false); return; }
    tRef.current = setTimeout(async () => {
      try { const r = await fetch(url + '?q=' + encodeURIComponent(v.trim()), { credentials: 'same-origin' });
        const rows = await r.json(); setList(Array.isArray(rows) ? rows : []); setOpen(Array.isArray(rows) && rows.length > 0); } catch (_) { /* ignore */ }
    }, 220);
  };
  const pick = (o) => { onPick({ id: o.id, label: o.label || o.name }); setText(''); setList([]); setOpen(false); };
  return (
    <div className="cm-search">
      <i className="fas fa-magnifying-glass" aria-hidden="true" />
      <input type="search" placeholder={placeholder} autoComplete="off" autoFocus={autoFocus} value={text}
             onChange={(e) => onInput(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} aria-label={placeholder} />
      {open && <div className="cm-ac" role="listbox">{list.map((o) => (
        <button type="button" role="option" aria-selected="false" key={o.id} onMouseDown={(e) => { e.preventDefault(); pick(o); }}>
          <span className="rs-av sm" aria-hidden="true">{initials(o.name || o.label)}</span>
          <span>{o.label || (o.sid ? `${o.name} (${o.sid})` : o.name)}</span></button>))}</div>}
    </div>
  );
}

// ============================================================================
// Inbox — staff chat. Two panes on laptops; list → full-screen thread on phones.
// ============================================================================
function Inbox({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const active = d.active;
  const [text, setText] = useState('');
  const [att, setAtt] = useState(null);
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState([]);       // optimistic bubbles
  const [starting, setStarting] = useState(false);
  const [picked, setPicked] = useState([]);
  const [groupTitle, setGroupTitle] = useState('');
  const [q, setQ] = useState('');
  const endRef = useRef();
  const inputRef = useRef();
  const msgs = active ? active.messages : [];
  useEffect(() => { setPending([]); }, [active && active.id, msgs.length]);
  useEffect(() => { if (endRef.current) endRef.current.scrollIntoView({ block: 'end' }); }, [active && active.id, msgs.length, pending.length]);

  const convs = (d.conversations || []).filter((c) => !q || (c.title + ' ' + (c.last || '')).toLowerCase().includes(q.toLowerCase()));
  const canSend = canWrite(d, 'inbox_send');
  const send = async (e) => {
    e.preventDefault();
    const body = text.trim();
    if ((!body && !att) || sending) return;
    setSending(true);
    setPending((p) => [...p, { id: 'p' + Date.now(), body, attachment: att, mine: true, at: 'Sending…' }]);
    setText(''); const a = att; setAtt(null);
    const r = await submitJson(active.send_url, { body, attachment_id: a ? a.id : '' });
    setSending(false);
    if (r.ok) nav.refresh(); else { notify('error', r.error || 'Could not send.'); setPending([]); setText(body); setAtt(a); }
    if (inputRef.current) inputRef.current.focus();
  };
  const startConv = async () => {
    if (!picked.length) { notify('error', 'Pick at least one person.'); return; }
    const r = await submitJson(d.urls.start, { user_ids: picked.map((p) => p.id), title: groupTitle });
    if (r.ok) { setStarting(false); setPicked([]); setGroupTitle(''); nav.go(r.redirect); }
    else notify('error', r.error || 'Could not start that conversation.');
  };

  const list = (
    <aside className="cm-convs">
      <div className="cm-convs-h">
        <div className="cm-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Search chats" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search chats" /></div>
        {canSend && !phone && <button type="button" className="cm-ib primary" onClick={() => setStarting(true)} aria-label="New conversation" title="New conversation"><i className="fas fa-pen-to-square" aria-hidden="true" /></button>}
      </div>
      <div className="cm-convs-l">
        {convs.length ? convs.map((c) => (
          <A key={c.id} to={d.urls.thread + c.id} className={'cm-conv' + (active && active.id === c.id ? ' on' : '') + (c.unread ? ' unread' : '')}>
            <span className={'rs-av' + (c.kind === 'group' ? ' grp' : '')} aria-hidden="true">{c.kind === 'group' ? <i className="fas fa-users" /> : initials(c.title)}</span>
            <span className="cm-conv-t"><b>{c.title}</b><small>{c.last || 'No messages yet'}</small></span>
            <span className="cm-conv-m"><small>{c.last_at}</small>{c.unread > 0 && <em>{c.unread}</em>}</span>
          </A>)) : (
          <Blank icon="fa-comments" title={q ? 'No chats match' : 'No conversations yet'}>
            {!q && canSend && <button type="button" className="rs-btn primary" onClick={() => setStarting(true)}><i className="fas fa-pen-to-square" aria-hidden="true" /> Start one</button>}</Blank>)}
      </div>
    </aside>
  );

  const thread = active ? (
    <section className="cm-thread">
      <header className="cm-thread-h">
        {phone && <A to={d.nav.inbox} className="cm-ib" aria-label="Back to chats"><i className="fas fa-arrow-left" aria-hidden="true" /></A>}
        <span className={'rs-av' + (active.kind === 'group' ? ' grp' : '')} aria-hidden="true">{active.kind === 'group' ? <i className="fas fa-users" /> : initials(active.title)}</span>
        <span className="cm-thread-t"><b>{active.title}</b><small>{active.kind === 'group' ? 'Group' : 'Direct message'}</small></span>
      </header>
      <div className="cm-msgs">
        {msgs.length || pending.length ? [...msgs, ...pending].map((m, i, all) => {
          const prev = all[i - 1];
          const day = (m.at || '').split(' ').slice(0, 2).join(' ');
          const showDay = m.at !== 'Sending…' && (!prev || (prev.at || '').split(' ').slice(0, 2).join(' ') !== day);
          return (
            <React.Fragment key={m.id}>
              {showDay && day && <div className="cm-day"><span>{day}</span></div>}
              <div className={'cm-b' + (m.mine ? ' mine' : '') + (String(m.id).startsWith('p') ? ' sending' : '')}>
                <div>
                  {!m.mine && active.kind === 'group' && <b className="cm-b-who">{m.sender}</b>}
                  {m.body && <p>{m.body}</p>}
                  {m.attachment && <FileLink a={m.attachment} />}
                  <small>{String(m.at || '').split(' ').slice(2).join(' ') || m.at}</small>
                </div>
              </div>
            </React.Fragment>);
        }) : <div className="cm-hello"><i className="fas fa-hand" aria-hidden="true" /> Say hello to {active.title}.</div>}
        <div ref={endRef} />
      </div>
      {canSend && (
        <form className="cm-composer" onSubmit={send}>
          <AttachField url={d.urls.upload} value={att} onChange={setAtt} notify={notify} compact />
          <textarea ref={inputRef} rows={1} placeholder="Message" value={text} aria-label="Message"
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !phone) { e.preventDefault(); send(e); } }} />
          <button type="submit" className="cm-send-b" aria-label="Send" disabled={(!text.trim() && !att) || sending}><i className="fas fa-paper-plane" aria-hidden="true" /></button>
        </form>)}
    </section>
  ) : (
    <section className="cm-thread empty"><Blank icon="fa-comment-dots" title="Pick a chat">
      <p>Choose a conversation on the left, or start a new one.</p></Blank></section>
  );

  return (
    <Page d={d} className={'cm-inbox-page' + (phone && active ? ' chat-open' : '')}>
      {!(phone && active) && (
        <Head icon="fa-comments" title="Inbox" sub="Message colleagues one-to-one or in groups.">
          {canSend && <button type="button" className="rs-btn primary" onClick={() => setStarting(true)}><i className="fas fa-pen-to-square" aria-hidden="true" /> New chat</button>}
        </Head>)}
      <div className="cm-inbox">
        {(!phone || !active) && list}
        {(!phone || active) && thread}
      </div>
      {starting && (
        <Sheet title="New conversation" onClose={() => setStarting(false)}>
          <div className="cm-sheet">
            <Search url={d.urls.users} placeholder="Search staff by name…" onPick={(o) => setPicked((p) => (p.some((x) => x.id === o.id) ? p : [...p, o]))} autoFocus />
            {picked.length > 0 && <div className="cm-tags">{picked.map((p) => (
              <span className="cm-tag" key={p.id}>{p.label}<button type="button" aria-label={`Remove ${p.label}`} onClick={() => setPicked((s) => s.filter((x) => x.id !== p.id))}><i className="fas fa-xmark" aria-hidden="true" /></button></span>))}</div>}
            {picked.length > 1 && <Field label="Group name"><input value={groupTitle} onChange={(e) => setGroupTitle(e.target.value)} placeholder="e.g. Exams committee" /></Field>}
            <small className="cm-mute">{picked.length > 1 ? 'Everyone picked joins one group chat.' : 'Pick one person for a direct chat, or several for a group.'}</small>
            <div className="cm-sheet-f">
              <button type="button" className="rs-btn ghost" onClick={() => setStarting(false)}>Cancel</button>
              <button type="button" className="rs-btn primary" disabled={!picked.length} onClick={startConv}><i className="fas fa-comments" aria-hidden="true" /> {picked.length > 1 ? 'Create group' : 'Start chat'}</button>
            </div>
          </div>
        </Sheet>)}
    </Page>
  );
}

// ============================================================================
// Announcements (notices)
// ============================================================================
const CAT = { Important: ['fa-circle-exclamation', 'bad'], Event: ['fa-calendar-day', 'mid'], Info: ['fa-circle-info', 'info'] };
function AnnForm({ d, notify, item, onDone, onCancel }) {
  const blank = { title: '', body: '', category: 'Info', audience: 'All', starts_on: '', ends_on: '', is_pinned: false, needs_ack: false };
  const [f, setF] = useState(item ? { title: item.title, body: item.body, category: item.category, audience: item.audience,
    starts_on: item.starts_iso || '', ends_on: item.ends_iso || '', is_pinned: item.is_pinned, needs_ack: item.needs_ack } : blank);
  const [att, setAtt] = useState(item ? item.attachment : null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Give the notice a title.'); return; }
    setBusy(true);
    const r = await submitJson(item ? item.edit_url : d.add_url, { ...f, is_pinned: f.is_pinned ? 'on' : '', needs_ack: f.needs_ack ? 'on' : '',
      attachment_id: att ? att.id || item && item.attachment_id || '' : '' });
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Saved.'); onDone(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <form className="cm-sheet" onSubmit={submit}>
      <Field label="Title"><input value={f.title} onChange={(e) => set('title', e.target.value)} placeholder="e.g. Third term exam timetable" autoFocus /></Field>
      <Field label="Message"><textarea rows={4} value={f.body} onChange={(e) => set('body', e.target.value)} placeholder="What do people need to know?" /></Field>
      <div className="cm-f"><span>Type</span>
        <Seg label="Type" value={f.category} onChange={(v) => set('category', v)} options={[
          { value: 'Info', icon: 'fa-circle-info', label: 'Info' }, { value: 'Important', icon: 'fa-circle-exclamation', label: 'Important' },
          { value: 'Event', icon: 'fa-calendar', label: 'Event' }]} /></div>
      <div className="cm-f"><span>Who sees it</span>
        <Chips label="Audience" value={f.audience} onChange={(v) => set('audience', v)} items={['All', 'Staff', 'Students', 'Parents'].map((x) => ({ value: x, label: x }))} /></div>
      <div className="cm-row2">
        <Field label="Show from" grow><input type="date" value={f.starts_on} onChange={(e) => set('starts_on', e.target.value)} /></Field>
        <Field label="Until" grow><input type="date" value={f.ends_on} onChange={(e) => set('ends_on', e.target.value)} /></Field>
      </div>
      <div className="cm-toggles">
        <div className="cm-sched"><span><b>Pin to the top</b><small>Stays above newer notices</small></span><Switch on={f.is_pinned} onChange={(v) => set('is_pinned', v)} label="Pin to the top" /></div>
        <div className="cm-sched"><span><b>Ask staff to acknowledge</b><small>See who has read it</small></span><Switch on={f.needs_ack} onChange={(v) => set('needs_ack', v)} label="Ask staff to acknowledge" /></div>
      </div>
      <AttachField url={d.upload_url} value={att} onChange={setAtt} notify={notify} />
      <div className="cm-sheet-f">
        <button type="button" className="rs-btn ghost" onClick={onCancel}>Cancel</button>
        <button className="rs-btn primary" disabled={busy}><i className="fas fa-bullhorn" aria-hidden="true" /> {item ? 'Save changes' : 'Post notice'}</button>
      </div>
    </form>
  );
}
function Announcements({ d, notify }) {
  const nav = useNav();
  const [cat, setCat] = useState('');
  const [editing, setEditing] = useState(null);   // null | 'new' | item
  const items = (d.items || []).filter((a) => !cat || a.category === cat);
  const count = (c) => (d.items || []).filter((a) => a.category === c).length;
  const del = async (a) => {
    if (!await confirm({ title: 'Delete notice?', message: `“${a.title}” will be removed for everyone.`, tone: 'danger', confirmText: 'Delete' })) return;
    const r = await submitJson(a.delete_url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not delete.');
  };
  const canAdd = canWrite(d, 'announcements_create');
  return (
    <Page d={d}>
      <Head icon="fa-bullhorn" title="Notices" sub="Announcements shown on staff, student and parent dashboards.">
        {canAdd && <button type="button" className="rs-btn primary" onClick={() => setEditing('new')}><i className="fas fa-plus" aria-hidden="true" /> New notice</button>}
      </Head>
      {(d.items || []).length > 0 && (
        <Seg label="Filter notices" value={cat} onChange={setCat} options={[
          { value: '', label: 'All', count: d.items.length }, { value: 'Important', label: 'Important', count: count('Important') },
          { value: 'Event', label: 'Events', count: count('Event') }, { value: 'Info', label: 'Info', count: count('Info') }]} />)}
      {items.length ? (
        <div className="cm-anns">{items.map((a) => {
          const [ic, t] = CAT[a.category] || CAT.Info;
          return (
            <article key={a.id} className={'rs-card cm-ann ' + t + (a.is_active ? '' : ' off')}>
              <div className="cm-ann-h">
                <span className={'cm-ch ' + t} aria-hidden="true"><i className={'fas ' + ic} /></span>
                <div className="cm-ann-t"><h3>{a.title}{a.is_pinned && <i className="fas fa-thumbtack cm-pin" title="Pinned" aria-label="Pinned" />}</h3>
                  <small>{a.created_at}{a.created_by ? ` · ${a.created_by}` : ''}{(a.starts_on || a.ends_on) ? ` · ${a.starts_on || '…'} – ${a.ends_on || '…'}` : ''}</small></div>
                {(canWrite(d, 'announcements_delete') || canWrite(d, 'announcements_create')) && (
                  <Menu label="Options" items={[
                    a.edit_url && canWrite(d, 'announcements_create') && { icon: 'fa-pen', label: 'Edit', onClick: () => setEditing(a) },
                    canWrite(d, 'announcements_delete') && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => del(a) },
                  ]} />)}
              </div>
              {a.body && <p className="cm-ann-b">{a.body}</p>}
              <div className="cm-ann-f">
                <span className="cm-pill">{a.audience === 'All' ? 'Everyone' : a.audience}</span>
                <span className={'cm-pill ' + t}>{a.category}</span>
                {a.needs_ack && <span className="cm-pill good"><i className="fas fa-circle-check" aria-hidden="true" /> {plural(a.ack_count, 'acknowledgement')}</span>}
                {!a.is_active && <span className="cm-pill">Not showing</span>}
                <FileLink a={a.attachment} />
              </div>
            </article>);
        })}</div>
      ) : (
        <Blank icon="fa-bullhorn" title={cat ? 'No notices of this type' : 'No notices yet'}>
          <p>Post a notice and it shows on everyone’s dashboard.</p>
          {canAdd && !cat && <button type="button" className="rs-btn primary" onClick={() => setEditing('new')}><i className="fas fa-plus" aria-hidden="true" /> New notice</button>}
        </Blank>)}
      {editing && (
        <Sheet title={editing === 'new' ? 'New notice' : 'Edit notice'} onClose={() => setEditing(null)}>
          <AnnForm d={d} notify={notify} item={editing === 'new' ? null : editing} onCancel={() => setEditing(null)}
                   onDone={() => { setEditing(null); nav.refresh(); }} />
        </Sheet>)}
    </Page>
  );
}

// ============================================================================
// History
// ============================================================================
function Messages({ d, notify }) {
  const nav = useNav();
  const s = d.sel || {};
  const [q, setQ] = useState(s.q || '');
  const [more, setMore] = useState(false);
  const [f, setF] = useState({ sender: s.sender || '', from: s.from || '', to: s.to || '' });
  const qRef = useRef();
  const cur = { type: s.type || '', status: s.status || '', sender: s.sender || '', q, from: s.from || '', to: s.to || '' };
  const go = (extra) => navParams(nav.go, d.urls.self, { ...cur, page: 1, ...extra });
  useEffect(() => {
    if ((s.q || '') === q) return undefined;
    clearTimeout(qRef.current); qRef.current = setTimeout(() => go({}), 400);
    return () => clearTimeout(qRef.current);
    /* eslint-disable-next-line */
  }, [q]);
  const processDue = async () => {
    const r = await submitJson(d.urls.process_scheduled, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Failed.');
  };
  const extraCount = [s.sender, s.from, s.to].filter(Boolean).length;
  return (
    <Page d={d}>
      <Head icon="fa-clock-rotate-left" title="History" sub={`${plural(d.total || 0, 'item')} — campaigns, notifications and notices`}>
        {canWrite(d, 'messages_create') && <A to={d.urls.compose} className="rs-btn primary"><i className="fas fa-pen-to-square" aria-hidden="true" /><span className="rs-hide-sm"> New message</span></A>}
        <Menu items={[
          d.urls.reports && { icon: 'fa-chart-line', label: 'Reports', onClick: () => nav.go(d.urls.reports) },
          canWrite(d, 'messages_edit') && { icon: 'fa-forward', label: 'Send scheduled campaigns that are due', onClick: processDue },
        ]} />
      </Head>
      <div className="cm-filters">
        <div className="cm-search grow"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Search title, message or audience…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search history" /></div>
        <select className="cm-sel" value={s.type || ''} onChange={(e) => go({ type: e.target.value })} aria-label="Type">
          <option value="">All types</option>{d.types.map((t) => <option key={t} value={t}>{t}</option>)}</select>
        <button type="button" className={'rs-btn ghost' + (extraCount ? ' on' : '')} onClick={() => setMore(true)}>
          <i className="fas fa-sliders" aria-hidden="true" /><span className="rs-hide-sm"> Filters</span>{extraCount > 0 && <em className="cm-badge">{extraCount}</em>}</button>
      </div>
      <Chips label="Status" value={s.status || ''} onChange={(v) => go({ status: v })} items={[{ value: '', label: 'Any status' }, ...d.statuses.map((t) => ({ value: t, label: t }))]} />
      <section className="rs-card">
        {d.items.length ? <div className="cm-list">{d.items.map((m) => <CampRow key={m.kind + m.id} m={m} />)}</div>
          : <Blank icon="fa-inbox" title="Nothing matches"><p>Try a broader search or clear the filters.</p>
            <button type="button" className="rs-btn ghost" onClick={() => navParams(nav.go, d.urls.self, {})}>Clear filters</button></Blank>}
      </section>
      {d.pages > 1 && (
        <div className="cm-pager">
          <button type="button" className="rs-btn ghost" disabled={!d.has_prev} onClick={() => go({ page: d.page_no - 1 })}><i className="fas fa-chevron-left" aria-hidden="true" /> Newer</button>
          <span>Page {d.page_no} of {d.pages}</span>
          <button type="button" className="rs-btn ghost" disabled={!d.has_next} onClick={() => go({ page: d.page_no + 1 })}>Older <i className="fas fa-chevron-right" aria-hidden="true" /></button>
        </div>)}
      {more && (
        <Sheet title="More filters" onClose={() => setMore(false)}>
          <div className="cm-sheet">
            <Field label="Sent by"><select value={f.sender} onChange={(e) => setF({ ...f, sender: e.target.value })}>
              <option value="">Anyone</option>{d.senders.map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
            <div className="cm-row2">
              <Field label="From" grow><input type="date" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} /></Field>
              <Field label="To" grow><input type="date" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} /></Field>
            </div>
            <div className="cm-sheet-f">
              <button type="button" className="rs-btn ghost" onClick={() => { setMore(false); go({ sender: '', from: '', to: '' }); }}>Clear</button>
              <button type="button" className="rs-btn primary" onClick={() => { setMore(false); go(f); }}>Apply</button>
            </div>
          </div>
        </Sheet>)}
    </Page>
  );
}

// ============================================================================
// Campaign detail
// ============================================================================
function MessageDetail({ d, notify }) {
  const nav = useNav();
  const m = d.msg;
  const [rows, setRows] = useState(d.rows);
  // Open on what still needs doing: the parents not yet messaged.
  const [flt, setFlt] = useState(() => (d.rows.some((r) => r.status !== 'Sent' && r.status !== 'Failed') ? 'Pending' : ''));
  const [q, setQ] = useState('');
  const [limit, setLimit] = useState(60);
  const [copied, setCopied] = useState(false);
  useEffect(() => { setRows(d.rows); }, [d.rows]);
  const canEdit = canWrite(d, 'messages_edit');
  const markSent = async (row) => {
    if (row.status === 'Sent') return;
    setRows((rs) => rs.map((x) => (x.id === row.id ? { ...x, status: 'Sent' } : x)));
    try { await fetch(row.sent_url, { method: 'POST', headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrfToken() } }); }
    catch (_) { setRows((rs) => rs.map((x) => (x.id === row.id ? { ...x, status: row.status } : x))); }
  };
  const action = async (url, opts, redirect) => {
    if (opts && !await confirm(opts)) return;
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message); redirect ? nav.go(r.redirect) : nav.refresh(); }
    else notify('error', r.error || 'That didn’t work.');
  };
  const copyNumbers = () => {
    const nums = rows.filter((r) => r.status !== 'Sent').map((r) => r.phone);
    navigator.clipboard.writeText((nums.length ? nums : rows.map((r) => r.phone)).join(', ')).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1600);
    });
  };
  const linkFor = (r) => (m.channel === 'SMS'
    ? `sms:${r.phone}?body=${encodeURIComponent(r.body)}`
    : `https://wa.me/${r.intl}?text=${encodeURIComponent(r.body)}`);
  const counts = useMemo(() => {
    const c = { Sent: 0, Pending: 0, Failed: 0 };
    rows.forEach((r) => { if (r.status === 'Sent') c.Sent += 1; else if (r.status === 'Failed') c.Failed += 1; else c.Pending += 1; });
    return c;
  }, [rows]);
  const shown = rows.filter((r) => (!flt || (flt === 'Pending' ? (r.status !== 'Sent' && r.status !== 'Failed') : r.status === flt))
    && (!q || (r.parent_name + ' ' + r.student_name + ' ' + r.phone).toLowerCase().includes(q.toLowerCase())));
  const linkable = m.channel === 'SMS' || m.channel === 'WhatsApp';
  const total = rows.length;
  return (
    <Page d={d}>
      <Head icon="fa-paper-plane" title={m.title} sub={`${m.channel} · ${m.audience_label} · ${m.created_at}${m.created_by ? ' by ' + m.created_by : ''}`}>
        {canEdit && d.gateway_ready && d.pending_count > 0 && (
          <button type="button" className="rs-btn primary" onClick={() => action(d.urls.send_gateway, { title: 'Send now?', message: `Send ${plural(d.pending_count, 'pending message')} via ${d.gateway_label}?`, confirmText: 'Send' })}>
            <i className="fas fa-tower-broadcast" aria-hidden="true" /> Send {d.pending_count} now</button>)}
        <Menu items={[
          { icon: copied ? 'fa-check' : 'fa-copy', label: copied ? 'Copied!' : (counts.Pending ? 'Copy pending numbers' : 'Copy all numbers'), onClick: copyNumbers },
          canEdit && counts.Sent < total && { icon: 'fa-check-double', label: 'Mark everyone as sent', onClick: () => action(d.urls.mark_all_sent, { title: 'Mark all as sent?', message: `All ${total} recipients will show as sent.`, confirmText: 'Mark sent' }) },
          canWrite(d, 'messages_export') && { icon: 'fa-file-csv', label: 'Export CSV', href: d.urls.export, native: true, download: true },
          canEdit && m.status === 'Scheduled' && { icon: 'fa-clock', label: 'Cancel the scheduled send', onClick: () => action(d.urls.cancel_schedule, { title: 'Cancel schedule?', message: 'It will stay as a draft you can send by hand.', confirmText: 'Cancel schedule' }) },
          canWrite(d, 'messages_create') && { icon: 'fa-pen-to-square', label: 'New message', onClick: () => nav.go(d.urls.compose) },
          canWrite(d, 'messages_delete') && { icon: 'fa-trash', label: 'Delete campaign', danger: true, onClick: () => action(d.urls.delete, { title: 'Delete campaign?', message: 'The campaign and its delivery log will be removed.', tone: 'danger', confirmText: 'Delete' }, true) },
        ]} />
      </Head>

      <div className="cm-detail">
        <section className="rs-card cm-prog">
          <div className="cm-prog-t">
            <span className="k">Delivered</span>
            <strong>{counts.Sent}<small> of {total}</small></strong>
            <Meter value={counts.Sent} max={total || 1} />
            <div className="cm-prog-f">
              <button type="button" onClick={() => setFlt('Pending')}><i className="fas fa-hourglass-half" aria-hidden="true" /> {counts.Pending} pending</button>
              {counts.Failed > 0 && <button type="button" className="bad" onClick={() => setFlt('Failed')}><i className="fas fa-triangle-exclamation" aria-hidden="true" /> {counts.Failed} failed</button>}
              {d.read_count > 0 && <span className="good"><i className="fas fa-book-open" aria-hidden="true" /> {d.read_count} read</span>}
              {m.status === 'Scheduled' && m.scheduled_at && <span className="info"><i className="fas fa-clock" aria-hidden="true" /> sends {m.scheduled_at}</span>}
            </div>
          </div>
          {!d.gateway_ready && linkable && counts.Pending > 0 && canEdit && (
            <p className="cm-hint"><i className="fas fa-hand-pointer" aria-hidden="true" /> Tap {m.channel === 'SMS' ? <i className="fas fa-comment-sms" aria-hidden="true" /> : <i className="fab fa-whatsapp" aria-hidden="true" />} beside each parent to open the message ready to send — it’s marked as sent for you.</p>)}
        </section>
        <section className="rs-card cm-msgcard">
          <div className="cm-step-h"><ChIcon ch={m.channel} size="sm" /><h3>Message</h3><small>{plural(d.segments || 1, 'SMS segment')}</small></div>
          <div className="cm-msgbody">{m.body}</div>
          <FileLink a={m.attachment} />
        </section>
      </div>

      <section className="rs-card">
        <div className="cm-rc-h">
          <Seg label="Recipients" value={flt} onChange={(v) => { setFlt(v); setLimit(60); }} options={[
            { value: '', label: 'All', count: total }, { value: 'Pending', label: 'Pending', count: counts.Pending },
            { value: 'Sent', label: 'Sent', count: counts.Sent }, ...(counts.Failed ? [{ value: 'Failed', label: 'Failed', count: counts.Failed }] : [])]} />
          <div className="cm-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
            <input type="search" placeholder="Find a parent or student" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a recipient" /></div>
        </div>
        {shown.length ? (
          <div className="cm-list">
            {shown.slice(0, limit).map((r) => (
              <div key={r.id} className={'cm-rcp' + (r.status === 'Sent' ? ' done' : '')}>
                <span className="rs-av" aria-hidden="true">{initials(r.parent_name || r.student_name)}</span>
                <span className="cm-rcp-t"><b>{r.parent_name || 'Parent'}</b>
                  <small>{r.student_name}{r.phone ? ` · ${r.phone}` : ''}</small>
                  {r.status === 'Failed' && r.error && <small className="bad" title={r.error}>{r.error.slice(0, 60)}</small>}</span>
                <span className="cm-rcp-s"><Pill s={r.status} />{r.read && <span className="cm-pill good"><i className="fas fa-book-open" aria-hidden="true" /> Read</span>}</span>
                <span className="cm-rcp-a">
                  {linkable && r.phone && (
                    <a className={'cm-ib ' + (m.channel === 'SMS' ? 'sms' : 'wa')} href={linkFor(r)} target="_blank" rel="noopener"
                       title={m.channel === 'SMS' ? 'Open SMS' : 'Open WhatsApp'} aria-label={(m.channel === 'SMS' ? 'Text ' : 'WhatsApp ') + (r.parent_name || r.student_name)}
                       onClick={() => canEdit && markSent(r)}><i className={chMeta(m.channel)[0]} aria-hidden="true" /></a>)}
                  {r.phone && <a className="cm-ib" href={'tel:' + r.phone} title="Call" aria-label={'Call ' + (r.parent_name || r.student_name)}><i className="fas fa-phone" aria-hidden="true" /></a>}
                  {canEdit && r.status !== 'Sent' && <button type="button" className="cm-ib" title="Mark as sent" aria-label="Mark as sent" onClick={() => markSent(r)}><i className="fas fa-check" aria-hidden="true" /></button>}
                </span>
              </div>))}
            {shown.length > limit && <button type="button" className="cm-showmore" onClick={() => setLimit((l) => l + 120)}>Show {Math.min(120, shown.length - limit)} more of {shown.length}</button>}
          </div>
        ) : <Blank icon="fa-user-check" title={q ? 'No one matches' : flt === 'Pending' ? 'Everyone’s been sent this' : 'No recipients here'} />}
      </section>
    </Page>
  );
}

// ============================================================================
// Reports
// ============================================================================
function Reports({ d }) {
  const nav = useNav();
  const s = d.sel || {};
  const r = d.data || {};
  const [from, setFrom] = useState(s.from || '');
  const [to, setTo] = useState(s.to || '');
  const apply = (f, t) => navParams(nav.go, d.urls.self, { from: f, to: t });
  const iso = (dt) => dt.toISOString().slice(0, 10);
  const preset = (days) => { const t = new Date(); const f = new Date(); f.setDate(t.getDate() - days); setFrom(iso(f)); setTo(iso(t)); apply(iso(f), iso(t)); };
  const exp = (fmt) => `${fmt === 'xlsx' ? d.urls.export_xlsx : d.urls.export_csv}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
  const chMax = Math.max(1, ...(r.by_channel || []).map((c) => c.recipients || 0));
  return (
    <Page d={d}>
      <Head icon="fa-chart-line" title="Reports" sub={`${r.from || ''} → ${r.to || ''}`}>
        {canWrite(d, 'reports_export') && <Menu label="Export" items={[
          { icon: 'fa-file-excel', label: 'Excel', href: exp('xlsx'), native: true },
          { icon: 'fa-file-csv', label: 'CSV', href: exp('csv'), native: true }]} />}
      </Head>
      <div className="cm-filters">
        <Chips label="Period" value="" onChange={(v) => preset(Number(v))} items={[{ value: '7', label: 'Last 7 days' }, { value: '30', label: 'Last 30 days' }, { value: '90', label: 'Last 90 days' }]} />
        <div className="cm-range">
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" />
          <span>→</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" />
          <button type="button" className="rs-btn primary sm" onClick={() => apply(from, to)}>Apply</button>
        </div>
      </div>
      <Tiles items={[
        { label: 'Campaigns', value: r.total_campaigns || 0, sub: `${r.announcements || 0} notices` },
        { label: 'Recipients', value: r.recipients || 0, sub: `${r.sent || 0} delivered` },
        { label: 'Delivery rate', value: r.delivery_rate == null ? '—' : r.delivery_rate, unit: r.delivery_rate == null ? '' : '%',
          tone: r.delivery_rate == null ? '' : r.delivery_rate >= 90 ? 'good' : r.delivery_rate >= 60 ? 'mid' : 'bad', sub: `${r.failed || 0} failed` },
        { label: 'Read', value: r.read || 0, sub: `${r.scheduled || 0} scheduled · ${r.drafts || 0} drafts` },
      ]} />
      <section className="rs-card">
        <div className="rs-card-h"><h3><i className="fas fa-chart-simple" aria-hidden="true" /> By channel</h3></div>
        {(r.by_channel || []).length ? (
          <div className="cm-chrep">{r.by_channel.map((c) => (
            <div key={c.channel} className="cm-chrep-r">
              <span className="n"><ChIcon ch={c.channel} size="sm" /><b>{c.channel}</b></span>
              <span className="bar"><i className={chMeta(c.channel)[1]} style={{ width: ((c.recipients || 0) / chMax * 100) + '%' }} /></span>
              <span className="v"><b>{c.recipients}</b> recipients</span>
              <span className="v">{c.sent} sent</span>
              <span className="v">{plural(c.campaigns, 'campaign')}</span>
            </div>))}</div>
        ) : <Blank icon="fa-chart-line" title="No activity in this period" />}
      </section>
    </Page>
  );
}

// ============================================================================
// Templates
// ============================================================================
function TplForm({ d, notify, t, onDone, onCancel }) {
  const [f, setF] = useState(t ? { name: t.name, category: t.category, body: t.body, is_active: t.is_active } : { name: '', category: '', body: '', is_active: true });
  const [busy, setBusy] = useState(false);
  const ref = useRef();
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const insert = (ph) => {
    const el = ref.current; const s = el ? el.selectionStart : f.body.length; const e = el ? el.selectionEnd : f.body.length;
    set('body', f.body.slice(0, s) + ph + f.body.slice(e));
    requestAnimationFrame(() => { if (el) { el.focus(); el.selectionStart = el.selectionEnd = s + ph.length; } });
  };
  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim() || !f.body.trim()) { notify('error', 'A template needs a name and a message.'); return; }
    setBusy(true);
    const r = await submitJson(t ? t.edit_url : d.add_url, t ? { ...f, is_active: f.is_active ? 'on' : '' } : f);
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Saved.'); onDone(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <form className="cm-sheet" onSubmit={submit}>
      <div className="cm-row2">
        <Field label="Name" grow><input value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Fee reminder" autoFocus /></Field>
        <Field label="Category" grow><input value={f.category} list="cmCats" onChange={(e) => set('category', e.target.value)} placeholder="Fees, Attendance, Event…" />
          <datalist id="cmCats">{['Fees', 'Attendance', 'General', 'Event', ...(d.categories || [])].filter((x, i, a) => a.indexOf(x) === i).map((c) => <option key={c} value={c} />)}</datalist></Field>
      </div>
      <div className="cm-f"><span>Message</span>
        <div className="cm-tagbar">{(d.placeholders || []).map((p) => <button type="button" key={p} className="cm-ph" onClick={() => insert(p)}>{p.replace(/[{}]/g, '')}</button>)}</div>
        <textarea ref={ref} rows={6} value={f.body} onChange={(e) => set('body', e.target.value)} placeholder="Dear {parent}, …" />
        <small className="cm-count"><span>{plural(f.body.length, 'character')}</span><span>{plural(f.body.length ? Math.ceil(f.body.length / 160) : 0, 'SMS segment')}</span></small></div>
      {t && <div className="cm-sched"><span><b>Active</b><small>Inactive templates are hidden from the composer</small></span><Switch on={f.is_active} onChange={(v) => set('is_active', v)} label="Active" /></div>}
      <div className="cm-sheet-f">
        <button type="button" className="rs-btn ghost" onClick={onCancel}>Cancel</button>
        <button className="rs-btn primary" disabled={busy}><i className="fas fa-check" aria-hidden="true" /> {t ? 'Save changes' : 'Save template'}</button>
      </div>
    </form>
  );
}
function Templates({ d, notify }) {
  const nav = useNav();
  const sel = d.sel || {};
  const [q, setQ] = useState(sel.q || '');
  const [editing, setEditing] = useState(null);
  const qRef = useRef();
  const reload = (extra) => navParams(nav.go, d.self_url, { q, category: sel.category || '', ...extra });
  useEffect(() => {
    if ((sel.q || '') === q) return undefined;
    clearTimeout(qRef.current); qRef.current = setTimeout(() => reload({}), 400);
    return () => clearTimeout(qRef.current);
    /* eslint-disable-next-line */
  }, [q]);
  const act = async (url, err, msg) => {
    const r = await submitJson(url, {});
    if (r.ok) { if (msg) notify('success', r.message || msg); nav.refresh(); } else notify('error', r.error || err);
  };
  const del = async (t) => {
    if (!await confirm({ title: 'Delete template?', message: `“${t.name}” will be deleted.`, tone: 'danger', confirmText: 'Delete' })) return;
    act(t.delete_url, 'Could not delete.');
  };
  const list = [...d.templates].sort((a, b) => (b.is_favorite ? 1 : 0) - (a.is_favorite ? 1 : 0));
  return (
    <Page d={d}>
      <Head icon="fa-file-lines" title="Templates" sub="Reusable messages, personalised for every parent.">
        {canWrite(d, 'templates_create') && <button type="button" className="rs-btn primary" onClick={() => setEditing('new')}><i className="fas fa-plus" aria-hidden="true" /> New template</button>}
      </Head>
      <div className="cm-filters">
        <div className="cm-search grow"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Search templates…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search templates" /></div>
      </div>
      {(d.categories || []).length > 0 && (
        <Chips label="Category" value={sel.category || ''} onChange={(v) => reload({ category: v })}
               items={[{ value: '', label: 'All' }, ...d.categories.map((c) => ({ value: c, label: c }))]} />)}
      {list.length ? (
        <div className="cm-tpls">{list.map((t) => (
          <article key={t.id} className={'rs-card cm-tpl' + (t.is_active ? '' : ' off')}>
            <div className="cm-tpl-h">
              {canWrite(d, 'templates_edit') ? (
                <button type="button" className={'cm-star' + (t.is_favorite ? ' on' : '')} aria-pressed={!!t.is_favorite}
                        aria-label={t.is_favorite ? 'Remove from favourites' : 'Add to favourites'} onClick={() => act(t.favorite_url, 'Could not update.')}>
                  <i className={(t.is_favorite ? 'fas' : 'far') + ' fa-star'} aria-hidden="true" /></button>) : null}
              <h3>{t.name}</h3>
              {t.category && <span className="cm-pill">{t.category}</span>}
              {!t.is_active && <span className="cm-pill mid">Inactive</span>}
            </div>
            <p className="cm-tpl-b">{t.body}</p>
            <div className="cm-tpl-f">
              <A to={t.use_url} className="rs-btn primary sm"><i className="fas fa-paper-plane" aria-hidden="true" /> Use</A>
              <Menu label="Options" items={[
                canWrite(d, 'templates_edit') && { icon: 'fa-pen', label: 'Edit', onClick: () => setEditing(t) },
                canWrite(d, 'templates_create') && { icon: 'fa-copy', label: 'Duplicate', onClick: () => act(t.duplicate_url, 'Could not duplicate.', 'Duplicated.') },
                canWrite(d, 'templates_delete') && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => del(t) },
              ]} />
            </div>
          </article>))}</div>
      ) : (
        <Blank icon="fa-file-lines" title={q || sel.category ? 'No templates match' : 'No templates yet'}>
          <p>Save messages you send often — fee reminders, absence notices, event invitations.</p>
          {canWrite(d, 'templates_create') && !q && <button type="button" className="rs-btn primary" onClick={() => setEditing('new')}><i className="fas fa-plus" aria-hidden="true" /> New template</button>}
        </Blank>)}
      {editing && (
        <Sheet title={editing === 'new' ? 'New template' : 'Edit template'} onClose={() => setEditing(null)}>
          <TplForm d={d} notify={notify} t={editing === 'new' ? null : editing} onCancel={() => setEditing(null)}
                   onDone={() => { setEditing(null); nav.refresh(); }} />
        </Sheet>)}
    </Page>
  );
}

// ============================================================================
// Contacts
// ============================================================================
function Contacts({ d }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q || '');
  const qRef = useRef();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, q, missing: d.missing ? 1 : '', ...extra });
  useEffect(() => {
    if ((d.q || '') === q) return undefined;
    clearTimeout(qRef.current); qRef.current = setTimeout(() => go({}), 400);
    return () => clearTimeout(qRef.current);
    /* eslint-disable-next-line */
  }, [q]);
  const cov = d.cov || { with_contact: 0, total: 0, pct: 0, without_contact: 0 };
  return (
    <Page d={d}>
      <Head icon="fa-address-book" title="Contacts" sub={`${cov.with_contact} of ${cov.total} students have a parent phone (${cov.pct}%)`} />
      <div className="cm-filters">
        <div className="cm-search grow"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Search student name or ID" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search students" /></div>
        <select className="cm-sel" value={d.class_id} onChange={(e) => go({ class_id: e.target.value })} aria-label="Class">
          <option value="">All classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        {d.terms.length > 1 && (
          <select className="cm-sel" value={d.term_id} onChange={(e) => go({ term_id: e.target.value })} aria-label="Term">
            {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select>)}
      </div>
      <Seg label="Show" value={d.missing ? 'missing' : ''} onChange={(v) => go({ missing: v ? 1 : '' })} options={[
        { value: '', label: 'Everyone' }, { value: 'missing', icon: 'fa-phone-slash', label: 'No contact', count: cov.without_contact }]} />
      <section className="rs-card">
        {d.rows.length ? (
          <div className="cm-list">{d.rows.map((row) => (
            <div key={row.student.id} className={'cm-ct' + (row.contacts.length ? '' : ' none')}>
              <span className="rs-av" aria-hidden="true">{initials(row.student.full_name)}</span>
              <span className="cm-ct-t"><b>{row.student.full_name}</b><small>{row.student.student_id}</small></span>
              <span className="cm-ct-c">
                {row.contacts.length ? row.contacts.map((c, i) => (
                  <span key={i} className="cm-ct-p">
                    <span className="who">{c.name || 'Parent'}{c.relationship && <small> · {c.relationship}</small>}{c.is_primary && row.contacts.length > 1 && <em>Primary</em>}</span>
                    <a href={'tel:' + c.phone_number} className="num">{c.phone_number}</a>
                    <a href={'tel:' + c.phone_number} className="cm-ib" aria-label={'Call ' + (c.name || 'parent')} title="Call"><i className="fas fa-phone" aria-hidden="true" /></a>
                    <a href={'https://wa.me/' + c.wa_intl} target="_blank" rel="noopener" className="cm-ib wa" aria-label={'WhatsApp ' + (c.name || 'parent')} title="WhatsApp"><i className="fab fa-whatsapp" aria-hidden="true" /></a>
                  </span>)) : <span className="cm-pill mid"><i className="fas fa-phone-slash" aria-hidden="true" /> No parent contact</span>}
              </span>
              <a href={row.student.view_url} className="cm-ib" title={row.contacts.length ? 'Open profile' : 'Add a contact on the profile'} aria-label={'Open ' + row.student.full_name}>
                <i className={'fas ' + (row.contacts.length ? 'fa-chevron-right' : 'fa-user-plus')} aria-hidden="true" /></a>
            </div>))}</div>
        ) : <Blank icon="fa-address-book" title="No students found"><p>Try another class or search.</p></Blank>}
      </section>
      <p className="cm-mute cm-foot">Add or change a parent’s number on the student’s profile.</p>
    </Page>
  );
}

// ============================================================================
// Settings
// ============================================================================
function Settings({ d, notify }) {
  const nav = useNav();
  const [cfg, setCfg] = useState(d.cfg);
  const [phoneNo, setPhoneNo] = useState('');
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [autos, setAutos] = useState(d.automations || []);
  const [autoDirty, setAutoDirty] = useState(false);
  const canEdit = canWrite(d, 'settings_edit');
  const set = (k, v) => setCfg((s) => ({ ...s, [k]: v }));
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.urls.save, cfg);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const test = async (e) => {
    e.preventDefault();
    if (!phoneNo.trim()) { notify('error', 'Enter a phone number to send the test to.'); return; }
    setTesting(true);
    const r = await submitJson(d.urls.test, { phone: phoneNo });
    setTesting(false);
    if (r.ok) notify('success', r.message); else notify('error', r.error || 'Test failed.');
  };
  const toggleAuto = (key) => { setAutos((a) => a.map((x) => (x.key === key ? { ...x, enabled: !x.enabled } : x))); setAutoDirty(true); };
  const saveAutos = async () => {
    const fields = {};
    autos.forEach((a) => { if (a.enabled) fields[a.key] = 'on'; });
    const r = await submitJson(d.urls.save_automations, fields);
    if (r.ok) { notify('success', r.message); setAutoDirty(false); } else notify('error', r.error || 'Could not save.');
  };
  const byCat = useMemo(() => {
    const g = {};
    autos.forEach((a) => { (g[a.category || 'Other'] = g[a.category || 'Other'] || []).push(a); });
    return g;
  }, [autos]);
  return (
    <Page d={d}>
      <Head icon="fa-gear" title="Settings" sub="SMS gateway and automatic notifications." />
      <div className={'cm-gw ' + (d.configured ? 'ok' : 'off')}>
        <span className="cm-gw-i"><i className={'fas ' + (d.configured ? 'fa-tower-broadcast' : 'fa-plug')} aria-hidden="true" /></span>
        <div><b>{d.configured ? `SMS sending is on — ${d.provider_label}` : 'SMS auto-send is off'}</b>
          <small>{d.configured
            ? (d.balance_ok ? `Balance: ${d.balance}` : `Balance unavailable${d.balance ? ` (${d.balance})` : ''}`)
            : 'Messages go out through one-tap WhatsApp / SMS links. Add a provider key below to send automatically.'}</small></div>
      </div>
      <div className="cm-grid2">
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-sliders" aria-hidden="true" /> SMS provider</h3></div>
          {!canEdit && <p className="cm-mute">You don’t have permission to change gateway settings.</p>}
          <form onSubmit={save} className="cm-stack">
            <fieldset disabled={!canEdit} className="cm-stack">
              <div className="cm-f"><span>Provider</span>
                <div className="cm-provs" role="radiogroup" aria-label="Provider">{d.providers.map((p) => (
                  <button type="button" role="radio" aria-checked={cfg.provider === p.key} key={p.key}
                          className={'cm-aud-i' + (cfg.provider === p.key ? ' on' : '')} onClick={() => set('provider', p.key)}>
                    <i className={'fas ' + (p.key === 'termii' || p.key === 'twilio' ? 'fa-tower-broadcast' : 'fa-hand-pointer')} aria-hidden="true" />
                    <span>{p.label}</span></button>))}</div></div>
              {cfg.provider && cfg.provider !== 'none' && (
                <Field label="Sender ID / From number" hint="Termii: your approved sender ID. Twilio: your number in +E.164 format.">
                  <input value={cfg.sender || ''} placeholder="e.g. SchoolName or +1415…" onChange={(e) => set('sender', e.target.value)} /></Field>)}
              {cfg.provider === 'termii' && (
                <Field label="Termii API key"><input value={cfg.termii_key || ''} placeholder="Paste your Termii API key" autoComplete="off" onChange={(e) => set('termii_key', e.target.value)} /></Field>)}
              {cfg.provider === 'twilio' && (
                <div className="cm-row2">
                  <Field label="Account SID" grow><input value={cfg.twilio_sid || ''} placeholder="ACxxxx…" autoComplete="off" onChange={(e) => set('twilio_sid', e.target.value)} /></Field>
                  <Field label="Auth token" grow><input type="password" value={cfg.twilio_token || ''} placeholder="Auth token" autoComplete="off" onChange={(e) => set('twilio_token', e.target.value)} /></Field>
                </div>)}
              <div><button type="submit" className="rs-btn primary" disabled={busy}><i className="fas fa-check" aria-hidden="true" /> Save provider</button></div>
            </fieldset>
          </form>
          {canEdit && d.configured && (
            <form onSubmit={test} className="cm-test">
              <Field label="Send a test SMS" grow><input value={phoneNo} placeholder="08031234567" inputMode="tel" onChange={(e) => setPhoneNo(e.target.value)} /></Field>
              <button type="submit" className="rs-btn ghost" disabled={testing}><i className={'fas ' + (testing ? 'fa-spinner fa-spin' : 'fa-vial')} aria-hidden="true" /> Send test</button>
            </form>)}
        </section>
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-circle-question" aria-hidden="true" /> How sending works</h3></div>
          <ol className="cm-how">
            <li><b>No provider?</b> Each campaign lists every parent with a one-tap WhatsApp / SMS button — nothing else to set up.</li>
            <li><b>Add Termii or Twilio</b> and a <em>Send now</em> button appears on every campaign; messages go out from the server.</li>
            <li><b>Failures are flagged</b> with the provider’s reason so you can retry.</li>
            <li><b>Your keys stay in your database.</b> Switch providers any time.</li>
          </ol>
        </section>
      </div>
      {d.automations && (
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-robot" aria-hidden="true" /> Automatic notifications</h3>
            <small>{autos.filter((a) => a.enabled).length} of {autos.length} on</small></div>
          {!d.is_admin && <p className="cm-mute">Only administrators can change these.</p>}
          {Object.entries(byCat).map(([cat, list]) => (
            <div key={cat} className="cm-autos"><h4>{cat}</h4>
              {list.map((a) => (
                <div className={'cm-auto' + (a.enabled ? '' : ' off')} key={a.key}>
                  <span><b>{a.label}</b><small>{a.description}</small></span>
                  <Switch on={a.enabled} onChange={() => toggleAuto(a.key)} disabled={!d.is_admin} label={a.label} />
                </div>))}
            </div>))}
          {d.is_admin && autoDirty && <Bar><span className="rs-bar-t"><b>Unsaved changes</b><small>Automatic notifications</small></span>
            <button type="button" className="rs-btn primary" onClick={saveAutos}><i className="fas fa-check" aria-hidden="true" /> Save</button></Bar>}
        </section>)}
    </Page>
  );
}

// ============================================================================
const SCREENS = { dashboard: Dashboard, compose: Compose, announcements: Announcements,
  templates: Templates, contacts: Contacts, messages: Messages, message_detail: MessageDetail,
  reports: Reports, settings: Settings, inbox: Inbox };

export default function CommunicationApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [toast, setToast] = useState(null);
  const notify = (tone, text) => setToast({ tone, text, at: Date.now() });
  const Screen = SCREENS[d.page] || Dashboard;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        <Screen d={d} notify={notify} />
        {toast && <Toast key={toast.at} tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}
      </SectionShell>
    </NavCtx.Provider>
  );
}
