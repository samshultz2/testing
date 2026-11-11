// Class setup — which classes and arms run this term, who teaches them and
// how many students each has. Laptop: class list on the left, the chosen class
// on the right (desktop-app master/detail). Phone: swipeable class chips over
// the panel. Decision helpers up top: unplaced students, classes not opened,
// arms without a class teacher; one-tap copy from last term.
import React, { useState, useMemo, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { useNav, navParams } from '../lib/section';
import { confirm } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Sheet, Blank, Menu, Tiles, usePhone } from '../subjects/results';
import { A, SecNav, Field, Toggle, Pill, plural } from '../components/appkit';

const HUES = ['#0f766e', '#2563eb', '#7c3aed', '#db2777', '#d97706', '#059669', '#4f46e5', '#0891b2'];
const hue = (s) => HUES[[...(s || '?')].reduce((a, c) => a + c.charCodeAt(0), 0) % HUES.length];

function useAct(notify) {
  const nav = useNav();
  return async (url, fields, ask) => {
    if (ask && !await confirm(ask)) return false;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); return true; }
    notify('error', r.error || 'That didn’t work.'); return false;
  };
}

const Gender = ({ b, g, total }) => (total ? (
  <div className="cs-g"><div className="rp-gender"><i className="m" style={{ flex: b || 0.0001 }} /><i className="f" style={{ flex: g || 0.0001 }} /></div>
    <span><i className="m" />{b} boys<i className="f" />{g} girls</span></div>) : null);

function TeacherSheet({ a, onClose, notify }) {
  const act = useAct(notify);
  const [f, setF] = useState({ form_teacher: a.form_teacher || '', form_teacher_phone: a.form_teacher_phone || '' });
  const [busy, setBusy] = useState(false);
  const save = async () => { setBusy(true); const ok = await act(a.edit_teacher_url, f); setBusy(false); if (ok) onClose(); };
  return (
    <Sheet title={`Class teacher · ${a.name}`} onClose={onClose}>
      <div className="su-form">
        <Field label="Name"><input type="text" value={f.form_teacher} autoFocus placeholder="e.g. Mrs Adeyemi" onChange={(e) => setF({ ...f, form_teacher: e.target.value })} /></Field>
        <Field label="Phone (optional)" hint="Shown on the roster so you can call them"><input type="tel" value={f.form_teacher_phone} onChange={(e) => setF({ ...f, form_teacher_phone: e.target.value })} /></Field>
        <div className="su-form-f">
          <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={save}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> Save</button>
        </div>
      </div>
    </Sheet>
  );
}

function AddArmsSheet({ d, cls, existing, onClose, notify }) {
  const act = useAct(notify);
  const free = (d.arms || []).filter((a) => !existing.includes(a.id));
  const [ids, setIds] = useState([]);
  const [teacher, setTeacher] = useState('');
  const [busy, setBusy] = useState(false);
  const toggle = (id) => setIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const save = async () => {
    if (!ids.length) { notify('error', 'Pick at least one arm.'); return; }
    setBusy(true);
    const ok = await act(d.add_url, { class_id: cls.id, form_teacher: teacher, arm_ids: ids, term_id: d.term_id });
    setBusy(false); if (ok) onClose();
  };
  return (
    <Sheet title={`Open arms for ${cls.name}`} onClose={onClose}>
      {!free.length ? (
        <div className="su-form"><p className="cm-mute">Every arm is already open for {cls.name}.</p>
          <A to={d.urls.arms} className="rs-btn primary">Create a new arm</A></div>
      ) : (
        <div className="su-form">
          <div className="cs-pick-h"><span className="k">Arms</span>
            <button type="button" className="cm-link" onClick={() => setIds(ids.length === free.length ? [] : free.map((a) => a.id))}>
              {ids.length === free.length ? 'Clear' : 'Select all'}</button></div>
          <div className="st-chips">{free.map((a) => (
            <button key={a.id} type="button" className={'st-chip' + (ids.includes(a.id) ? ' on' : '')} aria-pressed={ids.includes(a.id)} onClick={() => toggle(a.id)}>
              <span className="cs-dot" style={{ background: hue(a.name) }} />{a.name}{ids.includes(a.id) && <i className="fas fa-check" aria-hidden="true" />}</button>))}</div>
          <Field label="Class teacher (optional)" hint="Used for every arm you picked — change any of them later"><input type="text" value={teacher} onChange={(e) => setTeacher(e.target.value)} /></Field>
          <div className="su-form-f">
            <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="rs-btn primary" disabled={busy || !ids.length} onClick={save}>
              <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-plus')} aria-hidden="true" /> Open {ids.length || ''} arm{ids.length === 1 ? '' : 's'}</button>
          </div>
        </div>)}
    </Sheet>
  );
}

