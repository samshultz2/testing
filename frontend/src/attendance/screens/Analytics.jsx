import React, { useState } from 'react';
import { apiGet, apiPost } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, OfflineRequired } from '../../components/ui';
import { Tiles, Card, Ring, Person, MoreMenu, pctTone, fmtPct, fmtNum, UnmarkedNote } from '../kit';

const pctHex = (p) => (p >= 75 ? 'var(--success)' : p >= 50 ? 'var(--warning)' : 'var(--danger)');

// Horizontal % bars (class/branch ranking, trend as a column chart reused below).
function Bars({ rows, labelKey, valueKey }) {
  if (!rows || !rows.length) return <p className="att-sub">No data.</p>;
  return (
    <div className="att-bars">
      {rows.map((r, i) => (
        <div className="att-bar-row" key={i}>
          <div className="att-bar-lbl" title={r[labelKey]}>{r[labelKey]}</div>
          <div className="att-bar-track"><div className="att-bar-fill"
            style={{ width: Math.max(2, r[valueKey]) + '%', background: pctHex(r[valueKey]) }} /></div>
          <div className="att-bar-val">{fmtPct(r[valueKey])}</div>
        </div>))}
    </div>
  );
}

function ColumnChart({ rows }) {
  if (!rows || !rows.length) return <p className="att-sub">No data.</p>;
  return (
    <div className="att-trend" aria-label="Attendance percentage trend">
      {rows.map((t, i) => (
        <div key={i} className="att-trend-col" title={`${t.label}: ${fmtPct(t.percentage)}`}>
          <span className="att-trend-v">{fmtPct(t.percentage)}</span><div className="att-trend-bar" style={{ height: Math.max(4, t.percentage) + '%', background: pctHex(t.percentage) }} />
          <div className="att-trend-lbl">{t.label}</div>
        </div>))}
    </div>
  );
}

function HeatStrip({ rows }) {
  return (
    <div className="att-heat" role="img" aria-label="Attendance by weekday">
      {rows.map((r, i) => (
        <div key={i} className="att-heat-cell" title={`${r.label}: ${fmtPct(r.percentage)}`}
             style={{ background: r.percentage ? pctHex(r.percentage) : 'var(--gray-100,#f1f5f9)',
                      color: r.percentage ? '#fff' : 'inherit' }}>
          <div className="att-heat-day">{r.label}</div>
          <div className="att-heat-pct">{fmtPct(r.percentage)}</div>
        </div>))}
    </div>
  );
}

