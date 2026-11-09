import React, { useEffect, useState, useCallback } from 'react';
import { apiGet, apiPost, isPermanent } from '../../lib/api';
import { cachePut, cacheGet, enqueue } from '../../lib/offline';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, Banner, Pill, Toast } from '../../components/ui';
import { withGroups, genderLabel } from '../roster';
import { lastClass, rememberClass } from '../../lib/attprefs';
import { Picker, ClassChips, WeekStepper, Seg, ActionBar, MoreMenu, usePhone, initialsOf, pickInitialClass } from '../kit';

const key = (aid, wid) => `week|${aid}|${wid}`;

export default function WeekGrid() {
  const { classes = [], weeks = [], sync, initial, default_class, default_week } = useCtx();
  const [assignmentId, setAssignmentIdRaw] = useState(() => pickInitialClass(classes, default_class, initial, lastClass));
  const setAssignmentId = (id) => {
    setAssignmentIdRaw(id);
    const c = classes.find((x) => String(x.id) === String(id));
    if (c) rememberClass(id, c.name);
  };
  const phone = usePhone();
  const [weekId, setWeekId] = useState(
    default_week ? String(default_week) : (weeks[0] ? String(weeks[0].id) : ''));
  const [split, setSplit] = useState(false);
  const [state, setState] = useState({ idle: true });
  const [marks, setMarks] = useState({});           // {eid: {date: {am, pm}}}
  const [msg, setMsg] = useState(null);
  const [toast, setToast] = useState(null);   // floating save confirmation (no scroll)
  const [busy, setBusy] = useState(false);
  const [savedSig, setSavedSig] = useState(null);   // marks as last saved → "Saved ✓" until edited

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

  useEffect(() => { setMsg(null); setSavedSig(null); load(); }, [load]);

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
      await apiPost('/attendance/api/week/mark', payload);
      const w = weeks.find((x) => String(x.id) === String(weekId));
      const pct = totalMarks ? Math.round(presentMarks / totalMarks * 100) : 0;
      setSavedSig(JSON.stringify(marks));
      setToast({ tone: 'success', text: `Attendance saved — ${w ? 'Week ' + w.number : 'this week'}, ${d.days.length} day${d.days.length === 1 ? '' : 's'}, ${d.students.length} students (${pct}% present).` });
    } catch (e) {
      if (isPermanent(e)) setToast({ tone: 'error', text: `Couldn’t save: ${e.message}` });
      else { await enqueue('/attendance/api/week/mark', payload); await sync.refresh(); setToast({ tone: 'warn', text: 'Offline — the week is queued, will sync on reconnect.' }); }
    } finally { setBusy(false); }
  };

  const d = state.data;

  const nDays = d ? d.days.length : 0;
  const totalMarks = d ? d.students.length * nDays * 2 : 0;
  const presentMarks = d ? d.students.reduce((t, s) => t + d.days.reduce((u, day) => {
    const c = cell(s.enrollment_id, day.date); return u + (c.am ? 1 : 0) + (c.pm ? 1 : 0); }, 0), 0) : 0;
  const editable = d && d.students.length && nDays;
  const isSaved = !busy && savedSig !== null && savedSig === JSON.stringify(marks);
  const dayPresent = (date) => (d ? d.students.filter((s) => { const c = cell(s.enrollment_id, date); return c.am && c.pm; }).length : 0);
  const cols = { gridTemplateColumns: `minmax(0,1fr) repeat(${nDays}, ${phone ? 40 : 56}px)` };

  return (
    <div className={'md' + (phone && editable ? ' has-bar' : '')}>
      <Picker>
        <ClassChips classes={classes} value={assignmentId} onChange={setAssignmentId} />
        <div className="ak-pick-row2">
          <WeekStepper weeks={weeks} value={weekId} onChange={setWeekId} current={default_week} />
          <Seg label="Sessions" value={split ? 'split' : 'whole'} onChange={(v) => setSplit(v === 'split')}
               options={[{ value: 'whole', label: 'Whole day' }, { value: 'split', label: 'AM / PM' }]} />
        </div>
      </Picker>

      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      {toast && <Toast tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}

      {state.idle && <div className="md-card"><EmptyState icon="fa-table-cells-large" title="Pick a class and week" hint="Mark a whole week at once — handy for catching up a backlog. Loaded weeks are cached for offline use." /></div>}
      {state.loading && <div className="md-card"><Spinner label="Loading week…" /></div>}
      {state.error && <div className="md-card"><ErrorState title="Couldn’t load this week" detail={state.error.message} onRetry={load} /></div>}

      {d && (
        <div className="md-card">
          <div className="md-sum">
            <div className="md-sum-t">
              <strong>{d.class_name}</strong>
              <span>Week {d.week_number} · {d.students.length} students · {nDays} school day{nDays === 1 ? '' : 's'}</span>
              {state.source === 'cache' && <span className="md-pills"><Pill tone="amber">cached</Pill></span>}
            </div>
            {editable ? (
              <div className="md-meters">
                <div className="md-meter"><span>Present</span><div className="md-track"><i style={{ width: (totalMarks ? presentMarks / totalMarks * 100 : 0) + '%' }} /></div><b>{totalMarks ? Math.round(presentMarks / totalMarks * 100) : 0}%</b></div>
              </div>
            ) : null}
          </div>

          {!nDays ? (
            <EmptyState icon="fa-calendar-xmark" title="No school days" hint="This week has no school days (weekend/holidays only)." />
          ) : d.students.length === 0 ? (
            <EmptyState icon="fa-users-slash" title="No students enrolled" />
          ) : (
            <>
              <p className="md-note"><i className="fas fa-hand-pointer" aria-hidden="true" /> Tap a box to switch present/absent. Tap a <b>day</b> to flip the whole class that day, or a <b>name</b> for that student’s whole week.{split ? ' Top half is morning, bottom half afternoon.' : ''}</p>
              <div className="wg" role="grid" aria-label="Weekly attendance grid">
                <div className="wg-row wg-headrow" style={cols} role="row">
                  <span className="wg-corner" role="columnheader">Student</span>
                  {d.days.map((day) => (
                    <button key={day.date} type="button" className="wg-day" role="columnheader" onClick={() => toggleColumn(day.date)}
                            title={`Toggle everyone on ${day.label}`}>
                      <b>{String(day.label).split(' ')[0]} {parseInt(String(day.label).split(' ')[1] || '', 10) || ''}</b>
                      <small>{dayPresent(day.date)}/{d.students.length}</small>
                    </button>
                  ))}
                </div>
                {withGroups(d.students,
                  (gender, first, gkey) => <div key={gkey} className="wg-ghead">{genderLabel(gender)}</div>,
                  (s) => {
                    const wk = d.days.filter((day) => { const c = cell(s.enrollment_id, day.date); return c.am && c.pm; }).length;
                    return (
                      <div key={s.enrollment_id} className="wg-row" style={cols} role="row">
                        <button type="button" className="wg-who" onClick={() => toggleRow(s.enrollment_id)} title="Toggle this student’s whole week">
                          <span className="att-av" data-g={s.gender || ''} aria-hidden="true">{initialsOf(s.name)}</span>
                          <span className="wg-name">{s.name}<small>{wk}/{nDays} full days</small></span>
                        </button>
                        {d.days.map((day) => {
                          const c = cell(s.enrollment_id, day.date);
                          return split ? (
                            <span key={day.date} className="wg-split" role="gridcell">
                              <button type="button" className={'wg-half' + (c.am ? ' on' : '')} aria-pressed={!!c.am}
                                      onClick={() => setCell(s.enrollment_id, day.date, { am: !c.am })} aria-label={`${s.name} ${day.label} morning`}>AM</button>
                              <button type="button" className={'wg-half' + (c.pm ? ' on' : '')} aria-pressed={!!c.pm}
                                      onClick={() => setCell(s.enrollment_id, day.date, { pm: !c.pm })} aria-label={`${s.name} ${day.label} afternoon`}>PM</button>
                            </span>
                          ) : (
                            <button key={day.date} type="button" role="gridcell"
                                    className={'wg-cell ' + (c.am && c.pm ? 'on' : (c.am || c.pm) ? 'half' : 'off')}
                                    aria-pressed={!!(c.am && c.pm)} onClick={() => toggleWhole(s.enrollment_id, day.date)}
                                    aria-label={`${s.name} ${day.label} present`}>
                              <i className={'fas ' + (c.am && c.pm ? 'fa-check' : (c.am || c.pm) ? 'fa-circle-half-stroke' : 'fa-xmark')} aria-hidden="true" />
                            </button>
                          );
                        })}
                      </div>
                    );
                  })}
              </div>
            </>
          )}
          {editable && (
            <ActionBar phone={phone}>
              <div className="md-bar-count"><b>{totalMarks ? Math.round(presentMarks / totalMarks * 100) : 0}%</b> present this week</div>
              <button type="button" className="md-btn ghost" onClick={() => setAll(true)} title="Everyone present all week">
                <i className="fas fa-check-double" aria-hidden="true" /><span> All present</span></button>
              <MoreMenu items={[{ icon: 'fa-user-xmark', label: 'Everyone absent all week', onClick: () => setAll(false) }]} />
              <button type="button" className={'md-btn save' + (isSaved ? ' is-saved' : '')} onClick={save} disabled={busy}>
                <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : (isSaved ? 'fa-circle-check' : 'fa-check'))} aria-hidden="true" /> {isSaved ? 'Saved' : 'Save week'}</button>
            </ActionBar>
          )}
        </div>
      )}
    </div>
  );
}
