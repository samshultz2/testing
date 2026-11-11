import React, { useState } from 'react';
import { submitJson, useSave } from '../lib/forms';
import { useDraft } from '../lib/draft';
import { useSection, NavCtx, useNav } from '../lib/section';
import { confirm, Banner, SectionShell, Empty, Modal } from '../components/ui';
import { Head, Tiles, Chips, Menu, Blank, usePhone, initials } from '../subjects/results';
import { SecNav, Pill, SearchBox, plural } from '../components/appkit';
import { UserForm, UserView, Groups } from './UserScreens';

const A = ({ to, className, children, title }) => {
  const nav = useNav();
  return <a href={to} title={title} className={className}
    onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};

// Password policy comes from the server (single source of truth:
// utils.security.password_rules, bootstrapped into the form as d.password_rules)
// so this form can never drift from what add/edit will actually accept.
const ruleOk = (rule, v) =>
  rule.min_length != null ? (v || '').length >= rule.min_length : new RegExp(rule.regex).test(v || '');
const pwStrong = (rules, v) => (rules || []).every((r) => ruleOk(r, v));
const PwReqs = ({ rules, value }) => (
  <ul className="pw-reqs" style={{ listStyle: 'none', margin: '6px 0 2px', padding: 0, display: 'grid', gap: 3 }}>
    {(rules || []).map((rule) => {
      const ok = ruleOk(rule, value || '');
      return (
        <li key={rule.id} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 8, color: ok ? '#14875a' : 'var(--text-muted,#7b8598)' }}>
          <i aria-hidden="true" className={'fas ' + (ok ? 'fa-circle-check' : 'fa-circle')} style={{ fontSize: ok ? 11 : 7 }} />
          {rule.label}
        </li>
      );
    })}
  </ul>
);

// ---- Index: people directory --------------------------------------------------
const seen = (n) => (n == null ? 'Never signed in' : n === 0 ? 'Today' : n === 1 ? 'Yesterday'
  : n < 7 ? `${n} days ago` : n < 31 ? `${Math.floor(n / 7)} wk ago` : n < 365 ? `${Math.floor(n / 30)} mo ago` : 'Over a year ago');
const ROLE_TONE = { danger: 'bad', warning: 'mid', info: 'info', secondary: '' };
const KINDS = [['', 'Everyone'], ['admin', 'Admins'], ['teacher', 'Teachers'], ['staff', 'Other staff'], ['inactive', 'Inactive']];
const kindOf = (u) => (!u.is_active ? 'inactive' : u.is_admin ? 'admin' : u.is_teacher ? 'teacher' : 'staff');