function ArmCard({ a, usesArms, canEdit, canDel, onTeacher, onDelete }) {
  const label = a.arm || a.name;
  return (
    <article className={'cs-arm' + (a.students ? '' : ' empty')}>
      <div className="cs-arm-h">
        <span className="cs-av" style={{ background: hue(label) }}>{usesArms && a.arm ? a.arm.slice(0, 2) : <i className="fas fa-chalkboard" aria-hidden="true" />}</span>
        <A to={a.view_url} className="cs-arm-t"><b>{a.name}</b><small>{a.students ? plural(a.students, 'student') : 'No students yet'}</small></A>
        {(canEdit || (canDel && !a.ever)) && <Menu label={`More for ${a.name}`} items={[
          canEdit && { icon: 'fa-chalkboard-user', label: a.form_teacher ? 'Change class teacher' : 'Set class teacher', onClick: onTeacher },
          { icon: 'fa-users', label: 'Open roster', href: a.view_url },
          canDel && !a.ever && { icon: 'fa-trash', label: 'Remove from this term', danger: true, onClick: onDelete },
        ]} />}
      </div>
      <Gender b={a.boys} g={a.girls} total={a.students} />
      <button type="button" className={'cs-teach' + (a.form_teacher ? '' : ' none')} onClick={canEdit ? onTeacher : undefined} disabled={!canEdit}>
        <i className="fas fa-chalkboard-user" aria-hidden="true" /><span>{a.form_teacher || 'No class teacher'}</span>
        {a.form_teacher_phone && <a href={'tel:' + a.form_teacher_phone} onClick={(e) => e.stopPropagation()} className="cm-ib" aria-label="Call class teacher"><i className="fas fa-phone" aria-hidden="true" /></a>}
        {canEdit && <i className="fas fa-pen cs-pen" aria-hidden="true" />}
      </button>
      <A to={a.view_url} className="rs-btn ghost sm cs-open"><i className="fas fa-users" aria-hidden="true" /> {a.students ? 'Open roster' : 'Add students'}</A>
    </article>
  );
}

