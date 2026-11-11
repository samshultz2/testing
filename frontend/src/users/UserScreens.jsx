// User profile, add / edit form and permission groups — rebuilt on the
// results + app kits. The permission logic (role defaults, presets, group
// inheritance and per-user overrides, sub-parts and capabilities, the server
// password policy, drafts) is unchanged; only the presentation is new:
// role cards, preset chips, segmented View / Edit levels with the group's
// inherited level shown, a live summary, sticky save bar.
import React, { useState, useMemo } from 'react';
import { submitJson, useSave } from '../lib/forms';
import { useDraft } from '../lib/draft';
import { useNav } from '../lib/section';
import { confirm, Modal } from '../components/ui';
import { Head, Bar, Blank, Menu, usePhone, initials } from '../subjects/results';
import { A, SecNav, Field, Toggle, Pill, SearchBox, plural } from '../components/appkit';

const ruleOk = (rule, v) => (rule.min_length != null ? (v || '').length >= rule.min_length : new RegExp(rule.regex).test(v || ''));
const pwStrong = (rules, v) => (rules || []).every((r) => ruleOk(r, v));
const PwReqs = ({ rules, value }) => (
  <ul className="up-pw">{(rules || []).map((r) => {
    const ok = ruleOk(r, value || '');
    return <li key={r.id} className={ok ? 'ok' : ''}><i className={'fas ' + (ok ? 'fa-circle-check' : 'fa-circle')} aria-hidden="true" />{r.label}</li>;
  })}</ul>
);
const LVL = { view: 'View', edit: 'Edit', none: 'Revoked' };
const ROLES = [
  ['teacher', 'fa-chalkboard-user', 'Teacher', 'Their own classes and subjects: attendance, scores, reports.'],
  ['staff', 'fa-id-badge', 'Staff', 'Only the sections you switch on below — bursar, librarian, secretary…'],
  ['admin', 'fa-user-shield', 'Admin', 'Everything in their branch (or all branches if central).'],
  ['readonly', 'fa-eye', 'View only', 'Can look around the sections you allow but never change anything.'],
];
const TEACH = [['can_mark_attendance', 'Mark attendance'], ['can_view_student_details', 'See student details'],
  ['can_print_reports', 'Print reports'], ['can_enter_results', 'Enter results'], ['can_edit_results', 'Edit results after entry']];

function UNav({ d, active }) {
  const u = d.nav || {};
  return <SecNav label="Users" active={active} items={[
    ['index', 'fa-users', 'Users', u.index || d.back_url], ['matrix', 'fa-table-cells', 'Permission matrix', u.matrix],
    ['groups', 'fa-layer-group', 'Groups', u.groups]]} />;
}

// Segmented level picker: none / view / edit (+ inherit / revoke under a group).
function Level({ value, onChange, inherit, label }) {
  const opts = inherit !== undefined
    ? [['', inherit ? `Group: ${LVL[inherit]}` : 'Group: none'], ['view', 'View'], ['edit', 'Edit'], ['none', 'Revoke']]
    : [['', 'None'], ['view', 'View'], ['edit', 'Edit']];
  return (
    <div className="up-lv" role="radiogroup" aria-label={label}>{opts.map(([v, l]) => (
      <button key={v || 'x'} type="button" role="radio" aria-checked={(value || '') === v}
              className={((value || '') === v ? 'on ' : '') + (v || 'inh')} onClick={() => onChange(v)}>{l}</button>))}</div>
  );
}

