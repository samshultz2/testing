import { useState, useEffect, useCallback } from 'react';
import { flushOutbox, counts } from './offline';

// Track connectivity.
export function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down); };
  }, []);
  return online;
}

// Outbox sync: flush on reconnect, on mount, and every 30s; expose counts.
export function useSync() {
  const [state, setState] = useState({ pending: 0, failed: 0 });
  const refresh = useCallback(async () => setState(await counts()), []);
  const flush = useCallback(async () => { const r = await flushOutbox(); await refresh(); return r; }, [refresh]);
  useEffect(() => {
    refresh();
    const up = () => flush();
    window.addEventListener('online', up);
    const timer = setInterval(() => { if (navigator.onLine) flush(); }, 30000);
    if (navigator.onLine) flush();
    return () => { window.removeEventListener('online', up); clearInterval(timer); };
  }, [flush, refresh]);
  return { ...state, flush, refresh };
}

// Small data-loading helper with loading/error/stale (cached) states.
export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true });
  const run = useCallback(() => {
    let alive = true;
    setState({ loading: true });
    Promise.resolve(fn())
      .then((data) => { if (alive) setState({ loading: false, data }); })
      .catch((error) => { if (alive) setState({ loading: false, error }); });
    return () => { alive = false; };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(run, [run]);
  return [state, run];
}
