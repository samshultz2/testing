import React, { useEffect, useState, createContext, useContext, useCallback } from 'react';
import { apiGet } from '../lib/api';
import { cachePut, cacheGet, requestPersistence, failedItems, retryFailed, discardFailed } from '../lib/offline';
import { useOnline, useSync } from '../lib/hooks';
import { Spinner, ErrorState, Banner, Pill, Field, Select, FailedMarks } from '../components/ui';
import MarkDaily from './screens/MarkDaily';
import WeekGrid from './screens/WeekGrid';
import DailySummary from './screens/DailySummary';
import WeeklyReport from './screens/WeeklyReport';
import TermlyReport from './screens/TermlyReport';
import Alerts from './screens/Alerts';
import StudentProfile from './screens/StudentProfile';
import Analytics from './screens/Analytics';

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

const TABS = [
  { path: 'mark', label: 'Mark daily', icon: 'fa-user-check', el: MarkDaily, mark: true },
  { path: 'week', label: 'Weekly grid', icon: 'fa-table-cells-large', el: WeekGrid, mark: true },
  { path: 'daily', label: 'Daily summary', icon: 'fa-list-check', el: DailySummary },
  { path: 'weekly', label: 'Weekly report', icon: 'fa-calendar-week', el: WeeklyReport },
  { path: 'termly', label: 'Termly report', icon: 'fa-calendar-days', el: TermlyReport },
  { path: 'analytics', label: 'Analytics', icon: 'fa-chart-line', el: Analytics, insight: true },
  { path: 'student', label: 'Student profile', icon: 'fa-user', el: StudentProfile, insight: true },
  { path: 'alerts', label: 'Alerts', icon: 'fa-bell', el: Alerts },
];

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

  return (
    <Ctx.Provider value={{ ...data, online, sync, initial: { assignmentId: INIT.assignmentId, date: INIT.date, studentId: INIT.studentId } }}>
      <nav className="att-tabs" role="tablist" aria-label="Attendance sections">
        {tabs.map((t) => (
          <a key={t.path} href={'#/' + t.path} role="tab" aria-selected={t.path === active.path}
             className={'att-tab' + (t.path === active.path ? ' is-active' : '')}>
            <i className={'fas ' + t.icon} aria-hidden="true" /> <span>{t.label}</span>
          </a>
        ))}
        <span className="att-tabs-status">
          <Pill tone={online ? 'green' : 'red'}>{online ? 'Online' : 'Offline'}</Pill>
          {sync.pending > 0 && <Pill tone="amber">{sync.pending} pending</Pill>}
        </span>
      </nav>

      {(data.terms && data.terms.length > 0) && (
        <div style={{ margin: '12px 0', maxWidth: 320 }}>
          <Field label="Academic term" htmlFor="att-term">
            <Select id="att-term" value={selectedTerm} onChange={(v) => setTermId(Number(v))}
                    options={data.terms.map((t) => ({ value: String(t.id), label: t.name + (t.active ? ' (active)' : '') }))} />
          </Field>
        </div>
      )}

      {ctx.stale && <Banner tone="warn">Showing your saved data (offline) — reconnect to refresh.</Banner>}

      <FailedMarks
        items={failed}
        onRetry={async (f) => { await retryFailed(f); await sync.flush(); await refreshFailed(); }}
        onDiscard={async (f) => { await discardFailed(f.id); await sync.refresh(); await refreshFailed(); }}
      />

      <div role="tabpanel" style={{ marginTop: 8 }}>
        {ctx.loading ? <Spinner label="Loading attendance…" />
          : ctx.error ? <ErrorState title="Couldn’t load attendance" detail={ctx.error.message} onRetry={() => location.reload()} />
          : <Screen key={selectedTerm || 'none'} />}
      </div>
    </Ctx.Provider>
  );
}
