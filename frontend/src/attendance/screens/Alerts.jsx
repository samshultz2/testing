import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, OfflineRequired } from '../../components/ui';
import { Tiles, Card, Person, pctColor, pctTone } from '../kit';

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

  const critical = d ? d.alerts.filter((x) => x.status === 'critical').length : 0;
  const byClass = {};
  (d ? d.alerts : []).forEach((x) => { (byClass[x.class_name] = byClass[x.class_name] || []).push(x); });

  return (
    <div className="md">
      <section className="md-pick">
        <div className="md-pick-row"><span className="md-pick-l">Flag students below</span></div>
        <div className="ak-thr">
          {[50, 60, 75, 90].map((t) => (
            <button key={t} type="button" className={threshold === t ? 'on' : ''} aria-pressed={threshold === t} onClick={() => setThreshold(t)}>{t}%</button>))}
          <label className="ak-thr-custom">Custom
            <input type="number" min="0" max="100" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} aria-label="Custom threshold (%)" />%</label>
        </div>
      </section>

      {!online ? <div className="md-card"><OfflineRequired what="Attendance alerts" /></div>
        : syncing ? <div className="md-card"><Spinner label={`Syncing your saved marks… (${pending} left) — alerts will update once they reach the server.`} /></div>
        : state.loading ? <div className="md-card"><Spinner label="Loading alerts…" /></div>
        : state.error ? <div className="md-card"><ErrorState detail={state.error.message} /></div>
        : d && (
          <>
            <Tiles items={[
              { label: 'Flagged', value: d.alerts.length, sub: `below ${d.threshold}% · ${d.term.name}`, tone: d.alerts.length ? 'warn' : 'good' },
              { label: 'Critical', value: critical, sub: 'need urgent follow-up', tone: critical ? 'bad' : '' },
              { label: 'Warning', value: d.alerts.length - critical, sub: 'keep an eye on', tone: (d.alerts.length - critical) ? 'warn' : '' },
              { label: 'Classes affected', value: Object.keys(byClass).length },
            ]} />

            {d.alerts.length === 0 ? (
              <div className="md-card"><EmptyState icon="fa-circle-check" title="No students flagged"
                hint={`Every student you can view is at or above ${d.threshold}% attendance for this term.`} /></div>
            ) : (
              <Card icon="fa-bell" title={`${d.alerts.length} student${d.alerts.length === 1 ? '' : 's'} below ${d.threshold}%`} sub="Tap a student for their full attendance profile" flush
                    action={term && <a className="ak-btn" href={`/attendance/alerts/export?term_id=${term.id}&threshold=${threshold}`}><i className="fas fa-download" aria-hidden="true" /><span> Export</span></a>}>
                <ul className="ak-people">
                  {Object.entries(byClass).map(([cls, list]) => (
                    <React.Fragment key={cls}>
                      <li className="md-ghead">{cls}<span>{list.length}</span></li>
                      {list.map((a) => (
                        <Person key={a.student_id + '|' + a.class_name} name={a.student_name}
                                sub={`${a.present} of ${a.total} sessions · ${a.status}`}
                                tone={a.status === 'critical' ? 'out' : 'half'}
                                href={a.id ? `/attendance/app?student_id=${a.id}#/student` : undefined}
                                right={<><span className="tr-bar"><i style={{ width: a.percentage + '%', background: pctColor(a.percentage) }} /></span>
                                  <span className={'ak-pct ' + pctTone(a.percentage)}>{a.percentage}%</span></>} />))}
                    </React.Fragment>
                  ))}
                </ul>
              </Card>
            )}
          </>
        )}
    </div>
  );
}
