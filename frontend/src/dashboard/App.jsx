import React, { useState } from 'react';
import Chart, { chartTheme } from './charts';
import { Kpi, Widget, Empty, ChartBox, naira, nairaShort } from './components';
import Customize from './Customize';
import { apiGet, apiPost, csrfToken } from '../lib/api';
import { Toast, SetupChecklist } from '../components/ui';

const ICON = { jamb: 'fa-file-contract', waec: 'fa-file-alt', mock: 'fa-clipboard-list' };

// Reorderable/favouritable blocks — labels + icons for the block toolbar.
const BLOCK_META = {
  insights: { label: 'Needs attention', icon: 'fa-bell' },
  branches: { label: 'Branch performance', icon: 'fa-code-branch' },
  kpi: { label: 'Student KPIs', icon: 'fa-users' },
  crossmodule: { label: 'Module KPIs', icon: 'fa-layer-group' },
  exams: { label: 'Exam snapshots', icon: 'fa-file-contract' },
  charts: { label: 'Demographics', icon: 'fa-chart-pie' },
  attendance_trend: { label: 'Attendance trend', icon: 'fa-chart-line' },
  class_religion: { label: 'Class & religion', icon: 'fa-school' },
  people: { label: 'People', icon: 'fa-user-clock' },
};
const FALLBACK_ORDER = ['insights', 'branches', 'kpi', 'crossmodule', 'exams',
  'charts', 'attendance_trend', 'class_religion', 'people'];

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
      case 'insights': return has('insights') && !emptySchool;
      case 'branches': return has('branches') && (d.branch_comparison || []).length > 1;
      case 'kpi': return has('kpi') && !emptySchool;
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
    insights: <Insights items={d.insights || []} />,
    branches: <BranchComparison rows={d.branch_comparison || []} />,
    kpi: (
      <div className="kpi-row">
        <Kpi tone="blue" icon="fa-users" value={d.total_students} label="Students"
             delta={d.new_students_month > 0 ? { dir: 'up', text: `+${d.new_students_month} this month` } : undefined} />
        <Kpi tone="green" icon="fa-user-check" value={d.active_enrollments} label="Enrolled" />
        <Kpi tone="teal" icon="fa-percent" value={(d.attendance_stats || {}).today_percentage + '%'} label="Attendance today"
             delta={attendanceDelta(d.attendance_stats)} />
        <Kpi tone="purple" icon="fa-user-graduate" value={d.graduates_count} label="Graduates" />
      </div>
    ),
    crossmodule: (
      <div className="kpi-row">
        {d.finance_stat && <>
          <Kpi tone="green" icon="fa-coins" value={nairaShort(d.finance_stat.collected)} title={naira(d.finance_stat.collected)} label="Fees collected (term)"
               delta={d.finance_stat.collected_today > 0 ? { dir: 'up', text: `${nairaShort(d.finance_stat.collected_today)} today` } : undefined} />
          <Kpi tone="teal" icon="fa-scale-balanced" value={nairaShort(d.finance_stat.net)} title={naira(d.finance_stat.net)} label="Net (term)"
               delta={{ dir: d.finance_stat.net >= 0 ? 'up' : 'down', text: d.finance_stat.net >= 0 ? 'in surplus' : 'in deficit' }} />
        </>}
        {d.sales_stat && <Kpi tone="blue" icon="fa-cash-register" value={nairaShort(d.sales_stat.today)} title={naira(d.sales_stat.today)} label={`Sales today (${d.sales_stat.count_today})`} />}
        {d.hr_stat && <Kpi tone="purple" icon="fa-id-badge" value={d.hr_stat.total} label={`Staff (${d.hr_stat.teaching} teaching)`} />}
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
              datasets: [{ data: [d.male_students, d.female_students], backgroundColor: ['#4e73df', '#e74a3b'], borderWidth: 0 }] }} />
          </ChartBox>
        </Widget>
        <Widget icon="fa-route" title="Streams">
          <ChartBox>
            <Chart type="doughnut" options={doughnut()} ariaLabel={'Students by stream: ' + (Object.entries(d.stream_dist || {}).map(([k, v]) => `${k} ${v}`).join(', ') || 'no data')} data={{ labels: Object.keys(d.stream_dist || {}),
              datasets: [{ data: Object.values(d.stream_dist || {}), backgroundColor: ['#11998e', '#667eea', '#f6c23e', '#cbd5e1'], borderWidth: 0 }] }} />
          </ChartBox>
        </Widget>
        <Widget icon="fa-birthday-cake" title="Age groups">
          <ChartBox>
            <Chart type="bar" options={barOpts} ariaLabel={'Students by age group: ' + ['0-10', '11-13', '14-16', '17-19', '20+'].map((k) => `${k}: ${(d.age_distribution || {})[k] || 0}`).join(', ')} data={{ labels: ['0-10', '11-13', '14-16', '17-19', '20+'],
              datasets: [{ data: ['0-10', '11-13', '14-16', '17-19', '20+'].map((k) => (d.age_distribution || {})[k] || 0), backgroundColor: '#4e73df', borderRadius: 6 }] }} />
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
        <div>
          <h1>Welcome back{d.user_name ? ', ' + d.user_name : ''} 👋</h1>
          <p>{dateLabel}{d.active_session ? ' · ' + d.active_session.name : ''}</p>
        </div>
        <div className="dash-hero-actions">
          {d.active_term && <div className="term-chip"><i aria-hidden="true" className="fas fa-calendar-day" /> {d.active_term.name}</div>}
          <button type="button" onClick={refresh} disabled={refreshing} className="btn btn-secondary btn-sm"
                  title={'Refresh dashboard — last updated ' + updatedLabel} aria-label={'Refresh dashboard, last updated ' + updatedLabel}>
            <i aria-hidden="true" className={'fas fa-rotate' + (refreshing ? ' fa-spin' : '')} /> {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
          {!emptySchool && <button type="button" onClick={() => setArranging((v) => !v)}
                  className={'btn btn-sm ' + (arranging ? 'btn-primary' : 'btn-secondary')}
                  aria-pressed={arranging} title="Drag to reorder & pin favourite widgets">
            <i aria-hidden="true" className="fas fa-up-down-left-right" /> {arranging ? 'Done' : 'Arrange'}
          </button>}
          <button type="button" onClick={() => setCustomizing(true)} className="btn btn-secondary btn-sm" title="Choose widgets"><i aria-hidden="true" className="fas fa-sliders" /> Customize</button>
        </div>
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
            const color = a.category === 'Important' ? '#e74a3b' : a.category === 'Event' ? '#f6c23e' : 'var(--primary)';
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
          <i className={'fa-star ' + (favorite ? 'fas' : 'far')} style={{ color: favorite ? '#f6c23e' : 'var(--text-muted)' }} aria-hidden="true" />
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
  high: { color: '#e74a3b', label: 'Urgent' },
  medium: { color: '#f6c23e', label: 'Soon' },
  low: { color: '#4e73df', label: 'FYI' },
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
          return (
            <li key={it.key}>
              <a href={it.url} className="insight-row"
                 style={{ display: 'flex', alignItems: 'center', gap: '.7rem', padding: '.65rem .9rem',
                          borderLeft: '4px solid ' + sev.color, textDecoration: 'none', color: 'inherit',
                          borderBottom: '1px solid var(--border-color)' }}>
                <i aria-hidden="true" className={'fas ' + it.icon} style={{ color: sev.color, width: 18, textAlign: 'center' }} />
                <span style={{ flex: 1 }}>
                  <strong>{it.title}</strong>
                  {it.detail && <div className="text-muted text-sm">{it.detail}</div>}
                </span>
                <span className="badge" style={{ background: sev.color + '22', color: sev.color, fontWeight: 600 }}>{sev.label}</span>
                <i aria-hidden="true" className="fas fa-chevron-right text-muted" />
              </a>
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
                      <span style={{ display: 'block', height: '100%', width: (r.students / maxStudents * 100) + '%', background: '#4e73df' }} />
                    </span>
                  </div>
                </td>
                <td><span className={'badge ' + (r.attendance >= 75 ? 'badge-success' : r.attendance > 0 ? 'badge-warning' : 'badge-secondary')}>{r.attendance ? r.attendance + '%' : '—'}</span></td>
                <td style={{ textAlign: 'right' }} title={naira(r.fees)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                    <span aria-hidden="true" style={{ width: 48, height: 6, background: 'var(--border-color)', borderRadius: 3, overflow: 'hidden' }}>
                      <span style={{ display: 'block', height: '100%', width: (r.fees / maxFees * 100) + '%', background: '#11998e', float: 'right' }} />
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

function ExamCard({ kind, snap, url }) {
  return (
    <div className={'exam-card ' + kind}>
      <div className="top">
        <span><i aria-hidden="true" className={'fas ' + ICON[kind]} /> {kind === 'jamb' ? 'JAMB' : kind === 'waec' ? 'WAEC' : 'Latest Mock'} {snap && kind !== 'mock' ? snap.year : ''}</span>
        {(snap || kind === 'mock') && <a href={url} style={{ color: '#fff', opacity: .85 }} aria-label="Open"><i aria-hidden="true" className="fas fa-arrow-right" /></a>}
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
