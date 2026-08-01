import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Spinner, EmptyState, ErrorState, OfflineRequired,
         StatCards, SectionTitle, PerfBands } from '../../components/ui';
import { withGroups, GroupHeadRow } from '../roster';

const round1 = (n) => Math.round(n * 10) / 10;

// Read-only termly attendance report — full parity with the Jinja termly page:
// attendance rate, counts, gender table, session (AM/PM) table, term info,
// performance bands and the per-student weekly breakdown with totals.
export default function TermlyReport() {
  const { classes = [], term, online, sync = {}, default_class } = useCtx();
  const [assignmentId, setAssignmentId] = useState(default_class ? String(default_class) : '');

  // Wait for queued offline marks to flush before computing the report.
  const pending = sync.pending || 0;
  const syncing = online && pending > 0;
  const ready = online && !syncing && assignmentId;
  const [state] = useAsync(
    () => (ready
      ? apiGet(`/attendance/api/report/termly?assignment_id=${assignmentId}`)
      : Promise.resolve(null)),
    [assignmentId, online, syncing]
  );

  const d = state.data;
  const ct = d && d.class_totals;
  const ti = d && d.term_info;
  const maxSess = d ? ti.total_school_days * d.total_students : 0;

  // Performance bands, mirroring the Jinja thresholds (share of roll calls).
  let perf = null;
  if (d) {
    const times = ti.total_times_opened;
    const excT = Math.floor(times * 0.9), goodT = Math.floor(times * 0.75), fairT = Math.floor(times * 0.5);
    let exc = 0, gd = 0, fr = 0, pr = 0;
    d.students.forEach((s) => {
      if (s.termly_total >= excT) exc++;
      else if (s.termly_total >= goodT) gd++;
      else if (s.termly_total >= fairT) fr++;
      else pr++;
    });
    perf = [
      { tone: 'excellent', title: 'Excellent', count: exc, range: `≥90% (${excT}+)` },
      { tone: 'good', title: 'Good', count: gd, range: '75–89%' },
      { tone: 'fair', title: 'Fair', count: fr, range: '50–74%' },
      { tone: 'poor', title: 'Poor', count: pr, range: '<50%' },
    ];
  }

  return (
    <div>
      <Toolbar>
        <Field label="Class" htmlFor="tr-class" grow>
          <Select id="tr-class" value={assignmentId} onChange={setAssignmentId}
                  placeholder={classes.length ? '— Select class —' : 'No classes available'}
                  options={classes.map((c) => ({ value: String(c.id), label: c.name }))} />
        </Field>
      </Toolbar>

      {!online ? <OfflineRequired what="The termly report" />
        : syncing ? <Spinner label={`Syncing your saved marks… (${pending} left) — the report will update once they reach the server.`} />
        : !assignmentId ? <EmptyState icon="fa-hand-pointer" title="Pick a class" hint={`Choose a class to see its termly attendance${term ? ' for ' + term.name : ''}.`} />
        : state.loading ? <Spinner label="Loading termly report…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : d && (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 4 }}>
              <strong>{d.class_name}</strong>
              {term && (
                <a className="btn btn-success btn-sm" style={{ marginLeft: 'auto' }}
                   href={`/attendance/termly/export?assignment_id=${assignmentId}&term_id=${term.id}`}>
                  <i className="fas fa-download" aria-hidden="true" /> Export to Excel
                </a>
              )}
            </div>

            <StatCards items={[
              { value: ct.termly_percentage + '%', label: 'Attendance rate', primary: true },
              { value: d.total_students, label: 'Students' },
              { value: ti.total_times_opened, label: 'Times opened' },
              { value: ti.total_school_days, label: 'School days' },
            ]} />

            <SectionTitle icon="fa-venus-mars">Gender</SectionTitle>
            <div className="att-grid-wrap">
              <table className="att-grid" aria-label="Attendance by gender">
                <thead>
                  <tr><th scope="col" className="att-grid-name">Gender</th><th scope="col">Count</th><th scope="col">Attendance</th><th scope="col">Avg</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="att-grid-name">Male</td>
                    <td>{d.total_male_students}</td>
                    <td>{ct.male_attendance}</td>
                    <td>{d.total_male_students > 0 ? round1(ct.male_attendance / d.total_male_students) : 0}</td>
                  </tr>
                  <tr>
                    <td className="att-grid-name">Female</td>
                    <td>{d.total_female_students}</td>
                    <td>{ct.female_attendance}</td>
                    <td>{d.total_female_students > 0 ? round1(ct.female_attendance / d.total_female_students) : 0}</td>
                  </tr>
                </tbody>
                <tfoot>
                  {/* Avg total must match the per-row metric (attendance ÷ students),
                      not the term-wide daily average (ct.termly_average) which reads
                      as a nonsense "30.59" next to the 83/87 rows. */}
                  <tr><td className="att-grid-name">Total</td><td>{d.total_students}</td><td>{ct.total_attendance}</td><td>{d.total_students > 0 ? round1(ct.total_attendance / d.total_students) : 0}</td></tr>
                </tfoot>
              </table>
            </div>

            <SectionTitle icon="fa-clock">Session</SectionTitle>
            <div className="att-grid-wrap">
              <table className="att-grid" aria-label="Attendance by session">
                <thead>
                  <tr><th scope="col" className="att-grid-name">Session</th><th scope="col">Total</th><th scope="col">Max</th><th scope="col">%</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="att-grid-name">AM (morning)</td>
                    <td>{ct.total_morning}</td><td>{maxSess}</td>
                    <td>{maxSess > 0 ? round1((ct.total_morning / maxSess) * 100) : 0}%</td>
                  </tr>
                  <tr>
                    <td className="att-grid-name">PM (afternoon)</td>
                    <td>{ct.total_afternoon}</td><td>{maxSess}</td>
                    <td>{maxSess > 0 ? round1((ct.total_afternoon / maxSess) * 100) : 0}%</td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr><td className="att-grid-name">Both</td><td>{ct.total_attendance}</td><td>{maxSess * 2}</td><td>{ct.termly_percentage}%</td></tr>
                </tfoot>
              </table>
            </div>

            <SectionTitle icon="fa-info-circle">Term info</SectionTitle>
            <StatCards items={[
              { value: ti.total_weeks, label: 'Weeks' },
              { value: ti.total_school_days, label: 'Days' },
              { value: ti.total_times_opened, label: 'Roll calls' },
              { value: ct.termly_average, label: 'Daily average' },
            ]} />

            <SectionTitle icon="fa-medal">Performance</SectionTitle>
            <PerfBands bands={perf} />

            <SectionTitle icon="fa-users">Students</SectionTitle>
            {d.students.length === 0 ? (
              <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
            ) : (
              <div className="att-grid-wrap">
                <table className="att-grid" aria-label={'Termly report for ' + d.class_name}>
                  <thead>
                    <tr>
                      <th scope="col" className="att-grid-name">Student</th>
                      {d.weeks.map((w) => <th scope="col" key={w.id}>W{w.number}</th>)}
                      <th scope="col">AM</th>
                      <th scope="col">PM</th>
                      <th scope="col">Total</th>
                      <th scope="col">%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {withGroups(d.students,
                      (gender, first, key) => <GroupHeadRow key={key} gender={gender} first={first} colSpan={d.weeks.length + 5} />,
                      (s) => (
                      <tr key={s.student_id}>
                        <td className="att-grid-name">{s.student_name}<div className="att-sub">{s.gender}</div></td>
                        {s.weekly.map((w) => <td key={w.week_id}>{w.total}</td>)}
                        <td>{s.termly_morning}</td>
                        <td>{s.termly_afternoon}</td>
                        <td><b>{s.termly_total}</b></td>
                        <td>{s.termly_percentage}%</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td className="att-grid-name">Total</td>
                      {d.weekly_totals.map((t, i) => <td key={i}>{t}</td>)}
                      <td>{ct.total_morning}</td>
                      <td>{ct.total_afternoon}</td>
                      <td>{ct.total_attendance}</td>
                      <td>{ct.termly_percentage}%</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </>
        )}
    </div>
  );
}
