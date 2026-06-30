import React, { useEffect, useState, useCallback } from 'react';
import { apiGet, apiPost, isPermanent } from '../../lib/api';
import { cachePut, cacheGet, enqueue } from '../../lib/offline';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Button, Spinner, EmptyState, ErrorState, Banner, Pill, Toast } from '../../components/ui';

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
  // Remember the chosen class for next time.
  useEffect(() => {
    if (assignmentId) { try { localStorage.setItem('attendance:lastClass', String(assignmentId)); } catch (e) { /* ignore */ } }
  }, [assignmentId]);
  const [state, setState] = useState({ idle: true });   // idle | loading | data | error
  // Per enrollment: { am: bool, pm: bool }. Morning and afternoon are marked
  // independently and saved together — no "which session?" picker.
  const [present, setPresent] = useState({});
  const [msg, setMsg] = useState(null);
  const [toast, setToast] = useState(null);   // floating save confirmation (no scroll)
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
      const r = await apiPost('/attendance/api/mark', payload);
      setToast({ tone: 'success', text: `Saved ${r.count} student(s) — morning & afternoon.` });
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

  const boxStyle = { width: 22, height: 22, accentColor: 'var(--success, var(--success))', cursor: 'pointer' };
  const colStyle = { width: 52, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 };

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
      </Toolbar>

      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      {toast && <Toast tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}

      {state.idle && <EmptyState icon="fa-hand-pointer" title="Pick a class" hint="Choose a class and date to load its register. Loaded classes are cached so you can re-open them offline." />}
      {state.loading && <Spinner label="Loading register…" />}
      {state.error && <ErrorState title="Couldn’t load this class" detail={state.error.message} onRetry={load} />}

      {d && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
            <strong>{d.class_name}</strong>
            <span style={{ color: 'var(--text-muted)' }}>{d.date}</span>
            {state.source === 'cache' && <Pill tone="amber">cached</Pill>}
            {weekCached && online && <Pill tone="green"><i className="fas fa-download" aria-hidden="true" /> week saved offline</Pill>}
            <span style={{ marginLeft: 'auto', fontSize: 'var(--text-sm)' }}>AM <b>{amCount}</b>/{d.students.length} · PM <b>{pmCount}</b>/{d.students.length}</span>
          </div>

          {!d.week_id && <Banner tone="warn">This date isn’t in a school week — you can review, but saving is disabled.</Banner>}

          {notSchoolDay ? (
            <EmptyState icon="fa-calendar-xmark" title="Not a school day" hint={notSchoolReason} />
          ) : d.students.length === 0 ? (
            <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
          ) : (
            <>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)', margin: '4px 0 8px' }}>
                Everyone starts present. Untick a box to mark a student absent for just the morning or just the afternoon.
              </p>
              <ul className="att-list" aria-label={'Register for ' + d.class_name}>
                <li style={{ display: 'flex', alignItems: 'center', fontWeight: 700, borderBottom: '2px solid var(--border-color, var(--border-color))', padding: '6px 8px' }}>
                  <span style={{ flex: 1 }}>Student</span>
                  <span style={colStyle}>AM</span>
                  <span style={colStyle}>PM</span>
                </li>
                {d.students.map((s) => {
                  const v = present[s.enrollment_id] || { am: true, pm: true };
                  return (
                    <li key={s.enrollment_id} className={(v.am || v.pm) ? 'is-present' : 'is-absent'}
                        style={{ display: 'flex', alignItems: 'center', padding: '8px' }}>
                      <span className="att-av" data-g={s.gender || ''} aria-hidden="true">{initialsOf(s.name)}</span>
                      <span className="att-name" style={{ flex: 1 }}>{s.name}<span className="att-sub">{s.student_id}{s.gender ? ' · ' + s.gender : ''}</span></span>
                      <label style={colStyle}>
                        <input type="checkbox" style={boxStyle} checked={v.am} onChange={() => toggle(s.enrollment_id, 'am')} aria-label={`${s.name} present morning`} />
                      </label>
                      <label style={colStyle}>
                        <input type="checkbox" style={boxStyle} checked={v.pm} onChange={() => toggle(s.enrollment_id, 'pm')} aria-label={`${s.name} present afternoon`} />
                      </label>
                    </li>
                  );
                })}
              </ul>
            </>
          )}

          <div className="att-actions">
            <Button variant="secondary" size="sm" onClick={() => setAll('all', true)} disabled={!d.students.length || notSchoolDay}>All present</Button>
            <Button variant="light" size="sm" onClick={() => setAll('all', false)} disabled={!d.students.length || notSchoolDay}>All absent</Button>
            <Button variant="light" size="sm" onClick={() => setAll('am', false)} disabled={!d.students.length || notSchoolDay}>Clear AM</Button>
            <Button variant="light" size="sm" onClick={() => setAll('pm', false)} disabled={!d.students.length || notSchoolDay}>Clear PM</Button>
            <Button onClick={save} disabled={!canSave}>Save register</Button>
            <Button variant="light" size="sm" onClick={copyPrevious}
                    disabled={!online || !d.week_id || notSchoolDay || busy}
                    title={online ? 'Copy the previous school day’s marks' : 'Copy previous needs an internet connection'}>
              Copy previous day
            </Button>
            {!online && <span style={{ fontSize: 'var(--text-xs)', color: '#92400e' }}>“Copy previous” needs you to be online.</span>}
          </div>
        </>
      )}
    </div>
  );
}
