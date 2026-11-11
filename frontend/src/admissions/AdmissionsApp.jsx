// Admissions — from first enquiry to admitted student. Overview with the
// pipeline, what needs a decision and where applicants come from; applicants
// as a stage board (laptop) or list (phone) with one-tap "next stage"; an
// applicant page with a clickable stage tracker, admit sheet and contact
// actions; and the application form in sectioned cards with a sticky save bar.
import React, { useState, useMemo } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, SectionShell, Toast } from '../components/ui';
import { canWrite } from '../lib/perms';
import { compressPhoto } from '../lib/image';
import { isValidPhone, isValidEmail, relationshipFromName } from '../lib/validate';
import { COUNTRIES, NIGERIA_STATES, NIGERIA_STATES_LGAS, DEFAULT_COUNTRY, DEFAULT_STATE, ageFromDOB } from '../lib/geoData';
import { Head, Tiles, Seg, Chips, Sheet, Menu, Blank, Bar, Meter, usePhone, initials } from '../subjects/results';
import { A, SecNav, Field, Pill, SearchBox, Lookup, plural } from '../components/appkit';

const TONE = { Inquiry: '', Applied: 'info', Screening: 'info', Offered: 'mid', Accepted: 'mid', Admitted: 'good', Rejected: 'bad', Waitlisted: '' };
const ICON = { Inquiry: 'fa-circle-question', Applied: 'fa-file-lines', Screening: 'fa-clipboard-check', Offered: 'fa-envelope-open-text',
  Accepted: 'fa-handshake', Admitted: 'fa-user-graduate', Rejected: 'fa-circle-xmark', Waitlisted: 'fa-hourglass-half' };
const NEXT = { Inquiry: 'Applied', Applied: 'Screening', Screening: 'Offered', Offered: 'Accepted' };
const VERB = { Applied: 'Mark applied', Screening: 'Start screening', Offered: 'Make offer', Accepted: 'Mark accepted' };

function contactFieldError(k, v) {
  const val = (v || '').trim();
  if (!val) return '';
  if (k === 'parent_phone' || k === 'emergency_phone') return isValidPhone(val) ? '' : 'Enter a valid phone number, e.g. 08012345678.';
  if (k === 'parent_email') return isValidEmail(val) ? '' : 'Enter a valid email address.';
  return '';
}
const waPhone = (p) => { const x = (p || '').replace(/\D/g, ''); return x.startsWith('0') ? '234' + x.slice(1) : x; };

function ANav({ d }) {
  return <SecNav label="Admissions" active={d.active === 'dashboard' ? 'dashboard' : 'applicants'} items={[
    ['dashboard', 'fa-chart-pie', 'Overview', d.urls.dashboard],
    ['applicants', 'fa-users', 'Applicants', d.urls.applicants],
    ['blank', 'fa-file-pdf', 'Blank form', canWrite(d, 'download') ? d.urls.blank_form : null, { x: true, native: true }],
  ]} />;
}
const Av = ({ a, size }) => (a.photo_url
  ? <img src={a.photo_url} alt="" className={'ad-av' + (size ? ' ' + size : '')} />
  : <span className={'ad-av' + (size ? ' ' + size : '')}>{initials(a.full_name)}</span>);

