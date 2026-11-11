// Settings — the redesigned hub, branches, backup and audit screens.
// Hub: a health strip (backups, payments, errors, people) that says what needs
// attention, then every setting grouped by job with instant search.
import React, { useState } from 'react';
import { useSave, submitJson, postFile } from '../lib/forms';
import { canWrite } from '../lib/perms';
import { csrfToken } from '../lib/api';
import { useNav, navParams } from '../lib/section';
import { confirm } from '../components/ui';
import { Head, Tiles, Chips, Seg, Sheet, Blank, Bar, usePhone } from '../subjects/results';
import { A, Field, Toggle, Switch, Pill, SearchBox, plural } from '../components/appkit';

const ago = (n) => (n == null ? 'Never' : n <= 0 ? 'Today' : n === 1 ? 'Yesterday' : `${n} days ago`);

// ---- Settings home ----------------------------------------------------------
export function Index({ d }) {
  const [q, setQ] = useState('');
  const u = d.urls;
  const h = d.health || {};
  const hasAny = (...subs) => subs.some((s) => d.perms && d.perms.subs && d.perms.subs[s]);
  const admin = d.is_admin && d.is_central;
  const groups = [
    { key: 'school', title: 'School setup', tone: 'blue', items: [
      hasAny('school_info') && [u.school, 'fa-school', 'School info', 'Name, logo, address and contacts'],
      hasAny('academic_config') && [u.academic, 'fa-clock', 'Academic rules', 'School hours, student IDs, promotion pass mark'],
      hasAny('grades_view', 'grades_edit') && [u.grades, 'fa-star', 'Grade scale', 'A1–F9 bands and remarks'],
      hasAny('assessments_view', 'assessments_edit') && [u.assessments, 'fa-list-check', 'Assessments', 'CA tests, exams and max scores'],
      hasAny('traits_view', 'traits_edit') && [u.traits, 'fa-star-half-stroke', 'Behaviour traits', 'Affective domain on report cards'],
      hasAny('slots_view', 'slots_edit') && [u.timetable_slots, 'fa-calendar-days', 'Timetable periods', 'Period times and breaks'],
      u.exam_subjects && [u.exam_subjects, 'fa-file-signature', 'Exam subjects', 'WAEC/JAMB catalogue and compulsories', true],
    ] },
    { key: 'people', title: 'People & access', tone: 'violet', items: [
      admin && [u.people || u.users, 'fa-users-gear', 'Users & permissions', h.users != null ? `${plural(h.users, 'active account')}` : 'Accounts, roles and access', !!u.people],
      admin && u.invites && [u.invites, 'fa-user-plus', 'Staff invites', h.pending_signups ? `${plural(h.pending_signups, 'sign-up')} waiting for approval` : 'Self sign-up links for new staff', true, h.pending_signups ? 'warn' : null],
      admin && [u.branches, 'fa-code-branch', 'Branches', h.branches != null ? plural(h.branches, 'active branch', 'active branches') : 'Campuses and student-ID prefixes'],
      u.notifications && [u.notifications, 'fa-bell', 'My notifications', 'Which alerts you get, and where', true],
    ] },
    { key: 'money', title: 'Money', tone: 'green', items: [
      u.payments && [u.payments, 'fa-credit-card', 'Online fee payments', h.payments_on ? 'Connected — parents can pay online' : 'Not set up — parents can’t pay online yet', true, h.payments_on ? 'good' : 'warn'],
    ] },
    { key: 'data', title: 'Data & safety', tone: 'amber', items: [
      admin && [u.backup, 'fa-database', 'Backup & restore', h.backup_days != null ? `Last snapshot: ${ago(h.backup_days).toLowerCase()}` : 'No snapshot yet', false, h.backup_days == null || h.backup_days > 7 ? 'warn' : null],
      admin && [u.audit, 'fa-clipboard-list', 'Audit log', 'Who changed what, and when'],
      admin && u.error_log && [u.error_log, 'fa-bug', 'Error log', h.errors_24h ? `${plural(h.errors_24h, 'error')} in the last 24 hours` : 'No errors in the last 24 hours', true, h.errors_24h ? 'bad' : null],
      admin && u.performance && [u.performance, 'fa-gauge-high', 'Performance', 'Slow pages and database queries', true],
    ] },
    { key: 'more', title: 'Integrations & sharing', tone: 'teal', items: [
      hasAny('ocr_manage') && [u.ocr, 'fa-robot', 'AI result reading', 'Optional key for reading result images'],
      admin && u.admissions && [u.admissions, 'fa-graduation-cap', 'University admissions data', 'Universities, courses and cut-offs', true],
      u.share && [u.share, 'fa-qrcode', 'Share the app', 'QR code and links for staff, parents and students', true],
    ] },
  ].map((g) => ({ ...g, items: g.items.filter(Boolean).filter((it) => !q || (it[2] + ' ' + it[3]).toLowerCase().includes(q.toLowerCase())) }))
    .filter((g) => g.items.length);

  const pulse = admin ? [
    u.backup && { to: u.backup, icon: 'fa-database', k: 'Last backup', v: ago(h.backup_days), tone: h.backup_days == null || h.backup_days > 7 ? 'warn' : 'good' },
    u.payments && { to: u.payments, ext: true, icon: 'fa-credit-card', k: 'Online payments', v: h.payments_on ? 'On' : 'Off', tone: h.payments_on ? 'good' : 'warn' },
    u.error_log && h.errors_24h != null && { to: u.error_log, ext: true, icon: 'fa-bug', k: 'Errors · 24h', v: h.errors_24h, tone: h.errors_24h ? 'bad' : 'good' },
    h.pending_signups ? { to: u.invites, ext: true, icon: 'fa-user-clock', k: 'Sign-ups waiting', v: h.pending_signups, tone: 'warn' } : null,
  ].filter(Boolean) : [];

  return (
    <div className="rs cm sx">
      <Head icon="fa-gear" title="Settings" sub="Everything that shapes how the school runs — grouped by job." />
      {pulse.length > 0 && (
        <div className="sx-pulse">{pulse.map((p) => (
          <A key={p.k} to={p.to} native={p.ext} className={'sx-pl ' + p.tone}>
            <i className={'fas ' + p.icon} aria-hidden="true" /><span><small>{p.k}</small><b>{p.v}</b></span></A>))}</div>)}
      <div className="sx-search"><SearchBox value={q} onChange={setQ} placeholder="Find a setting…" /></div>
      {!groups.length && <Blank icon="fa-magnifying-glass" title="No setting matches"><p>Try another word.</p></Blank>}
      {groups.map((g) => (
        <section key={g.key} className="sx-group">
          <h2>{g.title}</h2>
          <div className="sx-grid">{g.items.map(([url, icon, title, sub, ext, tone]) => (
            <A key={title} to={url} native={ext} className={'sx-card ' + (tone || '')}>
              <span className={'sx-ic ' + g.tone}><i className={'fas ' + icon} aria-hidden="true" /></span>
              <span className="sx-t"><b>{title}</b><small>{tone && <i className={'sx-dot ' + tone} />}{sub}</small></span>
              <i className="fas fa-chevron-right sx-go" aria-hidden="true" />
            </A>))}</div>
        </section>))}
    </div>
  );
}

// ---- Branches ---------------------------------------------------------------
const BLANK_BRANCH = { name: '', code: '', phone: '', address: '', is_active: true, make_default: false };

function BranchSheet({ b, url, save, onClose, refresh }) {
  const [f, setF] = useState(b ? { name: b.name, code: b.code || '', phone: b.phone || '', address: b.address || '', is_active: b.is_active, make_default: false } : BLANK_BRANCH);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = (e) => {
    e.preventDefault();
    const fields = { name: f.name, code: f.code, phone: f.phone, address: f.address };
    if (b) { if (f.is_active) fields.is_active = 'on'; if (f.make_default) fields.make_default = 'on'; }
    save(url, fields, () => { onClose(); refresh(); });
  };
  return (
    <Sheet title={b ? `Edit ${b.name}` : 'Add a branch'} onClose={onClose}>
      <form onSubmit={submit} className="sx-form">
        <Field label="Branch name"><input value={f.name} onChange={set('name')} placeholder="e.g. Jemila" required autoFocus /></Field>
        <Field label="Code" hint={`Student IDs in this branch start with it — e.g. ${(f.code || 'JM')}00042`}>
          <input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '') })} placeholder="e.g. JM" maxLength={10} /></Field>
        <Field label="Phone"><input value={f.phone} onChange={set('phone')} inputMode="tel" /></Field>
        <Field label="Address"><input value={f.address} onChange={set('address')} /></Field>
        {b && <Toggle title="Active" sub="Inactive branches are hidden from pickers" on={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} disabled={b.is_default} />}
        {b && !b.is_default && <Toggle title="Make this the default branch" sub="Unassigned records belong here" on={f.make_default} onChange={(v) => setF({ ...f, make_default: v })} />}
        <button type="submit" className="rs-btn primary wide"><i className="fas fa-check" aria-hidden="true" /> {b ? 'Save changes' : 'Add branch'}</button>
      </form>
    </Sheet>
  );
}

