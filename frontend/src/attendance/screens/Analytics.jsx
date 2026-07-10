import React, { useState } from 'react';
import { apiGet } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Spinner, EmptyState, ErrorState, OfflineRequired,
         StatCards, SectionTitle, Pill, PerfBands } from '../../components/ui';

const pctTone = (p) => (p >= 75 ? '#1cc88a' : p >= 50 ? '#f6c23e' : '#e74a3b');

// Horizontal % bars (class/branch ranking, trend as a column chart reused below).
function Bars({ rows, labelKey, valueKey }) {
  if (!rows || !rows.length) return <p className="att-sub">No data.</p>;
  return (
    <div className="att-bars">
      {rows.map((r, i) => (
        <div className="att-bar-row" key={i}>
          <div className="att-bar-lbl" title={r[labelKey]}>{r[labelKey]}</div>
          <div className="att-bar-track"><div className="att-bar-fill"
            style={{ width: Math.max(2, r[valueKey]) + '%', background: pctTone(r[valueKey]) }} /></div>
          <div className="att-bar-val">{r[valueKey]}%</div>
        </div>))}
    </div>
  );
}

function ColumnChart({ rows }) {
  if (!rows || !rows.length) return <p className="att-sub">No data.</p>;
  return (
    <div className="att-trend" aria-label="Attendance percentage trend">
      {rows.map((t, i) => (
        <div key={i} className="att-trend-col" title={`${t.label}: ${t.percentage}%`}>
          <div className="att-trend-bar" style={{ height: Math.max(4, t.percentage) + '%', background: pctTone(t.percentage) }} />
          <div className="att-trend-lbl">{t.label}</div>
        </div>))}
    </div>
  );
}

function HeatStrip({ rows }) {
  return (
    <div className="att-heat" role="img" aria-label="Attendance by weekday">
      {rows.map((r, i) => (
        <div key={i} className="att-heat-cell" title={`${r.label}: ${r.percentage}%`}
             style={{ background: r.percentage ? pctTone(r.percentage) : 'var(--gray-100,#f1f5f9)',
                      color: r.percentage ? '#fff' : 'inherit' }}>
          <div className="att-heat-day">{r.label}</div>
          <div className="att-heat-pct">{r.percentage}%</div>
        </div>))}
    </div>
  );
}

export default function Analytics() {
  const { term, terms = [], online } = useCtx();
  const [termId, setTermId] = useState(term ? String(term.id) : '');
  const tid = termId || (term ? String(term.id) : '');
  const [state] = useAsync(
    () => (online && tid ? apiGet(`/attendance/api/analytics?term_id=${tid}`) : Promise.resolve(null)),
    [tid, online]);
  const d = state.data;

  const dist = d && [
    { tone: 'excellent', title: 'Excellent', count: d.distribution.excellent, range: '≥90%' },
    { tone: 'good', title: 'Good', count: d.distribution.good, range: '75–89%' },
    { tone: 'fair', title: 'Fair', count: d.distribution.fair, range: '50–74%' },
    { tone: 'poor', title: 'Poor', count: d.distribution.poor, range: '<50%' },
  ];

  return (
    <div>
      <Toolbar>
        {terms.length > 0 && (
          <label className="att-inline-field">Term{' '}
            <select className="form-control" style={{ maxWidth: 240, display: 'inline-block' }}
                    value={tid} onChange={(e) => setTermId(e.target.value)}>
              {terms.map((t) => <option key={t.id} value={String(t.id)}>{t.name}{t.active ? ' (active)' : ''}</option>)}
            </select>
          </label>)}
      </Toolbar>

      {!online ? <OfflineRequired what="Attendance analytics" />
        : state.loading ? <Spinner label="Crunching attendance analytics…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : !d ? <EmptyState icon="fa-chart-line" title="No term selected" hint="Pick a term to see analytics." />
        : (
          <>
            <StatCards items={[
              { value: d.kpis.overall + '%', label: 'Overall rate', primary: true },
              { value: d.kpis.students, label: 'Students' },
              { value: d.kpis.classes, label: 'Classes' },
              { value: d.kpis.chronic, label: `Chronic (<${d.critical}%)` },
              { value: d.kpis.school_days, label: 'School days' },
            ]} />
            <div className="att-sub" style={{ marginTop: -4 }}>
              Best: <b>{d.kpis.best_class}</b> · Needs attention: <b>{d.kpis.worst_class}</b>
            </div>

            <SectionTitle icon="fa-chart-column">Weekly trend</SectionTitle>
            <ColumnChart rows={d.trend} />

            <SectionTitle icon="fa-calendar-week">By weekday</SectionTitle>
            <HeatStrip rows={d.heatmap} />

            <SectionTitle icon="fa-layer-group">Attendance distribution</SectionTitle>
            <PerfBands bands={dist} />

            <SectionTitle icon="fa-ranking-star">Class ranking</SectionTitle>
            <Bars rows={d.class_rank} labelKey="class" valueKey="percentage" />

            {d.branch_rank.length > 0 && (<>
              <SectionTitle icon="fa-code-branch">Branch ranking</SectionTitle>
              <Bars rows={d.branch_rank} labelKey="branch" valueKey="percentage" />
            </>)}

            {d.most_improved.length > 0 && (<>
              <SectionTitle icon="fa-arrow-trend-up">Most improved{d.prev_term ? ` (vs ${d.prev_term})` : ''}</SectionTitle>
              <div className="att-grid-wrap">
                <table className="att-grid" aria-label="Most improved students">
                  <thead><tr><th className="att-grid-name" scope="col">Student</th><th scope="col">Class</th>
                    <th scope="col">Was</th><th scope="col">Now</th><th scope="col">Change</th></tr></thead>
                  <tbody>{d.most_improved.map((s) => (
                    <tr key={s.id}><td className="att-grid-name"><a href={`/attendance/app?student_id=${s.id}#/student`}>{s.name}</a></td>
                      <td>{s.class}</td><td>{s.from}%</td><td>{s.to}%</td>
                      <td><b style={{ color: '#1cc88a' }}>+{s.delta}</b></td></tr>))}
                  </tbody>
                </table>
              </div>
            </>)}

            <SectionTitle icon="fa-triangle-exclamation">Chronic absentees</SectionTitle>
            {d.chronic_list.length === 0
              ? <EmptyState icon="fa-circle-check" title="None flagged" hint={`No student is below ${d.critical}% this term.`} />
              : (
                <div className="att-grid-wrap">
                  <table className="att-grid" aria-label="Chronic absentees">
                    <thead><tr><th className="att-grid-name" scope="col">Student</th><th scope="col">Class</th><th scope="col">%</th></tr></thead>
                    <tbody>{d.chronic_list.map((s) => (
                      <tr key={s.id + '|' + s.class}><td className="att-grid-name"><a href={`/attendance/app?student_id=${s.id}#/student`}>{s.name}</a>
                        <div className="att-sub">{s.student_id}</div></td>
                        <td>{s.class}</td><td><Pill tone="red">{s.percentage}%</Pill></td></tr>))}
                    </tbody>
                  </table>
                </div>)}
          </>
        )}
    </div>
  );
}
