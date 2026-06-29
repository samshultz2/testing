/*
 * Attendance offline pilot (React + Dexie) — hardened.
 *
 *   Read  : roster cached in IndexedDB -> register opens offline.
 *   Write : offline marks go to an outbox; UI updates optimistically.
 *   Sync  : outbox flushes to POST /attendance/api/mark on reconnect, on load,
 *           and on a 30s timer. Failures are split into:
 *             - transient (offline / 5xx)  -> kept, retried later
 *             - permanent (4xx, e.g. no school week / forbidden) -> quarantined
 *               to a "failed" list so one bad entry can't block the queue.
 *   Durable: requests persistent storage so the outbox isn't evicted.
 *
 * Isolated page (/attendance/react); the existing Jinja flow is untouched.
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import Dexie from 'dexie';

const db = new Dexie('edusyncra_attendance');
db.version(2).stores({
  rosters: 'key',     // `${assignmentId}|${date}` -> roster json
  outbox: '++id',     // queued marks pending sync
  failed: '++id',     // quarantined marks that returned a permanent error
});
const rosterKey = (a, d) => `${a}|${d}`;

function csrfToken() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}
async function apiGet(url) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch' },
  });
  if (!res.ok) { const e = new Error('HTTP ' + res.status); e.status = res.status; throw e; }
  return res.json();
}
async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch' },
    body: JSON.stringify(body),
  });
  if (!res.ok) { const e = new Error('HTTP ' + res.status); e.status = res.status; throw e; }
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
  const [roster, setRoster] = useState(null);
  const [present, setPresent] = useState({});
  const [online, setOnline] = useState(navigator.onLine);
  const [pending, setPending] = useState(0);
  const [failed, setFailed] = useState([]);
  const [msg, setMsg] = useState('');
  const [source, setSource] = useState('');
  const flushing = useRef(false);

  const refresh = useCallback(async () => {
    setPending(await db.outbox.count());
    setFailed(await db.failed.toArray());
  }, []);

  // Flush oldest-first. Transient errors stop the run (retry later); permanent
  // (4xx) errors quarantine the entry so it can't block everything behind it.
  const flush = useCallback(async () => {
    if (flushing.current) return;
    flushing.current = true;
    try {
      const items = await db.outbox.orderBy('id').toArray();
      let synced = 0;
      for (const it of items) {
        try {
          await apiPost('/attendance/api/mark', it.payload);
          await db.outbox.delete(it.id);
          synced++;
        } catch (e) {
          if (e.status && e.status >= 400 && e.status < 500) {
            await db.failed.add({ payload: it.payload, reason: 'HTTP ' + e.status, ts: Date.now() });
            await db.outbox.delete(it.id);
            continue;                      // skip the poison entry, keep going
          }
          break;                           // transient — leave queued, retry later
        }
      }
      await refresh();
      if (synced) setMsg(`Synced ${synced} saved mark(s).`);
    } finally {
      flushing.current = false;
    }
  }, [refresh]);

  // Ask the browser to keep our storage (so the outbox can't be evicted).
  useEffect(() => {
    if (navigator.storage && navigator.storage.persist) navigator.storage.persist();
  }, []);

  // Load roster: network first (cache it), else the cached copy.
  useEffect(() => {
    let alive = true;
    (async () => {
      const key = rosterKey(assignmentId, date);
      try {
        const data = await apiGet(`/attendance/api/roster?assignment_id=${assignmentId}&date=${encodeURIComponent(date)}`);
        await db.rosters.put({ key, value: data });
        if (alive) { setRoster(data); setSource('network'); }
      } catch (e) {
        const cached = await db.rosters.get(key);
        if (!alive) return;
        if (cached) { setRoster(cached.value); setSource('cache'); }
        else setMsg('Couldn’t load this class (no network and nothing cached yet).');
      }
    })();
    return () => { alive = false; };
  }, [assignmentId, date]);

  useEffect(() => {
    if (!roster) return;
    const init = {};
    roster.students.forEach((s) => { init[s.enrollment_id] = !!s.morning_present; });
    setPresent(init);
  }, [roster]);

  // online/offline + initial flush + 30s retry timer.
  useEffect(() => {
    refresh();
    const up = () => { setOnline(true); flush(); };
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    if (navigator.onLine) flush();
    const timer = setInterval(() => { if (navigator.onLine) flush(); }, 30000);
    return () => {
      window.removeEventListener('online', up);
      window.removeEventListener('offline', down);
      clearInterval(timer);
    };
  }, [flush, refresh]);

  const toggle = (id) => setPresent((p) => ({ ...p, [id]: !p[id] }));
  const allPresent = () => {
    const all = {}; roster.students.forEach((s) => { all[s.enrollment_id] = true; });
    setPresent(all);
  };

  const save = async () => {
    if (!roster) return;
    const presentIds = roster.students.filter((s) => present[s.enrollment_id]).map((s) => s.enrollment_id);
    const payload = { assignment_id: assignmentId, date, session_type: 'morning', present: presentIds, auto_copy: true };

    // optimistic cache update so reopening reflects the marks
    const key = rosterKey(assignmentId, date);
    const updated = { ...roster, students: roster.students.map((s) => ({ ...s, morning_present: !!present[s.enrollment_id], afternoon_present: !!present[s.enrollment_id] })) };
    await db.rosters.put({ key, value: updated });

    try {
      const r = await apiPost('/attendance/api/mark', payload);
      setMsg(`Saved ${r.count} student(s) — online.`);
    } catch (e) {
      if (e.status && e.status >= 400 && e.status < 500) {
        setMsg(`Couldn’t save (HTTP ${e.status}) — check the date/permission; not queued.`);
        return;
      }
      await db.outbox.add({ payload, ts: Date.now() });
      await refresh();
      setMsg('No network — saved to the queue, will sync when you’re back online.');
    }
  };

  const retryFailed = async (f) => {
    await db.outbox.add({ payload: f.payload, ts: Date.now() });
    await db.failed.delete(f.id);
    await refresh();
    if (navigator.onLine) flush();
  };
  const discardFailed = async (f) => { await db.failed.delete(f.id); await refresh(); };

  if (!roster) return <p style={{ color: '#888' }}>{msg || 'Loading register…'}</p>;
  const presentCount = roster.students.filter((s) => present[s.enrollment_id]).length;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        <strong>{className || roster.class_name}</strong>
        <span style={{ color: 'var(--text-muted)' }}>{roster.date}</span>
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
            <span style={{ fontSize: 12, color: present[s.enrollment_id] ? 'var(--success)' : '#dc2626' }}>
              {present[s.enrollment_id] ? 'Present' : 'Absent'}
            </span>
          </label>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <button className="btn btn-secondary btn-sm" type="button" onClick={allPresent}>Mark all present</button>
        <button className="btn btn-primary" type="button" onClick={save} disabled={!roster.week_id}>Save register</button>
        {pending > 0 && <button className="btn btn-light btn-sm" type="button" onClick={flush}>Sync now ({pending})</button>}
        {msg && <span style={{ fontSize: 13, color: '#374151' }}>{msg}</span>}
      </div>

      {failed.length > 0 && (
        <div className="alert alert-danger" style={{ marginTop: 12 }}>
          <b>{failed.length} mark(s) couldn’t sync</b> (a server rejected them):
          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {failed.map((f) => (
              <li key={f.id} style={{ fontSize: 13, margin: '4px 0' }}>
                {f.payload.date} — {f.reason}
                <button className="btn btn-light btn-sm" style={{ marginLeft: 8 }} type="button" onClick={() => retryFailed(f)}>Retry</button>
                <button className="btn btn-light btn-sm" style={{ marginLeft: 4 }} type="button" onClick={() => discardFailed(f)}>Discard</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p style={{ marginTop: 10, fontSize: 12, color: 'var(--success)' }}>
        ✓ React + IndexedDB (Dexie), persistent storage. Marks queue offline and sync on reconnect; permanent errors are quarantined, not retried forever.
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
