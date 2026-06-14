/*
 * Attendance offline pilot (React + Dexie).
 *
 * Proves the hard part of "offline status": read + write while disconnected.
 *   - Read  : the roster is cached in IndexedDB, so the register opens offline.
 *   - Write : marks made offline go into an outbox queue and the UI updates
 *             optimistically.
 *   - Sync  : the outbox flushes to POST /attendance/api/mark when back online.
 *
 * Isolated page (/attendance-react). The existing Jinja attendance flow is
 * untouched. Class + date are chosen by the server-rendered form; this component
 * takes over the roster + marking for the selected class.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import Dexie from 'dexie';

// ---- IndexedDB (Dexie) ----
const db = new Dexie('edusyncra_attendance');
db.version(1).stores({
  rosters: 'key',          // key = `${assignmentId}|${date}` ; value = roster json
  outbox: '++id',          // queued marks waiting to sync
});
const rosterKey = (a, d) => `${a}|${d}`;

// ---- API helpers (cookie + CSRF, JSON-typed) ----
function csrfToken() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}
async function apiGet(url) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch' },
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}
async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
      'X-Requested-With': 'fetch',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

function StatusPill({ online, pending }) {
  const bg = online ? '#dcfce7' : '#fee2e2';
  const fg = online ? '#166534' : '#991b1b';
  return (
    <span style={{ background: bg, color: fg, borderRadius: 999, padding: '2px 10px', fontSize: 12, fontWeight: 600 }}>
      {online ? 'Online' : 'Offline'}{pending ? ` · ${pending} pending` : ''}
    </span>
  );
}

function App({ assignmentId, date, className }) {
  const [roster, setRoster] = useState(null);     // { students:[{enrollment_id, name, morning_present}], week_id, ... }
  const [present, setPresent] = useState({});     // enrollment_id -> bool
  const [online, setOnline] = useState(navigator.onLine);
  const [pending, setPending] = useState(0);
  const [msg, setMsg] = useState('');
  const [source, setSource] = useState('');       // 'network' | 'cache'

  const refreshPending = useCallback(async () => {
    setPending(await db.outbox.count());
  }, []);

  // Flush the outbox: POST each queued mark; drop it on success.
  const flush = useCallback(async () => {
    const items = await db.outbox.toArray();
    let synced = 0;
    for (const it of items) {
      try {
        await apiPost('/attendance/api/mark', it.payload);
        await db.outbox.delete(it.id);
        synced++;
      } catch (e) {
        break; // stop on first failure (likely offline again); retry later
      }
    }
    await refreshPending();
    if (synced) setMsg(`Synced ${synced} saved mark(s).`);
  }, [refreshPending]);

  // Load roster: network first (cache it), else fall back to the cached copy.
  useEffect(() => {
    let alive = true;
    (async () => {
      const key = rosterKey(assignmentId, date);
      try {
        const data = await apiGet(`/attendance/api/roster?assignment_id=${assignmentId}&date=${encodeURIComponent(date)}`);
        await db.rosters.put({ key, value: data });
        if (!alive) return;
        setRoster(data); setSource('network');
      } catch (e) {
        const cached = await db.rosters.get(key);
        if (!alive) return;
        if (cached) { setRoster(cached.value); setSource('cache'); }
        else setMsg('Couldn’t load this class (no network and nothing cached yet).');
      }
    })();
    return () => { alive = false; };
  }, [assignmentId, date]);

  // Seed the checkbox state from the roster.
  useEffect(() => {
    if (!roster) return;
    const init = {};
    roster.students.forEach((s) => { init[s.enrollment_id] = !!s.morning_present; });
    setPresent(init);
  }, [roster]);

  // Online/offline events + initial flush.
  useEffect(() => {
    refreshPending();
    const up = () => { setOnline(true); flush(); };
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    if (navigator.onLine) flush();
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down); };
  }, [flush, refreshPending]);

  const toggle = (id) => setPresent((p) => ({ ...p, [id]: !p[id] }));
  const allPresent = () => {
    const all = {}; roster.students.forEach((s) => { all[s.enrollment_id] = true; });
    setPresent(all);
  };

  const save = async () => {
    if (!roster) return;
    const presentIds = roster.students.filter((s) => present[s.enrollment_id]).map((s) => s.enrollment_id);
    const payload = { assignment_id: assignmentId, date, session_type: 'morning', present: presentIds, auto_copy: true };

    // Optimistically update the cached roster so reopening reflects the marks.
    const key = rosterKey(assignmentId, date);
    const updated = { ...roster, students: roster.students.map((s) => ({ ...s, morning_present: !!present[s.enrollment_id], afternoon_present: !!present[s.enrollment_id] })) };
    await db.rosters.put({ key, value: updated });

    try {
      const r = await apiPost('/attendance/api/mark', payload);
      setMsg(`Saved ${r.count} student(s) — online.`);
    } catch (e) {
      await db.outbox.add({ payload, ts: Date.now() });
      await refreshPending();
      setMsg('No network — saved to the queue, will sync when you’re back online.');
    }
  };

  if (!roster) return <p style={{ color: '#888' }}>{msg || 'Loading register…'}</p>;
  const presentCount = roster.students.filter((s) => present[s.enrollment_id]).length;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        <strong>{className || roster.class_name}</strong>
        <span style={{ color: '#6b7280' }}>{roster.date}</span>
        <StatusPill online={online} pending={pending} />
        {source === 'cache' && <span style={{ fontSize: 12, color: '#b45309' }}>(showing cached copy)</span>}
        <span style={{ marginLeft: 'auto', fontSize: 13 }}>Present: <b>{presentCount}</b>/{roster.students.length}</span>
      </div>

      {!roster.week_id && (
        <div className="alert alert-warning" style={{ marginBottom: 10 }}>
          This date isn’t in a school week for the term — you can review, but saving is disabled.
        </div>
      )}

      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
        {roster.students.map((s, i) => (
          <label key={s.enrollment_id}
                 style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                          borderTop: i ? '1px solid #f1f5f9' : 'none', cursor: 'pointer',
                          background: present[s.enrollment_id] ? '#f0fdf4' : '#fff' }}>
            <input type="checkbox" checked={!!present[s.enrollment_id]} onChange={() => toggle(s.enrollment_id)}
                   style={{ width: 18, height: 18 }} />
            <span style={{ flex: 1 }}>{s.name}</span>
            <span style={{ fontSize: 12, color: present[s.enrollment_id] ? '#16a34a' : '#dc2626' }}>
              {present[s.enrollment_id] ? 'Present' : 'Absent'}
            </span>
          </label>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
        <button className="btn btn-secondary btn-sm" type="button" onClick={allPresent}>Mark all present</button>
        <button className="btn btn-primary" type="button" onClick={save} disabled={!roster.week_id}>Save register</button>
        {pending > 0 && <button className="btn btn-light btn-sm" type="button" onClick={flush}>Sync now ({pending})</button>}
        {msg && <span style={{ fontSize: 13, color: '#374151' }}>{msg}</span>}
      </div>

      <p style={{ marginTop: 10, fontSize: 12, color: '#16a34a' }}>
        ✓ React + IndexedDB (Dexie). Load once online, then it works offline — marks queue and sync on reconnect.
      </p>
    </div>
  );
}

const mount = document.getElementById('attendance-app');
if (mount) {
  const assignmentId = parseInt(mount.dataset.assignmentId, 10);
  const date = mount.dataset.date;
  const className = mount.dataset.className || '';
  if (assignmentId) createRoot(mount).render(<App assignmentId={assignmentId} date={date} className={className} />);
}
