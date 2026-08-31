import { useState, useCallback } from 'react';

// Form recovery: persist a form's state to sessionStorage so a reload, an
// accidental navigation, or a crash doesn't lose what the user typed. The API
// mirrors useState (the setter accepts a value or an updater). Call clear()
// after a successful submit so a stale draft doesn't reappear next time.
//
// `opts.omit` lists keys never written to storage (e.g. passwords), so secrets
// are kept in memory only.
//
// `opts.signature` (optional) ties the draft to the server baseline it was taken
// against. When supplied, a stored draft is only restored if its signature still
// matches — so once the underlying record changes (e.g. after a successful edit)
// the now-stale draft is discarded and the form shows authoritative server data,
// instead of an old draft blanking out fields. Genuinely unsaved work (same
// baseline) is still recovered.
export function useDraft(key, initial, opts = {}) {
  const storageKey = 'draft:' + key;
  const omit = opts.omit || [];
  const signature = opts.signature != null ? String(opts.signature) : null;

  const persist = (value) => {
    try {
      const safe = {};
      Object.keys(value).forEach((k) => { if (omit.indexOf(k) < 0) safe[k] = value[k]; });
      const record = signature != null ? { __sig: signature, data: safe } : safe;
      sessionStorage.setItem(storageKey, JSON.stringify(record));
    } catch (e) { /* storage full / unavailable — drafts are best-effort */ }
  };

  const [state, setState] = useState(() => {
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (signature != null) {
          return (parsed && parsed.__sig === signature)
            ? { ...initial, ...parsed.data }    // same baseline — recover unsaved work
            : initial;                          // baseline changed — drop stale draft
        }
        return { ...initial, ...parsed };       // unsigned draft (other forms)
      }
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
