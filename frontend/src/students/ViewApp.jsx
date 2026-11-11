import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { apiGet } from '../lib/api';
import { postForm } from '../lib/forms';
import { confirm } from '../components/ui';
import { rememberViewed } from '../lib/studprefs';
import { canWrite } from '../lib/perms';

// Copies `text` to the clipboard and flashes a checkmark for ~1.2s to confirm.
// Falls back to a hidden-textarea + execCommand when the async Clipboard API
// isn't available (older browsers, or a non-HTTPS context).
function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  if (!text) return null;
  const doCopy = async (e) => {
    e.stopPropagation();
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(String(text));
      } else {
        const ta = document.createElement('textarea');
        ta.value = String(text);
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch (err) { /* clipboard unavailable — silently no-op */ }
  };
  return (
    <button type="button" className="copy-btn" onClick={doCopy}
            title={copied ? 'Copied!' : 'Copy'} aria-label={copied ? 'Copied' : `Copy ${text}`}>
      <i aria-hidden="true" className={'fas ' + (copied ? 'fa-check' : 'fa-copy')} />
    </button>
  );
}

// `copy` is the plain-text value to copy; defaults to `children` when that's
// itself a plain string (so most call sites don't need to pass it twice).
function Info({ label, children, copy }) {
  const copyText = copy !== undefined ? copy : (typeof children === 'string' ? children : null);
  return (
    <div className="info-row">
      <span className="text-muted">{label}</span>
      <span className="info-value-wrap"><strong>{children}</strong><CopyBtn text={copyText} /></span>
    </div>
  );
}

// Lightweight attendance donut (conic-gradient ring, no chart library) — the
// headline percentage lives in the hole, the ring fills to that share and turns
// danger-red when below the school's warning threshold.
function AttendanceDonut({ pct, warning, label = 'This term' }) {
  const p = Math.max(0, Math.min(100, Math.round(Number(pct) || 0)));
  const color = warning ? 'var(--danger)' : 'var(--success)';
  return (
    <div className="att-donut" style={{ '--p': p, '--c': color }} role="img"
         aria-label={`${label} attendance ${p}%`}>
      <div className="att-donut-hole">
        <span className="att-donut-pct">{p}%</span>
        <span className="att-donut-cap">{label}</span>
      </div>
    </div>
  );
}

// Hooks/utilities for the responsive layout: phone (< 760px) gets the native-
// app treatment (round action buttons, sticky segmented tabs, bottom sheets);
// laptops get a two-column workspace with a sticky rail.
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

// A plain profile card (no accordion — tabs keep the page short instead).
function Section({ icon, title, badge, action, wide, children, className = '' }) {
  return (
    <section className={'sv-card' + (wide ? ' sv-wide' : '') + (className ? ' ' + className : '')}>
      <header className="sv-card-head">
        <i aria-hidden="true" className={'fas ' + icon + ' sv-card-icon'} />
        <h2 className="sv-card-title">{title}</h2>
        {badge}
        {action && <span className="sv-card-act">{action}</span>}
      </header>
      <div className="sv-card-body">{children}</div>
    </section>
  );
}

// "⋯" overflow menu — closes on outside tap / Escape.
function Menu({ items, label = 'More actions', className = 'sp-btn', icon = 'fa-ellipsis', text, sheet = false }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open || sheet) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('touchstart', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('touchstart', close); document.removeEventListener('keydown', esc); };
  }, [open]);
  const list = items.filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="sv-menu" ref={ref}>
      <button type="button" className={className} aria-haspopup="true" aria-expanded={open}
              aria-label={label} title={label} onClick={() => setOpen((v) => !v)}>
        <i aria-hidden="true" className={'fas ' + icon} />{text && <span>{text}</span>}
      </button>
      {open && sheet && (
        <Sheet title="More actions" onClose={() => setOpen(false)}>
          <div className="sv-actsheet" role="menu">
            {list.map((it, i) => it.href
              ? <a key={i} role="menuitem" href={it.href} onClick={() => setOpen(false)}>
                  <span className="sv-round sm"><i aria-hidden="true" className={'fas ' + it.icon} /></span>{it.label}</a>
              : <button key={i} type="button" role="menuitem" className={it.danger ? 'danger' : ''}
                        onClick={() => { setOpen(false); it.onClick(); }}>
                  <span className="sv-round sm"><i aria-hidden="true" className={'fas ' + it.icon} /></span>{it.label}</button>)}
          </div>
        </Sheet>
      )}
      {open && !sheet && (
        <div className="sv-menu-pop" role="menu">
          {list.map((it, i) => it.href
            ? <a key={i} role="menuitem" href={it.href} onClick={() => setOpen(false)}>
                <i aria-hidden="true" className={'fas ' + it.icon} /> {it.label}</a>
            : <button key={i} type="button" role="menuitem" className={it.danger ? 'danger' : ''}
                      onClick={() => { setOpen(false); it.onClick(); }}>
                <i aria-hidden="true" className={'fas ' + it.icon} /> {it.label}</button>)}
        </div>
      )}
    </div>
  );
}