export function Branches({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [edit, setEdit] = useState(null);   // null | 'new' | branch
  const rows = d.branches;
  const total = rows.reduce((n, b) => n + (b.students || 0), 0) + ((d.unassigned && d.unassigned.students) || 0);
  const un = d.unassigned || {};
  return (
    <div className="rs cm sx">
      <Head icon="fa-code-branch" title="Branches" sub="Each campus, its people and its student-ID prefix.">
        <button type="button" className="rs-btn primary" onClick={() => setEdit('new')}><i className="fas fa-plus" aria-hidden="true" /> Add branch</button>
      </Head>
      <Tiles items={[
        { label: 'Active branches', value: rows.filter((b) => b.is_active).length },
        { label: 'Students', value: total },
        { label: 'Staff accounts', value: rows.reduce((n, b) => n + (b.staff || 0), 0) + (un.staff || 0) },
        un.students ? { label: 'Students with no branch', value: un.students, tone: 'warn', sub: `Count under the default branch` } : null,
      ]} />
      {!rows.length ? (
        <Blank icon="fa-code-branch" title="One school, one campus">
          <p>Add branches only if the school has more than one campus. Each branch sees only its own students and staff.</p>
          <button type="button" className="rs-btn primary" onClick={() => setEdit('new')}><i className="fas fa-plus" aria-hidden="true" /> Add the first branch</button></Blank>
      ) : (
        <div className="sx-branches">{rows.map((b) => {
          const share = total ? Math.round(100 * (b.students || 0) / total) : 0;
          return (
            <article key={b.id} className={'rs-card sx-br' + (b.is_active ? '' : ' off')}>
              <div className="sx-br-h">
                <span className="sx-br-code">{b.code || b.name.slice(0, 2).toUpperCase()}</span>
                <span className="sx-t"><b>{b.name}</b><small>{[b.phone, b.address].filter(Boolean).join(' · ') || 'No contact details'}</small></span>
                <button type="button" className="rs-btn sm ghost" onClick={() => setEdit(b)} aria-label={`Edit ${b.name}`}><i className="fas fa-pen" aria-hidden="true" /> Edit</button>
              </div>
              <div className="sx-br-pills">
                {b.is_default && <Pill tone="good" icon="fa-star">Default</Pill>}
                {!b.is_active && <Pill tone="bad">Inactive</Pill>}
                {b.code ? <Pill icon="fa-id-card">IDs {b.code}#####</Pill> : <Pill tone="warn" icon="fa-id-card">No code — uses school prefix</Pill>}
              </div>
              <div className="sx-br-n">
                <span><b>{b.students}</b>students</span><span><b>{b.staff}</b>staff</span><span><b>{b.classes}</b>classes this term</span>
              </div>
              <div className="sx-share" title={`${share}% of students`}><i style={{ width: share + '%' }} /></div>
            </article>);
        })}</div>
      )}
      <details className="rs-card sx-note"><summary><i className="fas fa-circle-info" aria-hidden="true" /> How branches work</summary>
        <p>Central staff (Director of Studies, Exams &amp; Standards, IT) see every branch; branch staff see only their own. The <b>default</b> branch holds new and unassigned records. A branch’s <b>code</b> becomes its student-ID prefix — Settings → Academic rules sets the school-wide prefix for branches without one.</p>
      </details>
      {edit && <BranchSheet b={edit === 'new' ? null : edit} url={edit === 'new' ? d.add_url : edit.edit_url} save={save} refresh={nav.refresh} onClose={() => setEdit(null)} />}
    </div>
  );
}

// ---- Backup & restore -------------------------------------------------------
const size = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

export function Backup({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [busy, setBusy] = useState(false);
  const [word, setWord] = useState('');
  const [file, setFile] = useState('');
  const days = d.last_backup_days;
  const tone = days == null || days > 7 ? 'warn' : 'good';
  const createSnap = async () => { setBusy(true); await save(d.create_url, {}, () => nav.refresh()); setBusy(false); };
  const onRestore = async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    if (await confirm({ title: 'Replace all data?', message: `Everything in the app will be replaced with “${file}”. A copy of the current data is saved first.`, confirmText: 'Restore', tone: 'danger' }))
      form.submit();
  };
  return (
    <div className="rs cm sx">
      <Head icon="fa-database" title="Backup & restore" sub="Keep a copy of the school’s data somewhere safe." />
      <section className={'rs-card sx-hero ' + tone}>
        <span className="sx-hero-ic"><i className={'fas ' + (tone === 'good' ? 'fa-shield-halved' : 'fa-triangle-exclamation')} aria-hidden="true" /></span>
        <div className="sx-t"><b>{days == null ? 'No snapshot yet' : `Last snapshot ${ago(days).toLowerCase()}`}</b>
          <small>{tone === 'good' ? 'Snapshots are taken automatically every day. Download one now and then to keep a copy off the server.' : 'Create a snapshot now, and download a copy to keep off the server.'}</small></div>
        <button type="button" className="rs-btn primary" onClick={createSnap} disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-camera')} aria-hidden="true" /> Snapshot now</button>
      </section>
      <Tiles items={[
        { label: 'Database size', value: size(d.db_size) },
        { label: 'Students', value: d.counts.students },
        { label: 'Sessions', value: d.counts.sessions, sub: `${d.counts.terms} terms` },
        { label: 'Users', value: d.counts.users },
      ]} />
      <div className="sx-acts">
        <a href={d.download_url} data-native className="rs-card sx-act"><i className="fas fa-download" aria-hidden="true" /><span className="sx-t"><b>Download full backup</b><small>The whole database (.db) — use this to restore</small></span></a>
        <a href={d.export_json_url} data-native className="rs-card sx-act"><i className="fas fa-file-code" aria-hidden="true" /><span className="sx-t"><b>Export as JSON</b><small>Readable data for other software</small></span></a>
      </div>
      <section className="rs-card sx-list">
        <div className="sx-list-h"><h3><i className="fas fa-box-archive" aria-hidden="true" /> Snapshots on the server</h3><span className="cm-mute">{plural(d.backups.length, 'snapshot')}</span></div>
        {d.backups.length ? d.backups.map((b, i) => (
          <div key={b.name} className="sx-snap">
            <i className="fas fa-clock-rotate-left" aria-hidden="true" />
            <span className="sx-t"><b>{b.modified}{i === 0 && <Pill tone="good">Latest</Pill>}</b><small>{b.name} · {size(b.size)}</small></span>
            <a href={b.download_url} data-native className="rs-btn sm ghost" aria-label={`Download ${b.name}`}><i className="fas fa-download" aria-hidden="true" /><span className="sx-hide-ph">Download</span></a>
          </div>)) : <p className="cm-mute sx-empty">No snapshots yet — they appear daily, or when you tap “Snapshot now”.</p>}
      </section>
      <section className="rs-card sx-danger">
        <h3><i className="fas fa-triangle-exclamation" aria-hidden="true" /> Restore from a backup</h3>
        <p>This replaces <b>all</b> current data with the file you choose. A copy of today’s data is saved first, so it can be undone.</p>
        <form method="POST" action={d.restore_url} encType="multipart/form-data" onSubmit={onRestore} className="sx-form">
          <input type="hidden" name="_csrf_token" value={csrfToken()} />
          <label className="sx-file"><i className="fas fa-file-arrow-up" aria-hidden="true" />
            <span>{file || 'Choose a backup file (.db or .sql)'}</span>
            <input type="file" name="file" accept=".db,.sql" required onChange={(e) => setFile(e.target.files[0] ? e.target.files[0].name : '')} /></label>
          <Field label="Type RESTORE to confirm"><input name="confirm" value={word} onChange={(e) => setWord(e.target.value)} autoComplete="off" placeholder="RESTORE" pattern="RESTORE" required /></Field>
          <button type="submit" className="rs-btn danger" disabled={!file || word !== 'RESTORE'}><i className="fas fa-upload" aria-hidden="true" /> Restore this backup</button>
        </form>
      </section>
    </div>
  );
}

// ---- Audit log --------------------------------------------------------------
function verb(a) {
  const s = (a || '').toLowerCase();
  if (/delete|remove|clear|purge/.test(s)) return ['fa-trash-can', 'bad'];
  if (/restore|backup|import/.test(s)) return ['fa-database', 'warn'];
  if (/permission|role|grant|group/.test(s)) return ['fa-key', 'warn'];
  if (/password|mfa|login|logout|lock/.test(s)) return ['fa-lock', 'info'];
  if (/create|add|new|invite|admit/.test(s)) return ['fa-plus', 'good'];
  if (/update|edit|change|set|save/.test(s)) return ['fa-pen', 'info'];
  if (/pay|fee|invoice|receipt/.test(s)) return ['fa-naira-sign', 'good'];
  return ['fa-circle-dot', ''];
}
const human = (a) => (a || '').replace(/[._]+/g, ' ');

export function Audit({ d }) {
  const nav = useNav();
  const phone = usePhone();
  const [f, setF] = useState({ ...d.filters });
  const [more, setMore] = useState(!!(d.filters.user || d.filters.action));
  const [open, setOpen] = useState(null);
  const st = d.stats || {};
  const go = (next, extra = {}) => {
    const p = {};
    ['q', 'action', 'user', 'from', 'to'].forEach((k) => { if (next[k]) p[k] = next[k]; });
    navParams(nav.go, d.base_url, { ...p, ...extra });
  };
  const apply = (patch) => { const n = { ...f, ...patch }; setF(n); go(n); };
  const range = !f.from && !f.to ? 'all' : f.to ? 'custom' : f.from === st.today_iso ? 'today' : f.from === st.week_iso ? 'week' : f.from === st.month_iso ? 'month' : 'custom';
  const pg = d.pagination || { page: 1, pages: 1, total: 0 };
  const days = [];
  d.logs.forEach((l) => { const last = days[days.length - 1]; if (last && last.day === l.day) last.rows.push(l); else days.push({ day: l.day, label: l.day_label, rows: [l] }); });
  const filtered = ['q', 'action', 'user', 'from', 'to'].some((k) => d.filters[k]);
  return (
    <div className="rs cm sx">
      <Head icon="fa-clipboard-list" title="Audit log" sub="Every sensitive change — who, what, when and from where. Entries can’t be edited or deleted." />
      <Tiles items={[
        { label: 'Today', value: st.today ?? '—' },
        { label: 'Last 7 days', value: st.week ?? '—' },
        { label: 'People active · 7 days', value: st.people ?? '—' },
        { label: 'Deletes & access changes · 7 days', value: st.risky ?? '—', tone: st.risky ? 'warn' : null },
      ]} />
      <section className="rs-card sx-filters">
        <form onSubmit={(e) => { e.preventDefault(); go(f); }} className="sx-frow">
          <SearchBox value={f.q} onChange={(v) => setF({ ...f, q: v })} placeholder="Search action, person, record…" />
          <button type="submit" className="rs-btn primary sm">Search</button>
          <button type="button" className={'rs-btn sm ghost' + (more ? ' on' : '')} onClick={() => setMore(!more)}><i className="fas fa-sliders" aria-hidden="true" />{!phone && ' Filters'}</button>
        </form>
        <Chips label="Period" value={range} onChange={(v) => v !== 'custom' && apply({ from: v === 'all' ? '' : st[v + '_iso'], to: '' })} items={[
          { value: 'all', label: 'All time' }, { value: 'today', label: 'Today' }, { value: 'week', label: '7 days' }, { value: 'month', label: '30 days' },
          ...(range === 'custom' ? [{ value: 'custom', label: 'Custom' }] : [])]} />
        {more && (
          <div className="sx-more">
            <Field label="Action"><select value={f.action} onChange={(e) => apply({ action: e.target.value })}>
              <option value="">All actions</option>{d.actions.map((a) => <option key={a} value={a}>{human(a)}</option>)}</select></Field>
            <Field label="Person"><input value={f.user} onChange={(e) => setF({ ...f, user: e.target.value })} onBlur={() => f.user !== d.filters.user && go(f)} placeholder="Name" /></Field>
            <Field label="From"><input type="date" value={f.from} onChange={(e) => apply({ from: e.target.value })} /></Field>
            <Field label="To"><input type="date" value={f.to} onChange={(e) => apply({ to: e.target.value })} /></Field>
          </div>)}
        {filtered && <button type="button" className="sx-clear" onClick={() => { setF({ q: '', action: '', user: '', from: '', to: '' }); nav.go(d.base_url); }}>
          <i className="fas fa-xmark" aria-hidden="true" /> Clear filters · {plural(pg.total, 'entry', 'entries')}</button>}
      </section>
      {!d.logs.length ? <Blank icon="fa-clipboard-list" title={filtered ? 'Nothing matches' : 'Nothing recorded yet'}><p>{filtered ? 'Try a wider period or fewer filters.' : 'Sensitive actions appear here as people use the app.'}</p></Blank> : days.map((g) => (
        <section key={g.day} className="rs-card sx-day">
          <h3>{g.label}<span>{plural(g.rows.length, 'entry', 'entries')}</span></h3>
          {g.rows.map((l) => {
            const [ic, tn] = verb(l.action);
            const isOpen = open === l.id;
            return (
              <div key={l.id} className={'sx-ev' + (isOpen ? ' open' : '')}>
                <button type="button" className="sx-ev-row" onClick={() => setOpen(isOpen ? null : l.id)} aria-expanded={isOpen}>
                  <span className={'sx-ev-ic ' + tn}><i className={'fas ' + ic} aria-hidden="true" /></span>
                  <span className="sx-t"><span className="sx-ev-l"><b>{l.user}</b> {human(l.action)}{l.target_label && <> · <em>{l.target_label}</em></>}</span>
                    <small>{[l.time, l.role, l.branch].filter(Boolean).join(' · ')}</small></span>
                  <i className={'fas fa-chevron-' + (isOpen ? 'up' : 'down') + ' sx-go'} aria-hidden="true" />
                </button>
                {isOpen && (
                  <dl className="sx-ev-d">
                    {l.detail && <><dt>Detail</dt><dd className="pre">{l.detail}</dd></>}
                    {l.target_type && <><dt>Record</dt><dd>{l.target_type}{l.target_label ? ` — ${l.target_label}` : ''}</dd></>}
                    <dt>When</dt><dd>{l.created_at}</dd>
                    <dt>Action code</dt><dd><code>{l.action}</code></dd>
                    {l.ip_address && <><dt>IP address</dt><dd>{l.ip_address}</dd></>}
                    {l.user_agent && <><dt>Device</dt><dd className="ua">{l.user_agent}</dd></>}
                    <dd className="sx-ev-a"><button type="button" className="rs-btn sm ghost" onClick={() => apply({ user: l.user, q: '' })}>All by {l.user}</button>
                      <button type="button" className="rs-btn sm ghost" onClick={() => apply({ action: l.action })}>All “{human(l.action)}”</button></dd>
                  </dl>)}
              </div>);
          })}
        </section>))}
      {pg.pages > 1 && (
        <div className="sx-pager">
          <button type="button" className="rs-btn sm ghost" disabled={!pg.has_prev} onClick={() => go(d.filters, { page: pg.prev_page })}><i className="fas fa-chevron-left" aria-hidden="true" /> Newer</button>
          <span className="cm-mute">Page {pg.page} of {pg.pages}</span>
          <button type="button" className="rs-btn sm ghost" disabled={!pg.has_next} onClick={() => go(d.filters, { page: pg.next_page })}>Older <i className="fas fa-chevron-right" aria-hidden="true" /></button>
        </div>)}
    </div>
  );
}

// ---- School info ------------------------------------------------------------
// Edit on the left, see the report-card letterhead update live on the right,
// with a checklist of what printouts are still missing.
const SCHOOL_KEYS = ['school_name', 'school_address', 'school_phone', 'school_email', 'school_motto', 'next_term_fees', 'next_term_begins'];

function clockNow(tz, fmt) {
  try {
    return new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: 'numeric', minute: '2-digit', hour12: fmt === '12h', weekday: 'short' }).format(new Date());
  } catch (e) { return ''; }
}

