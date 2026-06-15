import React, { useEffect, useState, useCallback } from 'react';
import { apiGet, apiPost, isPermanent } from '../../lib/api';
import { cachePut, cacheGet, enqueue } from '../../lib/offline';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Button, Spinner, EmptyState, ErrorState, Banner, Pill } from '../../components/ui';

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

export default function MarkDaily() {
  const { classes = [], today, online, sync, initial } = useCtx();
  // Seed from a deep link only when that class belongs to the loaded term.
  const seeded = initial && classes.some((c) => String(c.id) === String(initial.assignmentId));
  const [assignmentId, setAssignmentId] = useState(seeded ? String(initial.assignmentId) : '');
  const [date, setDate] = useState((seeded && initial.date) || today || '');
  const [session, setSession] = useState('morning');    // morning | afternoon
  const [autoCopyPm, setAutoCopyPm] = useState(true);   // morning also seeds afternoon
  const [state, setState] = useState({ idle: true });   // idle | loading | data | error
  const [present, setPresent] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [weekCached, setWeekCached] = useState(false);

  // After an online load, quietly cache every weekday of that week so the
  // teacher can mark the whole week offline — not just dates they opened first.
  const prefetchWeek = useCallback(async (aid, baseDate) => {
    if (!navigator.onLine) return;
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
    const field = session === 'afternoon' ? 'afternoon_present' : 'morning_present';
    const init = {};
    d.students.forEach((s) => { init[s.enrollment_id] = !!s[field]; });
    setPresent(init);
  }, [state.data, session]);

  const toggle = (id) => setPresent((p) => ({ ...p, [id]: !p[id] }));
  const setAll = (val) => {
    const all = {}; state.data.students.forEach((s) => { all[s.enrollment_id] = val; });
    setPresent(all);
  };

  const save = async () => {
    const d = state.data;
    const presentIds = d.students.filter((s) => present[s.enrollment_id]).map((s) => s.enrollment_id);
    // Marking the morning can also seed the afternoon (opt-out via the
    // checkbox); the afternoon session updates the afternoon only.
    const autoCopy = session === 'morning' && autoCopyPm;
    const payload = { assignment_id: Number(assignmentId), date, session_type: session, present: presentIds, auto_copy: autoCopy };
    // optimistic cache so reopening (even offline) reflects it
    const updated = { ...d, students: d.students.map((s) => {
      const val = !!present[s.enrollment_id];
      if (session === 'afternoon') return { ...s, afternoon_present: val };
      if (autoCopy) return { ...s, morning_present: val, afternoon_present: val };  // morning seeds afternoon
      return { ...s, morning_present: val };
    }) };
    await cachePut(key(assignmentId, date), updated);
    setBusy(true);
    try {
      const r = await apiPost('/attendance/api/mark', payload);
      setMsg({ tone: 'success', text: `Saved ${r.count} student(s).` });
    } catch (e) {
      if (isPermanent(e)) { setMsg({ tone: 'error', text: `Couldn’t save: ${e.message}` }); }
      else { await enqueue('/attendance/api/mark', payload); await sync.refresh(); setMsg({ tone: 'warn', text: 'Offline — queued, will sync when you reconnect.' }); }
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
  const presentCount = d ? d.students.filter((s) => present[s.enrollment_id]).length : 0;
  // A holiday/weekend is not a school day: the server rejects marks, so the
  // register is read-only here (parity with the classic page's block).
  const notSchoolDay = d && d.school_day === false;
  const notSchoolReason = d && (d.holiday
    ? `${d.date} was marked as ${d.holiday.type ? d.holiday.type.toLowerCase() : 'a holiday'}: ${d.holiday.reason}.`
    : d.weekend ? `${d.date} is a weekend.` : `${d.date} is not a school day.`);
  const canSave = d && d.week_id && d.students.length && !notSchoolDay && !busy;

  return (
    <div>
      <Toolbar>
        <Field label="Class" htmlFor="md-class" grow>
          <Select id="md-class" value={assignmentId} onChange={setAssignmentId}
                  placeholder={classes.length ? '— Select class —' : 'No classes available'}
                  options={classes.map((c) => ({ value: String(c.id), label: c.name }))} />
        </Field>
        <Field label="Date" htmlFor="md-date">
          <input id="md-date" type="date" className="form-control" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <Field label="Session" htmlFor="md-session">
          <Select id="md-session" value={session} onChange={setSession}
                  options={[{ value: 'morning', label: 'Morning' }, { value: 'afternoon', label: 'Afternoon' }]} />
        </Field>
      </Toolbar>

      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}

      {state.idle && <EmptyState icon="fa-hand-pointer" title="Pick a class" hint="Choose a class and date to load its register. Loaded classes are cached so you can re-open them offline." />}
      {state.loading && <Spinner label="Loading register…" />}
      {state.error && <ErrorState title="Couldn’t load this class" detail={state.error.message} onRetry={load} />}

      {d && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
            <strong>{d.class_name}</strong>
            <span style={{ color: '#6b7280' }}>{d.date}</span>
            {state.source === 'cache' && <Pill tone="amber">cached</Pill>}
            {weekCached && online && <Pill tone="green"><i className="fas fa-download" aria-hidden="true" /> week saved offline</Pill>}
            <span style={{ marginLeft: 'auto', fontSize: 13 }}>Present: <b>{presentCount}</b>/{d.students.length}</span>
          </div>

          {!d.week_id && <Banner tone="warn">This date isn’t in a school week — you can review, but saving is disabled.</Banner>}

          {notSchoolDay ? (
            <EmptyState icon="fa-calendar-xmark" title="Not a school day" hint={notSchoolReason} />
          ) : d.students.length === 0 ? (
            <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
          ) : (
            <>
              {session === 'morning' && (
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0 10px', fontSize: 14, fontWeight: 500 }}>
                  <input type="checkbox" checked={autoCopyPm} onChange={(e) => setAutoCopyPm(e.target.checked)} />
                  <span><i className="fas fa-copy" aria-hidden="true" /> Also mark afternoon (same as morning)</span>
                </label>
              )}
              <ul className="att-list" aria-label={'Register for ' + d.class_name}>
                {d.students.map((s) => {
                  const on = !!present[s.enrollment_id];
                  return (
                    <li key={s.enrollment_id} className={on ? 'is-present' : 'is-absent'}>
                      <label>
                        <input type="checkbox" checked={on} onChange={() => toggle(s.enrollment_id)} />
                        <span className="att-av" data-g={s.gender || ''} aria-hidden="true">{initialsOf(s.name)}</span>
                        <span className="att-name">{s.name}<span className="att-sub">{s.student_id}{s.gender ? ' · ' + s.gender : ''}</span></span>
                        <span className="att-flag">
                          <i className={'fas ' + (on ? 'fa-check' : 'fa-xmark')} aria-hidden="true" /> {on ? 'Present' : 'Absent'}
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </>
          )}

          <div className="att-actions">
            <Button variant="secondary" size="sm" onClick={() => setAll(true)} disabled={!d.students.length || notSchoolDay}>Mark all present</Button>
            <Button variant="light" size="sm" onClick={() => setAll(false)} disabled={!d.students.length || notSchoolDay}>Mark all absent</Button>
            <Button onClick={save} disabled={!canSave}>Save register</Button>
            <Button variant="light" size="sm" onClick={copyPrevious}
                    disabled={!online || !d.week_id || notSchoolDay || busy}
                    title={online ? 'Copy the previous school day’s marks' : 'Copy previous needs an internet connection'}>
              Copy previous day
            </Button>
            {!online && <span style={{ fontSize: 12, color: '#92400e' }}>“Copy previous” needs you to be online.</span>}
          </div>
        </>
      )}
    </div>
  );
}
