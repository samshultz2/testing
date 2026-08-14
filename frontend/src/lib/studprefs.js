// localStorage helpers for the Students list: recent search terms, recently
// viewed students, and named saved filters. Best-effort — any storage error
// degrades to "no memory" and never throws.
const RECENT_SEARCHES = 'students:recentSearches';
const RECENT_VIEWED = 'students:recentViewed';
const SAVED_FILTERS = 'students:savedFilters';

function read(key, fallback) {
  try { return JSON.parse(window.localStorage.getItem(key)) || fallback; }
  catch (_) { return fallback; }
}
function write(key, val) {
  try { window.localStorage.setItem(key, JSON.stringify(val)); } catch (_) { /* ignore */ }
}

// --- recent search terms -------------------------------------------------
export function recentSearches() { return read(RECENT_SEARCHES, []); }
export function rememberSearch(term) {
  const t = (term || '').trim();
  if (t.length < 2) return;               // ignore noise / single chars
  const list = recentSearches().filter((x) => x.toLowerCase() !== t.toLowerCase());
  list.unshift(t);
  write(RECENT_SEARCHES, list.slice(0, 8));
}
export function clearSearches() { write(RECENT_SEARCHES, []); }

// --- recently viewed students -------------------------------------------
export function recentViewed() { return read(RECENT_VIEWED, []); }
// Record a student the user opened. `s` = {id, name, student_id, url, photo}.
export function rememberViewed(s) {
  if (!s || !s.id) return;
  const list = recentViewed().filter((x) => String(x.id) !== String(s.id));
  list.unshift({ id: s.id, name: s.name, student_id: s.student_id, url: s.url, photo: s.photo || '' });
  write(RECENT_VIEWED, list.slice(0, 10));
}

// --- named saved filters -------------------------------------------------
export function savedFilters() { return read(SAVED_FILTERS, []); }
// Save the current filter set under a name (replacing any of the same name).
export function saveFilter(name, query) {
  const n = (name || '').trim();
  if (!n) return savedFilters();
  const q = { ...query }; delete q.page;   // page isn't part of a saved filter
  const list = savedFilters().filter((f) => f.name.toLowerCase() !== n.toLowerCase());
  list.unshift({ name: n, query: q });
  const capped = list.slice(0, 12);
  write(SAVED_FILTERS, capped);
  return capped;
}
export function deleteFilter(name) {
  const list = savedFilters().filter((f) => f.name.toLowerCase() !== (name || '').toLowerCase());
  write(SAVED_FILTERS, list);
  return list;
}
