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
const GP_TABS = [
  { key: 'overview', label: 'Overview', icon: 'fa-user' },
  { key: 'results', label: 'Results', icon: 'fa-file-lines' },
  { key: 'documents', label: 'Documents', icon: 'fa-file-signature' },
  { key: 'records', label: 'School record', icon: 'fa-folder-open' },
];
const ALUMNI_FIELDS = [['occupation', 'Occupation'], ['job_title', 'Job title'], ['employer', 'Employer'],
  ['higher_institution', 'University / institution'], ['course_of_study', 'Course of study'],
  ['phone', 'Phone'], ['email', 'Email'], ['linkedin_url', 'LinkedIn URL'], ['city', 'City'], ['country', 'Country']];
const CREDIT = new Set(['A1', 'B2', 'B3', 'C4', 'C5', 'C6']);

// One WAEC/NECO sitting: grade chips in a two-column grid.
function GpGrades({ data, label }) {
  const credits = data.subjects.filter((r) => CREDIT.has(r.grade)).length;
  return (
    <div className="gp2-exam">
      <div className="gp2-exam-h"><b>{data.exam_year}</b>
        <span className="pm-dim">{data.subjects.length} subjects · {credits} credit{credits === 1 ? '' : 's'}{data.exam_number ? ` · ${label} ${data.exam_number}` : ''}</span></div>
      <ul className="gp2-grades">
        {data.subjects.map((r, j) => (
          <li key={j}><span>{r.subject}</span><span className={'badge ' + (WAEC_GRADE_BADGE[r.grade] || 'badge-secondary')}>{r.grade}</span></li>))}
      </ul>
    </div>
  );
}