// Module permissions editor shared by the user form and groups.
export function PermEditor({ d, perms, setPerm, setAll, groupPerms }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState({});
  const t = q.trim().toLowerCase();
  const subsOf = (k) => (d.subsections || {})[k] || [];
  const mods = d.modules.filter((m) => !t || m.label.toLowerCase().includes(t)
    || subsOf(m.key).some((s) => s.label.toLowerCase().includes(t)));
  const granted = Object.entries(perms).filter(([k, v]) => !k.includes('.') && v && v !== 'none').length;
  const inh = (k) => (groupPerms ? (groupPerms[k] || null) : undefined);
  return (
    <div className="up-perm">
      <div className="up-perm-t">
        <SearchBox value={q} onChange={setQ} placeholder="Find a section…" />
        <span className="cm-mute">{plural(granted, 'section')} set{groupPerms ? ' here (plus the group)' : ''}</span>
        <Menu label="Set all" items={[
          { icon: 'fa-ban', label: groupPerms ? 'Reset all to the group' : 'No access to anything', onClick: () => setAll('') },
          { icon: 'fa-eye', label: 'View everything', onClick: () => setAll('view') },
          { icon: 'fa-pen', label: 'Edit everything', onClick: () => setAll('edit') },
        ]} />
      </div>
      {mods.map((m) => {
        const subs = subsOf(m.key);
        const isCap = (d.cap_modules || []).includes(m.key);
        const subSet = subs.filter((s) => perms[`${m.key}.${s.sub}`]).length;
        const isOpen = open[m.key] || (t && subs.some((s) => s.label.toLowerCase().includes(t)));
        const eff = perms[m.key] || (groupPerms && groupPerms[m.key]);
        return (
          <div key={m.key} className={'up-mod' + (eff && eff !== 'none' ? ' has' : '')}>
            <div className="up-mod-r">
              <span className="up-mod-t"><b>{m.label}</b>
                {subs.length > 0 && <button type="button" className="up-more" onClick={() => setOpen({ ...open, [m.key]: !isOpen })} aria-expanded={!!isOpen}>
                  {isCap ? <><i className="fas fa-key" aria-hidden="true" /> Special powers</> : `${subs.length} parts`}{subSet ? ` · ${subSet} set` : ''}
                  <i className={'fas fa-chevron-' + (isOpen ? 'up' : 'down')} aria-hidden="true" /></button>}</span>
              <Level value={perms[m.key]} onChange={(v) => setPerm(m.key, v)} inherit={inh(m.key)} label={m.label} />
            </div>
            {isOpen && subs.length > 0 && (
              <div className="up-subs">{subs.map((s) => {
                const sk = `${m.key}.${s.sub}`;
                const cap = (d.capabilities || []).includes(sk);
                return (
                  <div key={sk} className="up-sub">
                    <span>{cap ? <i className="fas fa-key" aria-hidden="true" /> : <i className="fas fa-turn-up fa-rotate-90" aria-hidden="true" />} {s.label}</span>
                    <Level value={perms[sk]} onChange={(v) => setPerm(sk, v)} inherit={inh(sk)} label={s.label} />
                  </div>);
              })}</div>)}
          </div>);
      })}
      <p className="cm-mute up-note"><i className="fas fa-circle-info" aria-hidden="true" /> A part’s level overrides its section. <i className="fas fa-key" aria-hidden="true" /> Special powers (e.g. generate timetable, generate result cards) are never implied — switch them on explicitly.</p>
    </div>
  );
}

// ============================================================================
// Add / edit user
// ============================================================================
function moduleDefaults(roleDefaults, role) {
  const lvl = role === 'readonly' ? 'view' : 'edit';
  const want = {};
  (roleDefaults[role] || []).forEach((m) => { want[m] = lvl; });
  return want;
}

