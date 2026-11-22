import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, OfflineRequired } from '../../components/ui';
import { withGroups, genderLabel } from '../roster';
import { lastClass, rememberClass } from '../../lib/attprefs';
import { Picker, ClassChips, Tiles, Card, Ring, MoreMenu, Seg, initialsOf, pctColor, pctTone, usePhone, pickInitialClass, fmtPct, fmtNum } from '../kit';
import { ColumnChart, Spread } from './Analytics';

const BANDS = [
  { k: 'excellent', t: 'Excellent', min: 90 },
  { k: 'good', t: 'Good', min: 75 },
  { k: 'fair', t: 'Fair', min: 50 },
  { k: 'poor', t: 'Poor', min: -1 },
];
const bandOf = (p) => BANDS.find((b) => p >= b.min).k;
const pctOf = (n, d) => (d > 0 ? Math.round(Math.min(n, d) / d * 10000) / 100 : 0);

// One student's weeks as small coloured cells (phone list + desktop table).
function WeekCell({ w, wk, big }) {
  if (!wk.days_so_far) return <span className={'tr2-c na' + (big ? ' big' : '')} title={`W${wk.number}: not yet`}>{big ? '–' : ''}</span>;
  const p = pctOf(w.total, wk.days_so_far * 2);
  return (
    <span className={'tr2-c' + (big ? ' big' : '')} title={`W${wk.number}: ${w.total} of ${wk.days_so_far * 2} sessions (${fmtPct(p)})`}
          style={{ background: `color-mix(in srgb, ${pctColor(p)} ${p >= 99.9 ? 88 : 30 + p * 0.45}%, var(--bg-card))`, color: p >= 60 ? '#fff' : 'var(--text-primary)' }}>
      {big ? w.total : ''}</span>
  );
}