// Add-record form container: a bottom sheet on phones, a centred dialog on
// laptops. Portalled to <body> so it sits above the global bottom nav.
function Sheet({ title, onClose, children }) {
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', esc);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', esc); document.body.style.overflow = prev; };
  }, []);
  return createPortal(
    <div className="sv-sheet-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sv-sheet" role="dialog" aria-modal="true" aria-label={title}>
        <div className="sv-sheet-grip" aria-hidden="true" />
        <div className="sv-sheet-head"><strong>{title}</strong>
          <button type="button" className="sv-x" onClick={onClose} aria-label="Close"><i aria-hidden="true" className="fas fa-xmark" /></button>
        </div>
        {children}
      </div>
    </div>, document.body);
}

const TABS = [
  { key: 'overview', label: 'Overview', icon: 'fa-user' },
  { key: 'exams', label: 'Exams', icon: 'fa-file-lines' },
  { key: 'records', label: 'Records', icon: 'fa-folder-open' },
  { key: 'contacts', label: 'Contacts', icon: 'fa-address-book', phoneOnly: true },
];
const tabFromHash = () => {
  const h = (typeof window !== 'undefined' ? window.location.hash : '').replace('#', '');
  return TABS.some((t) => t.key === h) ? h : 'overview';
};

// Colour + icon for the chosen-course eligibility verdict.
const ELIG_STYLE = {
  ON_TRACK: { badge: 'badge-success', bar: 'var(--success)', icon: 'fa-circle-check' },
  CLOSE: { badge: 'badge-warning', bar: 'var(--warning)', icon: 'fa-circle-half-stroke' },
  OFF_TRACK: { badge: 'badge-danger', bar: 'var(--danger)', icon: 'fa-triangle-exclamation' },
  NO_DATA: { badge: 'badge-secondary', bar: 'var(--gray-300)', icon: 'fa-hourglass-half' },
  NO_TARGET: { badge: 'badge-secondary', bar: 'var(--gray-300)', icon: 'fa-circle-question' },
};

