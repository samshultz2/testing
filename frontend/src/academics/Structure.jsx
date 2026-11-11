// School structure — Classes and Arms. Classes are grouped by section with
// this term's arms, students and subjects; level problems that would break
// promotion are flagged. Arms show where they're used (classes × arms grid),
// with the "we use arms" switch. Add / edit happen in sheets; deletes warn
// when students would be affected.
import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useNav } from '../lib/section';
import { confirm } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Sheet, Blank, Menu, Tiles, usePhone } from '../subjects/results';
import { A, SecNav, Field, Toggle, Pill, plural } from '../components/appkit';

function StructNav({ d, active }) {
  const u = d.urls;
  return <SecNav label="School structure" active={active} items={[
    ['classes', 'fa-school', 'Classes', u.classes],
    ['arms', 'fa-code-branch', 'Arms', u.arms],
    ['assignments', 'fa-sitemap', 'Class setup', u.assignments],
  ]} />;
}

function useAct(notify) {
  const nav = useNav();
  return async (url, fields, ok) => {
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', ok || r.message); nav.refresh(); return true; }
    notify('error', r.error || 'That didn’t work.'); return false;
  };
}

const Alerts = ({ alerts }) => (alerts.length ? (
  <section className="rs-card rp-attn"><span className="k">Worth checking</span>
    <div className="tm-alerts">{alerts.map((a, i) => (
      <div key={i} className={'cm-attn-i ' + a.tone}><i className={'fas ' + a.icon} aria-hidden="true" /><span>{a.text}</span>
        {a.link && <A to={a.link} className="rs-btn sm primary">{a.link_label}</A>}</div>))}</div>
  </section>) : null);

// ============================================================================
// Classes
// ============================================================================
function ClassSheet({ d, edit, onClose, notify }) {
  const act = useAct(notify);
  const [f, setF] = useState(edit ? { name: edit.name, level: String(edit.level), section: edit.section_set ? edit.section : '', description: edit.description }
    : { name: '', level: String(d.next_level), section: '', description: '' });
  const [busy, setBusy] = useState(false);
  const clash = d.classes.filter((c) => String(c.level) === f.level && (!edit || c.id !== edit.id)).map((c) => c.name);
  const save = async () => {
    if (!f.name.trim() || !f.level) { notify('error', 'A name and a level are needed.'); return; }
    setBusy(true);
    const ok = await act(edit ? edit.edit_url : d.add_url, f, edit ? `${f.name.toUpperCase()} saved.` : `${f.name.toUpperCase()} added.`);
    setBusy(false); if (ok) onClose();
  };
  return (
    <Sheet title={edit ? `Edit ${edit.name}` : 'Add a class'} onClose={onClose}>
      <div className="su-form">
        <div className="cm-row2">
          <Field label="Name" grow><input type="text" placeholder="e.g. JSS1" value={f.name} autoFocus={!edit}
            onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Level"><input type="number" min="-10" max="20" value={f.level} style={{ width: 96 }}
            onChange={(e) => setF({ ...f, level: e.target.value })} /></Field>
        </div>
        <small className={clash.length ? 'su-err' : 'cm-mute'}>
          {clash.length ? `${clash.join(', ')} already ${clash.length === 1 ? 'uses' : 'use'} level ${f.level} — promotion moves students to the next level.`
            : 'Promotion moves students from one level to the next, so give each class its own level.'}</small>
        <Field label="Section"><select value={f.section} onChange={(e) => setF({ ...f, section: e.target.value })}>
          <option value="">Work it out from the name</option>
          {d.sections.filter((s) => s.key !== 'other').map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></Field>
        <Field label="Description (optional)"><input type="text" value={f.description} placeholder="e.g. Junior Secondary 1"
          onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <div className="su-form-f">
          <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={save}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {edit ? 'Save' : 'Add class'}</button>
        </div>
      </div>
    </Sheet>
  );
}

export function Classes({ d, notify }) {
  const act = useAct(notify);
  const [sheet, setSheet] = useState(null);
  const canAdd = canWrite(d, 'structure_create');
  const canEdit = canWrite(d, 'structure_edit');
  const canDel = canWrite(d, 'structure_delete');
  const t = d.totals;
  const del = async (c) => {
    const ok = await confirm({ title: `Delete ${c.name}?`, tone: 'danger', confirmText: 'Delete class',
      message: c.students ? `${plural(c.students, 'student')} are in ${c.name} this term. They stay enrolled, but ${c.name} won’t be offered for new terms.`
        : `${c.name} won’t be offered for new terms. Past records are kept.` });
    if (ok) act(c.delete_url, {}, `${c.name} deleted.`);
  };
  const groups = d.sections.map((s) => ({ ...s, rows: d.classes.filter((c) => c.section === s.key) })).filter((g) => g.rows.length);
  return (
    <div className="rs cm su tm st">
      <StructNav d={d} active="classes" />
      <Head icon="fa-school" title="Classes" sub={d.term ? `This term: ${d.term}` : 'No active term'}>
        {canAdd && <button type="button" className="rs-btn primary" onClick={() => setSheet({})}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> Add class</span></button>}
      </Head>
      {d.classes.length > 0 && <Tiles items={[
        { label: 'Classes', value: t.classes, sub: d.term ? `${t.opened} opened this term` : '' },
        { label: 'Students this term', value: t.students },
        { label: 'Arms in use', value: t.arms },
      ]} />}
      <Alerts alerts={d.alerts} />
      {canAdd && d.suggest.length > 0 && (
        <section className="rs-card st-quick"><span className="k">Quick add</span>
          <div className="st-chips">{d.suggest.map((s) => (
            <button key={s.name} type="button" className="st-chip" onClick={() => act(d.add_url, s, `${s.name} added.`)}>
              <i className="fas fa-plus" aria-hidden="true" /> {s.name}<small>level {s.level}</small></button>))}</div>
        </section>)}

      {!d.classes.length ? (
        <Blank icon="fa-school" title="No classes yet"><p>Add your classes (JSS1, SSS2…) — tap a quick-add chip above, or add your own.</p></Blank>
      ) : groups.map((g) => (
        <section key={g.key} className="rs-card su-group">
          <div className="su-group-h"><h3>{g.label}</h3><span className="su-count">{g.rows.length}</span></div>
          {g.rows.map((c) => (
            <div key={c.id} className={'st-row' + (c.opened ? '' : ' closed')}>
              <span className="st-lv" title="Level"><small>Lv</small>{c.level}</span>
              <div className="st-main"><b>{c.name}</b>
                <small>{c.description || (c.opened ? '' : 'Not opened this term')}</small>
                {c.arms.some((a) => !a.default) && <div className="st-arms">{c.arms.filter((a) => !a.default).map((a) => (
                  <span key={a.name}>{a.name}<b>{a.students}</b></span>))}</div>}
              </div>
              <div className="st-num"><b>{c.students}</b><small>students</small></div>
              <div className="st-num subj"><b>{c.subjects}</b><small>subjects</small></div>
              <div className="st-act">
                {(canEdit || canDel) && <Menu label={`More for ${c.name}`} items={[
                  canEdit && { icon: 'fa-pen', label: 'Edit', onClick: () => setSheet({ edit: c }) },
                  { icon: 'fa-sitemap', label: 'Class setup', href: d.urls.assignments },
                  canDel && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => del(c) },
                ]} />}
              </div>
            </div>))}
        </section>))}
      {sheet && <ClassSheet d={d} edit={sheet.edit} notify={notify} onClose={() => setSheet(null)} />}
    </div>
  );
}