// Read-only termly attendance report for one class: how the class did, week
// by week, and every student's term with their weeks at a glance.
export default function TermlyReport() {
  const { classes = [], term, online, sync = {}, default_class, initial } = useCtx();
  const [assignmentId, setAssignmentIdRaw] = useState(() => pickInitialClass(classes, default_class, initial, lastClass));
  const setAssignmentId = (id) => {
    setAssignmentIdRaw(id);
    setBand(''); setQ('');
    const c = classes.find((x) => String(x.id) === String(id));
    if (c) rememberClass(id, c.name);
  };
  const phone = usePhone();
  const [band, setBand] = useState('');
  const [order, setOrder] = useState('roll');
  const [q, setQ] = useState('');

  // Wait for queued offline marks to flush before computing the report.
  const pending = sync.pending || 0;
  const syncing = online && pending > 0;
  const ready = online && !syncing && assignmentId;
  const [state] = useAsync(
    () => (ready ? apiGet(`/attendance/api/report/termly?assignment_id=${assignmentId}`) : Promise.resolve(null)),
    [assignmentId, online, syncing]);

  const body = () => {
    if (!online) return <div className="md-card"><OfflineRequired what="The termly report" /></div>;
    if (syncing) return <div className="md-card"><Spinner label={`Syncing your saved marks… (${pending} left) — the report will update once they reach the server.`} /></div>;
    if (!assignmentId) return <div className="md-card"><EmptyState icon="fa-hand-pointer" title="Pick a class" hint={`Choose a class to see its termly attendance${term ? ' for ' + term.name : ''}.`} /></div>;
    if (state.loading) return <div className="md-card"><Spinner label="Loading termly report…" /></div>;
    if (state.error) {
      return <div className="md-card">{/no weeks/i.test(state.error.message || '')
        ? <EmptyState icon="fa-calendar-week" title="No weeks set up yet" hint="Add this term’s weeks in Term Setup, then the termly report fills in as attendance is marked." />
        : <ErrorState detail={state.error.message} />}</div>;
    }
    const d = state.data;
    if (!d) return null;
    return Report({ d });
  };

  function Report({ d }) { // plain function (called, not mounted) so the search box keeps focus
    const ct = d.class_totals;
    const ti = d.term_info;
    const soFar = ti.times_opened_so_far != null ? ti.times_opened_so_far : ti.total_times_opened;
    const daysSoFar = ti.school_days_so_far != null ? ti.school_days_so_far : ti.total_school_days;
    const done = daysSoFar >= ti.total_school_days;
    const n = d.total_students;
    const pct = (s) => (s.pct_so_far != null ? s.pct_so_far : s.termly_percentage);
    const classPct = ct.pct_so_far != null ? ct.pct_so_far : ct.termly_percentage;
    const possible = n * soFar;
    const amPct = pctOf(ct.total_morning, n * daysSoFar);
    const pmPct = pctOf(ct.total_afternoon, n * daysSoFar);
    const boys = d.total_male_students, girls = d.total_female_students;
    const boysPct = pctOf(ct.male_attendance, boys * soFar);
    const girlsPct = pctOf(ct.female_attendance, girls * soFar);
    const weeks = d.weeks || [];
    const curWeek = weeks.filter((w) => w.days_so_far > 0).length;
    const trend = weeks.map((w, i) => ({ w, i })).filter(({ w }) => w.days_so_far > 0)
      .map(({ w, i }) => ({ label: 'W' + w.number, percentage: pctOf(d.weekly_totals[i], n * w.days_so_far * 2) }));

    const dist = { excellent: 0, good: 0, fair: 0, poor: 0 };
    d.students.forEach((s) => { dist[bandOf(pct(s))] += 1; });
    const below = d.students.filter((s) => pct(s) < 75).length;
    const sorted = d.students.slice().sort((a, b) => pct(a) - pct(b));
    const low = sorted[0], high = sorted[sorted.length - 1];

    const say = [];
    if (n) {
      say.push(below ? `${below} of ${n} student${n === 1 ? ' is' : 's are'} below 75%.` : `All ${n} students are at 75% or more.`);
      if (Math.abs(amPct - pmPct) >= 3) say.push(`Afternoons are ${String(Math.round(Math.abs(amPct - pmPct) * 10) / 10)} points ${pmPct < amPct ? 'lower' : 'higher'} than mornings.`);
      if (n > 1 && high && low && pct(high) !== pct(low)) say.push(`Highest ${high.student_name.split(' ')[0]} (${fmtPct(pct(high))}), lowest ${low.student_name.split(' ')[0]} (${fmtPct(pct(low))}).`);
    }

    const ql = q.trim().toLowerCase();
    let rows = d.students.filter((s) => (!band || bandOf(pct(s)) === band)
      && (!ql || (s.student_name + ' ' + (s.admission_no || '')).toLowerCase().includes(ql)));
    if (order !== 'roll') rows = rows.slice().sort((x, y) => (order === 'low' ? 1 : -1) * (pct(x) - pct(y)));
    const grouped = order === 'roll';
    const bandName = band && BANDS.find((b) => b.k === band).t;
    const profile = (s) => `/attendance/app?student_id=${s.student_id}#/student`;

    return (
      <>
        <div className={'ak-hero an2-hero tr2-hero' + (classPct < 75 ? ' warn' : '')}>
          <Ring pct={classPct} label={done ? 'This term' : 'So far'} size={104} />
          <div className="ak-hero-t">
            <span className="ak-kick">
              <span>{done ? 'Term complete' : `Week ${curWeek} of ${ti.total_weeks}`}</span>
              <span>{done ? `${ti.total_school_days} school days` : `${daysSoFar} of ${ti.total_school_days} school days`}</span>
            </span>
            <strong>{d.class_name}</strong>
            {say.length > 0 && <p className="an2-say">{say.join(' ')}</p>}
            <div className="ak-hero-chips">
              <span className="ak-chip"><i className="fas fa-sun" aria-hidden="true" /> Mornings <b>{fmtPct(amPct)}</b></span>
              <span className="ak-chip"><i className="fas fa-cloud-sun" aria-hidden="true" /> Afternoons <b>{fmtPct(pmPct)}</b></span>
            </div>
          </div>
          <div className="an2-acts no-print">
            {term && <a className="ak-btn" href={`/attendance/termly/export?assignment_id=${d.class_id || assignmentId}&term_id=${term.id}`}>
              <i className="fas fa-file-excel" aria-hidden="true" /><span> Excel</span></a>}
            <MoreMenu up={false} label="More" items={[
              { icon: 'fa-print', label: 'Print this report', onClick: () => window.print() },
              term && { icon: 'fa-table', label: 'Classic termly page', href: `/attendance/termly?assignment_id=${assignmentId}&term_id=${term.id}` },
            ]} />
          </div>
        </div>

        <Tiles items={[
          { label: 'On roll', value: n, sub: `${boys} boys · ${girls} girls` },
          { label: 'Present per day', value: fmtNum(daysSoFar ? Math.round(ct.total_attendance / (daysSoFar * 2) * 10) / 10 : 0), sub: `of ${n} students` },
          boys ? { label: 'Boys', value: fmtPct(boysPct), sub: `${ct.male_attendance} of ${boys * soFar} sessions`, tone: pctTone(boysPct) } : null,
          girls ? { label: 'Girls', value: fmtPct(girlsPct), sub: `${ct.female_attendance} of ${girls * soFar} sessions`, tone: pctTone(girlsPct) } : null,
        ]} />

        <div className="ak-grid2">
          <Card icon="fa-chart-column" title="Week by week" sub={done ? 'Class rate each week' : 'Weeks so far'}>
            {trend.length ? <ColumnChart rows={trend} /> : <p className="ak-empty">No school days yet this term.</p>}
          </Card>
          <Card icon="fa-users-viewfinder" title="How students are spread" sub="Tap a band to list those students">
            <Spread dist={dist} total={n} pickAll active={band}
                    onPick={(k) => { setBand(band === k ? '' : k); const el = document.getElementById('tr2-students'); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }} />
          </Card>
        </div>

        <div id="tr2-students">
          <Card icon="fa-users" title={band ? `${bandName} students` : 'Students'}
                sub={band ? <button type="button" className="ak-link" onClick={() => setBand('')}>Show all {n}</button>
                  : `${n} on roll · ${possible ? soFar : 0} sessions each${done ? '' : ' so far'}`} flush
                action={<Seg label="Order" value={order} onChange={setOrder} options={[
                  { value: 'roll', label: 'Register' }, { value: 'low', label: 'Lowest' }, { value: 'high', label: 'Highest' }]} />}>
            {n > 8 && (
              <div className="an2-find"><i className="fas fa-magnifying-glass" aria-hidden="true" />
                <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a student…" aria-label="Find a student" /></div>)}
            {rows.length === 0 ? <p className="ak-empty">{n ? 'No student matches.' : 'No students on this class roll.'}</p>
              : phone ? (
                <ul className="tr2-list">
                  {(grouped ? withGroups(rows, (g, first, key) => <li key={key} className="md-ghead">{genderLabel(g)}</li>, (s) => Row(s))
                    : rows.map((s) => Row(s)))}
                </ul>
              ) : (
                <div className="ak-tablewrap tr2-grid">
                  <table className="ak-table tr2-table" aria-label={'Termly report for ' + d.class_name}>
                    <thead><tr><th className="nm">Student</th>{weeks.map((w) => <th key={w.id} title={`${w.start} – ${w.end}`}>W{w.number}</th>)}
                      <th>AM</th><th>PM</th><th>Total</th><th>Rate</th></tr></thead>
                    <tbody>
                      {(grouped
                        ? withGroups(rows, (g, first, key) => <tr key={key} className="gh"><td colSpan={weeks.length + 5}>{genderLabel(g)}</td></tr>, (s) => TRow(s))
                        : rows.map((s) => TRow(s)))}
                    </tbody>
                    {!band && !ql && (
                      <tfoot><tr><td className="nm">Class</td>
                        {weeks.map((w, i) => <td key={w.id}>{w.days_so_far ? fmtPct(pctOf(d.weekly_totals[i], n * w.days_so_far * 2)).replace(/\.\d+%/, '%') : '–'}</td>)}
                        <td>{ct.total_morning}</td><td>{ct.total_afternoon}</td><td>{ct.total_attendance}</td>
                        <td><span className={'ak-pct ' + pctTone(classPct)}>{fmtPct(classPct)}</span></td></tr></tfoot>)}
                  </table>
                </div>
              )}
            <p className="ak-foot">Each week cell is that student’s sessions present (morning + afternoon){done ? '' : '; rates count school days up to today'}.</p>
          </Card>
        </div>
      </>
    );

    function Row(s) {
      const p = pct(s);
      return (
        <li key={s.student_id} className="tr2-row">
          <a href={profile(s)}>
            <span className="att-av" data-g={s.gender || ''} aria-hidden="true">{initialsOf(s.student_name)}</span>
            <span className="nm">{s.student_name}<small>{s.termly_total} of {soFar} · AM {s.termly_morning} · PM {s.termly_afternoon}</small></span>
            <span className={'ak-pct ' + pctTone(p)}>{fmtPct(p)}</span>
            <span className="wk" aria-hidden="true">{s.weekly.map((w, i) => <WeekCell key={w.week_id} w={w} wk={weeks[i]} />)}</span>
          </a>
        </li>
      );
    }
    function TRow(s) {
      const p = pct(s);
      return (
        <tr key={s.student_id} className={p < 50 ? 'low' : ''}>
          <td className="nm"><a href={profile(s)}>{s.student_name}</a></td>
          {s.weekly.map((w, i) => <td key={w.week_id} className="wc"><WeekCell w={w} wk={weeks[i]} big /></td>)}
          <td>{s.termly_morning}</td><td>{s.termly_afternoon}</td><td><b>{s.termly_total}</b></td>
          <td><span className="tr2-rate"><i style={{ width: Math.max(2, p) + '%', background: pctColor(p) }} /></span><span className={'ak-pct ' + pctTone(p)}>{fmtPct(p)}</span></td>
        </tr>
      );
    }
  }

  return (
    <div className="md an2 tr2">
      <Picker><ClassChips classes={classes} value={assignmentId} onChange={setAssignmentId} /></Picker>
      {body()}
    </div>
  );
}
