import React, { useState } from 'react';
import { apiGet, apiPost } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, OfflineRequired, Banner } from '../../components/ui';
import { withGroups, genderLabel } from '../roster';
import { Picker, ClassChips, DateStepper, Seg, Tiles, Card, Person, Dot, prettyDate, pctColor, fmtPct } from '../kit';
import { lastClass, recentClasses, rememberClass } from '../../lib/attprefs';

function AbsenteesPanel({ assignmentId, date, className, ready, onNotify, notifying, canNotify }) {
  const [state] = useAsync(
    () => (ready ? apiGet(`/attendance/api/absentees?assignment_id=${assignmentId}&date=${encodeURIComponent(date)}`)
                 : Promise.resolve(null)),
    [assignmentId, date, ready]
  );
  const [copied, setCopied] = useState(false);
  const a = state.data;
  if (!ready || state.loading || state.error || !a || a.absentees.length === 0) return null;

  const copyText = () => {
    navigator.clipboard.writeText(a.share_text).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1500);
    });
  };
  const shareUrl = 'https://wa.me/?text=' + encodeURIComponent(a.share_text);

  return (
    <Card icon="fa-user-clock" title={`Absent (${a.absentees.length})`} sub="Reach parents in one tap" className="ak-absent no-print"
          action={<>
            <a className="ak-btn wa" href={shareUrl} target="_blank" rel="noopener" title="Share the list on WhatsApp"><i className="fab fa-whatsapp" aria-hidden="true" /><span> Share</span></a>
            <button type="button" className="ak-btn" onClick={copyText} title="Copy the list"><i className={'fas ' + (copied ? 'fa-check' : 'fa-copy')} aria-hidden="true" /><span> {copied ? 'Copied' : 'Copy'}</span></button>
            {canNotify && <button type="button" className="ak-btn primary" disabled={notifying} onClick={onNotify} title="Draft an SMS to these parents">
              <i className="fas fa-comment-sms" aria-hidden="true" /><span> Notify parents</span></button>}
          </>}>
      <ul className="ak-people">
        {a.absentees.map((s) => (
          <Person key={s.student_id} name={s.student_name}
                  sub={s.parent_name ? `${s.parent_name}${s.parent_relationship ? ' (' + s.parent_relationship + ')' : ''}${s.parent_phone ? ' · ' + s.parent_phone : ''}` : 'No parent contact'}
                  right={<>
                    {s.parent_phone && <a className="ak-round call" href={'tel:' + s.parent_phone} aria-label={`Call ${s.parent_name || 'parent'}`}><i className="fas fa-phone" aria-hidden="true" /></a>}
                    {s.wa_intl && <a className="ak-round wa" href={'https://wa.me/' + s.wa_intl} target="_blank" rel="noopener" aria-label="WhatsApp this parent"><i className="fab fa-whatsapp" aria-hidden="true" /></a>}
                  </>} />
        ))}
      </ul>
    </Card>
  );
}