export default function Analytics() {
  const { term, terms = [], online } = useCtx();
  const [termId, setTermId] = useState(term ? String(term.id) : '');
  const [notifyChannel, setNotifyChannel] = useState('SMS');
  const [notifying, setNotifying] = useState(false);
  const tid = termId || (term ? String(term.id) : '');
  const notifyLow = async () => {
    setNotifying(true);
    try {
      const r = await apiPost('/attendance/api/notify/low', { term_id: tid, channel: notifyChannel });
      if (r && r.ok && r.redirect) window.location.href = r.redirect;
      else alert((r && r.error) || 'Could not draft the notice.');
    } catch (e) { alert(e.message || 'Could not draft the notice.'); }
    setNotifying(false);
  };
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

  const total = d ? (d.distribution.excellent + d.distribution.good + d.distribution.fair + d.distribution.poor) : 0;
  const BAND_STYLE = { excellent: 'good', good: 'good2', fair: 'warn', poor: 'bad' };

  return (
    <div className="md">
      <div className="ak-toolbar">
        {terms.length > 0 && (
          <label className="ax-term"><i className="fas fa-calendar" aria-hidden="true" />
            <select value={tid} onChange={(e) => setTermId(e.target.value)} aria-label="Term">
              {terms.map((t) => <option key={t.id} value={String(t.id)}>{t.name}{t.active ? ' (active)' : ''}</option>)}
            </select></label>)}
        {d && (
          <span className="ak-toolbar-r no-print">
            <a className="ak-btn" href={`/attendance/analytics/export?term_id=${tid}&format=xlsx`}><i className="fas fa-file-excel" aria-hidden="true" /><span> Excel</span></a>
            <MoreMenu up={false} label="More export options" items={[
              { icon: 'fa-file-csv', label: 'Download CSV', href: `/attendance/analytics/export?term_id=${tid}&format=csv` },
              { icon: 'fa-print', label: 'Print this page', onClick: () => window.print() },
            ]} />
          </span>)}
      </div>

      {!online ? <div className="md-card"><OfflineRequired what="Attendance analytics" /></div>
        : state.loading ? <div className="md-card"><Spinner label="Crunching attendance analytics…" /></div>
        : state.error ? <div className="md-card"><ErrorState detail={state.error.message} /></div>
        : !d ? <div className="md-card"><EmptyState icon="fa-chart-line" title="No term selected" hint="Pick a term to see analytics." /></div>
        : (
          <>
            <div className="ak-hero">
              <Ring pct={d.kpis.overall} label="Overall" />
              <div className="ak-hero-t">
                <span className="ak-kick"><span>{d.kpis.school_days} school days</span><span>{d.kpis.classes} classes</span><span>{d.kpis.students} students</span></span>
                <strong>School attendance</strong>
                <div className="ak-hero-chips">
                  <span className="ak-chip good"><i className="fas fa-trophy" aria-hidden="true" /> Best: <b>{d.kpis.best_class}</b></span>
                  <span className="ak-chip bad"><i className="fas fa-flag" aria-hidden="true" /> Needs attention: <b>{d.kpis.worst_class}</b></span>
                </div>
              </div>
            </div>

            <UnmarkedNote classes={d.unmarked_classes} what="the analytics" />

            <Tiles items={[
              { label: 'Students', value: d.kpis.students },
              { label: 'Classes', value: d.kpis.classes },
              { label: 'School days', value: d.kpis.school_days },
              { label: `Chronic (<${d.critical}%)`, value: d.kpis.chronic, tone: d.kpis.chronic ? 'bad' : 'good',
                onClick: () => { const el = document.getElementById('an-chronic'); if (el) el.scrollIntoView({ behavior: 'smooth' }); } },
            ]} />

            <div className="ak-bands">
              {dist.map((b) => (
                <div key={b.tone} className={'ak-band ' + BAND_STYLE[b.tone]}>
                  <span className="n">{b.count}</span><span className="t">{b.title}</span>
                  <span className="r">{b.range}{total ? ` · ${fmtPct(b.count / total * 100)}` : ''}</span>
                </div>))}
            </div>

            <div className="ak-grid2">
              <Card icon="fa-chart-column" title="Weekly trend" sub="Attendance rate by week"><ColumnChart rows={d.trend} /></Card>
              <Card icon="fa-calendar-week" title="By weekday" sub="Which days pupils miss most"><HeatStrip rows={d.heatmap} /></Card>
              <Card icon="fa-ranking-star" title="Class ranking" sub="Highest to lowest"><Bars rows={d.class_rank} labelKey="class" valueKey="percentage" /></Card>
              {d.branch_rank.length > 0
                ? <Card icon="fa-code-branch" title="Branch ranking"><Bars rows={d.branch_rank} labelKey="branch" valueKey="percentage" /></Card>
                : d.most_improved.length > 0 ? null : <span />}
              {d.most_improved.length > 0 && (
                <Card icon="fa-arrow-trend-up" title="Most improved" sub={d.prev_term ? `vs ${d.prev_term}` : ''} flush>
                  <ul className="ak-people">
                    {d.most_improved.map((s) => (
                      <Person key={s.id} name={s.name} sub={`${s.class} · ${fmtPct(s.from)} → ${fmtPct(s.to)}`} href={`/attendance/app?student_id=${s.id}#/student`}
                              right={<span className="ak-pct good">+{fmtNum(s.delta)}</span>} />))}
                  </ul>
                </Card>)}
            </div>

            <div id="an-chronic">
              <Card icon="fa-triangle-exclamation" title="Chronic absentees" sub={`Below ${d.critical}% this term`} flush
                    action={d.chronic_list.length > 0 && (
                      <span className="ak-notify no-print">
                        <select value={notifyChannel} onChange={(e) => setNotifyChannel(e.target.value)} aria-label="Channel">
                          <option>SMS</option><option>Email</option></select>
                        <button type="button" className="ak-btn primary" disabled={notifying} onClick={notifyLow} title="Drafts a message for review — nothing sends automatically">
                          <i className="fas fa-comment-sms" aria-hidden="true" /><span> Notify parents</span></button>
                      </span>)}>
                {d.chronic_list.length === 0
                  ? <EmptyState icon="fa-circle-check" title="None flagged" hint={`No student is below ${d.critical}% this term.`} />
                  : (
                    <ul className="ak-people">
                      {d.chronic_list.map((s) => (
                        <Person key={s.id + '|' + s.class} name={s.name} sub={`${s.class} · ${s.student_id}`} tone="out"
                                href={`/attendance/app?student_id=${s.id}#/student`}
                                right={<span className={'ak-pct ' + pctTone(s.percentage)}>{fmtPct(s.percentage)}</span>} />))}
                    </ul>)}
                {d.chronic_list.length > 0 && <p className="ak-foot">Notify parents drafts a message for you to review — nothing sends automatically.</p>}
              </Card>
            </div>
          </>
        )}
    </div>
  );
}
