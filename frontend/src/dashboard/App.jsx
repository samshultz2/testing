import React, { useState, useEffect } from 'react';
import Chart, { chartTheme } from './charts';
import { Kpi, KpiCard, Widget, Empty, ChartBox, naira, nairaShort } from './components';
import Customize from './Customize';
import { apiGet, apiPost, csrfToken } from '../lib/api';
import { chartPalette } from '../lib/hooks';
import { Toast, SetupChecklist } from '../components/ui';

const ICON = { jamb: 'fa-file-contract', waec: 'fa-file-alt', mock: 'fa-clipboard-list' };

// Reorderable/favouritable blocks — labels + icons for the block toolbar.
const BLOCK_META = {
  exec_summary: { label: 'Executive summary', icon: 'fa-gauge-high' },
  insights: { label: 'Needs attention', icon: 'fa-bell' },
  branches: { label: 'Branch performance', icon: 'fa-code-branch' },
  kpi: { label: 'Student KPIs', icon: 'fa-users' },
  academic: { label: 'Academic performance', icon: 'fa-graduation-cap' },
  timetable: { label: "Today's schedule", icon: 'fa-calendar-day' },
  finance_health: { label: 'Finance health', icon: 'fa-coins' },
  crossmodule: { label: 'Module KPIs', icon: 'fa-layer-group' },
  exams: { label: 'Exam snapshots', icon: 'fa-file-contract' },
  charts: { label: 'Demographics', icon: 'fa-chart-pie' },
  attendance_trend: { label: 'Attendance trend', icon: 'fa-chart-line' },
  class_religion: { label: 'Class & religion', icon: 'fa-school' },
  people: { label: 'People', icon: 'fa-user-clock' },
};
const FALLBACK_ORDER = ['exec_summary', 'insights', 'branches', 'kpi', 'academic',
  'timetable', 'finance_health', 'crossmodule', 'exams', 'charts', 'attendance_trend', 'class_religion', 'people'];

// Today's attendance vs the term average → a trend chip. Only shown once there's
// a term baseline and today has been marked, so it never reads a misleading 0.
function attendanceDelta(stats) {
  const s = stats || {};
  const today = Number(s.today_percentage) || 0;
  const term = Number(s.term_average) || 0;
  if (!today || !term) return undefined;
  const diff = Math.round((today - term) * 10) / 10;
  if (diff === 0) return { dir: 'flat', text: 'level with term avg' };
  return { dir: diff > 0 ? 'up' : 'down', text: `${diff > 0 ? '+' : ''}${diff} pp vs term` };
}

// Staff-attendance chip for the HR widget: only once someone's marked today, so
// an unmarked morning stays quiet instead of falsely reading "all present".
function hrAttendanceDelta(hr) {
  const att = (hr && hr.att) || {};
  if (!att.marked) return undefined;
  return att.absent
    ? { dir: 'down', text: `${att.absent} absent today` }
    : { dir: 'up', text: 'all present today' };
}