// Read-only daily attendance summary (server-computed → needs the network).
export default function DailySummary() {
  const { classes = [], today, online, sync = {}, default_class, can_mark } = useCtx();
  // A form teacher lands on their own class; otherwise fall back to the last one
  // this user looked at (if it's still one they can access).
  const classIds = new Set(classes.map((c) => String(c.id)));
  const initClass = default_class ? String(default_class)
    : (classIds.has(lastClass()) ? lastClass() : '');
  const [show, setShow] = useState('all');
  const [assignmentId, setAssignmentId] = useState(initClass);
  const pickClass = (id) => {
    setAssignmentId(id);
    const c = classes.find((x) => String(x.id) === String(id));
    if (c) rememberClass(id, c.name);
  };
  const recents = recentClasses().filter((r) => classIds.has(String(r.id)));
  const [date, setDate] = useState(today || '');
  const [notifying, setNotifying] = useState(false);
  const notifyAbsentees = async () => {
    setNotifying(true);
    try {
      const r = await apiPost('/attendance/api/notify/absentees', { assignment_id: assignmentId, date });
      if (r && r.ok && r.redirect) window.location.href = r.redirect;
      else alert((r && r.error) || 'Could not draft the notice.');
    } catch (e) { alert(e.message || 'Could not draft the notice.'); }
    setNotifying(false);
  };

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

  // Whole-week breakdown: every school day at a glance (no date-by-date picking).
  const [week] = useAsync(
    () => (ready
      ? apiGet(`/attendance/api/report/week-totals?assignment_id=${assignmentId}&date=${encodeURIComponent(date)}`)
      : Promise.resolve(null)),
    [assignmentId, date, online, syncing]
  );

  const pct = (present, total) => (total ? present / total * 100 : 0);
  const d = state.data;
  const flag = (v) => v == null ? <Pill tone="gray">—</Pill>
    : v ? <Pill tone="green">Present</Pill> : <Pill tone="red">Absent</Pill>;

  const total = d ? d.total_students : 0;
  // A day has two sessions: (AM present + PM present) / (2 x students).
  const dayRate = (am, pm, n) => (n ? (am + pm) / (2 * n) * 100 : 0);
  const rateDay = d ? (d.attendance_percentage ?? dayRate(d.morning_present, d.afternoon_present, total)) : 0;
  const isAbs = (s) => s.morning_present === false || s.afternoon_present === false;
  const absentCount = d ? d.students.filter(isAbs).length : 0;
  const shown = d ? d.students.filter((s) => (show === 'absent' ? isAbs(s) : show === 'present' ? !isAbs(s) : true)) : [];
  const days = (week.data && week.data.days) || [];

  return (
    <div className="md">
      <Picker>
        <ClassChips classes={classes} value={assignmentId} onChange={pickClass} />
        <DateStepper date={date} setDate={setDate} today={today} />
      </Picker>

      {!online ? <div className="md-card"><OfflineRequired what="The daily summary" /></div>
        : syncing ? <div className="md-card"><Spinner label={`Syncing your saved marks… (${pending} left) — the summary will update once they reach the server.`} /></div>
        : !assignmentId ? <div className="md-card"><EmptyState icon="fa-hand-pointer" title="Pick a class" hint="Choose a class to see who was present." /></div>
        : state.loading ? <div className="md-card"><Spinner label="Loading summary…" /></div>
        : state.error ? <div className="md-card"><ErrorState detail={state.error.message} /></div>
        : d && (
          <>
            {days.length > 0 && (
              <div className="ak-week" role="tablist" aria-label={`Week ${week.data.week_number || ''} at a glance`}>
                {days.map((wd) => {
                  const p = wd.pct ?? dayRate(wd.am_present, wd.pm_present, wd.total);
                  return (
                    <button key={wd.date} type="button" role="tab" aria-selected={wd.date === date}
                            className={'ak-wday' + (wd.date === date ? ' on' : '')} onClick={() => setDate(wd.date)}>
                      <span className="d">{new Date(wd.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short' })}</span>
                      <span className="n">{new Date(wd.date + 'T00:00:00').getDate()}</span>
                      <span className="ak-mini"><i style={{ width: p + '%', background: pctColor(p) }} /></span>
                      <span className="p">{wd.total ? fmtPct(p) : '—'}</span>
                    </button>
                  );
                })}
              </div>
            )}

            {d.school_day === false && (
              <Banner tone="warn">
                {d.holiday ? `Holiday — ${d.holiday.reason}${d.holiday.type ? ' (' + d.holiday.type + ')' : ''}.`
                  : d.weekend ? 'This date is a weekend.' : 'This date is not a school day.'}
                {' '}Marks aren’t expected on this day.
              </Banner>
            )}

            <Tiles items={[
              { label: 'Attendance', value: fmtPct(rateDay), sub: `${prettyDate(d.date)} · AM + PM`, tone: total ? (rateDay >= 75 ? 'good' : rateDay >= 50 ? 'warn' : 'bad') : '' },
              { label: 'Morning', value: d.morning_present, unit: `/${total}`, sub: `${d.morning_absent} absent`, tone: d.morning_absent ? 'warn' : 'good' },
              { label: 'Afternoon', value: d.afternoon_present, unit: `/${total}`, sub: `${d.afternoon_absent} absent`, tone: d.afternoon_absent ? 'warn' : 'good' },
              { label: 'Students', value: total, sub: d.class_name },
            ]} />

            <div className="ak-cols">
              <Card icon="fa-users" title={d.class_name} sub={prettyDate(d.date, true)} flush
                    action={<Seg label="Show" value={show} onChange={setShow} options={[
                      { value: 'all', label: 'All', count: d.students.length },
                      { value: 'absent', label: 'Absent', count: absentCount },
                      { value: 'present', label: 'Present', count: d.students.length - absentCount }]} />}>
                {d.students.length === 0 ? (
                  <EmptyState icon="fa-users-slash" title="No students enrolled" hint="This class has no active enrolments for the term." />
                ) : shown.length === 0 ? (
                  <p className="ak-empty">{show === 'absent' ? 'Nobody was absent. 🎉' : 'No one here.'}</p>
                ) : (
                  <ul className="ak-people">
                    {withGroups(shown,
                      (gender, first, gkey) => <li key={gkey} className="md-ghead">{genderLabel(gender)}</li>,
                      (s) => (
                        <Person key={s.student_id} name={s.student_name} gender={s.gender}
                                tone={s.morning_present === false && s.afternoon_present === false ? 'out' : isAbs(s) ? 'half' : ''}
                                sub={s.morning_present == null && s.afternoon_present == null ? 'Not marked' : isAbs(s) ? (s.morning_present === false && s.afternoon_present === false ? 'Absent all day' : 'Absent half day') : 'Present'}
                                right={<><Dot v={s.morning_present} label="AM" /><Dot v={s.afternoon_present} label="PM" /></>} />
                      ))}
                  </ul>
                )}
              </Card>
              <AbsenteesPanel assignmentId={assignmentId} date={date} className={d.class_name} ready={ready}
                              canNotify={can_mark !== false} notifying={notifying} onNotify={notifyAbsentees} />
            </div>
          </>
        )}
    </div>
  );
}
