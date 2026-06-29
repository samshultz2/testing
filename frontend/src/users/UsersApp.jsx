import React, { useState } from 'react';
import { submitJson, useSave } from '../lib/forms';
import { useDraft } from '../lib/draft';
import { useSection, NavCtx, useNav } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';

const A = ({ to, className, children, title }) => {
  const nav = useNav();
  return <a href={to} title={title} className={className}
    onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};

// ---- Index ------------------------------------------------------------------
function Index({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const toggle = (u) => save(u.toggle_url, {}, () => nav.refresh());
  return (
    <>
      <div className="page-header">
        <h1><i aria-hidden="true" className="fas fa-users-cog" /> User Management</h1>
        <div className="page-header-actions">
          <A to={d.matrix_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-table-cells" /> Permission Matrix</A>
          <A to={d.groups_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-layer-group" /> Permission Groups</A>
          <A to={d.add_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add User</A>
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-list" /> All Users ({d.users.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.users.length ? (
            <div className="table-responsive"><table className="data-table">
              <thead><tr><th>Username</th><th>Full Name</th><th>Role</th><th>Status</th><th>Last Login</th><th>Actions</th></tr></thead>
              <tbody>
                {d.users.map((u) => (
                  <tr key={u.id}>
                    <td><strong>{u.username}</strong></td>
                    <td>{u.full_name || '-'}</td>
                    <td><span className={`badge badge-${u.role_badge}`}>{u.display_role}</span></td>
                    <td><span className={`badge badge-${u.is_active ? 'success' : 'danger'}`}>{u.is_active ? 'Active' : 'Inactive'}</span></td>
                    <td>{u.last_login}</td>
                    <td><div className="d-flex gap-1">
                      <A to={u.view_url} className="btn btn-sm btn-info" title="View"><i aria-hidden="true" className="fas fa-eye" /></A>
                      <A to={u.edit_url} className="btn btn-sm btn-warning" title="Edit"><i aria-hidden="true" className="fas fa-edit" /></A>
                      {!u.is_self && (
                        <button type="button" onClick={() => toggle(u)}
                          className={`btn btn-sm btn-${u.is_active ? 'secondary' : 'success'}`}
                          title={u.is_active ? 'Deactivate' : 'Activate'}>
                          <i aria-hidden="true" className={`fas fa-${u.is_active ? 'ban' : 'check'}`} />
                        </button>
                      )}
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : (
            <Empty icon="fa-users" title="No Users">No users have been added yet</Empty>
          )}
        </div>
      </div>
    </>
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
function moduleDefaults(roleDefaults, role) {
  const mods = roleDefaults[role] || [];
  const lvl = role === 'readonly' ? 'view' : 'edit';
  const want = {};
  mods.forEach((m) => { want[m] = lvl; });
  return want;   // whole-module levels only
}

function UserForm({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const edit = d.page === 'edit';
  const u = d.user || {};
  // Signature of the server's current values, so a draft saved before an edit is
  // discarded once the save lands (otherwise the stale draft re-blanks fields on
  // reopen). Unchanged baseline = genuine unsaved work, still recovered.
  const editSig = edit ? JSON.stringify([
    u.email, u.full_name, u.phone, u.role, u.section, u.stream, u.manage_scope,
    u.rank, u.view_only, u.scope, u.branch_id, u.is_active, u.permission_group_id,
    u.own_permissions, u.teacher,
  ]) : null;
  const [f, setF, clearDraft] = useDraft('users-' + (edit ? 'edit-' + (u.id || '') : 'add'), {
    username: u.username || '',
    email: u.email || '',
    full_name: u.full_name || '',
    phone: u.phone || '',
    password: '', confirm_password: '', require_pw_change: true,   // add
    new_password: '',                                              // edit
    role: u.role || 'teacher',
    scope: u.scope === 'central' ? 'central' : 'branch',
    branch_id: u.branch_id || (d.branches.find((b) => b.is_default) || d.branches[0] || {}).id || '',
    section: u.section || '',
    stream: u.stream || '',
    manage_scope: u.manage_scope || 'none',
    rank: u.rank || 0,
    view_only: !!u.view_only,
    is_active: edit ? !!u.is_active : true,
    permission_group_id: u.permission_group_id ? String(u.permission_group_id) : '',
    teacher: u.teacher || { can_mark_attendance: true, can_view_student_details: true, can_print_reports: true, can_enter_results: false, can_edit_results: false },
  }, { omit: ['password', 'confirm_password', 'new_password'], signature: editSig });
  // Per-user OVERRIDES shown in the module selects. On add, seed from the role's
  // default modules. On edit, seed so the form displays the user's SAVED effective
  // access (permission_map) — not just own_permissions, which omits access derived
  // from the role/defaults and left the selects blank, forcing admins to re-pick
  // permissions they'd already set. Keys whose effective level the group already
  // grants stay blank (shown as "Inherit"), so we don't silently convert
  // group-inherited access into per-user overrides.
  const [perms, setPerms] = useState(() => {
    if (!edit) return moduleDefaults(d.role_defaults, u.role || 'teacher');
    const eff = u.permission_map || {};
    const grp = u.group_permissions || {};
    const seed = {};
    Object.keys(eff).forEach((k) => { if (eff[k] && eff[k] !== grp[k]) seed[k] = eff[k]; });
    // Keep any explicit overrides (e.g. a 'none' revoke) that don't surface in eff.
    Object.entries(u.own_permissions || {}).forEach(([k, v]) => { if (v && !(k in seed)) seed[k] = v; });
    return seed;
  });
  const groups = d.groups || [];
  const groupPerms = (groups.find((g) => String(g.id) === String(f.permission_group_id)) || {}).permissions || null;
  const [preset, setPreset] = useState('');

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const chk = (k) => (e) => setF({ ...f, [k]: e.target.checked });
  const setTeacher = (k) => (e) => setF({ ...f, teacher: { ...f.teacher, [k]: e.target.checked } });
  const setPerm = (key, val) => setPerms((p) => { const n = { ...p }; if (val) n[key] = val; else delete n[key]; return n; });

  const onRole = (e) => {
    const role = e.target.value;
    // Changing the role re-seeds whole-module access (capabilities/sub-parts kept).
    setF({ ...f, role });
    setPerms((p) => {
      const want = moduleDefaults(d.role_defaults, role);
      const next = {};
      Object.keys(p).forEach((k) => { if (k.includes('.')) next[k] = p[k]; });  // keep sub-parts/caps
      return { ...next, ...want };
    });
  };

  const applyPreset = (key) => {
    setPreset(key);
    const p = d.presets[key];
    if (!p) return;
    setF((cur) => ({
      ...cur, role: p.role, scope: p.scope === 'central' ? 'central' : 'branch',
      section: p.section || '', stream: p.stream || '',
      manage_scope: p.manage_scope || 'none', rank: p.rank || 0,
    }));
    setPerms((cur) => {
      const subs = {};
      Object.keys(cur).forEach((k) => { if (k.includes('.')) subs[k] = cur[k]; });
      if ((p.modules || []).length) {
        const want = {};
        p.modules.forEach((m) => { want[m] = 'edit'; });
        return { ...subs, ...want };
      }
      return { ...subs, ...moduleDefaults(d.role_defaults, p.role) };
    });
  };

  const showTeacher = f.role === 'teacher';
  const showModules = f.role !== 'admin';

  const submit = (e) => {
    e.preventDefault();
    const fields = {
      email: f.email, full_name: f.full_name, phone: f.phone,
      role: f.role, scope: f.scope, branch_id: f.branch_id,
      section: f.section, stream: f.stream,
      manage_scope: f.manage_scope, rank: f.rank,
    };
    if (edit) {
      if (f.new_password) fields.new_password = f.new_password;
      if (f.is_active) fields.is_active = 'on';
    } else {
      fields.username = f.username;
      fields.password = f.password;
      fields.confirm_password = f.confirm_password;
      if (f.require_pw_change) fields.require_pw_change = 'on';
    }
    if (f.view_only) fields.view_only = 'on';
    // Permission group (base) + per-user override selects (whole + sub-parts).
    if (showModules) {
      fields.permission_group_id = f.permission_group_id || '';
      Object.entries(perms).forEach(([k, v]) => { if (v) fields[`perm_${k}`] = v; });
    }
    // Teacher capability checkboxes.
    if (showTeacher) {
      ['can_mark_attendance', 'can_view_student_details', 'can_print_reports', 'can_enter_results', 'can_edit_results']
        .forEach((k) => { if (f.teacher[k]) fields[k] = 'on'; });
    }
    save(d.submit_url, fields, (r) => { clearDraft(); nav.go(r.redirect || d.back_url); });
  };

  const PermSelect = ({ pkey, ...rest }) => {
    const g = groupPerms ? groupPerms[pkey] : null;
    return (
      <select className="form-control perm-select" value={perms[pkey] || ''} onChange={(e) => setPerm(pkey, e.target.value)} {...rest}>
        {groupPerms
          ? <option value="">{g ? `Inherit (${g === 'edit' ? 'view & edit' : 'view'})` : 'Inherit (no access)'}</option>
          : <option value="">No access</option>}
        <option value="view">View only</option><option value="edit">View &amp; edit</option>
        {groupPerms && <option value="none">No access (revoke)</option>}
      </select>
    );
  };

  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className={`fas fa-user-${edit ? 'edit' : 'plus'}`} /> {edit ? 'Edit User' : 'Add New User'}</h1></div>
      <form onSubmit={submit}>
        <div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-user" /> Account Information</h3></div>
          <div className="card-body">
            <div className="form-row">
              <div className="form-group"><label className="form-label">Username {!edit && <span className="text-danger">*</span>}</label>
                {edit
                  ? <input type="text" className="form-control" value={f.username} disabled />
                  : <input type="text" className="form-control" value={f.username} onChange={set('username')} required pattern="[a-zA-Z0-9_]+" title="Letters, numbers, underscore only" placeholder="e.g., jdoe" />}</div>
              <div className="form-group"><label className="form-label">Email</label>
                <input type="email" className="form-control" value={f.email} onChange={set('email')} placeholder="email@example.com" /></div>
            </div>
            {!edit ? (
              <>
                <div className="form-row">
                  <div className="form-group"><label className="form-label">Password <span className="text-danger">*</span></label>
                    <input type="password" className="form-control" value={f.password} onChange={set('password')} required minLength="6" placeholder="Min 6 characters" /></div>
                  <div className="form-group"><label className="form-label">Confirm Password <span className="text-danger">*</span></label>
                    <input type="password" className="form-control" value={f.confirm_password} onChange={set('confirm_password')} required placeholder="Repeat password" /></div>
                </div>
                <label className="permission-item" style={{ display: 'inline-flex' }}>
                  <input type="checkbox" checked={f.require_pw_change} onChange={chk('require_pw_change')} /> <span>Require the user to change this password at first login</span></label>
              </>
            ) : null}
            <div className="form-row">
              <div className="form-group"><label className="form-label">Full Name</label>
                <input type="text" className="form-control" value={f.full_name} onChange={set('full_name')} placeholder="John Doe" /></div>
              <div className="form-group"><label className="form-label">Phone</label>
                <input type="tel" className="form-control" value={f.phone} onChange={set('phone')} placeholder="08012345678" /></div>
            </div>
            {edit && (
              <div className="form-group"><label className="form-label">New Password</label>
                <input type="password" className="form-control" value={f.new_password} onChange={set('new_password')} placeholder="Leave blank to keep current" minLength="6" /></div>
            )}
            <div className="form-group"><label className="form-label">Quick preset</label>
              <select className="form-control" value={preset} onChange={(e) => applyPreset(e.target.value)}>
                <option value="">— {edit ? 'Apply' : 'Choose'} a role preset (optional) —</option>
                {Object.entries(d.presets).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
              </select>
              {!edit && <small className="text-muted">{d.presets[preset]?.description || 'Pre-fills role, branch scope and module access — you can still tweak.'}</small>}
            </div>
            <div className="form-group"><label className="form-label">Role {!edit && <span className="text-danger">*</span>}</label>
              <select className="form-control" value={f.role} onChange={onRole}>
                <option value="teacher">Teacher</option><option value="staff">Staff (restricted)</option>
                <option value="admin">Admin</option><option value="readonly">View Only</option>
              </select></div>
            <div className="form-row">
              <div className="form-group"><label className="form-label">Branch scope</label>
                <select className="form-control" value={f.scope} onChange={set('scope')}>
                  <option value="branch">Single branch</option><option value="central">Central (all branches)</option>
                </select></div>
              {f.scope !== 'central' && (
                <div className="form-group"><label className="form-label">Branch</label>
                  <select className="form-control" value={f.branch_id} onChange={set('branch_id')}>
                    {d.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select></div>
              )}
            </div>
            <div className="form-row">
              <div className="form-group"><label className="form-label">Section <span className="text-muted">(optional)</span></label>
                <select className="form-control" value={f.section} onChange={set('section')}>
                  <option value="">All sections</option><option value="secondary">Secondary (JSS + SSS)</option><option value="primary">Nursery &amp; Primary</option>
                </select></div>
              <div className="form-group"><label className="form-label">Subject stream <span className="text-muted">(optional)</span></label>
                <select className="form-control" value={f.stream} onChange={set('stream')}>
                  <option value="">All streams</option><option value="arts">Arts &amp; Commercial</option><option value="science">Sciences</option>
                </select></div>
            </div>
            <div className="form-row">
              <div className="form-group"><label className="form-label">Can manage users</label>
                <select className="form-control" value={f.manage_scope} onChange={set('manage_scope')}>
                  <option value="none">No</option><option value="branch">Yes — their branch (lower ranks)</option><option value="central">Yes — all branches</option>
                </select></div>
              <div className="form-group"><label className="form-label">Rank <span className="text-muted">(authority level)</span></label>
                <input type="number" className="form-control" value={f.rank} onChange={set('rank')} min="0" max="100" /></div>
            </div>
            {edit && (
              <div className="form-group"><label className="toggle-label"><input type="checkbox" checked={f.is_active} onChange={chk('is_active')} /> <span>Account Active</span></label></div>
            )}
          </div>
        </div>

        {showTeacher && (
          <div className="card mb-3">
            <div className="card-header"><h3><i aria-hidden="true" className="fas fa-key" /> Teacher Permissions</h3></div>
            <div className="card-body">
              <div className="permission-grid">
                <label className="permission-item"><input type="checkbox" checked={f.teacher.can_mark_attendance} onChange={setTeacher('can_mark_attendance')} /> <span>Mark Attendance</span></label>
                <label className="permission-item"><input type="checkbox" checked={f.teacher.can_view_student_details} onChange={setTeacher('can_view_student_details')} /> <span>View Student Details</span></label>
                <label className="permission-item"><input type="checkbox" checked={f.teacher.can_print_reports} onChange={setTeacher('can_print_reports')} /> <span>Print Reports</span></label>
                <label className="permission-item"><input type="checkbox" checked={f.teacher.can_enter_results} onChange={setTeacher('can_enter_results')} /> <span>Enter Results</span></label>
                <label className="permission-item"><input type="checkbox" checked={f.teacher.can_edit_results} onChange={setTeacher('can_edit_results')} /> <span>Edit Results</span></label>
              </div>
              <p className="text-muted text-sm mt-2"><i aria-hidden="true" className="fas fa-info-circle" /> Teachers can only access classes and subjects assigned to them.</p>
            </div>
          </div>
        )}

        {showModules && (
          <div className="card mb-3">
            <div className="card-header"><h3><i aria-hidden="true" className="fas fa-th-large" /> Module Access</h3></div>
            <div className="card-body">
              {groups.length > 0 && (
                <div className="form-group">
                  <label className="form-label"><i aria-hidden="true" className="fas fa-layer-group" /> Permission group <span className="text-muted">(base template)</span></label>
                  <select className="form-control" value={f.permission_group_id} onChange={set('permission_group_id')}>
                    <option value="">— None (set each module individually) —</option>
                    {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                  <small className="text-muted">{groupPerms ? 'The group sets the baseline below; change any module to override it ("Revoke" removes a group grant).' : 'Optional: pick a group to grant a ready-made set of permissions.'}</small>
                </div>
              )}
              <div className="permission-grid">
                {d.modules.map((m) => {
                  const subs = d.subsections[m.key];
                  const isCap = d.cap_modules.includes(m.key);
                  return (
                    <div className="perm-block" key={m.key}>
                      <label className="permission-item perm-row"><span>{m.label}</span><PermSelect pkey={m.key} /></label>
                      {subs && (
                        <details className="perm-subs" open={isCap}>
                          <summary>{isCap ? <><i aria-hidden="true" className="fas fa-key" /> Special capabilities</> : `Detailed access (${subs.length} parts)`}</summary>
                          {subs.map((s) => {
                            const sk = `${m.key}.${s.sub}`;
                            const cap = d.capabilities.includes(sk);
                            return (
                              <label key={sk} className={`permission-item perm-row perm-sub ${cap ? 'perm-cap' : ''}`}>
                                <span>{cap ? <><i aria-hidden="true" className="fas fa-key" /> </> : '↳ '}{s.label}</span><PermSelect pkey={sk} />
                              </label>
                            );
                          })}
                        </details>
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="text-muted text-sm mt-2"><i aria-hidden="true" className="fas fa-info-circle" /> Choose each section's level — <strong>No access</strong>, <strong>View only</strong> or <strong>View &amp; edit</strong>. A part's level overrides the whole-module level. Admins always have full access.</p>
              <p className="text-muted text-sm mt-1"><i aria-hidden="true" className="fas fa-key" /> <strong>Special capabilities</strong> (e.g. <em>Generate Timetable</em>, <em>Generate Result Cards</em>) are extra powers not implied by module access — grant them explicitly under the module's expander.</p>
              <label className="permission-item mt-2" style={{ display: 'inline-flex' }}><input type="checkbox" checked={f.view_only} onChange={chk('view_only')} /> <span>View only — can browse but not create, edit or delete</span></label>
            </div>
          </div>
        )}

        <div className="d-flex gap-2">
          <button type="submit" className="btn btn-primary btn-lg"><i aria-hidden="true" className="fas fa-save" /> {edit ? 'Save Changes' : 'Create User'}</button>
          <A to={d.back_url} className="btn btn-secondary btn-lg">Cancel</A>
        </div>
      </form>
    </>
  );
}

// ---- View user --------------------------------------------------------------
function View({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const u = d.user;
  const reset = async () => {
    if (!await confirm("Reset this user's password to a temporary one? They will have to set a new password at next login.")) return;
    save(u.reset_password_url, {});
  };
  const removeAssign = (url, type) => save(url, { type, user_id: u.id }, () => nav.refresh());
  const perm = (active, label, icon) => (
    <div className={`perm ${active ? 'active' : ''}`}><i aria-hidden="true" className={`fas fa-${active ? icon : 'times'}`} /> {label}</div>
  );
  return (
    <>
      <div className="page-header">
        <div>
          <h1>{u.full_name || u.username}</h1>{' '}
          <span className={`badge badge-${u.role_badge}`}>{u.display_role}</span>{' '}
          <span className={`badge badge-${u.is_active ? 'success' : 'danger'}`}>{u.is_active ? 'Active' : 'Inactive'}</span>
        </div>
        <div className="page-header-actions">
          <A to={u.edit_url} className="btn btn-warning"><i aria-hidden="true" className="fas fa-edit" /> Edit</A>
          <button type="button" className="btn btn-secondary" onClick={reset}><i aria-hidden="true" className="fas fa-key" /> Reset Password</button>
          <A to={u.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A>
        </div>
      </div>
      <div className="row">
        <div className="col-md-6"><div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-user" /> Account Info</h3></div>
          <div className="card-body"><div className="info-grid">
            <div className="info-item"><span className="info-label">Username</span><span className="info-value">{u.username}</span></div>
            <div className="info-item"><span className="info-label">Email</span><span className="info-value">{u.email || 'Not set'}</span></div>
            <div className="info-item"><span className="info-label">Phone</span><span className="info-value">{u.phone || 'Not set'}</span></div>
            <div className="info-item"><span className="info-label">Last Login</span><span className="info-value">{u.last_login}</span></div>
            <div className="info-item"><span className="info-label">Created</span><span className="info-value">{u.created}</span></div>
          </div></div>
        </div></div>
        {u.teacher && (
          <div className="col-md-6"><div className="card mb-3">
            <div className="card-header"><h3><i aria-hidden="true" className="fas fa-key" /> Permissions</h3></div>
            <div className="card-body"><div className="permission-list">
              {perm(u.teacher.can_mark_attendance, 'Mark Attendance', 'check')}
              {perm(u.teacher.can_view_student_details, 'View Students', 'check')}
              {perm(u.teacher.can_print_reports, 'Print Reports', 'check')}
              {perm(u.teacher.can_enter_results, 'Enter Results', 'check')}
              {perm(u.teacher.can_edit_results, 'Edit Results', 'check')}
            </div></div>
          </div></div>
        )}
      </div>

      {u.module_access && (
        <div className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-th-large" /> Module Access</h3></div>
          <div className="card-body">
            {u.has_custom_modules ? (
              <div className="permission-list">
                {u.module_access.map((m) => (
                  <div key={m.key} className={`perm ${m.level ? 'active' : ''}`}>
                    <i aria-hidden="true" className={`fas fa-${m.level === 'edit' ? 'pen' : m.level === 'view' ? 'eye' : 'times'}`} /> {m.label}
                    {m.level && <span className="text-sm"> ({m.level === 'edit' ? 'edit' : 'view'})</span>}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted"><i aria-hidden="true" className="fas fa-info-circle" /> No custom modules set — using the default access for the <strong>{u.display_role}</strong> role.</p>
            )}
          </div>
        </div>
      )}

      {u.teacher && (
        <>
          <div className="card mb-3">
            <div className="card-header">
              <h3><i aria-hidden="true" className="fas fa-chalkboard-teacher" /> Class Assignments</h3>
              <A to={u.assign_class_url} className="btn btn-sm btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Assign</A>
            </div>
            <div className="card-body">
              {u.class_assignments.length ? (
                <div className="data-cards">{u.class_assignments.map((a) => (
                  <div className="data-card" key={a.id}>
                    <div className="data-card-header">
                      <div className="data-card-title">{a.name}</div>
                      {a.is_form_teacher && <span className="badge badge-success">Form Teacher</span>}
                    </div>
                    <div className="data-card-actions">
                      <button type="button" className="btn btn-sm btn-danger" onClick={async () => { if (await confirm('Remove?')) removeAssign(a.remove_url, 'class'); }}><i aria-hidden="true" className="fas fa-times" /></button>
                    </div>
                  </div>
                ))}</div>
              ) : <p className="text-muted">No class assignments</p>}
            </div>
          </div>
          <div className="card">
            <div className="card-header">
              <h3><i aria-hidden="true" className="fas fa-book" /> Subject Assignments</h3>
              <A to={u.assign_subject_url} className="btn btn-sm btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Assign</A>
            </div>
            <div className="card-body">
              {u.subject_assignments.length ? (
                <div className="data-cards">{u.subject_assignments.map((a) => (
                  <div className="data-card" key={a.id}>
                    <div className="data-card-header"><div className="data-card-title">{a.subject}</div></div>
                    <div className="data-card-row"><span className="data-card-label">Class</span><span>{a.class}</span></div>
                    <div className="data-card-actions">
                      <button type="button" className="btn btn-sm btn-danger" onClick={async () => { if (await confirm('Remove?')) removeAssign(a.remove_url, 'subject'); }}><i aria-hidden="true" className="fas fa-times" /></button>
                    </div>
                  </div>
                ))}</div>
              ) : <p className="text-muted">No subject assignments</p>}
            </div>
          </div>
        </>
      )}
    </>
  );
}

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
function Groups({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [editing, setEditing] = useState(null);
  const start = (g) => setEditing(g
    ? { id: g.id, name: g.name, description: g.description || '', branch_id: g.branch_id || '', permissions: { ...g.permissions }, edit_url: g.edit_url }
    : { id: null, name: '', description: '', branch_id: '', permissions: {} });
  const setField = (k, v) => setEditing((e) => ({ ...e, [k]: v }));
  const setPerm = (key, val) => setEditing((e) => { const p = { ...e.permissions }; if (val) p[key] = val; else delete p[key]; return { ...e, permissions: p }; });
  const submit = (ev) => {
    ev.preventDefault();
    if (!editing.name.trim()) { notify('error', 'Group name is required.'); return; }
    const fields = { name: editing.name, description: editing.description };
    if (d.can_pick_branch) fields.branch_id = editing.branch_id || '';
    Object.entries(editing.permissions).forEach(([k, v]) => { if (v) fields[`perm_${k}`] = v; });
    save(editing.id ? editing.edit_url : d.add_url, fields, (r) => { setEditing(null); nav.go(r.redirect || d.back_url); });
  };
  const del = (g) => { if (window.confirm(`Delete group "${g.name}"? Members keep their own permissions but lose this group's.`)) save(g.delete_url, {}, () => nav.refresh()); };
  const summary = (perms) => {
    const keys = Object.keys(perms);
    if (!keys.length) return <span className="text-muted">No modules</span>;
    return keys.map((k) => <span key={k} className="badge badge-secondary" style={{ marginRight: 4 }}>{(d.modules.find((m) => m.key === k) || {}).label || k}: {perms[k]}</span>);
  };
  return (
    <>
      <div className="page-header">
        <h1><i aria-hidden="true" className="fas fa-layer-group" /> Permission Groups</h1>
        <div className="page-header-actions">
          <A to={d.back_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Users</A>
          {!editing && <button type="button" className="btn btn-primary" onClick={() => start(null)}><i aria-hidden="true" className="fas fa-plus" /> New Group</button>}
        </div>
      </div>

      {editing && (
        <form onSubmit={submit} className="card mb-3">
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-edit" /> {editing.id ? 'Edit Group' : 'New Group'}</h3></div>
          <div className="card-body">
            <div className="form-row">
              <div className="form-group"><label className="form-label">Name <span className="text-danger">*</span></label>
                <input className="form-control" value={editing.name} onChange={(e) => setField('name', e.target.value)} required /></div>
              <div className="form-group"><label className="form-label">Description</label>
                <input className="form-control" value={editing.description} onChange={(e) => setField('description', e.target.value)} /></div>
            </div>
            {d.can_pick_branch && (
              <div className="form-group"><label className="form-label">Branch scope</label>
                <select className="form-control" value={editing.branch_id} onChange={(e) => setField('branch_id', e.target.value)}>
                  <option value="">All branches (central template)</option>
                  {d.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select></div>
            )}
            <label className="form-label mt-2">Module permissions</label>
            <div className="permission-grid">
              {d.modules.map((m) => (
                <label className="permission-item perm-row" key={m.key}><span>{m.label}</span>
                  <select className="form-control perm-select" value={editing.permissions[m.key] || ''} onChange={(e) => setPerm(m.key, e.target.value)}>
                    <option value="">No access</option><option value="view">View only</option><option value="edit">View &amp; edit</option>
                  </select>
                </label>
              ))}
            </div>
            <div className="d-flex gap-2 mt-3">
              <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> {editing.id ? 'Save Group' : 'Create Group'}</button>
              <button type="button" className="btn btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        </form>
      )}

      <div className="card">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-list" /> Groups ({d.groups.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.groups.length ? (
            <div className="table-responsive"><table className="data-table">
              <thead><tr><th>Name</th><th>Scope</th><th>Members</th><th>Permissions</th><th>Actions</th></tr></thead>
              <tbody>
                {d.groups.map((g) => (
                  <tr key={g.id}>
                    <td><strong>{g.name}</strong>{g.description && <div className="text-sm text-muted">{g.description}</div>}</td>
                    <td>{g.branch_name}</td>
                    <td>{g.user_count}</td>
                    <td>{summary(g.permissions)}</td>
                    <td><div className="d-flex gap-1">
                      {g.manageable ? (
                        <>
                          <button type="button" className="btn btn-sm btn-warning" title="Edit" onClick={() => start(g)}><i aria-hidden="true" className="fas fa-edit" /></button>
                          <button type="button" className="btn btn-sm btn-danger" title="Delete" onClick={() => del(g)}><i aria-hidden="true" className="fas fa-trash" /></button>
                        </>
                      ) : <span className="text-muted text-sm">Central</span>}
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : <Empty icon="fa-layer-group" title="No Groups">Create a group to grant a ready-made set of permissions to users.</Empty>}
        </div>
      </div>
    </>
  );
}

const SCREENS = {
  index: Index, matrix: Matrix, add: UserForm, edit: UserForm,
  view: View, assign_class: AssignClass, assign_subject: AssignSubject,
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
