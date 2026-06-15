import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Spinner, EmptyState, ErrorState, OfflineRequired, Pill, StatCards, Banner } from '../../components/ui';

// Read-only daily attendance summary (server-computed → needs the network).
export default function DailySummary() {
  const { classes = [], today, online, sync = {} } = useCtx();
  const [assignmentId, setAssignmentId] = useState('');
  const [date, setDate] = useState(today || '');

  // Wait for queued offline marks to flush before computing the summary.
  const pending = sync.pending || 0;
  const syncing = online && pending > 0;
  const ready = online && !syncing && assignmentId && date;
  const [state] = useAsync(
    () => (ready
      ? apiGet(`/attendance/api/daily-summary?assignment_id=${assignmentId}&date=${encodeURIComponent(date)}`)
      : Promise.resolve(null)),
    [assignmentId, date, online, syncing]
  );

  const d = state.data;
  const flag = (v) => v == null ? <Pill tone="gray">—</Pill>
    : v ? <Pill tone="green">Present</Pill> : <Pill tone="red">Absent</Pill>;

  return (
    <div>
      <Toolbar>
        <Field label="Class" htmlFor="ds-class" grow>
          <Select id="ds-class" value={assignmentId} onChange={setAssignmentId}
                  placeholder={classes.length ? '— Select class —' : 'No classes available'}
                  options={classes.map((c) => ({ value: String(c.id), label: c.name }))} />
        </Field>
        <Field label="Date" htmlFor="ds-date">
          <input id="ds-date" type="date" className="form-control" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
      </Toolbar>

      {!online ? <OfflineRequired what="The daily summary" />
        : syncing ? <Spinner label={`Syncing your saved marks… (${pending} left) — the summary will update once they reach the server.`} />
        : !assignmentId ? <EmptyState icon="fa-hand-pointer" title="Pick a class" hint="Choose a class and date to see who was present." />
        : state.loading ? <Spinner label="Loading summary…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : d && (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 4 }}>
              <strong>{d.class_name}</strong>
              <span style={{ color: '#6b7280' }}>{new Date(d.date).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</span>
            </div>

            {d.school_day === false && (
              <Banner tone="warn">
                {d.holiday ? `Holiday — ${d.holiday.reason}${d.holiday.type ? ' (' + d.holiday.type + ')' : ''}.`
                  : d.weekend ? 'This date is a weekend.' : 'This date is not a school day.'}
                {' '}Marks aren’t expected on this day.
              </Banner>
            )}

            <StatCards items={[
              { value: d.total_students, label: 'Total students' },
              { value: d.morning_present, label: 'AM present' },
              { value: d.morning_absent, label: 'AM absent' },
              { value: d.afternoon_present, label: 'PM present' },
              { value: d.afternoon_absent, label: 'PM absent' },
            ]} />

            {d.students.length === 0 ? (
              <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
            ) : (
              <div className="att-grid-wrap">
                <table className="att-grid" aria-label={'Daily summary for ' + d.class_name}>
                  <thead>
                    <tr>
                      <th scope="col" className="att-grid-name">Student</th>
                      <th scope="col">Gender</th>
                      <th scope="col">Morning</th>
                      <th scope="col">Afternoon</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.students.map((s) => (
                      <tr key={s.student_id}>
                        <td className="att-grid-name">{s.student_name}</td>
                        <td>{s.gender}</td>
                        <td>{flag(s.morning_present)}</td>
                        <td>{flag(s.afternoon_present)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
    </div>
  );
}
