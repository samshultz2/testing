import React, { useState, useMemo, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, PageHeader, Empty, SectionShell, SuccessBanner } from '../components/ui';
import { canWrite } from '../lib/perms';



// ---- Shared bits for the promotion / graduation screens (pm-*) -------------
function useMedia(query) {
  const get = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false);
  const [m, setM] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const on = () => setM(mq.matches);
    on();
    if (mq.addEventListener) mq.addEventListener('change', on); else mq.addListener(on);
    return () => { if (mq.removeEventListener) mq.removeEventListener('change', on); else mq.removeListener(on); };
  }, [query]);
  return m;
}
const usePhone = () => useMedia('(max-width: 759px)');
const pmInitials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';

function PmHead({ icon, kicker, title, sub, back, actions }) {
  return (
    <header className="pm-head">
      {back && <a href={back} className="pm-back" aria-label="Back"><i aria-hidden="true" className="fas fa-arrow-left" /></a>}
      {icon && <span className="pm-logo" aria-hidden="true"><i className={'fas ' + icon} /></span>}
      <div className="pm-head-t">
        {kicker && <span className="pm-kick">{kicker}</span>}
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {actions && <div className="pm-head-a">{actions}</div>}
    </header>
  );
}
function PmTiles({ items }) {
  return (
    <div className="pm-tiles">
      {items.filter(Boolean).map((t, i) => {
        const Tag = t.onClick ? 'button' : (t.href ? 'a' : 'div');
        return (
          <Tag key={i} href={t.href} type={t.onClick ? 'button' : undefined} onClick={t.onClick}
               aria-pressed={t.onClick ? !!t.on : undefined}
               className={'pm-tile' + (t.tone ? ' ' + t.tone : '') + (t.onClick || t.href ? ' click' : '') + (t.on ? ' on' : '')}>
            <span className="l">{t.icon && <i aria-hidden="true" className={'fas ' + t.icon} />}{t.label}</span>
            <span className="v">{t.value}</span>
            {t.sub && <span className="s">{t.sub}</span>}
          </Tag>
        );
      })}
    </div>
  );
}
function PmSeg({ options, value, onChange, label, small }) {
  return (
    <div className={'pm-seg' + (small ? ' sm' : '')} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value}
                className={(o.value === value ? 'on ' : '') + (o.tone || '')} onClick={() => onChange(o.value)}>
          {o.icon && <i aria-hidden="true" className={'fas ' + o.icon} />}{o.label}
        </button>
      ))}
    </div>
  );
}
function PmMenu({ items, label = 'More', icon = 'fa-ellipsis', text, up }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close); document.addEventListener('touchstart', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('touchstart', close); };
  }, [open]);
  const list = items.filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="pm-menu" ref={ref}>
      <button type="button" className="pm-btn" aria-haspopup="true" aria-expanded={open} aria-label={label} title={label} onClick={() => setOpen((v) => !v)}>
        <i aria-hidden="true" className={'fas ' + icon} />{text && <span>{text}</span>}</button>
      {open && (
        <div className={'pm-menu-pop' + (up ? ' up' : '')} role="menu">
          {list.map((it, i) => (it.href
            ? <a key={i} role="menuitem" href={it.href} onClick={() => setOpen(false)}>
                <i aria-hidden="true" className={'fas ' + it.icon} /> <span>{it.label}</span>{it.badge ? <b className="pm-menu-n">{it.badge}</b> : null}</a>
            : <button key={i} type="button" role="menuitem" onClick={() => { setOpen(false); it.onClick(); }}>
                <i aria-hidden="true" className={'fas ' + it.icon} /> <span>{it.label}</span></button>))}
        </div>
      )}
    </div>
  );
}
// Sticky bar at the bottom of the work area on laptops; fixed above the bottom
// nav on phones (portalled so it isn't trapped under the nav's stacking layer).
function PmBar({ phone, children }) {
  const bar = <div className={'pm-bar' + (phone ? ' fixed' : '')}>{children}</div>;
  return phone ? createPortal(bar, document.body) : bar;
}
function PmSheet({ title, onClose, children }) {
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', esc);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', esc); document.body.style.overflow = prev; };
  }, []);
  return createPortal(
    <div className="pm-sheet-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="pm-sheet" role="dialog" aria-modal="true" aria-label={title}>
        <div className="pm-grip" aria-hidden="true" />
        <div className="pm-sheet-h"><strong>{title}</strong>
          <button type="button" className="pm-x" onClick={onClose} aria-label="Close"><i aria-hidden="true" className="fas fa-xmark" /></button></div>
        {children}
      </div>
    </div>, document.body);
}

// ---- Index: the promotion & graduation hub --------------------------------
function Index({ d }) {
  const steps = [
    { key: 'rules', icon: 'fa-sliders', title: 'Promotion rules', desc: 'Pass mark, next class and streams', stat: `${d.rules_count} active` },
    { key: 'process', icon: 'fa-arrow-up-right-dots', title: 'Promote students', desc: 'Review each class and move them up', stat: 'Start here', primary: true },
    { key: 'preview', icon: 'fa-user-graduate', title: 'Graduate SSS3', desc: 'Pick the leavers and the graduation date', stat: 'Batch' },
    { key: 'graduates', icon: 'fa-graduation-cap', title: 'Graduates', desc: 'Records, documents and alumni', stat: d.graduates_count != null ? `${d.graduates_count} graduates` : '' },
  ];
  return (
    <div className="pm">
      <PmHead icon="fa-stairs" kicker={d.active_session ? `Active session · ${d.active_session}` : 'No active session'}
              title="Promotion & graduation" sub="Move every class up at the end of the session, then graduate the leavers." />
      <ol className="pm-steps">
        {steps.map((st, i) => d.urls[st.key] && (
          <li key={st.key}>
            <a href={d.urls[st.key]} className={'pm-step' + (st.primary ? ' primary' : '')}>
              <span className="pm-step-n">{i + 1}</span>
              <span className="pm-step-ic"><i aria-hidden="true" className={'fas ' + st.icon} /></span>
              <span className="pm-step-t"><strong>{st.title}</strong><small>{st.desc}</small></span>
              {st.stat && <span className="pm-step-s">{st.stat}</span>}
              <i aria-hidden="true" className="fas fa-chevron-right pm-chev" />
            </a>
          </li>
        ))}
      </ol>

      <section className="pm-card">
        <header className="pm-card-h">
          <span className="pm-card-ic"><i aria-hidden="true" className="fas fa-clock-rotate-left" /></span>
          <div className="pm-card-t"><h3>Recent promotions</h3><small>{d.promotions_count ? `${d.promotions_count} recorded in total` : 'Nothing recorded yet'}</small></div>
          {d.urls.history && <a href={d.urls.history} className="pm-btn"><span>Full history</span> <i aria-hidden="true" className="fas fa-arrow-right" /></a>}
        </header>
        {d.recent.length ? (
          <ul className="pm-people">
            {d.recent.map((p, i) => (
              <li key={i} className="pm-person">
                <span className="pm-av" aria-hidden="true">{pmInitials(p.name)}</span>
                <span className="pm-pn"><strong>{p.name}</strong>
                  <small>{p.from_class} <i aria-hidden="true" className="fas fa-arrow-right" /> {p.to_class}{p.stream ? ` · ${p.stream}` : ''}</small></span>
                <span className={'badge ' + p.status_badge}>{p.status}</span>
              </li>
            ))}
          </ul>
        ) : <p className="pm-empty">Promotions you save will show up here.</p>}
      </section>
    </div>
  );
}