function Index({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const phone = usePhone();
  const [q, setQ] = useState('');
  const [kind, setKind] = useState('');
  const [flag, setFlag] = useState('');
  const users = d.users;
  const active = users.filter((u) => u.is_active);
  const never = active.filter((u) => u.last_days == null && (u.created_days == null || u.created_days >= 3));
  const dormant = active.filter((u) => u.last_days != null && u.last_days >= 90 && !u.is_self);
  const noMfa = active.filter((u) => u.is_admin && !u.mfa);
  const flags = { never: never.map((u) => u.id), dormant: dormant.map((u) => u.id), nomfa: noMfa.map((u) => u.id) };
  const counts = {};
  users.forEach((u) => { const k = kindOf(u); counts[k] = (counts[k] || 0) + 1; if (u.is_active && k !== 'inactive') counts[''] = (counts[''] || 0) + 1; });
  counts[''] = users.length;
  const t = q.trim().toLowerCase();
  const rows = users.filter((u) => (!kind || kindOf(u) === kind) && (!flag || flags[flag].includes(u.id))
    && (!t || [u.full_name, u.username, u.email, u.phone, u.display_role, u.group, u.branch].join(' ').toLowerCase().includes(t)));
  const toggle = async (u) => {
    if (u.is_active && !await confirm({ title: `Deactivate ${u.full_name || u.username}?`, confirmText: 'Deactivate',
      message: 'They won’t be able to sign in. Their records and history stay; you can reactivate them any time.' })) return;
    save(u.toggle_url, {}, () => nav.refresh());
  };
  const del = async (u) => {
    if (await confirm({ title: `Delete ${u.full_name || u.username}?`, tone: 'danger', confirmText: 'Delete',
      message: `This removes the login account "${u.username}" and can’t be undone. To keep it but block sign-in, use Deactivate instead.` })) {
      save(u.delete_url, {}, () => nav.refresh());
    }
  };
  const menu = (u) => <Menu label={`Actions for ${u.username}`} items={[
    { icon: 'fa-id-badge', label: 'Open profile', onClick: () => nav.go(u.view_url) },
    { icon: 'fa-pen', label: 'Edit access', onClick: () => nav.go(u.edit_url) },
    !u.is_self && { icon: u.is_active ? 'fa-ban' : 'fa-circle-check', label: u.is_active ? 'Deactivate' : 'Reactivate', onClick: () => toggle(u) },
    u.can_delete && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => del(u) },
  ]} />;
  const alerts = [
    noMfa.length > 0 && { k: 'nomfa', tone: 'bad', ic: 'fa-shield-halved', t: `${plural(noMfa.length, 'admin')} without two-step sign-in — admins can see everything, so their accounts matter most` },
    never.length > 0 && { k: 'never', tone: 'mid', ic: 'fa-user-clock', t: `${plural(never.length, 'account')} never signed in — check they got their login details` },
    dormant.length > 0 && { k: 'dormant', tone: 'info', ic: 'fa-bed', t: `${plural(dormant.length, 'account')} unused for 3+ months — deactivate staff who have left` },
  ].filter(Boolean);
  return (
    <div className="rs cm us">
      <SecNav label="Users" active="index" items={[
        ['index', 'fa-users', 'Users', location.pathname], ['matrix', 'fa-table-cells', 'Permission matrix', d.matrix_url], ['groups', 'fa-layer-group', 'Groups', d.groups_url]]} />
      <Head icon="fa-users-gear" title="Users" sub={`${plural(active.length, 'active account')} · who can sign in and what they can do`}>
        <A to={d.add_url} className="rs-btn primary"><i className="fas fa-user-plus" aria-hidden="true" /><span className="rs-hide-sm"> Add user</span></A>
      </Head>
      <Tiles items={[
        { label: 'Active', value: active.length, sub: `${users.length - active.length} inactive` },
        { label: 'Admins', value: counts.admin || 0, sub: `${noMfa.length ? noMfa.length + ' without 2FA' : 'all protected'}`, tone: noMfa.length ? 'bad' : 'good' },
        { label: 'Teachers', value: counts.teacher || 0 },
        { label: 'Signed in this week', value: active.filter((u) => u.last_days != null && u.last_days < 7).length, sub: `of ${active.length}` },
      ]} />
      {alerts.length > 0 && (
        <section className="rs-card rp-attn"><span className="k">Worth checking</span>
          <div className="tm-alerts">{alerts.map((a) => (
            <button key={a.k} type="button" className={'cm-attn-i ' + a.tone + (flag === a.k ? ' on' : '')} onClick={() => setFlag(flag === a.k ? '' : a.k)}>
              <i className={'fas ' + a.ic} aria-hidden="true" /><span>{a.t}</span><small>{flag === a.k ? 'Showing' : 'Show'}</small></button>))}</div>
        </section>)}
      <div className="us-tools">
        <SearchBox value={q} onChange={setQ} placeholder="Search name, username, email, role…" />
        <Chips label="Who" value={kind} onChange={(v) => { setKind(v); setFlag(''); }}
               items={KINDS.map(([k, l]) => ({ value: k, label: l, sub: counts[k] || 0 }))} />
      </div>
      {flag && <div className="us-flag"><span>Showing: {alerts.find((a) => a.k === flag)?.t.split(' — ')[0]}</span><button type="button" className="cm-link" onClick={() => setFlag('')}>Show everyone</button></div>}
      {!rows.length ? <Blank icon="fa-users" title={users.length ? 'No one matches' : 'No users yet'} /> : (
        <section className="rs-card su-group">
          {!phone && <div className="us-row us-hd"><span>Person</span><span>Role</span><span>Branch</span><span>Last seen</span><span /></div>}
          {rows.map((u) => (
            <div key={u.id} className={'us-row' + (u.is_active ? '' : ' off')}>
              <A to={u.view_url} className="us-who">
                <span className={'us-av ' + (ROLE_TONE[u.role_badge] || '')}>{initials(u.full_name || u.username)}</span>
                <span className="us-who-t"><b>{u.full_name || u.username}{u.is_self && <em> (you)</em>}</b>
                  <small>@{u.username}{u.email ? ` · ${u.email}` : ''}</small></span></A>
              <span className="us-role"><Pill tone={ROLE_TONE[u.role_badge]}>{u.display_role}</Pill>
                {u.group && <small><i className="fas fa-layer-group" aria-hidden="true" /> {u.group}</small>}
                {u.view_only && <small>View only</small>}</span>
              {!phone && <span className="us-br">{u.branch || '—'}</span>}
              <span className={'us-seen' + (u.last_days == null ? ' never' : u.last_days >= 90 ? ' old' : '')}>
                {!u.is_active ? <Pill tone="bad">Inactive</Pill> : seen(u.last_days)}
                {u.is_active && (u.mfa ? <small className="ok"><i className="fas fa-shield-halved" aria-hidden="true" /> 2FA</small>
                  : u.is_admin ? <small className="no"><i className="fas fa-shield" aria-hidden="true" /> No 2FA</small> : null)}</span>
              <span className="us-act">{menu(u)}</span>
            </div>))}
        </section>)}
    </div>
  );
}

