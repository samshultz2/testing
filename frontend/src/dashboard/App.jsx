import React, { useState } from 'react';
import Chart, { chartTheme } from './charts';
import { Kpi, Widget, Empty, ChartBox, naira, nairaShort } from './components';
import Customize from './Customize';

const ICON = { jamb: 'fa-file-contract', waec: 'fa-file-alt', mock: 'fa-clipboard-list' };

export default function App({ data }) {
  const d = data || {};
  const enabled = d.enabled || [];
  const has = (k) => enabled.includes(k);
  const urls = d.urls || {};
  const t = chartTheme();
  const [customizing, setCustomizing] = useState(false);

  const doughnut = (extra) => ({
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
    cutout: '62%', ...extra,
  });
  const barOpts = {
    responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true, ticks: { stepSize: 1, precision: 0 }, grid: { color: t.grid } }, x: { grid: { display: false } } },
  };

  const crossModule = d.finance_stat || d.sales_stat || d.hr_stat || d.cbt_stat || d.library_stat;
  const dateLabel = d.today ? new Date(d.today).toLocaleDateString(undefined,
    { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }) : '';
  const tc = d.teacher_classes;

  return (
    <>
      {/* Hero */}
      <div className="dash-hero">
        <div>
          <h1>Welcome back{d.user_name ? ', ' + d.user_name : ''} 👋</h1>
          <p>{dateLabel}{d.active_session ? ' · ' + d.active_session.name : ''}</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem' }}>
          {d.active_term && <div className="term-chip"><i className="fas fa-calendar-day" /> {d.active_term.name}</div>}
          <button type="button" onClick={() => setCustomizing(true)} className="btn btn-secondary btn-sm" title="Choose widgets"><i className="fas fa-sliders" /> Customize</button>
        </div>
      </div>

      {customizing && <Customize catalog={d.widget_catalog} onClose={() => setCustomizing(false)} />}

      {/* Teacher: My Classes */}
      {tc !== null && tc !== undefined && (
        <div className="card">
          <div className="card-header">
            <h3><i className="fas fa-chalkboard-teacher" /> My Classes</h3>
            <a href={urls.week_grid} className="btn btn-secondary btn-sm"><i className="fas fa-calendar-week" /> Mark a week</a>
          </div>
          <div className="card-body">
            {tc.length ? (
              <div className="data-cards">
                {tc.map((c) => (
                  <div className="data-card" key={c.id}>
                    <div className="data-card-header">
                      <div className="data-card-title">{c.name}</div>
                      <span className="badge badge-info">{c.count} student{c.count === 1 ? '' : 's'}</span>
                    </div>
                    <div className="data-card-actions" style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
                      <a href={c.mark_url} className="btn btn-primary btn-sm" style={{ flex: 1 }}><i className="fas fa-clipboard-check" /> Attendance</a>
                      <a href={c.week_url} className="btn btn-secondary btn-sm" style={{ flex: 1 }}><i className="fas fa-calendar-week" /> Week</a>
                      {d.can_results && <a href={urls.bulk_entry} className="btn btn-secondary btn-sm" style={{ flex: 1 }}><i className="fas fa-pen" /> Scores</a>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty icon="fa-chalkboard">You have no classes assigned for {d.active_term ? d.active_term.name : 'this term'}. Ask an admin to set you as a form teacher.</Empty>
            )}
          </div>
        </div>
      )}

      {/* Announcements */}
      {(d.announcements || []).length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem', marginBottom: '1.1rem' }}>
          {d.announcements.map((a, i) => {
            const color = a.category === 'Important' ? '#e74a3b' : a.category === 'Event' ? '#f6c23e' : 'var(--primary)';
            const icon = a.category === 'Important' ? 'fa-triangle-exclamation' : a.category === 'Event' ? 'fa-calendar-day' : 'fa-bullhorn';
            return (
              <div key={i} style={{ display: 'flex', gap: '.6rem', alignItems: 'flex-start', background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderLeft: '4px solid ' + color, borderRadius: 'var(--radius-md)', padding: '.7rem .9rem' }}>
                <i className={'fas ' + icon} style={{ color, marginTop: '.2rem' }} />
                <div style={{ flex: 1 }}><strong>{a.title}</strong>{a.body && <div className="text-muted text-sm">{a.body}</div>}</div>
                {a.is_pinned && <i className="fas fa-thumbtack text-muted" title="Pinned" />}
              </div>
            );
          })}
        </div>
      )}

      {/* Student KPIs */}
      {has('kpi') && (
        <div className="kpi-row">
          <Kpi tone="blue" icon="fa-users" value={d.total_students} label="Students" />
          <Kpi tone="green" icon="fa-user-check" value={d.active_enrollments} label="Enrolled" />
          <Kpi tone="teal" icon="fa-percent" value={(d.attendance_stats || {}).today_percentage + '%'} label="Attendance today" />
          <Kpi tone="purple" icon="fa-user-graduate" value={d.graduates_count} label="Graduates" />
        </div>
      )}

      {/* Cross-module KPIs */}
      {crossModule && (
        <div className="kpi-row">
          {d.finance_stat && <>
            <Kpi tone="green" icon="fa-coins" value={nairaShort(d.finance_stat.collected)} title={naira(d.finance_stat.collected)} label="Fees collected (term)" />
            <Kpi tone="teal" icon="fa-scale-balanced" value={nairaShort(d.finance_stat.net)} title={naira(d.finance_stat.net)} label="Net (term)" />
          </>}
          {d.sales_stat && <Kpi tone="blue" icon="fa-cash-register" value={nairaShort(d.sales_stat.today)} title={naira(d.sales_stat.today)} label={`Sales today (${d.sales_stat.count_today})`} />}
          {d.hr_stat && <Kpi tone="purple" icon="fa-id-badge" value={d.hr_stat.total} label={`Staff (${d.hr_stat.teaching} teaching)`} />}
          {d.cbt_stat && <Kpi tone="blue" icon="fa-laptop-code" value={d.cbt_stat.published} label={`CBT exams · ${d.cbt_stat.attempts} attempts`} />}
          {d.library_stat && <Kpi tone="teal" icon="fa-book" value={d.library_stat.books} label={`Books · ${d.library_stat.on_loan} on loan`} />}
        </div>
      )}

      {/* Exam snapshots */}
      {has('exams') && (
        <div className="dash-grid c3">
          <ExamCard kind="jamb" snap={d.jamb_snapshot} url={urls.jamb_list} />
          <ExamCard kind="waec" snap={d.waec_snapshot} url={urls.waec_list} />
          <ExamCard kind="mock" snap={d.mock_snapshot} url={urls.mock_index} />
        </div>
      )}

      {/* Charts */}
      {has('charts') && (
        <div className="dash-grid c3">
          <Widget icon="fa-venus-mars" title="Gender">
            <ChartBox>
              <Chart type="doughnut" options={doughnut()} data={{ labels: ['Male', 'Female'],
                datasets: [{ data: [d.male_students, d.female_students], backgroundColor: ['#4e73df', '#e74a3b'], borderWidth: 0 }] }} />
            </ChartBox>
          </Widget>
          <Widget icon="fa-route" title="Streams">
            <ChartBox>
              <Chart type="doughnut" options={doughnut()} data={{ labels: Object.keys(d.stream_dist || {}),
                datasets: [{ data: Object.values(d.stream_dist || {}), backgroundColor: ['#11998e', '#667eea', '#f6c23e', '#cbd5e1'], borderWidth: 0 }] }} />
            </ChartBox>
          </Widget>
          <Widget icon="fa-birthday-cake" title="Age groups">
            <ChartBox>
              <Chart type="bar" options={barOpts} data={{ labels: ['0-10', '11-13', '14-16', '17-19', '20+'],
                datasets: [{ data: ['0-10', '11-13', '14-16', '17-19', '20+'].map((k) => (d.age_distribution || {})[k] || 0), backgroundColor: '#4e73df', borderRadius: 6 }] }} />
            </ChartBox>
          </Widget>
        </div>
      )}

      {/* Attendance trend + Top JAMB */}
      {has('attendance_trend') && (
        <div className="dash-grid split">
          <Widget icon="fa-chart-line" title="Attendance trend"
                  action={<a href={urls.weekly_summary} className="btn btn-secondary btn-sm">Details</a>}>
            <ChartBox>
              {(d.attendance_trend || []).length ? (
                <Chart type="line" options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                  scales: { y: { beginAtZero: true, max: 100, grid: { color: t.grid } }, x: { grid: { display: false } } } }}
                  data={{ labels: d.attendance_trend.map((x) => x.label),
                    datasets: [{ data: d.attendance_trend.map((x) => x.pct), borderColor: '#11998e', backgroundColor: 'rgba(17,153,142,.12)', fill: true, tension: .35, pointRadius: 4, pointBackgroundColor: '#11998e', borderWidth: 3 }] }} />
              ) : <Empty icon="fa-chart-line">No attendance recorded yet</Empty>}
            </ChartBox>
          </Widget>
          <Widget icon="fa-trophy" title="Top JAMB">
            {d.jamb_snapshot && d.jamb_snapshot.top && d.jamb_snapshot.top.length ? (
              <div className="lead-list">
                {d.jamb_snapshot.top.map((x, i) => (
                  <div className="lead-item" key={i}>
                    <span className={'lead-rank' + (i === 0 ? ' g1' : i === 1 ? ' g2' : i === 2 ? ' g3' : '')}>{i + 1}</span>
                    <span className="lead-name">{x.name}</span>
                    <span className="lead-score">{x.score}</span>
                  </div>
                ))}
              </div>
            ) : <Empty icon="fa-trophy">No JAMB results</Empty>}
          </Widget>
        </div>
      )}

      {/* Class enrollment + Religion */}
      {has('class_religion') && (
        <div className="dash-grid split">
          <Widget icon="fa-school" title="Class enrollment"
                  action={<a href={urls.classes_list} className="btn btn-secondary btn-sm">Manage</a>}>
            <ChartBox height="240px">
              {(d.class_stats || []).length ? (
                <Chart type="bar" options={{ responsive: true, maintainAspectRatio: false,
                  plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
                  scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, grid: { color: t.grid } } } }}
                  data={{ labels: d.class_stats.map((c) => c.name), datasets: [
                    { label: 'Male', data: d.class_stats.map((c) => c.male), backgroundColor: '#4e73df', borderRadius: 4 },
                    { label: 'Female', data: d.class_stats.map((c) => c.female), backgroundColor: '#e74a3b', borderRadius: 4 }] }} />
              ) : <Empty icon="fa-school">No class enrollment</Empty>}
            </ChartBox>
          </Widget>
          <Widget icon="fa-pray" title="Religion">
            {Object.keys(d.religion_stats || {}).length ? (
              Object.entries(d.religion_stats).map(([rel, count]) => (
                <div className="relig-bar" key={rel}>
                  <span className="lab">{rel}</span>
                  <span className="track"><span className="fill" style={{ width: (d.total_students ? (count / d.total_students * 100).toFixed(1) : 0) + '%' }} /></span>
                  <span className="num">{count}</span>
                </div>
              ))
            ) : <Empty icon="fa-chart-bar">No data</Empty>}
          </Widget>
        </div>
      )}

      {/* People: Birthdays + Recent students + Activity */}
      {has('people') && (
        <div className={'dash-grid ' + ((d.recent_activity || []).length ? 'c3' : 'c2')}>
          <Widget icon="fa-gift" title="Birthdays">
            {(d.birthdays_today || []).map((s, i) => (
              <div className="birthday-item highlight" key={'t' + i}>
                <span className="birthday-avatar">🎂</span>
                <div><div className="birthday-name">{s.full_name}</div><div className="birthday-date">Today · {s.age} yrs</div></div>
              </div>
            ))}
            {(d.birthdays_week || []).slice(0, 5).map((s, i) => (
              <div className="birthday-item" key={'w' + i}>
                <span className="birthday-avatar">🎈</span>
                <div><div className="birthday-name">{s.full_name}</div><div className="birthday-date">{s.date_label}</div></div>
              </div>
            ))}
            {!(d.birthdays_today || []).length && !(d.birthdays_week || []).length && <Empty icon="fa-calendar-day">No birthdays this week</Empty>}
          </Widget>

          <Widget icon="fa-user-clock" title="Recent students" bodyStyle={{ padding: '.4rem 1rem' }}
                  action={<a href={urls.students_list} className="btn btn-secondary btn-sm">All</a>}>
            {(d.recent_students || []).length ? d.recent_students.map((s) => (
              <a href={s.url} className="recent-item" key={s.id}>
                <div className={'recent-avatar ' + (s.gender === 'Male' ? 'male' : 'female')}><i className={'fas ' + (s.gender === 'Male' ? 'fa-male' : 'fa-female')} /></div>
                <div style={{ flex: 1 }}><div className="recent-name">{s.full_name}</div><div className="recent-id">{s.student_id}</div></div>
                <i className="fas fa-chevron-right text-muted" />
              </a>
            )) : <Empty icon="fa-users">No students yet</Empty>}
          </Widget>

          {(d.recent_activity || []).length > 0 && (
            <Widget icon="fa-clipboard-list" title="Recent activity"
                    action={<a href={urls.audit_log} className="btn btn-secondary btn-sm">Log</a>}>
              {d.recent_activity.map((a, i) => (
                <div className="act-item" key={i}>
                  <span className="badge badge-primary">{a.action}</span>
                  <div><div>{a.detail || ''}</div><div className="text-muted" style={{ fontSize: '.7rem' }}>{a.user} · {a.created_at}</div></div>
                </div>
              ))}
            </Widget>
          )}
        </div>
      )}

      {/* Quick actions */}
      <Widget icon="fa-bolt" title="Quick actions">
        <div className="quick-actions">
          <a href={urls.add_student} className="btn btn-primary"><i className="fas fa-user-plus" /> Add Student</a>
          <a href={urls.mark_attendance} className="btn btn-success"><i className="fas fa-clipboard-check" /> Mark Attendance</a>
          <a href={urls.scores_entry} className="btn btn-info"><i className="fas fa-edit" /> Enter Scores</a>
          <a href={urls.scan_waec} className="btn btn-secondary"><i className="fas fa-camera" /> Scan Result</a>
          <a href={urls.analytics_hub} className="btn btn-outline"><i className="fas fa-chart-pie" /> Analytics</a>
          <a href={urls.readiness} className="btn btn-outline"><i className="fas fa-clipboard-check" /> Readiness</a>
        </div>
      </Widget>
    </>
  );
}