// ---- Rules -----------------------------------------------------------------
function Rules({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const canEdit = canWrite(d, 'promote_rules');
  const del = async (r) => {
    if (!await confirm(`Delete the rule ${r.from_class} → ${r.to_class}${r.stream_name ? ' (' + r.stream_name + ')' : ''}?`)) return;
    setBusy(true);
    const res = await submitJson(r.delete_url, {});
    setBusy(false);
    if (res.ok) nav.refresh(); else notify('error', res.error || 'Could not delete.');
  };
  // Group the rules by the class they promote FROM, in class order, so the page
  // reads as the school's promotion ladder.
  const classes = d.classes && d.classes.length ? d.classes
    : [...new Map(d.rules.map((r) => [r.from_class_id, { id: r.from_class_id, name: r.from_class }])).values()];
  const byClass = {};
  d.rules.forEach((r) => { (byClass[r.from_class_id] = byClass[r.from_class_id] || []).push(r); });
  Object.values(byClass).forEach((l) => l.sort((x, y) => y.priority - x.priority));
  const covered = classes.filter((c) => byClass[c.id]).length;
  const streamed = d.rules.filter((r) => r.stream_name).length;

  return (
    <div className="pm">
      <PmHead back={(d.urls && d.urls.index) || '/promotion/'} kicker="Promotion & graduation" title="Promotion rules"
              sub="Where each class goes next, and what a student needs to get there."
              actions={canEdit ? <a href={d.add_url} className="pm-btn primary"><i aria-hidden="true" className="fas fa-plus" /> <span>Add rule</span></a> : null} />

      <PmTiles items={[
        { label: 'Rules', icon: 'fa-sliders', value: d.rules.length, sub: 'active' },
        { label: 'Classes covered', icon: 'fa-school', value: `${covered}/${classes.length}`, sub: covered < classes.length ? 'others use the pass mark' : 'every class', tone: covered ? 'good' : '' },
        { label: 'Stream rules', icon: 'fa-code-branch', value: streamed, sub: 'Science, Arts…' },
        d.threshold != null ? { label: 'Default pass mark', icon: 'fa-percent', value: `${d.threshold}%`, sub: 'when no rule matches' } : null,
      ]} />

      <div className="pm-rules">
        <ol className="pm-ladder">
          {classes.map((c) => {
            const list = byClass[c.id] || [];
            return (
              <li key={c.id} className={'pm-rung' + (list.length ? '' : ' none')}>
                <div className="pm-rung-h">
                  <span className="pm-rung-c">{c.name}</span>
                  <span className="pm-rung-n">{list.length ? `${list.length} rule${list.length === 1 ? '' : 's'}` : `Pass mark ${d.threshold != null ? d.threshold + '%' : ''} · no rule`}</span>
                </div>
                {list.length > 0 && (
                  <ul className="pm-rule-list">
                    {list.map((r, i) => (
                      <li key={r.id} className="pm-rule">
                        <span className="pm-rule-p" title="Checked in this order — higher priority first">{i + 1}</span>
                        <div className="pm-rule-b">
                          <div className="pm-rule-t">
                            <strong>{r.from_class} <i aria-hidden="true" className="fas fa-arrow-right" /> {r.to_class}</strong>
                            {r.stream_name ? <span className="pm-tag">{r.stream_name}</span> : <span className="pm-tag plain">Basic</span>}
                          </div>
                          <div className="pm-rule-m">
                            <span><i aria-hidden="true" className="fas fa-percent" /> Average ≥ <b>{r.min_average}%</b></span>
                            <span><i aria-hidden="true" className="fas fa-sort-amount-up" /> Priority <b>{r.priority}</b></span>
                          </div>
                          {(r.required || []).length > 0 ? (
                            <div className="pm-rule-s">{r.required.map((nm) => <span key={nm}>{nm}</span>)}</div>
                          ) : r.required_count > 0 ? <small className="pm-dim">{r.required_count} required subjects</small> : null}
                        </div>
                        {canEdit && <button type="button" className="pm-icon danger" disabled={busy} onClick={() => del(r)} aria-label="Delete rule" title="Delete rule">
                          <i aria-hidden="true" className="fas fa-trash-can" /></button>}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
          {classes.length === 0 && <p className="pm-empty">No classes set up yet.</p>}
        </ol>

        <aside className="pm-card pm-help">
          <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-circle-info" /></span>
            <div className="pm-card-t"><h3>How rules work</h3></div></header>
          <ol className="pm-howto">
            <li><b>No rule?</b> Students at or above the pass mark{d.threshold != null ? ` (${d.threshold}%)` : ''} go up to the next class.</li>
            <li><b>Basic rule</b> — set where a class goes and the average it needs.</li>
            <li><b>Stream rules</b> (e.g. SSS1 → SSS2 Science) — add the subjects whose average must meet the minimum.</li>
            <li>Rules are checked <b>highest priority first</b>; the first one a student meets is recommended.</li>
          </ol>
          {d.urls && d.urls.process && <a href={d.urls.process} className="pm-btn wide"><i aria-hidden="true" className="fas fa-arrow-up-right-dots" /> Go to Promote students</a>}
        </aside>
      </div>
    </div>
  );
}

// ---- Add rule --------------------------------------------------------------
function AddRule({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ from_class_id: '', to_class_id: '', stream_name: '', min_average: '50', priority: '0' });
  const [subjects, setSubjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.from_class_id || !f.to_class_id) { notify('error', 'Pick both classes.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, 'required_subjects[]': subjects });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const toggleSubj = (id) => setSubjects((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const phone = usePhone();
  const cname = (id) => (d.classes.find((c) => String(c.id) === String(id)) || {}).name;
  // When "from" is picked, suggest the next class up as "to".
  const pickFrom = (id) => {
    const i = d.classes.findIndex((c) => String(c.id) === String(id));
    setF((s) => ({ ...s, from_class_id: id, to_class_id: s.to_class_id || (d.classes[i + 1] ? String(d.classes[i + 1].id) : '') }));
  };
  const chips = (value, onPick, label) => (
    <div className="pm-chips" role="radiogroup" aria-label={label}>
      {d.classes.map((c) => (
        <button key={c.id} type="button" role="radio" aria-checked={String(c.id) === String(value)}
                className={String(c.id) === String(value) ? 'on' : ''} onClick={() => onPick(String(c.id))}>{c.name}</button>))}
    </div>
  );
  return (
    <form onSubmit={submit} className="pm" id="pm-rule-form">
      <PmHead back={d.urls.rules} kicker="Promotion rules" title="New rule"
              sub={f.from_class_id && f.to_class_id ? `${cname(f.from_class_id)} → ${cname(f.to_class_id)}${f.stream_name ? ' · ' + f.stream_name : ''} · average ≥ ${f.min_average}%` : 'Pick where students move from and to.'} />

      <section className="pm-pick">
        <span className="pm-pick-l">1 · From class</span>{chips(f.from_class_id, pickFrom, 'From class')}
        <span className="pm-pick-l">2 · Goes up to</span>{chips(f.to_class_id, (id) => set('to_class_id', id), 'To class')}
      </section>

      <section className="pm-pick">
        <span className="pm-pick-l">3 · Requirements</span>
        <div className="pm-req">
          <label className="pm-field"><span>Stream (optional)</span>
            <input type="text" className="pm-input" placeholder="e.g. Science, Arts — blank for basic" value={f.stream_name} onChange={(e) => set('stream_name', e.target.value)} /></label>
          <label className="pm-field"><span>Minimum average</span>
            <span className="pm-num"><input type="number" min="0" max="100" step="0.5" value={f.min_average} onChange={(e) => set('min_average', e.target.value)} />%</span></label>
          <label className="pm-field"><span>Priority <small>(higher first)</small></span>
            <span className="pm-num"><input type="number" min="0" max="10" value={f.priority} onChange={(e) => set('priority', e.target.value)} /></span></label>
        </div>
      </section>

      <section className="pm-pick">
        <div className="pm-pick-row"><span className="pm-pick-l">4 · Required subjects <small className="pm-dim">— their average must meet the minimum</small></span>
          {d.subjects.length > 0 && <button type="button" className="pm-link" onClick={() => setSubjects(subjects.length ? [] : d.subjects.map((x) => String(x.id)))}>{subjects.length ? `Clear (${subjects.length})` : 'Select all'}</button>}</div>
        {d.subjects.length ? (
          <div className="pm-chips wrap" role="group" aria-label="Required subjects">
            {d.subjects.map((x) => {
              const id = String(x.id);
              return <button key={x.id} type="button" aria-pressed={subjects.includes(id)} className={subjects.includes(id) ? 'on' : ''} onClick={() => toggleSubj(id)}>
                {subjects.includes(id) && <i aria-hidden="true" className="fas fa-check" />} {x.name}</button>;
            })}
          </div>
        ) : <p className="pm-dim">No subjects set up yet.</p>}
      </section>

      {(() => {
        const bar = (
          <div className={'pm-formbar' + (phone ? ' fixed' : '')}>
            <a href={d.urls.rules} className="pm-btn">Cancel</a>
            <button type="submit" form="pm-rule-form" className="pm-btn primary big" disabled={busy}><i aria-hidden="true" className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} /> Save rule</button>
          </div>);
        return phone ? createPortal(bar, document.body) : bar;
      })()}
    </form>
  );
}

// ---- Process ---------------------------------------------------------------
// Streams (class arms) available for a destination class, falling back to the
// global stream list when a class has no arms configured yet.
function streamsForClass(d, classId) {
  const byClass = (d.class_streams && d.class_streams[String(classId)]) || [];
  return byClass.length ? byClass : (d.streams || []);
}

function Process({ d, notify }) {
  const nav = useNav();
  const defaultClass = d.classes[0] ? String(d.classes[0].id) : '';
  const [rows, setRows] = useState(() => d.students.map((s) => ({
    id: s.id, action: s.recommendation.status === 'graduated' ? 'graduated'
      : (s.recommendation.status === 'promote' ? 'promoted' : (s.recommendation.status === 'repeat' ? 'repeated' : 'skip')),
    to_class_id: s.recommendation.to_class ? String(s.recommendation.to_class) : defaultClass,
    stream: s.recommendation.stream || '', average: s.average,
    isGrad: s.recommendation.status === 'graduated',
  })));
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);               // milestone summary, shown briefly before the log
  const [sel, setSel] = useState(() => new Set());      // selected student ids
  const [bulk, setBulk] = useState({ action: 'promoted', to_class_id: defaultClass, stream: '' });
  const phone = usePhone();
  const [filter, setFilter] = useState('');
  const [q, setQ] = useState('');
  const [selMode, setSelMode] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const setRow = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  // Only non-graduating rows can be bulk-promoted to a class/stream.
  const selectableIds = rows.filter((r) => !r.isGrad).map((r) => r.id);
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => sel.has(id));
  const toggleAll = () => setSel(allSelected ? new Set() : new Set(selectableIds));

  const applyBulk = () => {
    if (!sel.size) { notify('error', 'Select at least one student first.'); return; }
    setRows((rs) => rs.map((r) => (sel.has(r.id) && !r.isGrad ? {
      ...r, action: bulk.action,
      to_class_id: bulk.action === 'promoted' ? (bulk.to_class_id || r.to_class_id) : r.to_class_id,
      stream: bulk.action === 'promoted' && bulk.stream !== '' ? bulk.stream : r.stream,
    } : r)));
  };
  // Quick path for "just this one student" (or a handful): tick their box(es),
  // then this zeroes every other row to Skip in one click instead of having
  // to flip each remaining row's dropdown by hand.
  const skipUnselected = () => {
    if (!sel.size) { notify('error', 'Select at least one student first.'); return; }
    setRows((rs) => rs.map((r) => (sel.has(r.id) || r.isGrad ? r : { ...r, action: 'skip' })));
  };

  const submit = async () => {
    setBusy(true);
    const fields = { from_session_id: d.from_session_id, to_session_id: d.to_session_id,
      class_id: d.class_id, arm_id: d.arm_id,
      'student_id[]': rows.map((r) => r.id), 'average[]': rows.map((r) => r.average ?? ''),
      'action[]': rows.map((r) => r.action), 'to_class_id[]': rows.map((r) => r.to_class_id || ''),
      'stream[]': rows.map((r) => r.stream) };
    const res = await submitJson(d.execute_url, fields);
    if (res.ok) {
      // Celebrate the milestone with a summary of what just happened, then
      // continue to the promotion log. Keep `busy` so the button stays locked.
      const c = rows.reduce((a, r) => { a[r.action] = (a[r.action] || 0) + 1; return a; }, {});
      const parts = [];
      if (c.promoted) parts.push(`${c.promoted} promoted`);
      if (c.repeated) parts.push(`${c.repeated} repeating`);
      if (c.graduated) parts.push(`${c.graduated} graduating`);
      if (c.skip) parts.push(`${c.skip} skipped`);
      setDone(parts.join(' · ') || `${rows.length} students processed`);
      setTimeout(() => nav.go(res.redirect), 1700);
    } else { setBusy(false); notify('error', res.error || 'Could not save promotions.'); }
  };

  const bulkStreams = streamsForClass(d, bulk.to_class_id);
  const go = (patch) => navParams(nav.go, d.urls.self, { from_session_id: d.from_session_id, to_session_id: d.to_session_id,
    class_id: d.class_id, arm_id: d.arm_id, ...patch });
  const sum = rows.reduce((acc, r) => { acc[r.action] = (acc[r.action] || 0) + 1; return acc; }, {});
  const canSave = canWrite(d, 'promote_execute');
  const term = q.trim().toLowerCase();
  const visible = d.students.map((st, i) => [st, i]).filter(([st, i]) =>
    (!filter || rows[i].action === filter) && (!term || `${st.name} ${st.student_no || ''} ${st.assignment}`.toLowerCase().includes(term)));
  const className = (id) => (d.classes.find((c) => String(c.id) === String(id)) || {}).name || '';
  const ready = d.from_session_id && d.class_id;

  return (
    <div className={'pm' + (phone && d.students.length && canSave ? ' has-bar' : '')}>
      {done && <SuccessBanner title="Promotions saved" summary={`${done} — opening the promotion log…`} />}
      <PmHead back="/promotion/" kicker={`Pass mark ${d.threshold}%`} title="Promote students"
              sub={ready ? `${d.selected_class_name}${d.arm_id ? ' · ' + ((d.arm_options || []).find((x) => String(x.id) === String(d.arm_id)) || {}).name : ''} — rows are pre-filled with the recommended action.` : 'Choose the sessions and a class to begin.'} />

      <section className="pm-pick">
        <div className="pm-sessions">
          <label className="pm-field"><span>From session</span>
            <select value={d.from_session_id} onChange={(e) => go({ from_session_id: e.target.value })}>
              <option value="">Choose…</option>{d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
          <i aria-hidden="true" className="fas fa-arrow-right pm-arrow" />
          <label className="pm-field"><span>To session</span>
            <select value={d.to_session_id} onChange={(e) => go({ to_session_id: e.target.value })}>
              <option value="">Choose…</option>{d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        </div>
        <span className="pm-pick-l">Class</span>
        <div className="pm-chips" role="radiogroup" aria-label="Class">
          {d.classes.map((c) => (
            <button key={c.id} type="button" role="radio" aria-checked={String(c.id) === String(d.class_id)}
                    className={String(c.id) === String(d.class_id) ? 'on' : ''} onClick={() => go({ class_id: c.id, arm_id: '' })}>{c.name}</button>))}
        </div>
        {d.class_id && (d.arm_options || []).length > 1 && (<>
          <span className="pm-pick-l">Arm</span>
          <div className="pm-chips" role="radiogroup" aria-label="Arm">
            <button type="button" role="radio" aria-checked={!d.arm_id} className={!d.arm_id ? 'on' : ''} onClick={() => go({ arm_id: '' })}>All arms</button>
            {d.arm_options.map((x) => (
              <button key={x.id} type="button" role="radio" aria-checked={String(x.id) === String(d.arm_id)}
                      className={String(x.id) === String(d.arm_id) ? 'on' : ''} onClick={() => go({ arm_id: x.id })}>{x.name}</button>))}
          </div>
        </>)}
      </section>

      {d.students.length ? (<>
        <PmTiles items={[
          { label: 'All', value: d.students.length, sub: 'students', onClick: () => setFilter(''), on: !filter },
          { label: 'Promote', icon: 'fa-arrow-up', value: sum.promoted || 0, tone: 'good', onClick: () => setFilter('promoted'), on: filter === 'promoted' },
          { label: 'Repeat', icon: 'fa-rotate-left', value: sum.repeated || 0, tone: 'warn', onClick: () => setFilter('repeated'), on: filter === 'repeated' },
          sum.graduated ? { label: 'Graduate', icon: 'fa-user-graduate', value: sum.graduated, tone: 'info', onClick: () => setFilter('graduated'), on: filter === 'graduated' } : null,
          { label: 'Skip', icon: 'fa-forward', value: sum.skip || 0, onClick: () => setFilter('skip'), on: filter === 'skip' },
        ]} />

        <section className="pm-card">
          <header className="pm-card-h">
            <div className="pm-search"><i aria-hidden="true" className="fas fa-search" />
              <input type="search" placeholder="Search students…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search students" /></div>
            {selMode
              ? <button type="button" className="pm-btn" onClick={() => { setSelMode(false); setSel(new Set()); }}>Done</button>
              : <button type="button" className="pm-btn" onClick={() => setSelMode(true)}><i aria-hidden="true" className="fas fa-check-square" /> <span>Select</span></button>}
          </header>
          {selMode && (
            <div className="pm-selbar">
              <label><input type="checkbox" checked={allSelected} onChange={toggleAll} /> {sel.size ? `${sel.size} selected` : 'Select all'}</label>
              <button type="button" className="pm-btn primary" disabled={!sel.size} onClick={() => setBulkOpen(true)}>
                <i aria-hidden="true" className="fas fa-wand-magic-sparkles" /> Change selected</button>
            </div>
          )}
          {visible.length === 0 ? <p className="pm-empty">No students match.</p> : (
            <ul className="pm-rows">
              {visible.map(([st, i]) => {
                const r = rows[i];
                const rowStreams = streamsForClass(d, r.to_class_id);
                const opts = r.stream && !rowStreams.includes(r.stream) ? [r.stream, ...rowStreams] : rowStreams;
                return (
                  <li key={st.id} className={'pm-row act-' + r.action + (sel.has(st.id) ? ' sel' : '')}>
                    <div className="pm-row-who">
                      {selMode && !r.isGrad
                        ? <input type="checkbox" checked={sel.has(st.id)} onChange={() => toggle(st.id)} aria-label={'Select ' + st.name} />
                        : <span className="pm-av" data-g={st.gender || ''} aria-hidden="true">{pmInitials(st.name)}</span>}
                      <span className="pm-pn"><strong>{st.name}</strong>
                        <small>{st.assignment}{st.existing_status ? ` · already ${st.existing_status}` : ''}</small></span>
                      {st.average != null
                        ? <span className={'pm-avg ' + (st.over_threshold ? 'good' : 'bad')} title="Third-term average">{st.average}%</span>
                        : <span className="pm-avg none">No scores</span>}
                    </div>
                    {st.recommendation.message && !/^no scores?$/i.test(st.recommendation.message.trim()) && (
                      <p className="pm-rec"><i aria-hidden="true" className="fas fa-lightbulb" /> {st.recommendation.message}</p>)}
                    <div className="pm-row-do">
                      <PmSeg small label={`Action for ${st.name}`} value={r.action} onChange={(v) => setRow(i, 'action', v)}
                             options={r.isGrad
                               ? [{ value: 'graduated', label: 'Graduate', icon: 'fa-user-graduate', tone: 'info' }, { value: 'skip', label: 'Skip' }]
                               : [{ value: 'promoted', label: 'Promote', icon: 'fa-arrow-up', tone: 'good' },
                                  { value: 'repeated', label: 'Repeat', icon: 'fa-rotate-left', tone: 'warn' },
                                  { value: 'skip', label: 'Skip' }]} />
                      {!r.isGrad && r.action === 'promoted' && (
                        <span className="pm-to">
                          <label className="pm-mini"><span>To</span>
                            <select value={r.to_class_id} onChange={(e) => setRow(i, 'to_class_id', e.target.value)} aria-label={`Promote ${st.name} to`}>
                              {d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
                          <label className="pm-mini"><span>Stream</span>
                            <select value={r.stream} onChange={(e) => setRow(i, 'stream', e.target.value)} aria-label={`Stream for ${st.name}`}>
                              <option value="">None</option>{opts.map((nm) => <option key={nm} value={nm}>{nm}</option>)}</select></label>
                        </span>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {canSave && (
            <PmBar phone={phone}>
              <span className="pm-bar-sum">
                {sum.promoted ? <b className="good">{sum.promoted} up</b> : null}
                {sum.repeated ? <b className="warn">{sum.repeated} repeat</b> : null}
                {sum.graduated ? <b className="info">{sum.graduated} graduate</b> : null}
                {sum.skip ? <b>{sum.skip} skip</b> : null}
              </span>
              <button type="button" className="pm-btn primary big" disabled={busy} onClick={submit}>
                <i aria-hidden="true" className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} /> Save promotions</button>
            </PmBar>
          )}
        </section>
      </>) : (
        <section className="pm-card"><div className="pm-card-b">
          {ready
            ? <Empty icon="fa-users" title="No students"><p>No students found for {d.selected_class_name} in the selected session’s Third Term.</p></Empty>
            : <Empty icon="fa-hand-pointer" title="Pick a class"><p>Choose the session you’re promoting from and a class — every student loads with the recommended action.</p></Empty>}
        </div></section>
      )}

      {bulkOpen && (
        <PmSheet title={`Change ${sel.size} selected`} onClose={() => setBulkOpen(false)}>
          <span className="form-label">Action</span>
          <PmSeg label="Bulk action" value={bulk.action} onChange={(v) => setBulk((b) => ({ ...b, action: v }))}
                 options={[{ value: 'promoted', label: 'Promote', icon: 'fa-arrow-up' }, { value: 'repeated', label: 'Repeat', icon: 'fa-rotate-left' }, { value: 'skip', label: 'Skip' }]} />
          {bulk.action === 'promoted' && (
            <div className="pm-two">
              <label className="pm-field"><span>Promote to</span>
                <select value={bulk.to_class_id} onChange={(e) => setBulk((b) => ({ ...b, to_class_id: e.target.value, stream: '' }))}>
                  {d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
              <label className="pm-field"><span>Stream</span>
                <select value={bulk.stream} onChange={(e) => setBulk((b) => ({ ...b, stream: e.target.value }))}>
                  <option value="">No change</option>{bulkStreams.map((nm) => <option key={nm} value={nm}>{nm}</option>)}</select></label>
            </div>
          )}
          <button type="button" className="pm-btn primary big wide" onClick={() => { applyBulk(); setBulkOpen(false); }}>
            Apply to {sel.size} student{sel.size === 1 ? '' : 's'}{bulk.action === 'promoted' ? ` → ${className(bulk.to_class_id)}` : ''}</button>
          <button type="button" className="pm-btn wide" onClick={() => { skipUnselected(); setBulkOpen(false); }}
                  title="Keep the selected students and skip everyone else">
            <i aria-hidden="true" className="fas fa-user-check" /> Only process these {sel.size} — skip everyone else</button>
        </PmSheet>
      )}
    </div>
  );
}

// Graduate lifecycle status -> status-dot tone. Keeps the status column
// scannable (everything was a flat "info" badge before) without needing a
// backend change.
const GRAD_STATUS_TONE = {
  'Graduation Pending': 'warning',
  'Graduated': 'info',
  'Certificate Issued': 'primary',
  'Alumni Active': 'success',
  'Transcript Requested': 'warning',
  'Transcript Issued': 'primary',
  'Employment Verification Completed': 'success',
  'Further Education Recorded': 'success',
  'Alumni Ambassador': 'success',
  'Deceased': 'secondary',
};
function gradInitials(name) {
  const parts = (name || '').split(' ').filter(Boolean);
  if (!parts.length) return '—';
  return ((parts[0][0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

// Photo when available, falling back to an initials tile (and back to
// initials again if the photo URL 404s) — same pattern as the Students list.
function GradAvatar({ name, photo }) {
  const [broken, setBroken] = useState(false);
  return (photo && !broken)
    ? <span className="grad-av"><img src={photo} alt="" loading="lazy" onError={() => setBroken(true)} /></span>
    : <span className="grad-av" aria-hidden="true">{gradInitials(name)}</span>;
}

// ---- Graduates -------------------------------------------------------------
function Graduates({ d }) {
  const nav = useNav();
  const phone = usePhone();
  const docTypes = d.doc_types || [];
  const [bulkType, setBulkType] = useState(docTypes.length ? docTypes[0].type : '');
  const [q, setQ] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [missingOnly, setMissingOnly] = useState(false);
  const males = d.graduates.filter((g) => g.gender === 'Male').length;
  const females = d.graduates.filter((g) => g.gender === 'Female').length;
  const isMissing = (g) => !g.has_waec && !g.has_neco && !g.has_jamb;
  const noResults = d.graduates.filter(isMissing).length;
  const hasFilters = !!(d.session_id || d.status);
  // Live search + client-side sort over the loaded graduates — matches name,
  // student ID, session or status.
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    let list = !t ? d.graduates.slice() : d.graduates.filter((g) => (
      `${g.full_name} ${g.student_id} ${g.graduation_session || ''} ${g.status || ''}`
    ).toLowerCase().includes(t));
    if (missingOnly) list = list.filter(isMissing);
    if (sortBy === 'name_desc') list.sort((x, y) => y.full_name.localeCompare(x.full_name));
    else if (sortBy === 'status') list.sort((x, y) => (x.status || '').localeCompare(y.status || ''));
    else list.sort((x, y) => x.full_name.localeCompare(y.full_name));
    return list;
  }, [q, d.graduates, sortBy, missingOnly]);
  const bulkHref = d.bulk_url && bulkType
    ? `${d.bulk_url}?doc_type=${encodeURIComponent(bulkType)}${d.session_id ? `&session_id=${d.session_id}` : ''}${d.status ? `&status=${encodeURIComponent(d.status)}` : ''}`
    : null;
  const clearFilters = () => { setMissingOnly(false); navParams(nav.go, window.location.pathname, {}); };
  const canBatch = canWrite(d, 'graduates_sss3');
  const canBulk = canWrite(d, 'documents_bulk_generate') && docTypes.length > 0 && d.bulk_url;
  const res = (on, label) => <span className={'grad-res' + (on ? ' on' : '')}><i aria-hidden="true" className={'fas fa-' + (on ? 'circle-check' : 'circle')} /> {label}</span>;

  return (
    <div className="pm">
      <PmHead back="/promotion/" kicker="Promotion & graduation" title="Graduates"
              sub="Every student who has left — their results, documents and alumni status."
              actions={<>
                {canBatch && !phone && <a href={d.preview_url} className="pm-btn primary"><i aria-hidden="true" className="fas fa-user-graduate" /> <span>Batch graduate</span></a>}
                <PmMenu label="More" items={[
                  d.alumni_url && { href: d.alumni_url, icon: 'fa-address-book', label: 'Alumni directory', badge: d.pending_requests || null },
                  d.compare_url && { href: d.compare_url, icon: 'fa-chart-column', label: 'Compare with SSS3' },
                  d.doc_templates_url && { href: d.doc_templates_url, icon: 'fa-swatchbook', label: 'Document designs' },
                  d.verifications_url && { href: d.verifications_url, icon: 'fa-shield-halved', label: 'Verifications' },
                ]} />
              </>} />

      <PmTiles items={[
        { label: 'Graduates', icon: 'fa-graduation-cap', value: d.graduates.length, sub: d.session_id ? 'in this session' : 'all sessions' },
        { label: 'Male', icon: 'fa-mars', value: males },
        { label: 'Female', icon: 'fa-venus', value: females },
        { label: 'No results yet', icon: 'fa-file-circle-question', value: noResults, tone: noResults ? 'warn' : 'good',
          sub: noResults ? (missingOnly ? 'showing these only' : 'tap to show them') : 'all uploaded',
          onClick: noResults ? () => setMissingOnly((v) => !v) : undefined, on: missingOnly },
        d.pending_requests > 0 && d.alumni_url ? { label: 'Document requests', icon: 'fa-inbox', value: d.pending_requests, tone: 'warn', href: d.alumni_url, sub: 'waiting' } : null,
      ]} />

      <section className="pm-card">
        <header className="pm-card-h wrap">
          <div className="pm-search"><i aria-hidden="true" className="fas fa-search" />
            <input type="search" placeholder="Name, student ID, session or status…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search graduates" /></div>
          <label className="pm-mini"><span>Session</span>
            <select value={d.session_id} onChange={(e) => navParams(nav.go, window.location.pathname, { session_id: e.target.value, status: d.status || '' })}>
              <option value="">All</option>{d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
          <label className="pm-mini"><span>Status</span>
            <select value={d.status || ''} onChange={(e) => navParams(nav.go, window.location.pathname, { session_id: d.session_id || '', status: e.target.value })}>
              <option value="">All</option>{(d.statuses || []).map((x) => <option key={x} value={x}>{x}</option>)}</select></label>
          <label className="pm-mini"><span>Sort</span>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="name">A–Z</option><option value="name_desc">Z–A</option><option value="status">Status</option></select></label>
          {(hasFilters || missingOnly) && <button type="button" className="pm-btn" onClick={clearFilters}><i aria-hidden="true" className="fas fa-rotate-left" /> <span>Clear</span></button>}
        </header>
        {canBulk && d.graduates.length > 0 && (
          <div className="pm-bulkdoc">
            <i aria-hidden="true" className="fas fa-file-zipper" />
            <span>Issue a document to everyone listed:</span>
            <select value={bulkType} onChange={(e) => setBulkType(e.target.value)} aria-label="Document type">
              {docTypes.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}</select>
            <a href={bulkHref} className="pm-btn" data-native="1">Bulk issue</a>
          </div>
        )}
        {!d.graduates.length ? (
          <div className="pm-card-b"><Empty icon="fa-graduation-cap" title="No graduates">
            <p>{hasFilters ? 'No graduates match the current filters.' : 'No students have been marked as graduated yet.'}</p>
            {hasFilters ? <div className="empty-state-actions"><button type="button" className="btn btn-secondary" onClick={clearFilters}><i aria-hidden="true" className="fas fa-rotate-left" /> Clear filters</button></div>
              : canBatch && <div className="empty-state-actions"><a href={d.preview_url} className="btn btn-primary"><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate this year’s SSS3</a></div>}
          </Empty></div>
        ) : shown.length === 0 ? <p className="pm-empty">No graduates match{q ? ` “${q}”` : ''}.</p> : (
          <ul className="pm-grads">
            {shown.map((g) => {
              const tone = GRAD_STATUS_TONE[g.status] || 'info';
              return (
                <li key={g.id}>
                  <a href={g.profile_url} className="pm-grad">
                    <GradAvatar name={g.full_name} photo={g.photo_url} />
                    <span className="pm-pn"><strong>{g.full_name}</strong>
                      <small>{g.student_id}{g.graduation_session ? ` · ${g.graduation_session}` : ''}{g.graduation_date ? ` · ${g.graduation_date}` : ''}</small></span>
                    <span className={'grad-status tone-' + tone}><span className="dot" aria-hidden="true" />{g.status || 'Graduated'}</span>
                    <span className="pm-res">{res(g.has_waec, 'WAEC')}{res(g.has_neco, 'NECO')}{res(g.has_jamb, 'JAMB')}</span>
                    <i aria-hidden="true" className="fas fa-chevron-right pm-chev" />
                  </a>
                </li>
              );
            })}
          </ul>
        )}
        {shown.length > 0 && <p className="pm-foot">{shown.length}{shown.length !== d.graduates.length ? ` of ${d.graduates.length}` : ''} graduate{shown.length === 1 ? '' : 's'}</p>}
      </section>

      {canBatch && phone && createPortal(
        <a href={d.preview_url} className="pm-fab"><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate</a>, document.body)}
    </div>
  );
}

// ---- Batch graduation ------------------------------------------------------
// Pick the session, tick the SSS3 students to graduate and choose the
// graduation date: the last day of that session, or the day it's processed.
function GraduatePreview({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState(() => new Set(d.students.map((s) => s.id)));
  const [mode, setMode] = useState(d.session_end ? 'session_end' : 'today');
  const [q, setQ] = useState('');
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? d.students.filter((s) => (s.full_name + ' ' + s.student_id).toLowerCase().includes(t)) : d.students;
  }, [q, d.students]);
  const allShownPicked = shown.length > 0 && shown.every((s) => picked.has(s.id));
  const toggle = (id) => setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleShown = () => setPicked((p) => {
    const n = new Set(p);
    shown.forEach((s) => (allShownPicked ? n.delete(s.id) : n.add(s.id)));
    return n;
  });
  const dateLabel = mode === 'session_end' ? d.session_end_label : d.today_label;
  const doGraduate = async () => {
    const ids = d.students.filter((s) => picked.has(s.id)).map((s) => s.id);
    if (!ids.length) { notify('error', 'Tick at least one student to graduate.'); return; }
    if (!await confirm(`Graduate ${ids.length} SSS3 student(s) of ${d.session ? d.session.name : 'this session'}? Their graduation date will be ${dateLabel}.`)) return;
    setBusy(true);
    const r = await submitJson(d.confirm_url, { session_id: d.session && d.session.id, date_mode: mode, student_ids: ids });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not graduate students.');
  };
  const pickSession = (e) => nav.go(d.preview_url + '?session_id=' + encodeURIComponent(e.target.value));
  const canGrad = canWrite(d, 'graduates_sss3');
  const boys = d.students.filter((s) => s.gender === 'Male' && picked.has(s.id)).length;
  const girls = d.students.filter((s) => s.gender === 'Female' && picked.has(s.id)).length;

  return (
    <div className={'pm' + (phone && d.students.length && canGrad ? ' has-bar' : '')}>
      <PmHead back={d.urls.graduates} kicker="Graduates" title="Graduate SSS3"
              sub="Choose the session, the graduation date, and who is leaving." />

      <div className="pm-gp-top">
        <section className="pm-pick">
          <span className="pm-pick-l">1 · SSS3 class of</span>
          <label className="pm-field big"><select value={d.session ? d.session.id : ''} onChange={pickSession} aria-label="Session">
            {d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
          <div className="pm-gp-facts">
            <span><b>{d.students.length}</b> not yet graduated</span>
            {d.already_count > 0 && <span><b>{d.already_count}</b> already graduated</span>}
          </div>
        </section>
        <section className="pm-pick">
          <span className="pm-pick-l">2 · Graduation date</span>
          <div className="pm-dates" role="radiogroup" aria-label="Graduation date">
            <button type="button" role="radio" aria-checked={mode === 'session_end'} disabled={!d.session_end}
                    className={'pm-date' + (mode === 'session_end' ? ' on' : '')} onClick={() => setMode('session_end')}>
              <i aria-hidden="true" className="fas fa-flag-checkered" />
              <span><strong>End of {d.session ? d.session.name : 'session'}</strong>
                <small>{d.session_end ? d.session_end_label : 'No end date set'}</small></span>
            </button>
            <button type="button" role="radio" aria-checked={mode === 'today'}
                    className={'pm-date' + (mode === 'today' ? ' on' : '')} onClick={() => setMode('today')}>
              <i aria-hidden="true" className="fas fa-calendar-day" />
              <span><strong>Today</strong><small>{d.today_label}</small></span>
            </button>
          </div>
          {!d.session_end && <p className="pm-hint">No end date for this session — <a href={d.urls.sessions}>set it under Sessions</a> to use it.</p>}
        </section>
      </div>

      <section className="pm-card">
        <header className="pm-card-h wrap">
          <div className="pm-card-t"><h3>3 · Who is graduating?</h3><small>Tap a student to leave them out</small></div>
          {d.students.length > 0 && <>
            <div className="pm-search"><i aria-hidden="true" className="fas fa-search" />
              <input type="search" placeholder="Search name or ID" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search students" /></div>
            <button type="button" className="pm-btn" onClick={toggleShown}>{allShownPicked ? 'Untick all' : 'Tick all'}</button>
          </>}
        </header>
        {d.students.length ? (
          <ul className="pm-pickl">
            {shown.map((st) => (
              <li key={st.id}>
                <label className={'pm-pickrow' + (picked.has(st.id) ? ' on' : '')}>
                  <input type="checkbox" checked={picked.has(st.id)} onChange={() => toggle(st.id)} aria-label={'Graduate ' + st.full_name} />
                  <span className="pm-av" data-g={st.gender || ''} aria-hidden="true">{pmInitials(st.full_name)}</span>
                  <span className="pm-pn"><strong>{st.full_name}</strong><small>{st.student_id}{st.gender ? ' · ' + st.gender : ''}</small></span>
                  <span className="pm-tick" aria-hidden="true"><i className={'fas ' + (picked.has(st.id) ? 'fa-circle-check' : 'fa-circle')} /></span>
                </label>
              </li>))}
            {shown.length === 0 && <p className="pm-empty">No student matches “{q}”.</p>}
          </ul>
        ) : (
          <div className="pm-card-b"><Empty icon="fa-circle-check" title="Nobody left to graduate">
            <p>No SSS3 students to graduate for {d.session ? d.session.name : 'this session'} — they’re all graduated already, or no SSS3 class is set up for it.</p>
            <div className="empty-state-actions"><a href={d.urls.graduates} className="btn btn-secondary">See graduates</a></div>
          </Empty></div>
        )}
        {canGrad && d.students.length > 0 && (
          <PmBar phone={phone}>
            <span className="pm-bar-sum"><b>{picked.size}</b> of {d.students.length}<small> · {boys} boys · {girls} girls · {dateLabel}</small></span>
            <button type="button" className="pm-btn primary big" disabled={busy || picked.size === 0} onClick={doGraduate}>
              <i aria-hidden="true" className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-user-graduate')} /> Graduate {picked.size}</button>
          </PmBar>
        )}
      </section>
    </div>
  );
}

// ---- Graduate profile ------------------------------------------------------
const NGN = (n) => '₦' + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });

// Compact label/value pair for the profile rail (null when there's nothing to show).
const GpKV = ({ label, value }) => (value || value === 0) ? (
  <div className="gp-kv"><div className="k">{label}</div><div className="v">{value}</div></div>
) : null;

const ALUMNI_FIELD_ICONS = {
  occupation: 'fa-briefcase', job_title: 'fa-id-badge', employer: 'fa-building',
  higher_institution: 'fa-school', course_of_study: 'fa-book', phone: 'fa-phone',
  email: 'fa-envelope', linkedin_url: 'fa-link', city: 'fa-location-dot', country: 'fa-flag',
};

const WAEC_GRADE_BADGE = {
  A1: 'badge-success', B2: 'badge-success', B3: 'badge-success',
  C4: 'badge-warning', C5: 'badge-warning', C6: 'badge-warning',
  D7: 'badge-danger', E8: 'badge-danger', F9: 'badge-danger',
};
function GraduateProfile({ d, notify }) {
  const s = d.student;
  const rec = d.record || {};
  const bio = rec.bio || {};
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(d.status || 'Graduated');
  const [reason, setReason] = useState('');
  const [alu, setAlu] = useState(d.alumni || {});
  const [pw, setPw] = useState('');
  const setAluField = (k, v) => setAlu((a) => ({ ...a, [k]: v }));
  const saveAlumni = async () => {
    setBusy(true);
    const r = await submitJson(d.alumni_save_url, alu);
    setBusy(false);
    if (r.ok) notify && notify('success', r.message || 'Alumni details saved.');
    else notify && notify('error', r.error || 'Could not save.');
  };
  const savePassword = async () => {
    if (pw.length < 6) { notify && notify('error', 'Password must be at least 6 characters.'); return; }
    setBusy(true);
    const r = await submitJson(d.set_password_url, { password: pw });
    setBusy(false);
    if (r.ok) { notify && notify('success', r.message || 'Password set.'); setPw(''); }
    else notify && notify('error', r.error || 'Could not set password.');
  };
  const fulfilReq = (req) => { window.open(req.fulfil_url, '_blank'); setTimeout(() => nav.refresh && nav.refresh(), 1500); };
  const declineReq = async (req) => {
    if (!await confirm(`Decline the request for ${req.label}?`)) return;
    const r = await submitJson(req.decline_url, {});
    if (r.ok) { notify && notify('success', r.message || 'Request declined.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not decline.');
  };
  const undoGraduate = async () => {
    if (!await confirm(`Un-graduate ${s.full_name}? They will move back to active students and leave the Graduates list. Their records are kept.`)) return;
    setBusy(true);
    const r = await submitJson(d.urls.ungraduate, {});
    setBusy(false);
    if (r.ok) nav.go(r.redirect);
    else notify && notify('error', r.error || 'Could not un-graduate this student.');
  };
  const saveStatus = async () => {
    if (status === (d.status || 'Graduated')) { notify && notify('error', 'Pick a different status first.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.change_status, { status, reason });
    setBusy(false);
    if (r.ok) { notify && notify('success', r.message || 'Status updated.'); setReason(''); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not update status.');
  };
  const revokeDoc = async (doc) => {
    const verb = doc.revoked ? 'Reinstate' : 'Revoke';
    if (!await confirm(`${verb} ${doc.label}? ` + (doc.revoked
      ? 'It will verify as genuine again.'
      : 'It will verify as INVALID on the public portal.'))) return;
    const r = await submitJson(doc.revoke_url, {});
    if (r.ok) { notify && notify('success', r.message || 'Done.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not update the document.');
  };
  return (
    <>
      <div className="profile-hero">
        <div className="ph-cover" />
        <div className="ph-body">
          <div className="ph-avatar" style={bio.photo_url
              ? { padding: 0, overflow: 'hidden' }
              : { background: 'linear-gradient(135deg,var(--primary),var(--primary-hover))' }} aria-hidden="true">
            {bio.photo_url
              ? <img src={bio.photo_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : ((s.full_name || '?').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?')}
          </div>
          <div className="ph-id">
            <h1 className="ph-name">{s.full_name}</h1>
            <div className="ph-meta">
              <span className="badge badge-primary">{s.student_id}</span>
              {s.gender && <span className={'badge ' + (s.gender === 'Male' ? 'badge-info' : 'badge-warning')}>{s.gender}</span>}
              <span className="badge badge-success"><i aria-hidden="true" className="fas fa-user-graduate" /> {d.status || 'Graduated'}</span>
              {d.graduation_session && <span className="badge badge-secondary">Class of {d.graduation_session}</span>}
            </div>
          </div>
        </div>
        <div className="ph-actions">
          <a href={d.urls.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>
          <a href={d.urls.full_profile} className="btn btn-primary"><i aria-hidden="true" className="fas fa-user" /> Full Profile</a>
          {d.urls.ungraduate && canWrite(d, 'promote_graduate_status') && <button type="button" className="btn btn-danger" disabled={busy} onClick={undoGraduate}>
            <i aria-hidden="true" className="fas fa-rotate-left" /> Un-graduate</button>}
        </div>
      </div>
      <div className="gp-grid">
        {/* ===================== RAIL ===================== */}
        <div className="gp-rail">

          <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic p"><i aria-hidden="true" className="fas fa-graduation-cap" /></span><h3>Graduation</h3></div></div>
            <div className="gp-sec-body">
              {((rec.attendance && rec.attendance.total > 0) || rec.finance || (typeof rec.clinic_visits === 'number' && rec.clinic_visits > 0)) &&
                <div className="gp-qstats" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(90px,1fr))' }}>
                  {rec.attendance && rec.attendance.total > 0 && <div className="gp-qstat"><b>{rec.attendance.percent}%</b><span>Attendance</span></div>}
                  {rec.finance && <div className="gp-qstat"><b>{NGN(rec.finance.total_paid)}</b><span>Fees paid</span></div>}
                  {typeof rec.clinic_visits === 'number' && rec.clinic_visits > 0 && <div className="gp-qstat"><b>{rec.clinic_visits}</b><span>Clinic visits</span></div>}
                </div>}
              <GpKV label="Status" value={d.status || 'Graduated'} />
              <GpKV label="Graduated" value={d.graduation_date} />
              <GpKV label="Session" value={d.graduation_session} />
            </div>
          </div>

          {d.urls.change_status && canWrite(d, 'promote_graduate_status') && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic a"><i aria-hidden="true" className="fas fa-arrows-turn-right" /></span><h3>Update Status</h3></div></div>
            <div className="gp-sec-body">
              <div className="gp-status-now"><span className="dot" aria-hidden="true" /><b>Currently: {d.status || 'Graduated'}</b></div>
              <div className="gp-field"><label>New status</label>
                <select className="form-control" value={status} onChange={(e) => setStatus(e.target.value)}>
                  {(d.statuses || []).map((st) => <option key={st} value={st}>{st}</option>)}</select></div>
              <div className="gp-field"><label>Reason <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(audit trail)</span></label>
                <textarea className="form-control" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Certificate collected on 12 Aug" /></div>
              <button type="button" className="btn btn-primary" style={{ width: '100%' }} disabled={busy} onClick={saveStatus}><i aria-hidden="true" className="fas fa-save" /> Update status</button>
            </div>
          </div>}

          {d.set_password_url && d.is_admin && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic i"><i aria-hidden="true" className="fas fa-key" /></span><h3>Portal Access</h3></div></div>
            <div className="gp-sec-body">
              <p style={{ margin: '0 0 .8rem', fontSize: '.78rem', color: 'var(--text-muted)' }}>Set a password so this graduate can sign in to the alumni portal. They can also log in with a verification code from any document you issued them.</p>
              <div className="gp-field"><label>New password</label>
                <div className="gp-ctrl"><i aria-hidden="true" className="fas fa-lock gp-pre" />
                  <input className="form-control" type="text" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="At least 6 characters" /></div></div>
              <button type="button" className="btn btn-secondary" style={{ width: '100%' }} disabled={busy} onClick={savePassword}><i aria-hidden="true" className="fas fa-key" /> Set password</button>
              {d.alumni_login_url && <div style={{ marginTop: '.8rem', padding: '.6rem .7rem', background: 'var(--gray-50)', borderRadius: 'var(--radius-md)', fontSize: '.76rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '.4rem', overflow: 'hidden' }}>
                <i aria-hidden="true" className="fas fa-link" style={{ flexShrink: 0 }} />
                <a href={d.alumni_login_url} target="_blank" rel="noopener noreferrer" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.alumni_login_url}</a>
              </div>}
            </div>
          </div>}

        </div>

        {/* ===================== MAIN ===================== */}
        <div className="gp-main">

          {(d.status_history && d.status_history.length > 0) && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic g"><i aria-hidden="true" className="fas fa-clock-rotate-left" /></span><h3>Status History</h3></div><span className="meta">{d.status_history.length} change{d.status_history.length === 1 ? '' : 's'}</span></div>
            <div className="gp-tl">
              {d.status_history.map((h, i) => (
                <div className="gp-tlrow" key={i}><span className={'gp-tldot' + (i === 0 ? '' : ' muted')} aria-hidden="true" />
                  <div className="gp-tlbody">
                    <div className="gp-tlchange">{h.old || '—'} <span className="arrow">→</span> <strong>{h.new}</strong></div>
                    <div className="gp-tlmeta">{h.reason ? h.reason + ' · ' : ''}{h.at}{h.actor ? ` · by ${h.actor}` : ''}</div>
                  </div></div>
              ))}
            </div>
          </div>}

          {/* ---- Documents ---- */}
          {d.documents && d.documents.length > 0 && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic s"><i aria-hidden="true" className="fas fa-file-signature" /></span><h3>Documents</h3></div><span className="meta">{d.documents.length} types</span></div>
            <div className="gp-doctiles">
              {d.documents.map((doc) => (
                <div className="gp-doctile" key={doc.type}>
                  <div className={'gp-dt-ribbon ' + (doc.revoked ? 'revoked' : doc.number ? 'issued' : 'none')} />
                  <div className="gp-dt-body">
                    <div className="gp-dt-top">
                      <span className={'gp-dt-ic' + (doc.revoked ? ' danger' : doc.number ? '' : ' off')}>
                        <i aria-hidden="true" className={'fas ' + (doc.revoked ? 'fa-file-circle-xmark' : doc.number ? 'fa-file-circle-check' : 'fa-file-signature')} /></span>
                      {doc.revoked ? <span className="badge badge-danger">Revoked</span>
                        : doc.number ? <span className="badge badge-success">Issued</span>
                        : <span className="badge badge-secondary">Not issued</span>}
                    </div>
                    <div><div className="gp-dt-label">{doc.label}</div>{doc.number && <div className="gp-dt-num">No. {doc.number}{doc.reprint_count > 0 ? ` · ${doc.reprint_count} reprint${doc.reprint_count === 1 ? '' : 's'}` : ''}</div>}</div>
                    {doc.number && <div className="gp-dt-verify">
                      {doc.verify_count > 0 ? <><i aria-hidden="true" className="fas fa-circle-check" style={{ color: 'var(--success)' }} /> {doc.verify_count}× checked</> : <><i aria-hidden="true" className="fas fa-circle" /> not yet checked</>}
                      {doc.verify_url && <>· <a href={doc.verify_url} target="_blank" rel="noopener noreferrer">verify link</a></>}
                    </div>}
                    <div className="gp-dt-actions">
                      {canWrite(d, 'documents_generate') && <a href={doc.download_url} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm">
                        <i aria-hidden="true" className={'fas ' + (doc.number ? 'fa-rotate' : 'fa-download')} /> {doc.number ? 'Re-issue' : 'Generate'}</a>}
                      {doc.number && doc.revoke_url && canWrite(d, 'documents_generate') && <button type="button" className="btn btn-secondary btn-sm" onClick={() => revokeDoc(doc)}>
                        <i aria-hidden="true" className={'fas ' + (doc.revoked ? 'fa-rotate-left' : 'fa-ban')} /> {doc.revoked ? 'Reinstate' : 'Revoke'}</button>}
                    </div>
                  </div>
                </div>))}
            </div>
            <p className="text-muted text-sm" style={{ margin: '0 1.25rem 1.1rem' }}>
              <i aria-hidden="true" className="fas fa-qrcode" /> Each PDF carries a QR code + unique number; anyone can confirm it at the public verification page.</p>
          </div>}

          {/* ---- Document requests (from the alumni portal) ---- */}
          {d.doc_requests && d.doc_requests.length > 0 && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic a"><i aria-hidden="true" className="fas fa-inbox" /></span><h3>Document Requests</h3></div><span className="meta">from the alumni portal</span></div>
            <div className="gp-rowlist">
              {d.doc_requests.map((r) => (
                <div className="gp-rlrow" key={r.id}>
                  <span className="ric"><i aria-hidden="true" className="fas fa-file" /></span>
                  <div className="rbody"><div className="rtitle">{r.label}</div><div className="rsub">Requested {r.requested_at}{r.note ? ` · "${r.note}"` : ''}</div></div>
                  {r.status === 'pending' ? <>
                    <span className="badge badge-warning">pending</span>
                    {canWrite(d, 'documents_requests') && <div className="ractions">
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => fulfilReq(r)}><i aria-hidden="true" className="fas fa-file-arrow-down" /></button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => declineReq(r)}><i aria-hidden="true" className="fas fa-xmark" /></button>
                    </div>}
                  </> : <span className="rval">{r.response_note || (r.status === 'fulfilled' ? 'Issued' : r.status === 'declined' ? 'Declined' : r.status)}</span>}
                </div>
              ))}
            </div>
          </div>}

          {/* ---- Alumni details ---- */}
          {d.alumni_save_url && canWrite(d, 'graduates_alumni_edit') && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic i"><i aria-hidden="true" className="fas fa-id-badge" /></span><h3>Alumni Details</h3></div>
              {d.alumni && d.alumni.updated_at && <span className="meta">Updated {d.alumni.updated_at}{d.alumni.updated_by ? ` by ${d.alumni.updated_by}` : ''}</span>}</div>
            <div className="gp-sec-body">
              <div className="gp-formgrid">
                {[['occupation', 'Occupation'], ['job_title', 'Job title'], ['employer', 'Employer'],
                  ['higher_institution', 'Higher institution'], ['course_of_study', 'Course of study'],
                  ['phone', 'Phone'], ['email', 'Email'], ['linkedin_url', 'LinkedIn URL'],
                  ['city', 'City'], ['country', 'Country']].map(([k, lab]) => (
                  <div className="gp-field" key={k}><label>{lab}</label>
                    <div className="gp-ctrl"><i aria-hidden="true" className={'fas ' + ALUMNI_FIELD_ICONS[k] + ' gp-pre'} />
                      <input className="form-control" value={alu[k] || ''} onChange={(e) => setAluField(k, e.target.value)} /></div></div>))}
              </div>
              <div className="gp-field"><label>Achievements</label>
                <textarea className="form-control" rows={2} value={alu.achievements || ''} onChange={(e) => setAluField('achievements', e.target.value)} /></div>
              <div className="gp-chk"><input type="checkbox" checked={!!alu.willing_to_mentor} onChange={(e) => setAluField('willing_to_mentor', e.target.checked)} /> Willing to mentor current students</div>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={saveAlumni}><i aria-hidden="true" className="fas fa-save" /> Save alumni details</button>
            </div>
          </div>}

          {/* ---- Permanent record (read-only) ---- */}
          <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic g"><i aria-hidden="true" className="fas fa-id-card" /></span><h3>Biodata</h3></div></div>
            <div className="gp-sec-body" style={{ display: 'flex', gap: '1.2rem', flexWrap: 'wrap' }}>
              {bio.photo_url ? <img src={bio.photo_url} alt="" style={{ width: 96, height: 96, objectFit: 'cover', borderRadius: 12, border: '1px solid var(--border-color)' }} /> : null}
              <div style={{ flex: 1, minWidth: 240, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.6rem 1.2rem' }}>
                <GpKV label="Date of Birth" value={bio.date_of_birth} />
                <GpKV label="Admission Session" value={rec.admission_session} />
                <GpKV label="House" value={bio.house} />
                <GpKV label="Boarding" value={bio.boarding_status} />
                <GpKV label="Stream" value={bio.stream} />
                <GpKV label="Blood Group" value={bio.blood_group} />
                <GpKV label="Genotype" value={bio.genotype} />
                <GpKV label="Allergies" value={bio.allergies} />
                <GpKV label="Religion" value={bio.religion} />
                <div style={{ gridColumn: '1/-1' }}><GpKV label="Address" value={bio.home_address} /></div>
                <GpKV label="WAEC Subjects" value={bio.waec_subjects} />
                <GpKV label="JAMB Subjects" value={bio.jamb_subjects} />
                <GpKV label="JAMB Reg. No." value={bio.jamb_reg_number} />
              </div>
            </div>
          </div>

          {rec.class_history && rec.class_history.length > 0 && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic g"><i aria-hidden="true" className="fas fa-timeline" /></span><h3>Class &amp; Arm History</h3></div></div>
            <div className="gp-rowlist">
              {rec.class_history.map((h, i) => (
                <div className="gp-rlrow" key={i}><span className="ric"><i aria-hidden="true" className="fas fa-layer-group" /></span>
                  <div className="rbody"><div className="rtitle">{h.klass} {h.arm}</div><div className="rsub">{h.session} · {h.term}</div></div></div>
              ))}
            </div>
          </div>}

          {rec.academic && (rec.academic.terms_count > 0) && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic p"><i aria-hidden="true" className="fas fa-chart-line" /></span><h3>Academic History</h3></div>
              {rec.academic.cumulative != null && <span className="badge badge-primary">Cumulative avg: {rec.academic.cumulative}%</span>}</div>
            <div className="gp-sec-body">
              {rec.academic.terms.map((t, i) => (
                <div className="gp-examblock" key={i}>
                  <div className="gp-examhead"><b>{t.session}</b><span className="muted">{t.term}</span>{t.average != null && <span className="muted">Term avg: {t.average}%</span>}</div>
                  <div className="subjects-grid" style={{ padding: '.85rem .95rem' }}>
                    {t.subjects.map((sub, j) => (
                      <div className="subject-item" key={j}><span>{sub.subject}</span><strong>{sub.score}{sub.grade ? ` · ${sub.grade}` : ''}</strong></div>))}
                  </div>
                </div>
              ))}
            </div>
          </div>}

          {rec.finance && rec.finance.recent && rec.finance.recent.length > 0 && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic s"><i aria-hidden="true" className="fas fa-receipt" /></span><h3>Recent Fee Payments</h3></div></div>
            <div className="gp-rowlist">
              {rec.finance.recent.map((p, i) => (
                <div className="gp-rlrow" key={i}><span className="ric" style={{ background: 'var(--success-light)', color: 'var(--success)' }}><i aria-hidden="true" className="fas fa-naira-sign" /></span>
                  <div className="rbody"><div className="rtitle">{NGN(p.amount)}</div><div className="rsub">{p.date} · {p.method || '—'}</div></div>
                  <span className="rval">{p.receipt || '—'}</span></div>
              ))}
            </div>
          </div>}

          {rec.discipline && rec.discipline.length > 0 && <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic w"><i aria-hidden="true" className="fas fa-gavel" /></span><h3>Discipline Records</h3></div></div>
            <div className="gp-rowlist">
              {rec.discipline.map((r, i) => (
                <div className="gp-rlrow" key={i}><span className="ric"><i aria-hidden="true" className="fas fa-gavel" /></span>
                  <div className="rbody"><div className="rtitle">{r.category}{r.severity ? ` · ${r.severity}` : ''}</div><div className="rsub">{r.date}{r.description ? ` — ${r.description}` : ''}</div></div>
                  <span className="rval">{r.action || '—'}</span></div>
              ))}
            </div>
          </div>}

          <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic p"><i aria-hidden="true" className="fas fa-file-alt" /></span><h3>WAEC Results</h3></div>
              {canWrite(d) && <a href={d.urls.add_waec} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}</div>
            <div className="gp-sec-body">{d.waec_by_year.length ? d.waec_by_year.map((data, i) => (
              <div className="gp-examblock" key={i}>
                <div className="gp-examhead"><b>{data.exam_year}</b>{data.exam_number && <span className="muted">Exam No: {data.exam_number}</span>}</div>
                <div className="subjects-grid" style={{ padding: '.85rem .95rem' }}>
                  {data.subjects.map((r, j) => (
                    <div className="subject-item" key={j}><span>{r.subject}</span><span className={'badge ' + (WAEC_GRADE_BADGE[r.grade] || 'badge-secondary')}>{r.grade}</span></div>))}
                </div>
              </div>
            )) : <Empty icon="fa-file-alt" title=""><p>No WAEC results recorded</p>{canWrite(d) && <a href={d.urls.add_waec} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add WAEC Result</a>}</Empty>}</div>
          </div>

          <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic p"><i aria-hidden="true" className="fas fa-file-lines" /></span><h3>NECO Results</h3></div>
              {canWrite(d) && <a href={d.urls.add_neco} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}</div>
            <div className="gp-sec-body">{(d.neco_by_year || []).length ? d.neco_by_year.map((data, i) => (
              <div className="gp-examblock" key={i}>
                <div className="gp-examhead"><b>{data.exam_year}</b>{data.exam_number && <span className="muted">Reg No: {data.exam_number}</span>}</div>
                <div className="subjects-grid" style={{ padding: '.85rem .95rem' }}>
                  {data.subjects.map((r, j) => (
                    <div className="subject-item" key={j}><span>{r.subject}</span><span className={'badge ' + (WAEC_GRADE_BADGE[r.grade] || 'badge-secondary')}>{r.grade}</span></div>))}
                </div>
              </div>
            )) : <Empty icon="fa-file-lines" title=""><p>No NECO results recorded</p>{canWrite(d) && <a href={d.urls.add_neco} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add NECO Result</a>}</Empty>}</div>
          </div>

          <div className="gp-sec">
            <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic a"><i aria-hidden="true" className="fas fa-file-contract" /></span><h3>JAMB Results</h3></div>
              {canWrite(d) && <a href={d.urls.add_jamb} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}</div>
            <div className="gp-sec-body">{d.jamb_results.length ? d.jamb_results.map((j, i) => (
              <div className="gp-examblock" key={i}>
                <div className="gp-examhead"><b>{j.exam_year}</b>{j.registration_number && <span className="muted">Reg No: {j.registration_number}</span>}<span className="badge badge-primary">{j.total_score}</span></div>
                <div className="subjects-grid" style={{ padding: '.85rem .95rem' }}>
                  {j.subjects.map((sub, k) => (
                    <div className="subject-item" key={k}><span>{sub.name}</span><strong>{sub.score}</strong></div>))}
                </div>
              </div>
            )) : <Empty icon="fa-file-contract" title=""><p>No JAMB results recorded</p>{canWrite(d) && <a href={d.urls.add_jamb} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add JAMB Result</a>}</Empty>}</div>
          </div>

          {d.contacts.length > 0 && (
            <div className="gp-sec">
              <div className="gp-sec-head"><div className="ttl"><span className="gp-sec-ic g"><i aria-hidden="true" className="fas fa-phone" /></span><h3>Contact Information</h3></div></div>
              <div className="gp-contacts">
                {d.contacts.map((c, i) => (
                  <div className="gp-contact" key={i}>
                    <span className="cav">{(c.name || '?').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()}</span>
                    <div><div className="cname">{c.name}</div><div className="crel">{c.relationship}</div></div>
                    <span className="cphone">{c.phone}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </>
  );
}

// ---- History ---------------------------------------------------------------
function History({ d }) {
  const nav = useNav();
  const [filter, setFilter] = useState('');
  const [q, setQ] = useState('');
  const count = (st) => d.records.filter((r) => r.status === st).length;
  const t = q.trim().toLowerCase();
  const shown = d.records.filter((r) => (!filter || r.status === filter)
    && (!t || `${r.name} ${r.student_no || ''} ${r.from_class} ${r.to_class} ${r.stream || ''}`.toLowerCase().includes(t)));
  const groups = {};
  shown.forEach((r) => { (groups[r.from_class] = groups[r.from_class] || []).push(r); });
  const sess = d.sessions.find((x) => String(x.id) === String(d.session_id));
  const ICON = { promoted: 'fa-arrow-up', repeated: 'fa-rotate-left', graduated: 'fa-user-graduate', withdrawn: 'fa-door-open' };
  const avgs = d.records.filter((r) => r.average != null).map((r) => r.average);
  const meanAvg = avgs.length ? Math.round(avgs.reduce((x, y) => x + y, 0) / avgs.length * 10) / 10 : null;

  return (
    <div className="pm">
      <PmHead back={(d.urls && d.urls.index) || '/promotion/'} kicker="Promotion & graduation" title="Promotion history"
              sub={sess ? `What happened at the end of ${sess.name}.` : 'Pick a session to see who moved where.'}
              actions={d.urls && d.urls.process ? <a href={d.urls.process} className="pm-btn"><i aria-hidden="true" className="fas fa-arrow-up-right-dots" /> <span>Promote students</span></a> : null} />

      <section className="pm-pick">
        <span className="pm-pick-l">Session promoted from</span>
        <div className="pm-chips" role="radiogroup" aria-label="Session">
          {d.sessions.map((x) => (
            <button key={x.id} type="button" role="radio" aria-checked={String(x.id) === String(d.session_id)}
                    className={String(x.id) === String(d.session_id) ? 'on' : ''}
                    onClick={() => navParams(nav.go, window.location.pathname, { session_id: x.id })}>{x.name}</button>))}
        </div>
      </section>

      {d.records.length ? (<>
        <PmTiles items={[
          { label: 'All', value: d.records.length, sub: meanAvg != null ? `avg ${meanAvg}%` : 'records', onClick: () => setFilter(''), on: !filter },
          { label: 'Promoted', icon: 'fa-arrow-up', value: count('promoted'), tone: 'good', onClick: () => setFilter('promoted'), on: filter === 'promoted' },
          { label: 'Repeated', icon: 'fa-rotate-left', value: count('repeated'), tone: 'warn', onClick: () => setFilter('repeated'), on: filter === 'repeated' },
          { label: 'Graduated', icon: 'fa-user-graduate', value: count('graduated'), tone: 'info', onClick: () => setFilter('graduated'), on: filter === 'graduated' },
          count('withdrawn') ? { label: 'Withdrawn', icon: 'fa-door-open', value: count('withdrawn'), onClick: () => setFilter('withdrawn'), on: filter === 'withdrawn' } : null,
        ]} />

        <section className="pm-card">
          <header className="pm-card-h">
            <div className="pm-search"><i aria-hidden="true" className="fas fa-search" />
              <input type="search" placeholder="Search name, ID, class or stream…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search records" /></div>
            <span className="pm-dim pm-count">{shown.length}{shown.length !== d.records.length ? ` of ${d.records.length}` : ''}</span>
          </header>
          {shown.length === 0 ? <p className="pm-empty">No records match.</p> : (
            <ul className="pm-hist">
              {Object.entries(groups).map(([cls, list]) => (
                <React.Fragment key={cls}>
                  <li className="pm-ghead">From {cls}<span>{list.length}</span></li>
                  {list.map((r, i) => (
                    <li key={cls + i} className={'pm-hrow st-' + r.status}>
                      <span className="pm-av" data-g={r.gender || ''} aria-hidden="true">{pmInitials(r.name)}</span>
                      <span className="pm-pn">
                        {r.student_url ? <a href={r.student_url}><strong>{r.name}</strong></a> : <strong>{r.name}</strong>}
                        <small>{r.student_no}{r.date ? ` · ${r.date}` : ''}{r.by ? ` · by ${r.by}` : ''}</small>
                      </span>
                      <span className="pm-move">{r.from_class} <i aria-hidden="true" className="fas fa-arrow-right" /> <b>{r.to_class}</b>{r.stream ? <span className="pm-tag">{r.stream}</span> : null}</span>
                      {r.average != null ? <span className={'pm-avg ' + (r.status === 'repeated' ? 'bad' : 'good')}>{r.average}%</span> : <span className="pm-avg none">—</span>}
                      <span className={'pm-st st-' + r.status}><i aria-hidden="true" className={'fas ' + (ICON[r.status] || 'fa-circle')} /> {r.status}{r.is_manual ? <small> · manual</small> : null}</span>
                    </li>
                  ))}
                </React.Fragment>
              ))}
            </ul>
          )}
        </section>
      </>) : (
        <section className="pm-card"><div className="pm-card-b">
          {d.session_id
            ? <Empty icon="fa-clock-rotate-left" title="No records for this session"><p>Nobody was promoted from {sess ? sess.name : 'this session'} yet.</p>
                {d.urls && d.urls.process && <div className="empty-state-actions"><a href={d.urls.process} className="btn btn-primary"><i aria-hidden="true" className="fas fa-arrow-up-right-dots" /> Promote students</a></div>}</Empty>
            : <Empty icon="fa-hand-pointer" title="Pick a session"><p>Choose a session above to see its promotion records.</p></Empty>}
        </div></section>
      )}
    </div>
  );
}

// ---- Graduate vs SSS3 comparison -------------------------------------------
// One metric row: a labelled value for each cohort, with the better side hinted.
function CompareRow({ label, g, s, suffix = '', better = 'high', sNote }) {
  const fmt = (v) => (v == null ? '—' : v + suffix);
  let gHi = false, sHi = false;
  if (g != null && s != null && g !== s) {
    const gWins = better === 'high' ? g > s : g < s;
    gHi = gWins; sHi = !gWins;
  }
  const cell = (v, hi) => <td style={{ textAlign: 'right', fontWeight: hi ? 700 : 400, color: hi ? 'var(--success, #2e7d32)' : 'inherit' }}>{fmt(v)}</td>;
  return (
    <tr>
      <td>{label}</td>
      {cell(g, gHi)}
      {s == null && sNote ? <td style={{ textAlign: 'right' }} className="text-muted">{sNote}</td> : cell(s, sHi)}
    </tr>
  );
}

function WaecCompareTable({ g, s }) {
  const sNull = s == null;
  return (
    <table className="data-table">
      <thead><tr><th>Metric</th><th style={{ textAlign: 'right' }}>Graduates</th><th style={{ textAlign: 'right' }}>Current SSS3</th></tr></thead>
      <tbody>
        <CompareRow label="Students with results" g={g ? g.n : 0} s={sNull ? null : s.n} sNote={sNull ? 'no real WAEC yet' : ''} />
        <CompareRow label="Avg credits (C6+)" g={g ? g.avg_credits : null} s={sNull ? null : s.avg_credits} sNote={sNull ? '—' : ''} />
        <CompareRow label="Avg distinctions (B3+)" g={g ? g.avg_distinctions : null} s={sNull ? null : s.avg_distinctions} sNote={sNull ? '—' : ''} />
        <CompareRow label="% with 5+ credits" g={g ? g.pct_5_credits : null} s={sNull ? null : s.pct_5_credits} suffix="%" sNote={sNull ? '—' : ''} />
        <CompareRow label="% with 5 incl. Eng & Maths" g={g ? g.pct_5_incl_core : null} s={sNull ? null : s.pct_5_incl_core} suffix="%" sNote={sNull ? '—' : ''} />
      </tbody>
    </table>
  );
}

function JambCompareTable({ g, s }) {
  const sNull = s == null;
  return (
    <table className="data-table">
      <thead><tr><th>Metric</th><th style={{ textAlign: 'right' }}>Graduates</th><th style={{ textAlign: 'right' }}>Current SSS3</th></tr></thead>
      <tbody>
        <CompareRow label="Students with results" g={g ? g.n : 0} s={sNull ? null : s.n} sNote={sNull ? 'no real JAMB yet' : ''} />
        <CompareRow label="Average score" g={g ? g.avg_score : null} s={sNull ? null : s.avg_score} sNote={sNull ? '—' : ''} />
        <CompareRow label="Highest score" g={g ? g.max_score : null} s={sNull ? null : s.max_score} sNote={sNull ? '—' : ''} />
        <CompareRow label="% scoring 180+" g={g ? g.pct_above_floor : null} s={sNull ? null : s.pct_above_floor} suffix="%" sNote={sNull ? '—' : ''} />
      </tbody>
    </table>
  );
}

function GradeDistRow({ name, g, s, order }) {
  const cells = (dist) => order.map((gr) => <td key={gr} style={{ textAlign: 'center' }}>{dist && dist[gr] ? dist[gr] : '·'}</td>);
  return (<>
    <tr><td colSpan={order.length + 1} style={{ background: 'var(--bg-tertiary)', fontWeight: 600 }}>{name}</td></tr>
    <tr><td className="text-muted">Graduates</td>{cells(g)}</tr>
    {s && <tr><td className="text-muted">Current SSS3</td>{cells(s)}</tr>}
  </>);
}

function GraduateCompare({ d }) {
  const nav = useNav();
  const c = d.comparison;
  const cohorts = c.cohorts;
  const noData = cohorts.graduates.total === 0;
  const dirBadge = (p) => {
    if (!p) return null;
    const cls = p.direction === 'improved' ? 'badge-success' : p.direction === 'declined' ? 'badge-danger' : 'badge-secondary';
    const sign = p.avg_delta > 0 ? '+' : '';
    return <span className={'badge ' + cls}>{p.direction} ({sign}{p.avg_delta})</span>;
  };
  return (
    <>
      <PageHeader title="Graduates vs Current SSS3"
        actions={<a href={d.urls.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>} />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Graduate cohort (session)</label>
          <select className="form-control" value={d.session_id} onChange={(e) => navParams(nav.go, d.urls.self, { session_id: e.target.value })}>
            <option value="">All graduates</option>{d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
      </div></div></div>

      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-graduation-cap" /></div>
          <div className="stat-content"><h3>{cohorts.graduates.total}</h3><p>{cohorts.graduates.label}</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-users" /></div>
          <div className="stat-content"><h3>{cohorts.sss3.total}</h3><p>{cohorts.sss3.label}</p></div></div>
      </div>

      {noData ? (
        <div className="card"><div className="card-body"><Empty icon="fa-chart-column" title="No graduates to compare">
          <p>Once a cohort has been graduated (with mock/real results recorded), this page compares them against the current SSS3 class.</p></Empty></div></div>
      ) : (<>
        <div className="card mb-3"><div className="card-body">
          <p className="text-muted" style={{ margin: 0 }}><i aria-hidden="true" className="fas fa-circle-info" /> Real WAEC/JAMB exists only for graduates. The <strong>mock</strong> rows compare both cohorts on the same exams; the graduates' mock→real pattern below projects where the current class may land.</p>
        </div></div>

        {/* WAEC */}
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-alt" /> WAEC — Real</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><WaecCompareTable g={c.real_waec.graduates} s={c.real_waec.sss3} /></div></div></div>
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-alt" /> WAEC — Mock (latest sitting)</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><WaecCompareTable g={c.mock_waec.graduates} s={c.mock_waec.sss3} /></div></div></div>

        {/* Grade spread */}
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-layer-group" /> WAEC grade spread</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><table className="data-table">
            <thead><tr><th>Cohort</th>{c.grade_order.map((g) => <th key={g} style={{ textAlign: 'center' }}>{g}</th>)}</tr></thead>
            <tbody>
              <GradeDistRow name="Real WAEC" order={c.grade_order} g={c.real_waec.graduates && c.real_waec.graduates.grade_distribution} s={null} />
              <GradeDistRow name="Mock WAEC" order={c.grade_order} g={c.mock_waec.graduates && c.mock_waec.graduates.grade_distribution} s={c.mock_waec.sss3 && c.mock_waec.sss3.grade_distribution} />
            </tbody>
          </table></div></div></div>

        {/* JAMB */}
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-contract" /> JAMB — Real</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><JambCompareTable g={c.real_jamb.graduates} s={c.real_jamb.sss3} /></div></div></div>
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-file-contract" /> JAMB — Mock (best)</h3></div>
          <div className="card-body" style={{ padding: 0 }}><div className="table-container"><JambCompareTable g={c.mock_jamb.graduates} s={c.mock_jamb.sss3} /></div></div></div>

        {/* Pattern + projection */}
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-arrow-trend-up" /> Mock → Real pattern (graduates) &amp; projection</h3></div>
          <div className="card-body">
            <div className="info-grid">
              <div className="info-row"><span className="text-muted">WAEC credits: real vs mock</span><strong>{c.pattern.waec_credits ? dirBadge(c.pattern.waec_credits) : <span className="text-muted">not enough paired data</span>}</strong></div>
              {c.pattern.waec_credits && <div className="info-row"><span className="text-muted">Graduates who beat their mock (WAEC)</span><strong>{c.pattern.waec_credits.pct_improved}% of {c.pattern.waec_credits.n}</strong></div>}
              <div className="info-row"><span className="text-muted">JAMB score: real vs mock</span><strong>{c.pattern.jamb_score ? dirBadge(c.pattern.jamb_score) : <span className="text-muted">not enough paired data</span>}</strong></div>
              {c.pattern.jamb_score && <div className="info-row"><span className="text-muted">Graduates who beat their mock (JAMB)</span><strong>{c.pattern.jamb_score.pct_improved}% of {c.pattern.jamb_score.n}</strong></div>}
            </div>
            {(c.projection.waec || c.projection.jamb) && (
              <div className="card mt-3" style={{ background: 'var(--bg-tertiary)' }}><div className="card-body">
                <h4 style={{ marginTop: 0 }}><i aria-hidden="true" className="fas fa-wand-magic-sparkles" /> Projection for current SSS3</h4>
                <p className="text-muted text-sm">Applying the graduates' mock→real shift to the current class's mock averages.</p>
                {c.projection.waec && <p>WAEC credits: mock avg <strong>{c.projection.waec.mock_avg_credits}</strong> → projected real <strong>{c.projection.waec.projected_avg_credits}</strong> <span className="text-muted">(shift {c.projection.waec.shift > 0 ? '+' : ''}{c.projection.waec.shift}, from {c.projection.waec.basis_n} graduates)</span></p>}
                {c.projection.jamb && <p>JAMB score: mock avg <strong>{c.projection.jamb.mock_avg_score}</strong> → projected real <strong>{c.projection.jamb.projected_avg_score}</strong> <span className="text-muted">(shift {c.projection.jamb.shift > 0 ? '+' : ''}{c.projection.jamb.shift}, from {c.projection.jamb.basis_n} graduates)</span></p>}
              </div></div>
            )}
          </div></div>

        {/* Subject pass rates side by side */}
        {(c.mock_waec.graduates.subject_pass_rates.length > 0 || (c.mock_waec.sss3 && c.mock_waec.sss3.subject_pass_rates.length > 0)) && (
          <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-list-check" /> Mock WAEC subject pass rates</h3></div>
            <div className="card-body" style={{ padding: 0 }}><div className="table-container"><table className="data-table">
              <thead><tr><th>Subject</th><th style={{ textAlign: 'right' }}>Graduates</th><th style={{ textAlign: 'right' }}>Current SSS3</th></tr></thead>
              <tbody>{(() => {
                const gMap = {}; c.mock_waec.graduates.subject_pass_rates.forEach((r) => { gMap[r.subject] = r.pass_rate; });
                const sMap = {}; (c.mock_waec.sss3 ? c.mock_waec.sss3.subject_pass_rates : []).forEach((r) => { sMap[r.subject] = r.pass_rate; });
                const subjects = Array.from(new Set([...Object.keys(gMap), ...Object.keys(sMap)])).sort();
                return subjects.map((sub) => <CompareRow key={sub} label={sub} g={gMap[sub] != null ? gMap[sub] : null} s={sMap[sub] != null ? sMap[sub] : null} suffix="%" />);
              })()}</tbody>
            </table></div></div></div>
        )}
      </>)}
    </>
  );
}

// ---- Alumni directory + advanced search + export + bulk email (admin) -----
function _qsFromFilters(f) {
  const p = {};
  ['q', 'occupation', 'employer', 'institution', 'city', 'country'].forEach((k) => { if (f[k]) p[k] = f[k]; });
  if (f.session_id) p.session_id = f.session_id;
  if (f.mentor) p.mentor = '1';
  if (f.career) p.career = '1';
  if (f.has_contact) p.has_contact = '1';
  return p;
}

const ALUMNI_TEXT_FILTERS = [['occupation', 'Occupation', 'fa-briefcase'], ['employer', 'Employer', 'fa-building'],
  ['institution', 'University / institution', 'fa-building-columns'], ['city', 'City', 'fa-location-dot'], ['country', 'Country', 'fa-earth-africa']];

function Alumni({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [f, setF] = useState(d.filters || {});
  const [mail, setMail] = useState({ open: false, subject: '', body: '', busy: false });
  const [more, setMore] = useState(false);
  const [q, setQ] = useState((d.filters || {}).q || '');
  const apply = (next) => { setF(next); navParams(nav.go, window.location.pathname, _qsFromFilters(next)); };
  const setAndApply = (k, v) => apply({ ...f, [k]: v });
  const clearFilters = () => { setQ(''); apply({}); };
  // Live search: re-query the server a moment after typing stops.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return undefined; }
    const t = setTimeout(() => { if ((f.q || '') !== q) apply({ ...f, q }); }, 450);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  const exportUrl = d.export_url + '?' + new URLSearchParams(_qsFromFilters(f)).toString();
  const requests = d.requests || [];
  const alumni = d.alumni || [];

  const fulfilReq = (r) => { window.open(r.fulfil_url, '_blank'); setTimeout(() => nav.refresh && nav.refresh(), 1500); };
  const declineReq = async (r) => {
    if (!await confirm(`Decline ${r.student_name}'s request for ${r.label}?`)) return;
    const res = await submitJson(r.decline_url, {});
    if (res.ok) { notify && notify('success', res.message || 'Declined.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', res.error || 'Could not decline.');
  };
  const sendMail = async () => {
    if (!mail.subject.trim() || !mail.body.trim()) { notify && notify('error', 'Subject and message are required.'); return; }
    if (!await confirm(`Send this email to the ${d.contactable} alumni in this list who have an email address?`)) return;
    setMail((m) => ({ ...m, busy: true }));
    const r = await submitJson(d.bulk_email_url, { subject: mail.subject, body: mail.body, ..._qsFromFilters(f) });
    setMail((m) => ({ ...m, busy: false }));
    if (r.ok) { notify && notify('success', r.message || 'Sending.'); setMail({ open: false, subject: '', body: '', busy: false }); }
    else notify && notify('error', r.error || 'Could not send.');
  };
  // Active filters as removable chips.
  const sessName = (id) => ((d.sessions || []).find((x) => String(x.id) === String(id)) || {}).name;
  const active = [
    f.session_id && { k: 'session_id', label: `Class of ${sessName(f.session_id) || ''}` },
    ...ALUMNI_TEXT_FILTERS.filter(([k]) => f[k]).map(([k, lab]) => ({ k, label: `${lab}: ${f[k]}` })),
    f.mentor && { k: 'mentor', label: 'Mentors' }, f.career && { k: 'career', label: 'Has career info' }, f.has_contact && { k: 'has_contact', label: 'Has contact' },
  ].filter(Boolean);
  const anyFilter = active.length > 0 || !!f.q;
  const wa = (ph) => { const n = String(ph || '').replace(/\D/g, ''); return n ? 'https://wa.me/' + (n.startsWith('0') ? '234' + n.slice(1) : n) : null; };

  return (
    <div className="pm">
      <PmHead back={d.graduates} kicker="Graduates" title="Alumni directory"
              sub="Find former students by where they work, study or live — and stay in touch."
              actions={<>
                {canWrite(d, 'alumni_bulk_email') && <button type="button" className="pm-btn primary" onClick={() => setMail((m) => ({ ...m, open: true }))}>
                  <i aria-hidden="true" className="fas fa-envelope" /> <span>Email alumni</span></button>}
                <PmMenu label="More" items={[
                  d.analytics_url && { href: d.analytics_url, icon: 'fa-chart-pie', label: 'Alumni analytics' },
                  canWrite(d, 'alumni_export') && { href: exportUrl, icon: 'fa-file-csv', label: 'Export this list (CSV)' },
                ]} />
              </>} />

      <PmTiles items={[
        { label: 'Alumni', icon: 'fa-user-graduate', value: d.total, sub: anyFilter ? `${d.shown} match` : 'all graduates' },
        { label: 'Mentors', icon: 'fa-hands-helping', value: d.mentors, tone: 'good', sub: f.mentor ? 'showing mentors' : 'willing to help',
          onClick: () => setAndApply('mentor', !f.mentor), on: !!f.mentor },
        { label: 'Reachable by email', icon: 'fa-at', value: d.contactable, sub: 'in this list' },
        requests.length ? { label: 'Document requests', icon: 'fa-inbox', value: requests.length, tone: 'warn', sub: 'waiting for you',
          onClick: () => { const el = document.getElementById('al-req'); if (el) el.scrollIntoView({ behavior: 'smooth' }); } } : null,
      ]} />

      {requests.length > 0 && (
        <section className="pm-card" id="al-req">
          <header className="pm-card-h"><span className="pm-card-ic warn"><i aria-hidden="true" className="fas fa-inbox" /></span>
            <div className="pm-card-t"><h3>Document requests</h3><small>Oldest first — issue or decline each one</small></div></header>
          <ul className="pm-people">
            {requests.map((r) => (
              <li key={r.id} className="pm-person al-req">
                <span className="pm-av" aria-hidden="true">{pmInitials(r.student_name)}</span>
                <span className="pm-pn">
                  {r.profile_url ? <a href={r.profile_url}><strong>{r.student_name}</strong></a> : <strong>{r.student_name}</strong>}
                  <small><b>{r.label}</b> · {r.requested_at}{r.admission_no ? ` · ${r.admission_no}` : ''}</small>
                  {r.note && <small className="al-note">“{r.note}”</small>}
                </span>
                {canWrite(d, 'documents_requests') && <span className="al-req-a">
                  <button type="button" className="pm-btn primary" onClick={() => fulfilReq(r)}><i aria-hidden="true" className="fas fa-file-arrow-down" /> <span>Issue</span></button>
                  <button type="button" className="pm-icon danger" onClick={() => declineReq(r)} aria-label="Decline request" title="Decline"><i aria-hidden="true" className="fas fa-xmark" /></button>
                </span>}
              </li>))}
          </ul>
        </section>
      )}

      <section className="pm-card">
        <header className="pm-card-h wrap">
          <div className="pm-search"><i aria-hidden="true" className="fas fa-search" />
            <input type="search" placeholder="Search by name or admission number…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search alumni" /></div>
          <label className="pm-mini"><span>Class of</span>
            <select value={f.session_id || ''} onChange={(e) => setAndApply('session_id', e.target.value)}>
              <option value="">All years</option>{(d.sessions || []).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
          <button type="button" className="pm-btn" onClick={() => setMore(true)}><i aria-hidden="true" className="fas fa-sliders" /> <span>More filters</span></button>
        </header>
        <div className="al-quick">
          {[['mentor', 'Mentors', 'fa-hands-helping'], ['career', 'Has career / study info', 'fa-briefcase'], ['has_contact', 'Has phone or email', 'fa-phone']].map(([k, lab, ic]) => (
            <button key={k} type="button" aria-pressed={!!f[k]} className={'al-qchip' + (f[k] ? ' on' : '')} onClick={() => setAndApply(k, !f[k])}>
              <i aria-hidden="true" className={'fas ' + (f[k] ? 'fa-check' : ic)} /> {lab}</button>))}
          {active.filter((x) => !['mentor', 'career', 'has_contact'].includes(x.k)).map((x) => (
            <button key={x.k} type="button" className="al-qchip on" onClick={() => setAndApply(x.k, '')} aria-label={`Remove filter ${x.label}`}>
              {x.label} <i aria-hidden="true" className="fas fa-xmark" /></button>))}
          {anyFilter && <button type="button" className="pm-link" onClick={clearFilters}>Clear all</button>}
        </div>

        {alumni.length ? (
          <ul className="al-grid">
            {alumni.map((a) => {
              const work = a.employer || a.higher_institution;
              const role = a.job_title || a.occupation || (a.higher_institution && a.course ? a.course : null);
              const place = [a.city, a.country].filter(Boolean).join(', ');
              const waUrl = wa(a.phone);
              return (
                <li key={a.id} className="al-card">
                  <a href={a.profile_url} className="al-top">
                    <GradAvatar name={a.full_name} photo={a.photo_url} />
                    <span className="pm-pn"><strong>{a.full_name}</strong>
                      <small>{a.student_id}{a.graduation_session ? ` · Class of ${a.graduation_session}` : ''}</small></span>
                    {a.willing_to_mentor && <span className="al-mentor" title="Willing to mentor current students"><i aria-hidden="true" className="fas fa-hands-helping" /> Mentor</span>}
                  </a>
                  <div className="al-info">
                    {(role || work) ? (
                      <span><i aria-hidden="true" className={'fas ' + (a.higher_institution && !a.employer ? 'fa-building-columns' : 'fa-briefcase')} />
                        {role}{role && work ? ' · ' : ''}{work && <b>{work}</b>}</span>
                    ) : <span className="pm-dim"><i aria-hidden="true" className="fas fa-briefcase" /> No career info yet</span>}
                    {place && <span><i aria-hidden="true" className="fas fa-location-dot" /> {place}</span>}
                  </div>
                  <div className="al-acts">
                    {a.phone && <a className="al-c call" href={'tel:' + a.phone} aria-label={`Call ${a.full_name}`} title={a.phone}><i aria-hidden="true" className="fas fa-phone" /></a>}
                    {waUrl && <a className="al-c wa" href={waUrl} target="_blank" rel="noopener" data-native="1" aria-label={`WhatsApp ${a.full_name}`}><i aria-hidden="true" className="fab fa-whatsapp" /></a>}
                    {a.email && <a className="al-c mail" href={'mailto:' + a.email} aria-label={`Email ${a.full_name}`} title={a.email}><i aria-hidden="true" className="fas fa-envelope" /></a>}
                    {a.linkedin && <a className="al-c in" href={a.linkedin} target="_blank" rel="noopener" data-native="1" aria-label="LinkedIn profile"><i aria-hidden="true" className="fab fa-linkedin-in" /></a>}
                    {!a.phone && !a.email && !a.linkedin && <span className="pm-dim al-none">No contact details</span>}
                    <a href={a.profile_url} className="pm-btn al-view">Profile <i aria-hidden="true" className="fas fa-chevron-right" /></a>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="pm-card-b"><Empty icon="fa-address-book" title={anyFilter ? 'No alumni match' : 'No alumni yet'}>
            <p>{anyFilter ? 'Try removing a filter or searching another name.' : 'Graduates appear here once students are marked as graduated.'}</p>
            {anyFilter && <div className="empty-state-actions"><button type="button" className="btn btn-secondary" onClick={clearFilters}><i aria-hidden="true" className="fas fa-rotate-left" /> Clear filters</button></div>}
          </Empty></div>
        )}
        {alumni.length > 0 && <p className="pm-foot">{alumni.length} of {d.total} alumni</p>}
      </section>

      {more && (
        <PmSheet title="More filters" onClose={() => setMore(false)}>
          <div className="al-filters">
            {ALUMNI_TEXT_FILTERS.map(([k, lab, ic]) => (
              <label key={k} className="pm-field"><span><i aria-hidden="true" className={'fas ' + ic} /> {lab}</span>
                <input className="pm-input" value={f[k] || ''} onChange={(e) => setF((x) => ({ ...x, [k]: e.target.value }))}
                       onKeyDown={(e) => { if (e.key === 'Enter') { apply(f); setMore(false); } }} /></label>))}
          </div>
          <button type="button" className="pm-btn primary big wide" onClick={() => { apply({ ...f, q }); setMore(false); }}>Show results</button>
          <button type="button" className="pm-btn wide" onClick={() => { clearFilters(); setMore(false); }}>Clear all filters</button>
        </PmSheet>
      )}

      {mail.open && (
        <PmSheet title="Email alumni" onClose={() => setMail((m) => ({ ...m, open: false }))}>
          <p className="al-to"><i aria-hidden="true" className="fas fa-users" /> Goes to <b>{d.contactable}</b> alumni with an email address{anyFilter ? ' in this filtered list' : ''}.</p>
          {!d.email_configured && <p className="al-warn"><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Email isn’t set up on this server yet, so sending will fail until SMTP is configured.</p>}
          <label className="pm-field"><span>Subject</span>
            <input className="pm-input" value={mail.subject} onChange={(e) => setMail((m) => ({ ...m, subject: e.target.value }))} placeholder="e.g. Homecoming 2026" /></label>
          <label className="pm-field" style={{ marginTop: '.6rem' }}><span>Message</span>
            <textarea className="pm-input al-ta" rows={6} value={mail.body} onChange={(e) => setMail((m) => ({ ...m, body: e.target.value }))} /></label>
          <button type="button" className="pm-btn primary big wide" disabled={mail.busy || !d.email_configured || !d.contactable} onClick={sendMail}>
            <i aria-hidden="true" className={'fas ' + (mail.busy ? 'fa-spinner fa-spin' : 'fa-paper-plane')} /> Send to {d.contactable} alumni</button>
        </PmSheet>
      )}
    </div>
  );
}

// ---- Alumni analytics -----------------------------------------------------
function BreakdownCard({ title, icon, rows }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return null;
  return (
    <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className={'fas ' + icon} /> {title}</h3></div>
      <div className="card-body">{rows.map((r, i) => (
        <div key={i} style={{ marginBottom: '.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.9rem' }}><span>{r.label}</span><strong>{r.count}</strong></div>
          <div style={{ height: 8, background: 'var(--border-color,#eee)', borderRadius: 6, overflow: 'hidden' }}>
            <div style={{ width: `${(r.count / max) * 100}%`, height: '100%', background: 'var(--primary,#0d6a4e)' }} /></div>
        </div>))}</div></div>
  );
}

function AlumniAnalytics({ d }) {
  const req = d.requests || {};
  return (
    <>
      <PageHeader title="Alumni Analytics" actions={
        <a href={d.alumni_dir} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Directory</a>} />
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-user-graduate" /></div><div className="stat-content"><h3>{d.total}</h3><p>Graduates</p></div></div>
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-id-badge" /></div><div className="stat-content"><h3>{d.with_profile}</h3><p>With alumni profile</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-briefcase" /></div><div className="stat-content"><h3>{d.employed}</h3><p>Employed</p></div></div>
        <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-graduation-cap" /></div><div className="stat-content"><h3>{d.higher_ed}</h3><p>In higher education</p></div></div>
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-hands-helping" /></div><div className="stat-content"><h3>{d.mentors}</h3><p>Willing to mentor</p></div></div>
        <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-address-card" /></div><div className="stat-content"><h3>{d.contactable}</h3><p>Contactable</p></div></div>
      </div>
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon primary"><i aria-hidden="true" className="fas fa-file-signature" /></div><div className="stat-content"><h3>{d.docs_total}</h3><p>Documents issued</p></div></div>
        <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-hourglass-half" /></div><div className="stat-content"><h3>{req.pending || 0}</h3><p>Requests pending</p></div></div>
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-check" /></div><div className="stat-content"><h3>{req.fulfilled || 0}</h3><p>Requests fulfilled</p></div></div>
        <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-xmark" /></div><div className="stat-content"><h3>{req.declined || 0}</h3><p>Requests declined</p></div></div>
      </div>
      <BreakdownCard title="By graduation session" icon="fa-calendar" rows={d.by_session || []} />
      <BreakdownCard title="By status" icon="fa-flag" rows={d.by_status || []} />
      <BreakdownCard title="Top employers" icon="fa-building" rows={d.top_employers || []} />
      <BreakdownCard title="Top institutions" icon="fa-university" rows={d.top_institutions || []} />
      <BreakdownCard title="Top occupations" icon="fa-briefcase" rows={d.top_occupations || []} />
      <BreakdownCard title="Top locations" icon="fa-location-dot" rows={d.top_locations || []} />
      <BreakdownCard title="Documents by type" icon="fa-file-lines" rows={d.docs_by_type || []} />
    </>
  );
}

// ---- Document branding studio --------------------------------------------
function BrandingStudio({ d, notify }) {
  const nav = useNav();
  const b = d.branding || {};
  const [primary, setPrimary] = useState(b.primary_color || '');
  const [accent, setAccent] = useState(b.accent_color || '');
  const [secondary, setSecondary] = useState(b.secondary_color || '');
  const [motto, setMotto] = useState(b.motto || '');
  const [verify, setVerify] = useState(b.verify_enabled !== false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const save = async () => {
    setBusy(true);
    const r = await submitJson(d.branding_save_url, {
      primary_color: primary, accent_color: accent, secondary_color: secondary,
      motto, verify_enabled: verify ? '1' : '0',
    });
    setBusy(false);
    if (r.ok) { notify && notify('success', r.message || 'Branding saved.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not save branding.');
  };
  const swatch = (label, val, set) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: '.25rem', fontSize: '.85rem' }}>
      <span className="text-muted">{label}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
        <input type="color" value={val || '#0e3a2f'} onChange={(e) => set(e.target.value)}
          style={{ width: 40, height: 32, padding: 0, border: '1px solid var(--border,#cbd5e1)', borderRadius: 6 }} />
        <input type="text" value={val} placeholder="default" onChange={(e) => set(e.target.value)}
          className="form-control" style={{ width: 100 }} />
        {val && <button type="button" className="btn btn-secondary btn-sm" onClick={() => set('')}>Reset</button>}
      </span>
    </label>
  );
  return (
    <div className="card mb-3"><div className="card-body">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setOpen((o) => !o)}>
        <strong><i aria-hidden="true" className="fas fa-palette" /> Branding studio</strong>
        <span className="text-muted text-sm">Colours &amp; motto override every design · <i className={'fas fa-chevron-' + (open ? 'up' : 'down')} aria-hidden="true" /></span>
      </div>
      {open && <div style={{ marginTop: '.9rem' }}>
        <div style={{ display: 'flex', gap: '1.2rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          {swatch('Primary', primary, setPrimary)}
          {swatch('Accent', accent, setAccent)}
          {swatch('Secondary / gold', secondary, setSecondary)}
          <label style={{ display: 'flex', flexDirection: 'column', gap: '.25rem', fontSize: '.85rem', flex: '1 1 220px' }}>
            <span className="text-muted">Motto</span>
            <input type="text" value={motto} onChange={(e) => setMotto(e.target.value)}
              className="form-control" placeholder="e.g. Knowledge, Integrity, Service" maxLength={160} />
          </label>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem', marginTop: '.8rem', fontSize: '.9rem' }}>
          <input type="checkbox" checked={verify} onChange={(e) => setVerify(e.target.checked)} />
          Show QR verification block on issued documents
        </label>
        {canWrite(d, 'documents_templates') && <div style={{ marginTop: '.9rem' }}>
          <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={save}>
            <i aria-hidden="true" className="fas fa-save" /> {busy ? 'Saving…' : 'Save branding'}</button>
          <span className="text-muted text-sm" style={{ marginLeft: '.6rem' }}>Previews update after saving.</span>
        </div>}
      </div>}
    </div></div>
  );
}

// ---- Document design templates (admin) ------------------------------------
function DocTemplates({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState('');
  const setDefault = async (t) => {
    setBusy(t.key);
    const r = await submitJson(t.set_url, { template_key: t.key });
    setBusy('');
    if (r.ok) { notify && notify('success', r.message || 'Default set.'); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not set default.');
  };
  const groups = d.doc_types_grouped || [];
  return (
    <>
      <PageHeader title="Document Designs" actions={
        <a href={d.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>} />
      {d.branding_save_url && <BrandingStudio d={d} notify={notify} />}
      {groups.length > 0 ? (
        <div className="mb-3">
          {groups.map((g) => (
            <div key={g.category} style={{ marginBottom: '.6rem' }}>
              <div className="text-muted text-sm" style={{ marginBottom: '.3rem', textTransform: 'uppercase', letterSpacing: '.03em' }}>{g.category}</div>
              <div style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
                {g.items.map((dt) => (
                  <a key={dt.key} href={dt.url} className={'btn btn-sm ' + (dt.key === d.doc_type ? 'btn-primary' : 'btn-secondary')}>{dt.label}</a>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (d.doc_types && d.doc_types.length > 1 && <div className="tabs mb-3" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
        {d.doc_types.map((dt) => (
          <a key={dt.key} href={dt.url} className={'btn btn-sm ' + (dt.key === d.doc_type ? 'btn-primary' : 'btn-secondary')}>{dt.label}</a>
        ))}</div>)}
      <div className="card mb-3"><div className="card-body">
        <p className="text-muted" style={{ margin: 0 }}>
          <i aria-hidden="true" className="fas fa-circle-info" /> Choose the design used when you issue a {d.doc_type_label.toLowerCase()}.
          Every design shows your school's own details — only the layout changes. Previews use sample data.
        </p></div></div>
      <div className="data-cards">
        {(d.templates || []).map((t) => (
          <div className="data-card" key={t.key} style={t.is_default ? { borderColor: 'var(--primary,#0e8a64)', borderWidth: 2 } : null}>
            <div className="data-card-header">
              <div className="data-card-title">{t.name}</div>
              {t.is_default ? <span className="badge badge-success"><i aria-hidden="true" className="fas fa-check" /> Default</span>
                : <span className="badge badge-secondary">Available</span>}
            </div>
            <p className="text-sm text-muted" style={{ minHeight: '2.6em' }}>{t.description}</p>
            <div className="data-card-actions">
              <a href={t.preview_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm w-100">
                <i aria-hidden="true" className="fas fa-eye" /> Preview</a>
              {canWrite(d, 'documents_templates') && <button type="button" className="btn btn-primary btn-sm w-100" style={{ marginTop: '.4rem' }}
                disabled={t.is_default || busy === t.key} onClick={() => setDefault(t)}>
                <i aria-hidden="true" className="fas fa-star" /> {t.is_default ? 'Current default' : 'Set as default'}</button>}
            </div>
          </div>))}
      </div>
    </>
  );
}

// ---- Document verification activity (admin) -------------------------------
const _VBADGE = { valid: 'badge-success', revoked: 'badge-danger', not_found: 'badge-warning' };
const _VLABEL = { valid: 'Valid', revoked: 'Revoked', not_found: 'Unknown code' };

function VerifyRow({ v }) {
  return (
    <tr>
      <td>{v.at}</td>
      <td><span className={'badge ' + (_VBADGE[v.result] || 'badge-secondary')}>{_VLABEL[v.result] || v.result}</span></td>
      <td>{v.doc_label}</td>
      <td>{v.student_url ? <a href={v.student_url}>{v.student}</a> : (v.student || '—')}</td>
      <td><code>{v.code}</code></td>
      <td>{v.source === 'qr' ? <span title="QR link scanned"><i aria-hidden="true" className="fas fa-qrcode" /> Scan</span> : 'Typed'}</td>
    </tr>
  );
}

function DocVerifications({ d }) {
  const nav = useNav();
  const s = d.summary || {};
  const table = (rows) => (
    <div className="table-responsive"><table className="data-table"><thead><tr>
      <th>When</th><th>Result</th><th>Document</th><th>Graduate</th><th>Code</th><th>Via</th>
    </tr></thead><tbody>{rows.map((v) => <VerifyRow key={v.id} v={v} />)}</tbody></table></div>
  );
  return (
    <>
      <PageHeader title="Verification Activity" actions={
        <a href={d.urls.graduates} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Graduates</a>} />
      <div className="card mb-3"><div className="card-body"><div className="filter-form">
        <div className="form-group"><label className="form-label">Period</label>
          <select className="form-control" value={d.days} onChange={(e) => navParams(nav.go, window.location.pathname, { days: e.target.value })}>
            {[30, 90, 180, 365].map((n) => <option key={n} value={n}>Last {n} days</option>)}</select></div>
      </div></div></div>
      <div className="stats-grid mb-3">
        <div className="stat-card"><div className="stat-icon info"><i aria-hidden="true" className="fas fa-magnifying-glass" /></div><div className="stat-content"><h3>{s.total || 0}</h3><p>Total checks</p></div></div>
        <div className="stat-card"><div className="stat-icon success"><i aria-hidden="true" className="fas fa-circle-check" /></div><div className="stat-content"><h3>{s.valid || 0}</h3><p>Verified genuine</p></div></div>
        <div className="stat-card"><div className="stat-icon secondary"><i aria-hidden="true" className="fas fa-ban" /></div><div className="stat-content"><h3>{s.revoked || 0}</h3><p>Revoked-doc checks</p></div></div>
        <div className="stat-card"><div className="stat-icon warning"><i aria-hidden="true" className="fas fa-triangle-exclamation" /></div><div className="stat-content"><h3>{s.not_found || 0}</h3><p>Unknown codes</p></div></div>
      </div>
      <div className="card mb-3"><div className="card-body">
        <p className="text-muted" style={{ margin: 0 }}>
          <i aria-hidden="true" className="fas fa-shield-halved" /> Every public check of one of your documents is logged here — no personal data about the person checking is stored, only a privacy-safe daily fingerprint.
        </p></div></div>
      <div className="card mb-3"><div className="card-header"><h3>Recent checks</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          {(d.rows || []).length ? table(d.rows)
            : <div style={{ padding: '1rem' }}><Empty icon="fa-magnifying-glass" title="No checks yet"><p>Nobody has verified one of your documents in this period.</p></Empty></div>}
        </div></div>
      {(d.unknown || []).length > 0 && <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Unknown-code attempts</h3></div>
        <div className="card-body" style={{ padding: 0 }}>{table(d.unknown)}</div></div>}
    </>
  );
}

const SCREENS = { index: Index, rules: Rules, add_rule: AddRule, process: Process,
  graduates: Graduates, graduate_preview: GraduatePreview, graduate_profile: GraduateProfile,
  graduate_compare: GraduateCompare, history: History, alumni: Alumni,
  alumni_analytics: AlumniAnalytics, doc_templates: DocTemplates,
  doc_verifications: DocVerifications };

export default function PromotionApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  // Remount the Process screen whenever its student set changes (new class/
  // session), so row state is re-derived instead of going stale — otherwise
  // rows[i] is undefined for the new list and the render crashes.
  const screenKey = d.page === 'process'
    ? 'process:' + (d.students || []).map((s) => s.id).join('-')
    : d.page;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen key={screenKey} d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