// ============================================================================
// Arms
// ============================================================================
function ArmSheet({ d, edit, onClose, notify, onDelete }) {
  const act = useAct(notify);
  const [f, setF] = useState({ name: edit ? edit.name : '', description: edit ? edit.description : '' });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!f.name.trim()) { notify('error', 'Give the arm a name.'); return; }
    setBusy(true);
    const ok = await act(edit ? edit.edit_url : d.add_url, f, edit ? 'Arm saved.' : `Arm ${f.name} added.`);
    setBusy(false); if (ok) onClose();
  };
  return (
    <Sheet title={edit ? `Edit ${edit.name}` : 'Add an arm'} onClose={onClose}>
      <div className="su-form">
        <Field label="Name" hint="e.g. A, Gold, Science"><input type="text" value={f.name} autoFocus={!edit} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        {!edit && d.suggest.length > 0 && <div className="st-chips">{d.suggest.map((n) => (
          <button key={n} type="button" className={'st-chip' + (f.name === n ? ' on' : '')} onClick={() => setF({ ...f, name: n })}>{n}</button>))}</div>}
        <Field label="Description (optional)"><input type="text" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        {edit && edit.classes.length > 0 && <small className="cm-mute">Renaming updates {plural(edit.classes.length, 'class', 'classes')} that use it.</small>}
        <div className="su-form-f">
          {edit && onDelete && <button type="button" className="rs-btn ghost st-del" onClick={() => { onClose(); onDelete(edit); }}><i className="fas fa-trash" aria-hidden="true" /> Delete</button>}
          <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={save}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {edit ? 'Save' : 'Add arm'}</button>
        </div>
      </div>
    </Sheet>
  );
}