// The university-aspiration section of the profile: chosen-course verdict with a
// gap-to-target progress bar, second choice, career goal, admission outcome and
// any scholarships. Rendered whenever the student has any aspiration data.
function AspirationCard({ s, asp, scholarships }) {
  const hasAny = s.target_university || s.target_course || s.jamb_target || s.career_goal ||
    s.admission_status || (scholarships && scholarships.length) ||
    (s.waec_subjects && s.waec_subjects.length) || (s.jamb_subjects && s.jamb_subjects.length);
  if (!hasAny) return null;
  const st = (asp && ELIG_STYLE[asp.status]) || ELIG_STYLE.NO_TARGET;
  const target = (asp && asp.target) || s.jamb_target;
  const proj = asp && asp.projected;
  const pct = (target && proj != null) ? Math.max(0, Math.min(100, Math.round((proj / target) * 100))) : null;
  return (
    <Section icon="fa-graduation-cap" title="University Aspiration"
             badge={asp && asp.status ? <span className={'badge ' + st.badge}><i aria-hidden="true" className={'fas ' + st.icon} /> {asp.status_label}</span> : null}>
        <div className="info-grid">
          <Info label="Target University">{s.target_university || 'Not set'}</Info>
          <Info label="Target Course">{s.target_course || 'Not set'}</Info>
          <Info label="Department / Faculty">{s.target_department || 'Not set'}</Info>
          <Info label="JAMB Target Score">{target ? `${target} / 400` : 'Not set'}</Info>
          {(s.target2_university || s.target2_course) &&
            <Info label="Second Choice">{[s.target2_university, s.target2_course].filter(Boolean).join(' · ') || 'Not set'}</Info>}
          {s.career_goal && <Info label="Career Goal">{s.career_goal}</Info>}
          {s.admission_status && <Info label="Admission Status"><span className="badge badge-info">{s.admission_status}</span></Info>}
          {(s.admitted_university || s.admitted_course) &&
            <Info label="Admitted To">{[s.admitted_university, s.admitted_course].filter(Boolean).join(' · ')}</Info>}
          <Info label="WAEC Subjects">{(s.waec_subjects || []).join(', ') || 'Not set'}</Info>
          <Info label="JAMB Subjects">{(s.jamb_subjects || []).join(', ') || 'Not set'}</Info>
        </div>

        {pct != null && (
          <div style={{ marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.85rem', marginBottom: '.3rem' }}>
              <span className="text-muted">Projected JAMB {proj} of target {target}</span>
              <strong>{asp.gap != null && asp.gap > 0 ? `${asp.gap} to go` : 'Target met'}</strong>
            </div>
            <div style={{ height: 10, borderRadius: 6, background: 'var(--gray-200, #e5e7eb)', overflow: 'hidden' }}>
              <div style={{ width: pct + '%', height: '100%', background: st.bar, transition: 'width .4s' }} />
            </div>
          </div>
        )}

        {asp && (asp.missing_jamb || []).length > 0 && (
          <p className="text-muted" style={{ marginTop: '.75rem', marginBottom: 0, fontSize: '.85rem' }}>
            <i aria-hidden="true" className="fas fa-triangle-exclamation" style={{ color: 'var(--danger)' }} /> Missing required JAMB subject(s): <strong>{asp.missing_jamb.join(', ')}</strong>
          </p>
        )}
        {asp && (asp.missing_waec || []).length > 0 && (
          <p className="text-muted" style={{ marginTop: '.35rem', marginBottom: 0, fontSize: '.85rem' }}>
            <i aria-hidden="true" className="fas fa-triangle-exclamation" style={{ color: 'var(--warning)' }} /> O'level subject(s) not yet projected to credit: <strong>{asp.missing_waec.join(', ')}</strong>
          </p>
        )}
        {asp && (asp.reasons || []).length > 0 && asp.status === 'ON_TRACK' && (
          <p className="text-muted" style={{ marginTop: '.75rem', marginBottom: 0, fontSize: '.85rem' }}>
            <i aria-hidden="true" className="fas fa-circle-check" style={{ color: 'var(--success)' }} /> Projected to meet subject, credit and score requirements for this course.
          </p>
        )}

        {(scholarships && scholarships.length > 0) && (
          <div style={{ marginTop: '1rem' }}>
            <strong style={{ display: 'block', marginBottom: '.5rem' }}><i aria-hidden="true" className="fas fa-award" /> Scholarships</strong>
            <div className="data-cards">
              {scholarships.map((sc, i) => (
                <div className="data-card" key={i}>
                  <div className="data-card-header">
                    <div className="data-card-title">{sc.name}</div>
                    {sc.status && <span className="badge badge-info">{sc.status}</span>}
                  </div>
                  {sc.provider && <div className="data-card-row"><span className="data-card-label">Provider</span><span>{sc.provider}</span></div>}
                  {sc.amount != null && <div className="data-card-row"><span className="data-card-label">Amount</span><span>₦{Number(sc.amount).toLocaleString()}</span></div>}
                </div>
              ))}
            </div>
          </div>
        )}
    </Section>
  );
}

export default function ViewApp({ initial }) {
  const [data, setData] = useState(initial || {});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTabState] = useState(tabFromHash);
  const [sheet, setSheet] = useState(null);           // 'discipline' | 'clinic' | null
  const phone = useMedia('(max-width: 759px)');
  const d = data || {};
  const s = d.student || {};
  const urls = d.urls || {};
  const canEditStudent = canWrite(d, 'edit');
  const initials = (s.full_name || '?').split(' ').filter(Boolean).slice(0, 2)
    .map((w) => w[0]).join('').toUpperCase() || '?';
  const cur = (d.enrollments || [])[0];
  const curClass = cur ? [cur.class, cur.arm].filter(Boolean).join(' ') : '';
  const contacts = d.contacts || [];
  const primary = contacts.find((c) => c.is_primary) || contacts[0];
  const att = d.attendance;
  const asp = d.aspiration;
  const aspSt = asp && asp.status ? ELIG_STYLE[asp.status] : null;
  const discipline = d.discipline || [];
  const clinic = d.clinic || [];

  // Record this profile in the "recently viewed" list the students list offers
  // as quick links. Keyed by id so re-opening just bumps it to the top.
  useEffect(() => {
    if (s.id) rememberViewed({ id: s.id, name: s.full_name, student_id: s.student_id,
                               photo: s.photo_url || '',
                               url: (urls.self || window.location.pathname) });
  }, [s.id]);

  // The Contacts tab only exists on phones; on laptops contacts live in the rail.
  useEffect(() => { if (!phone && tab === 'contacts') setTabState('overview'); }, [phone]);
  const setTab = (k) => {
    setTabState(k);
    try { window.history.replaceState(null, '', '#' + k); } catch (e) { /* ignore */ }
  };

  const refresh = async () => {
    try { setData(await apiGet(`/api/students/${s.id}`)); } catch (e) { /* keep */ }
  };
  const run = async (url, fields, okMsg) => {
    setBusy(true); setMsg(null);
    try {
      const res = await postForm(url, fields);
      if (!res.ok && !(res.redirected || res.type === 'opaqueredirect')) {
        const ct = res.headers.get('content-type') || '';
        const text = ct.includes('json') ? (await res.json()).error : 'Action failed.';
        setMsg({ tone: 'error', text: text || 'Action failed.' }); return false;
      }
      setMsg({ tone: 'success', text: okMsg });
      await refresh();
      return true;
    } catch (e) { setMsg({ tone: 'error', text: e.message || 'Action failed.' }); return false; }
    finally { setBusy(false); }
  };
  const graduate = async () => {
    if (await confirm(`${s.is_graduated ? 'Undo graduation for' : 'Mark as graduate:'} ${s.full_name}?`))
      run(urls.graduate, {}, 'Updated graduation status.');
  };

  const moreItems = [
    { href: urls.predictions, icon: 'fa-chart-line', label: 'Predictions' },
    urls.id_card && { href: urls.id_card, icon: 'fa-id-card', label: 'ID Card' },
    phone && { href: urls.exam_report, icon: 'fa-file-lines', label: 'Exam Report' },
    att && att.url && { href: att.url, icon: 'fa-calendar-check', label: 'Attendance profile' },
    canEditStudent && { onClick: graduate, icon: s.is_graduated ? 'fa-rotate-left' : 'fa-user-graduate',
                        label: s.is_graduated ? 'Undo graduation' : 'Mark as graduate' },
    { href: urls.list, icon: 'fa-arrow-left', label: 'Back to students' },
  ];

  // ── Quick facts strip (tap → jumps to the tab that explains it) ──
  const jamb = (d.jamb || {}).latest;
  const stats = [
    att && { k: 'att', label: 'Attendance', value: att.percentage + '%', tone: att.warning ? 'bad' : 'good',
             sub: [att.term_name, att.session_name].filter(Boolean).join(' · ') || 'This term', go: phone ? 'overview' : null },
    { k: 'jamb', label: 'JAMB', value: jamb ? jamb.score : '—', sub: jamb ? `${jamb.year} · of 400` : 'No result', go: 'exams' },
    { k: 'waec', label: 'WAEC', value: (d.waec || {}).count || 0, sub: 'subjects', go: 'exams' },
    d.neco && { k: 'neco', label: 'NECO', value: d.neco.count || 0, sub: 'subjects', go: 'exams' },
    asp && asp.status && { k: 'asp', label: 'Aspiration', value: asp.status_label, small: true,
                           tone: { ON_TRACK: 'good', CLOSE: 'warn', OFF_TRACK: 'bad' }[asp.status], sub: s.target_course || 'Target', go: 'overview' },
    { k: 'disc', label: 'Discipline', value: discipline.length, tone: discipline.some((r) => r.severity === 'Major') ? 'bad' : null,
      sub: discipline.length ? `last ${discipline[0].date}` : 'Clean record', go: 'records' },
  ].filter(Boolean);

  const tabs = TABS.filter((t) => phone || !t.phoneOnly);
  const counts = { records: discipline.length + clinic.length,
                   exams: ((d.waec || {}).count ? 1 : 0) + ((d.neco || {}).count ? 1 : 0) + (jamb ? 1 : 0),
                   contacts: contacts.length };

  const contactsCard = (
    <Section icon="fa-address-book" title="Contacts" className="sv-contacts"
             badge={contacts.length ? <span className="sv-count">{contacts.length}</span> : null}
             action={canEditStudent ? <a href={urls.edit} className="sv-link">Manage</a> : null}>
      {contacts.length ? (
        <ul className="sv-people">
          {contacts.map((c, i) => (
            <li key={i}>
              <span className="sv-pav" aria-hidden="true">{(c.name || c.relationship || '?').trim()[0].toUpperCase()}</span>
              <span className="sv-pmain">
                <strong>{c.name || 'Contact'}{c.is_primary && <span className="sv-prim">Primary</span>}</strong>
                <span className="text-muted">{[c.relationship, c.phone_number].filter(Boolean).join(' · ')}<CopyBtn text={c.phone_number} /></span>
              </span>
              {c.phone_number && <span className="sv-pact">
                <a href={'sms:' + c.phone_number} className="sv-round sm" aria-label={`Text ${c.name || 'contact'}`}><i aria-hidden="true" className="fas fa-comment" /></a>
                <a href={'tel:' + c.phone_number} className="sv-round sm sv-call" aria-label={`Call ${c.name || 'contact'}`}><i aria-hidden="true" className="fas fa-phone" /></a>
              </span>}
            </li>
          ))}
        </ul>
      ) : <p className="sv-empty">No contacts added{canEditStudent ? ' — add a parent or guardian from Edit.' : '.'}</p>}
    </Section>
  );

  const attendanceCard = att ? (
    <Section icon="fa-calendar-check" title="Attendance"
             badge={<span className={'sv-pill ' + (att.warning ? 'bad' : 'good')}>{att.percentage}%</span>}
             action={att.url ? <a href={att.url} className="sv-link">Full profile</a> : null}>
      <div className="att-summary">
        <div className="att-donut-wrap">
          <AttendanceDonut pct={att.percentage} warning={att.warning} label={att.term_name || 'This term'} />
          {att.warning && att.threshold != null && <span className="text-muted att-donut-warn">below {att.threshold}% threshold</span>}
        </div>
        <div className="sv-att-legend">
          <span><i className="dot good" />Present <b>{att.present_days}</b></span>
          <span><i className="dot warn" />Late <b>{att.late_days}</b></span>
          <span><i className="dot bad" />Absent <b>{att.absent_days}</b></span>
          {att.terms > 1 && <span className="text-muted">Overall ({att.terms} terms) <b>{att.overall_percentage}%</b></span>}
        </div>
      </div>
    </Section>
  ) : null;

  return (
    <div className={'sv' + (phone ? ' sv-phone' : '')}>
      {/* ── Profile header ── */}
      <header className="sv-head">
        <div className="sv-band" aria-hidden="true" />
        <div className="sv-head-row">
          {s.photo_url
            ? <img className="sv-avatar" src={s.photo_url} alt={s.full_name} />
            : <div className="sv-avatar sv-avatar-ph" aria-hidden="true">{initials}</div>}
          <div className="sv-id">
            <h1 className="sv-name">{s.full_name}</h1>
            <div className="sv-meta">
              <span className="sv-sid">{s.student_id}<CopyBtn text={s.student_id} /></span>
              {curClass && <span><i aria-hidden="true" className="fas fa-school" /> {curClass}</span>}
              {cur && cur.term && !phone && <span className="text-muted">{cur.term}</span>}
            </div>
            <div className="sp-chips">
              {s.is_graduated && <span className="sp-chip sv-chip-grad"><i aria-hidden="true" className="fas fa-user-graduate" /> Graduate{s.graduated_on ? ` · ${s.graduated_on}` : ''}</span>}
              {s.gender && <span className={'sp-chip ' + (s.gender === 'Male' ? 'sp-chip-blue' : 'sp-chip-rose')}><i aria-hidden="true" className={'fas ' + (s.gender === 'Male' ? 'fa-mars' : 'fa-venus')} /> {s.gender}</span>}
              {s.age != null && <span className="sp-chip"><i aria-hidden="true" className="fas fa-cake-candles" /> {s.age} yrs</span>}
              {s.stream && <span className="sp-chip"><i aria-hidden="true" className="fas fa-cube" /> {s.stream}</span>}
              {s.house && <span className="sp-chip"><i aria-hidden="true" className="fas fa-flag" /> {s.house}</span>}
              {s.boarding_status && <span className="sp-chip"><i aria-hidden="true" className="fas fa-bed" /> {s.boarding_status}</span>}
            </div>
          </div>
          {!phone && (
            <div className="sv-head-acts">
              {canEditStudent && <a href={urls.edit} className="btn btn-primary"><i aria-hidden="true" className="fas fa-pen" /> Edit</a>}
              <a href={urls.exam_report} className="sp-btn"><i aria-hidden="true" className="fas fa-file-lines" /> Exam Report</a>
              <a href={urls.report_card} className="sp-btn"><i aria-hidden="true" className="fas fa-file-invoice" /> Report Card</a>
              <Menu items={moreItems} />
            </div>
          )}
        </div>
        {phone && (
          <div className="sv-quick">
            {primary && primary.phone_number
              ? <a href={'tel:' + primary.phone_number} className="sv-qa"><span className="sv-round sv-call"><i aria-hidden="true" className="fas fa-phone" /></span>Call</a>
              : <button type="button" className="sv-qa" onClick={() => setTab('contacts')}><span className="sv-round"><i aria-hidden="true" className="fas fa-address-book" /></span>Contacts</button>}
            <a href={urls.report_card} className="sv-qa"><span className="sv-round"><i aria-hidden="true" className="fas fa-file-invoice" /></span>Report</a>
            <a href={urls.exam_report} className="sv-qa"><span className="sv-round"><i aria-hidden="true" className="fas fa-chart-column" /></span>Exams</a>
            {canEditStudent && <a href={urls.edit} className="sv-qa"><span className="sv-round"><i aria-hidden="true" className="fas fa-pen" /></span>Edit</a>}
            <div className="sv-qa"><Menu items={moreItems} className="sv-round" sheet /><span>More</span></div>
          </div>
        )}
      </header>

      {msg && (
        <div className={'alert alert-' + ({ success: 'success', error: 'danger' }[msg.tone] || 'info') + ' sv-msg'} role="status">
          <span>{msg.text}</span>
          <button type="button" onClick={() => setMsg(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      {/* ── Quick facts ── */}
      <div className="sv-stats">
        {stats.map((t) => (
          <button type="button" key={t.k} className={'sv-stat' + (t.tone ? ' ' + t.tone : '')}
                  onClick={() => t.go && setTab(t.go)} disabled={!t.go}>
            <span className="sv-stat-l">{t.label}</span>
            <span className={'sv-stat-v' + (t.small ? ' small' : '')}>{t.value}</span>
            <span className="sv-stat-s">{t.sub}</span>
          </button>
        ))}
      </div>

      {/* ── Tabs ── */}
      <nav className="sv-tabs" role="tablist" aria-label="Profile sections">
        {tabs.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key}
                  className={tab === t.key ? 'on' : ''} onClick={() => setTab(t.key)}>
            {!phone && <i aria-hidden="true" className={'fas ' + t.icon} />}{t.label}
            {counts[t.key] > 0 && t.key !== 'exams' && <span className="sv-tab-n">{counts[t.key]}</span>}
          </button>
        ))}
      </nav>

      <div className="sv-cols">
        <main className="sv-main" role="tabpanel">
          {tab === 'overview' && (
            <div className="sv-grid">
              {phone && attendanceCard}
              <Section icon="fa-user" title="Personal"
                       action={canEditStudent ? <a href={urls.edit} className="sv-link">Edit</a> : null}>
                <div className="info-grid">
                  <Info label="Full Name" copy={s.full_name}>{s.full_name}</Info>
                  <Info label="Gender" copy={s.gender}>{s.gender || 'Not set'}</Info>
                  <Info label="Date of Birth" copy={s.date_of_birth}>{s.date_of_birth || 'Not set'}</Info>
                  <Info label="Age" copy={s.age != null ? String(s.age) : null}>{s.age != null ? s.age + ' years' : 'N/A'}</Info>
                  <Info label="Religion" copy={s.religion}>{s.religion || 'Not set'}</Info>
                  <Info label="Address" copy={s.home_address}>{s.home_address || 'Not set'}</Info>
                  <Info label="Hobbies" copy={s.hobbies}>{s.hobbies || 'Not set'}</Info>
                  <Info label="Stream" copy={s.stream}>{s.stream || 'Not set'}</Info>
                </div>
              </Section>
              <AspirationCard s={s} asp={asp} scholarships={d.scholarships || []} />
              {((d.identity && d.identity.nin) || s.house || s.boarding_status) && (
                <Section icon="fa-id-card" title="Identity & Pastoral">
                  <div className="info-grid">
                    {d.identity && d.identity.nin && <Info label="NIN">{d.identity.nin}</Info>}
                    {s.house && <Info label="House">{s.house}</Info>}
                    {s.boarding_status && <Info label="Boarding">{s.boarding_status}</Info>}
                  </div>
                </Section>
              )}
              {d.medical && (
                <Section icon="fa-notes-medical" title="Medical">
                  <div className="info-grid">
                    {d.medical.blood_group && <Info label="Blood Group"><span className="badge badge-danger">{d.medical.blood_group}</span></Info>}
                    {d.medical.genotype && <Info label="Genotype"><span className="badge badge-warning">{d.medical.genotype}</span></Info>}
                    {d.medical.allergies && <Info label="Allergies">{d.medical.allergies}</Info>}
                    {d.medical.medical_conditions && <Info label="Conditions">{d.medical.medical_conditions}</Info>}
                    {d.medical.disabilities && <Info label="Disabilities">{d.medical.disabilities}</Info>}
                    {d.medical.medications && <Info label="Medications">{d.medical.medications}</Info>}
                    {d.medical.medical_notes && <Info label="Notes">{d.medical.medical_notes}</Info>}
                    {d.medical.emergency_medical && <Info label="Emergency Instructions">{d.medical.emergency_medical}</Info>}
                  </div>
                </Section>
              )}
            </div>
          )}

          {tab === 'exams' && (
            <div className="sv-grid">
              <div className="sv-exams sv-wide">
                <ExamTile name="WAEC" icon="fa-file-alt" tone="waec" count={(d.waec || {}).count}
                          unit="subjects" addUrl={(d.waec || {}).add_url} viewUrl={(d.waec || {}).view_url} />
                {d.neco && <ExamTile name="NECO" icon="fa-file-lines" tone="neco" count={d.neco.count}
                          unit="subjects" addUrl={d.neco.add_url} viewUrl={d.neco.view_url} />}
                <ExamTile name="JAMB" icon="fa-file-contract" tone="jamb" count={jamb ? jamb.score : 0}
                          unit={jamb ? `of 400 · ${jamb.year}` : ''} addUrl={(d.jamb || {}).add_url}
                          target={asp && asp.target ? asp.target : s.jamb_target} score={jamb ? jamb.score : null} />
              </div>
              <ExamNumbers id={d.identity} />
              <Section icon="fa-chart-line" title="Reports & forecasts">
                <ul className="sv-links">
                  <li><a href={urls.exam_report}><i aria-hidden="true" className="fas fa-file-lines" /><span><strong>Exam report</strong><small>All board and mock results in one place</small></span><i aria-hidden="true" className="fas fa-chevron-right" /></a></li>
                  <li><a href={urls.predictions}><i aria-hidden="true" className="fas fa-chart-line" /><span><strong>Predictions</strong><small>Projected WAEC grades and JAMB score</small></span><i aria-hidden="true" className="fas fa-chevron-right" /></a></li>
                  <li><a href={urls.report_card}><i aria-hidden="true" className="fas fa-file-invoice" /><span><strong>Report card</strong><small>Termly class scores</small></span><i aria-hidden="true" className="fas fa-chevron-right" /></a></li>
                </ul>
              </Section>
            </div>
          )}

          {tab === 'records' && (
            <div className="sv-grid">
              <Section icon="fa-gavel" title="Discipline"
                       badge={<span className="sv-count">{discipline.length}</span>}
                       action={<button type="button" className="sp-btn sp-btn-sm sp-btn-primary" onClick={() => setSheet('discipline')}><i aria-hidden="true" className="fas fa-plus" /> Add</button>}>
                {discipline.length ? (
                  <ul className="sv-log">{discipline.map((r) => (
                    <li key={r.id} className={r.severity === 'Major' ? 'major' : ''}>
                      <div className="sv-log-top">
                        <strong>{r.category || 'Incident'}</strong>
                        {r.severity && <span className={'sv-pill ' + (r.severity === 'Major' ? 'bad' : 'warn')}>{r.severity}</span>}
                        <span className="sv-log-date">{r.date}</span>
                      </div>
                      <p>{r.description}</p>
                      <div className="sv-log-foot">
                        <span>{r.action_taken ? <><b>Action:</b> {r.action_taken}</> : 'No action recorded'}{r.reported_by && <span className="text-muted"> · {r.reported_by}</span>}</span>
                        <button type="button" className="sv-del" disabled={busy} aria-label="Remove record"
                                onClick={async () => { if (await confirm('Remove this record?')) run(r.delete_url, {}, 'Record removed.'); }}><i aria-hidden="true" className="fas fa-trash-can" /></button>
                      </div>
                    </li>
                  ))}</ul>
                ) : <p className="sv-empty"><i aria-hidden="true" className="fas fa-circle-check" /> No discipline records.</p>}
              </Section>

              <Section icon="fa-briefcase-medical" title="Sick Bay"
                       badge={<span className="sv-count">{clinic.length}</span>}
                       action={<button type="button" className="sp-btn sp-btn-sm sp-btn-primary" onClick={() => setSheet('clinic')}><i aria-hidden="true" className="fas fa-plus" /> Add</button>}>
                {clinic.length ? (
                  <ul className="sv-log">{clinic.map((v) => (
                    <li key={v.id}>
                      <div className="sv-log-top">
                        <strong>{v.complaint}</strong>
                        <span className={'sv-pill ' + (v.parent_notified ? 'good' : 'warn')}>{v.parent_notified ? 'Parent told' : 'Parent not told'}</span>
                        <span className="sv-log-date">{v.date}</span>
                      </div>
                      <div className="sv-log-foot">
                        <span>{v.treatment ? <><b>Treatment:</b> {v.treatment}</> : 'No treatment recorded'}{v.attended_by && <span className="text-muted"> · {v.attended_by}</span>}</span>
                        <button type="button" className="sv-del" disabled={busy} aria-label="Remove visit"
                                onClick={async () => { if (await confirm('Remove this visit?')) run(v.delete_url, {}, 'Visit removed.'); }}><i aria-hidden="true" className="fas fa-trash-can" /></button>
                      </div>
                    </li>
                  ))}</ul>
                ) : <p className="sv-empty"><i aria-hidden="true" className="fas fa-circle-check" /> No clinic visits.</p>}
              </Section>

              <Section icon="fa-school" title="Class History"
                       badge={(d.enrollments || []).length ? <span className="sv-count">{d.enrollments.length}</span> : null}>
                {(d.enrollments || []).length ? (
                  <ol className="sv-timeline">{d.enrollments.map((e, i) => (
                    <li key={i} className={i === 0 ? 'now' : ''}>
                      <strong>{[e.class, e.arm].filter(Boolean).join(' ')}</strong>
                      <span className="text-muted">{e.term}</span>
                    </li>
                  ))}</ol>
                ) : <p className="sv-empty">Not enrolled yet.</p>}
              </Section>

              {d.communications && d.communications.count > 0 && (
                <Section icon="fa-comments" title="Messages to parents"
                         badge={<span className="sv-count">{d.communications.count}</span>}>
                  <ul className="sv-log">{d.communications.items.map((m, i) => (
                    <li key={i}>
                      <div className="sv-log-top">
                        <strong>{m.title}</strong>
                        <span className={'sv-pill ' + (m.status === 'Sent' ? 'good' : m.status === 'Failed' ? 'bad' : 'warn')}>{m.status}{m.read ? ' · read' : ''}</span>
                        <span className="sv-log-date">{m.date || ''}</span>
                      </div>
                      {m.snippet && <p className="text-muted">{m.snippet}</p>}
                      {m.channel && <div className="sv-log-foot"><span className="text-muted">{m.channel}</span></div>}
                    </li>
                  ))}</ul>
                </Section>
              )}

              {d.history && d.history.length > 0 && <ChangeHistory rows={d.history} />}
            </div>
          )}

          {tab === 'contacts' && phone && <div className="sv-grid">{contactsCard}</div>}
        </main>

        {!phone && (
          <aside className="sv-rail">
            {contactsCard}
            {attendanceCard}
          </aside>
        )}
      </div>

      {sheet === 'discipline' && (
        <Sheet title="Add discipline record" onClose={() => setSheet(null)}>
          <DisciplineForm categories={d.discipline_categories || []} today={d.today} disabled={busy}
                          onAdd={async (f) => { const ok = await run(urls.discipline_add, f, 'Discipline record added.'); if (ok) setSheet(null); return ok; }} />
        </Sheet>
      )}
      {sheet === 'clinic' && (
        <Sheet title="Add sick bay visit" onClose={() => setSheet(null)}>
          <ClinicForm today={d.today} disabled={busy}
                      onAdd={async (f) => { const ok = await run(urls.clinic_add, f, 'Clinic visit added.'); if (ok) setSheet(null); return ok; }} />
        </Sheet>
      )}
    </div>
  );
}

// One exam tile on the Exams tab: big number, what it means, View / Add.
function ExamTile({ name, icon, tone, count, unit, addUrl, viewUrl, target, score }) {
  const has = !!count;
  const pct = (target && score != null) ? Math.max(0, Math.min(100, Math.round((score / 400) * 100))) : null;
  const tpct = target ? Math.round((target / 400) * 100) : null;
  return (
    <div className={'sv-exam ' + tone}>
      <div className="sv-exam-top">
        <span className="sv-exam-ic"><i aria-hidden="true" className={'fas ' + icon} /></span>
        <strong>{name}</strong>
      </div>
      {has
        ? <div className="sv-exam-v">{count}<small>{unit}</small></div>
        : <div className="sv-exam-none">No {name} results yet</div>}
      {pct != null && (
        <div className="sv-exam-bar" title={`Target ${target}`}>
          <span style={{ width: pct + '%' }} className={score >= target ? 'met' : ''} />
          <i style={{ left: tpct + '%' }} aria-hidden="true" />
          <small>{score >= target ? 'Target met' : `${target - score} below target ${target}`}</small>
        </div>
      )}
      <div className="sv-exam-acts">
        {has && viewUrl && <a href={viewUrl} className="sp-btn sp-btn-sm sp-btn-primary"><i aria-hidden="true" className="fas fa-eye" /> View</a>}
        {addUrl && <a href={addUrl} className="sp-btn sp-btn-sm"><i aria-hidden="true" className="fas fa-plus" /> Add</a>}
      </div>
    </div>
  );
}

// Exam registration numbers / PINs (all copyable) — the details staff copy
// into the WAEC, NECO and JAMB portals.
function ExamNumbers({ id }) {
  const rows = id ? [
    ['WAEC Reg. Number', id.waec_reg_number], ['Serial Number', id.serial_number], ['WAEC e-PIN', id.waec_epin],
    ['NECO Reg. Number', id.neco_reg_number], ['NECO Token / e-PIN', id.neco_epin],
    ['JAMB Reg. Number', id.jamb_reg_number], ['JAMB Profile Code', id.jamb_profile_code],
  ].filter((r) => r[1]) : [];
  return (
    <Section icon="fa-hashtag" title="Exam numbers & PINs">
      {rows.length
        ? <div className="info-grid">{rows.map(([l, v]) => <Info key={l} label={l}>{v}</Info>)}</div>
        : <p className="sv-empty">No exam numbers recorded yet.</p>}
    </Section>
  );
}

const ACTION_LABELS = {
  'student.create': 'Created', 'student.update': 'Edited', 'student.import': 'Imported',
  'delete_student': 'Deleted', 'bulk_set_stream': 'Stream (bulk)', 'bulk_set_gender': 'Gender (bulk)',
  'bulk_set_house': 'House (bulk)', 'bulk_set_boarding': 'Boarding (bulk)',
  'bulk_message_students': 'Messaged parents', 'bulk_add_subject': 'WAEC subject (bulk)',
  'welfare.discipline_add': 'Discipline added', 'welfare.discipline_delete': 'Discipline removed',
  'welfare.clinic_add': 'Sick bay visit', 'welfare.clinic_delete': 'Sick bay visit removed',
};

function ChangeHistory({ rows }) {
  const [q, setQ] = useState('');
  const term = q.trim().toLowerCase();
  const shown = term
    ? rows.filter((r) => `${ACTION_LABELS[r.action] || r.action} ${r.user} ${r.detail} ${r.when}`.toLowerCase().includes(term))
    : rows;
  return (
    <Section icon="fa-clock-rotate-left" title="Change History" wide
             badge={<span className="badge badge-secondary">{rows.length}</span>}>
        <input type="search" className="form-control" style={{ maxWidth: 240, marginBottom: '.7rem' }} placeholder="Search history…"
               value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search change history" />
        {shown.length ? (
          <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
            <table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>When</th><th>Action</th><th>By</th><th>Details</th></tr></thead>
              <tbody>{shown.map((r, i) => (
                <tr key={i}>
                  <td data-label="When" style={{ whiteSpace: 'nowrap' }}>{r.when}</td>
                  <td data-label="Action"><span className="badge badge-secondary">{ACTION_LABELS[r.action] || r.action}</span></td>
                  <td data-label="By">{r.user}{r.role && <span className="text-muted"> · {r.role}</span>}</td>
                  <td data-label="Details" style={{ fontSize: '.85rem' }}>{r.detail || '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : <p className="text-muted">No matching history.</p>}
    </Section>
  );
}

function DisciplineForm({ categories, today, disabled, onAdd }) {
  const [f, setF] = useState({ date: today || '', category: categories[0] || '', severity: 'Minor', description: '', action_taken: '' });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.description.trim()) return;
    if (await onAdd(f)) setF((x) => ({ ...x, description: '', action_taken: '' }));
  };
  return (
    <form onSubmit={submit} className="sv-form">
      <div className="form-group"><label className="form-label">Date</label><input type="date" className="form-control" value={f.date} onChange={(e) => set('date', e.target.value)} /></div>
      <div className="form-group"><label className="form-label">Category</label>
        <select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select></div>
      <div className="form-group"><label className="form-label">Severity</label>
        <select className="form-control" value={f.severity} onChange={(e) => set('severity', e.target.value)}><option>Minor</option><option>Major</option></select></div>
      <div className="form-group sv-full"><label className="form-label">What happened</label>
        <input type="text" className="form-control" placeholder="Describe the incident" required value={f.description} onChange={(e) => set('description', e.target.value)} /></div>
      <div className="form-group sv-full"><label className="form-label">Action taken</label>
        <input type="text" className="form-control" placeholder="e.g., Warning, parent called" value={f.action_taken} onChange={(e) => set('action_taken', e.target.value)} /></div>
      <button type="submit" className="btn btn-primary sv-form-go" disabled={disabled}><i aria-hidden="true" className="fas fa-plus" /> Save record</button>
    </form>
  );
}

function ClinicForm({ today, disabled, onAdd }) {
  const [f, setF] = useState({ date: today || '', complaint: '', treatment: '', parent_notified: false });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.complaint.trim()) return;
    const ok = await onAdd({ ...f, parent_notified: f.parent_notified ? 'on' : '' });
    if (ok) setF((x) => ({ ...x, complaint: '', treatment: '', parent_notified: false }));
  };
  return (
    <form onSubmit={submit} className="sv-form">
      <div className="form-group"><label className="form-label">Date</label><input type="date" className="form-control" value={f.date} onChange={(e) => set('date', e.target.value)} /></div>
      <div className="form-group sv-full"><label className="form-label">Complaint / symptom</label>
        <input type="text" className="form-control" placeholder="e.g., Headache, fever" required value={f.complaint} onChange={(e) => set('complaint', e.target.value)} /></div>
      <div className="form-group sv-full"><label className="form-label">Treatment given</label>
        <input type="text" className="form-control" placeholder="e.g., Paracetamol, rest" value={f.treatment} onChange={(e) => set('treatment', e.target.value)} /></div>
      <div className="form-group"><label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
        <input type="checkbox" checked={f.parent_notified} onChange={(e) => set('parent_notified', e.target.checked)} /> Parent notified</label></div>
      <button type="submit" className="btn btn-primary sv-form-go" disabled={disabled}><i aria-hidden="true" className="fas fa-plus" /> Save record</button>
    </form>
  );
}
