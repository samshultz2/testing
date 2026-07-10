import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Field, Spinner, EmptyState, ErrorState, OfflineRequired, Pill } from '../../components/ui';

// Read-only attendance alerts: students below a threshold, scoped to the
// classes this user may access. Server-computed → needs the network.
export default function Alerts() {
  const { term, online, sync = {} } = useCtx();
  const [threshold, setThreshold] = useState(75);

  // Wait for queued offline marks to flush so alerts reflect the latest marks.
  const pending = sync.pending || 0;
  const syncing = online && pending > 0;
  const termParam = term ? `&term_id=${term.id}` : '';
  const [state] = useAsync(
    () => (online && !syncing
      ? apiGet(`/attendance/api/report/alerts?threshold=${threshold}${termParam}`)
      : Promise.resolve(null)),
    [threshold, term && term.id, online, syncing]
  );

  const d = state.data;

  return (
    <div>
      <Toolbar>
        <Field label="Below threshold (%)" htmlFor="al-threshold">
          <input id="al-threshold" type="number" min="0" max="100" className="form-control"
                 style={{ maxWidth: 120 }} value={threshold}
                 onChange={(e) => setThreshold(Number(e.target.value))} />
        </Field>
      </Toolbar>

      {!online ? <OfflineRequired what="Attendance alerts" />
        : syncing ? <Spinner label={`Syncing your saved marks… (${pending} left) — alerts will update once they reach the server.`} />
        : state.loading ? <Spinner label="Loading alerts…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : d && (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
              <strong>{d.term.name}</strong>
              <span style={{ color: 'var(--text-muted)' }}>Students below {d.threshold}% attendance</span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                <Pill tone={d.alerts.length ? 'amber' : 'green'}>{d.alerts.length} flagged</Pill>
                {term && d.alerts.length > 0 && (
                  <a className="btn btn-success btn-sm"
                     href={`/attendance/alerts/export?term_id=${term.id}&threshold=${threshold}`}>
                    <i className="fas fa-download" aria-hidden="true" /> Export
                  </a>
                )}
              </span>
            </div>

            {d.alerts.length === 0 ? (
              <EmptyState icon="fa-circle-check" title="No students flagged"
                          hint={`Every student you can view is at or above ${d.threshold}% attendance for this term.`} />
            ) : (
              <div className="att-grid-wrap">
                <table className="att-grid" aria-label="Attendance alerts">
                  <thead>
                    <tr>
                      <th scope="col" className="att-grid-name">Student</th>
                      <th scope="col">Class</th>
                      <th scope="col">Present</th>
                      <th scope="col">%</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.alerts.map((a) => (
                      <tr key={a.student_id + '|' + a.class_name}>
                        <td className="att-grid-name">{a.id
                          ? <a href={`/attendance/app?student_id=${a.id}#/student`}>{a.student_name}</a>
                          : a.student_name}</td>
                        <td>{a.class_name}</td>
                        <td>{a.present}/{a.total}</td>
                        <td>{a.percentage}%</td>
                        <td><Pill tone={a.status === 'critical' ? 'red' : 'amber'}>{a.status}</Pill></td>
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