export default function App({ data: initialData }) {
  const [data, setData] = useState(initialData);
  const [toast, setToast] = useState(null);   // surface a refresh failure instead of silently keeping stale data
  const d = data || {};
  const enabled = d.enabled || [];
  const has = (k) => enabled.includes(k);
  const urls = d.urls || {};
  const t = chartTheme();
  const [customizing, setCustomizing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(() => new Date());
  const [ackedIds, setAckedIds] = useState(new Set());
  const ackAnn = async (a) => {
    try {
      await fetch(a.ack_url, { method: 'POST', credentials: 'same-origin',
        headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrfToken() } });
      setAckedIds((s) => new Set(s).add(a.id));
    } catch (_) { /* ignore */ }
  };

  // Re-fetch widget data in place — after customising or on demand — with a
  // visible loading state, so leaders can pull fresh numbers without a full
  // page reload. Cached metrics (defaulters, branch comparison) refresh on
  // their own TTL; everything else is recomputed live.
  const refresh = async () => {
    setRefreshing(true);
    try { setData(await apiGet('/api/dashboard/data')); setUpdatedAt(new Date()); }
    catch (e) { setToast({ tone: 'warn', text: 'Couldn’t refresh the dashboard — showing the last loaded data.' }); }
    finally { setRefreshing(false); }
  };
  const updatedLabel = updatedAt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

  // ── Personalization: block order, favourites, arrange mode, per-block refresh.
  const [arranging, setArranging] = useState(false);
  const [order, setOrder] = useState(() => ((d.layout && d.layout.order) || FALLBACK_ORDER).slice());
  const [favorites, setFavorites] = useState(() => ((d.layout && d.layout.favorites) || []).slice());
  const [hoveredBlock, setHoveredBlock] = useState(null);
  const [blockBusy, setBlockBusy] = useState({});
  const [dragId, setDragId] = useState(null);
  const [overId, setOverId] = useState(null);

  // Keep the dashboard "alive": quietly re-fetch the numbers on an interval so
  // the headline KPIs and widgets stay current without a manual refresh. Paused
  // while arranging/customising (don't clobber in-progress edits) and while the
  // tab is hidden (no background polling). The animated counters/sparklines make
  // the update read as live movement, not a jarring jump.
  useEffect(() => {
    const timer = setInterval(async () => {
      if (document.hidden || arranging || customizing) return;
      try { setData(await apiGet('/api/dashboard/data')); setUpdatedAt(new Date()); }
      catch (_e) { /* keep the last data silently on a transient failure */ }
    }, 60000);
    return () => clearInterval(timer);
  }, [arranging, customizing]);

  // Persist a layout patch (order and/or favourites). Best-effort — a failed
  // save surfaces a toast but the optimistic UI state stays.
  const persist = (patch) => {
    apiPost(urls.save_layout, patch).catch(() =>
      setToast({ tone: 'warn', text: 'Couldn’t save your dashboard layout.' }));
  };
  const moveBlock = (from, to) => {
    if (!from || from === to) return;
    setOrder((prev) => {
      const next = prev.filter((x) => x !== from);
      const idx = next.indexOf(to);
      if (idx === -1) next.push(from); else next.splice(idx, 0, from);
      persist({ order: next });
      return next;
    });
  };
  const toggleFav = (id) => {
    setFavorites((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      persist({ favorites: next });
      return next;
    });
  };
  // True per-widget refresh: fetch only this block's slice and merge it in.
  const refreshBlock = async (id) => {
    if (!urls.widget_data) return;
    setBlockBusy((b) => ({ ...b, [id]: true }));
    try {
      const slice = await apiGet(urls.widget_data.replace('__BLOCK__', id));
      setData((prev) => ({ ...prev, ...slice }));
    } catch (e) {
      setToast({ tone: 'warn', text: 'Couldn’t refresh that widget.' });
    } finally {
      setBlockBusy((b) => ({ ...b, [id]: false }));
    }
  };
  const drag = {
    overId,
    onStart: (e, id) => { setDragId(id); e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setData('text/plain', id); } catch (_) { /* IE */ } },
    onOver: (e, id) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (id !== overId) setOverId(id); },
    onDrop: (e, id) => { e.preventDefault(); moveBlock(dragId, id); setDragId(null); setOverId(null); },
    onEnd: () => { setDragId(null); setOverId(null); },
  };

  const doughnut = (extra) => ({
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
    cutout: '62%', ...extra,
  });
  const barOpts = {
    responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true, ticks: { stepSize: 1, precision: 0 }, grid: { color: t.grid } }, x: { grid: { display: false } } },
  };

  const tc = d.teacher_classes;
  // Fresh school: no students yet on a management dashboard → show a friendly
  // "get started" checklist instead of a wall of zero KPIs and empty charts.
  const emptySchool = has('kpi') && (d.total_students || 0) === 0 && (tc === null || tc === undefined);
  const setupSteps = [
    { label: 'Create your classes', hint: 'Set up the classes and arms students will belong to', href: urls.classes_list },
    { label: 'Add your first student', hint: 'Register a student to start building your roll', href: urls.add_student },
    { label: 'Record attendance', hint: 'Mark a class present for the day', href: urls.mark_attendance },
    { label: 'Enter scores', hint: 'Capture assessment results for a subject', href: urls.scores_entry },
  ].filter((s) => s.href);

  const crossModule = d.finance_stat || d.sales_stat || d.hr_stat || d.cbt_stat || d.library_stat;
  const dateLabel = d.today ? new Date(d.today).toLocaleDateString(undefined,
    { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }) : '';

  // Which blocks should render, given permissions/data (permission scoping is
  // enforced server-side via `enabled`; these are the client-side data gates).
  const visible = (id) => {
    switch (id) {
      case 'exec_summary': return has('exec_summary') && (d.exec_summary || []).length > 0 && !emptySchool;
      case 'insights': return has('insights') && !emptySchool;
      case 'branches': return has('branches') && (d.branch_comparison || []).length > 1;
      case 'kpi': return has('kpi') && !emptySchool;
      case 'academic': return has('academic') && !!d.academic && !emptySchool;
      case 'timetable': return has('timetable') && !!d.timetable_today && (d.timetable_today.slots || []).length > 0 && !emptySchool;
      case 'finance_health': return has('finance_health') && !!d.finance_health && !emptySchool;
      case 'crossmodule': return !!crossModule;
      case 'exams': return has('exams') && !emptySchool;
      case 'charts': return has('charts') && !emptySchool;
      case 'attendance_trend': return has('attendance_trend') && !emptySchool;
      case 'class_religion': return has('class_religion') && !emptySchool;
      case 'people': return has('people') && !emptySchool;
      default: return false;
    }
  };

  // Each block's content (the existing sections, now data-driven and orderable).
  const blockNodes = {
    exec_summary: <ExecSummary tiles={d.exec_summary || []} />,
    insights: <Insights items={d.insights || []} />,
    branches: <BranchComparison rows={d.branch_comparison || []} />,
    kpi: (() => {
      const hk = d.headline_kpis || {};
      return (
        <div className="kpi-row">
          <KpiCard tone="blue" icon="fa-users" value={d.total_students} label="Students"
                   sub="Total registered students"
                   delta={(hk.students || {}).delta} deltaLabel={(hk.students || {}).delta_label}
                   series={(hk.students || {}).series} />
          <KpiCard tone="green" icon="fa-user-check" value={d.active_enrollments} label="Enrolled"
                   sub="Active students"
                   delta={(hk.enrolled || {}).delta} deltaLabel={(hk.enrolled || {}).delta_label}
                   series={(hk.enrolled || {}).series} />
          <KpiCard tone="orange" icon="fa-percent" value={(d.attendance_stats || {}).today_percentage + '%'}
                   label="Attendance Today" sub="Average attendance"
                   delta={(hk.attendance || {}).delta} deltaLabel={(hk.attendance || {}).delta_label}
                   series={(hk.attendance || {}).series} />
          <KpiCard tone="purple" icon="fa-user-graduate" value={d.graduates_count} label="Graduates"
                   sub="This session"
                   delta={(hk.graduates || {}).delta} deltaLabel={(hk.graduates || {}).delta_label}
                   series={(hk.graduates || {}).series} />
        </div>
      );
    })(),
    academic: <AcademicPerformance a={d.academic} urls={urls} t={t} />,
    timetable: <TodaySchedule data={d.timetable_today} urls={urls} teacher={!!d.teacher_classes} />,
    finance_health: <FinanceHealth f={d.finance_health} urls={urls} t={t} />,
    crossmodule: (
      <div className="kpi-row">
        {d.finance_stat && <>
          <Kpi tone="green" icon="fa-coins" value={nairaShort(d.finance_stat.collected)} title={naira(d.finance_stat.collected)} label="Fees collected (term)"
               delta={d.finance_stat.collected_today > 0 ? { dir: 'up', text: `${nairaShort(d.finance_stat.collected_today)} today` } : undefined} />
          <Kpi tone="teal" icon="fa-scale-balanced" value={nairaShort(d.finance_stat.net)} title={naira(d.finance_stat.net)} label="Net (term)"
               delta={{ dir: d.finance_stat.net >= 0 ? 'up' : 'down', text: d.finance_stat.net >= 0 ? 'in surplus' : 'in deficit' }} />
        </>}
        {d.sales_stat && <Kpi tone="blue" icon="fa-cash-register" value={nairaShort(d.sales_stat.today)} title={naira(d.sales_stat.today)} label={`Sales today (${d.sales_stat.count_today})`} />}
        {d.hr_stat && <Kpi tone="purple" icon="fa-id-badge" value={d.hr_stat.total} label={`Staff (${d.hr_stat.teaching} teaching)`}
             delta={hrAttendanceDelta(d.hr_stat)} />}
        {d.cbt_stat && <Kpi tone="blue" icon="fa-laptop-code" value={d.cbt_stat.published} label={`CBT exams · ${d.cbt_stat.attempts} attempts`} />}
        {d.library_stat && <Kpi tone="teal" icon="fa-book" value={d.library_stat.books} label={`Books · ${d.library_stat.on_loan} on loan`} />}
      </div>
    ),
    exams: (
      <div className="dash-grid c3">
        <ExamCard kind="jamb" snap={d.jamb_snapshot} url={urls.jamb_list} />
        <ExamCard kind="waec" snap={d.waec_snapshot} url={urls.waec_list} />
        <ExamCard kind="mock" snap={d.mock_snapshot} url={urls.mock_index} />
      </div>
    ),
    charts: (
      <div className="dash-grid c3">
        <Widget icon="fa-venus-mars" title="Gender">
          <ChartBox>
            <Chart type="doughnut" options={doughnut()} ariaLabel={`Gender split: ${d.male_students || 0} male, ${d.female_students || 0} female`} data={{ labels: ['Male', 'Female'],
              datasets: [{ data: [d.male_students, d.female_students], backgroundColor: [chartPalette().male, chartPalette().female], borderWidth: 0 }] }} />
          </ChartBox>
        </Widget>
        <Widget icon="fa-route" title="Streams">
          <ChartBox>
            <Chart type="doughnut" options={doughnut()} ariaLabel={'Students by stream: ' + (Object.entries(d.stream_dist || {}).map(([k, v]) => `${k} ${v}`).join(', ') || 'no data')} data={{ labels: Object.keys(d.stream_dist || {}),
              datasets: [{ data: Object.values(d.stream_dist || {}), backgroundColor: chartPalette().categorical, borderWidth: 0 }] }} />
          </ChartBox>
        </Widget>
        <Widget icon="fa-birthday-cake" title="Age groups">
          <ChartBox>
            <Chart type="bar" options={barOpts} ariaLabel={'Students by age group: ' + ['0-10', '11-13', '14-16', '17-19', '20+'].map((k) => `${k}: ${(d.age_distribution || {})[k] || 0}`).join(', ')} data={{ labels: ['0-10', '11-13', '14-16', '17-19', '20+'],
              datasets: [{ data: ['0-10', '11-13', '14-16', '17-19', '20+'].map((k) => (d.age_distribution || {})[k] || 0), backgroundColor: chartPalette().indigo, borderRadius: 6 }] }} />
          </ChartBox>
        </Widget>
      </div>
    ),
    attendance_trend: (
      <div className="dash-grid split">
        <Widget icon="fa-chart-line" title="Attendance trend"
                action={<a href={urls.weekly_summary} className="btn btn-secondary btn-sm">Details</a>}>
          <ChartBox>
            {(d.attendance_trend || []).length ? (
              <Chart type="line"
                ariaLabel={'Attendance trend by week: ' + d.attendance_trend.map((x) => `${x.label} ${x.pct}%`).join(', ')}
                options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, max: 100, grid: { color: t.grid } }, x: { grid: { display: false } } } }}
                data={{ labels: d.attendance_trend.map((x) => x.label),
                  datasets: [{ data: d.attendance_trend.map((x) => x.pct), borderColor: chartPalette().green, backgroundColor: chartPalette().fill, fill: true, tension: .35, pointRadius: 4, pointBackgroundColor: chartPalette().green, borderWidth: 3 }] }} />
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
    ),
    class_religion: (
      <div className="dash-grid split">
        <Widget icon="fa-school" title="Class enrollment"
                action={<a href={urls.classes_list} className="btn btn-secondary btn-sm">Manage</a>}>
          <ChartBox height="240px">
            {(d.class_stats || []).length ? (
              <Chart type="bar"
                ariaLabel={'Class enrollment by gender: ' + d.class_stats.map((c) => `${c.name} ${c.total}`).join(', ')}
                options={{ responsive: true, maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
                scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, grid: { color: t.grid } } } }}
                data={{ labels: d.class_stats.map((c) => c.name), datasets: [
                  { label: 'Male', data: d.class_stats.map((c) => c.male), backgroundColor: chartPalette().male, borderRadius: 4 },
                  { label: 'Female', data: d.class_stats.map((c) => c.female), backgroundColor: chartPalette().female, borderRadius: 4 }] }} />
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
          ) : <Empty icon="fa-pray">No religion recorded yet — it’ll appear here as you add students</Empty>}
        </Widget>
      </div>
    ),
    people: (
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
              <div className={'recent-avatar ' + (s.gender === 'Male' ? 'male' : 'female')}><i aria-hidden="true" className={'fas ' + (s.gender === 'Male' ? 'fa-male' : 'fa-female')} /></div>
              <div style={{ flex: 1 }}><div className="recent-name">{s.full_name}</div><div className="recent-id">{s.student_id}</div></div>
              <i aria-hidden="true" className="fas fa-chevron-right text-muted" />
            </a>
          )) : <Empty icon="fa-users">No students yet</Empty>}
        </Widget>

        {(d.recent_activity || []).length > 0 && (
          <Widget icon="fa-clipboard-list" title="Recent activity"
                  action={<a href={urls.audit_log} className="btn btn-secondary btn-sm">Log</a>}>
            {d.recent_activity.map((a, i) => (
              <div className="act-item" key={i}>
                <span className="badge badge-primary">{a.action}</span>
                <div><div>{a.detail || ''}</div><div className="text-muted" style={{ fontSize: 'var(--text-xs)' }}>{a.user} · {a.created_at}</div></div>
              </div>
            ))}
          </Widget>
        )}
      </div>
    ),
  };

  // Final render order: favourites first (preserving order), then the rest.
  const visibleIds = order.filter(visible);
  const favSet = new Set(favorites);
  const orderedIds = [...visibleIds.filter((id) => favSet.has(id)),
                      ...visibleIds.filter((id) => !favSet.has(id))];

  return (
    <>
      {toast && <Toast tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}
      {/* Hero */}
      <div className="dash-hero">
        <div className="dash-hero-main">
          <div className="dash-hero-eyebrow">Good to see you again,</div>
          <h1>{d.user_name || 'there'} <span className="dash-wave" aria-hidden="true">👋</span></h1>
          <p>{dateLabel}{d.active_session ? ' · ' + d.active_session.name : ''}</p>
          <div className="dash-hero-actions">
            {d.active_term && <span className="term-pill"><i aria-hidden="true" className="fas fa-calendar-day" /> {d.active_term.name}</span>}
            <button type="button" onClick={refresh} disabled={refreshing} className="hero-btn"
                    title={'Refresh dashboard — last updated ' + updatedLabel} aria-label={'Refresh dashboard, last updated ' + updatedLabel}>
              <i aria-hidden="true" className={'fas fa-rotate' + (refreshing ? ' fa-spin' : '')} /> {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
            {!emptySchool && <button type="button" onClick={() => setArranging((v) => !v)}
                    className={'hero-btn' + (arranging ? ' active' : '')}
                    aria-pressed={arranging} title="Drag to reorder & pin favourite widgets">
              <i aria-hidden="true" className="fas fa-up-down-left-right" /> {arranging ? 'Done' : 'Arrange'}
            </button>}
            <button type="button" onClick={() => setCustomizing(true)} className="hero-btn" title="Choose widgets">
              <i aria-hidden="true" className="fas fa-sliders" /> Customize
            </button>
          </div>
        </div>
        <SchoolArt />
        <span className="dash-hero-dots" aria-hidden="true" />
      </div>
      <div aria-live="polite" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap' }}>
        {refreshing ? 'Refreshing dashboard' : 'Dashboard updated ' + updatedLabel}
      </div>

      {customizing && <Customize catalog={d.widget_catalog} onSaved={refresh} onClose={() => setCustomizing(false)} />}

      {/* First-run: fresh school gets a guided checklist, not a wall of zeros */}
      {emptySchool && <SetupChecklist steps={setupSteps} />}

      {/* Role-aware landing: a finance-only staffer (bursar) gets a finance-first
          home with a direct shortcut into their workspace. */}
      {d.home_focus === 'finance' && (
        <a className="focus-hero keep-on-readonly" href={urls.finance_overview}>
          <span className="fh-ic" aria-hidden="true"><i className="fas fa-coins" /></span>
          <span className="fh-body">
            <strong>Open the Finance workspace</strong>
            <span>Record payments, track collections, expenses and defaulters</span>
          </span>
          <i aria-hidden="true" className="fas fa-arrow-right fh-go" />
        </a>
      )}

      {/* Teacher: My Classes */}
      {tc !== null && tc !== undefined && (
        <div className="card">
          <div className="card-header">
            <h3><i aria-hidden="true" className="fas fa-chalkboard-teacher" /> My Classes</h3>
            <a href={urls.week_grid} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-calendar-week" /> Mark a week</a>
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
                      <a href={c.mark_url} className="btn btn-primary btn-sm" style={{ flex: 1 }}><i aria-hidden="true" className="fas fa-clipboard-check" /> Attendance</a>
                      <a href={c.week_url} className="btn btn-secondary btn-sm" style={{ flex: 1 }}><i aria-hidden="true" className="fas fa-calendar-week" /> Week</a>
                      {d.can_results && <a href={urls.bulk_entry} className="btn btn-secondary btn-sm" style={{ flex: 1 }}><i aria-hidden="true" className="fas fa-pen" /> Scores</a>}
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
            const color = a.category === 'Important' ? 'var(--danger)' : a.category === 'Event' ? 'var(--warning)' : 'var(--primary)';
            const icon = a.category === 'Important' ? 'fa-triangle-exclamation' : a.category === 'Event' ? 'fa-calendar-day' : 'fa-bullhorn';
            return (
              <div key={i} style={{ display: 'flex', gap: '.6rem', alignItems: 'flex-start', background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderLeft: '4px solid ' + color, borderRadius: 'var(--radius-md)', padding: '.7rem .9rem' }}>
                <i aria-hidden="true" className={'fas ' + icon} style={{ color, marginTop: '.2rem' }} />
                <div style={{ flex: 1 }}><strong>{a.title}</strong>{a.body && <div className="text-muted text-sm">{a.body}</div>}
                  {a.attachment && <div style={{ marginTop: '.3rem' }}><a href={a.attachment.url} className="text-sm"><i aria-hidden="true" className="fas fa-paperclip" /> {a.attachment.name}</a></div>}
                  {a.needs_ack && ((a.acked || ackedIds.has(a.id))
                    ? <div className="text-sm" style={{ color: 'var(--success)', marginTop: '.35rem' }}><i aria-hidden="true" className="fas fa-circle-check" /> Acknowledged</div>
                    : <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: '.4rem' }} onClick={() => ackAnn(a)}><i aria-hidden="true" className="fas fa-check" /> Acknowledge</button>)}
                </div>
                {a.is_pinned && <i aria-hidden="true" className="fas fa-thumbtack text-muted" title="Pinned" />}
              </div>
            );
          })}
        </div>
      )}

      {/* Arrange hint bar */}
      {arranging && !emptySchool && (
        <div className="alert alert-info" role="status" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <span><i aria-hidden="true" className="fas fa-circle-info" /> Drag widgets to reorder, and use the ★ to pin favourites to the top. Changes save automatically.</span>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setArranging(false)}>Done</button>
        </div>
      )}

      {/* Reorderable / favouritable / individually-refreshable widget blocks.
          Permission scoping is enforced server-side (via `enabled` and the
          per-widget endpoint); the render just honours the user's order. */}
      {orderedIds.map((id) => (
        <DashBlock key={id} id={id} meta={BLOCK_META[id]} arranging={arranging}
                   favorite={favSet.has(id)} busy={!!blockBusy[id]}
                   hovered={hoveredBlock === id} onHover={setHoveredBlock}
                   onToggleFav={() => toggleFav(id)} onRefresh={() => refreshBlock(id)}
                   drag={drag}>
          {blockNodes[id]}
        </DashBlock>
      ))}

      {/* Quick actions — permission-aware (server filters to actions this role
          can actually perform), so no role sees a button that 403s on click. */}
      {(d.quick_actions || []).length > 0 && (
        <Widget icon="fa-bolt" title="Quick actions">
          <div className="quick-actions">
            {d.quick_actions.map((a, i) => (
              // keep-on-readonly: these are already permission-filtered server-side,
              // so the blunt client read-only sweep must not strip them (the dashboard
              // landing is itself a non-writable page, which marks it data-readonly).
              <a key={i} href={a.url} className={'btn keep-on-readonly ' + (a.tone || 'btn-secondary')}>
                <i aria-hidden="true" className={'fas ' + a.icon} /> {a.label}
              </a>
            ))}
          </div>
        </Widget>
      )}
    </>
  );
}

