import React, { useEffect, useState, createContext, useContext, useCallback } from 'react';
import { apiGet } from '../lib/api';
import { cachePut, cacheGet, requestPersistence, failedItems, retryFailed, discardFailed } from '../lib/offline';
import { useOnline, useSync } from '../lib/hooks';
import { Spinner, ErrorState, Banner, Pill, FailedMarks } from '../components/ui';
import MarkDaily from './screens/MarkDaily';
import WeekGrid from './screens/WeekGrid';

const Ctx = createContext(null);
export const useCtx = () => useContext(Ctx);

const TABS = [
  { path: 'mark', label: 'Mark daily', icon: 'fa-user-check', el: MarkDaily },
  { path: 'week', label: 'Weekly grid', icon: 'fa-table-cells-large', el: WeekGrid },
];

function useHashRoute() {
  const get = () => location.hash.replace(/^#\/?/, '') || 'mark';
  const [route, setRoute] = useState(get);
  useEffect(() => {
    const f = () => setRoute(get());
    window.addEventListener('hashchange', f);
    return () => window.removeEventListener('hashchange', f);
  }, []);
  return route;
}

export default function App() {
  const online = useOnline();
  const sync = useSync();
  const route = useHashRoute();
  const [ctx, setCtx] = useState({ loading: true });
  const [failed, setFailed] = useState([]);

  const refreshFailed = useCallback(async () => setFailed(await failedItems()), []);

  useEffect(() => { requestPersistence(); }, []);
  useEffect(() => { refreshFailed(); }, [sync.failed, refreshFailed]);

  // Context (term/classes/weeks/holidays): network first, fall back to cache.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await apiGet('/attendance/api/context');
        await cachePut('context', data);
        if (alive) setCtx({ loading: false, data });
      } catch (e) {
        const cached = await cacheGet('context');
        if (!alive) return;
        if (cached) setCtx({ loading: false, data: cached, stale: true });
        else setCtx({ loading: false, error: e });
      }
    })();
    return () => { alive = false; };
  }, []);

  const active = TABS.find((t) => t.path === route) || TABS[0];
  const Screen = active.el;

  return (
    <Ctx.Provider value={{ ...(ctx.data || {}), online, sync }}>
      <nav className="att-tabs" role="tablist" aria-label="Attendance sections">
        {TABS.map((t) => (
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

      {ctx.stale && <Banner tone="warn">Showing your saved classes (offline) — reconnect to refresh.</Banner>}

      <FailedMarks
        items={failed}
        onRetry={async (f) => { await retryFailed(f); await sync.flush(); await refreshFailed(); }}
        onDiscard={async (f) => { await discardFailed(f.id); await sync.refresh(); await refreshFailed(); }}
      />

      <div role="tabpanel" style={{ marginTop: 12 }}>
        {ctx.loading ? <Spinner label="Loading attendance…" />
          : ctx.error ? <ErrorState title="Couldn’t load attendance" detail={ctx.error.message} onRetry={() => location.reload()} />
          : <Screen />}
      </div>
    </Ctx.Provider>
  );
}
