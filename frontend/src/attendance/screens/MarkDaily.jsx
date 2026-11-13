import React, { useEffect, useState, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { apiGet, apiPost, isPermanent } from '../../lib/api';
import { cachePut, cacheGet, enqueue, isSlowConnection } from '../../lib/offline';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, Banner, Pill, Toast } from '../../components/ui';
import { withGroups, genderLabel, groupHeadStyle } from '../roster';
import { rememberClass } from '../../lib/attprefs';

const key = (aid, date) => `roster|${aid}|${date}`;

// Local YYYY-MM-DD (no UTC shift) for a Date.
const ymd = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;

// Mon–Fri of the week containing `iso` — the days worth caching for offline
// marking (the server flags weekends/holidays as non-school days anyway).
function weekdays(iso) {
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d)) return [];
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return Array.from({ length: 5 }, (_, i) => {
    const x = new Date(monday); x.setDate(monday.getDate() + i); return ymd(x);
  });
}

// Up to two initials from a name, for the row avatar.
const initialsOf = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';


// Step a YYYY-MM-DD date by ±1 school day (skips Saturday and Sunday).
function stepDay(iso, dir) {
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d)) return iso;
  do { d.setDate(d.getDate() + dir); } while (d.getDay() === 0 || d.getDay() === 6);
  return ymd(d);
}
const prettyDate = (iso) => {
  const d = new Date(iso + 'T00:00:00');
  return isNaN(d) ? iso : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
};

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

