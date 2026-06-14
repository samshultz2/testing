import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Field, Select, Spinner, EmptyState, ErrorState, OfflineRequired, Pill } from '../../components/ui';

// Read-only termly attendance report (per-student weekly totals + percentage).
export default function TermlyReport() {
  const { classes = [], term, online } = useCtx();
  const [assignmentId, setAssignmentId] = useState('');

  const ready = online && assignmentId;
  const [state] = useAsync(
    () => (ready
      ? apiGet(`/attendance/api/report/termly?assignment_id=${assignmentId}`)
      : Promise.resolve(null)),
    [assignmentId, online]
  );

  const d = state.data;

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
        : !assignmentId ? <EmptyState icon="fa-hand-pointer" title="Pick a class" hint={`Choose a class to see its termly attendance${term ? ' for ' + term.name : ''}.`} />
        : state.loading ? <Spinner label="Loading termly report…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : d && (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
              <strong>{d.class_name}</strong>
              <span style={{ color: '#6b7280' }}>{d.term_info.total_weeks} week(s) · {d.term_info.total_school_days} school day(s)</span>
              <span style={{ marginLeft: 'auto' }}>
                <Pill tone="green">{d.class_totals.termly_percentage}% attendance</Pill>
              </span>
            </div>

            {d.students.length === 0 ? (
              <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
            ) : (
              <div className="att-grid-wrap">
                <table className="att-grid" aria-label={'Termly report for ' + d.class_name}>
                  <thead>
                    <tr>
                      <th scope="col" className="att-grid-name">Student</th>
                      {d.weeks.map((w) => <th scope="col" key={w.id}>W{w.number}</th>)}
                      <th scope="col">Total</th>
                      <th scope="col">%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.students.map((s) => (
                      <tr key={s.student_id}>
                        <td className="att-grid-name">{s.student_name}</td>
                        {s.weekly.map((w) => <td key={w.week_id}>{w.total}</td>)}
                        <td><b>{s.termly_total}</b></td>
                        <td>{s.percentage}%</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td className="att-grid-name"><b>Class total</b></td>
                      {d.weekly_totals.map((t, i) => <td key={i}><b>{t}</b></td>)}
                      <td><b>{d.class_totals.total_attendance}</b></td>
                      <td><b>{d.class_totals.termly_percentage}%</b></td>
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
