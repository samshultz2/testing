import React, { useEffect, useState, createContext, useContext, useCallback } from 'react';
import { apiGet } from '../lib/api';
import { cachePut, cacheGet, requestPersistence, failedItems, retryFailed, discardFailed } from '../lib/offline';
import { useOnline, useSync } from '../lib/hooks';
import { Spinner, ErrorState, Banner, Pill, FailedMarks } from '../components/ui';
import MarkDaily from './screens/MarkDaily';
import WeekGrid from './screens/WeekGrid';
import DailySummary from './screens/DailySummary';
import WeeklyReport from './screens/WeeklyReport';
import TermlyReport from './screens/TermlyReport';
import Alerts from './screens/Alerts';
import StudentProfile from './screens/StudentProfile';
import Analytics from './screens/Analytics';
import Interventions from './screens/Interventions';

const Ctx = createContext(null);
export const useCtx = () => useContext(Ctx);

// Deep-link params (e.g. from the dashboard): /attendance/app?tab=mark&
// assignment_id=12&term_id=4&date=2026-06-10 — read once at load.
const INIT = (() => {
  const p = new URLSearchParams(location.search);
  return {
    termId: p.get('term_id') ? Number(p.get('term_id')) : null,
    assignmentId: p.get('assignment_id') || '',
    date: p.get('date') || '',
    tab: p.get('tab') || (p.get('student_id') ? 'student' : ''),
    studentId: p.get('student_id') || '',
  };
})();

// Grouped so the nav reads Mark → Reports → Insights (a side rail on laptops,
// one swipeable chip row on phones — never five wrapped rows of tabs).
const TABS = [
  { path: 'mark', label: 'Mark daily', short: 'Mark', icon: 'fa-user-check', el: MarkDaily, mark: true, group: 'Mark',
    hint: 'Take today’s register' },
  { path: 'week', label: 'Weekly grid', short: 'Week grid', icon: 'fa-table-cells-large', el: WeekGrid, mark: true, group: 'Mark',
    hint: 'Mark or fix a whole week' },
  { path: 'daily', label: 'Daily summary', short: 'Daily', icon: 'fa-list-check', el: DailySummary, group: 'Reports',
    hint: 'Who was present on a day' },
  { path: 'weekly', label: 'Weekly report', short: 'Weekly', icon: 'fa-calendar-week', el: WeeklyReport, group: 'Reports',
    hint: 'A week at a glance' },
  { path: 'termly', label: 'Termly report', short: 'Termly', icon: 'fa-calendar-days', el: TermlyReport, group: 'Reports',
    hint: 'Term totals per student' },
  { path: 'analytics', label: 'Analytics', short: 'Analytics', icon: 'fa-chart-line', el: Analytics, insight: true, group: 'Insights',
    hint: 'Trends, days and classes' },
  { path: 'interventions', label: 'Interventions', short: 'Interventions', icon: 'fa-hand-holding-heart', el: Interventions, insight: true, group: 'Insights',
    hint: 'Follow up absentees' },
  { path: 'student', label: 'Student profile', short: 'Student', icon: 'fa-user', el: StudentProfile, insight: true, group: 'Insights',
    hint: 'One student’s record' },
  { path: 'alerts', label: 'Alerts', short: 'Alerts', icon: 'fa-bell', el: Alerts, group: 'Insights',
    hint: 'Below-threshold students' },
];
const GROUPS = ['Mark', 'Reports', 'Insights'];

