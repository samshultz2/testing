import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, OfflineRequired } from '../../components/ui';
import { withGroups, genderLabel } from '../roster';
import { lastClass, rememberClass } from '../../lib/attprefs';
import { Picker, ClassChips, Tiles, Card, Ring, Meter, Seg, initialsOf, pctColor, pctTone, usePhone, pickInitialClass } from '../kit';

const round1 = (n) => Math.round(n * 10) / 10;

// Read-only termly attendance report — full parity with the Jinja termly page:
// attendance rate, counts, gender table, session (AM/PM) table, term info,
// performance bands and the per-student weekly breakdown with totals.
export default function TermlyReport() {
  const { classes = [], term, online, sync = {}, default_class, initial } = useCtx();
  const [assignmentId, setAssignmentIdRaw] = useState(() => pickInitialClass(classes, default_class, initial, lastClass));
  const setAssignmentId = (id) => {
    setAssignmentIdRaw(id);
    const c = classes.find((x) => String(x.id) === String(id));
    if (c) rememberClass(id, c.name);
  };
  const phone = usePhone();
  const [band, setBand] = useState('');            // '' = everyone, else a band tone
  const [order, setOrder] = useState('roll');      // roll | low | high

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

  const bandOf = (s) => {
    if (!perf) return '';
    const times = ti.total_times_opened;
    if (s.termly_total >= Math.floor(times * 0.9)) return 'excellent';
    if (s.termly_total >= Math.floor(times * 0.75)) return 'good';
    if (s.termly_total >= Math.floor(times * 0.5)) return 'fair';
    return 'poor';
  };
  let rows = d ? d.students.filter((s) => !band || bandOf(s) === band) : [];
  if (order !== 'roll') rows = rows.slice().sort((x, y) => (order === 'low' ? 1 : -1) * (x.termly_percentage - y.termly_percentage));
  const amPct = maxSess > 0 ? round1((ct.total_morning / maxSess) * 100) : 0;
  const pmPct = maxSess > 0 ? round1((ct.total_afternoon / maxSess) * 100) : 0;
  const BAND_STYLE = { excellent: 'good', good: 'good2', fair: 'warn', poor: 'bad' };

  return (
    <div className="md">
      <Picker><ClassChips classes={classes} value={assignmentId} onChange={setAssignmentId} /></Picker>

      {!online ? <div className="md-card"><OfflineRequired what="The termly report" /></div>
        : syncing ? <div className="md-card"><Spinner label={`Syncing your saved marks… (${pending} left) — the report will update once they reach the server.`} /></div>
        : !assignmentId ? <div className="md-card"><EmptyState icon="fa-hand-pointer" title="Pick a class" hint={`Choose a class to see its termly attendance${term ? ' for ' + term.name : ''}.`} /></div>
        : state.loading ? <div className="md-card"><Spinner label="Loading termly report…" /></div>
        : state.error ? <div className="md-card">{/no weeks/i.test(state.error.message || '') ? <EmptyState icon="fa-calendar-week" title="No weeks set up yet" hint="Add this term’s weeks in Term Setup, then the termly report fills in as attendance is marked." /> : <ErrorState detail={state.error.message} />}</div>
        : d && (
          <>
            <div className="ak-hero">
              <Ring pct={ct.termly_percentage} label="This term" />
              <div className="ak-hero-t">
                <span className="ak-kick">{term ? term.name : 'Term'} · {ti.total_weeks} weeks · {ti.total_school_days} school days</span>
                <strong>{d.class_name}</strong>
                <div className="ak-hero-m">
                  <Meter label="Morning" pct={amPct} />
                  <Meter label="Afternoon" pct={pmPct} />
                </div>
              </div>
              {term && <a className="ak-btn" href={`/attendance/termly/export?assignment_id=${assignmentId}&term_id=${term.id}`}>
                <i className="fas fa-file-excel" aria-hidden="true" /><span> Excel</span></a>}
            </div>

            <Tiles items={[
              { label: 'Students', value: d.total_students, sub: `${d.total_male_students} boys · ${d.total_female_students} girls` },
              { label: 'Roll calls', value: ti.total_times_opened, sub: 'times opened' },
              { label: 'Present / day', value: ct.termly_average, sub: 'average students' },
              { label: 'Boys avg', value: d.total_male_students > 0 ? round1(ct.male_attendance / d.total_male_students) : 0, sub: 'sessions each' },
              { label: 'Girls avg', value: d.total_female_students > 0 ? round1(ct.female_attendance / d.total_female_students) : 0, sub: 'sessions each' },
            ]} />

            <div className="ak-bands" role="radiogroup" aria-label="Filter by attendance band">
              {perf.map((b) => (
                <button key={b.tone} type="button" role="radio" aria-checked={band === b.tone}
                        className={'ak-band ' + BAND_STYLE[b.tone] + (band === b.tone ? ' on' : '')}
                        onClick={() => setBand(band === b.tone ? '' : b.tone)}>
                  <span className="n">{b.count}</span><span className="t">{b.title}</span><span className="r">{b.range}</span>
                </button>
              ))}
            </div>

            <Card icon="fa-users" title={band ? `${perf.find((b) => b.tone === band).title} students` : 'Students'}
                  sub={band ? <button type="button" className="ak-link" onClick={() => setBand('')}>Show everyone</button> : `${d.students.length} on roll`} flush
                  action={<Seg label="Order" value={order} onChange={setOrder} options={[
                    { value: 'roll', label: 'Register' }, { value: 'low', label: 'Lowest' }, { value: 'high', label: 'Highest' }]} />}>
              {rows.length === 0 ? <p className="ak-empty">No students in this band.</p> : (phone || order !== 'roll' || band) ? (
                <ul className="ak-people">
                  {rows.map((s) => (
                    <li key={s.student_id} className={'ak-person tr-row ' + pctTone(s.termly_percentage)}>
                      <span className="ak-pmain">
                        <span className="att-av" data-g={s.gender || ''} aria-hidden="true">{initialsOf(s.student_name)}</span>
                        <span className="ak-pname">{s.student_name}<small>AM {s.termly_morning} · PM {s.termly_afternoon} · {s.termly_total} sessions</small></span>
                      </span>
                      <span className="tr-bar"><i style={{ width: s.termly_percentage + '%', background: pctColor(s.termly_percentage) }} /></span>
                      <b className="tr-pct">{s.termly_percentage}%</b>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="ak-tablewrap">
                  <table className="ak-table" aria-label={'Termly report for ' + d.class_name}>
                    <thead><tr><th className="nm">Student</th>{d.weeks.map((w) => <th key={w.id}>W{w.number}</th>)}<th>AM</th><th>PM</th><th>Total</th><th>%</th></tr></thead>
                    <tbody>
                      {withGroups(d.students,
                        (gender, first, gkey) => <tr key={gkey} className="gh"><td colSpan={d.weeks.length + 5}>{genderLabel(gender)}</td></tr>,
                        (s) => (
                          <tr key={s.student_id}>
                            <td className="nm">{s.student_name}</td>
                            {s.weekly.map((w) => <td key={w.week_id}>{w.total}</td>)}
                            <td>{s.termly_morning}</td><td>{s.termly_afternoon}</td><td><b>{s.termly_total}</b></td>
                            <td><span className={'ak-pct ' + pctTone(s.termly_percentage)}>{s.termly_percentage}%</span></td>
                          </tr>
                        ))}
                    </tbody>
                    <tfoot><tr><td className="nm">Total</td>{d.weekly_totals.map((t, i) => <td key={i}>{t}</td>)}
                      <td>{ct.total_morning}</td><td>{ct.total_afternoon}</td><td>{ct.total_attendance}</td><td>{ct.termly_percentage}%</td></tr></tfoot>
                  </table>
                </div>
              )}
            </Card>
          </>
        )}
    </div>
  );
}
