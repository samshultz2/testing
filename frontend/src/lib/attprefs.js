// Small localStorage helpers so the attendance screens remember the user's last
// selected class and offer quick access to recently-used classes. Best-effort —
// any storage error degrades to "no memory", never throws.
// Share the "last class" key with MarkDaily so both screens agree.
const LAST = 'attendance:lastClass';
const RECENT = 'att_recent_classes';

export function lastClass() {
  try { return window.localStorage.getItem(LAST) || ''; } catch (_) { return ''; }
}

export function recentClasses() {
  try { return JSON.parse(window.localStorage.getItem(RECENT)) || []; } catch (_) { return []; }
}

// Record a class selection: remember it as "last" and prepend to recents
// (deduped, capped). `label` is the human class name for the quick-pick chips.
export function rememberClass(id, label) {
  if (!id) return;
  try {
    window.localStorage.setItem(LAST, String(id));
    const list = recentClasses().filter((x) => String(x.id) !== String(id));
    list.unshift({ id: String(id), label: label || String(id) });
    window.localStorage.setItem(RECENT, JSON.stringify(list.slice(0, 6)));
  } catch (_) { /* ignore */ }
}
