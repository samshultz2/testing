import React, { useEffect, useState, useCallback } from 'react';
import { apiGet, apiPost, isPermanent } from '../../lib/api';
import { cachePut, cacheGet, enqueue } from '../../lib/offline';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Button, Spinner, EmptyState, ErrorState, Banner, Pill, Toast } from '../../components/ui';

const key = (aid, wid) => `week|${aid}|${wid}`;

export default function WeekGrid() {
  const { classes = [], weeks = [], sync, initial, default_class, default_week } = useCtx();
  const seeded = initial && classes.some((c) => String(c.id) === String(initial.assignmentId));
  const [assignmentId, setAssignmentId] = useState(
    seeded ? String(initial.assignmentId) : (default_class ? String(default_class) : ''));
  const [weekId, setWeekId] = useState(
    default_week ? String(default_week) : (weeks[0] ? String(weeks[0].id) : ''));
  const [split, setSplit] = useState(false);
  const [state, setState] = useState({ idle: true });
  const [marks, setMarks] = useState({});           // {eid: {date: {am, pm}}}
  const [msg, setMsg] = useState(null);
  const [toast, setToast] = useState(null);   // floating save confirmation (no scroll)
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!assignmentId || !weekId) { setState({ idle: true }); return; }
    setState({ loading: true });
    const k = key(assignmentId, weekId);
    try {
      const data = await apiGet(`/attendance/api/week?assignment_id=${assignmentId}&week_id=${weekId}`);
      await cachePut(k, data);
      setState({ data, source: 'network' });
    } catch (e) {
      const cached = await cacheGet(k);
      if (cached) setState({ data: cached, source: 'cache' });
      else setState({ error: e });
    }
  }, [assignmentId, weekId]);

  useEffect(() => { setMsg(null); load(); }, [load]);

  useEffect(() => {
    const d = state.data;
    if (!d) return;
    const init = {};
    d.students.forEach((s) => { init[s.enrollment_id] = { ...s.days }; });
    setMarks(init);
  }, [state.data]);

  const cell = (eid, date) => (marks[eid] && marks[eid][date]) || { am: true, pm: true };
  const setCell = (eid, date, patch) =>
    setMarks((m) => ({ ...m, [eid]: { ...m[eid], [date]: { ...cell(eid, date), ...patch } } }));
  const toggleWhole = (eid, date) => { const c = cell(eid, date); const v = !(c.am && c.pm); setCell(eid, date, { am: v, pm: v }); };
  const setAll = (val) => {
    const d = state.data; const next = {};
    d.students.forEach((s) => { next[s.enrollment_id] = {}; d.days.forEach((day) => { next[s.enrollment_id][day.date] = { am: val, pm: val }; }); });
    setMarks(next);
  };
  // Tap a day heading to toggle that whole column; tap a name to toggle that
  // student's whole week (parity with the classic week grid).
  const toggleColumn = (date) => {
    const d = state.data;
    const anyOn = d.students.some((s) => { const c = cell(s.enrollment_id, date); return c.am || c.pm; });
    const v = !anyOn;
    setMarks((m) => {
      const next = { ...m };
      d.students.forEach((s) => { next[s.enrollment_id] = { ...next[s.enrollment_id], [date]: { am: v, pm: v } }; });
      return next;
    });
  };
  const toggleRow = (eid) => {
    const d = state.data;
    const anyOn = d.days.some((day) => { const c = cell(eid, day.date); return c.am || c.pm; });
    const v = !anyOn;
    setMarks((m) => ({ ...m, [eid]: Object.fromEntries(d.days.map((day) => [day.date, { am: v, pm: v }])) }));
  };

  const save = async () => {
    const d = state.data;
    const list = [];
    d.students.forEach((s) => d.days.forEach((day) => {
      const c = cell(s.enrollment_id, day.date);
      list.push({ enrollment_id: s.enrollment_id, date: day.date, am: !!c.am, pm: !!c.pm });
    }));
    const payload = { assignment_id: Number(assignmentId), week_id: Number(weekId), marks: list };
    // optimistic cache
    const updated = { ...d, students: d.students.map((s) => ({ ...s, days: { ...marks[s.enrollment_id] } })) };
    await cachePut(key(assignmentId, weekId), updated);
    setBusy(true);
    try {
      const r = await apiPost('/attendance/api/week/mark', payload);
      setToast({ tone: 'success', text: `Saved ${r.saved} entries for the week.` });
    } catch (e) {
      if (isPermanent(e)) setToast({ tone: 'error', text: `Couldn’t save: ${e.message}` });
      else { await enqueue('/attendance/api/week/mark', payload); await sync.refresh(); setToast({ tone: 'warn', text: 'Offline — the week is queued, will sync on reconnect.' }); }
    } finally { setBusy(false); }
  };

  const d = state.data;

  return (
    <div>
      <Toolbar>
        <Field label="Class" htmlFor="wg-class" grow>
          <Select id="wg-class" value={assignmentId} onChange={setAssignmentId}
                  placeholder={classes.length ? '— Select class —' : 'No classes available'}
                  options={classes.map((c) => ({ value: String(c.id), label: c.name }))} />
        </Field>
        <Field label="Week" htmlFor="wg-week">
          <Select id="wg-week" value={weekId} onChange={setWeekId}
                  placeholder={weeks.length ? '— Select week —' : 'No weeks'}
                  options={weeks.map((w) => ({ value: String(w.id), label: `Week ${w.number}` }))} />
        </Field>
        <Field label="Sessions" htmlFor="wg-split">
          <Select id="wg-split" value={split ? 'split' : 'whole'} onChange={(v) => setSplit(v === 'split')}
                  options={[{ value: 'whole', label: 'Whole day' }, { value: 'split', label: 'AM / PM' }]} />
        </Field>
      </Toolbar>

      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      {toast && <Toast tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}

      {state.idle && <EmptyState icon="fa-table-cells-large" title="Pick a class and week" hint="Load a whole week as a grid — handy for catching up a backlog. Loaded grids cache for offline use." />}
      {state.loading && <Spinner label="Loading week…" />}
      {state.error && <ErrorState title="Couldn’t load this week" detail={state.error.message} onRetry={load} />}

      {d && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
            <strong>{d.class_name}</strong>
            <span style={{ color: 'var(--text-muted)' }}>Week {d.week_number}</span>
            {state.source === 'cache' && <Pill tone="amber">cached</Pill>}
          </div>

          {!d.days.length ? (
            <EmptyState icon="fa-calendar-xmark" title="No school days" hint="This week has no school days (weekend/holidays only)." />
          ) : d.students.length === 0 ? (
            <EmptyState icon="fa-users-slash" title="No students enrolled" />
          ) : (
            <div className="att-grid-wrap" tabIndex="0" aria-label="Weekly attendance grid">
              <table className="att-grid">
                <thead>
                  <tr>
                    <th scope="col" className="att-grid-name">Student</th>
                    {d.days.map((day) => (
                      <th key={day.date} scope="col">
                        <button type="button" className="att-linkbtn" onClick={() => toggleColumn(day.date)}
                                title="Toggle this whole day">{day.label}</button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.students.map((s) => (
                    <tr key={s.enrollment_id}>
                      <th scope="row" className="att-grid-name">
                        <button type="button" className="att-linkbtn" onClick={() => toggleRow(s.enrollment_id)}
                                title="Toggle this student's week">{s.name}</button>
                      </th>
                      {d.days.map((day) => {
                        const c = cell(s.enrollment_id, day.date);
                        return (
                          <td key={day.date}>
                            {split ? (
                              <span className="att-ampm">
                                <label title={`${s.name} ${day.label} AM`}>
                                  <input type="checkbox" checked={!!c.am} onChange={(e) => setCell(s.enrollment_id, day.date, { am: e.target.checked })} />
                                  <span aria-hidden="true">AM</span>
                                </label>
                                <label title={`${s.name} ${day.label} PM`}>
                                  <input type="checkbox" checked={!!c.pm} onChange={(e) => setCell(s.enrollment_id, day.date, { pm: e.target.checked })} />
                                  <span aria-hidden="true">PM</span>
                                </label>
                              </span>
                            ) : (
                              <input type="checkbox" aria-label={`${s.name} ${day.label} present`}
                                     checked={!!(c.am && c.pm)} onChange={() => toggleWhole(s.enrollment_id, day.date)} />
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="att-actions">
            <Button variant="secondary" size="sm" onClick={() => setAll(true)} disabled={!d.students.length}>Mark all present</Button>
            <Button variant="light" size="sm" onClick={() => setAll(false)} disabled={!d.students.length}>Mark all absent</Button>
            <Button onClick={save} disabled={!d.students.length || !d.days.length || busy}>Save week</Button>
          </div>
          {!!d.days.length && d.students.length > 0 && (
            <p className="att-legend">Tip: tap a day heading to toggle that whole day, or a name to toggle that student’s week.</p>
          )}
        </>
      )}
    </div>
  );
}
