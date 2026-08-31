import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Spinner, EmptyState, ErrorState, OfflineRequired, Pill,
         StatCards, InfoGrid, SectionTitle, AmPm } from '../../components/ui';
import { withGroups, GroupHeadRow } from '../roster';

// Read-only weekly attendance report — full parity with the Jinja weekly page:
// attendance rate, student/school-day/roll-call counts, week totals (AM/PM/
// combined, male/female, max possible) and a per-student daily breakdown.
export default function WeeklyReport() {
  const { classes = [], weeks = [], online, sync = {}, default_class, default_week } = useCtx();
  const [assignmentId, setAssignmentId] = useState(default_class ? String(default_class) : '');
  const [weekId, setWeekId] = useState(
    default_week ? String(default_week) : (weeks.length ? String(weeks[0].id) : ''));

  // Don't compute the report until any marks queued offline have been flushed,
  // otherwise a reconnect could show server stats that omit this week's marks.
  const pending = sync.pending || 0;
  const syncing = online && pending > 0;
  const ready = online && !syncing && assignmentId && weekId;
  const [state] = useAsync(
    () => (ready
      ? apiGet(`/attendance/api/report/weekly?assignment_id=${assignmentId}&week_id=${weekId}`)
      : Promise.resolve(null)),
    [assignmentId, weekId, online, syncing]
  );

  const d = state.data;
  const ct = d && d.class_totals;
  const maxPossible = d ? d.total_students * d.times_opened : 0;

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
        : syncing ? <Spinner label={`Syncing your saved marks… (${pending} left) — the report will update once they reach the server.`} />
        : !assignmentId ? <EmptyState icon="fa-hand-pointer" title="Pick a class" hint="Choose a class and week to see the attendance breakdown." />
        : !weekId ? <EmptyState icon="fa-calendar-week" title="No weeks defined" hint="This term has no weeks set up yet." />
        : state.loading ? <Spinner label="Loading weekly report…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : d && (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 4 }}>
              <strong>{d.class_name}</strong>
              <span style={{ color: 'var(--text-muted)' }}>Week {d.week_info.week_number} · {d.week_info.start_date} → {d.week_info.end_date}</span>
              <a className="btn btn-success btn-sm" style={{ marginLeft: 'auto' }}
                 href={`/attendance/weekly/export?assignment_id=${assignmentId}&week_id=${weekId}`}>
                <i className="fas fa-download" aria-hidden="true" /> Export to Excel
              </a>
            </div>

            <StatCards items={[
              { value: ct.weekly_percentage + '%', label: 'Attendance rate', primary: true },
              { value: d.total_students, label: 'Students' },
              { value: d.school_days_count, label: 'School days' },
              { value: d.times_opened, label: 'Roll calls' },
            ]} />

            <SectionTitle icon="fa-calculator">Week {d.week_info.week_number} totals</SectionTitle>
            <InfoGrid items={[
              { label: 'Morning', value: ct.total_morning },
              { label: 'Afternoon', value: ct.total_afternoon },
              { label: 'Combined', value: ct.total_attendance, tone: 'primary' },
              { label: 'Male', value: ct.male_attendance },
              { label: 'Female', value: ct.female_attendance },
              { label: 'Max possible', value: maxPossible },
            ]} />

            <SectionTitle icon="fa-list">Student breakdown</SectionTitle>
            {d.students.length === 0 ? (
              <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
            ) : (
              <>
                <div className="att-grid-wrap">
                  <table className="att-grid" aria-label={'Weekly report for ' + d.class_name}>
                    <thead>
                      <tr>
                        <th scope="col" className="att-grid-name">Student</th>
                        {d.school_days.map((day) => (
                          <th scope="col" key={day}>
                            {new Date(day).toLocaleDateString(undefined, { weekday: 'short' })}
                            <div className="att-sub">{new Date(day).getDate()}</div>
                          </th>
                        ))}
                        <th scope="col">AM</th>
                        <th scope="col">PM</th>
                        <th scope="col">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {withGroups(d.students,
                        (gender, first, key) => <GroupHeadRow key={key} gender={gender} first={first} colSpan={d.school_days.length + 4} />,
                        (s) => (
                        <tr key={s.student_id}>
                          <td className="att-grid-name">{s.student_name}<div className="att-sub">{s.gender}</div></td>
                          {s.daily.map((day) => (
                            <td key={day.date} title={day.day_name}><AmPm am={day.morning} pm={day.afternoon} /></td>
                          ))}
                          <td>{s.weekly_morning}</td>
                          <td>{s.weekly_afternoon}</td>
                          <td><b>{s.weekly_total}</b></td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr>
                        <td className="att-grid-name">Class total</td>
                        {d.school_days.map((day) => <td key={day}>—</td>)}
                        <td>{ct.total_morning}</td>
                        <td>{ct.total_afternoon}</td>
                        <td>{ct.total_attendance}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
                <p className="att-legend">
                  <b>Legend:</b> <span style={{ color: 'var(--success)' }}>✓</span> present, <span style={{ color: 'var(--danger)' }}>✗</span> absent ·
                  {' '}each cell shows AM then PM · <b>AM</b> = morning, <b>PM</b> = afternoon.
                </p>
              </>
            )}
          </>
        )}
    </div>
  );
}