export function UserForm({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const phone = usePhone();
  const edit = d.page === 'edit';
  const u = d.user || {};
  const editSig = edit ? JSON.stringify([u.email, u.full_name, u.phone, u.role, u.section, u.stream, u.manage_scope,
    u.rank, u.view_only, u.scope, u.branch_id, u.is_active, u.permission_group_id, u.own_permissions, u.teacher]) : null;
  const [f, setF, clearDraft] = useDraft('users-' + (edit ? 'edit-' + (u.id || '') : 'add'), {
    username: u.username || '', email: u.email || '', full_name: u.full_name || '', phone: u.phone || '',
    password: '', confirm_password: '', require_pw_change: true, new_password: '',
    role: u.role || 'teacher', scope: u.scope === 'central' ? 'central' : 'branch',
    branch_id: u.branch_id || (d.branches.find((b) => b.is_default) || d.branches[0] || {}).id || '',
    section: u.section || '', stream: u.stream || '', manage_scope: u.manage_scope || 'none', rank: u.rank || 0,
    view_only: !!u.view_only, is_active: edit ? !!u.is_active : true, create_staff: false,
    permission_group_id: u.permission_group_id ? String(u.permission_group_id) : '',
    teacher: u.teacher || { can_mark_attendance: true, can_view_student_details: true, can_print_reports: true, can_enter_results: false, can_edit_results: false },
  }, { omit: ['password', 'confirm_password', 'new_password'], signature: editSig });
  const [perms, setPerms] = useState(() => {
    if (!edit) return moduleDefaults(d.role_defaults, u.role || 'teacher');
    const eff = u.permission_map || {};
    const grp = u.group_permissions || {};
    const seed = {};
    Object.keys(eff).forEach((k) => { if (eff[k] && eff[k] !== grp[k]) seed[k] = eff[k]; });
    Object.entries(u.own_permissions || {}).forEach(([k, v]) => { if (v && !(k in seed)) seed[k] = v; });
    return seed;
  });
  const groups = d.groups || [];
  const group = groups.find((g) => String(g.id) === String(f.permission_group_id));
  const groupPerms = group ? group.permissions : null;
  const [preset, setPreset] = useState('');
  const [errors, setErrors] = useState({});
  const [more, setMore] = useState(!!(edit && (f.section || f.stream || f.manage_scope !== 'none' || Number(f.rank))));
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const setPerm = (key, val) => setPerms((p) => { const n = { ...p }; if (val) n[key] = val; else delete n[key]; return n; });
  const setAll = (val) => setPerms(() => { if (!val) return {}; const n = {}; d.modules.forEach((m) => { n[m.key] = val; }); return n; });
  const onRole = (role) => {
    setF({ ...f, role });
    setPerms((p) => {
      const next = {};
      Object.keys(p).forEach((k) => { if (k.includes('.')) next[k] = p[k]; });
      return { ...next, ...moduleDefaults(d.role_defaults, role) };
    });
  };
  const applyPreset = (key) => {
    setPreset(key);
    const p = d.presets[key];
    if (!p) return;
    setF((cur) => ({ ...cur, role: p.role, scope: p.scope === 'central' ? 'central' : 'branch', section: p.section || '',
      stream: p.stream || '', manage_scope: p.manage_scope || 'none', rank: p.rank || 0 }));
    setPerms((cur) => {
      const subs = {};
      Object.keys(cur).forEach((k) => { if (k.includes('.')) subs[k] = cur[k]; });
      if ((p.modules || []).length) { const want = {}; p.modules.forEach((m) => { want[m] = 'edit'; }); return { ...subs, ...want }; }
      return { ...subs, ...moduleDefaults(d.role_defaults, p.role) };
    });
  };
  const showTeacher = f.role === 'teacher';
  const showModules = f.role !== 'admin';
  const pwMin = (d.password_rules || []).reduce((m, r) => (r.min_length != null ? r.min_length : m), 12);
  const submit = () => {
    const errs = {};
    if (!edit) {
      if (!f.username.trim() || !/^[a-zA-Z0-9_]+$/.test(f.username)) errs.username = 'Letters, numbers and _ only.';
      if (!pwStrong(d.password_rules, f.password)) errs.password = 'Doesn’t meet the requirements yet.';
      if (f.confirm_password !== f.password) errs.confirm_password = 'Passwords don’t match.';
    } else if (f.new_password && !pwStrong(d.password_rules, f.new_password)) {
      errs.new_password = 'Doesn’t meet the requirements yet.';
    }
    setErrors(errs);
    if (Object.keys(errs).length) { notify('error', 'Please fix the highlighted fields.'); return; }
    const fields = { email: f.email, full_name: f.full_name, phone: f.phone, role: f.role, scope: f.scope, branch_id: f.branch_id,
      section: f.section, stream: f.stream, manage_scope: f.manage_scope, rank: f.rank };
    if (edit) {
      if (f.new_password) fields.new_password = f.new_password;
      if (f.is_active) fields.is_active = 'on';
    } else {
      fields.username = f.username; fields.password = f.password; fields.confirm_password = f.confirm_password;
      if (f.require_pw_change) fields.require_pw_change = 'on';
      if (f.create_staff) fields.create_staff = 'on';
    }
    if (f.view_only) fields.view_only = 'on';
    if (showModules) {
      fields.permission_group_id = f.permission_group_id || '';
      Object.entries(perms).forEach(([k, v]) => { if (v) fields[`perm_${k}`] = v; });
    }
    if (showTeacher) TEACH.forEach(([k]) => { if (f.teacher[k]) fields[k] = 'on'; });
    save(d.submit_url, fields, (r) => { clearDraft(); nav.go(r.redirect || d.back_url); });
  };
  const err = (k) => errors[k] && <small className="up-err">{errors[k]}</small>;
  const access = useMemo(() => {
    const eff = { ...(groupPerms || {}), ...perms };
    const top = d.modules.filter((m) => eff[m.key] && eff[m.key] !== 'none');
    return { edit: top.filter((m) => eff[m.key] === 'edit'), view: top.filter((m) => eff[m.key] === 'view') };
  }, [perms, groupPerms, d.modules]);
  const branchName = f.scope === 'central' ? 'All branches' : ((d.branches.find((b) => String(b.id) === String(f.branch_id)) || {}).name || '');
  const role = ROLES.find((r) => r[0] === f.role) || ROLES[0];
  return (
    <div className="rs cm up">
      <UNav d={d} active="index" />
      <Head icon={edit ? 'fa-user-pen' : 'fa-user-plus'} title={edit ? `Edit ${u.full_name || u.username}` : 'Add a user'}
            sub={edit ? `@${u.username}` : 'Create a sign-in for a member of staff.'} />
      <div className="up-wrap">
        <div className="up-main">
          {!edit && Object.keys(d.presets || {}).length > 0 && (
            <section className="rs-card up-sec"><div className="rs-card-h"><h3><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Start from a job</h3></div>
              <div className="st-chips">{Object.entries(d.presets).map(([k, p]) => (
                <button key={k} type="button" className={'st-chip' + (preset === k ? ' on' : '')} onClick={() => applyPreset(k)}>{p.label}</button>))}</div>
              <small className="cm-mute">{d.presets[preset]?.description || 'Fills in the role, branch and sections for that job — you can still change anything.'}</small>
            </section>)}

          <section className="rs-card up-sec">
            <div className="rs-card-h"><h3><i className="fas fa-id-card" aria-hidden="true" /> Who they are</h3></div>
            <div className="cm-row2">
              <Field label="Full name" grow><input type="text" value={f.full_name} onChange={set('full_name')} placeholder="e.g. Grace Okafor" /></Field>
              <Field label={edit ? 'Username' : 'Username *'} grow>
                <input type="text" value={f.username} onChange={set('username')} disabled={edit} autoCapitalize="none" placeholder="e.g. grace.okafor" />{err('username')}</Field>
            </div>
            <div className="cm-row2">
              <Field label="Email" grow hint="Used for password resets"><input type="email" value={f.email} onChange={set('email')} placeholder="name@school.com" /></Field>
              <Field label="Phone" grow><input type="tel" value={f.phone} onChange={set('phone')} placeholder="08012345678" /></Field>
            </div>
          </section>

          <section className="rs-card up-sec">
            <div className="rs-card-h"><h3><i className="fas fa-key" aria-hidden="true" /> {edit ? 'Password' : 'Sign-in password'}</h3></div>
            {!edit ? (<>
              <div className="cm-row2">
                <Field label="Password *" grow><input type="password" value={f.password} onChange={set('password')} minLength={pwMin} placeholder={`At least ${pwMin} characters`} autoComplete="new-password" />{err('password')}</Field>
                <Field label="Repeat it *" grow><input type="password" value={f.confirm_password} onChange={set('confirm_password')} autoComplete="new-password"
                  onBlur={() => setErrors((e) => ({ ...e, confirm_password: f.confirm_password && f.confirm_password !== f.password ? 'Passwords don’t match.' : undefined }))} />{err('confirm_password')}</Field>
              </div>
              <PwReqs rules={d.password_rules} value={f.password} />
              <Toggle title="Make them choose their own password" sub="They set a new one the first time they sign in" on={f.require_pw_change} onChange={(v) => setF({ ...f, require_pw_change: v })} />
              <Toggle title="Also create their staff (HR) record" sub="Uses these details for payroll, leave and staff attendance" on={f.create_staff} onChange={(v) => setF({ ...f, create_staff: v })} />
            </>) : (<>
              <Field label="New password" hint="Leave blank to keep the current one"><input type="password" value={f.new_password} onChange={set('new_password')} minLength={pwMin} autoComplete="new-password" />{err('new_password')}</Field>
              {f.new_password && <PwReqs rules={d.password_rules} value={f.new_password} />}
              <Toggle title="Account active" sub={f.is_active ? 'They can sign in' : 'Sign-in is blocked; their history is kept'} on={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} />
            </>)}
          </section>

          <section className="rs-card up-sec">
            <div className="rs-card-h"><h3><i className="fas fa-user-tag" aria-hidden="true" /> Role</h3></div>
            <div className="up-roles" role="radiogroup" aria-label="Role">{ROLES.map(([k, ic, l, sub]) => (
              <button key={k} type="button" role="radio" aria-checked={f.role === k} className={f.role === k ? 'on' : ''} onClick={() => onRole(k)}>
                <i className={'fas ' + ic} aria-hidden="true" /><b>{l}</b><small>{sub}</small></button>))}</div>
            <div className="cm-row2">
              <Field label="Branch access" grow><select value={f.scope} onChange={set('scope')}>
                <option value="branch">One branch</option><option value="central">All branches</option></select></Field>
              {f.scope !== 'central' && <Field label="Branch" grow><select value={f.branch_id} onChange={set('branch_id')}>
                {d.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>}
            </div>
            <button type="button" className="up-more up-adv" onClick={() => setMore(!more)} aria-expanded={!!more}>
              More options — section, stream, managing other users <i className={'fas fa-chevron-' + (more ? 'up' : 'down')} aria-hidden="true" /></button>
            {more && (<>
              <div className="cm-row2">
                <Field label="Section" grow><select value={f.section} onChange={set('section')}>
                  <option value="">All sections</option><option value="secondary">Secondary (JSS + SSS)</option><option value="primary">Nursery & Primary</option></select></Field>
                <Field label="Subject stream" grow><select value={f.stream} onChange={set('stream')}>
                  <option value="">All streams</option><option value="arts">Arts & Commercial</option><option value="science">Sciences</option></select></Field>
              </div>
              <div className="cm-row2">
                <Field label="Can manage other users" grow><select value={f.manage_scope} onChange={set('manage_scope')}>
                  <option value="none">No</option><option value="branch">Yes — in their branch (lower ranks)</option><option value="central">Yes — all branches</option></select></Field>
                <Field label="Rank" hint="Higher can manage lower"><input type="number" min="0" max="100" value={f.rank} onChange={set('rank')} style={{ width: 110 }} /></Field>
              </div>
            </>)}
          </section>

          {showTeacher && (
            <section className="rs-card up-sec">
              <div className="rs-card-h"><h3><i className="fas fa-chalkboard-user" aria-hidden="true" /> What they can do in their classes</h3></div>
              {TEACH.map(([k, l]) => <Toggle key={k} title={l} on={!!f.teacher[k]} onChange={(v) => setF({ ...f, teacher: { ...f.teacher, [k]: v } })} />)}
              <small className="cm-mute">Teachers only ever see the classes and subjects assigned to them.</small>
            </section>)}

          {showModules ? (
            <section className="rs-card up-sec">
              <div className="rs-card-h"><h3><i className="fas fa-table-cells-large" aria-hidden="true" /> Sections they can open</h3></div>
              {groups.length > 0 && (
                <Field label="Permission group" hint={group ? 'The group sets the starting point; change any section to override it.' : 'Optional — a ready-made set of sections shared by a team.'}>
                  <select value={f.permission_group_id} onChange={set('permission_group_id')}>
                    <option value="">No group — set each section here</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>)}
              <PermEditor d={d} perms={perms} setPerm={setPerm} setAll={setAll} groupPerms={groupPerms} />
              <Toggle title="View only" sub="Can browse the sections above but never create, change or delete" on={f.view_only} onChange={(v) => setF({ ...f, view_only: v })} />
            </section>
          ) : (
            <section className="rs-card up-sec up-admin"><i className="fas fa-user-shield" aria-hidden="true" />
              <span><b>Admins can open everything</b><small>{f.scope === 'central' ? 'Across every branch.' : `In ${branchName || 'their branch'}.`} Pick another role to limit what they see.</small></span></section>)}
        </div>

        {!phone && (
          <aside className="up-side">
            <section className="rs-card up-sum">
              <span className="us-av lg">{initials(f.full_name || f.username || '?')}</span>
              <b>{f.full_name || 'New user'}</b><small>{f.username ? '@' + f.username : 'no username yet'}</small>
              <div className="up-sum-p"><Pill icon={role[1]}>{role[2]}</Pill><Pill>{branchName}</Pill>{f.view_only && <Pill tone="mid">View only</Pill>}{group && <Pill tone="info">{group.name}</Pill>}</div>
              {f.role === 'admin' ? <p className="cm-mute">Full access{f.scope === 'central' ? ' to every branch' : ''}.</p> : (
                <div className="up-sum-a">
                  <span className="k">Can change ({access.edit.length})</span><p>{access.edit.map((m) => m.label).join(', ') || '—'}</p>
                  <span className="k">Can view ({access.view.length})</span><p>{access.view.map((m) => m.label).join(', ') || '—'}</p>
                </div>)}
              <button type="button" className="rs-btn primary su-block" onClick={submit}><i className="fas fa-check" aria-hidden="true" /> {edit ? 'Save changes' : 'Create user'}</button>
              <A to={d.back_url} className="rs-btn ghost su-block">Cancel</A>
            </section>
          </aside>)}
      </div>
      {phone && (
        <Bar><A to={d.back_url} className="rs-btn ghost">Cancel</A>
          <button type="button" className="rs-btn primary" onClick={submit}><i className="fas fa-check" aria-hidden="true" /> {edit ? 'Save' : 'Create user'}</button></Bar>)}
    </div>
  );
}

// ============================================================================
// Profile
// ============================================================================
function ResetResultModal({ r, onClose }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { try { await navigator.clipboard.writeText(r.temp_password); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch (_) { /* select instead */ } };
  return (
    <Modal title="Password reset" icon="fa-key" size="sm" onClose={onClose} closeOnBackdrop={false}
           footer={<button type="button" className="rs-btn primary" onClick={onClose}>Done</button>}>
      {r.emailed ? (
        <div className="up-reset ok"><i className="fas fa-paper-plane" aria-hidden="true" />
          <b>New password sent by email</b><p>A temporary password for <strong>{r.username}</strong> was emailed to <strong>{r.user_email}</strong>. They must change it when they sign in.</p></div>
      ) : (
        <div className="up-reset">
          <p>{r.user_email ? 'Email couldn’t be sent, so share this temporary password securely with ' : 'There’s no email on file, so give this temporary password to '}<strong>{r.username}</strong>. They must change it at their next sign-in.</p>
          <div className="up-reset-pw"><code>{r.temp_password}</code>
            <button type="button" className="rs-btn ghost" onClick={copy}><i className={'fas ' + (copied ? 'fa-check' : 'fa-copy')} aria-hidden="true" /> {copied ? 'Copied' : 'Copy'}</button></div>
          <small className="cm-mute"><i className="fas fa-triangle-exclamation" aria-hidden="true" /> It won’t be shown again after you close this.</small>
        </div>)}
    </Modal>
  );
}

const ago = (n) => (n == null ? 'Never signed in' : n === 0 ? 'Today' : n === 1 ? 'Yesterday' : n < 31 ? `${n} days ago` : n < 365 ? `${Math.floor(n / 30)} months ago` : 'Over a year ago');

export function UserView({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const u = d.user;
  const [reset, setReset] = useState(null);
  const doReset = async () => {
    if (!await confirm({ title: 'Reset password?', confirmText: 'Reset', message: `${u.full_name || u.username} gets a temporary password and must choose a new one when they sign in.` })) return;
    const r = await submitJson(u.reset_password_url, {});
    if (r.ok) setReset(r); else notify('error', r.error || 'Could not reset the password.');
  };
  const resetMfa = async () => {
    if (!await confirm({ title: 'Turn off two-step sign-in?', confirmText: 'Turn off', tone: 'danger', message: 'Only do this for someone who has lost their authenticator phone. They can set it up again afterwards.' })) return;
    save(u.reset_mfa_url, {}, () => nav.refresh());
  };
  const toggle = async () => {
    if (u.is_active && !await confirm({ title: `Deactivate ${u.full_name || u.username}?`, confirmText: 'Deactivate', message: 'They won’t be able to sign in. Their history stays and you can reactivate them.' })) return;
    save(u.toggle_url, {}, () => nav.refresh());
  };
  const removeAssign = async (url, type, label) => {
    if (await confirm({ title: `Remove ${label}?`, confirmText: 'Remove', message: 'They will no longer see this class / subject.' })) save(url, { type, user_id: u.id }, () => nav.refresh());
  };
  const tone = { danger: 'bad', warning: 'mid', info: 'info', secondary: '' }[u.role_badge] || '';
  const mods = u.module_access || [];
  return (
    <div className="rs cm up">
      <UNav d={d} active="index" />
      <section className="rs-card up-hero">
        <span className={'us-av xl ' + tone}>{initials(u.full_name || u.username)}</span>
        <div className="up-hero-t">
          <h1>{u.full_name || u.username}{u.is_self && <em> (you)</em>}</h1>
          <div className="up-hero-m"><span>@{u.username}</span>{u.branch && <span><i className="fas fa-code-branch" aria-hidden="true" /> {u.branch}</span>}{u.group && <span><i className="fas fa-layer-group" aria-hidden="true" /> {u.group}</span>}</div>
          <div className="up-sum-p"><Pill tone={tone}>{u.display_role}</Pill>
            {u.is_active ? <Pill tone="good">Active</Pill> : <Pill tone="bad">Inactive</Pill>}
            {u.mfa_enabled ? <Pill tone="good" icon="fa-shield-halved">2FA on</Pill> : <Pill tone={u.is_admin ? 'bad' : ''} icon="fa-shield">No 2FA</Pill>}
            {u.view_only && <Pill tone="mid">View only</Pill>}</div>
        </div>
        <div className="up-hero-a">
          <A to={u.edit_url} className="rs-btn primary"><i className="fas fa-pen" aria-hidden="true" /> Edit</A>
          <Menu label="More" items={[
            { icon: 'fa-key', label: 'Reset password', onClick: doReset },
            u.mfa_enabled && { icon: 'fa-shield-halved', label: 'Turn off two-step sign-in', onClick: resetMfa },
            !u.is_self && { icon: u.is_active ? 'fa-ban' : 'fa-circle-check', label: u.is_active ? 'Deactivate' : 'Reactivate', onClick: toggle },
          ]} />
        </div>
      </section>
      <div className="up-grid">
        <section className="rs-card up-sec">
          <div className="rs-card-h"><h3><i className="fas fa-id-card" aria-hidden="true" /> Account</h3></div>
          <dl className="ad-kv">
            <dt>Email</dt><dd>{u.email ? <a href={'mailto:' + u.email}>{u.email}</a> : '—'}</dd>
            <dt>Phone</dt><dd>{u.phone ? <a href={'tel:' + u.phone}>{u.phone}</a> : '—'}</dd>
            <dt>Last seen</dt><dd>{ago(u.last_days)}{u.last_login !== 'Never' && <small> · {u.last_login}</small>}</dd>
            <dt>Account created</dt><dd>{u.created || '—'}</dd>
            <dt>Manages users</dt><dd>{{ none: 'No', branch: 'In their branch', central: 'All branches' }[u.manage_scope] || 'No'}</dd>
          </dl>
        </section>
        <section className="rs-card up-sec">
          <div className="rs-card-h"><h3><i className="fas fa-table-cells-large" aria-hidden="true" /> What they can open</h3>
            <A to={u.edit_url} className="cm-link">Change <i className="fas fa-arrow-right" aria-hidden="true" /></A></div>
          {u.is_admin ? <p className="cm-mute">Everything — admins have full access.</p>
            : !u.has_custom_modules ? <p className="cm-mute">The standard sections for the {u.display_role} role.</p> : (
              <div className="up-acc">
                {['edit', 'view'].map((lv) => {
                  const xs = mods.filter((m) => m.level === lv);
                  return xs.length ? <div key={lv}><span className="k">{lv === 'edit' ? 'Can change' : 'Can view'}</span>
                    <div className="st-chips">{xs.map((m) => <span key={m.key} className={'up-chip ' + lv}><i className={'fas ' + (lv === 'edit' ? 'fa-pen' : 'fa-eye')} aria-hidden="true" /> {m.label}</span>)}</div></div> : null;
                })}
                <small className="cm-mute">{plural(mods.filter((m) => !m.level).length, 'section')} hidden from them.</small>
              </div>)}
        </section>
        {u.teacher && (
          <section className="rs-card up-sec">
            <div className="rs-card-h"><h3><i className="fas fa-chalkboard-user" aria-hidden="true" /> In their classes</h3></div>
            <div className="up-tp">{TEACH.map(([k, l]) => (
              <span key={k} className={u.teacher[k] ? 'on' : ''}><i className={'fas ' + (u.teacher[k] ? 'fa-circle-check' : 'fa-circle-xmark')} aria-hidden="true" /> {l}</span>))}</div>
          </section>)}
        {u.teacher && (
          <section className="rs-card up-sec">
            <div className="rs-card-h"><h3><i className="fas fa-school" aria-hidden="true" /> Classes</h3>
              <A to={u.assign_class_url} className="rs-btn sm ghost"><i className="fas fa-plus" aria-hidden="true" /> Assign</A></div>
            {u.class_assignments.length ? u.class_assignments.map((a) => (
              <div key={a.id} className="up-as"><b>{a.name}</b>{a.is_form_teacher && <Pill tone="good">Form teacher</Pill>}
                <button type="button" className="cm-ib" aria-label={`Remove ${a.name}`} onClick={() => removeAssign(a.remove_url, 'class', a.name)}><i className="fas fa-xmark" aria-hidden="true" /></button></div>))
              : <p className="cm-mute">No classes yet.</p>}
          </section>)}
        {u.teacher && (
          <section className="rs-card up-sec">
            <div className="rs-card-h"><h3><i className="fas fa-book" aria-hidden="true" /> Subjects</h3>
              <A to={u.assign_subject_url} className="rs-btn sm ghost"><i className="fas fa-plus" aria-hidden="true" /> Assign</A></div>
            {u.subject_assignments.length ? u.subject_assignments.map((a) => (
              <div key={a.id} className="up-as"><b>{a.subject}</b><small>{a.class}</small>
                <button type="button" className="cm-ib" aria-label={`Remove ${a.subject}`} onClick={() => removeAssign(a.remove_url, 'subject', `${a.subject} (${a.class})`)}><i className="fas fa-xmark" aria-hidden="true" /></button></div>))
              : <p className="cm-mute">No subjects yet.</p>}
          </section>)}
        {!u.teacher && u.can_enable_teaching && (
          <section className="rs-card up-sec up-admin"><i className="fas fa-chalkboard-user" aria-hidden="true" />
            <span><b>Do they teach too?</b><small>Turn on teaching to give them classes (as form teacher) and subjects.</small></span>
            <button type="button" className="rs-btn ghost" onClick={() => save(u.enable_teaching_url, {}, () => nav.refresh())}>Enable teaching</button></section>)}
      </div>
      {reset && <ResetResultModal r={reset} onClose={() => setReset(null)} />}
    </div>
  );
}

// ============================================================================
// Permission groups
// ============================================================================
export function Groups({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const phone = usePhone();
  const [editing, setEditing] = useState(null);
  const start = (g) => setEditing(g
    ? { id: g.id, name: g.name, description: g.description || '', branch_id: g.branch_id || '', permissions: { ...g.permissions }, edit_url: g.edit_url }
    : { id: null, name: '', description: '', branch_id: '', permissions: {} });
  const setField = (k, v) => setEditing((e) => ({ ...e, [k]: v }));
  const setPerm = (key, val) => setEditing((e) => { const p = { ...e.permissions }; if (val) p[key] = val; else delete p[key]; return { ...e, permissions: p }; });
  const setAll = (val) => setEditing((e) => { if (!val) return { ...e, permissions: {} }; const p = {}; d.modules.forEach((m) => { p[m.key] = val; }); return { ...e, permissions: p }; });
  const submit = () => {
    if (!editing.name.trim()) { notify('error', 'Give the group a name.'); return; }
    const fields = { name: editing.name, description: editing.description };
    if (d.can_pick_branch) fields.branch_id = editing.branch_id || '';
    Object.entries(editing.permissions).forEach(([k, v]) => { if (v) fields[`perm_${k}`] = v; });
    save(editing.id ? editing.edit_url : d.add_url, fields, () => { setEditing(null); nav.refresh(); });
  };
  const del = async (g) => {
    if (await confirm({ title: `Delete “${g.name}”?`, tone: 'danger', confirmText: 'Delete',
      message: `${plural(g.user_count || 0, 'member')} keep their own settings but lose what this group gave them.` })) save(g.delete_url, {}, () => nav.refresh());
  };
  const labelFor = (k) => {
    const m = d.modules.find((x) => x.key === k);
    if (m) return m.label;
    const [mk, sk] = k.split('.');
    const s = ((d.subsections || {})[mk] || []).find((x) => x.sub === sk);
    return s ? s.label : k;
  };
  if (editing) {
    return (
      <div className="rs cm up">
        <UNav d={d} active="groups" />
        <Head icon="fa-layer-group" title={editing.id ? `Edit “${editing.name || 'group'}”` : 'New permission group'} sub="Everyone in the group gets these sections. You can still adjust any one person." />
        <section className="rs-card up-sec">
          <div className="cm-row2">
            <Field label="Name *" grow><input type="text" value={editing.name} autoFocus placeholder="e.g. Bursary team" onChange={(e) => setField('name', e.target.value)} /></Field>
            <Field label="What it’s for" grow><input type="text" value={editing.description} placeholder="e.g. Fees and expenses" onChange={(e) => setField('description', e.target.value)} /></Field>
            {d.can_pick_branch && <Field label="Branch" grow><select value={editing.branch_id} onChange={(e) => setField('branch_id', e.target.value)}>
              <option value="">All branches</option>{d.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>}
          </div>
        </section>
        <section className="rs-card up-sec">
          <div className="rs-card-h"><h3><i className="fas fa-table-cells-large" aria-hidden="true" /> Sections</h3></div>
          <PermEditor d={d} perms={editing.permissions} setPerm={setPerm} setAll={setAll} />
        </section>
        <Bar><span className="ad-bar-t">{plural(Object.keys(editing.permissions).filter((k) => !k.includes('.')).length, 'section')} set</span>
          <button type="button" className="rs-btn ghost" onClick={() => setEditing(null)}>Cancel</button>
          <button type="button" className="rs-btn primary" onClick={submit}><i className="fas fa-check" aria-hidden="true" /> {editing.id ? 'Save group' : 'Create group'}</button></Bar>
      </div>
    );
  }
  return (
    <div className="rs cm up">
      <UNav d={d} active="groups" />
      <Head icon="fa-layer-group" title="Permission groups" sub="Ready-made sets of sections for a team — give someone the group instead of ticking each section.">
        <button type="button" className="rs-btn primary" onClick={() => start(null)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> New group</span></button>
      </Head>
      {!d.groups.length ? (
        <Blank icon="fa-layer-group" title="No groups yet"><p>For example a “Bursary” group with Finance, or “Exams office” with Results and CBT.</p>
          <button type="button" className="rs-btn primary" onClick={() => start(null)}><i className="fas fa-plus" aria-hidden="true" /> New group</button></Blank>
      ) : (
        <div className="up-groups">{d.groups.map((g) => {
          const keys = Object.keys(g.permissions || {}).filter((k) => !k.includes('.'));
          const parts = Object.keys(g.permissions || {}).length - keys.length;
          return (
            <article key={g.id} className="rs-card up-group">
              <div className="up-group-h"><span className="up-group-ic"><i className="fas fa-layer-group" aria-hidden="true" /></span>
                <div><b>{g.name}</b><small>{g.description || 'No description'}</small></div>
                {g.manageable ? <Menu label={`More for ${g.name}`} items={[
                  { icon: 'fa-pen', label: 'Edit', onClick: () => start(g) }, { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => del(g) }]} />
                  : <Pill>Central</Pill>}</div>
              <div className="up-group-m"><span><b>{g.user_count || 0}</b> {g.user_count === 1 ? 'member' : 'members'}</span><span>{g.branch_name}</span></div>
              <div className="st-chips">{keys.slice(0, phone ? 4 : 8).map((k) => (
                <span key={k} className={'up-chip ' + g.permissions[k]}><i className={'fas ' + (g.permissions[k] === 'edit' ? 'fa-pen' : 'fa-eye')} aria-hidden="true" /> {labelFor(k)}</span>))}
                {keys.length > (phone ? 4 : 8) && <span className="up-chip">+{keys.length - (phone ? 4 : 8)} more</span>}
                {parts > 0 && <span className="up-chip">{plural(parts, 'part')}</span>}
                {!keys.length && !parts && <span className="cm-mute">No sections yet</span>}</div>
              {g.manageable && <button type="button" className="rs-btn ghost sm" onClick={() => start(g)}>Edit sections</button>}
            </article>);
        })}</div>)}
    </div>
  );
}
