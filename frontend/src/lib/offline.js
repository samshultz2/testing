// Offline data layer shared by every attendance screen:
//   - rosters/grids cache (read offline)
//   - an outbox of pending writes (write offline) that flushes on reconnect,
//     splitting transient failures (retry) from permanent ones (quarantine).
import Dexie from 'dexie';
import { apiPost, isPermanent } from './api';

export const db = new Dexie('edusyncra_attendance');
db.version(2).stores({
  rosters: 'key',   // arbitrary cache: `${kind}|...` -> value
  outbox: '++id',   // { url, payload, ts } pending writes
  failed: '++id',   // { url, payload, reason, ts } permanently rejected
});

export async function requestPersistence() {
  if (navigator.storage && navigator.storage.persist) {
    try { await navigator.storage.persist(); } catch (_) {}
  }
}

export const cachePut = (key, value) => db.rosters.put({ key, value });
export const cacheGet = async (key) => {
  const r = await db.rosters.get(key);
  return r ? r.value : null;
};

export const enqueue = (url, payload) => db.outbox.add({ url, payload, ts: Date.now() });

let flushing = false;
export async function flushOutbox() {
  if (flushing) return { synced: 0 };
  flushing = true;
  let synced = 0;
  try {
    const items = await db.outbox.orderBy('id').toArray();
    for (const it of items) {
      try {
        await apiPost(it.url, it.payload);
        await db.outbox.delete(it.id);
        synced++;
      } catch (e) {
        if (isPermanent(e)) {            // poison entry — quarantine, keep going
          await db.failed.add({ url: it.url, payload: it.payload, reason: e.message || ('HTTP ' + e.status), ts: Date.now() });
          await db.outbox.delete(it.id);
          continue;
        }
        break;                            // transient — stop, retry later
      }
    }
  } finally {
    flushing = false;
  }
  return { synced };
}

export const counts = async () => ({ pending: await db.outbox.count(), failed: await db.failed.count() });
export const failedItems = () => db.failed.toArray();
export const retryFailed = async (f) => {
  await db.outbox.add({ url: f.url, payload: f.payload, ts: Date.now() });
  await db.failed.delete(f.id);
};
export const discardFailed = (id) => db.failed.delete(id);