// Small upward "more actions" menu for the register bar.
function MoreMenu({ items }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close); document.addEventListener('touchstart', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('touchstart', close); };
  }, [open]);
  return (
    <div className="md-more" ref={ref}>
      <button type="button" className="md-btn ghost" aria-haspopup="true" aria-expanded={open} aria-label="More actions" onClick={() => setOpen((v) => !v)}>
        <i className="fas fa-ellipsis" aria-hidden="true" /></button>
      {open && (
        <div className="md-more-pop" role="menu">
          {items.filter(Boolean).map((it, i) => (
            <button key={i} type="button" role="menuitem" disabled={it.disabled} title={it.title}
                    onClick={() => { setOpen(false); it.onClick(); }}>
              <i className={'fas ' + it.icon} aria-hidden="true" /> {it.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function MarkDaily() {
  const { classes = [], today, online, sync, initial, default_class } = useCtx();
  // Seed from a deep link only when that class belongs to the loaded term.
  const seeded = initial && classes.some((c) => String(c.id) === String(initial.assignmentId));
  // Otherwise fall back to the last class this user marked (if still in the list),
  // so admins don't re-pick it every visit.
  const remembered = (() => {
    try {
      const v = localStorage.getItem('attendance:lastClass');
      return v && classes.some((c) => String(c.id) === v) ? v : '';
    } catch (e) { return ''; }
  })();
  // A form teacher lands on their own class without picking it.
  const [assignmentId, setAssignmentId] = useState(
    seeded ? String(initial.assignmentId)
           : (default_class ? String(default_class) : remembered));
  const [date, setDate] = useState((seeded && initial.date) || today || '');
  // Remember the chosen class for next time (shared with the other screens'
  // "recent classes" quick-pick).
  useEffect(() => {
    if (!assignmentId) return;
    const c = classes.find((x) => String(x.id) === String(assignmentId));
    rememberClass(assignmentId, c ? c.name : String(assignmentId));
  }, [assignmentId]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [state, setState] = useState({ idle: true });   // idle | loading | data | error
  // Per enrollment: { am: bool, pm: bool }. Morning and afternoon are marked
  // independently and saved together — no "which session?" picker.
  const [present, setPresent] = useState({});
  const [msg, setMsg] = useState(null);
  const [toast, setToast] = useState(null);   // floating save confirmation (no scroll)
  const [busy, setBusy] = useState(false);
  const [savedSig, setSavedSig] = useState(null);   // marks as last saved → "Saved ✓" until edited
  const [weekCached, setWeekCached] = useState(false);

  // After an online load, quietly cache every weekday of that week so the
  // teacher can mark the whole week offline — not just dates they opened first.
  // Skipped on a detectably slow/metered connection: it's a nice-to-have for
  // offline resilience, but on a slow network it's 4 extra requests competing
  // with the roster the user is actually looking at right now.
  const prefetchWeek = useCallback(async (aid, baseDate) => {
    if (!navigator.onLine || isSlowConnection()) return;
    let any = false;
    for (const dt of weekdays(baseDate)) {
      if (dt === baseDate) { any = true; continue; }
      try {
        const data = await apiGet(`/attendance/api/roster?assignment_id=${aid}&date=${encodeURIComponent(dt)}`);
        await cachePut(key(aid, dt), data);
        any = true;
      } catch (_) { /* best effort — skip days that fail */ }
    }
    setWeekCached(any);
  }, []);

  const load = useCallback(async () => {
    if (!assignmentId || !date) { setState({ idle: true }); return; }
    setState({ loading: true });
    setWeekCached(false);
    const k = key(assignmentId, date);
    try {
      const data = await apiGet(`/attendance/api/roster?assignment_id=${assignmentId}&date=${encodeURIComponent(date)}`);
      await cachePut(k, data);
      setState({ data, source: 'network' });
      prefetchWeek(assignmentId, date);   // fire-and-forget
    } catch (e) {
      const cached = await cacheGet(k);
      if (cached) setState({ data: cached, source: 'cache' });
      else setState({ error: e });
    }
  }, [assignmentId, date, prefetchWeek]);

  useEffect(() => { setMsg(null); load(); }, [load]);

  useEffect(() => {
    const d = state.data;
    if (!d) return;
    const init = {};
    // Default everyone present for both sessions (roster returns true when there
    // is no existing record for the day).
    d.students.forEach((s) => { init[s.enrollment_id] = { am: !!s.morning_present, pm: !!s.afternoon_present }; });
    setPresent(init);
  }, [state.data]);

  const toggle = (id, sess) => setPresent((p) => ({ ...p, [id]: { ...p[id], [sess]: !p[id][sess] } }));
  // val for one session ('am'/'pm') across everyone, or both at once ('all').
  const setAll = (sess, val) => {
    setPresent((p) => {
      const out = {};
      state.data.students.forEach((s) => {
        const cur = p[s.enrollment_id] || { am: true, pm: true };
        out[s.enrollment_id] = {
          am: (sess === 'all' || sess === 'am') ? val : cur.am,
          pm: (sess === 'all' || sess === 'pm') ? val : cur.pm,
        };
      });
      return out;
    });
  };

  const save = async () => {
    const d = state.data;
    const am = d.students.filter((s) => present[s.enrollment_id] && present[s.enrollment_id].am).map((s) => s.enrollment_id);
    const pm = d.students.filter((s) => present[s.enrollment_id] && present[s.enrollment_id].pm).map((s) => s.enrollment_id);
    const payload = { assignment_id: Number(assignmentId), date, mode: 'dual', am, pm };
    // optimistic cache so reopening (even offline) reflects it
    const updated = { ...d, students: d.students.map((s) => {
      const v = present[s.enrollment_id] || { am: true, pm: true };
      return { ...s, morning_present: !!v.am, afternoon_present: !!v.pm };
    }) };
    await cachePut(key(assignmentId, date), updated);
    setBusy(true);
    try {
      await apiPost('/attendance/api/mark', payload);
      const full = d.students.filter((s) => { const v = present[s.enrollment_id] || { am: true, pm: true }; return v.am && v.pm; }).length;
      const day = date ? new Date(date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' }) : 'today';
      setSavedSig(date + JSON.stringify(present));
      setToast({ tone: 'success', text: `Attendance saved for ${day} — ${full} of ${d.students.length} present all day.` });
    } catch (e) {
      if (isPermanent(e)) { setToast({ tone: 'error', text: `Couldn’t save: ${e.message}` }); }
      else { await enqueue('/attendance/api/mark', payload); await sync.refresh(); setToast({ tone: 'warn', text: 'Offline — queued, will sync when you reconnect.' }); }
    } finally { setBusy(false); }
  };

  const copyPrevious = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await apiPost('/attendance/api/copy-previous', { assignment_id: Number(assignmentId), date });
      setMsg({ tone: r.copied ? 'success' : 'warn', text: r.copied ? `Copied ${r.copied} from ${r.from}.` : (r.note || 'Nothing to copy.') });
      await load();
    } catch (e) {
      setMsg({ tone: 'error', text: `Couldn’t copy: ${e.message}` });
    } finally { setBusy(false); }
  };

  const d = state.data;
  const amCount = d ? d.students.filter((s) => present[s.enrollment_id] && present[s.enrollment_id].am).length : 0;
  const pmCount = d ? d.students.filter((s) => present[s.enrollment_id] && present[s.enrollment_id].pm).length : 0;
  // A holiday/weekend is not a school day: the server rejects marks, so the
  // register is read-only here (parity with the classic page's block).
  const notSchoolDay = d && d.school_day === false;
  const notSchoolReason = d && (d.holiday
    ? `${d.date} was marked as ${d.holiday.type ? d.holiday.type.toLowerCase() : 'a holiday'}: ${d.holiday.reason}.`
    : d.weekend ? `${d.date} is a weekend.` : `${d.date} is not a school day.`);
  const canSave = d && d.week_id && d.students.length && !notSchoolDay && !busy;
  const isSaved = !busy && savedSig !== null && savedSig === date + JSON.stringify(present);

  const phone = useMedia('(max-width: 759px)');
  const chipsRef = useRef(null);
  useEffect(() => {
    const el = chipsRef.current && chipsRef.current.querySelector('.on');
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [assignmentId]);
  const total = d ? d.students.length : 0;
  const absentAm = total - amCount;
  const absentPm = total - pmCount;
  const absentees = d ? d.students.filter((s) => { const v = present[s.enrollment_id]; return v && !v.am && !v.pm; }) : [];
  const editable = d && d.students.length && !notSchoolDay;
  // Tap the name: if they're in for any session, mark out for both; otherwise in for both.
  const flipBoth = (id) => setPresent((p) => {
    const v = p[id] || { am: true, pm: true };
    const to = !(v.am || v.pm);
    return { ...p, [id]: { am: to, pm: to } };
  });

  const bar = d && editable ? (
    <div className={'md-bar' + (phone ? ' fixed' : '')}>
      <div className="md-bar-count" aria-live="polite">
        <b>{amCount}</b>/{total} AM · <b>{pmCount}</b>/{total} PM
      </div>
      <button type="button" className="md-btn ghost" onClick={() => setAll('all', true)} title="Mark everyone present">
        <i className="fas fa-check-double" aria-hidden="true" /><span> All present</span></button>
      <MoreMenu items={[
        { icon: 'fa-user-xmark', label: 'Everyone absent', onClick: () => setAll('all', false) },
        { icon: 'fa-sun', label: 'Clear morning (AM)', onClick: () => setAll('am', false) },
        { icon: 'fa-moon', label: 'Clear afternoon (PM)', onClick: () => setAll('pm', false) },
        { icon: 'fa-clone', label: 'Copy previous school day', onClick: copyPrevious,
          disabled: !online || !d.week_id || busy, title: online ? 'Copy the previous school day’s marks' : 'Needs an internet connection' },
      ]} />
      <button type="button" className={'md-btn save' + (isSaved ? ' is-saved' : '')} onClick={save} disabled={!canSave}>
        <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : (isSaved ? 'fa-circle-check' : 'fa-check'))} aria-hidden="true" /> {isSaved ? 'Saved' : 'Save'}</button>
    </div>
  ) : null;

  return (
    <div className={'md' + (phone && d && editable ? ' has-bar' : '')}>
      <section className="md-pick">
        <div className="md-pick-row">
          <span className="md-pick-l">Class</span>
          {classes.length > 8 && (
            <select className="md-select" value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)} aria-label="Class">
              <option value="">Choose a class</option>
              {classes.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
            </select>
          )}
        </div>
        {classes.length === 0 ? <p className="md-none">No classes available for this term.</p> : (
          <div className="md-classes" ref={chipsRef} role="radiogroup" aria-label="Class">
            {classes.map((c) => (
              <button key={c.id} type="button" role="radio" aria-checked={String(c.id) === String(assignmentId)}
                      className={String(c.id) === String(assignmentId) ? 'on' : ''} onClick={() => setAssignmentId(String(c.id))}>
                {c.name}</button>
            ))}
          </div>
        )}
        <div className="md-date">
          <button type="button" className="md-step" onClick={() => setDate(stepDay(date, -1))} aria-label="Previous school day"><i className="fas fa-chevron-left" aria-hidden="true" /></button>
          <label className="md-date-box">
            <i className="fas fa-calendar-day" aria-hidden="true" />
            <span>{prettyDate(date)}</span>
            <input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} aria-label="Date" />
          </label>
          <button type="button" className="md-step" onClick={() => setDate(stepDay(date, 1))} aria-label="Next school day"><i className="fas fa-chevron-right" aria-hidden="true" /></button>
          {today && date !== today && <button type="button" className="md-today" onClick={() => setDate(today)}>Today</button>}
        </div>
      </section>

      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      {toast && <Toast tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}

      {state.idle && <div className="md-card"><EmptyState icon="fa-hand-pointer" title="Pick a class" hint="Choose a class to load its register. Loaded classes are cached so you can re-open them offline." /></div>}
      {state.loading && <div className="md-card"><Spinner label="Loading register…" /></div>}
      {state.error && <div className="md-card"><ErrorState title="Couldn’t load this class" detail={state.error.message} onRetry={load} /></div>}

      {d && (
        <div className="md-card">
          <div className="md-sum">
            <div className="md-sum-t">
              <strong>{d.class_name}</strong>
              <span>{prettyDate(d.date)} · {total} student{total === 1 ? '' : 's'}</span>
              <span className="md-pills">
                {state.source === 'cache' && <Pill tone="amber">cached</Pill>}
                {weekCached && online && <Pill tone="green"><i className="fas fa-download" aria-hidden="true" /> week saved offline</Pill>}
              </span>
            </div>
            {editable ? (
              <div className="md-meters">
                <div className="md-meter"><span>Morning</span><div className="md-track"><i style={{ width: (total ? amCount / total * 100 : 0) + '%' }} /></div><b>{amCount}/{total}</b></div>
                <div className="md-meter"><span>Afternoon</span><div className="md-track"><i style={{ width: (total ? pmCount / total * 100 : 0) + '%' }} /></div><b>{pmCount}/{total}</b></div>
              </div>
            ) : null}
          </div>

          {!d.week_id && <Banner tone="warn">This date isn’t in a school week — you can review, but saving is disabled.</Banner>}

          {notSchoolDay ? (
            <EmptyState icon="fa-calendar-xmark" title="Not a school day" hint={notSchoolReason} />
          ) : d.students.length === 0 ? (
            <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
          ) : (
            <>
              {(absentAm || absentPm) ? (
                <p className="md-note abs"><i className="fas fa-user-xmark" aria-hidden="true" /> {absentees.length ? <>Absent all day: <b>{absentees.map((x) => x.name).join(', ')}</b>{(absentAm > absentees.length || absentPm > absentees.length) ? ' · some half-day' : ''}</> : 'Some students are out for half the day.'}</p>
              ) : (
                <p className="md-note"><i className="fas fa-circle-info" aria-hidden="true" /> Everyone starts present. Tap <b>AM</b> or <b>PM</b> to mark a session absent, or tap a name for the whole day.</p>
              )}
              <ul className="md-list" aria-label={'Register for ' + d.class_name}>
                {withGroups(d.students,
                  (gender, first, gkey) => (
                    <li key={gkey} className="md-ghead">{genderLabel(gender)}
                      <span>{d.students.filter((x) => x.gender === gender).length}</span></li>
                  ),
                  (s) => {
                    const v = present[s.enrollment_id] || { am: true, pm: true };
                    const st = v.am && v.pm ? 'in' : (v.am || v.pm) ? 'half' : 'out';
                    return (
                      <li key={s.enrollment_id} className={'md-row ' + st}>
                        <button type="button" className="md-who" onClick={() => flipBoth(s.enrollment_id)}
                                aria-label={`${s.name}: ${st === 'out' ? 'absent' : st === 'half' ? 'half day' : 'present'}. Tap to toggle the whole day.`}>
                          <span className="att-av" data-g={s.gender || ''} aria-hidden="true">{initialsOf(s.name)}</span>
                          <span className="md-name"><span>{s.name}{s.medical && <i role="img" aria-label={'Medical: ' + s.medical} className="fas fa-heart-pulse md-med" title={s.medical} />}</span><small>{s.student_id}{st === 'out' ? ' · absent' : st === 'half' ? ' · half day' : ''}</small></span>
                        </button>
                        <button type="button" className={'md-tg' + (v.am ? ' on' : '')} aria-pressed={v.am}
                                onClick={() => toggle(s.enrollment_id, 'am')} aria-label={`${s.name} present morning`}>
                          <i className={'fas ' + (v.am ? 'fa-check' : 'fa-xmark')} aria-hidden="true" />AM</button>
                        <button type="button" className={'md-tg' + (v.pm ? ' on' : '')} aria-pressed={v.pm}
                                onClick={() => toggle(s.enrollment_id, 'pm')} aria-label={`${s.name} present afternoon`}>
                          <i className={'fas ' + (v.pm ? 'fa-check' : 'fa-xmark')} aria-hidden="true" />PM</button>
                      </li>
                    );
                  }
                )}
              </ul>
            </>
          )}
          {!phone && bar}
        </div>
      )}
      {phone && bar && createPortal(bar, document.body)}
    </div>
  );
}