function GraduateProfile({ d, notify }) {
  const s = d.student;
  const rec = d.record || {};
  const bio = rec.bio || {};
  const nav = useNav();
  const phone = usePhone();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(d.status || 'Graduated');
  const [reason, setReason] = useState('');
  const [alu, setAlu] = useState(d.alumni || {});
  const [pw, setPw] = useState('');
  const [editAlu, setEditAlu] = useState(false);
  const [tab, setTabState] = useState(() => {
    const h = (window.location.hash || '').slice(1);
    return GP_TABS.some((t) => t.key === h) ? h : 'overview';
  });
  const setTab = (k) => { setTabState(k); try { window.history.replaceState(null, '', '#' + k); } catch (e) { /* ignore */ } };
  const setAluField = (k, v) => setAlu((a) => ({ ...a, [k]: v }));
  const saveAlumni = async () => {
    setBusy(true);
    const r = await submitJson(d.alumni_save_url, alu);
    setBusy(false);
    if (r.ok) { notify && notify('success', r.message || 'Alumni details saved.'); setEditAlu(false); }
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

  const saved = d.alumni || {};
  const tone = GRAD_STATUS_TONE[d.status] || 'info';
  const docs = d.documents || [];
  const issued = docs.filter((x) => x.number && !x.revoked).length;
  const reqs = d.doc_requests || [];
  const pending = reqs.filter((r) => r.status === 'pending').length;
  const latestWaec = (d.waec_by_year || [])[0];
  const waecCredits = latestWaec ? latestWaec.subjects.filter((r) => CREDIT.has(r.grade)).length : null;
  const jambBest = (d.jamb_results || []).length ? Math.max(...d.jamb_results.map((j) => Number(j.total_score) || 0)) : null;
  const callNo = saved.phone || ((d.contacts || [])[0] || {}).phone;
  const canStatus = d.urls.change_status && canWrite(d, 'promote_graduate_status');
  const canPortal = d.set_password_url && d.is_admin;
  const canAlu = d.alumni_save_url && canWrite(d, 'graduates_alumni_edit');
  const moreItems = [
    { href: d.urls.full_profile, icon: 'fa-user', label: 'Full student profile' },
    { href: d.urls.graduates, icon: 'fa-arrow-left', label: 'Back to graduates' },
    d.urls.ungraduate && canWrite(d, 'promote_graduate_status') && { onClick: undoGraduate, icon: 'fa-rotate-left', label: 'Un-graduate…' },
  ];
  const work = saved.employer || saved.higher_institution;
  const role = saved.job_title || saved.occupation || saved.course_of_study;

  // ---- Panels (laptop rail; on phones they sit at the end of Overview) ----
  const railPanels = (<>
    <section className="pm-card">
      <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-graduation-cap" /></span>
        <div className="pm-card-t"><h3>Graduation</h3></div></header>
      <dl className="gp2-kv">
        <div><dt>Status</dt><dd><span className={'grad-status tone-' + tone}><span className="dot" aria-hidden="true" />{d.status || 'Graduated'}</span></dd></div>
        {d.graduation_date && <div><dt>Graduated</dt><dd>{d.graduation_date}</dd></div>}
        {d.graduation_session && <div><dt>Class of</dt><dd>{d.graduation_session}</dd></div>}
        {rec.admission_session && <div><dt>Admitted</dt><dd>{rec.admission_session}</dd></div>}
      </dl>
    </section>
    {canStatus && (
      <section className="pm-card">
        <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-arrows-turn-right" /></span>
          <div className="pm-card-t"><h3>Update status</h3><small>Recorded in the history with your reason</small></div></header>
        <div className="pm-card-b gp2-form">
          <label className="pm-field"><span>New status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {(d.statuses || []).map((st) => <option key={st} value={st}>{st}</option>)}</select></label>
          <label className="pm-field"><span>Reason</span>
            <textarea className="pm-input gp2-ta" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Certificate collected on 12 Aug" /></label>
          <button type="button" className="pm-btn primary wide" disabled={busy || status === (d.status || 'Graduated')} onClick={saveStatus}><i aria-hidden="true" className="fas fa-check" /> Update status</button>
        </div>
      </section>
    )}
    {canPortal && (
      <section className="pm-card">
        <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-key" /></span>
          <div className="pm-card-t"><h3>Alumni portal access</h3><small>They can also sign in with any document’s verification code</small></div></header>
        <div className="pm-card-b gp2-form">
          <label className="pm-field"><span>New password</span>
            <input className="pm-input" type="text" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="At least 6 characters" /></label>
          <button type="button" className="pm-btn wide" disabled={busy || pw.length < 6} onClick={savePassword}><i aria-hidden="true" className="fas fa-key" /> Set password</button>
          {d.alumni_login_url && <a className="gp2-link" href={d.alumni_login_url} target="_blank" rel="noopener noreferrer" data-native="1"><i aria-hidden="true" className="fas fa-link" /> {d.alumni_login_url}</a>}
        </div>
      </section>
    )}
  </>);

  return (
    <div className="pm gp2">
      <header className="gp2-head">
        <div className="gp2-band" aria-hidden="true" />
        <div className="gp2-head-row">
          {bio.photo_url ? <img className="gp2-av" src={bio.photo_url} alt="" />
            : <span className="gp2-av ph" aria-hidden="true">{pmInitials(s.full_name)}</span>}
          <div className="gp2-id">
            <h1>{s.full_name}</h1>
            <div className="gp2-chips">
              <span className="gp2-chip id">{s.student_id}</span>
              {s.gender && <span className="gp2-chip"><i aria-hidden="true" className={'fas ' + (s.gender === 'Male' ? 'fa-mars' : 'fa-venus')} /> {s.gender}</span>}
              <span className={'gp2-chip grad-status tone-' + tone}><span className="dot" aria-hidden="true" />{d.status || 'Graduated'}</span>
              {d.graduation_session && <span className="gp2-chip"><i aria-hidden="true" className="fas fa-user-graduate" /> Class of {d.graduation_session}</span>}
            </div>
            {(role || work) && <p className="gp2-now"><i aria-hidden="true" className="fas fa-briefcase" /> {role}{role && work ? ' · ' : ''}{work && <b>{work}</b>}{saved.city ? ` · ${saved.city}` : ''}</p>}
          </div>
          {!phone && (
            <div className="gp2-acts">
              <a href={d.urls.full_profile} className="pm-btn"><i aria-hidden="true" className="fas fa-user" /> Full profile</a>
              <PmMenu items={moreItems} />
            </div>
          )}
        </div>
        {phone && (
          <div className="gp2-quick">
            {callNo ? <a className="gp2-qa" href={'tel:' + callNo}><span className="gp2-round call"><i aria-hidden="true" className="fas fa-phone" /></span>Call</a> : null}
            {saved.email ? <a className="gp2-qa" href={'mailto:' + saved.email}><span className="gp2-round"><i aria-hidden="true" className="fas fa-envelope" /></span>Email</a> : null}
            <button type="button" className="gp2-qa" onClick={() => setTab('documents')}><span className="gp2-round"><i aria-hidden="true" className="fas fa-file-signature" /></span>Documents</button>
            {canAlu && <button type="button" className="gp2-qa" onClick={() => setEditAlu(true)}><span className="gp2-round"><i aria-hidden="true" className="fas fa-pen" /></span>Edit</button>}
            <div className="gp2-qa"><PmMenu items={moreItems} icon="fa-ellipsis" label="More" /><span>More</span></div>
          </div>
        )}
      </header>

      <PmTiles items={[
        rec.academic && rec.academic.cumulative != null ? { label: 'Overall average', icon: 'fa-chart-line', value: `${rec.academic.cumulative}%`, sub: `${rec.academic.terms_count} terms`, onClick: () => setTab('records') } : null,
        latestWaec ? { label: `WAEC ${latestWaec.exam_year}`, icon: 'fa-file-alt', value: waecCredits, sub: `credits of ${latestWaec.subjects.length}`, tone: waecCredits >= 5 ? 'good' : 'warn', onClick: () => setTab('results') }
          : { label: 'WAEC', icon: 'fa-file-alt', value: '—', sub: 'no result yet', tone: 'warn', onClick: () => setTab('results') },
        jambBest != null ? { label: 'JAMB', icon: 'fa-file-contract', value: jambBest, sub: 'best score / 400', tone: jambBest >= 200 ? 'good' : 'warn', onClick: () => setTab('results') } : null,
        { label: 'Documents', icon: 'fa-file-signature', value: `${issued}/${docs.length}`, sub: pending ? `${pending} request${pending === 1 ? '' : 's'} waiting` : 'issued', tone: pending ? 'warn' : '', onClick: () => setTab('documents') },
        rec.attendance && rec.attendance.total > 0 ? { label: 'Attendance', icon: 'fa-calendar-check', value: `${rec.attendance.percent}%`, sub: 'while at school' } : null,
        rec.finance && Number(rec.finance.total_paid) > 0 ? { label: 'Fees paid', icon: 'fa-receipt', value: NGN(rec.finance.total_paid), onClick: () => setTab('records') } : null,
      ]} />

      <nav className="gp2-tabs" role="tablist" aria-label="Graduate sections">
        {GP_TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? 'on' : ''} onClick={() => setTab(t.key)}>
            {!phone && <i aria-hidden="true" className={'fas ' + t.icon} />}{phone && t.key === 'records' ? 'Record' : t.label}
            {t.key === 'documents' && pending > 0 && <span className="gp2-n">{pending}</span>}
          </button>))}
      </nav>

      <div className="gp2-cols">
        <main className="gp2-main">
          {tab === 'overview' && (<>
            <section className="pm-card">
              <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-id-badge" /></span>
                <div className="pm-card-t"><h3>Alumni details</h3>
                  <small>{saved.updated_at ? `Updated ${saved.updated_at}${saved.updated_by ? ' by ' + saved.updated_by : ''}` : 'Not filled in yet'}</small></div>
                {canAlu && <button type="button" className="pm-btn" onClick={() => setEditAlu(true)}><i aria-hidden="true" className="fas fa-pen" /> <span>Edit</span></button>}
              </header>
              <dl className="gp2-kv grid">
                {ALUMNI_FIELDS.filter(([k]) => saved[k]).map(([k, lab]) => (
                  <div key={k}><dt><i aria-hidden="true" className={'fas ' + ALUMNI_FIELD_ICONS[k]} /> {lab}</dt>
                    <dd>{k === 'phone' ? <a href={'tel:' + saved[k]}>{saved[k]}</a> : k === 'email' ? <a href={'mailto:' + saved[k]}>{saved[k]}</a>
                      : k === 'linkedin_url' ? <a href={saved[k]} target="_blank" rel="noopener noreferrer" data-native="1">LinkedIn profile</a> : saved[k]}</dd></div>))}
                {saved.willing_to_mentor && <div><dt><i aria-hidden="true" className="fas fa-hands-helping" /> Mentoring</dt><dd>Willing to mentor current students</dd></div>}
                {saved.achievements && <div className="wide"><dt><i aria-hidden="true" className="fas fa-trophy" /> Achievements</dt><dd>{saved.achievements}</dd></div>}
              </dl>
              {!ALUMNI_FIELDS.some(([k]) => saved[k]) && !saved.achievements && (
                <p className="pm-empty">No career, study or contact details yet.{canAlu ? ' Tap Edit to add them.' : ''}</p>)}
            </section>

            {d.status_history && d.status_history.length > 0 && (
              <section className="pm-card">
                <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-clock-rotate-left" /></span>
                  <div className="pm-card-t"><h3>Status history</h3><small>{d.status_history.length} change{d.status_history.length === 1 ? '' : 's'}</small></div></header>
                <ol className="gp2-tl">
                  {d.status_history.map((h, i) => (
                    <li key={i} className={i === 0 ? 'now' : ''}>
                      <div>{h.old || '—'} <i aria-hidden="true" className="fas fa-arrow-right" /> <b>{h.new}</b></div>
                      <small>{h.reason ? h.reason + ' · ' : ''}{h.at}{h.actor ? ` · by ${h.actor}` : ''}</small>
                    </li>))}
                </ol>
              </section>
            )}

            {d.contacts.length > 0 && (
              <section className="pm-card">
                <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-address-book" /></span>
                  <div className="pm-card-t"><h3>Family contacts</h3><small>From the school record</small></div></header>
                <ul className="pm-people">
                  {d.contacts.map((c, i) => (
                    <li key={i} className="pm-person">
                      <span className="pm-av" aria-hidden="true">{pmInitials(c.name)}</span>
                      <span className="pm-pn"><strong>{c.name}</strong><small>{c.relationship}{c.phone ? ` · ${c.phone}` : ''}</small></span>
                      {c.phone && <a className="al-c call" href={'tel:' + c.phone} aria-label={`Call ${c.name}`}><i aria-hidden="true" className="fas fa-phone" /></a>}
                    </li>))}
                </ul>
              </section>
            )}
            {phone && railPanels}
          </>)}

          {tab === 'results' && (<>
            {[['WAEC', 'fa-file-alt', d.waec_by_year || [], d.urls.add_waec, 'Exam No.'], ['NECO', 'fa-file-lines', d.neco_by_year || [], d.urls.add_neco, 'Reg No.']].map(([nm, ic, list, add, lab]) => (
              <section className="pm-card" key={nm}>
                <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className={'fas ' + ic} /></span>
                  <div className="pm-card-t"><h3>{nm}</h3><small>{list.length ? `${list.length} sitting${list.length === 1 ? '' : 's'}` : 'No results recorded'}</small></div>
                  {canWrite(d) && add && <a href={add} className="pm-btn"><i aria-hidden="true" className="fas fa-plus" /> <span>Add</span></a>}</header>
                {list.length ? <div className="pm-card-b gp2-exams">{list.map((data, i) => <GpGrades key={i} data={data} label={lab} />)}</div>
                  : <p className="pm-empty">No {nm} results recorded yet.</p>}
              </section>
            ))}
            <section className="pm-card">
              <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-file-contract" /></span>
                <div className="pm-card-t"><h3>JAMB</h3><small>{d.jamb_results.length ? `${d.jamb_results.length} sitting${d.jamb_results.length === 1 ? '' : 's'}` : 'No results recorded'}</small></div>
                {canWrite(d) && <a href={d.urls.add_jamb} className="pm-btn"><i aria-hidden="true" className="fas fa-plus" /> <span>Add</span></a>}</header>
              {d.jamb_results.length ? (
                <div className="pm-card-b gp2-exams">
                  {d.jamb_results.map((j, i) => (
                    <div className="gp2-exam" key={i}>
                      <div className="gp2-exam-h"><b>{j.exam_year}</b><span className="gp2-score">{j.total_score}<small>/400</small></span>
                        {j.registration_number && <span className="pm-dim">Reg No. {j.registration_number}</span>}</div>
                      <ul className="gp2-jamb">
                        {j.subjects.map((sub, k) => (
                          <li key={k}><span>{sub.name}</span><span className="aa-track"><i style={{ width: `${Math.min(100, Number(sub.score) || 0)}%` }} /></span><b>{sub.score}</b></li>))}
                      </ul>
                    </div>))}
                </div>
              ) : <p className="pm-empty">No JAMB results recorded yet.</p>}
            </section>
          </>)}

          {tab === 'documents' && (<>
            {reqs.length > 0 && (
              <section className="pm-card">
                <header className="pm-card-h"><span className="pm-card-ic warn"><i aria-hidden="true" className="fas fa-inbox" /></span>
                  <div className="pm-card-t"><h3>Requests from the alumni portal</h3><small>{pending ? `${pending} waiting` : 'All handled'}</small></div></header>
                <ul className="pm-people">
                  {reqs.map((r) => (
                    <li key={r.id} className="pm-person al-req">
                      <span className="pm-card-ic"><i aria-hidden="true" className="fas fa-file" /></span>
                      <span className="pm-pn"><strong>{r.label}</strong><small>Requested {r.requested_at}{r.note ? ` · “${r.note}”` : ''}</small></span>
                      {r.status === 'pending' ? (canWrite(d, 'documents_requests') ? <span className="al-req-a">
                        <button type="button" className="pm-btn primary" onClick={() => fulfilReq(r)}><i aria-hidden="true" className="fas fa-file-arrow-down" /> <span>Issue</span></button>
                        <button type="button" className="pm-icon danger" onClick={() => declineReq(r)} aria-label="Decline" title="Decline"><i aria-hidden="true" className="fas fa-xmark" /></button>
                      </span> : <span className="badge badge-warning">pending</span>)
                        : <span className={'badge ' + (r.status === 'fulfilled' ? 'badge-success' : 'badge-secondary')}>{r.response_note || (r.status === 'fulfilled' ? 'Issued' : r.status === 'declined' ? 'Declined' : r.status)}</span>}
                    </li>))}
                </ul>
              </section>
            )}
            <section className="pm-card">
              <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-file-signature" /></span>
                <div className="pm-card-t"><h3>Documents</h3><small>Each PDF carries a QR code and number anyone can verify</small></div></header>
              {docs.length ? (
                <ul className="gp2-docs">
                  {docs.map((doc) => {
                    const st = doc.revoked ? 'revoked' : doc.number ? 'issued' : 'none';
                    return (
                      <li key={doc.type} className={'gp2-doc ' + st}>
                        <span className="gp2-doc-ic"><i aria-hidden="true" className={'fas ' + (doc.revoked ? 'fa-file-circle-xmark' : doc.number ? 'fa-file-circle-check' : 'fa-file')} /></span>
                        <span className="pm-pn"><strong>{doc.label}</strong>
                          <small>{doc.revoked ? 'Revoked — verifies as invalid' : doc.number ? `No. ${doc.number}${doc.reprint_count ? ` · ${doc.reprint_count} reprint${doc.reprint_count === 1 ? '' : 's'}` : ''} · ${doc.verify_count ? `checked ${doc.verify_count}×` : 'not checked yet'}` : 'Not issued yet'}</small></span>
                        <span className="gp2-doc-a">
                          {doc.number && doc.verify_url && <a href={doc.verify_url} target="_blank" rel="noopener noreferrer" data-native="1" className="pm-icon" aria-label="Open verification page" title="Verification page"><i aria-hidden="true" className="fas fa-qrcode" /></a>}
                          {doc.number && doc.revoke_url && canWrite(d, 'documents_generate') && <button type="button" className="pm-icon danger" onClick={() => revokeDoc(doc)} aria-label={doc.revoked ? 'Reinstate' : 'Revoke'} title={doc.revoked ? 'Reinstate' : 'Revoke'}>
                            <i aria-hidden="true" className={'fas ' + (doc.revoked ? 'fa-rotate-left' : 'fa-ban')} /></button>}
                          {canWrite(d, 'documents_generate') && <a href={doc.download_url} target="_blank" rel="noopener noreferrer" data-native="1" className={'pm-btn' + (doc.number ? '' : ' primary')}>
                            <i aria-hidden="true" className={'fas ' + (doc.number ? 'fa-rotate' : 'fa-download')} /> <span>{doc.number ? 'Re-issue' : 'Generate'}</span></a>}
                        </span>
                      </li>);
                  })}
                </ul>
              ) : <p className="pm-empty">No document types are set up.</p>}
            </section>
          </>)}

          {tab === 'records' && (<>
            <section className="pm-card">
              <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-id-card" /></span>
                <div className="pm-card-t"><h3>Biodata</h3><small>Kept from their time at school</small></div></header>
              <dl className="gp2-kv grid">
                {[['Date of birth', bio.date_of_birth], ['Admission session', rec.admission_session], ['House', bio.house], ['Boarding', bio.boarding_status],
                  ['Stream', bio.stream], ['Religion', bio.religion], ['Blood group', bio.blood_group], ['Genotype', bio.genotype], ['Allergies', bio.allergies],
                  ['WAEC subjects', bio.waec_subjects], ['JAMB subjects', bio.jamb_subjects], ['JAMB reg. no.', bio.jamb_reg_number]]
                  .filter(([, v]) => v || v === 0).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
                {bio.home_address && <div className="wide"><dt>Address</dt><dd>{bio.home_address}</dd></div>}
              </dl>
            </section>

            {rec.academic && rec.academic.terms_count > 0 && (
              <section className="pm-card">
                <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-chart-line" /></span>
                  <div className="pm-card-t"><h3>Term results</h3><small>{rec.academic.terms_count} terms{rec.academic.cumulative != null ? ` · overall ${rec.academic.cumulative}%` : ''}</small></div></header>
                <div className="gp2-terms">
                  {rec.academic.terms.map((t, i) => (
                    <details key={i} className="gp2-term" open={i === 0}>
                      <summary><b>{t.session}</b> <span className="pm-dim">{t.term}</span>
                        {t.average != null && <span className={'pm-avg ' + (t.average >= 50 ? 'good' : 'bad')}>{t.average}%</span>}</summary>
                      <ul className="gp2-grades">
                        {t.subjects.map((sub, j) => <li key={j}><span>{sub.subject}</span><b>{sub.score}{sub.grade ? ` · ${sub.grade}` : ''}</b></li>)}
                      </ul>
                    </details>))}
                </div>
              </section>
            )}

            {rec.class_history && rec.class_history.length > 0 && (
              <section className="pm-card">
                <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-timeline" /></span>
                  <div className="pm-card-t"><h3>Classes</h3></div></header>
                <ol className="gp2-tl">
                  {rec.class_history.map((h, i) => (
                    <li key={i}><div><b>{h.klass} {h.arm}</b></div><small>{h.session} · {h.term}</small></li>))}
                </ol>
              </section>
            )}

            {rec.finance && rec.finance.recent && rec.finance.recent.length > 0 && (
              <section className="pm-card">
                <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-receipt" /></span>
                  <div className="pm-card-t"><h3>Fee payments</h3><small>{NGN(rec.finance.total_paid)} paid in total</small></div></header>
                <ul className="pm-people">
                  {rec.finance.recent.map((pmt, i) => (
                    <li key={i} className="pm-person"><span className="pm-pn"><strong>{NGN(pmt.amount)}</strong><small>{pmt.date} · {pmt.method || '—'}</small></span>
                      <span className="pm-dim">{pmt.receipt || ''}</span></li>))}
                </ul>
              </section>
            )}

            {rec.discipline && rec.discipline.length > 0 && (
              <section className="pm-card">
                <header className="pm-card-h"><span className="pm-card-ic warn"><i aria-hidden="true" className="fas fa-gavel" /></span>
                  <div className="pm-card-t"><h3>Discipline</h3><small>{rec.discipline.length} record{rec.discipline.length === 1 ? '' : 's'}</small></div></header>
                <ul className="pm-people">
                  {rec.discipline.map((r, i) => (
                    <li key={i} className="pm-person"><span className="pm-pn"><strong>{r.category}{r.severity ? ` · ${r.severity}` : ''}</strong>
                      <small>{r.date}{r.description ? ` — ${r.description}` : ''}</small></span><span className="pm-dim">{r.action || ''}</span></li>))}
                </ul>
              </section>
            )}
          </>)}
        </main>

        {!phone && <aside className="gp2-rail">{railPanels}</aside>}
      </div>

      {editAlu && (
        <PmSheet title="Alumni details" onClose={() => setEditAlu(false)}>
          <div className="gp2-editgrid">
            {ALUMNI_FIELDS.map(([k, lab]) => (
              <label key={k} className="pm-field"><span><i aria-hidden="true" className={'fas ' + ALUMNI_FIELD_ICONS[k]} /> {lab}</span>
                <input className="pm-input" value={alu[k] || ''} onChange={(e) => setAluField(k, e.target.value)}
                       type={k === 'email' ? 'email' : k === 'phone' ? 'tel' : 'text'} /></label>))}
          </div>
          <label className="pm-field" style={{ marginTop: '.6rem' }}><span><i aria-hidden="true" className="fas fa-trophy" /> Achievements</span>
            <textarea className="pm-input gp2-ta" rows={3} value={alu.achievements || ''} onChange={(e) => setAluField('achievements', e.target.value)} /></label>
          <label className="gp2-check"><input type="checkbox" checked={!!alu.willing_to_mentor} onChange={(e) => setAluField('willing_to_mentor', e.target.checked)} /> Willing to mentor current students</label>
          <button type="button" className="pm-btn primary big wide" disabled={busy} onClick={saveAlumni}><i aria-hidden="true" className="fas fa-check" /> Save details</button>
        </PmSheet>
      )}
    </div>
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
// One measure as two bars (graduates vs current SSS3), the better one ticked.
function VsMetric({ label, g, s, suffix = '', better = 'high', max, sNote, gNote }) {
  const top = max || Math.max(1, Number(g) || 0, Number(s) || 0);
  const has = (v) => v != null && !Number.isNaN(Number(v));
  let win = null;
  if (has(g) && has(s) && Number(g) !== Number(s)) win = (better === 'high' ? Number(g) > Number(s) : Number(g) < Number(s)) ? 'g' : 's';
  const bar = (v, who) => (
    <div className={'vs-bar ' + who + (win === who ? ' win' : '')}>
      <span className="vs-who">{who === 'g' ? 'Graduates' : 'SSS3'}</span>
      <span className="vs-track">{has(v) && <i style={{ width: `${Math.max(2, (Number(v) / top) * 100)}%` }} />}</span>
      <b>{has(v) ? v + suffix : ((who === 's' ? sNote : gNote) ? <small>{who === 's' ? sNote : gNote}</small> : '—')}{win === who && <i aria-hidden="true" className="fas fa-circle-check" />}</b>
    </div>
  );
  return <div className="vs-metric"><span className="vs-l">{label}</span>{bar(g, 'g')}{bar(s, 's')}</div>;
}

function VsBlock({ title, icon, sub, children }) {
  return (
    <section className="pm-card">
      <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className={'fas ' + icon} /></span>
        <div className="pm-card-t"><h3>{title}</h3>{sub && <small>{sub}</small>}</div></header>
      <div className="vs-body">{children}</div>
    </section>
  );
}

const WAEC_ROWS = (x) => (x ? [
  ['Students with results', x.n, '', 'high', null], ['Average credits (C6 or better)', x.avg_credits, '', 'high', 9],
  ['Average distinctions (B3 or better)', x.avg_distinctions, '', 'high', 9], ['5+ credits', x.pct_5_credits, '%', 'high', 100],
  ['5 credits incl. English & Maths', x.pct_5_incl_core, '%', 'high', 100]] : []);
const JAMB_ROWS = (x) => (x ? [
  ['Students with results', x.n, '', 'high', null], ['Average score', x.avg_score, '', 'high', 400],
  ['Highest score', x.max_score, '', 'high', 400], ['Scoring 180+', x.pct_above_floor, '%', 'high', 100]] : []);

// A cohort with nobody sitting the exam has no figures — show "no results"
// instead of comparing against a meaningless 0.
function VsTable({ g, s, rows, sNote }) {
  const gOk = g && g.n > 0, sOk = s && s.n > 0;
  const gr = rows(g || {}), sr = rows(s || {});
  return gr.map(([label, gv, suf, better, max], i) => (
    <VsMetric key={label} label={label} g={gOk || i === 0 ? (g ? gv : 0) : null} s={sOk || (i === 0 && s) ? sr[i][1] : null}
              suffix={suf} better={better} max={max}
              sNote={!s ? sNote : 'no results'} gNote="no results" />));
}

// Stacked grade spread for one cohort (share of all grades at each level).
const GRADE_TONE = { A1: '#15803d', B2: '#16a34a', B3: '#22c55e', C4: '#0ea5e9', C5: '#38bdf8', C6: '#7dd3fc', D7: '#f59e0b', E8: '#f97316', F9: '#ef4444' };
function GradeStack({ label, dist, order }) {
  const total = order.reduce((t, gr) => t + ((dist && dist[gr]) || 0), 0);
  return (
    <div className="vs-stack">
      <span className="vs-who">{label}<small>{total ? `${total} grades` : 'no grades'}</small></span>
      <div className="vs-stack-bar" role="img" aria-label={`${label} grade spread`}>
        {total ? order.filter((gr) => dist[gr]).map((gr) => (
          <span key={gr} style={{ flexGrow: dist[gr], background: GRADE_TONE[gr] || 'var(--gray-400)' }} title={`${gr}: ${dist[gr]} (${Math.round(dist[gr] / total * 100)}%)`}>
            {dist[gr] / total >= 0.07 ? gr : ''}</span>)) : <span style={{ flexGrow: 1, background: 'var(--gray-200)' }} />}
      </div>
    </div>
  );
}

function GraduateCompare({ d }) {
  const nav = useNav();
  const c = d.comparison;
  const cohorts = c.cohorts;
  const noData = cohorts.graduates.total === 0;
  const [tab, setTab] = useState('waec');
  const [sort, setSort] = useState('gap');
  const mg = c.mock_waec.graduates || {}, ms = c.mock_waec.sss3;
  const jg = c.mock_jamb.graduates || {}, js = c.mock_jamb.sss3;
  // Headline: how the current class compares on the same (mock) exams.
  const verdict = (() => {
    if (!ms || !(mg.n > 0) || !(ms.n > 0) || mg.pct_5_incl_core == null || ms.pct_5_incl_core == null) return null;
    const diff = Math.round((ms.pct_5_incl_core - mg.pct_5_incl_core) * 10) / 10;
    if (Math.abs(diff) < 2) return { tone: 'flat', text: 'Current SSS3 is level with the graduates on mock WAEC (5 credits incl. English & Maths).' };
    return diff > 0 ? { tone: 'good', text: `Current SSS3 is ahead of the graduates by ${diff} points on mock WAEC (5 credits incl. English & Maths).` }
      : { tone: 'bad', text: `Current SSS3 is behind the graduates by ${Math.abs(diff)} points on mock WAEC (5 credits incl. English & Maths).` };
  })();
  const dir = (p) => (p ? { cls: p.direction === 'improved' ? 'good' : p.direction === 'declined' ? 'bad' : '', sign: p.avg_delta > 0 ? '+' : '' } : null);

  const gMap = {}; (mg.subject_pass_rates || []).forEach((r) => { gMap[r.subject] = r.pass_rate; });
  const sMap = {}; ((ms && ms.subject_pass_rates) || []).forEach((r) => { sMap[r.subject] = r.pass_rate; });
  let subjects = Array.from(new Set([...Object.keys(gMap), ...Object.keys(sMap)])).map((sub) => ({
    sub, g: gMap[sub] != null ? gMap[sub] : null, s: sMap[sub] != null ? sMap[sub] : null,
    gap: (sMap[sub] != null && gMap[sub] != null) ? Math.round((sMap[sub] - gMap[sub]) * 10) / 10 : null }));
  if (sort === 'gap') subjects.sort((x, y) => (x.gap == null) - (y.gap == null) || (x.gap - y.gap));
  else subjects.sort((x, y) => x.sub.localeCompare(y.sub));
  const behind = subjects.filter((x) => x.gap != null && x.gap < 0).length;

  return (
    <div className="pm">
      <PmHead back={d.urls.graduates} kicker="Graduates" title="Graduates vs current SSS3"
              sub="See how this year’s SSS3 is tracking against a class that has already sat WAEC and JAMB." />

      <section className="pm-pick">
        <span className="pm-pick-l">Compare current SSS3 with</span>
        <div className="pm-chips" role="radiogroup" aria-label="Graduate cohort">
          <button type="button" role="radio" aria-checked={!d.session_id} className={!d.session_id ? 'on' : ''} onClick={() => navParams(nav.go, d.urls.self, {})}>All graduates</button>
          {d.sessions.map((x) => (
            <button key={x.id} type="button" role="radio" aria-checked={String(x.id) === String(d.session_id)}
                    className={String(x.id) === String(d.session_id) ? 'on' : ''} onClick={() => navParams(nav.go, d.urls.self, { session_id: x.id })}>Class of {x.name}</button>))}
        </div>
      </section>

      <section className="pm-card vs-hero">
        <div className="vs-cohort g"><span className="vs-dot" /><b>{cohorts.graduates.total}</b><span>{cohorts.graduates.label}</span></div>
        <span className="vs-vs">vs</span>
        <div className="vs-cohort s"><span className="vs-dot" /><b>{cohorts.sss3.total}</b><span>{cohorts.sss3.label}</span></div>
        {!noData && (c.projection.waec || c.projection.jamb) && (
          <div className="vs-proj">
            <span className="pm-kick"><i aria-hidden="true" className="fas fa-wand-magic-sparkles" /> Where current SSS3 may land</span>
            <div className="vs-proj-row">
              {c.projection.waec && <div><b>{c.projection.waec.projected_avg_credits}</b><span>WAEC credits (avg)</span><small>mock {c.projection.waec.mock_avg_credits} · shift {c.projection.waec.shift > 0 ? '+' : ''}{c.projection.waec.shift}</small></div>}
              {c.projection.jamb && <div><b>{c.projection.jamb.projected_avg_score}</b><span>JAMB score (avg)</span><small>mock {c.projection.jamb.mock_avg_score} · shift {c.projection.jamb.shift > 0 ? '+' : ''}{c.projection.jamb.shift}</small></div>}
            </div>
          </div>
        )}
      </section>

      {noData ? (
        <section className="pm-card"><div className="pm-card-b"><Empty icon="fa-chart-column" title="No graduates to compare">
          <p>Once a class has graduated with mock and real results recorded, this page compares them with the current SSS3.</p></Empty></div></section>
      ) : (<>
        {!(mg.n > 0) && !(c.real_waec.graduates && c.real_waec.graduates.n > 0) && !(jg.n > 0) && (
          <p className="vs-verdict"><i aria-hidden="true" className="fas fa-circle-info" /> These graduates have no mock or real WAEC/JAMB results recorded, so there’s nothing to compare yet — pick another class above, or add their results.</p>)}
        {verdict && <p className={'vs-verdict ' + verdict.tone}><i aria-hidden="true" className={'fas ' + (verdict.tone === 'good' ? 'fa-arrow-trend-up' : verdict.tone === 'bad' ? 'fa-arrow-trend-down' : 'fa-equals')} /> {verdict.text}</p>}

        <div className="vs-legend"><span><i className="g" />Graduates</span><span><i className="s" />Current SSS3</span>
          <small><i aria-hidden="true" className="fas fa-circle-check" /> marks the stronger cohort</small></div>

        <PmSeg label="Section" value={tab} onChange={setTab} options={[
          { value: 'waec', label: 'WAEC', icon: 'fa-file-alt' }, { value: 'jamb', label: 'JAMB', icon: 'fa-file-contract' },
          { value: 'subjects', label: 'Subjects', icon: 'fa-list-check' }, { value: 'pattern', label: 'Mock → real', icon: 'fa-arrow-trend-up' }]} />

        {tab === 'waec' && (<div className="vs-grid">
          <VsBlock title="Mock WAEC" icon="fa-clipboard-list" sub="Both classes on the same kind of exam (latest sitting)">
            <VsTable g={c.mock_waec.graduates} s={c.mock_waec.sss3} rows={WAEC_ROWS} sNote="no mock yet" /></VsBlock>
          <VsBlock title="Real WAEC" icon="fa-file-alt" sub="Only graduates have sat it so far">
            <VsTable g={c.real_waec.graduates} s={c.real_waec.sss3} rows={WAEC_ROWS} sNote="not sat yet" /></VsBlock>
          <VsBlock title="Grade spread" icon="fa-layer-group" sub="Share of all grades, best (A1) to worst (F9)">
            <GradeStack label="Graduates · real" dist={c.real_waec.graduates && c.real_waec.graduates.grade_distribution} order={c.grade_order} />
            <GradeStack label="Graduates · mock" dist={mg.grade_distribution} order={c.grade_order} />
            <GradeStack label="SSS3 · mock" dist={ms && ms.grade_distribution} order={c.grade_order} />
            <div className="vs-gkey">{c.grade_order.map((gr) => <span key={gr}><i style={{ background: GRADE_TONE[gr] }} />{gr}</span>)}</div>
          </VsBlock>
        </div>)}

        {tab === 'jamb' && (<div className="vs-grid">
          <VsBlock title="Mock JAMB" icon="fa-clipboard-list" sub="Each student’s best mock">
            <VsTable g={c.mock_jamb.graduates} s={c.mock_jamb.sss3} rows={JAMB_ROWS} sNote="no mock yet" /></VsBlock>
          <VsBlock title="Real JAMB" icon="fa-file-contract" sub="Only graduates have sat it so far">
            <VsTable g={c.real_jamb.graduates} s={c.real_jamb.sss3} rows={JAMB_ROWS} sNote="not sat yet" /></VsBlock>
        </div>)}

        {tab === 'subjects' && (
          <section className="pm-card">
            <header className="pm-card-h wrap"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-list-check" /></span>
              <div className="pm-card-t"><h3>Mock WAEC pass rate by subject</h3>
                <small>{!(mg.n > 0) ? 'The graduates have no mock WAEC results to compare with yet' : behind ? `Current SSS3 trails in ${behind} subject${behind === 1 ? '' : 's'} — they’re listed first` : 'Current SSS3 is level or ahead everywhere'}</small></div>
              <PmSeg small label="Order" value={sort} onChange={setSort} options={[{ value: 'gap', label: 'Biggest gap' }, { value: 'name', label: 'A–Z' }]} />
            </header>
            {subjects.length ? (
              <ul className="vs-subs">
                {subjects.map((x) => (
                  <li key={x.sub}>
                    <span className="vs-sub-n">{x.sub}</span>
                    <span className="vs-mini g"><i style={{ width: `${x.g || 0}%` }} /><b>{x.g != null ? x.g + '%' : '—'}</b></span>
                    <span className="vs-mini s"><i style={{ width: `${x.s || 0}%` }} /><b>{x.s != null ? x.s + '%' : '—'}</b></span>
                    <span className={'vs-gap ' + (x.gap == null ? '' : x.gap < 0 ? 'bad' : x.gap > 0 ? 'good' : '')}>{x.gap == null ? '—' : `${x.gap > 0 ? '+' : ''}${x.gap}`}</span>
                  </li>))}
              </ul>
            ) : <p className="pm-empty">No mock WAEC subject results yet.</p>}
          </section>
        )}

        {tab === 'pattern' && (
          <VsBlock title="How graduates did in the real exam vs their mocks" icon="fa-arrow-trend-up" sub="Used to project where the current SSS3 may land">
            {[['WAEC credits', c.pattern.waec_credits], ['JAMB score', c.pattern.jamb_score]].map(([lab, p]) => {
              const x = dir(p);
              return (
                <div key={lab} className="vs-pat">
                  <span className="vs-l">{lab}</span>
                  {p ? (<>
                    <span className={'vs-pat-d ' + x.cls}><i aria-hidden="true" className={'fas ' + (p.direction === 'improved' ? 'fa-arrow-up' : p.direction === 'declined' ? 'fa-arrow-down' : 'fa-minus')} /> {p.direction} <b>{x.sign}{p.avg_delta}</b> on average</span>
                    <span className="vs-pat-n"><b>{p.pct_improved}%</b> of {p.n} graduates beat their mock</span>
                    <span className="vs-track"><i style={{ width: `${p.pct_improved}%` }} /></span>
                  </>) : <span className="pm-dim">Not enough graduates with both a mock and a real result yet.</span>}
                </div>);
            })}
          </VsBlock>
        )}
      </>)}
    </div>
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
// Ranked horizontal bars; each row can open the directory filtered to it.
function BreakdownCard({ title, icon, rows, sub, linkFor, total, empty }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <section className="pm-card aa-card">
      <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className={'fas ' + icon} /></span>
        <div className="pm-card-t"><h3>{title}</h3>{sub && <small>{sub}</small>}</div></header>
      {rows.length ? (
        <ol className="aa-bars">
          {rows.map((r, i) => {
            const href = linkFor ? linkFor(r) : null;
            const body = (<>
              <span className="aa-rank">{i + 1}</span>
              <span className="aa-lab" title={r.label}>{r.label}</span>
              <span className="aa-track"><i style={{ width: `${(r.count / max) * 100}%` }} /></span>
              <b className="aa-n">{r.count}{total ? <small> {Math.round(r.count / total * 100)}%</small> : null}</b>
              {href && <i aria-hidden="true" className="fas fa-chevron-right aa-go" />}
            </>);
            return <li key={i}>{href ? <a href={href} className="aa-row link" title={`See these alumni`}>{body}</a> : <div className="aa-row">{body}</div>}</li>;
          })}
        </ol>
      ) : <p className="pm-empty">{empty || 'No data yet.'}</p>}
    </section>
  );
}

function AlumniAnalytics({ d }) {
  const req = d.requests || {};
  const dest = d.destinations || {};
  const total = d.total || 0;
  const pct = (n, of = total) => (of ? Math.round((n / of) * 100) : 0);
  const coverage = pct(d.with_profile);
  const dir = d.alumni_dir;
  const q = (k, v) => `${dir}?${k}=${encodeURIComponent(v)}`;
  const reqTotal = (req.pending || 0) + (req.fulfilled || 0) + (req.declined || 0);
  const segs = [
    ['working', 'Working', 'var(--primary)', dest.working || 0],
    ['both', 'Working & studying', '#7c3aed', dest.both || 0],
    ['studying', 'In higher education', 'var(--info)', dest.studying || 0],
    ['no_info', 'Profile, no career info', 'var(--warning)', dest.no_info || 0],
    ['no_profile', 'No profile yet', 'var(--gray-300)', dest.no_profile || 0],
  ];
  // Plain-language next steps, worked out from the numbers.
  const tips = [];
  if (total && dest.no_profile) tips.push(['fa-id-card', 'warn', `${dest.no_profile} of ${total} graduates (${pct(dest.no_profile)}%) have no alumni profile yet — share the alumni portal link with them.`]);
  if (dest.no_info) tips.push(['fa-briefcase', 'warn', `${dest.no_info} profile${dest.no_info === 1 ? '' : 's'} say nothing about work or study — a short email asking for an update would fill the gaps.`]);
  if (req.pending) tips.push(['fa-inbox', 'bad', `${req.pending} document request${req.pending === 1 ? ' is' : 's are'} waiting — open the directory to issue or decline.`]);
  if (d.mentors) tips.push(['fa-hands-helping', 'good', `${d.mentors} alumni offered to mentor — invite them to a careers day for current SSS students.`]);
  if (d.with_profile && d.contactable < d.with_profile) tips.push(['fa-address-card', 'warn', `${d.with_profile - d.contactable} profile${d.with_profile - d.contactable === 1 ? ' has' : 's have'} no phone or email, so they can’t be reached.`]);

  return (
    <div className="pm">
      <PmHead back={dir} kicker="Graduates" title="Alumni analytics"
              sub="Where former students are now, how reachable they are, and what they’ve asked for."
              actions={<a href={dir} className="pm-btn"><i aria-hidden="true" className="fas fa-address-book" /> <span>Directory</span></a>} />

      <section className="pm-card aa-hero">
        <div className="aa-ring" style={{ '--p': coverage }} role="img" aria-label={`${coverage}% of graduates have an alumni profile`}>
          <div><b>{coverage}%</b><small>have a profile</small></div>
        </div>
        <div className="aa-hero-t">
          <span className="pm-kick">Where our {total} alumni are now</span>
          <div className="aa-split" role="img" aria-label="Destinations">
            {segs.filter((x) => x[3]).map(([k, lab, col, n]) => (
              <span key={k} style={{ flexGrow: n, background: col }} title={`${lab}: ${n}`} />))}
            {!total && <span style={{ flexGrow: 1, background: 'var(--gray-200)' }} />}
          </div>
          <ul className="aa-legend">
            {segs.map(([k, lab, col, n]) => (
              <li key={k}><i style={{ background: col }} />{lab}<b>{n}</b><small>{pct(n)}%</small></li>))}
          </ul>
        </div>
      </section>

      <PmTiles items={[
        { label: 'Graduates', icon: 'fa-user-graduate', value: total, href: dir, sub: 'open the directory' },
        { label: 'Mentors', icon: 'fa-hands-helping', value: d.mentors, tone: 'good', sub: 'willing to help', href: `${dir}?mentor=1` },
        { label: 'Contactable', icon: 'fa-address-card', value: d.contactable, sub: `${pct(d.contactable)}% · phone or email`, href: `${dir}?has_contact=1` },
        { label: 'Documents issued', icon: 'fa-file-signature', value: d.docs_total, sub: 'certificates, transcripts…' },
        { label: 'Requests waiting', icon: 'fa-hourglass-half', value: req.pending || 0, tone: req.pending ? 'warn' : 'good', sub: req.pending ? 'tap to handle' : 'all handled', href: req.pending ? dir : undefined },
      ]} />

      {tips.length > 0 && (
        <section className="pm-card">
          <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-lightbulb" /></span>
            <div className="pm-card-t"><h3>What to do next</h3><small>Worked out from the numbers below</small></div></header>
          <ul className="aa-tips">{tips.map(([ic, tone, text], i) => <li key={i} className={tone}><i aria-hidden="true" className={'fas ' + ic} />{text}</li>)}</ul>
        </section>
      )}

      <div className="aa-grid">
        <BreakdownCard title="Top employers" icon="fa-building" sub="Tap one to see those alumni" rows={d.top_employers || []}
                       linkFor={(r) => q('employer', r.label)} empty="No employers recorded yet." />
        <BreakdownCard title="Universities & institutions" icon="fa-building-columns" sub="Tap one to see those alumni" rows={d.top_institutions || []}
                       linkFor={(r) => q('institution', r.label)} empty="No institutions recorded yet." />
        <BreakdownCard title="Jobs" icon="fa-briefcase" rows={d.top_occupations || []}
                       linkFor={(r) => q('occupation', r.label)} empty="No occupations recorded yet." />
        <BreakdownCard title="Where they live" icon="fa-location-dot" rows={d.top_locations || []}
                       linkFor={(r) => q('city', String(r.label).split(',')[0].trim())} empty="No locations recorded yet." />
        <BreakdownCard title="Class of" icon="fa-calendar" sub="Graduates per session" rows={d.by_session || []} total={total}
                       linkFor={(r) => (r.id ? q('session_id', r.id) : null)} />
        <BreakdownCard title="Graduate status" icon="fa-flag" rows={d.by_status || []} total={total} />
        <section className="pm-card aa-card">
          <header className="pm-card-h"><span className="pm-card-ic"><i aria-hidden="true" className="fas fa-file-lines" /></span>
            <div className="pm-card-t"><h3>Documents & requests</h3><small>{d.docs_total} issued · {reqTotal} requested by alumni</small></div></header>
          {reqTotal > 0 && (
            <div className="aa-req">
              <div className="aa-split thin">
                {req.fulfilled ? <span style={{ flexGrow: req.fulfilled, background: 'var(--success)' }} /> : null}
                {req.pending ? <span style={{ flexGrow: req.pending, background: 'var(--warning)' }} /> : null}
                {req.declined ? <span style={{ flexGrow: req.declined, background: 'var(--danger)' }} /> : null}
              </div>
              <ul className="aa-legend">
                <li><i style={{ background: 'var(--success)' }} />Fulfilled<b>{req.fulfilled || 0}</b></li>
                <li><i style={{ background: 'var(--warning)' }} />Waiting<b>{req.pending || 0}</b></li>
                <li><i style={{ background: 'var(--danger)' }} />Declined<b>{req.declined || 0}</b></li>
              </ul>
            </div>
          )}
          {(d.docs_by_type || []).length ? (
            <ol className="aa-bars">
              {d.docs_by_type.map((r, i) => {
                const mx = Math.max(1, ...d.docs_by_type.map((x) => x.count));
                return <li key={i}><div className="aa-row"><span className="aa-rank">{i + 1}</span><span className="aa-lab">{r.label}</span>
                  <span className="aa-track"><i style={{ width: `${(r.count / mx) * 100}%` }} /></span><b className="aa-n">{r.count}</b></div></li>;
              })}
            </ol>
          ) : <p className="pm-empty">No documents issued yet.</p>}
        </section>
      </div>
    </div>
  );
}

// ---- Document branding (summary card + edit sheet) ------------------------
function BrandingStudio({ d, notify, onClose }) {
  const nav = useNav();
  const b = d.branding || {};
  const [primary, setPrimary] = useState(b.primary_color || '');
  const [accent, setAccent] = useState(b.accent_color || '');
  const [secondary, setSecondary] = useState(b.secondary_color || '');
  const [motto, setMotto] = useState(b.motto || '');
  const [verify, setVerify] = useState(b.verify_enabled !== false);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    const r = await submitJson(d.branding_save_url, {
      primary_color: primary, accent_color: accent, secondary_color: secondary,
      motto, verify_enabled: verify ? '1' : '0',
    });
    setBusy(false);
    if (r.ok) { notify && notify('success', r.message || 'Branding saved — previews updated.'); onClose(); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not save branding.');
  };
  const DEF = { p: '#0e3a2f', a: '#0e8a64', s: '#c9a227' };
  const swatch = (label, hint, val, set, def) => (
    <div className="dd-sw">
      <label className="dd-sw-pick" style={{ background: val || def }} title={`Pick ${label.toLowerCase()} colour`}>
        <input type="color" value={val || def} onChange={(e) => set(e.target.value)} aria-label={`${label} colour`} /></label>
      <div className="dd-sw-t"><strong>{label}</strong><small>{hint}</small>
        <span className="dd-sw-v"><input type="text" value={val} placeholder="default" onChange={(e) => set(e.target.value)} aria-label={`${label} colour code`} />
          {val && <button type="button" className="pm-link" onClick={() => set('')}>Reset</button>}</span></div>
    </div>
  );
  return (
    <PmSheet title="Document branding" onClose={onClose}>
      <div className="dd-sample" style={{ '--p': primary || DEF.p, '--a': accent || DEF.a, '--s': secondary || DEF.s }} aria-hidden="true">
        <div className="dd-sample-band" />
        <div className="dd-sample-body"><b>Your School</b><small>{motto || 'Your motto here'}</small><span className="dd-sample-line" /><span className="dd-sample-line short" />
          <span className="dd-sample-seal" />{verify && <span className="dd-sample-qr"><i className="fas fa-qrcode" /></span>}</div>
      </div>
      <p className="dd-note">These colours and the motto apply to <b>every</b> design and document type.</p>
      {swatch('Primary', 'Headings and main bands', primary, setPrimary, DEF.p)}
      {swatch('Accent', 'Lines, highlights and tables', accent, setAccent, DEF.a)}
      {swatch('Secondary', 'Seals, borders and gold details', secondary, setSecondary, DEF.s)}
      <label className="pm-field" style={{ marginTop: '.7rem' }}><span>Motto</span>
        <input type="text" className="pm-input" value={motto} onChange={(e) => setMotto(e.target.value)} placeholder="e.g. Knowledge, Integrity, Service" maxLength={160} /></label>
      <label className="gp2-check"><input type="checkbox" checked={verify} onChange={(e) => setVerify(e.target.checked)} /> Print a QR verification block on issued documents</label>
      {canWrite(d, 'documents_templates')
        ? <button type="button" className="pm-btn primary big wide" disabled={busy} onClick={save}><i aria-hidden="true" className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} /> Save branding</button>
        : <p className="dd-note">You can view the branding but not change it.</p>}
    </PmSheet>
  );
}

// ---- Document design gallery (admin) ---------------------------------------
function DocTemplates({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [busy, setBusy] = useState('');
  const [brandOpen, setBrandOpen] = useState(false);
  const [pickOpen, setPickOpen] = useState(false);
  const [q, setQ] = useState('');
  const setDefault = async (t) => {
    setBusy(t.key);
    const r = await submitJson(t.set_url, { template_key: t.key });
    setBusy('');
    if (r.ok) { notify && notify('success', r.message || `${t.name} is now the design for ${d.doc_type_label}.`); nav.refresh && nav.refresh(); }
    else notify && notify('error', r.error || 'Could not set default.');
  };
  const groups = (d.doc_types_grouped && d.doc_types_grouped.length) ? d.doc_types_grouped
    : [{ category: 'Documents', items: (d.doc_types || []).map((x) => ({ key: x.key, label: x.label, url: x.url })) }];
  const t = q.trim().toLowerCase();
  const filtered = groups.map((g) => ({ ...g, items: g.items.filter((x) => !t || x.label.toLowerCase().includes(t)) })).filter((g) => g.items.length);
  const templates = d.templates || [];
  const current = templates.find((x) => x.is_default);
  const canEdit = canWrite(d, 'documents_templates');
  const b = d.branding || {};

  const typeList = (onPick) => (<>
    <div className="pm-search dd-search"><i aria-hidden="true" className="fas fa-search" />
      <input type="search" placeholder="Find a document…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a document type" /></div>
    <nav className="dd-types" aria-label="Document types">
      {filtered.map((g) => (
        <div key={g.category} className="dd-group">
          <span className="dd-group-h">{g.category}</span>
          {g.items.map((x) => (
            <a key={x.key} href={x.url} className={x.key === d.doc_type ? 'on' : ''} aria-current={x.key === d.doc_type ? 'page' : undefined}
               onClick={onPick}>{x.label}{x.key === d.doc_type && <i aria-hidden="true" className="fas fa-check" />}</a>))}
        </div>))}
      {!filtered.length && <p className="pm-empty">No document matches “{q}”.</p>}
    </nav>
  </>);

  return (
    <div className="pm">
      <PmHead back={d.graduates} kicker="Graduates" title="Document designs"
              sub="Pick how each certificate, transcript and letter looks. Your school’s details fill in automatically." />

      <div className="dd-cols">
        {!phone && <aside className="pm-card dd-rail">{typeList()}</aside>}

        <main className="dd-main">
          {phone && (
            <button type="button" className="dd-typebtn" onClick={() => setPickOpen(true)}>
              <span className="pm-card-ic"><i aria-hidden="true" className="fas fa-file-lines" /></span>
              <span className="pm-pn"><small>Document</small><strong>{d.doc_type_label}</strong></span>
              <span className="pm-link">Change <i aria-hidden="true" className="fas fa-chevron-down" /></span>
            </button>
          )}

          {d.branding_save_url && (
            <section className="pm-card dd-brand">
              <div className="dd-brand-sw" aria-hidden="true">
                {[b.primary_color || '#0e3a2f', b.accent_color || '#0e8a64', b.secondary_color || '#c9a227'].map((c, i) => <span key={i} style={{ background: c }} />)}
              </div>
              <div className="pm-pn"><strong>Branding</strong>
                <small>{b.motto ? `“${b.motto}”` : 'No motto set'} · QR verification {b.verify_enabled !== false ? 'on' : 'off'}{!(b.primary_color || b.accent_color || b.secondary_color) ? ' · default colours' : ''}</small></div>
              <button type="button" className="pm-btn" onClick={() => setBrandOpen(true)}><i aria-hidden="true" className="fas fa-palette" /> <span>{canEdit ? 'Edit' : 'View'}</span></button>
            </section>
          )}

          <section className="pm-card">
            <header className="pm-card-h">
              <span className="pm-card-ic"><i aria-hidden="true" className="fas fa-swatchbook" /></span>
              <div className="pm-card-t"><h3>{d.doc_type_label}</h3>
                <small>{templates.length} design{templates.length === 1 ? '' : 's'}{current ? ` · in use: ${current.name}` : ''} · previews use sample data</small></div>
            </header>
            {templates.length ? (
              <ul className="dd-gallery">
                {templates.map((tp) => (
                  <li key={tp.key} className={'dd-card' + (tp.is_default ? ' on' : '')}>
                    <a href={tp.preview_url} target="_blank" rel="noopener noreferrer" data-native="1" className="dd-thumb" title="Open the full PDF preview">
                      {tp.thumb_url ? <img src={tp.thumb_url} alt={`${tp.name} design preview`} loading="lazy" /> : <i aria-hidden="true" className="fas fa-file-pdf" />}
                      {tp.is_default && <span className="dd-badge"><i aria-hidden="true" className="fas fa-check" /> In use</span>}
                    </a>
                    <div className="dd-info"><strong>{tp.name}</strong><small>{tp.description}</small></div>
                    <div className="dd-acts">
                      <a href={tp.preview_url} target="_blank" rel="noopener noreferrer" data-native="1" className="pm-btn"><i aria-hidden="true" className="fas fa-eye" /> PDF</a>
                      {canEdit && (tp.is_default
                        ? <span className="dd-inuse"><i aria-hidden="true" className="fas fa-circle-check" /> In use</span>
                        : <button type="button" className="pm-btn primary" disabled={busy === tp.key} onClick={() => setDefault(tp)}>
                            <i aria-hidden="true" className={'fas ' + (busy === tp.key ? 'fa-spinner fa-spin' : 'fa-check')} /> Use this</button>)}
                    </div>
                  </li>))}
              </ul>
            ) : <p className="pm-empty">No designs available for this document yet.</p>}
          </section>
        </main>
      </div>

      {brandOpen && <BrandingStudio d={d} notify={notify} onClose={() => setBrandOpen(false)} />}
      {pickOpen && <PmSheet title="Choose a document" onClose={() => setPickOpen(false)}>{typeList(() => setPickOpen(false))}</PmSheet>}
    </div>
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
