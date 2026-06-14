import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Spinner, EmptyState, ErrorState, OfflineRequired, Pill } from '../../components/ui';

// Read-only weekly attendance report (students × school-days + class totals).
export default function WeeklyReport() {
  const { classes = [], weeks = [], online } = useCtx();
  const [assignmentId, setAssignmentId] = useState('');
  const [weekId, setWeekId] = useState(weeks.length ? String(weeks[0].id) : '');

  const ready = online && assignmentId && weekId;
  const [state] = useAsync(
    () => (ready
      ? apiGet(`/attendance/api/report/weekly?assignment_id=${assignmentId}&week_id=${weekId}`)
      : Promise.resolve(null)),
    [assignmentId, weekId, online]
  );

  const d = state.data;
  const cell = (v) => v ? '✓' : '·';

  return (
    <div>
      <Toolbar>
        <Field label="Class" htmlFor="wr-class" grow>
          <Select id="wr-class" value={assignmentId} onChange={setAssignmentId}
                  placeholder={classes.length ? '— Select class —' : 'No classes available'}
                  options={classes.map((c) => ({ value: String(c.id), label: c.name }))} />
        </Field>
        <Field label="Week" htmlFor="wr-week">
          <Select id="wr-week" value={weekId} onChange={setWeekId}
                  placeholder={weeks.length ? '— Select week —' : 'No weeks'}
                  options={weeks.map((w) => ({ value: String(w.id), label: `Week ${w.number}` }))} />
        </Field>
      </Toolbar>

      {!online ? <OfflineRequired what="The weekly report" />
        : !assignmentId ? <EmptyState icon="fa-hand-pointer" title="Pick a class" hint="Choose a class and week to see the attendance breakdown." />
        : !weekId ? <EmptyState icon="fa-calendar-week" title="No weeks defined" hint="This term has no weeks set up yet." />
        : state.loading ? <Spinner label="Loading weekly report…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : d && (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
              <strong>{d.class_name}</strong>
              <span style={{ color: '#6b7280' }}>Week {d.week_info.week_number} · {d.week_info.start_date} → {d.week_info.end_date}</span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Pill tone="gray">{d.school_days_count} school day(s)</Pill>
                <Pill tone="green">{d.class_totals.weekly_percentage}% attendance</Pill>
              </span>
            </div>

            {d.students.length === 0 ? (
              <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
            ) : (
              <div className="att-grid-wrap">
                <table className="att-grid" aria-label={'Weekly report for ' + d.class_name}>
                  <thead>
                    <tr>
                      <th scope="col" className="att-grid-name">Student</th>
                      {d.school_days.map((day) => (
                        <th scope="col" key={day}>{new Date(day).toLocaleDateString(undefined, { weekday: 'short' })}</th>
                      ))}
                      <th scope="col">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.students.map((s) => (
                      <tr key={s.student_id}>
                        <td className="att-grid-name">{s.student_name}</td>
                        {s.daily.map((day) => (
                          <td key={day.date} title={`${day.day_name}: AM ${cell(day.morning)} / PM ${cell(day.afternoon)}`}>
                            {cell(day.morning)}{cell(day.afternoon)}
                          </td>
                        ))}
                        <td><b>{s.weekly_total}</b></td>
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