function useHashRoute() {
  const get = () => location.hash.replace(/^#\/?/, '') || INIT.tab || 'mark';
  const [route, setRoute] = useState(get);
  useEffect(() => {
    const f = () => setRoute(get());
    window.addEventListener('hashchange', f);
    return () => window.removeEventListener('hashchange', f);
  }, []);
  return route;
}

const ctxKey = (termId) => 'context' + (termId ? '|' + termId : '');

export default function App() {
  const online = useOnline();
  const sync = useSync();
  const route = useHashRoute();
  const [termId, setTermId] = useState(INIT.termId);   // null = active term
  const [ctx, setCtx] = useState({ loading: true });
  const [failed, setFailed] = useState([]);

  const refreshFailed = useCallback(async () => setFailed(await failedItems()), []);
  useEffect(() => { requestPersistence(); }, []);
  useEffect(() => { refreshFailed(); }, [sync.failed, refreshFailed]);

  // Context for the selected (or active) term: network first, cache fallback.
  useEffect(() => {
    let alive = true;
    setCtx((c) => ({ ...c, loading: !c.data, refreshing: true }));
    (async () => {
      const url = '/attendance/api/context' + (termId ? `?term_id=${termId}` : '');
      try {
        const data = await apiGet(url);
        await cachePut(ctxKey(termId), data);
        if (alive) setCtx({ loading: false, data });
      } catch (e) {
        const cached = (await cacheGet(ctxKey(termId))) || (await cacheGet('context'));
        if (!alive) return;
        if (cached) setCtx({ loading: false, data: cached, stale: true });
        else setCtx({ loading: false, error: e });
      }
    })();
    return () => { alive = false; };
  }, [termId]);

  const data = ctx.data || {};
  // View-only users (no marking permission) don't see the marking tabs.
  const canMark = data.can_mark !== false;
  const tabs = TABS.filter((t) => !t.mark || canMark);
  const active = tabs.find((t) => t.path === route) || tabs[0];
  const Screen = active.el;
  const selectedTerm = termId != null ? String(termId) : (data.term ? String(data.term.id) : '');

  const navRef = React.useRef(null);
  useEffect(() => {
    const el = navRef.current && navRef.current.querySelector('.on');
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [active.path]);
  const termObj = (data.terms || []).find((t) => String(t.id) === selectedTerm);

  return (
    <Ctx.Provider value={{ ...data, online, sync, initial: { assignmentId: INIT.assignmentId, date: INIT.date, studentId: INIT.studentId } }}>
      <header className="ax-head">
        <span className="ax-logo" aria-hidden="true"><i className="fas fa-clipboard-user" /></span>
        <div className="ax-title">
          <span className="ax-kicker">Attendance{termObj ? ` · ${termObj.name}` : ''}</span>
          <h1>{active.label}</h1>
        </div>
        <div className="ax-head-acts">
          {(data.terms && data.terms.length > 0) && (
            <label className="ax-term" title="Academic term">
              <i className="fas fa-calendar" aria-hidden="true" />
              <select value={selectedTerm} onChange={(e) => setTermId(Number(e.target.value))} aria-label="Academic term">
                {data.terms.map((t) => <option key={t.id} value={String(t.id)}>{t.name + (t.active ? ' (active)' : '')}</option>)}
              </select>
            </label>
          )}
          <span className={'ax-net ' + (online ? 'on' : 'off')} title={online ? 'Online' : 'Offline — marks are saved and sync later'}>
            <i className={'fas ' + (online ? 'fa-wifi' : 'fa-plane')} aria-hidden="true" /><span>{online ? 'Online' : 'Offline'}</span>
          </span>
          {sync.pending > 0 && <Pill tone="amber">{sync.pending} pending</Pill>}
        </div>
      </header>

      <nav className="ax-chips" ref={navRef} role="tablist" aria-label="Attendance sections">
        {tabs.map((t) => (
          <a key={t.path} href={'#/' + t.path} role="tab" aria-selected={t.path === active.path}
             className={t.path === active.path ? 'on' : ''}>
            <i className={'fas ' + t.icon} aria-hidden="true" />{t.short}
          </a>
        ))}
      </nav>

      <div className="ax-cols">
        <aside className="ax-rail" aria-label="Attendance sections">
          {GROUPS.map((g) => {
            const list = tabs.filter((t) => t.group === g);
            if (!list.length) return null;
            return (
              <div key={g} className="ax-group">
                <span className="ax-group-h">{g}</span>
                {list.map((t) => (
                  <a key={t.path} href={'#/' + t.path} className={t.path === active.path ? 'on' : ''}
                     aria-current={t.path === active.path ? 'page' : undefined}>
                    <span className="ax-ic"><i className={'fas ' + t.icon} aria-hidden="true" /></span>
                    <span className="ax-lb"><strong>{t.label}</strong><small>{t.hint}</small></span>
                  </a>
                ))}
              </div>
            );
          })}
          <a className="ax-classic" href="/attendance/"><i className="fas fa-table-list" aria-hidden="true" /> Classic view</a>
        </aside>

        <main className="ax-main" role="tabpanel">
          {ctx.stale && <Banner tone="warn">Showing your saved data (offline) — reconnect to refresh.</Banner>}
          <FailedMarks
            items={failed}
            onRetry={async (f) => { await retryFailed(f); await sync.flush(); await refreshFailed(); }}
            onDiscard={async (f) => { await discardFailed(f.id); await sync.refresh(); await refreshFailed(); }}
          />
          <div className={'ax-panel' + (active.path === 'mark' ? ' bare' : '')}>
            {ctx.loading ? <Spinner label="Loading attendance…" />
              : ctx.error ? <ErrorState title="Couldn’t load attendance" detail={ctx.error.message} onRetry={() => location.reload()} />
              : <Screen key={selectedTerm || 'none'} />}
          </div>
        </main>
      </div>
    </Ctx.Provider>
  );
}