export function Arms({ d, notify }) {
  const act = useAct(notify);
  const phone = usePhone();
  const [sheet, setSheet] = useState(null);
  const canAdd = canWrite(d, 'structure_create');
  const canEdit = canWrite(d, 'structure_edit');
  const canDel = canWrite(d, 'structure_delete');
  const del = async (a) => {
    const ok = await confirm({ title: `Delete arm ${a.name}?`, tone: 'danger', confirmText: 'Delete arm',
      message: a.students ? `${a.classes.join(', ')} use ${a.name} this term (${plural(a.students, 'student')}). They keep their places, but ${a.name} won’t be offered for new terms.`
        : `${a.name} won’t be offered for new terms.` });
    if (ok) act(a.delete_url, {}, `Arm ${a.name} deleted.`);
  };
  const setUses = async (on) => {
    if (!on && !await confirm({ title: 'Turn off arms?', confirmText: 'Turn off',
      message: 'New terms will use one group per class. Existing arms and enrolments are kept.' })) return;
    act(d.uses_url, { uses_arms: on ? '1' : '0' }, on ? 'Arms turned on.' : 'Arms turned off.');
  };
  const used = d.grid.filter((g) => Object.keys(g.cells).length);
  const inUse = d.arms.filter((a) => a.classes.length);
  const idle = d.arms.filter((a) => !a.classes.length);
  const cols = inUse.length ? inUse : d.arms;
  const noArms = d.grid.length - used.length;
  return (
    <div className="rs cm su tm st">
      <StructNav d={d} active="arms" />
      <Head icon="fa-code-branch" title="Arms" sub="Streams inside a class — JSS1 Gold, JSS1 Silver…">
        {canAdd && d.uses_arms && <button type="button" className="rs-btn primary" onClick={() => setSheet({})}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> Add arm</span></button>}
      </Head>
      <section className="rs-card st-uses">
        <Toggle title="Our school splits classes into arms" sub={d.uses_arms ? 'Each class can have several arms, each with its own students and form teacher.'
          : 'Each class is one group. Turn on if you have JSS1 A, JSS1 B…'} on={d.uses_arms} disabled={!canEdit} onChange={setUses} />
      </section>

      {d.uses_arms && (!d.arms.length ? (
        <Blank icon="fa-code-branch" title="No arms yet"><p>Add arms like A and B, or Gold and Silver, then open them for each class in Class setup.</p>
          {canAdd && <button type="button" className="rs-btn primary" onClick={() => setSheet({})}><i className="fas fa-plus" aria-hidden="true" /> Add arm</button>}</Blank>
      ) : (
        <>
          <div className="st-armgrid">{inUse.map((a) => (
            <article key={a.id} className={'st-arm' + (a.classes.length ? '' : ' idle')}>
              <div className="st-arm-h"><span className="st-arm-ic">{a.name.slice(0, 2)}</span>
                <div className="st-arm-t"><b>{a.name}</b><small>{a.description || plural(a.classes.length, 'class', 'classes')}</small></div>
                {(canEdit || canDel) && <Menu label={`More for ${a.name}`} items={[
                  canEdit && { icon: 'fa-pen', label: 'Edit', onClick: () => setSheet({ edit: a }) },
                  canDel && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => del(a) },
                ]} />}
              </div>
              <div className="st-arm-f"><span><b>{a.students}</b> students</span>
                {a.classes.length ? <span className="st-arm-c">{a.classes.slice(0, 4).join(' · ')}{a.classes.length > 4 ? ` +${a.classes.length - 4}` : ''}</span>
                  : <Pill>Idle</Pill>}</div>
            </article>))}</div>
          {idle.length > 0 && (
            <section className="rs-card st-quick"><span className="k">Not used this term</span>
              <div className="st-chips">{idle.map((a) => (
                <button key={a.id} type="button" className="st-chip idle" disabled={!canEdit && !canDel}
                        onClick={() => setSheet({ edit: a })}>{a.name}{(canEdit || canDel) && <i className="fas fa-pen" aria-hidden="true" />}</button>))}</div>
              <small className="cm-mute">Open an arm for a class in Class setup, or tap one to rename or delete it.</small>
            </section>)}

          <section className="rs-card st-grid-c">
            <div className="rs-card-h"><h3>Who has which arm{d.term ? ` · ${d.term}` : ''}</h3>
              <A to={d.urls.assignments} className="cm-link">Open arms for a class <i className="fas fa-arrow-right" aria-hidden="true" /></A></div>
            {!used.length ? <p className="cm-mute">No class has arms opened this term yet.</p> : phone ? (
              <div className="st-plist">{used.map((g) => (
                <div key={g.id} className="st-prow"><b>{g.name}</b>
                  <div className="st-arms">{d.arms.filter((a) => g.cells[a.id]).map((a) => (
                    <A key={a.id} to={g.cells[a.id].url}>{a.name}<b>{g.cells[a.id].students}</b></A>))}</div></div>))}</div>
            ) : (
              <div className="st-tbl-w"><table className="st-tbl">
                <thead><tr><th>Class</th>{cols.map((a) => <th key={a.id}>{a.name}</th>)}<th>Total</th></tr></thead>
                <tbody>{used.map((g) => {
                  const tot = Object.values(g.cells).reduce((x, c) => x + c.students, 0);
                  return (
                    <tr key={g.id}><th>{g.name}</th>
                      {cols.map((a) => { const c = g.cells[a.id]; return (
                        <td key={a.id}>{c ? <A to={c.url} className="st-cell">{c.students}</A> : <span className="st-dash">–</span>}</td>); })}
                      <td className="st-tot">{tot || '–'}</td></tr>);
                })}</tbody>
              </table></div>)}
            {used.length > 0 && noArms > 0 && <small className="cm-mute">{plural(noArms, 'class', 'classes')} have no arms open this term.</small>}
          </section>
        </>))}
      {sheet && <ArmSheet d={d} edit={sheet.edit} notify={notify} onDelete={canDel ? del : null} onClose={() => setSheet(null)} />}
    </div>
  );
}
