import React, { useState } from 'react';
import { apiGet, apiPost } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Autocomplete, Spinner, EmptyState, ErrorState, Pill } from '../../components/ui';
import { Tiles, Card, Ring, initialsOf, pctTone, fmtPct } from '../kit';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const STATUS_TONE = { present: 'var(--success)', late: 'var(--warning)', absent: 'var(--danger)', unmarked: 'var(--gray-200)' };
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
        <div key={i} className="att-trend-col" title={`${t.label}: ${fmtPct(t.percentage)}`}>
          <span className="att-trend-v">{fmtPct(t.percentage)}</span><div className="att-trend-bar" style={{ height: Math.max(4, t.percentage) + '%',
            background: t.percentage >= 75 ? 'var(--success)' : t.percentage >= 50 ? 'var(--warning)' : 'var(--danger)' }} />
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
    <div className="md">
      <section className="md-pick ak-search">
        <Autocomplete label="Find a student" url="/attendance/api/student-search"
                      placeholder="Search name or student ID…"
                      onPick={(id) => id && setStudentId(String(id))} />
      </section>

      {!studentId ? <div className="md-card"><EmptyState icon="fa-user-magnifying-glass" title="Search for a student"
                                hint="Find any student to see their full attendance record across every term." /></div>
        : state.loading ? <div className="md-card"><Spinner label="Loading profile…" /></div>
        : state.error ? <div className="md-card"><ErrorState detail={state.error.message} /></div>
        : d && (
          <>
            <div className={'ak-hero sp2' + (d.warning ? ' warn' : '')}>
              {d.student.photo_url ? <img className="sp2-av" src={d.student.photo_url} alt="" />
                : <span className="sp2-av" aria-hidden="true">{initialsOf(d.student.name)}</span>}
              <div className="ak-hero-t">
                <span className="ak-kick"><span>{d.student.student_id}</span>{d.student.gender ? <span>{d.student.gender}</span> : null}<span>{d.overall.terms} term{d.overall.terms === 1 ? '' : 's'} tracked</span></span>
                <strong>{d.student.name}</strong>
                {d.warning
                  ? <span className="ak-chip bad"><i className="fas fa-triangle-exclamation" aria-hidden="true" /> Below the {d.threshold}% threshold — may need an intervention</span>
                  : <span className="ak-chip good"><i className="fas fa-circle-check" aria-hidden="true" /> Attendance is on track</span>}
              </div>
              <Ring pct={d.overall.percentage} label="Overall" />
              <div className="sp2-acts no-print">
                {d.warning && !hasOpen && <button type="button" className="ak-btn primary" onClick={openIntervention}>
                  <i className="fas fa-hand-holding-heart" aria-hidden="true" /><span> Open intervention</span></button>}
                <button type="button" className="ak-btn" onClick={() => window.print()}><i className="fas fa-print" aria-hidden="true" /><span> Print</span></button>
              </div>
            </div>

            <Tiles items={[
              { label: 'Full days', value: d.overall.full_days, tone: 'good' },
              { label: 'Late / partial', value: d.overall.late_days, tone: d.overall.late_days ? 'warn' : '' },
              { label: 'Absent days', value: d.overall.absent_days, tone: d.overall.absent_days ? 'bad' : '' },
              { label: 'Terms tracked', value: d.overall.terms },
            ]} />

            <div className="ak-grid2">
              {d.focus && (
                <Card icon="fa-calendar-check" title={`${d.focus.term} calendar`} sub={d.focus.class} className="ak-span2">
                  <div className="att-cal-legend">
                    {['present', 'late', 'absent', 'unmarked'].map((st) => (
                      <span key={st}><span className="att-cal-dot" style={{ background: STATUS_TONE[st] }} /> {STATUS_LABEL[st]}</span>))}
                  </div>
                  <TermCalendar calendar={d.focus.calendar} />
                </Card>)}
              <Card icon="fa-calendar-days" title="Term by term" flush>
                {d.terms.length === 0 ? <p className="ak-empty">No attendance recorded yet.</p> : (
                  <ul className="ak-people">
                    {d.terms.map((t) => (
                      <li key={t.enrollment_id} className="ak-person">
                        <span className="ak-pmain"><span className="ak-pname">{t.term} <span className="ak-dim">· {t.session}</span>
                          <small>{t.class} · {t.full_days} present · {t.late_days} late · {t.absent_days} absent</small></span></span>
                        <span className={'ak-pct ' + pctTone(t.percentage)}>{fmtPct(t.percentage)}</span>
                      </li>))}
                  </ul>)}
              </Card>
              {d.trend.length > 1 && <Card icon="fa-chart-line" title="Trend by term"><TrendBars trend={d.trend} /></Card>}
              {(d.interventions || []).length > 0 && (
                <Card icon="fa-hand-holding-heart" title="Interventions" flush>
                  <ul className="ak-people">
                    {d.interventions.map((iv) => (
                      <li key={iv.id} className="ak-person col">
                        <div className="sp2-iv">
                          <strong>{iv.reason || 'Intervention'}</strong>
                          <Pill tone={iv.status === 'Resolved' ? 'green' : iv.status === 'Escalated' ? 'red' : 'amber'}>{iv.status}</Pill>
                        </div>
                        <small className="ak-dim">Opened {iv.opened}{iv.opened_by ? ' by ' + iv.opened_by : ''}{iv.baseline != null ? ` · was ${fmtPct(iv.baseline)}` : ''}{iv.current != null ? ` → now ${fmtPct(iv.current)}` : ''}</small>
                        {iv.outcome && <small>Outcome: {iv.outcome}</small>}
                        {iv.notes.length > 0 && (
                          <ol className="iv2-tl">{iv.notes.map((n, i) => (
                            <li key={i}><b>{n.kind}</b> <span className="ak-dim">· {n.date}</span>{n.body && <div>{n.body}</div>}
                              {n.next_action && <div className="ak-dim">Next: {n.next_action}{n.next_date ? ` (by ${n.next_date})` : ''}</div>}</li>))}
                          </ol>)}
                      </li>))}
                  </ul>
                </Card>)}
              {(d.notifications || []).length > 0 && (
                <Card icon="fa-comment-sms" title="Messages to parents" flush>
                  <ul className="ak-people">
                    {d.notifications.map((n, i) => (
                      <li key={i} className="ak-person">
                        <span className="ak-pmain"><span className="ak-pname">{n.title.replace('Attendance: ', '')}<small>{n.channel} · {n.date}</small></span></span>
                        <Pill tone={n.status === 'Sent' ? 'green' : 'amber'}>{n.status}</Pill>
                      </li>))}
                  </ul>
                </Card>)}
            </div>
          </>
        )}
    </div>
  );
}