function ExamCard({ kind, snap, url }) {
  return (
    <div className={'exam-card ' + kind}>
      <div className="top">
        <span><i className={'fas ' + ICON[kind]} /> {kind === 'jamb' ? 'JAMB' : kind === 'waec' ? 'WAEC' : 'Latest Mock'} {snap && kind !== 'mock' ? snap.year : ''}</span>
        {(snap || kind === 'mock') && <a href={url} style={{ color: '#fff', opacity: .85 }}><i className="fas fa-arrow-right" /></a>}
      </div>
      {!snap ? (
        <><div className="big">—</div><div className="sub">{kind === 'jamb' ? 'No JAMB results yet' : kind === 'waec' ? 'No WAEC results yet' : 'No mock exams yet'}</div></>
      ) : kind === 'jamb' ? (
        <>
          <div><div className="big">{snap.mean}</div><div className="sub">mean across {snap.count} candidates</div></div>
          <div className="chips"><span className="chip">Top {snap.max}</span><span className="chip">≥200: {snap.above_200} ({snap.above_200_pct}%)</span></div>
        </>
      ) : kind === 'waec' ? (
        <>
          <div><div className="big">{snap.pass_rate}%</div><div className="sub">credit pass rate</div></div>
          <div className="chips"><span className="chip">{snap.students} students</span><span className="chip">{snap.entries} entries</span></div>
        </>
      ) : (
        <>
          <div><div className="big">{snap.mean}</div><div className="sub">{snap.name} · {snap.count} sat</div></div>
          <div className="chips"><span className="chip">Top {snap.max}</span></div>
        </>
      )}
    </div>
  );
}