const TOOL_BTN = { background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px', lineHeight: 1, fontSize: '.8rem' };

// Wraps a dashboard block with a floating toolbar (favourite ★, per-widget
// refresh, and — in Arrange mode — a drag handle) that straddles the block's
// top border so it never overlaps in-content action buttons. Favourited blocks
// keep their toolbar visible as a persistent marker.
function DashBlock({ id, meta, arranging, favorite, busy, hovered, onHover, onToggleFav, onRefresh, drag, children }) {
  const show = hovered || arranging || favorite;
  const isDropTarget = arranging && drag.overId === id;
  return (
    <div className="dash-block"
         style={{ position: 'relative', marginBottom: '1.1rem', borderRadius: 'var(--radius-md)',
                  outline: isDropTarget ? '2px dashed var(--primary)' : arranging ? '1px dashed var(--border-color)' : 'none',
                  outlineOffset: 4, cursor: arranging ? 'grab' : 'default' }}
         draggable={arranging}
         onDragStart={arranging ? (e) => drag.onStart(e, id) : undefined}
         onDragOver={arranging ? (e) => drag.onOver(e, id) : undefined}
         onDrop={arranging ? (e) => drag.onDrop(e, id) : undefined}
         onDragEnd={arranging ? drag.onEnd : undefined}
         onMouseEnter={() => onHover(id)} onMouseLeave={() => onHover(null)}>
      <div style={{ position: 'absolute', top: 0, right: 16, transform: 'translateY(-50%)', zIndex: 6,
                    display: 'flex', gap: 2, alignItems: 'center', background: 'var(--bg-card)',
                    border: '1px solid var(--border-color)', borderRadius: 999, padding: '1px 4px',
                    boxShadow: 'var(--shadow-sm)', opacity: show ? 1 : 0,
                    pointerEvents: show ? 'auto' : 'none', transition: 'opacity .15s' }}>
        {arranging && <span aria-hidden="true" title="Drag to reorder" style={{ color: 'var(--text-muted)', padding: '0 2px', cursor: 'grab' }}><i className="fas fa-grip-vertical" /></span>}
        <button type="button" style={TOOL_BTN} onClick={onToggleFav} aria-pressed={favorite}
                title={favorite ? 'Unpin favourite' : 'Pin as favourite'}
                aria-label={(favorite ? 'Unpin ' : 'Pin ') + (meta ? meta.label : 'widget') + ' as favourite'}>
          <i className={'fa-star ' + (favorite ? 'fas' : 'far')} style={{ color: favorite ? 'var(--accent)' : 'var(--text-muted)' }} aria-hidden="true" />
        </button>
        <button type="button" style={TOOL_BTN} onClick={onRefresh} disabled={busy}
                title={'Refresh ' + (meta ? meta.label : 'widget')} aria-label={'Refresh ' + (meta ? meta.label : 'widget')}>
          <i className={'fas fa-rotate' + (busy ? ' fa-spin' : '')} style={{ color: 'var(--text-muted)' }} aria-hidden="true" />
        </button>
      </div>
      {children}
    </div>
  );
}

const SEV = {
  high: { color: 'var(--danger)', label: 'Urgent' },
  medium: { color: 'var(--warning)', label: 'Soon' },
  low: { color: 'var(--info)', label: 'FYI' },
};

// The Needs-Attention panel: a prioritized, deep-linked action list. Items are
// already sorted + permission-filtered server-side; an empty list reads as a
// reassuring "all clear" rather than disappearing silently.
function Insights({ items }) {
  if (!items.length) {
    return (
      <div className="card insights-card" style={{ marginBottom: '1.1rem' }}>
        <div className="card-body" style={{ display: 'flex', alignItems: 'center', gap: '.6rem' }}>
          <i aria-hidden="true" className="fas fa-circle-check" style={{ color: 'var(--success)', fontSize: '1.2rem' }} />
          <div><strong>All clear</strong><div className="text-muted text-sm">Nothing needs your attention right now.</div></div>
        </div>
      </div>
    );
  }
  return (
    <div className="card insights-card" style={{ marginBottom: '1.1rem' }}>
      <div className="card-header">
        <h3><i aria-hidden="true" className="fas fa-bell" /> Needs attention <span className="badge badge-danger" style={{ marginLeft: 6 }}>{items.length}</span></h3>
      </div>
      <ul className="card-body" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column' }}>
        {items.map((it) => {
          const sev = SEV[it.severity] || SEV.low;
          // The whole row deep-links to the resolving module. An optional action
          // (e.g. "Send reminder") is a sibling button — not nested in the row's
          // <a> — so it can navigate somewhere else without invalid nested links.
          return (
            <li key={it.key} className="insight-row"
                style={{ display: 'flex', alignItems: 'center', gap: '.7rem', padding: '.65rem .9rem',
                         borderLeft: '4px solid ' + sev.color,
                         borderBottom: '1px solid var(--border-color)' }}>
              <a href={it.url}
                 style={{ display: 'flex', alignItems: 'center', gap: '.7rem', flex: 1,
                          textDecoration: 'none', color: 'inherit', minWidth: 0 }}>
                <i aria-hidden="true" className={'fas ' + it.icon} style={{ color: sev.color, width: 18, textAlign: 'center' }} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <strong>{it.title}</strong>
                  {it.detail && <div className="text-muted text-sm">{it.detail}</div>}
                </span>
                <span className="badge" style={{ background: `color-mix(in srgb, ${sev.color} 15%, transparent)`, color: sev.color, fontWeight: 600 }}>{sev.label}</span>
              </a>
              {it.action ? (
                <a href={it.action.url} className="btn btn-sm btn-outline"
                   style={{ whiteSpace: 'nowrap', flexShrink: 0 }}>
                  {it.action.icon && <i aria-hidden="true" className={'fas ' + it.action.icon} />} {it.action.label}
                </a>
              ) : (
                <i aria-hidden="true" className="fas fa-chevron-right text-muted" />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// Branch scorecard for central users: compares students, term attendance and
// term fees across branches, with an inline bar so the leading branch is
// obvious at a glance. Sorted by student headcount.
function BranchComparison({ rows }) {
  const sorted = [...rows].sort((a, b) => b.students - a.students);
  const maxStudents = Math.max(1, ...sorted.map((r) => r.students));
  const maxFees = Math.max(1, ...sorted.map((r) => r.fees));
  const best = sorted.reduce((m, r) => (r.attendance > (m ? m.attendance : -1) ? r : m), null);
  return (
    <div className="widget" style={{ marginBottom: '1.1rem' }}>
      <div className="wh">
        <h3><i className="fas fa-code-branch" aria-hidden="true" /> Branch performance</h3>
      </div>
      <div className="wb" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="data-table" style={{ margin: 0 }}>
          <thead>
            <tr><th>Branch</th><th>Students</th><th>Attendance</th><th style={{ textAlign: 'right' }}>Fees (term)</th></tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.name}</strong>
                  {best && r.id === best.id && best.attendance > 0 &&
                    <span className="badge badge-success" style={{ marginLeft: 6 }} title="Highest attendance">Top attendance</span>}
                </td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ minWidth: 34 }}>{r.students}</span>
                    <span aria-hidden="true" style={{ flex: 1, minWidth: 40, height: 6, background: 'var(--border-color)', borderRadius: 3, overflow: 'hidden' }}>
                      <span style={{ display: 'block', height: '100%', width: (r.students / maxStudents * 100) + '%', background: 'var(--info)' }} />
                    </span>
                  </div>
                </td>
                <td><span className={'badge ' + (r.attendance >= 75 ? 'badge-success' : r.attendance > 0 ? 'badge-warning' : 'badge-secondary')}>{r.attendance ? r.attendance + '%' : '—'}</span></td>
                <td style={{ textAlign: 'right' }} title={naira(r.fees)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                    <span aria-hidden="true" style={{ width: 48, height: 6, background: 'var(--border-color)', borderRadius: 3, overflow: 'hidden' }}>
                      <span style={{ display: 'block', height: '100%', width: (r.fees / maxFees * 100) + '%', background: 'var(--primary)', float: 'right' }} />
                    </span>
                    <span>{nairaShort(r.fees)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Shared performance-colour helpers: green ≥70, amber ≥50, red below — the
// traffic-light an educator/bursar reads at a glance.
const RECO_TONE = { positive: 'var(--success)', negative: 'var(--danger)', warning: 'var(--warning)', insight: 'var(--info)' };
const rateColor = (v) => (v >= 70 ? '#16a34a' : v >= 50 ? '#d97706' : '#dc2626');
const rateTone = (v) => (v >= 70 ? 'green' : v >= 50 ? 'amber' : 'red');

function RecoList({ items }) {
  if (!items || !items.length) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem', marginTop: '.7rem' }}>
      {items.map((r, i) => (
        <div key={i} style={{ borderLeft: '3px solid ' + (RECO_TONE[r.tone] || 'var(--info)'), padding: '.25rem 0 .3rem .6rem' }}>
          <div style={{ fontWeight: 700, fontSize: '.82rem' }}>{r.title}</div>
          <div className="text-muted" style={{ fontSize: '.78rem', lineHeight: 1.4 }}>{r.text}</div>
        </div>
      ))}
    </div>
  );
}

// Historically-challenging subjects: those below a healthy pass rate averaged
// across the session's terms — a chronic weakness (e.g. Maths/Physics) worth
// steering before external exams, not a one-term dip. A tiny sparkline of
// per-term pass rates shows the trajectory at a glance.
function ChronicSubjects({ rows, urls }) {
  if (!rows || !rows.length) return null;
  return (
    <div style={{ marginTop: '.8rem', borderTop: '1px dashed var(--border-color)', paddingTop: '.6rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: '.45rem' }}>
        <i aria-hidden="true" className="fas fa-clock-rotate-left text-muted" />
        <strong style={{ fontSize: '.82rem' }}>Historically challenging</strong>
        <span className="text-muted" style={{ fontSize: '.72rem' }}>avg pass across the session</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '.35rem' }}>
        {rows.map((x) => (
          <div key={x.name} style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
            <span style={{ flex: 1, fontSize: '.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{x.name}</span>
            <Sparkline values={x.spark} />
            <span style={{ fontSize: '.72rem' }} className="text-muted">{x.terms} terms</span>
            <span style={{ minWidth: 42, textAlign: 'right', fontWeight: 700, color: rateColor(x.mean_pass) }}>{x.mean_pass}%</span>
          </div>
        ))}
      </div>
      {urls && urls.institution_analytics && (
        <a href={urls.institution_analytics} className="text-muted"
           style={{ display: 'inline-block', marginTop: '.4rem', fontSize: '.74rem' }}>
          Full subject analytics →
        </a>
      )}
    </div>
  );
}

// A minimal inline bar sparkline (no chart library) for per-term pass rates.
function Sparkline({ values }) {
  const vals = (values || []).map((v) => Math.max(0, Math.min(100, Number(v) || 0)));
  if (!vals.length) return null;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'flex-end', gap: 2, height: 18 }}
          aria-label={'Per-term pass rate: ' + vals.map((v) => v + '%').join(', ')}>
      {vals.map((v, i) => (
        <span key={i} title={v + '%'} style={{ width: 5, height: Math.max(2, Math.round(v / 100 * 18)),
                    background: rateColor(v), borderRadius: 1, display: 'inline-block' }} />
      ))}
    </span>
  );
}

// Today's schedule glance: the period in session right now (with how many
// classes are running), what's up next, and the full day's period ladder with
// the live period highlighted. Teacher-scoped users see their own lessons.
function TodaySchedule({ data, urls, teacher }) {
  const [openSlot, setOpenSlot] = useState(null);   // expanded period id
  const [detail, setDetail] = useState({});         // slotId -> {loading|rows|error}
  const toggleSlot = async (s) => {
    if (s.is_break || !s.classes) return;           // breaks / empty periods aren't drillable
    const id = s.id;
    setOpenSlot((cur) => (cur === id ? null : id));
    if (detail[id]) return;                          // already fetched
    setDetail((m) => ({ ...m, [id]: { loading: true } }));
    try {
      const res = await apiGet('/api/dashboard/timetable/slot/' + id);
      setDetail((m) => ({ ...m, [id]: { rows: res.rows || [] } }));
    } catch (_e) {
      setDetail((m) => ({ ...m, [id]: { error: true } }));
    }
  };
  if (!data) return null;
  const slots = data.slots || [];
  const cur = data.current_slot;
  const nxt = data.next_slot;
  const link = teacher ? urls.timetable_mine : urls.timetable_view;
  const plural = (n) => (n === 1 ? 'class' : 'classes');
  // A period schedule exists but nothing is timetabled for today (e.g. a
  // weekend, or the term's grid isn't built yet) — say so plainly instead of
  // showing a ladder of empty periods or vanishing after the user enabled it.
  if (!data.total_today) {
    return (
      <Widget icon="fa-calendar-day" title={`Today's schedule · ${data.day}`}
              action={link && <a href={link} className="btn btn-secondary btn-sm">Open timetable</a>}>
        <Empty icon="fa-mug-hot">No classes scheduled for {data.day}.</Empty>
      </Widget>
    );
  }
  return (
    <Widget icon="fa-calendar-day" title={`Today's schedule · ${data.day}`}
            action={link && <a href={link} className="btn btn-secondary btn-sm">Open timetable</a>}>
      <div style={{ display: 'flex', gap: '.6rem', flexWrap: 'wrap', marginBottom: '.7rem' }}>
        <div style={{ flex: '1 1 160px', border: '1px solid var(--border-color)', borderRadius: 10, padding: '.55rem .7rem',
                      background: cur ? 'rgba(28,200,138,.08)' : 'transparent' }}>
          <div className="text-muted" style={{ fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.03em' }}>In session now</div>
          {cur ? (
            <>
              <div style={{ fontWeight: 700 }}>{cur.name} <span className="text-muted" style={{ fontWeight: 400, fontSize: '.75rem' }}>{cur.start}–{cur.end}</span></div>
              <div style={{ fontSize: '.8rem' }}>{data.in_session} {plural(data.in_session)} running</div>
            </>
          ) : <div style={{ fontWeight: 600, color: 'var(--text-secondary)', marginTop: 2 }}>No period in session</div>}
        </div>
        <div style={{ flex: '1 1 160px', border: '1px solid var(--border-color)', borderRadius: 10, padding: '.55rem .7rem' }}>
          <div className="text-muted" style={{ fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.03em' }}>Up next</div>
          {nxt ? (
            <>
              <div style={{ fontWeight: 700 }}>{nxt.name} <span className="text-muted" style={{ fontWeight: 400, fontSize: '.75rem' }}>{nxt.start}</span></div>
              <div style={{ fontSize: '.8rem' }}>{nxt.classes} {plural(nxt.classes)} scheduled</div>
            </>
          ) : <div style={{ fontWeight: 600, color: 'var(--text-secondary)', marginTop: 2 }}>Day complete</div>}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {slots.map((s) => {
          const isNow = s.state === 'now';
          const drillable = !s.is_break && !!s.classes;
          const isOpen = openSlot === s.id;
          const det = detail[s.id];
          return (
            <div key={s.id}>
              <div role={drillable ? 'button' : undefined} tabIndex={drillable ? 0 : undefined}
                   aria-expanded={drillable ? isOpen : undefined}
                   onClick={drillable ? () => toggleSlot(s) : undefined}
                   onKeyDown={drillable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSlot(s); } } : undefined}
                   style={{ display: 'flex', alignItems: 'center', gap: '.6rem', padding: '.4rem .5rem',
                        borderLeft: '3px solid ' + (isNow ? 'var(--success)' : 'transparent'),
                        background: isOpen ? 'var(--gray-50)' : (isNow ? 'rgba(28,200,138,.07)' : 'transparent'),
                        opacity: s.state === 'past' ? .55 : 1, borderRadius: 6,
                        cursor: drillable ? 'pointer' : 'default' }}>
                <span className="text-muted" style={{ width: 92, fontSize: '.75rem', fontVariantNumeric: 'tabular-nums' }}>{s.start}–{s.end}</span>
                <span style={{ flex: 1, fontSize: '.83rem', fontWeight: s.is_break ? 400 : 600, fontStyle: s.is_break ? 'italic' : 'normal' }}>
                  {s.name}{isNow && <span className="badge badge-success" style={{ marginLeft: 6 }}>Now</span>}
                </span>
                {drillable && (
                  <span className="badge" style={{ background: 'var(--border-color)', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                    {s.classes} {plural(s.classes)}
                  </span>
                )}
                {drillable && <i className={'fas fa-chevron-' + (isOpen ? 'up' : 'down')} aria-hidden="true"
                                 style={{ fontSize: '.7rem', color: 'var(--text-muted)', width: 12, textAlign: 'center' }} />}
              </div>
              {isOpen && (
                <div style={{ padding: '.35rem .5rem .6rem 95px' }}>
                  {det && det.loading && <div className="text-muted" style={{ fontSize: '.8rem' }}>Loading…</div>}
                  {det && det.error && <div className="text-muted" style={{ fontSize: '.8rem' }}>Couldn’t load this period.</div>}
                  {det && det.rows && det.rows.length === 0 &&
                    <div className="text-muted" style={{ fontSize: '.8rem' }}>No classes in this period.</div>}
                  {det && det.rows && det.rows.map((r, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '.6rem', fontSize: '.8rem',
                                 padding: '.32rem 0', borderBottom: i < det.rows.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                      <span style={{ fontWeight: 600, width: 84, flexShrink: 0 }}>{r.class_arm}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div>{r.subject}</div>
                        <div className="text-muted" style={{ fontSize: '.75rem', marginTop: 1 }}>
                          <i className="fas fa-user" aria-hidden="true" style={{ marginRight: 5, opacity: .6 }} />
                          {r.teacher}{r.room ? ' · ' + r.room : ''}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Widget>
  );
}

// School-at-a-glance: a permission-filtered executive KPI band across students,
// attendance, academics, finance and exams. Tiles are already gated server-side
// (a user only receives tiles for modules they may access), so this just lays
// them out — each with its value, a context sub-line and an optional trend chip.
function ExecSummary({ tiles }) {
  if (!tiles.length) return null;
  return (
    <div className="widget" style={{ marginBottom: '1.1rem' }}>
      <div className="wh">
        <h3><i className="fas fa-gauge-high" aria-hidden="true" /> School at a glance</h3>
      </div>
      <div className="wb">
        <div className="kpi-row" style={{ marginBottom: 0 }}>
          {tiles.map((tl) => (
            <div className="kpi" key={tl.key}>
              <div className={'ic ' + (tl.tone || 'blue')}><i className={'fas ' + tl.icon} aria-hidden="true" /></div>
              <div style={{ minWidth: 0 }}>
                <div className="v">{tl.value}</div>
                <div className="l">{tl.label}</div>
                {tl.sub && <div className="text-muted" style={{ fontSize: 'var(--text-xs)', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={tl.sub}>{tl.sub}</div>}
                {tl.delta && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-xs)', fontWeight: 600, marginTop: 2,
                                color: tl.delta.dir === 'up' ? 'var(--success)' : tl.delta.dir === 'down' ? 'var(--danger)' : 'var(--text-secondary)' }}>
                    <i className={'fas ' + (tl.delta.dir === 'up' ? 'fa-arrow-trend-up' : tl.delta.dir === 'down' ? 'fa-arrow-trend-down' : 'fa-minus')} aria-hidden="true" />
                    <span>{tl.delta.text}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Academic performance: the internal-grades quality a head-teacher steers on —
// pass/distinction rates, completion, average by section, the subjects failing
// most students and evidence-based recommendations. Server-scoped to the
// caller's classes; only shown to users permitted the results module.
function AcademicPerformance({ a, urls, t }) {
  if (!a || !a.summary) return null;
  const s = a.summary;
  const sections = a.sections || [];
  const weak = a.weak_subjects || [];
  const unit = (a.unit_kind || 'Section').toLowerCase();
  return (
    <>
      <div className="kpi-row">
        <Kpi tone="blue" icon="fa-chart-simple" value={s.class_average} label={'Class average · ' + (a.scope_label || 'school')} />
        <Kpi tone={rateTone(s.pass_rate)} icon="fa-circle-check" value={s.pass_rate + '%'} label={'Pass rate (≥' + s.pass_mark + ')'} />
        <Kpi tone="purple" icon="fa-star" value={s.distinction_rate + '%'} label={'Distinctions (≥' + s.distinction_mark + ')'} />
        <Kpi tone="teal" icon="fa-clipboard-check" value={s.completion + '%'} label="Scores entered" />
      </div>
      <div className="dash-grid split">
        <Widget icon="fa-graduation-cap" title={'Average by ' + unit}
                action={urls.institution_analytics && <a href={urls.institution_analytics} className="btn btn-secondary btn-sm">Analytics</a>}>
          <ChartBox height="240px">
            {sections.length ? (
              <Chart type="bar"
                ariaLabel={'Average score by ' + unit + ': ' + sections.map((x) => x.label + ' ' + x.average).join(', ')}
                options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                  scales: { y: { beginAtZero: true, max: 100, grid: { color: t.grid } }, x: { grid: { display: false } } } }}
                data={{ labels: sections.map((x) => x.label),
                  datasets: [{ data: sections.map((x) => x.average), backgroundColor: sections.map((x) => rateColor(x.pass_rate)), borderRadius: 6 }] }} />
            ) : <Empty icon="fa-graduation-cap">No scores entered yet</Empty>}
          </ChartBox>
        </Widget>
        <Widget icon="fa-triangle-exclamation" title="Subjects needing attention"
                action={a.intervention_count > 0 ? <span className="badge badge-danger">{a.intervention_count} at risk</span> : null}>
          {weak.length ? (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ margin: 0 }}>
                <thead><tr><th>Subject</th><th style={{ textAlign: 'right' }}>Avg</th><th style={{ textAlign: 'right' }}>Pass</th></tr></thead>
                <tbody>
                  {weak.map((x) => (
                    <tr key={x.name}>
                      <td>{x.name}</td>
                      <td style={{ textAlign: 'right' }}>{x.average}</td>
                      <td style={{ textAlign: 'right', color: rateColor(x.pass_rate), fontWeight: 700 }}>{x.pass_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Empty icon="fa-circle-check">Every subject is passing</Empty>}
          <ChronicSubjects rows={a.chronic_subjects} urls={urls} />
          <RecoList items={a.recommendations} />
        </Widget>
      </div>
    </>
  );
}

// Finance health: the bursar/MBA view of fee collection — expected vs collected,
// collection rate, outstanding + defaulters and a collection trend. Only shown
// to users permitted the finance module.
function FinanceHealth({ f, urls, t }) {
  if (!f) return null;
  const rate = f.collection_rate;
  const trend = f.trend || [];
  return (
    <>
      <div className="kpi-row">
        <Kpi tone="green" icon="fa-hand-holding-dollar" value={nairaShort(f.collected)} title={naira(f.collected)} label="Collected (term)"
             delta={f.collected_today > 0 ? { dir: 'up', text: nairaShort(f.collected_today) + ' today' } : undefined} />
        <Kpi tone={rate == null ? 'blue' : rateTone(rate)} icon="fa-gauge-high" value={rate == null ? '—' : rate + '%'} label="Collection rate" />
        <Kpi tone="amber" icon="fa-file-invoice-dollar" value={nairaShort(f.outstanding)} title={naira(f.outstanding)} label={'Outstanding · ' + f.defaulter_count + ' owing'} />
        <Kpi tone={f.net >= 0 ? 'teal' : 'red'} icon="fa-scale-balanced" value={nairaShort(f.net)} title={naira(f.net)} label="Net (term)"
             delta={{ dir: f.net >= 0 ? 'up' : 'down', text: f.net >= 0 ? 'surplus' : 'deficit' }} />
      </div>
      <div className="dash-grid split">
        <Widget icon="fa-gauge-high" title="Fee collection"
                action={urls.finance_collections && <a href={urls.finance_collections} className="btn btn-secondary btn-sm">Collections</a>}>
          {rate == null ? <Empty icon="fa-file-invoice-dollar">No fees expected yet this term</Empty> : (
            <div style={{ padding: '.3rem 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.82rem', marginBottom: 4 }}>
                <span className="text-muted">Collected {nairaShort(f.collected)}</span>
                <span className="text-muted">Expected {nairaShort(f.expected)}</span>
              </div>
              <div style={{ height: 14, borderRadius: 8, background: 'var(--border-color)', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: Math.min(100, rate) + '%', background: rateColor(rate), borderRadius: 8, transition: 'width .3s' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '.7rem' }}>
                <span style={{ fontSize: '1.6rem', fontWeight: 800, color: rateColor(rate) }}>{rate}%</span>
                {urls.defaulters && <a href={urls.defaulters} className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-user-clock" /> {f.defaulter_count} defaulters</a>}
              </div>
            </div>
          )}
        </Widget>
        <Widget icon="fa-chart-line" title="Collection trend">
          <ChartBox>
            {trend.length ? (
              <Chart type="line"
                ariaLabel={'Weekly fee collection: ' + trend.map((x) => x.label + ' ' + nairaShort(x.amount)).join(', ')}
                options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                  scales: { y: { beginAtZero: true, grid: { color: t.grid }, ticks: { callback: (v) => nairaShort(v) } }, x: { grid: { display: false } } } }}
                data={{ labels: trend.map((x) => x.label), datasets: [{ data: trend.map((x) => x.amount), borderColor: chartPalette().green, backgroundColor: chartPalette().fill, fill: true, tension: .35, pointRadius: 3, borderWidth: 3 }] }} />
            ) : <Empty icon="fa-chart-line">No payments recorded yet</Empty>}
          </ChartBox>
        </Widget>
      </div>
    </>
  );
}

// Exam snapshot card — a restrained, theme-aware surface card (no gradients):
// the exam's accent shows only as a top hairline + a tinted icon tile, the metric
// sits in the app's own text colours, and the meter/pills use design tokens so the
// card recolours with the active theme and reads the same in light and dark. Styles
// are inline so the refreshed look ships with the hash-busted JS bundle rather than
// the (possibly SW-cached) page shell.
const EXAM_ACCENT = {
  jamb: '#3b82f6',   // blue
  waec: '#0d9488',   // teal
  mock: '#8b5cf6',   // violet
};

function ExamStatPill({ k, v }) {
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.15,
                   background: 'var(--gray-50)', border: '1px solid var(--border-color)',
                   borderRadius: 'var(--radius-sm)', padding: '.3rem .55rem' }}>
      <span style={{ fontSize: '.62rem', textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--text-muted)' }}>{k}</span>
      <span style={{ fontSize: '.9rem', fontWeight: 700 }}>{v}</span>
    </span>
  );
}

function ExamMeter({ pct, label, accent }) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div style={{ marginTop: '.15rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.68rem', color: 'var(--text-muted)', marginBottom: 3 }}>
        <span>{label}</span><span>{p}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 'var(--radius-full)', background: 'var(--gray-100)', overflow: 'hidden' }}>
        <div style={{ width: p + '%', height: '100%', borderRadius: 'var(--radius-full)', background: accent }} />
      </div>
    </div>
  );
}

function ExamCard({ kind, snap, url }) {
  const title = kind === 'jamb' ? 'JAMB' : kind === 'waec' ? 'WAEC' : 'Latest Mock';
  const year = snap && kind !== 'mock' ? snap.year : '';

  let big = '—', unit = '', caption, meter = null, stats = [];
  if (!snap) {
    caption = kind === 'jamb' ? 'No JAMB results yet' : kind === 'waec' ? 'No WAEC results yet' : 'No mock exams yet';
  } else if (kind === 'jamb') {
    big = snap.mean; unit = 'avg'; caption = `mean across ${snap.count} candidates`;
    meter = { pct: snap.above_200_pct, label: 'Scoring ≥200' };
    stats = [{ k: 'Top score', v: snap.max }, { k: '≥200', v: snap.above_200 }];
  } else if (kind === 'waec') {
    big = snap.pass_rate; unit = '%'; caption = 'credit pass rate';
    meter = { pct: snap.pass_rate, label: 'Credit passes' };
    stats = [{ k: 'Students', v: snap.students }, { k: 'Entries', v: snap.entries }];
  } else {
    big = snap.mean; unit = 'avg'; caption = `${snap.name} · ${snap.count} sat`;
    stats = [{ k: 'Top score', v: snap.max }];
  }

  const accent = EXAM_ACCENT[kind] || 'var(--primary)';
  return (
    <div style={{ position: 'relative', overflow: 'hidden', color: 'var(--text-primary)',
                  background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                  borderTop: '3px solid ' + accent, borderRadius: 'var(--radius-lg)',
                  boxShadow: 'var(--shadow-xs)', padding: '1.15rem', minHeight: 172,
                  display: 'flex', flexDirection: 'column', gap: '.7rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '.55rem' }}>
        <span style={{ width: 36, height: 36, borderRadius: 'var(--radius-md)', flexShrink: 0,
                       background: `color-mix(in srgb, ${accent} 16%, var(--bg-card))`, color: accent,
                       display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          <i aria-hidden="true" className={'fas ' + ICON[kind]} />
        </span>
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
          <strong style={{ fontSize: '.9rem' }}>{title}</strong>
          {year && <span style={{ fontSize: '.68rem', color: 'var(--text-muted)' }}>{year}</span>}
        </div>
        {(snap || kind === 'mock') && (
          <a href={url} aria-label={'Open ' + title} style={{ marginLeft: 'auto', color: accent }}>
            <i aria-hidden="true" className="fas fa-arrow-right" />
          </a>
        )}
      </div>

      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '.3rem' }}>
          <span style={{ fontSize: '2.4rem', fontWeight: 800, lineHeight: 1, fontFamily: 'var(--font-display)' }}>{big}</span>
          {unit && <span style={{ fontSize: '.8rem', color: 'var(--text-muted)' }}>{unit}</span>}
        </div>
        <div style={{ fontSize: '.76rem', color: 'var(--text-muted)', marginTop: 2 }}>{caption}</div>
      </div>

      {meter && <ExamMeter pct={meter.pct} label={meter.label} accent={accent} />}

      {stats.length > 0 && (
        <div style={{ display: 'flex', gap: '.45rem', marginTop: 'auto', flexWrap: 'wrap' }}>
          {stats.map((s) => <ExamStatPill key={s.k} k={s.k} v={s.v} />)}
        </div>
      )}
    </div>
  );
}

// Decorative school-building illustration for the hero. Purely ornamental, so
// it's aria-hidden. Painted in white-opacity monochrome (no fixed hue) so it sits
// correctly on ANY theme's hero gradient — green, blue, plum, slate, etc.
function SchoolArt() {
  return (
    <div className="dash-hero-art" aria-hidden="true">
      <svg viewBox="0 0 240 180" width="100%" height="100%" preserveAspectRatio="xMidYMax meet">
        {/* soft ground + bushes */}
        <ellipse cx="120" cy="168" rx="120" ry="16" fill="rgba(255,255,255,.06)" />
        <circle cx="40" cy="150" r="26" fill="rgba(255,255,255,.10)" />
        <circle cx="205" cy="150" r="30" fill="rgba(255,255,255,.09)" />
        {/* main building */}
        <rect x="58" y="86" width="124" height="72" rx="6" fill="rgba(255,255,255,.92)" />
        <rect x="58" y="150" width="124" height="8" rx="2" fill="rgba(255,255,255,.5)" />
        {/* roof */}
        <polygon points="120,44 190,90 50,90" fill="rgba(255,255,255,.68)" />
        <polygon points="120,44 190,90 120,90" fill="rgba(255,255,255,.82)" />
        {/* flag */}
        <rect x="118" y="26" width="3" height="20" rx="1.5" fill="rgba(255,255,255,.9)" />
        <polygon points="121,27 137,32 121,37" fill="rgba(255,255,255,.7)" />
        {/* clock on the gable */}
        <circle cx="120" cy="74" r="9" fill="rgba(255,255,255,.95)" />
        <circle cx="120" cy="74" r="9" fill="none" stroke="rgba(255,255,255,.55)" strokeWidth="1.5" />
        <line x1="120" y1="74" x2="120" y2="69" stroke="rgba(15,23,42,.4)" strokeWidth="1.4" strokeLinecap="round" />
        <line x1="120" y1="74" x2="124" y2="76" stroke="rgba(15,23,42,.4)" strokeWidth="1.4" strokeLinecap="round" />
        {/* door */}
        <rect x="106" y="120" width="28" height="38" rx="14" fill="rgba(255,255,255,.62)" />
        <rect x="106" y="120" width="28" height="38" rx="14" fill="none" stroke="rgba(255,255,255,.5)" strokeWidth="1.2" />
        <circle cx="128" cy="140" r="1.6" fill="rgba(15,23,42,.35)" />
        {/* windows */}
        {[72, 150].map((x) => (
          <g key={x}>
            <rect x={x} y="104" width="20" height="20" rx="3" fill="rgba(255,255,255,.55)" />
            <line x1={x + 10} y1="104" x2={x + 10} y2="124" stroke="rgba(255,255,255,.85)" strokeWidth="1.4" />
            <line x1={x} y1="114" x2={x + 20} y2="114" stroke="rgba(255,255,255,.85)" strokeWidth="1.4" />
          </g>
        ))}
      </svg>
    </div>
  );
}
