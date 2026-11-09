import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, OfflineRequired } from '../../components/ui';
import { withGroups, genderLabel } from '../roster';
import { lastClass, rememberClass } from '../../lib/attprefs';
import { Picker, ClassChips, WeekStepper, Tiles, Card, Ring, Meter, Dot, initialsOf, pctTone, pickInitialClass, fmtPct } from '../kit';

// Read-only weekly attendance report — full parity with the Jinja weekly page:
// attendance rate, student/school-day/roll-call counts, week totals (AM/PM/
// combined, male/female, max possible) and a per-student daily breakdown.
export default function WeeklyReport() {
  const { classes = [], weeks = [], online, sync = {}, default_class, default_week, initial } = useCtx();
  const [assignmentId, setAssignmentIdRaw] = useState(() => pickInitialClass(classes, default_class, initial, lastClass));
  const setAssignmentId = (id) => {
    setAssignmentIdRaw(id);
    const c = classes.find((x) => String(x.id) === String(id));
    if (c) rememberClass(id, c.name);
  };
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

  const nDays = d ? d.school_days.length : 0;
  const maxEach = nDays * 2;
  const cols = { gridTemplateColumns: `minmax(0,1fr) repeat(${nDays}, 52px) 64px` };
  const fmtDay = (day) => new Date(String(day).slice(0, 10) + 'T00:00:00');

  return (
    <div className="md">
      <Picker>
        <ClassChips classes={classes} value={assignmentId} onChange={setAssignmentId} />
        <WeekStepper weeks={weeks} value={weekId} onChange={setWeekId} current={default_week} />
      </Picker>

      {!online ? <div className="md-card"><OfflineRequired what="The weekly report" /></div>
        : syncing ? <div className="md-card"><Spinner label={`Syncing your saved marks… (${pending} left) — the report will update once they reach the server.`} /></div>
        : !assignmentId ? <div className="md-card"><EmptyState icon="fa-hand-pointer" title="Pick a class" hint="Choose a class to see the week’s attendance." /></div>
        : !weekId ? <div className="md-card"><EmptyState icon="fa-calendar-week" title="No weeks defined" hint="This term has no weeks set up yet." /></div>
        : state.loading ? <div className="md-card"><Spinner label="Loading weekly report…" /></div>
        : state.error ? <div className="md-card"><ErrorState detail={state.error.message} /></div>
        : d && (
          <>
            <div className="ak-hero">
              <Ring pct={ct.weekly_percentage} label="Attendance" />
              <div className="ak-hero-t">
                <span className="ak-kick">Week {d.week_info.week_number} · {d.week_info.start_date} → {d.week_info.end_date}</span>
                <strong>{d.class_name}</strong>
                <div className="ak-hero-m">
                  <Meter label="Morning" value={ct.total_morning} max={maxPossible} />
                  <Meter label="Afternoon" value={ct.total_afternoon} max={maxPossible} />
                </div>
              </div>
              <a className="ak-btn" href={`/attendance/weekly/export?assignment_id=${assignmentId}&week_id=${weekId}`}>
                <i className="fas fa-file-excel" aria-hidden="true" /><span> Excel</span></a>
            </div>

            <Tiles items={[
              { label: 'Students', value: d.total_students },
              { label: 'School days', value: d.school_days_count },
              { label: 'Roll calls', value: d.times_opened },
              { label: 'Boys present', value: ct.male_attendance, sub: 'sessions' },
              { label: 'Girls present', value: ct.female_attendance, sub: 'sessions' },
              { label: 'Combined', value: ct.total_attendance, unit: `/${maxPossible * 2}`, sub: 'sessions present' },
            ]} />

            <Card icon="fa-list" title="Students" sub="Each day shows morning then afternoon" flush>
              {d.students.length === 0 ? (
                <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
              ) : (
                <div className="wr">
                  <div className="wr-row wr-head" style={cols}>
                    <span>Student</span>
                    {d.school_days.map((day) => (
                      <span key={day} className="c"><b>{fmtDay(day).toLocaleDateString(undefined, { weekday: 'short' })}</b><small>{fmtDay(day).getDate()}</small></span>
                    ))}
                    <span className="c">Total</span>
                  </div>
                  {withGroups(d.students,
                    (gender, first, gkey) => <div key={gkey} className="wg-ghead">{genderLabel(gender)}</div>,
                    (s) => {
                      const p = maxEach ? s.weekly_total / maxEach * 100 : 0;
                      return (
                        <div key={s.student_id} className="wr-row" style={cols}>
                          <span className="wr-who">
                            <span className="att-av" data-g={s.gender || ''} aria-hidden="true">{initialsOf(s.student_name)}</span>
                            <span className="wg-name">{s.student_name}<small>AM {s.weekly_morning} · PM {s.weekly_afternoon}</small></span>
                          </span>
                          {s.daily.map((day) => (
                            <span key={day.date} className="c wr-pair" title={day.day_name} data-d={String(day.day_name || '').slice(0, 3)}>
                              <Dot v={day.morning} label={`${day.day_name} AM`} /><Dot v={day.afternoon} label={`${day.day_name} PM`} />
                            </span>
                          ))}
                          <span className={'c wr-tot ' + pctTone(p)}><b>{s.weekly_total}</b><small>{fmtPct(p)}</small></span>
                        </div>
                      );
                    })}
                  <div className="wr-row wr-foot" style={cols}>
                    <span>Class total</span>
                    {d.school_days.map((day) => <span key={day} className="c" />)}
                    <span className="c"><b>{ct.total_attendance}</b></span>
                  </div>
                </div>
              )}
            </Card>
          </>
        )}
    </div>
  );
}
