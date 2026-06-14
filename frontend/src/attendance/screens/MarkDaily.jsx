import React, { useEffect, useState, useCallback } from 'react';
import { apiGet, apiPost, isPermanent } from '../../lib/api';
import { cachePut, cacheGet, enqueue } from '../../lib/offline';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Button, Spinner, EmptyState, ErrorState, Banner, Pill } from '../../components/ui';

const key = (aid, date) => `roster|${aid}|${date}`;

export default function MarkDaily() {
  const { classes = [], today, online, sync } = useCtx();
  const [assignmentId, setAssignmentId] = useState('');
  const [date, setDate] = useState(today || '');
  const [session, setSession] = useState('morning');    // morning | afternoon
  const [state, setState] = useState({ idle: true });   // idle | loading | data | error
  const [present, setPresent] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!assignmentId || !date) { setState({ idle: true }); return; }
    setState({ loading: true });
    const k = key(assignmentId, date);
    try {
      const data = await apiGet(`/attendance/api/roster?assignment_id=${assignmentId}&date=${encodeURIComponent(date)}`);
      await cachePut(k, data);
      setState({ data, source: 'network' });
    } catch (e) {
      const cached = await cacheGet(k);
      if (cached) setState({ data: cached, source: 'cache' });
      else setState({ error: e });
    }
  }, [assignmentId, date]);

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
    // Marking the morning also seeds the afternoon (auto_copy); the afternoon
    // session updates the afternoon only.
    const autoCopy = session === 'morning';
    const payload = { assignment_id: Number(assignmentId), date, session_type: session, present: presentIds, auto_copy: autoCopy };
    // optimistic cache so reopening (even offline) reflects it
    const updated = { ...d, students: d.students.map((s) => {
      const val = !!present[s.enrollment_id];
      if (session === 'afternoon') return { ...s, afternoon_present: val };
      return { ...s, morning_present: val, afternoon_present: val };  // morning seeds afternoon
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
            <span style={{ marginLeft: 'auto', fontSize: 13 }}>Present: <b>{presentCount}</b>/{d.students.length}</span>
          </div>

          {!d.week_id && <Banner tone="warn">This date isn’t in a school week — you can review, but saving is disabled.</Banner>}

          {d.students.length === 0 ? (
            <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
          ) : (
            <ul className="att-list" aria-label={'Register for ' + d.class_name}>
              {d.students.map((s) => (
                <li key={s.enrollment_id} className={present[s.enrollment_id] ? 'is-present' : 'is-absent'}>
                  <label>
                    <input type="checkbox" checked={!!present[s.enrollment_id]} onChange={() => toggle(s.enrollment_id)} />
                    <span className="att-name">{s.name}</span>
                    <span className="att-flag">{present[s.enrollment_id] ? 'Present' : 'Absent'}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}

          <div className="att-actions">
            <Button variant="secondary" size="sm" onClick={() => setAll(true)} disabled={!d.students.length}>Mark all present</Button>
            <Button variant="light" size="sm" onClick={() => setAll(false)} disabled={!d.students.length}>Mark all absent</Button>
            <Button onClick={save} disabled={!d.week_id || !d.students.length || busy}>Save register</Button>
            <Button variant="light" size="sm" onClick={copyPrevious}
                    disabled={!online || !d.week_id || busy}
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
