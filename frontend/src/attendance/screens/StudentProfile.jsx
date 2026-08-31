import React, { useState } from 'react';
import { apiGet, apiPost } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Autocomplete, Spinner, EmptyState, ErrorState,
         StatCards, SectionTitle, Pill } from '../../components/ui';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const STATUS_TONE = { present: '#16a34a', late: '#d97706', absent: '#dc2626', unmarked: 'var(--border-color)' };
const STATUS_LABEL = { present: 'Present', late: 'Late / partial', absent: 'Absent', unmarked: 'Not marked' };

// A compact month-grouped calendar of a term's school days, colour-coded.
function TermCalendar({ calendar }) {
  const byMonth = {};
  (calendar || []).forEach((c) => {
    const dt = new Date(c.date);
    const key = dt.getFullYear() + '-' + dt.getMonth();
    (byMonth[key] = byMonth[key] || { y: dt.getFullYear(), m: dt.getMonth(), days: {} }).days[dt.getDate()] = c;
  });
  const months = Object.values(byMonth).sort((a, b) => (a.y - b.y) || (a.m - b.m));
  return (
    <div className="att-cal-months">
      {months.map((mo) => {
        const first = new Date(mo.y, mo.m, 1).getDay();
        const dim = new Date(mo.y, mo.m + 1, 0).getDate();
        const cells = [];
        for (let i = 0; i < first; i++) cells.push(null);
        for (let dd = 1; dd <= dim; dd++) cells.push(dd);
        return (
          <div className="att-cal" key={mo.y + '-' + mo.m}>
            <div className="att-cal-title">{MONTHS[mo.m]} {mo.y}</div>
            <div className="att-cal-grid">
              {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((w, i) => <div key={'h' + i} className="att-cal-h">{w}</div>)}
              {cells.map((dd, i) => {
                if (!dd) return <div key={i} className="att-cal-c att-cal-empty" />;
                const c = mo.days[dd];
                if (!c) return <div key={i} className="att-cal-c att-cal-off">{dd}</div>;
                return <div key={i} className="att-cal-c" title={`${c.date} · ${STATUS_LABEL[c.status]}`}
                            style={{ background: STATUS_TONE[c.status], color: c.status === 'unmarked' ? 'inherit' : '#fff' }}>{dd}</div>;
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TrendBars({ trend }) {
  if (!trend || trend.length === 0) return null;
  return (
    <div className="att-trend" aria-label="Attendance percentage by term">
      {trend.map((t, i) => (
        <div key={i} className="att-trend-col" title={`${t.label}: ${t.percentage}%`}>
          <div className="att-trend-bar" style={{ height: Math.max(4, t.percentage) + '%',
            background: t.percentage >= 75 ? '#16a34a' : t.percentage >= 50 ? '#d97706' : '#dc2626' }} />
          <div className="att-trend-lbl">{t.label}</div>
        </div>))}
    </div>
  );
}

export default function StudentProfile() {
  const { initial = {} } = useCtx();
  const [studentId, setStudentId] = useState(initial.studentId || '');
  const [tick, setTick] = useState(0);
  const [state] = useAsync(
    () => (studentId ? apiGet(`/attendance/api/student/${studentId}`) : Promise.resolve(null)),
    [studentId, tick]);

  const d = state.data;
  const openIntervention = async () => {
    const r = await apiPost('/attendance/api/interventions/open',
      { student_id: studentId, term_id: d && d.active_term_id });
    if (r && r.ok) setTick((t) => t + 1); else alert((r && r.error) || 'Could not open intervention.');
  };
  const hasOpen = d && (d.interventions || []).some((i) => ['Open', 'In progress', 'Escalated'].includes(i.status));
  return (
    <div>
      <Toolbar>
        <div style={{ flex: 1, minWidth: 220 }}>
          <Autocomplete label="Find a student" url="/attendance/api/student-search"
                        placeholder="Search name or student ID…"
                        onPick={(id) => id && setStudentId(String(id))} />
        </div>
        {d && d.warning && !hasOpen && <button className="btn btn-primary btn-sm no-print" onClick={openIntervention}>
          <i className="fas fa-hand-holding-heart" aria-hidden="true" /> Open intervention</button>}
        {d && <button className="btn btn-secondary btn-sm no-print" onClick={() => window.print()}>
          <i className="fas fa-print" aria-hidden="true" /> Print</button>}
      </Toolbar>

      {!studentId ? <EmptyState icon="fa-user-magnifying-glass" title="Search for a student"
                                hint="Find any student to see their complete attendance profile across every term." />
        : state.loading ? <Spinner label="Loading profile…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : d && (
          <div className="att-profile">
            <div className="att-profile-head">
              {d.student.photo_url ? <img className="att-avatar" src={d.student.photo_url} alt="" />
                : <div className="att-avatar">{(d.student.name || '').split(' ').map((x) => x[0]).slice(0, 2).join('').toUpperCase()}</div>}
              <div>
                <h2 style={{ margin: 0 }}>{d.student.name}</h2>
                <div className="att-sub">{d.student.student_id}{d.student.gender ? ' · ' + d.student.gender : ''}</div>
                <div style={{ marginTop: 6 }}>
                  <Pill tone={d.warning ? 'red' : 'green'}>{d.overall.percentage}% overall</Pill>{' '}
                  {d.warning && <Pill tone="amber">Below {d.threshold}% threshold</Pill>}
                </div>
              </div>
            </div>

            {d.warning && (
              <div className="att-warn" role="alert">
                <i className="fas fa-triangle-exclamation" aria-hidden="true" /> This student's overall attendance
                ({d.overall.percentage}%) is below the {d.threshold}% warning threshold and may need intervention.
              </div>)}

            <StatCards items={[
              { value: d.overall.percentage + '%', label: 'Overall rate', primary: true },
              { value: d.overall.full_days, label: 'Full-present days' },
              { value: d.overall.late_days, label: 'Late / partial' },
              { value: d.overall.absent_days, label: 'Absent days' },
              { value: d.overall.terms, label: 'Terms tracked' },
            ]} />

            {d.trend.length > 1 && (<><SectionTitle icon="fa-chart-line">Trend by term</SectionTitle><TrendBars trend={d.trend} /></>)}

            <SectionTitle icon="fa-calendar-days">Term-by-term</SectionTitle>
            <div className="att-grid-wrap">
              <table className="att-grid" aria-label="Attendance by term">
                <thead><tr><th className="att-grid-name" scope="col">Term</th><th scope="col">Class</th>
                  <th scope="col">Present</th><th scope="col">Late</th><th scope="col">Absent</th><th scope="col">%</th></tr></thead>
                <tbody>
                  {d.terms.map((t) => (
                    <tr key={t.enrollment_id}>
                      <td className="att-grid-name">{t.term}<div className="att-sub">{t.session}</div></td>
                      <td>{t.class}</td><td>{t.full_days}</td><td>{t.late_days}</td><td>{t.absent_days}</td>
                      <td><b style={{ color: t.percentage >= 75 ? '#16a34a' : t.percentage >= 50 ? '#d97706' : '#dc2626' }}>{t.percentage}%</b></td>
                    </tr>))}
                  {d.terms.length === 0 && <tr><td colSpan={6} className="att-sub">No attendance recorded yet.</td></tr>}
                </tbody>
              </table>
            </div>

            {d.focus && (
              <>
                <SectionTitle icon="fa-calendar-check">{d.focus.term} calendar · {d.focus.class}</SectionTitle>
                <div className="att-cal-legend">
                  {['present', 'late', 'absent', 'unmarked'].map((s) => (
                    <span key={s}><span className="att-cal-dot" style={{ background: STATUS_TONE[s] }} /> {STATUS_LABEL[s]}</span>))}
                </div>
                <TermCalendar calendar={d.focus.calendar} />
              </>)}

            {(d.interventions || []).length > 0 && (
              <>
                <SectionTitle icon="fa-hand-holding-heart">Interventions</SectionTitle>
                {d.interventions.map((iv) => (
                  <div key={iv.id} className="iv-case">
                    <div className="iv-case-head">
                      <div><strong>{iv.reason || 'Intervention'}</strong>
                        <span className="att-sub"> · opened {iv.opened}{iv.opened_by ? ' by ' + iv.opened_by : ''}</span></div>
                      <div className="iv-case-metrics">
                        {iv.baseline != null && <span className="att-sub">was {iv.baseline}%</span>}
                        {iv.current != null && <Pill tone={iv.direction === 'up' ? 'green' : iv.direction === 'down' ? 'red' : 'gray'}>{iv.current}%{iv.delta != null ? ` (${iv.delta > 0 ? '+' : ''}${iv.delta})` : ''}</Pill>}
                        <Pill tone={iv.status === 'Resolved' ? 'green' : iv.status === 'Escalated' ? 'red' : 'amber'}>{iv.status}</Pill>
                      </div>
                    </div>
                    {iv.outcome && <div className="att-sub">Outcome: {iv.outcome}</div>}
                    {iv.notes.length > 0 && (
                      <ul className="iv-notes">{iv.notes.map((n, i) => (
                        <li key={i}><b>{n.kind}</b> · {n.date}{n.body ? ` — ${n.body}` : ''}{n.next_action ? <span className="att-sub"> → {n.next_action}{n.next_date ? ` (${n.next_date})` : ''}</span> : null}</li>))}
                      </ul>)}
                  </div>))}
              </>)}

            {(d.notifications || []).length > 0 && (
              <>
                <SectionTitle icon="fa-comment-sms">Parent notifications</SectionTitle>
                <div className="att-grid-wrap">
                  <table className="att-grid" aria-label="Parent notification history">
                    <thead><tr><th className="att-grid-name" scope="col">Notice</th><th scope="col">Channel</th>
                      <th scope="col">Date</th><th scope="col">Status</th></tr></thead>
                    <tbody>{d.notifications.map((n, i) => (
                      <tr key={i}><td className="att-grid-name">{n.title.replace('Attendance: ', '')}</td>
                        <td>{n.channel}</td><td>{n.date}</td>
                        <td><Pill tone={n.status === 'Sent' ? 'green' : 'amber'}>{n.status}</Pill></td></tr>))}
                    </tbody>
                  </table>
                </div>
              </>)}
          </div>
        )}
    </div>
  );
}
