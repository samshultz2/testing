import { useState, useCallback } from 'react';

// Form recovery: persist a form's state to sessionStorage so a reload, an
// accidental navigation, or a crash doesn't lose what the user typed. The API
// mirrors useState (the setter accepts a value or an updater). Call clear()
// after a successful submit so a stale draft doesn't reappear next time.
//
// `opts.omit` lists keys never written to storage (e.g. passwords), so secrets
// are kept in memory only.
export function useDraft(key, initial, opts = {}) {
  const storageKey = 'draft:' + key;
  const omit = opts.omit || [];

  const persist = (value) => {
    try {
      const safe = {};
      Object.keys(value).forEach((k) => { if (omit.indexOf(k) < 0) safe[k] = value[k]; });
      sessionStorage.setItem(storageKey, JSON.stringify(safe));
    } catch (e) { /* storage full / unavailable — drafts are best-effort */ }
  };

  const [state, setState] = useState(() => {
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) return { ...initial, ...JSON.parse(saved) };
    } catch (e) { /* ignore */ }
    return initial;
  });

  const set = useCallback((next) => {
    setState((prev) => {
      const value = typeof next === 'function' ? next(prev) : next;
      persist(value);
      return value;
    });
  }, [storageKey]);

  const clear = useCallback(() => {
    try { sessionStorage.removeItem(storageKey); } catch (e) { /* ignore */ }
  }, [storageKey]);

  return [state, set, clear];
}
