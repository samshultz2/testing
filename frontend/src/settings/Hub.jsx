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
import { A, Field, Toggle, Pill, SearchBox, plural } from '../components/appkit';

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
