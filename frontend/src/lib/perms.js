// Permission-aware UI helpers. The server injects a `perms` block into every
// React section payload (utils/spa.current_section_perms):
//   { module, level, write, read_only, subs: { <sub>: { level, write } } }
// so the client can hide actions the user isn't allowed to perform. The server
// still enforces every write — these helpers are purely about not SHOWING a
// button that would fail.

// May the current user make changes here? Pass a sub-section key to check a
// specific slice (e.g. canWrite(d, 'payments')); omit it for whole-module write.
// Fails open when no perms block is present (older payloads) — the server gate
// still applies.
export function canWrite(d, sub) {
  const p = d && d.perms;
  if (!p) return true;
  if (sub && p.subs && p.subs[sub]) return !!p.subs[sub].write;
  return p.write !== false;
}

// True when the user may only view this section (no create/edit/delete).
export function isReadOnly(d) {
  return !canWrite(d);
}