// ============================================================================
// Overview
// ============================================================================
function Dashboard({ d }) {
  const nav = useNav();
  const s = d.stats, act = d.action || {};
  const maxF = Math.max(1, ...s.funnel.map((f) => f.count));
  const maxS = Math.max(1, ...(d.sources || []).map((x) => x.count));
  const list = (st) => d.urls.applicants + '?' + new URLSearchParams({ status: st, session_id: d.session_id || '' });
  const todo = [
    act.stale > 0 && { to: act.stale_url, tone: 'mid', ic: 'fa-clock', t: `${plural(act.stale, 'application')} waiting over 2 weeks for a next step` },
    act.offered > 0 && { to: act.offered_url, tone: 'info', ic: 'fa-envelope-open-text', t: `${plural(act.offered, 'offer')} not yet accepted` },
    act.accepted > 0 && { to: act.accepted_url, tone: 'good', ic: 'fa-user-check', t: `${plural(act.accepted, 'applicant')} accepted — ready to admit` },
    act.linkable > 0 && { to: act.linkable_url, tone: 'info', ic: 'fa-link', t: `${plural(act.linkable, 'applicant')} may already have a student record — link them to bring the details across` },
  ].filter(Boolean);
  return (
    <div className="rs cm ad">
      <ANav d={d} />
      <Head icon="fa-user-plus" title="Admissions" sub={`${plural(d.new_week || 0, 'new application')} this week`}>
        <select className="cm-sel" value={d.session_id} aria-label="Session" onChange={(e) => navParams(nav.go, d.urls.dashboard, { session_id: e.target.value })}>
          <option value="">All sessions</option>{d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
        {canWrite(d, 'create') && <A to={d.urls.add} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> New application</span></A>}
      </Head>
      <Tiles items={[
        { label: 'Applications', value: s.total, sub: `${d.gender.male} boys · ${d.gender.female} girls` },
        { label: 'In progress', value: s.pending },
        { label: 'Admitted', value: s.admitted, tone: 'good' },
        { label: 'Conversion', value: s.conversion, unit: '%', sub: `${s.rejected} not offered`, tone: s.conversion >= 50 ? 'good' : s.conversion >= 25 ? 'mid' : '' },
      ]} />
      {todo.length > 0 && (
        <section className="rs-card rp-attn"><span className="k">Needs a decision</span>
          <div className="tm-alerts">{todo.map((x) => (
            <A key={x.t} to={x.to} className={'cm-attn-i ' + x.tone}><i className={'fas ' + x.ic} aria-hidden="true" /><span>{x.t}</span><i className="fas fa-chevron-right" aria-hidden="true" /></A>))}</div>
        </section>)}
      <div className="ad-grid">
        <section className="rs-card ad-funnel">
          <div className="rs-card-h"><h3><i className="fas fa-filter" aria-hidden="true" /> Pipeline</h3><A to={d.urls.applicants} className="cm-link">Board <i className="fas fa-arrow-right" aria-hidden="true" /></A></div>
          {s.funnel.map((f, i) => {
            const prev = i ? s.funnel[i - 1].count : null;
            return (
              <A key={f.stage} to={list(f.stage)} className="ad-fn">
                <span className={'ad-fn-ic ' + TONE[f.stage]}><i className={'fas ' + ICON[f.stage]} aria-hidden="true" /></span>
                <span className="ad-fn-t">{f.stage}</span>
                <span className="ad-fn-b"><i style={{ width: Math.max(2, f.count / maxF * 100) + '%' }} /></span>
                <b>{f.count}</b>
              </A>);
          })}
          <div className="ad-out">
            {['Waitlisted', 'Rejected'].map((o) => <A key={o} to={list(o)} className="ad-out-i"><Pill tone={TONE[o]} icon={ICON[o]}>{o}</Pill><b>{(s.by_status || {})[o] || 0}</b></A>)}</div>
        </section>
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-school" aria-hidden="true" /> Demand by class</h3></div>
          {(d.classes_full || []).length ? (
            <div className="ad-cls">{d.classes_full.map((c) => (
              <div key={c.name} className="ad-cls-r"><b>{c.name}</b>
                <Meter value={c.admitted} max={c.count || 1} tone="good" />
                <span>{c.admitted}/{c.count} admitted</span>
                <small>{c.avg_score != null ? `avg ${c.avg_score}` : '—'}</small></div>))}</div>
          ) : <p className="cm-mute">No applications yet.</p>}
        </section>
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-bullhorn" aria-hidden="true" /> How they heard about us</h3></div>
          {(d.sources || []).length ? (
            <div className="rp-bars">{d.sources.map((x) => (
              <div key={x.name} className="ad-src"><span>{x.name}</span><span className="ad-src-b"><i style={{ width: x.count / maxS * 100 + '%' }} /></span><b>{x.count}</b></div>))}</div>
          ) : <p className="cm-mute">No sources recorded yet.</p>}
        </section>
      </div>
      <section className="rs-card su-group">
        <div className="su-group-h"><h3><i className="fas fa-clock-rotate-left" aria-hidden="true" /> Latest applications</h3><A to={d.urls.applicants} className="cm-link">All <i className="fas fa-arrow-right" aria-hidden="true" /></A></div>
        {d.recent.length ? d.recent.map((r) => (
          <A key={r.id} to={r.detail_url} className="ad-row">
            <Av a={r} /><span className="ad-row-t"><b>{r.full_name}</b><small>{r.application_no} · {r.intended_class} · {r.applied}</small></span>
            <Pill tone={TONE[r.status]}>{r.status}</Pill></A>)) : <Blank icon="fa-user-plus" title="No applications yet" />}
      </section>
    </div>
  );
}

// ============================================================================
// Applicants — board (laptop) / list (phone)
// ============================================================================
function Applicants({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [view, setView] = useState(() => { try { return localStorage.getItem('adm-view') || 'board'; } catch (e) { return 'board'; } });
  const [q, setQ] = useState(d.q || '');
  const [busy, setBusy] = useState(null);
  const canEdit = canWrite(d, 'edit');
  const board = !phone && view === 'board' && !d.status;
  const go = (k, v) => navParams(nav.go, d.urls.applicants, { status: d.status, session_id: d.session_id, class_id: d.class_id, q, [k]: v });
  const setV = (v) => { setView(v); try { localStorage.setItem('adm-view', v); } catch (e) { /* ignore */ } };
  const move = async (r, to) => {
    setBusy(r.id);
    const res = await submitJson(r.status_url, { status: to });
    setBusy(null);
    if (res.ok) { notify('success', `${r.full_name}: ${to}`); nav.refresh(); } else notify('error', res.error || 'Could not update.');
  };
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? d.rows.filter((r) => [r.full_name, r.application_no, r.parent_phone, r.parent_name].join(' ').toLowerCase().includes(t)) : d.rows;
  }, [d.rows, q]);
  const counts = {};
  d.rows.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
  const Card = ({ r }) => (
    <div className="ad-card">
      <A to={r.detail_url} className="ad-card-h"><Av a={r} /><span><b>{r.full_name}</b><small>{r.intended_class} · {r.application_no}</small></span></A>
      <div className="ad-card-m">
        {r.entrance_score !== '—' && <span><i className="fas fa-star" aria-hidden="true" /> {r.entrance_score}</span>}
        {r.match && <span className="ad-match" title={`Looks like ${r.match.name} (${r.match.student_id})`}><i className="fas fa-link" aria-hidden="true" /> Student?</span>}
        {r.waiting != null && r.waiting >= 14 && !['Admitted', 'Rejected'].includes(r.status) && <span className="late"><i className="fas fa-clock" aria-hidden="true" /> {r.waiting}d</span>}
        {r.parent_phone && <a href={'tel:' + r.parent_phone} className="cm-ib" aria-label={`Call ${r.parent_name || 'parent'}`}><i className="fas fa-phone" aria-hidden="true" /></a>}
      </div>
      {canEdit && NEXT[r.status] && <button type="button" className="rs-btn sm ghost ad-next" disabled={busy === r.id} onClick={() => move(r, NEXT[r.status])}>
        {busy === r.id ? <i className="fas fa-spinner fa-spin" aria-hidden="true" /> : <>{VERB[NEXT[r.status]]} <i className="fas fa-arrow-right" aria-hidden="true" /></>}</button>}
    </div>
  );
  return (
    <div className="rs cm ad">
      <ANav d={d} />
      <Head icon="fa-users" title="Applicants" sub={plural(d.rows.length, 'application')}>
        <a href={d.urls.export} data-native className="rs-btn ghost"><i className="fas fa-file-csv" aria-hidden="true" /><span className="rs-hide-sm"> Export</span></a>
        {canWrite(d, 'create') && <A to={d.urls.add} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> New</span></A>}
      </Head>
      <div className="ad-tools">
        <SearchBox value={q} onChange={setQ} placeholder="Name, application no. or phone" />
        <select className="cm-sel" value={d.class_id} aria-label="Class" onChange={(e) => go('class_id', e.target.value)}>
          <option value="">All classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <select className="cm-sel" value={d.session_id} aria-label="Session" onChange={(e) => go('session_id', e.target.value)}>
          <option value="">All sessions</option>{d.sessions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
        {!phone && !d.status && <Seg value={view} onChange={setV} label="View" options={[{ value: 'board', label: 'Board', icon: 'fa-table-columns' }, { value: 'list', label: 'List', icon: 'fa-list' }]} />}
      </div>
      {d.possible && (
        <div className="cm-attn-i info ad-poss"><i className="fas fa-link" aria-hidden="true" />
          <span>Applicants who look like a student already on the system. Open one and use <b>Link</b> to attach the application and copy its details.</span>
          <A to={d.urls.applicants} className="rs-btn sm ghost">Show all</A></div>)}
      <Chips label="Stage" value={d.status} onChange={(v) => go('status', v)}
             items={[{ value: '', label: 'All', sub: d.rows.length }, ...d.statuses.map((x) => ({ value: x, label: x, sub: counts[x] || 0 }))]} />

      {!rows.length ? <Blank icon="fa-user-plus" title={d.rows.length ? 'No match' : 'No applications yet'}>
        {canWrite(d, 'create') && !d.rows.length && <A to={d.urls.add} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /> New application</A>}</Blank>
      : board ? (
        <div className="ad-board">{[...d.stages, 'Waitlisted', 'Rejected'].map((st) => {
          const col = rows.filter((r) => r.status === st);
          if (!col.length && ['Waitlisted', 'Rejected'].includes(st)) return null;
          return (
            <section key={st} className={'ad-col ' + TONE[st]}>
              <div className="ad-col-h"><i className={'fas ' + ICON[st]} aria-hidden="true" /><b>{st}</b><span>{col.length}</span></div>
              <div className="ad-col-b">{col.map((r) => <Card key={r.id} r={r} />)}{!col.length && <p className="cm-mute">None</p>}</div>
            </section>);
        })}</div>
      ) : (
        <section className="rs-card su-group">{rows.map((r) => (
          <div key={r.id} className="ad-li">
            <A to={r.detail_url} className="ad-li-m"><Av a={r} />
              <span className="ad-row-t"><b>{r.full_name}</b><small>{r.intended_class} · {r.application_no}{r.parent_phone ? ' · ' + r.parent_phone : ''}</small></span></A>
            <Pill tone={TONE[r.status]}>{r.status}</Pill>
            {!phone && <span className="ad-li-s">{r.entrance_score}</span>}
            {canEdit && NEXT[r.status] && <button type="button" className="rs-btn sm ghost" disabled={busy === r.id} onClick={() => move(r, NEXT[r.status])} title={VERB[NEXT[r.status]]}>
              {busy === r.id ? <i className="fas fa-spinner fa-spin" aria-hidden="true" /> : <><span className="rs-hide-sm">{VERB[NEXT[r.status]]} </span><i className="fas fa-arrow-right" aria-hidden="true" /></>}</button>}
          </div>))}</section>)}
    </div>
  );
}

// ============================================================================
// Applicant page
// ============================================================================
function ApplicantDetail({ d, notify }) {
  const nav = useNav();
  const a = d.applicant;
  const [admit, setAdmit] = useState(false);
  const [linking, setLinking] = useState(false);
  const [pick, setPick] = useState(null);
  const link = async (st) => {
    if (!await confirm({ title: `Link to ${st.name || st.label}?`, confirmText: 'Link',
      message: 'This application will be marked admitted and attached to that student. Anything their record is missing (photo, contacts, health, address…) is copied in — nothing on it is overwritten.' })) return;
    setBusy(true);
    const r = await submitJson(d.urls.link, { student_id: st.id });
    setBusy(false);
    if (r.ok) { setLinking(false); notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not link.');
  };
  const [arm, setArm] = useState(d.assignments[0] ? String(d.assignments[0].id) : '');
  const [busy, setBusy] = useState(false);
  const canEdit = canWrite(d, 'edit');
  const idx = d.stages.indexOf(a.status);
  const setStatus = async (st) => {
    if (st === a.status) return;
    if (['Rejected', 'Waitlisted'].includes(st) && !await confirm({ title: `${st === 'Rejected' ? 'Decline' : 'Waitlist'} ${a.full_name}?`,
      confirmText: st === 'Rejected' ? 'Decline' : 'Waitlist', tone: st === 'Rejected' ? 'danger' : undefined,
      message: 'The parent is told about the decision if decision messages are switched on.' })) return;
    const r = await submitJson(d.urls.status, { status: st });
    if (r.ok) { notify('success', `Status: ${st}`); nav.refresh(); } else notify('error', r.error || 'Could not update.');
  };
  const doAdmit = async () => {
    setBusy(true);
    const r = await submitJson(d.urls.convert, { assignment_id: arm });
    setBusy(false);
    if (r.ok) { window.location.href = r.redirect; } else notify('error', r.error || 'Could not admit.');
  };
  const copyOver = async () => {
    setBusy(true);
    const r = await submitJson(d.urls.copy, {});
    setBusy(false);
    notify(r.ok ? 'success' : 'error', r.ok ? r.message : (r.error || 'Could not copy.'));
  };
  const del = async () => {
    if (!await confirm({ title: `Delete ${a.full_name}’s application?`, tone: 'danger', confirmText: 'Delete', message: 'This can’t be undone.' })) return;
    const r = await submitJson(d.urls.delete, {});
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not delete.');
  };
  const KV = ({ rows }) => <dl className="ad-kv">{rows.map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd>{v}</dd></React.Fragment>)}</dl>;
  return (
    <div className="rs cm ad">
      <ANav d={d} />
      <section className="rs-card ad-hero">
        <Av a={a} size="lg" />
        <div className="ad-hero-t">
          <h1>{a.full_name}</h1>
          <div className="ad-hero-m"><span>{a.application_no}</span>{a.intended_class && <span><i className="fas fa-school" aria-hidden="true" /> {a.intended_class}</span>}
            {a.session && <span>{a.session}</span>}{a.age != null && <span>{a.age} yrs</span>}{a.gender && <span>{a.gender}</span>}</div>
          <Pill tone={TONE[a.status]} icon={ICON[a.status]}>{a.status}</Pill>
        </div>
        <div className="ad-hero-a">
          {a.parent_phone && <a href={'tel:' + a.parent_phone} className="ad-ca"><i className="fas fa-phone" aria-hidden="true" /><span>Call</span></a>}
          {a.parent_phone && <a href={'https://wa.me/' + waPhone(a.parent_phone)} target="_blank" rel="noopener" className="ad-ca wa"><i className="fab fa-whatsapp" aria-hidden="true" /><span>WhatsApp</span></a>}
          {a.parent_email && <a href={'mailto:' + a.parent_email} className="ad-ca"><i className="fas fa-envelope" aria-hidden="true" /><span>Email</span></a>}
          <Menu label="More" items={[
            canEdit && { icon: 'fa-pen', label: 'Edit application', onClick: () => nav.go(d.urls.edit) },
            canWrite(d, 'download') && { icon: 'fa-file-pdf', label: 'Download PDF', href: d.urls.pdf, native: true },
            canWrite(d, 'download') && { icon: 'fa-file-word', label: 'Download Word', href: d.urls.docx, native: true },
            canWrite(d, 'delete') && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: del },
          ]} />
        </div>
      </section>

      <section className="rs-card ad-track">
        <ol className="ad-steps">{d.stages.map((st, i) => (
          <li key={st} className={(i < idx ? 'done' : i === idx ? 'on' : '') + (idx < 0 ? ' off' : '')}>
            <button type="button" disabled={!canEdit || st === 'Admitted' || !!a.admitted_student_id} onClick={() => setStatus(st)} aria-current={i === idx ? 'step' : undefined}>
              <span className="ad-dot">{i < idx ? <i className="fas fa-check" aria-hidden="true" /> : i + 1}</span><small>{st}</small></button></li>))}</ol>
        <div className="ad-track-a">
          {a.admitted_student_id ? <>
            {canWrite(d, 'convert') && <button type="button" className="rs-btn ghost" disabled={busy} onClick={copyOver}>
              <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-file-import')} aria-hidden="true" /> Copy details to student record</button>}
            <A to={a.student_url} className="rs-btn primary"><i className="fas fa-user-graduate" aria-hidden="true" /> Open student record</A>
          </> : canEdit && <>
            {a.status === 'Admitted' && canWrite(d, 'convert') && <button type="button" className="rs-btn primary" onClick={() => setAdmit(true)}><i className="fas fa-user-graduate" aria-hidden="true" /> Create student record</button>}
            {NEXT[a.status] && <button type="button" className="rs-btn primary" onClick={() => setStatus(NEXT[a.status])}>{VERB[NEXT[a.status]]} <i className="fas fa-arrow-right" aria-hidden="true" /></button>}
            {['Offered', 'Accepted'].includes(a.status) && canWrite(d, 'convert') && <button type="button" className={'rs-btn ' + (a.status === 'Accepted' ? 'primary' : 'ghost')} onClick={() => setAdmit(true)}><i className="fas fa-user-graduate" aria-hidden="true" /> Admit</button>}
            {!['Rejected', 'Admitted'].includes(a.status) && <button type="button" className="rs-btn ghost" onClick={() => setStatus('Waitlisted')}>Waitlist</button>}
            {!['Rejected', 'Admitted'].includes(a.status) && <button type="button" className="rs-btn ghost ad-no" onClick={() => setStatus('Rejected')}>Decline</button>}
            {['Rejected', 'Waitlisted'].includes(a.status) && <button type="button" className="rs-btn ghost" onClick={() => setStatus('Screening')}>Reopen</button>}
          </>}
        </div>
      </section>

      {!a.admitted_student_id && canWrite(d, 'convert') && (d.matches.length > 0 ? (
        <section className="rs-card ad-matches">
          <div className="rs-card-h"><h3><i className="fas fa-link" aria-hidden="true" /> Already a student?</h3>
            <button type="button" className="cm-link" onClick={() => setLinking(true)}>Search for someone else</button></div>
          <p className="cm-mute">If {a.full_name} was admitted and given a student record by hand, link it here to bring the application details across.</p>
          {d.matches.map((m) => (
            <div key={m.id} className={'ad-mt' + (m.strong ? ' strong' : '')}>
              <span className="ad-av">{(m.name || '?').split(' ').slice(0, 2).map((w) => w[0]).join('')}</span>
              <span className="ad-row-t"><A to={m.url}><b>{m.name}</b></A>
                <small>{[m.student_id, m.class, m.dob].filter(Boolean).join(' · ')}</small>
                <span className="ad-why">{m.reasons.map((x) => <Pill key={x} tone={m.strong ? 'good' : ''}>{x}</Pill>)}</span></span>
              <button type="button" className={'rs-btn sm ' + (m.strong ? 'primary' : 'ghost')} disabled={busy} onClick={() => link(m)}><i className="fas fa-link" aria-hidden="true" /> Link</button>
            </div>))}
        </section>
      ) : (
        <button type="button" className="ad-linkbar" onClick={() => setLinking(true)}>
          <i className="fas fa-link" aria-hidden="true" /><span><b>Already gave {a.first_name || 'them'} a student record by hand?</b><small>Link it to this application to copy the details across.</small></span>
          <i className="fas fa-chevron-right" aria-hidden="true" /></button>))}

      <div className="ad-dgrid">
        <section className="rs-card"><div className="rs-card-h"><h3><i className="fas fa-id-card" aria-hidden="true" /> Applicant</h3></div><KV rows={d.info} /></section>
        <section className="rs-card"><div className="rs-card-h"><h3><i className="fas fa-people-roof" aria-hidden="true" /> Parent / guardian</h3></div><KV rows={d.parent} />
          {d.emergency && <><div className="rs-card-h ad-sub"><h3>Emergency contact</h3></div><KV rows={d.emergency} /></>}</section>
        {d.notes && <section className="rs-card ad-notes"><div className="rs-card-h"><h3><i className="fas fa-note-sticky" aria-hidden="true" /> Notes</h3></div><p>{d.notes}</p></section>}
      </div>

      {linking && (
        <Sheet title="Link to an existing student" onClose={() => { setLinking(false); setPick(null); }}>
          <div className="su-form">
            <Field label="Find the student" hint="Type at least two letters of their name or student ID">
              <Lookup url={d.urls.student_search} placeholder="Search students" autoFocus picked={pick}
                      onPick={setPick} onClear={() => setPick(null)} icon="fa-user-graduate" /></Field>
            <p className="cm-mute">The application is marked admitted and linked. Missing details on the student record — photo, contacts, blood group, address… — are filled from the application; nothing is overwritten.</p>
            <div className="su-form-f">
              <button type="button" className="rs-btn ghost" onClick={() => { setLinking(false); setPick(null); }}>Cancel</button>
              <button type="button" className="rs-btn primary" disabled={!pick || busy} onClick={() => link(pick)}><i className="fas fa-link" aria-hidden="true" /> Link</button>
            </div>
          </div>
        </Sheet>)}
      {admit && (
        <Sheet title={`Admit ${a.full_name}`} onClose={() => setAdmit(false)}>
          <div className="su-form">
            <p className="cm-mute">Creates the student record from the application — names, date of birth, passport photo, address, blood group and genotype, parent and emergency contacts. Other details (previous school, origin…) show on the student’s profile.</p>
            <Field label="Put them in a class (optional)">
              <select value={arm} onChange={(e) => setArm(e.target.value)}>
                <option value="">Don’t place in a class yet</option>
                {d.assignments.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</select></Field>
            {!d.assignments.length && <small className="cm-mute">No {a.intended_class || ''} class is open for {a.session || 'that session'} yet — you can place them later in Class setup.</small>}
            <div className="su-form-f">
              <button type="button" className="rs-btn ghost" onClick={() => setAdmit(false)}>Cancel</button>
              <button type="button" className="rs-btn primary" disabled={busy} onClick={doAdmit}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-user-graduate')} aria-hidden="true" /> Admit</button>
            </div>
          </div>
        </Sheet>)}
    </div>
  );
}

// ============================================================================
// Application form
// ============================================================================
function ApplicantForm({ d, notify }) {
  const nav = useNav();
  const a = d.applicant || {};
  const editing = !!d.applicant;
  const init = useMemo(() => ({
    first_name: a.first_name || '', surname: a.surname || '', middle_name: a.middle_name || '',
    gender: a.gender || '', date_of_birth: a.date_of_birth || '', previous_school: a.previous_school || '',
    source: a.source || '', session_id: a.session_id ? String(a.session_id) : (editing ? '' : String(d.active_session_id || '')),
    intended_class_id: a.intended_class_id ? String(a.intended_class_id) : '', status: 'Applied',
    entrance_score: a.entrance_score === '' || a.entrance_score == null ? '' : String(a.entrance_score),
    parent_name: a.parent_name || '', relationship: a.relationship || '', parent_phone: a.parent_phone || '',
    parent_email: a.parent_email || '', address: a.address || '', notes: a.notes || '',
    emergency_name: a.emergency_name || '', emergency_relationship: a.emergency_relationship || '',
    emergency_phone: a.emergency_phone || '', emergency_address: a.emergency_address || '',
    country: a.country || DEFAULT_COUNTRY, state_of_origin: a.state_of_origin || (!a.country || a.country === DEFAULT_COUNTRY ? DEFAULT_STATE : ''), lga: a.lga || '',
    father_occupation: a.father_occupation || '', languages_spoken: a.languages_spoken || '',
    blood_group: a.blood_group || '', genotype: a.genotype || '', photo_data: '',
  }), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  const dirty = JSON.stringify(f) !== JSON.stringify(init);
  const photoPreview = f.photo_data === '__clear__' ? '' : (f.photo_data && f.photo_data.slice(0, 5) === 'data:' ? f.photo_data : (a.photo_url || ''));
  const age = ageFromDOB(f.date_of_birth);
  const hasStates = f.country === DEFAULT_COUNTRY;
  const lgas = NIGERIA_STATES_LGAS[f.state_of_origin] || [];
  const onPhoto = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) { notify('error', 'Please choose an image file.'); return; }
    if (file.size > 50 * 1024 * 1024) { notify('error', 'That image is too large to process (max 50 MB).'); return; }
    try { const url = await compressPhoto(file); setF((s) => ({ ...s, photo_data: url })); } catch (err) { notify('error', 'Could not read that image.'); }
  };
  const set = (k, v) => {
    setF((s) => {
      const next = { ...s, [k]: v };
      if (k === 'parent_name') { const rel = relationshipFromName(v); if (rel) next.relationship = rel; }
      else if (k === 'emergency_name') { const rel = relationshipFromName(v); if (rel) next.emergency_relationship = rel; }
      else if (k === 'country') {
        if (v === DEFAULT_COUNTRY) { if (!s.state_of_origin) next.state_of_origin = DEFAULT_STATE; }
        else if (NIGERIA_STATES.includes(s.state_of_origin)) { next.state_of_origin = ''; next.lga = ''; }
      } else if (k === 'state_of_origin') { const l = NIGERIA_STATES_LGAS[v] || []; if (s.lga && !l.includes(s.lga)) next.lga = ''; }
      return next;
    });
    setErrors((er) => { if (!er[k]) return er; const msg = contactFieldError(k, v); if (!msg) { const { [k]: _d, ...rest } = er; return rest; } return { ...er, [k]: msg }; });
  };
  const blur = (k) => setErrors((er) => { const msg = contactFieldError(k, f[k]); if (!msg) { if (!er[k]) return er; const { [k]: _d, ...rest } = er; return rest; } return { ...er, [k]: msg }; });
  const submit = async () => {
    if (!f.first_name.trim() || !f.surname.trim()) { notify('error', 'First name and surname are required.'); return; }
    const er = {};
    ['parent_phone', 'parent_email', 'emergency_phone'].forEach((k) => { const m = contactFieldError(k, f[k]); if (m) er[k] = m; });
    setErrors(er);
    if (Object.keys(er).length) { notify('error', 'Please fix the highlighted fields.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const T = (label, k, props = {}) => (
    <Field label={label} grow key={k} hint={errors[k] ? undefined : props.hint}>
      <input type={props.type || 'text'} value={f[k]} placeholder={props.placeholder} step={props.step} inputMode={props.inputMode}
             aria-invalid={errors[k] ? true : undefined} onBlur={props.check ? () => blur(k) : undefined} onChange={(e) => set(k, e.target.value)} />
      {errors[k] && <small className="su-err">{errors[k]}</small>}
    </Field>);
  const S = (label, k, opts) => (
    <Field label={label} grow key={k}><select value={f[k]} onChange={(e) => set(k, e.target.value)}><option value="">—</option>
      {opts.map((o) => (Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o}>{o}</option>))}</select></Field>);
  return (
    <div className="rs cm ad">
      <ANav d={d} />
      <Head icon={editing ? 'fa-pen' : 'fa-user-plus'} title={editing ? 'Edit application' : 'New application'} sub={editing ? (a.first_name + ' ' + a.surname) : 'Only first name and surname are required.'} />
      <div className="ad-form">
        <section className="rs-card ad-fs">
          <div className="rs-card-h"><h3><i className="fas fa-child" aria-hidden="true" /> Applicant</h3></div>
          <div className="ad-photo">
            {photoPreview ? <img src={photoPreview} alt="Passport" /> : <span className="ad-photo-x"><i className="fas fa-camera" aria-hidden="true" /></span>}
            <div><label className="rs-btn ghost sm"><i className="fas fa-upload" aria-hidden="true" /> {photoPreview ? 'Change photo' : 'Add passport photo'}
              <input type="file" accept="image/*" capture="user" hidden onChange={onPhoto} /></label>
              {photoPreview && <button type="button" className="rs-btn ghost sm" onClick={() => set('photo_data', '__clear__')}>Remove</button>}</div>
          </div>
          <div className="cm-row2">{T('First name *', 'first_name')}{T('Surname *', 'surname')}{T('Middle name', 'middle_name')}</div>
          <div className="cm-row2">{S('Gender', 'gender', ['Male', 'Female'])}
            <Field label="Date of birth" grow hint={age !== null ? `${age} ${age === 1 ? 'year' : 'years'} old` : undefined}><input type="date" value={f.date_of_birth} onChange={(e) => set('date_of_birth', e.target.value)} /></Field>
            {T('Previous school', 'previous_school')}</div>
        </section>
        <section className="rs-card ad-fs">
          <div className="rs-card-h"><h3><i className="fas fa-file-lines" aria-hidden="true" /> Application</h3></div>
          <div className="cm-row2">{S('Session', 'session_id', d.sessions.map((x) => [String(x.id), x.name]))}{S('Class applying for', 'intended_class_id', d.classes.map((c) => [String(c.id), c.name]))}</div>
          <div className="cm-row2">
            {!editing && S('Starting stage', 'status', d.statuses)}
            {T('Entrance score', 'entrance_score', { type: 'number', step: '0.5', inputMode: 'decimal' })}
            {S('How they heard about us', 'source', d.sources || [])}</div>
        </section>
        <section className="rs-card ad-fs">
          <div className="rs-card-h"><h3><i className="fas fa-people-roof" aria-hidden="true" /> Parent / guardian</h3></div>
          <div className="cm-row2">{T('Name', 'parent_name', { placeholder: 'e.g. Mr. John Okafor' })}{T('Relationship', 'relationship', { placeholder: 'Father / Mother / Guardian' })}</div>
          <div className="cm-row2">{T('Phone', 'parent_phone', { type: 'tel', placeholder: '08012345678', check: true, inputMode: 'tel' })}{T('Email', 'parent_email', { type: 'email', check: true })}</div>
          {T('Home address', 'address')}
        </section>
        <section className="rs-card ad-fs">
          <div className="rs-card-h"><h3><i className="fas fa-kit-medical" aria-hidden="true" /> Emergency contact</h3></div>
          <div className="cm-row2">{T('Name', 'emergency_name')}{T('Relationship', 'emergency_relationship', { placeholder: 'Uncle / Aunt / Neighbour' })}</div>
          <div className="cm-row2">{T('Phone', 'emergency_phone', { type: 'tel', placeholder: '08012345678', check: true, inputMode: 'tel' })}{T('Address', 'emergency_address')}</div>
        </section>
        <section className="rs-card ad-fs">
          <div className="rs-card-h"><h3><i className="fas fa-earth-africa" aria-hidden="true" /> Origin & health</h3></div>
          <div className="cm-row2">
            <Field label="Country" grow><select value={f.country} onChange={(e) => set('country', e.target.value)}>
              {f.country && !COUNTRIES.includes(f.country) && <option value={f.country}>{f.country}</option>}
              {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
            <Field label="State of origin" grow>{hasStates
              ? <select value={f.state_of_origin} onChange={(e) => set('state_of_origin', e.target.value)}><option value="">—</option>
                  {f.state_of_origin && !NIGERIA_STATES.includes(f.state_of_origin) && <option value={f.state_of_origin}>{f.state_of_origin}</option>}
                  {NIGERIA_STATES.map((x) => <option key={x} value={x}>{x}</option>)}</select>
              : <input type="text" value={f.state_of_origin} onChange={(e) => set('state_of_origin', e.target.value)} />}</Field>
            <Field label="L.G.A. of origin" grow>{hasStates && f.state_of_origin
              ? <select value={f.lga} onChange={(e) => set('lga', e.target.value)}><option value="">—</option>
                  {f.lga && !lgas.includes(f.lga) && <option value={f.lga}>{f.lga}</option>}
                  {lgas.map((l) => <option key={l} value={l}>{l}</option>)}</select>
              : <input type="text" value={f.lga} disabled={hasStates && !f.state_of_origin} placeholder={hasStates && !f.state_of_origin ? 'Pick a state first' : ''} onChange={(e) => set('lga', e.target.value)} />}</Field>
          </div>
          <div className="cm-row2">{T("Father's occupation", 'father_occupation')}{T('Languages at home', 'languages_spoken')}
            {S('Blood group', 'blood_group', ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'])}{S('Genotype', 'genotype', ['AA', 'AS', 'SS', 'AC', 'SC'])}</div>
          <Field label="Notes"><textarea rows="3" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></Field>
        </section>
      </div>
      <Bar>
        <span className="ad-bar-t">{dirty ? 'Unsaved changes' : editing ? 'No changes yet' : 'Fill in what you have — you can add the rest later'}</span>
        <A to={editing ? a.detail_url : d.urls.applicants} className="rs-btn ghost">Cancel</A>
        <button type="button" className="rs-btn primary" disabled={busy || (editing && !dirty)} onClick={submit}>
          <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {editing ? 'Save changes' : 'Create application'}</button>
      </Bar>
    </div>
  );
}

const SCREENS = { dashboard: Dashboard, applicants: Applicants, applicant_form: ApplicantForm, applicant_detail: ApplicantDetail };

export default function AdmissionsApp({ data }) {
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