export function School({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const s = d.settings || {};
  const can = canWrite(d, 'school_info');
  const init = {
    ...Object.fromEntries(SCHOOL_KEYS.map((k) => [k, s[k] || ''])),
    timezone: d.current_tz || '', time_format: d.current_time_format || '24h',
  };
  const [f, setF] = useState(init);
  const [base, setBase] = useState(init);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const dirty = Object.keys(f).some((k) => f[k] !== base[k]);
  const submit = async (e) => {
    e && e.preventDefault();
    setSaving(true);
    const r = await save(d.submit_url, f, () => nav.refresh());
    setSaving(false);
    if (r && r.ok) setBase(f);
  };
  const pickLogo = async (file) => {
    if (!file) return;
    setBusy(true);
    const r = await postFile(d.logo_upload_url, file);
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Logo updated.'); nav.refresh(); }
    else notify('error', r.error || 'Could not upload that image.');
  };
  const removeLogo = async () => {
    if (!await confirm({ title: 'Remove the logo?', message: 'Printouts and the app header will show the app logo instead.', confirmText: 'Remove', tone: 'danger' })) return;
    setBusy(true);
    const r = await submitJson(d.logo_remove_url, {});
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Logo removed.'); nav.refresh(); }
    else notify('error', r.error || 'Could not remove the logo.');
  };
  const checks = [
    ['Logo', !!d.logo_url], ['School name', !!f.school_name.trim()], ['Address', !!f.school_address.trim()],
    ['Phone', !!f.school_phone.trim()], ['Email', !!f.school_email.trim()], ['Motto', !!f.school_motto.trim()],
    ['Next term date', !!f.next_term_begins.trim()],
  ];
  const done = checks.filter((c) => c[1]).length;
  const initials = (f.school_name || 'School').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  const nt = d.next_term;
  return (
    <div className="rs cm sx sc">
      <Head icon="fa-school" title="School info" sub="Your school’s identity — used in the app header and on every report card, result and printout." />
      <div className="sc-wrap">
        <form onSubmit={submit} className="sc-main">
          <fieldset disabled={!can} className="sc-fs">
            <section className="rs-card sc-sec">
              <h3><i className="fas fa-id-badge" aria-hidden="true" /> Identity</h3>
              <div className="sc-logo">
                <span className="sc-logo-box">{d.logo_url ? <img src={d.logo_url} alt="School logo" /> : <b>{initials}</b>}</span>
                <span className="sx-t"><b>{d.logo_url ? 'School logo' : 'No logo yet'}</b>
                  <small>PNG, JPG or WEBP. A square logo on a white or clear background prints best.</small>
                  {can && <span className="sc-logo-a">
                    <label className={'rs-btn sm' + (d.logo_url ? ' ghost' : ' primary')}>
                      <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-upload')} aria-hidden="true" /> {d.logo_url ? 'Replace' : 'Upload logo'}
                      <input type="file" accept="image/png,image/jpeg,image/webp" hidden disabled={busy}
                             onChange={(e) => { const x = e.target.files && e.target.files[0]; e.target.value = ''; pickLogo(x); }} /></label>
                    {d.logo_url && <button type="button" className="rs-btn sm ghost" onClick={removeLogo} disabled={busy}>Remove</button>}
                  </span>}</span>
              </div>
              <Field label="School name"><input value={f.school_name} onChange={set('school_name')} placeholder="e.g. Greenfield College" /></Field>
              <Field label="Motto" hint="Printed under the name on report cards"><input value={f.school_motto} onChange={set('school_motto')} placeholder="e.g. Knowledge and Character" /></Field>
            </section>

            <section className="rs-card sc-sec">
              <h3><i className="fas fa-address-book" aria-hidden="true" /> Contact</h3>
              <Field label="Address"><textarea rows={2} value={f.school_address} onChange={set('school_address')} placeholder="Street, town, state" /></Field>
              <div className="sc-2">
                <Field label="Phone"><input type="tel" inputMode="tel" value={f.school_phone} onChange={set('school_phone')} placeholder="0803 000 0000" /></Field>
                <Field label="Email"><input type="email" value={f.school_email} onChange={set('school_email')} placeholder="info@school.com" /></Field>
              </div>
            </section>

            <section className="rs-card sc-sec">
              <h3><i className="fas fa-file-lines" aria-hidden="true" /> On report cards</h3>
              <div className="sc-2">
                <Field label="Next term begins">
                  <input value={f.next_term_begins} onChange={set('next_term_begins')} placeholder="e.g. 27 April 2026" /></Field>
                <Field label="Next term fees"><input value={f.next_term_fees} onChange={set('next_term_fees')} placeholder="e.g. ₦62,000" /></Field>
              </div>
              {nt && can && f.next_term_begins !== nt.begins && (
                <button type="button" className="sc-hint" onClick={() => setF({ ...f, next_term_begins: nt.begins })}>
                  <i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Use <b>{nt.begins}</b> — when {nt.name} starts</button>)}
              <small className="cm-mute">Shown at the bottom of every report card this term. Leave blank to hide the line.</small>
            </section>

            <section className="rs-card sc-sec">
              <h3><i className="fas fa-clock" aria-hidden="true" /> Time &amp; clock</h3>
              <Field label="Time zone" hint="Used for every date, time, exam window and record in the app">
                <select value={f.timezone} onChange={set('timezone')}>
                  {(d.timezones || []).map((tz) => <option key={tz} value={tz}>{tz.replace(/_/g, ' ')}</option>)}</select></Field>
              <div className="cm-f"><span>Clock style</span>
                <Seg label="Clock style" value={f.time_format} onChange={(v) => setF({ ...f, time_format: v })} options={[
                  { value: '24h', label: '24-hour · 13:40' }, { value: '12h', label: '12-hour · 1:40 pm' }]} />
                <small>For timetables and every printout. Now at school: <b>{clockNow(f.timezone, f.time_format)}</b></small></div>
            </section>
          </fieldset>
          {can && dirty && (
            <Bar>
              <span className="sc-state"><i className="fas fa-circle" aria-hidden="true" /> Unsaved changes</span>
              <button type="button" className="rs-btn ghost" onClick={() => setF(base)}>Undo</button>
              <button type="button" className="rs-btn primary" disabled={!dirty || saving} onClick={submit}>
                <i className={'fas ' + (saving ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {saving ? 'Saving…' : 'Save'}</button>
            </Bar>)}
        </form>

        <aside className="sc-side">
          <section className="rs-card sc-prev">
            <span className="k">Report card preview</span>
            <div className="sc-paper">
              <div className="sc-lh">
                <span className="sc-lh-logo">{d.logo_url ? <img src={d.logo_url} alt="" /> : <b>{initials}</b>}</span>
                <div><h4>{f.school_name || 'School name'}</h4>
                  {f.school_motto && <em>“{f.school_motto}”</em>}
                  <p>{f.school_address || 'Address'}</p>
                  <p>{[f.school_phone, f.school_email].filter(Boolean).join(' · ') || 'Phone · Email'}</p></div>
              </div>
              <div className="sc-lines"><i /><i /><i style={{ width: '70%' }} /><i /><i style={{ width: '55%' }} /></div>
              {(f.next_term_begins || f.next_term_fees) && <div className="sc-foot">
                {f.next_term_begins && <span>Next term begins: <b>{f.next_term_begins}</b></span>}
                {f.next_term_fees && <span>Next term fees: <b>{f.next_term_fees}</b></span>}</div>}
            </div>
          </section>
          <section className="rs-card sc-check">
            <div className="sc-check-h"><b>{done === checks.length ? 'Printouts are complete' : `${checks.length - done} detail${checks.length - done === 1 ? '' : 's'} missing`}</b><span>{done}/{checks.length}</span></div>
            <div className="sx-share"><i style={{ width: Math.round(100 * done / checks.length) + '%' }} /></div>
            <ul>{checks.map(([k, ok]) => <li key={k} className={ok ? 'ok' : ''}><i className={'fas ' + (ok ? 'fa-circle-check' : 'fa-circle')} aria-hidden="true" />{k}</li>)}</ul>
          </section>
        </aside>
      </div>
    </div>
  );
}

// ---- Academic rules ---------------------------------------------------------
// School day planner (does the timetable fit the day?), pass/promotion marks on
// one scale, a live student-ID preview per branch, and the arms switch with a
// warning when arms are in use.
const toMin = (t) => { const m = /^(\d{1,2}):(\d{2})/.exec(t || ''); return m ? (+m[1]) * 60 + (+m[2]) : null; };
const fmtMin = (m, fmt) => {
  const h = Math.floor(m / 60) % 24, mm = String(m % 60).padStart(2, '0');
  if (fmt === '12h') return `${(h % 12) || 12}:${mm} ${h < 12 ? 'am' : 'pm'}`;
  return `${String(h).padStart(2, '0')}:${mm}`;
};
const dur = (m) => { m = Math.abs(m); const h = Math.floor(m / 60); return [h && `${h} h`, (m % 60) && `${m % 60} min`].filter(Boolean).join(' ') || '0 min'; };

function Stepper({ value, onChange, min, max, step = 1, unit, label, disabled }) {
  const v = Number(value) || 0;
  const clamp = (x) => String(Math.max(min, Math.min(max, x)));
  return (
    <div className="ac-step" role="group" aria-label={label}>
      <button type="button" onClick={() => onChange(clamp(v - step))} disabled={disabled || v <= min} aria-label={`Less ${label}`}><i className="fas fa-minus" aria-hidden="true" /></button>
      <input inputMode="numeric" value={value} disabled={disabled} aria-label={label}
             onChange={(e) => onChange(e.target.value.replace(/[^\d.]/g, ''))} onBlur={() => onChange(clamp(v))} />
      {unit && <em>{unit}</em>}
      <button type="button" onClick={() => onChange(clamp(v + step))} disabled={disabled || v >= max} aria-label={`More ${label}`}><i className="fas fa-plus" aria-hidden="true" /></button>
    </div>
  );
}

const shortCode = (name) => { const m = /^(\d{4})\/(\d{4})$/.exec((name || '').trim()); return m ? m[1].slice(2) + m[2].slice(2) : null; };

export function Academic({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const s = d.settings || {};
  const can = canWrite(d, 'academic_config');
  const str = (v, dflt) => (v === undefined || v === null || v === '' ? dflt : String(v));
  const on = (v, dflt) => (str(v, dflt) !== 'false' && str(v, dflt) !== '0' ? '1' : '0');
  const init = {
    school_day_start: str(s.school_day_start, '08:20'), school_day_end: str(s.school_day_end, '14:10'),
    period_duration: str(s.period_duration, '40'), break_duration: str(s.break_duration, '30'),
    periods_per_day: str(s.periods_per_day, '8'), pass_mark: str(s.pass_mark, '50'),
    promotion_threshold: str(s.promotion_threshold, '50'),
    student_id_prefix: str(s.student_id_prefix, 'STU'), student_id_digits: str(s.student_id_digits, '5'),
    student_id_include_session: on(s.student_id_include_session, 'false'),
    uses_class_arms: on(s.uses_class_arms, 'true'),
  };
  const [f, setF] = useState(init);
  const [base, setBase] = useState(init);
  const [saving, setSaving] = useState(false);
  const put = (k) => (v) => setF((o) => ({ ...o, [k]: v }));
  const dirty = Object.keys(f).some((k) => f[k] !== base[k]);
  const submit = async (e) => {
    e && e.preventDefault();
    setSaving(true);
    const r = await save(d.submit_url, f, () => nav.refresh());
    setSaving(false);
    if (r && r.ok) setBase(f);
  };
  const tf = s.time_format === '12h' ? '12h' : '24h';

  // Day plan: periods + one break, against the set school day.
  const start = toMin(f.school_day_start), end = toMin(f.school_day_end);
  const P = Math.max(0, parseInt(f.periods_per_day, 10) || 0), L = Math.max(0, parseInt(f.period_duration, 10) || 0), Br = Math.max(0, parseInt(f.break_duration, 10) || 0);
  const need = P * L + Br;
  const finish = start != null ? start + need : null;
  const spare = start != null && end != null ? end - finish : null;
  const span = start != null && end != null && end > start ? Math.max(end - start, need) : need || 1;
  const half = Math.ceil(P / 2);
  const segs = [];
  for (let i = 0; i < P; i++) {
    segs.push({ k: 'p' + i, w: L, label: String(i + 1) });
    if (i === half - 1 && Br) segs.push({ k: 'br', w: Br, label: 'Break', br: true });
  }
  const dayBad = start == null || end == null || end <= start;

  // Marks.
  const pass = Number(f.pass_mark) || 0, promo = Number(f.promotion_threshold) || 0;

  // Student IDs.
  const code = f.student_id_include_session === '1' ? shortCode(d.active_session_name) : null;
  const digits = Math.max(3, Math.min(parseInt(f.student_id_digits, 10) || 5, 12));
  const idFor = (prefix) => `${prefix}${code || ''}${'1'.padStart(digits, '0')}`;
  const prefix = (f.student_id_prefix || 'STU').toUpperCase();
  const prefixBad = !!f.student_id_prefix && !/^[A-Z0-9]{1,10}$/.test(f.student_id_prefix);
  const branches = d.branches || [];
  const armsOff = f.uses_class_arms === '0';

  return (
    <div className="rs cm sx sc ac">
      <Head icon="fa-sliders" title="Academic rules" sub="The school day, pass marks, student ID format and how classes are split." />
      <form onSubmit={submit} className="ac-grid">
        <fieldset disabled={!can} className="sc-fs ac-col">
          <section className="rs-card sc-sec">
            <h3><i className="fas fa-sun" aria-hidden="true" /> School day</h3>
            <div className="sc-2">
              <Field label="Starts"><input type="time" value={f.school_day_start} onChange={(e) => put('school_day_start')(e.target.value)} /></Field>
              <Field label="Ends"><input type="time" value={f.school_day_end} onChange={(e) => put('school_day_end')(e.target.value)} /></Field>
            </div>
            <div className="ac-3">
              <div className="cm-f"><span>Periods a day</span><Stepper label="periods a day" value={f.periods_per_day} onChange={put('periods_per_day')} min={4} max={12} /></div>
              <div className="cm-f"><span>Each period</span><Stepper label="period length" value={f.period_duration} onChange={put('period_duration')} min={20} max={90} step={5} unit="min" /></div>
              <div className="cm-f"><span>Break</span><Stepper label="break length" value={f.break_duration} onChange={put('break_duration')} min={5} max={60} step={5} unit="min" /></div>
            </div>
            <div className="ac-day" aria-hidden="true">
              {segs.map((g) => <span key={g.k} className={g.br ? 'br' : ''} style={{ flexGrow: g.w }}>{g.label}</span>)}
              {spare > 0 && <span className="free" style={{ flexGrow: spare }} />}
            </div>
            <div className="ac-day-ax"><span>{start != null ? fmtMin(start, tf) : '—'}</span><span>{end != null ? fmtMin(end, tf) : '—'}</span></div>
            {dayBad ? <div className="cm-attn-i bad"><i className="fas fa-circle-xmark" aria-hidden="true" /><span>The day must end after it starts.</span></div>
              : spare < 0 ? <div className="cm-attn-i bad"><i className="fas fa-triangle-exclamation" aria-hidden="true" /><span><b>Doesn’t fit.</b> {P} periods and the break finish at {fmtMin(finish, tf)} — {dur(spare)} after school ends. Shorten periods, drop one, or end later.</span></div>
              : <div className="cm-attn-i good"><i className="fas fa-circle-check" aria-hidden="true" /><span><b>Fits.</b> Lessons end at {fmtMin(finish, tf)}{spare > 0 ? `, ${dur(spare)} before the day ends` : ', exactly at the end of the day'}.</span></div>}
            {d.urls && d.urls.slots && <small className="cm-mute">Timetable periods are built from these numbers{d.slots ? ` — ${plural(d.slots, 'period')} set up now` : ''}. <A to={d.urls.slots}>Open timetable periods</A></small>}
          </section>

          <section className="rs-card sc-sec">
            <h3><i className="fas fa-graduation-cap" aria-hidden="true" /> Pass &amp; promotion</h3>
            <div className="ac-scale" aria-hidden="true">
              <i className="fail" style={{ width: Math.min(pass, promo) + '%' }} />
              <b className="pm" style={{ left: pass + '%' }}><em>Pass {pass}%</em></b>
              <b className="pr" style={{ left: promo + '%' }}><em>Promote {promo}%</em></b>
            </div>
            <div className="sc-2">
              <div className="cm-f"><span>Pass mark</span><Stepper label="pass mark" value={f.pass_mark} onChange={put('pass_mark')} min={30} max={70} unit="%" />
                <small>A subject score below this shows as a fail on report cards.</small></div>
              <div className="cm-f"><span>Promotion average</span><Stepper label="promotion average" value={f.promotion_threshold} onChange={put('promotion_threshold')} min={30} max={70} unit="%" />
                <small>Students with a yearly average at or above this are recommended for promotion.</small></div>
            </div>
            {promo < pass && <div className="cm-attn-i mid"><i className="fas fa-circle-info" aria-hidden="true" /><span>Promotion is lower than the pass mark, so a student can be promoted with a failing average.</span></div>}
            {d.urls && d.urls.promotion && <small className="cm-mute">See who this affects in <A to={d.urls.promotion} native>Promotion</A>.</small>}
          </section>
        </fieldset>

        <fieldset disabled={!can} className="sc-fs ac-col">
          <section className="rs-card sc-sec">
            <h3><i className="fas fa-id-card" aria-hidden="true" /> Student ID format</h3>
            <div className="ac-id">
              <span className="k">Next new ID</span>
              <code>{prefix}<em>{code || ''}</em>{'1'.padStart(digits, '0')}</code>
              <small>{d.latest_id ? <>Most recent ID: <b>{d.latest_id}</b> · </> : null}Existing IDs never change.</small>
            </div>
            <div className="sc-2">
              <Field label="Prefix" hint={prefixBad ? 'Letters and digits only, up to 10' : 'Blank uses STU'}>
                <input value={f.student_id_prefix} maxLength={10} aria-invalid={prefixBad || undefined}
                       onChange={(e) => put('student_id_prefix')(e.target.value.toUpperCase().replace(/\s/g, ''))} placeholder="STU" /></Field>
              <div className="cm-f"><span>Number length</span><Stepper label="number length" value={f.student_id_digits} onChange={put('student_id_digits')} min={3} max={12} unit="digits" /></div>
            </div>
            <Toggle title="Add the session to each ID" on={f.student_id_include_session === '1'} onChange={(v) => put('student_id_include_session')(v ? '1' : '0')}
                    sub={d.active_session_name && shortCode(d.active_session_name)
                      ? `${d.active_session_name} adds ${shortCode(d.active_session_name)} — numbering restarts from 1 each session`
                      : 'No active session yet — this takes effect once one is set'} />
            {branches.length > 0 && (
              <div className="ac-br">
                <span className="k">By branch</span>
                {branches.map((b) => (
                  <div key={b.name}><span>{b.name}</span><code>{idFor(b.code || prefix)}</code>
                    {b.code ? <small>own code</small> : <small>school prefix</small>}</div>))}
                {d.urls && d.urls.branches && <small className="cm-mute">A branch’s own code replaces the prefix. <A to={d.urls.branches}>Edit branch codes</A></small>}
              </div>)}
          </section>

          <section className="rs-card sc-sec">
            <h3><i className="fas fa-code-branch" aria-hidden="true" /> Class structure</h3>
            <Toggle title="Classes are split into arms" sub="e.g. JSS 1A, JSS 1B. Turn off if each class is a single group." on={!armsOff} onChange={(v) => put('uses_class_arms')(v ? '1' : '0')} />
            {armsOff && d.arms_in_use > 0 && base.uses_class_arms === '1' && (
              <div className="cm-attn-i mid"><i className="fas fa-triangle-exclamation" aria-hidden="true" />
                <span>{plural(d.arms_in_use, 'arm is', 'arms are')} in use this term. Existing classes keep their arms; this only hides arms when setting up new classes.</span></div>)}
            {d.urls && d.urls.arms && !armsOff && <small className="cm-mute"><A to={d.urls.arms}>Manage arms</A></small>}
          </section>
        </fieldset>

        {can && dirty && (
          <Bar>
            <span className="sc-state"><i className="fas fa-circle" aria-hidden="true" /> Unsaved changes</span>
            <button type="button" className="rs-btn ghost" onClick={() => setF(base)}>Undo</button>
            <button type="button" className="rs-btn primary" disabled={saving || prefixBad} onClick={submit}>
              <i className={'fas ' + (saving ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {saving ? 'Saving…' : 'Save'}</button>
          </Bar>)}
      </form>
    </div>
  );
}

// ---- Grade scale ------------------------------------------------------------
// Bands drawn on a 0–100 bar; gaps, overlaps and decimal scores that fall
// between bands are called out (with a one-tap fix); each band shows how many
// of this term's results it would hold, live as you edit.
const PRESETS = {
  waec: { label: 'WAEC style (A1–F9)', rows: [['A1', 75, 100, 'Excellent'], ['B2', 70, 74, 'Very good'], ['B3', 65, 69, 'Good'], ['C4', 60, 64, 'Credit'], ['C5', 55, 59, 'Credit'], ['C6', 50, 54, 'Credit'], ['D7', 45, 49, 'Pass'], ['E8', 40, 44, 'Pass'], ['F9', 0, 39, 'Fail']] },
  classic: { label: 'Classic (A–F)', rows: [['A', 70, 100, 'Excellent'], ['B', 60, 69, 'Very good'], ['C', 50, 59, 'Good'], ['D', 45, 49, 'Fair'], ['E', 40, 44, 'Poor'], ['F', 0, 39, 'Fail']] },
  primary: { label: 'Primary (A–F, wider bands)', rows: [['A', 80, 100, 'Excellent'], ['B', 65, 79, 'Very good'], ['C', 50, 64, 'Good'], ['D', 40, 49, 'Fair'], ['F', 0, 39, 'Needs improvement']] },
};
// Same rule as GradeScale.band_for: exact band first, else a decimal just past
// a band's top (69.5 after 60–69) belongs to that band.
function bandFor(v, rows) {
  const ok = rows.filter((r) => r.min_score !== '' && r.max_score !== '');
  const exact = ok.find((r) => v >= +r.min_score && v <= +r.max_score);
  if (exact) return exact;
  let best = null;
  ok.forEach((r) => { if (v >= +r.min_score && v < +r.max_score + 1 && (!best || +r.min_score > +best.min_score)) best = r; });
  return best;
}
const bandColor = (i, n) => `hsl(${Math.round(150 - (150 * i) / Math.max(1, n - 1))} 62% 42%)`;

function gradeIssues(rows, spread) {
  const ok = rows.filter((r) => r.min_score !== '' && r.max_score !== '');
  const iss = [];
  rows.forEach((r) => {
    if (!String(r.grade).trim()) iss.push({ bad: true, t: 'A band has no grade letter.' });
    if (r.min_score !== '' && r.max_score !== '' && +r.min_score > +r.max_score) iss.push({ bad: true, t: `${r.grade || 'A band'}: “from” is higher than “to”.` });
  });
  const seen = {};
  rows.forEach((r) => { const g = String(r.grade).trim().toUpperCase(); if (g) { if (seen[g]) iss.push({ bad: true, t: `Grade ${g} is listed twice.` }); seen[g] = 1; } });
  const sorted = [...ok].sort((a, b) => +a.min_score - +b.min_score);
  if (sorted.length && +sorted[0].min_score > 0) iss.push({ t: `Scores from 0 to ${+sorted[0].min_score - 1} have no grade.`, fix: true });
  if (sorted.length && +sorted[sorted.length - 1].max_score < 100) iss.push({ t: `Scores above ${sorted[sorted.length - 1].max_score} have no grade.`, fix: true });
  for (let i = 1; i < sorted.length; i++) {
    const lo = sorted[i - 1], hi = sorted[i];
    if (+hi.min_score > +lo.max_score + 1) iss.push({ t: `Gap: ${+lo.max_score + 1}–${+hi.min_score - 1} has no grade.`, fix: true });
    if (+hi.min_score <= +lo.max_score) iss.push({ t: `${lo.grade} and ${hi.grade} overlap at ${hi.min_score}–${Math.min(+lo.max_score, +hi.max_score)}.`, fix: true });
  }
  const lost = spread.filter(([v]) => !bandFor(v, rows));
  const n = lost.reduce((k, [, c]) => k + c, 0);
  if (n) iss.push({ t: `${plural(n, 'result')} this term (e.g. ${lost[0][0]}) would get no grade with these bands.`, fix: true });
  return iss;
}

export function Grades({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const can = canWrite(d, 'grades_edit');
  const phone = usePhone();
  const init = (d.grades || []).map((g) => ({ grade: g.grade, min_score: String(g.min_score), max_score: String(g.max_score), remark: g.remark || '' }));
  const [rows, setRows] = useState(init);
  const [base, setBase] = useState(init);
  const [saving, setSaving] = useState(false);
  const [preset, setPreset] = useState(false);
  const spread = d.spread || [];
  const total = spread.reduce((n, [, c]) => n + c, 0);
  const dirty = JSON.stringify(rows) !== JSON.stringify(base);
  const issues = gradeIssues(rows, spread);
  const blocking = issues.some((x) => x.bad);
  const set = (i, k) => (e) => {
    const v = k === 'grade' ? e.target.value.toUpperCase().slice(0, 5) : k === 'remark' ? e.target.value.slice(0, 50) : e.target.value.replace(/\D/g, '').slice(0, 3);
    setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  };
  const count = (r) => spread.filter(([v]) => bandFor(v, rows) === r).reduce((n, [, c]) => n + c, 0);
  const add = () => {
    const low = rows.reduce((m, r) => Math.min(m, r.min_score === '' ? 100 : +r.min_score), 100);
    setRows([...rows, { grade: '', min_score: '0', max_score: String(Math.max(0, low - 1)), remark: '' }]);
  };
  // Sort high→low, top band to 100, bottom to 0, each band ends just below
  // where the one above starts.
  const closeGaps = () => {
    const s = [...rows].filter((r) => r.min_score !== '').sort((a, b) => +b.min_score - +a.min_score);
    setRows(s.map((r, i) => ({ ...r, max_score: String(i === 0 ? 100 : +s[i - 1].min_score - 1), min_score: i === s.length - 1 ? '0' : r.min_score })));
  };
  const usePreset = (k) => { setRows(PRESETS[k].rows.map(([g, a, b, rm]) => ({ grade: g, min_score: String(a), max_score: String(b), remark: rm }))); setPreset(false); };
  const submit = async () => {
    const s = [...rows].sort((a, b) => (+b.min_score || 0) - (+a.min_score || 0));
    setSaving(true);
    const r = await save(d.save_url, {
      'grade[]': s.map((x) => x.grade), 'min_score[]': s.map((x) => x.min_score),
      'max_score[]': s.map((x) => x.max_score), 'remark[]': s.map((x) => x.remark),
    }, () => nav.refresh());
    setSaving(false);
    if (r && r.ok) { setRows(s); setBase(s); }
  };
  const view = [...rows.map((r, i) => ({ r, i }))].sort((a, b) => (+b.r.min_score || 0) - (+a.r.min_score || 0));
  const colorOf = Object.fromEntries(view.map((x, k) => [x.i, bandColor(k, view.length)]));
  const pm = Number(d.pass_mark) || 50;
  const pmGrade = rows.find((r) => r.min_score !== '' && pm >= +r.min_score && pm <= +r.max_score);
  return (
    <div className="rs cm sx gr">
      <Head icon="fa-star" title="Grade scale" sub="How a subject total becomes a grade and remark on report cards and broadsheets.">
        {can && <button type="button" className="rs-btn ghost" onClick={() => setPreset(true)}><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Start from a preset</button>}
      </Head>

      <section className="rs-card gr-viz">
        <div className="gr-bar">
          {view.filter((x) => x.r.min_score !== '' && x.r.max_score !== '' && +x.r.max_score >= +x.r.min_score).map(({ r, i }) => (
            <span key={i} style={{ left: `${+r.min_score}%`, width: `${Math.max(1, Math.min(100, +r.max_score) - +r.min_score + 1)}%`, background: colorOf[i] }} title={`${r.grade} ${r.min_score}–${r.max_score}`}>{r.grade}</span>))}
          <b className="gr-pm" style={{ left: pm + '%' }}><em>Pass {pm}</em></b>
        </div>
        <div className="gr-ax"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div>
        {issues.length ? (
          <div className="gr-iss">{issues.map((x, k) => (
            <div key={k} className={'cm-attn-i ' + (x.bad ? 'bad' : 'mid')}><i className={'fas ' + (x.bad ? 'fa-circle-xmark' : 'fa-triangle-exclamation')} aria-hidden="true" /><span>{x.t}</span></div>))}
            {can && issues.some((x) => x.fix) && <button type="button" className="rs-btn sm primary" onClick={closeGaps}><i className="fas fa-link" aria-hidden="true" /> Join the bands up</button>}
          </div>
        ) : <div className="cm-attn-i good"><i className="fas fa-circle-check" aria-hidden="true" /><span>Every score from 0 to 100 gets exactly one grade.{pmGrade ? ` The pass mark (${pm}) is a ${pmGrade.grade}.` : ''}</span></div>}
      </section>

      <section className="rs-card gr-list">
        <div className="gr-row gr-hd"><span>Grade</span><span>From</span><span>To</span><span>Remark</span><span>{d.spread_term ? `Results · ${d.spread_term}` : 'Results'}</span><span /></div>
        {view.map(({ r, i }) => {
          const n = count(r);
          return (
            <div key={i} className="gr-row">
              <span className="gr-g">{phone && <small className="gr-gl">Grade</small>}<i style={{ background: colorOf[i] }} /><input value={r.grade} onChange={set(i, 'grade')} placeholder="A1" aria-label="Grade" disabled={!can} /></span>
              <span>{phone && <small>From</small>}<input inputMode="numeric" value={r.min_score} onChange={set(i, 'min_score')} aria-label={`${r.grade} from`} disabled={!can} /></span>
              <span>{phone && <small>To</small>}<input inputMode="numeric" value={r.max_score} onChange={set(i, 'max_score')} aria-label={`${r.grade} to`} disabled={!can} /></span>
              <span className="gr-rm"><input value={r.remark} onChange={set(i, 'remark')} placeholder="Remark" aria-label={`${r.grade} remark`} disabled={!can} /></span>
              <span className="gr-n">{total ? <><b>{n}</b><em><i style={{ width: `${Math.round(100 * n / total)}%`, background: colorOf[i] }} /></em><small>{Math.round(100 * n / total)}%</small></> : <small className="cm-mute">—</small>}</span>
              <span>{can && <button type="button" className="gr-x" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label={`Remove ${r.grade || 'band'}`}><i className="fas fa-xmark" aria-hidden="true" /></button>}</span>
            </div>);
        })}
        {!rows.length && <p className="cm-mute sx-empty">No grades yet — start from a preset or add a band.</p>}
        {can && <button type="button" className="gr-add" onClick={add}><i className="fas fa-plus" aria-hidden="true" /> Add a band</button>}
      </section>
      {!total && <p className="cm-mute gr-note"><i className="fas fa-circle-info" aria-hidden="true" /> Once scores are entered, each band shows how many results it holds.</p>}

      {can && dirty && (
        <Bar>
          <span className="sc-state"><i className="fas fa-circle" aria-hidden="true" /> Unsaved changes</span>
          <button type="button" className="rs-btn ghost" onClick={() => setRows(base)}>Undo</button>
          <button type="button" className="rs-btn primary" disabled={saving || blocking} onClick={submit}>
            <i className={'fas ' + (saving ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {saving ? 'Saving…' : 'Save'}</button>
        </Bar>)}

      {preset && (
        <Sheet title="Start from a preset" onClose={() => setPreset(false)}>
          <div className="gr-presets">
            {Object.entries(PRESETS).map(([k, p]) => (
              <button key={k} type="button" className="rs-card gr-pre" onClick={() => usePreset(k)}>
                <b>{p.label}</b>
                <span className="gr-pre-bar">{p.rows.map(([g, a, b], j) => <i key={g} style={{ width: `${b - a + 1}%`, background: bandColor(p.rows.length - 1 - j, p.rows.length) }} />).reverse()}</span>
                <small>{p.rows.map(([g, a]) => `${g} ${a}+`).join(' · ')}</small>
              </button>))}
            <p className="cm-mute">This replaces the bands on screen. Nothing is saved until you tap Save.</p>
          </div>
        </Sheet>)}
    </div>
  );
}

// ---- Behaviour traits -------------------------------------------------------
// Traits on report cards vs hidden, in print order, each with how teachers
// rated it this term; a live report-card preview; suggested traits to add.
export function Traits({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const can = canWrite(d, 'traits_edit');
  // Nothing saved yet → report cards use the built-in list, so start from it.
  const builtIn = !(d.traits || []).length;
  const init = builtIn ? (d.defaults || []).map((t) => ({ key: t.key, label: t.label, is_active: true }))
    : d.traits.map((t) => ({ key: t.key, label: t.label, is_active: !!t.is_active }));
  const [rows, setRows] = useState(init);
  const [base, setBase] = useState(init);
  const [saving, setSaving] = useState(false);
  const [text, setText] = useState('');
  const usage = d.usage || {};
  const dirty = JSON.stringify(rows) !== JSON.stringify(base);
  const shown = rows.filter((r) => r.is_active), hidden = rows.filter((r) => !r.is_active);
  const lc = (x) => x.trim().toLowerCase();
  const dupe = (label, self) => rows.some((r) => r !== self && lc(r.label) === lc(label));
  const blank = rows.some((r) => !r.label.trim());
  const dupes = rows.some((r) => r.label.trim() && dupe(r.label, r));
  const upd = (r, patch) => setRows(rows.map((x) => (x === r ? { ...x, ...patch } : x)));
  const move = (r, dir) => {
    const list = [...shown]; const i = list.indexOf(r); const j = i + dir;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    setRows([...list, ...hidden]);
  };
  const add = (label, key = '') => {
    const l = label.trim();
    if (!l || dupe(l)) return;
    setRows([...shown, { key, label: l, is_active: true }, ...hidden]);
    setText('');
  };
  const suggestions = (d.defaults || []).filter((x) => !rows.some((r) => r.key === x.key || lc(r.label) === lc(x.label)));
  const submit = async () => {
    const order = [...shown, ...hidden];
    setSaving(true);
    const r = await save(d.save_url, {
      'key[]': order.map((x) => x.key || ''), 'label[]': order.map((x) => x.label.trim()),
      'active[]': order.map((x, i) => (x.is_active ? String(i) : null)).filter((x) => x !== null),
    }, () => nav.refresh());
    setSaving(false);
    if (r && r.ok) { setRows(order); setBase(order); }
  };
  const Row = ({ r, i, list }) => {
    const u = r.key && usage[r.key];
    return (
      <div className={'tr-row' + (r.is_active ? '' : ' off')}>
        {r.is_active && can ? (
          <span className="tr-mv">
            <button type="button" onClick={() => move(r, -1)} disabled={i === 0} aria-label={`Move ${r.label} up`}><i className="fas fa-chevron-up" aria-hidden="true" /></button>
            <button type="button" onClick={() => move(r, 1)} disabled={i === list.length - 1} aria-label={`Move ${r.label} down`}><i className="fas fa-chevron-down" aria-hidden="true" /></button>
          </span>) : <span className="tr-mv" />}
        <span className="tr-l">
          <input value={r.label} maxLength={80} disabled={!can} aria-label="Trait name" aria-invalid={(!r.label.trim() || dupe(r.label, r)) || undefined}
                 onChange={(e) => upd(r, { label: e.target.value })} />
          <small>{u ? <>Rated for {plural(u.n, 'student')} · average <b>{u.avg}</b> / 5</> : r.key ? 'Not rated this term' : 'New'}{!r.label.trim() ? ' · needs a name' : dupe(r.label, r) ? ' · same name as another trait' : ''}</small>
        </span>
        {u && <span className="tr-avg" title={`Average ${u.avg} of 5`}>{[1, 2, 3, 4, 5].map((k) => <i key={k} className={k <= Math.round(u.avg) ? 'on' : ''} />)}</span>}
        <Switch on={r.is_active} onChange={(v) => setRows(v ? [...shown, { ...r, is_active: true }, ...hidden.filter((x) => x !== r)] : [...shown.filter((x) => x !== r), { ...r, is_active: false }, ...hidden])}
                disabled={!can} label={r.is_active ? `Hide ${r.label}` : `Show ${r.label}`} />
      </div>);
  };
  return (
    <div className="rs cm sx tr">
      <Head icon="fa-star-half-stroke" title="Behaviour traits" sub="The affective domain rated 1–5 on every report card. Hiding a trait keeps its past ratings." >
        {d.rate_url && <A to={d.rate_url} native className="rs-btn ghost"><i className="fas fa-pen" aria-hidden="true" /> Rate students</A>}
      </Head>
      <Tiles items={[
        { label: 'On report cards', value: shown.length, tone: shown.length > 14 ? 'warn' : null, sub: shown.length > 14 ? 'Long lists can push the card to a 2nd page' : null },
        { label: 'Hidden', value: hidden.length },
        { label: d.usage_term ? `Students rated · ${d.usage_term}` : 'Students rated', value: d.rated || 0 },
      ]} />
      <div className="tr-wrap">
        <div className="tr-main">
          <section className="rs-card tr-list">
            <div className="tr-h"><h3><i className="fas fa-eye" aria-hidden="true" /> On report cards</h3><span className="cm-mute">in print order</span></div>
            {shown.map((r, i) => <React.Fragment key={r.key || 'n' + i}>{Row({ r, i, list: shown })}</React.Fragment>)}
            {builtIn && !dirty && <p className="cm-mute tr-note"><i className="fas fa-circle-info" aria-hidden="true" /> These are the app’s standard traits. Change any of them and save to make the list your own.</p>}
            {!shown.length && <p className="cm-mute sx-empty">Nothing selected — report cards will use the app’s standard traits.</p>}
            {can && (
              <form className="tr-add" onSubmit={(e) => { e.preventDefault(); add(text); }}>
                <input value={text} onChange={(e) => setText(e.target.value)} maxLength={80} placeholder="Add a trait, e.g. Leadership" aria-label="New trait" />
                <button type="submit" className="rs-btn sm primary" disabled={!text.trim() || dupe(text)}><i className="fas fa-plus" aria-hidden="true" /> Add</button>
              </form>)}
            {can && suggestions.length > 0 && (
              <div className="tr-sug"><span className="cm-mute">Suggested:</span>
                {suggestions.map((x) => <button key={x.key} type="button" onClick={() => add(x.label, x.key)}><i className="fas fa-plus" aria-hidden="true" /> {x.label}</button>)}</div>)}
          </section>
          {hidden.length > 0 && (
            <section className="rs-card tr-list">
              <div className="tr-h"><h3><i className="fas fa-eye-slash" aria-hidden="true" /> Hidden</h3><span className="cm-mute">not printed · ratings kept</span></div>
              {hidden.map((r, i) => <React.Fragment key={r.key || 'h' + i}>{Row({ r, i, list: hidden })}</React.Fragment>)}
            </section>)}
        </div>
        <aside className="sc-side">
          <section className="rs-card sc-prev">
            <span className="k">Report card preview</span>
            <div className="sc-paper tr-paper">
              <table>
                <thead><tr><th>Affective domain</th>{(d.rating_labels || []).map(([k]) => <th key={k}>{k}</th>)}</tr></thead>
                <tbody>{shown.slice(0, 16).map((r, i) => (
                  <tr key={i}><td>{r.label || '—'}</td>{(d.rating_labels || []).map(([k]) => <td key={k}>{k === [4, 5, 3, 4, 5, 4][i % 6] ? '✓' : ''}</td>)}</tr>))}
                  {shown.length > 16 && <tr><td colSpan={6}>+ {shown.length - 16} more…</td></tr>}</tbody>
              </table>
              <p className="tr-key">{(d.rating_labels || []).map(([k, v]) => `${k} ${v}`).join(' · ')}</p>
            </div>
          </section>
        </aside>
      </div>
      {can && dirty && (
        <Bar>
          <span className="sc-state"><i className="fas fa-circle" aria-hidden="true" /> Unsaved changes</span>
          <button type="button" className="rs-btn ghost" onClick={() => setRows(base)}>Undo</button>
          <button type="button" className="rs-btn primary" disabled={saving || blank || dupes} onClick={submit}>
            <i className={'fas ' + (saving ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {saving ? 'Saving…' : 'Save'}</button>
        </Bar>)}
    </div>
  );
}