export default function ClassSetup({ d, notify }) {
  const nav = useNav();
  const act = useAct(notify);
  const phone = usePhone();
  const usesArms = d.uses_arms;
  const byClass = useMemo(() => {
    const m = {};
    (d.assignments || []).forEach((a) => { (m[a.class_id] = m[a.class_id] || []).push(a); });
    Object.values(m).forEach((l) => l.sort((x, y) => (x.arm || '').localeCompare(y.arm || '')));
    return m;
  }, [d.assignments]);
  const classes = d.classes || [];
  const [tab, setTabState] = useState(() => {
    const h = (window.location.hash || '').match(/^#class-(\d+)$/);
    const id = h ? Number(h[1]) : null;
    if (id && classes.some((c) => c.id === id)) return id;
    return ((classes.find((c) => byClass[c.id]) || classes[0]) || {}).id;
  });
  const setTab = (id) => { setTabState(id); try { window.history.replaceState(null, '', '#class-' + id); } catch (e) { /* ignore */ } };
  const chipsRef = useRef(null);
  useEffect(() => { const el = chipsRef.current && chipsRef.current.querySelector('.on'); if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', inline: 'center' }); }, [tab]);
  const [sheet, setSheet] = useState(null);
  const canAdd = canWrite(d, 'structure_create');
  const canEdit = canWrite(d, 'structure_edit');
  const canDel = canWrite(d, 'structure_delete');
  const canBulk = canWrite(d, 'structure_bulk');
  const cls = classes.find((c) => c.id === tab);
  const arms = byClass[tab] || [];
  const all = d.assignments || [];
  const tot = all.reduce((t, a) => ({ s: t.s + a.students, noT: t.noT + (a.form_teacher ? 0 : 1), empty: t.empty + (a.students ? 0 : 1) }), { s: 0, noT: 0, empty: 0 });
  const ct = arms.reduce((t, a) => ({ s: t.s + a.students, b: t.b + a.boys, g: t.g + a.girls }), { s: 0, b: 0, g: 0 });
  const missing = classes.filter((c) => !byClass[c.id]);
  const prev = d.prev_term;

  const toggleArms = async (on) => {
    if (!on && !await confirm({ title: 'Turn off arms?', confirmText: 'Turn off', message: 'New classes will be one group each. Existing arms and students are kept.' })) return;
    act(d.toggle_url, { uses_arms: on ? '1' : '0' });
  };
  const copyPrev = () => act(d.urls.copy, { from_term_id: prev.id, to_term_id: d.term_id, copy_enrollments: 'on' }, {
    title: `Copy classes from ${prev.name}?`, confirmText: 'Copy',
    message: `Opens the same ${plural(prev.classes, 'class', 'classes')} and arms for ${d.selected_term.name} and puts each student back in their class. Students already placed this term keep their class.` });
  const delArm = (a) => act(a.delete_url, {}, { title: `Remove ${a.name} from this term?`, tone: 'danger', confirmText: 'Remove', message: 'It has never had students, so nothing is lost.' });

  const alerts = [
    d.unplaced > 0 && all.length > 0 && { tone: 'mid', icon: 'fa-user-slash', text: `${plural(d.unplaced, 'student')} not in any class this term — they won’t appear on registers or score sheets.`, link: d.urls.students, label: 'Students' },
    tot.noT > 0 && { tone: 'info', icon: 'fa-chalkboard-user', text: `${plural(tot.noT, usesArms ? 'arm' : 'class', usesArms ? 'arms' : 'classes')} without a class teacher.` },
    tot.empty > 0 && { tone: 'info', icon: 'fa-chair', text: `${plural(tot.empty, usesArms ? 'arm has' : 'class has', usesArms ? 'arms have' : 'classes have')} no students yet.` },
  ].filter(Boolean);

  return (
    <div className="rs cm su tm st cs">
      <SecNav label="School structure" active="assignments" items={[
        ['classes', 'fa-school', 'Classes', d.urls.classes], ['arms', 'fa-code-branch', 'Arms', d.urls.arms], ['assignments', 'fa-sitemap', 'Class setup', d.urls.assignments]]} />
      <Head icon="fa-sitemap" title="Class setup" sub={d.selected_term ? `Who is in which class for ${d.selected_term.name}` : 'Choose a term'}>
        <select className="cm-sel" value={d.term_id} aria-label="Term" onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value })}>
          <option value="">Choose a term…</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select>
      </Head>

      {!d.selected_term ? <Blank icon="fa-calendar" title="Pick a term"><p>Choose the term whose classes you want to set up.</p></Blank> : (<>
        <Tiles items={[
          { label: 'Classes open', value: classes.length - missing.length, unit: `/${classes.length}`, tone: missing.length ? 'mid' : 'good' },
          usesArms && { label: 'Arms', value: all.length },
          { label: 'Students placed', value: tot.s, sub: d.unplaced ? `${d.unplaced} not placed` : 'everyone placed', tone: d.unplaced ? 'mid' : '' },
          { label: 'No class teacher', value: tot.noT, tone: tot.noT ? 'mid' : 'good' },
        ].filter(Boolean)} />

        {!all.length && prev && canBulk && (
          <section className="rs-card cs-start">
            <span className="cs-start-ic"><i className="fas fa-copy" aria-hidden="true" /></span>
            <div><b>Start from {prev.name}</b><small>Open the same {plural(prev.classes, 'class', 'classes')} and put every student back in their class — then adjust.</small></div>
            <button type="button" className="rs-btn primary" onClick={copyPrev}><i className="fas fa-copy" aria-hidden="true" /> Copy classes & students</button>
          </section>)}
        {!usesArms && missing.length > 0 && canBulk && (
          <section className="rs-card cs-start">
            <span className="cs-start-ic"><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /></span>
            <div><b>{plural(missing.length, 'class', 'classes')} not open this term</b><small>Open them all at once to start placing students.</small></div>
            <button type="button" className="rs-btn primary" onClick={() => act(d.setup_url, { term_id: d.term_id })}>Open all</button>
          </section>)}

        {alerts.length > 0 && (
          <section className="rs-card rp-attn"><span className="k">Worth checking</span>
            <div className="tm-alerts">{alerts.map((a, i) => (
              <div key={i} className={'cm-attn-i ' + a.tone}><i className={'fas ' + a.icon} aria-hidden="true" /><span>{a.text}</span>
                {a.link && <A to={a.link} className="rs-btn sm ghost">{a.label}</A>}</div>))}</div>
          </section>)}

        <div className="cs-wrap">
          {phone ? (
            <nav className="cs-chips" ref={chipsRef} role="tablist" aria-label="Classes">{classes.map((c) => {
              const l = byClass[c.id] || []; const n = l.reduce((t, a) => t + a.students, 0);
              return (
                <button key={c.id} type="button" role="tab" aria-selected={tab === c.id} className={(tab === c.id ? 'on' : '') + (l.length ? '' : ' unset')} onClick={() => setTab(c.id)}>
                  <b>{c.name}</b><small>{l.length ? (usesArms ? `${l.length} arm${l.length === 1 ? '' : 's'} · ${n}` : `${n} students`) : 'Not open'}</small></button>);
            })}</nav>
          ) : (
            <nav className="rs-card cs-rail" role="tablist" aria-label="Classes">{classes.map((c) => {
              const l = byClass[c.id] || []; const n = l.reduce((t, a) => t + a.students, 0);
              const warn = l.some((a) => !a.form_teacher || !a.students);
              return (
                <button key={c.id} type="button" role="tab" aria-selected={tab === c.id} className={(tab === c.id ? 'on' : '') + (l.length ? '' : ' unset')} onClick={() => setTab(c.id)}>
                  <span className={'cs-st ' + (!l.length ? 'off' : warn ? 'mid' : 'ok')} aria-hidden="true" />
                  <span className="cs-rail-t"><b>{c.name}</b><small>{l.length ? (usesArms ? `${plural(l.length, 'arm')}` : 'Open') : 'Not open'}</small></span>
                  <span className="cs-rail-n">{l.length ? n : '–'}</span>
                </button>);
            })}
              {canEdit && <div className="cs-rail-f"><Toggle title="Uses arms" sub={usesArms ? 'JSS1 Gold, JSS1 Silver…' : 'One group per class'} on={usesArms} onChange={toggleArms} /></div>}
            </nav>)}

          {cls && (
            <section className="rs-card cs-panel" role="tabpanel">
              <div className="cs-panel-h">
                <div><h2>{cls.name}</h2>
                  <small>{arms.length ? `${usesArms ? `${plural(arms.length, 'arm')} · ` : ''}${plural(ct.s, 'student')}` : `Not open for ${d.selected_term.name}`}</small></div>
                {arms.length > 0 && <Gender b={ct.b} g={ct.g} total={ct.s} />}
                {canAdd && usesArms && arms.length > 0 && <button type="button" className="rs-btn primary" onClick={() => setSheet({ add: true })}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> Open arms</span></button>}
              </div>
              {arms.length ? (
                <div className="cs-arms">{arms.map((a) => (
                  <ArmCard key={a.id} a={a} usesArms={usesArms} canEdit={canEdit} canDel={canDel}
                           onTeacher={() => setSheet({ teacher: a })} onDelete={() => delArm(a)} />))}</div>
              ) : (
                <Blank icon="fa-door-closed" title={`${cls.name} isn’t open this term`}>
                  <p>{usesArms ? 'Open one or more arms, then add students to each.' : 'Open it to start adding students.'}</p>
                  {canAdd && (usesArms
                    ? <button type="button" className="rs-btn primary" onClick={() => setSheet({ add: true })}><i className="fas fa-plus" aria-hidden="true" /> Open arms for {cls.name}</button>
                    : <button type="button" className="rs-btn primary" onClick={() => act(d.add_url, { class_id: cls.id, form_teacher: '', arm_ids: [], term_id: d.term_id })}><i className="fas fa-plus" aria-hidden="true" /> Open {cls.name}</button>)}
                </Blank>)}
              {phone && canEdit && <div className="cs-phone-arms"><Toggle title="Uses arms" sub={usesArms ? 'Classes split into arms' : 'One group per class'} on={usesArms} onChange={toggleArms} /></div>}
            </section>)}
        </div>
      </>)}
      {sheet && sheet.add && cls && <AddArmsSheet d={d} cls={cls} existing={arms.map((a) => a.arm_id)} notify={notify} onClose={() => setSheet(null)} />}
      {sheet && sheet.teacher && <TeacherSheet a={sheet.teacher} notify={notify} onClose={() => setSheet(null)} />}
    </div>
  );
}