// ---- Permission matrix ------------------------------------------------------
function Matrix({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [rows, setRows] = useState(() => {
    const m = {};
    // For grouped users the cells edit per-user OVERRIDES (so leaving a cell on
    // "Inherit" keeps the group's grant live); for others, their own perms.
    d.users.forEach((u) => { m[u.id] = { perms: { ...(u.group_name ? u.own_perms : u.perms) }, view_only: u.view_only }; });
    return m;
  });
  const setCell = (uid, key, val) => setRows((r) => ({ ...r, [uid]: { ...r[uid], perms: { ...r[uid].perms, [key]: val } } }));
  const setView = (uid, val) => setRows((r) => ({ ...r, [uid]: { ...r[uid], view_only: val } }));
  const submit = (e) => {
    e.preventDefault();
    const fields = {};
    d.users.filter((u) => !u.is_admin).forEach((u) => {
      d.modules.forEach((m) => {
        const lvl = rows[u.id].perms[m.key];
        if (lvl) fields[`perm_${u.id}_${m.key}`] = lvl;
      });
      if (rows[u.id].view_only) fields[`view_${u.id}`] = 'on';
    });
    save(d.save_url, fields, () => nav.refresh());
  };
  return (
    <>
      <div className="page-header">
        <h1><i aria-hidden="true" className="fas fa-table-cells" /> Permission Matrix</h1>
        <div className="page-header-actions"><A to={d.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A></div>
      </div>
      <p className="matrix-note"><i aria-hidden="true" className="fas fa-info-circle" /> Per cell: <strong>—</strong> no access, <strong>V</strong> view only, <strong>E</strong> view &amp; edit. For a user in a <strong><i aria-hidden="true" className="fas fa-layer-group" /> group</strong>, the first option (<strong>·V</strong>/<strong>·E</strong>/<strong>·—</strong>) means <em>inherit</em> the group's level and <strong>✕</strong> revokes it; V/E override it. A user with no cells set falls back to their group or role default. <strong>Admins</strong> always have full access. The <strong>View only</strong> column forces every section read-only.</p>
      <form onSubmit={submit}>
        <div className="card"><div className="card-body matrix-wrap">
          <table className="matrix">
            <thead><tr>
              <th className="user">User</th>
              {d.modules.map((m) => <th key={m.key} className="rot"><span>{m.label}</span></th>)}
              <th className="rot"><span>View only</span></th>
            </tr></thead>
            <tbody>
              {d.users.map((u) => (u.is_admin ? (
                <tr key={u.id} className="admin-row">
                  <td className="user">{u.name} <span className="badge badge-warning">Admin</span></td>
                  {d.modules.map((m) => <td key={m.key}><i aria-hidden="true" className="fas fa-check" style={{ color: 'var(--success)' }} /></td>)}
                  <td>—</td>
                </tr>
              ) : (
                <tr key={u.id}>
                  <td className="user"><A to={u.view_url}>{u.name}</A> <span className="badge badge-secondary">{u.display_role}</span>
                    {u.group_name && <div className="text-sm text-muted"><i aria-hidden="true" className="fas fa-layer-group" /> {u.group_name}</div>}</td>
                  {d.modules.map((m) => {
                    const g = u.group_name ? u.group_perms[m.key] : null;
                    return (
                    <td key={m.key}>
                      <select className="matrix-sel" value={rows[u.id].perms[m.key] || ''} onChange={(e) => setCell(u.id, m.key, e.target.value)}
                        title={u.group_name ? `Group grants: ${g ? (g === 'edit' ? 'edit' : 'view') : 'none'}` : undefined}>
                        {u.group_name
                          ? <option value="">{g ? (g === 'edit' ? '·E' : '·V') : '·—'}</option>
                          : <option value="">—</option>}
                        <option value="view">V</option><option value="edit">E</option>
                        {u.group_name && <option value="none">✕</option>}
                      </select>
                    </td>
                  ); })}
                  <td><input type="checkbox" checked={rows[u.id].view_only} onChange={(e) => setView(u.id, e.target.checked)} /></td>
                </tr>
              )))}
              {!d.has_editable && (
                <tr><td className="user" colSpan={d.modules.length + 2}>No non-admin users yet. <A to={d.add_url}>Add a user</A>.</td></tr>
              )}
            </tbody>
          </table>
        </div></div>
        <div className="d-flex gap-2 mt-3">
          <button type="submit" className="btn btn-primary btn-lg"><i aria-hidden="true" className="fas fa-save" /> Save Matrix</button>
          <A to={d.back_url} className="btn btn-secondary btn-lg">Cancel</A>
        </div>
      </form>
    </>
  );
}

// ---- Shared add/edit user form ---------------------------------------------
// ---- View user --------------------------------------------------------------
// ---- Assign class / subject -------------------------------------------------
function AssignClass({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [assignment_id, setAid] = useState('');
  const [is_form_teacher, setFt] = useState(true);
  const submit = (e) => {
    e.preventDefault();
    const fields = { assignment_id };
    if (is_form_teacher) fields.is_form_teacher = 'on';
    save(d.submit_url, fields, (r) => nav.go(r.redirect || d.back_url));
  };
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-chalkboard-teacher" /> Assign Class to {d.user.name}</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Select Class</label>
          <select className="form-control" value={assignment_id} onChange={(e) => setAid(e.target.value)} required>
            <option value="">-- Select Class --</option>
            {d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}
          </select></div>
        <div className="form-group"><label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
          <input type="checkbox" checked={is_form_teacher} onChange={(e) => setFt(e.target.checked)} style={{ width: '1.2rem', height: '1.2rem' }} /> <span>Assign as Form Teacher</span></label></div>
        <div className="d-flex gap-2">
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Assign</button>
          <A to={d.back_url} className="btn btn-secondary">Cancel</A>
        </div>
      </form></div></div>
    </>
  );
}

function AssignSubject({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [assignment_id, setAid] = useState('');
  const [subject_id, setSid] = useState('');
  const submit = (e) => {
    e.preventDefault();
    save(d.submit_url, { assignment_id, subject_id }, (r) => nav.go(r.redirect || d.back_url));
  };
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-book" /> Assign Subject to {d.user.name}</h1></div>
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Select Class</label>
          <select className="form-control" value={assignment_id} onChange={(e) => setAid(e.target.value)} required>
            <option value="">-- Select Class --</option>
            {d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}
          </select></div>
        <div className="form-group"><label className="form-label">Select Subject</label>
          <select className="form-control" value={subject_id} onChange={(e) => setSid(e.target.value)} required>
            <option value="">-- Select Subject --</option>
            {d.subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select></div>
        <div className="d-flex gap-2">
          <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Assign</button>
          <A to={d.back_url} className="btn btn-secondary">Cancel</A>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Permission groups ------------------------------------------------------
const SCREENS = {
  index: Index, matrix: Matrix, add: UserForm, edit: UserForm,
  view: UserView, assign_class: AssignClass, assign_subject: AssignSubject,
  groups: Groups,
};

export default function UsersApp({ data }) {
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
