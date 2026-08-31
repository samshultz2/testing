# UI Component Architecture & Guide

Production guide to the shared React UI layer used by every section app in this
project (`frontend/src/`). It documents the component architecture, the
props/API of each primitive, copy-paste usage examples, and the best practices
that keep ~30 section bundles consistent, accessible, and small.

> Audit context: a full reusability + accessibility audit (June 2026) found the
> foundation solid but enforcement weak — no shared modal, ~50 native
> `window.confirm()` calls, and a keyboard-inaccessible autocomplete. This guide
> reflects the components added/upgraded to close those gaps. See
> "Migration status" at the end for what remains.

---

## 1. Architecture

### The big picture — hybrid Jinja + React islands

Each feature is a **server-rendered Jinja shell** that mounts a single React
**island**. There is no client router and no global store; the server is the
source of truth.

```
Browser ── GET /students ──► Flask renders templates/students/*.html
            (shell + <script id="students-data">{…JSON…}</script>)
                              │
                              ▼
           students-app.js (esbuild IIFE) hydrates #students-app
                              │
            soft-nav / filter / page  ── fetch(?…, X-Requested-With) ──► same route returns JSON
                              ▼
                    useSection() swaps payload in place (no reload)
```

- **One bundle per section** (`frontend/src/<name>-app.jsx` → `static/js/react/<name>-app.js`),
  built by esbuild and **committed** (the deploy target only `git pull`s).
- **Initial data** is embedded as JSON in a `<script>` tag and parsed at mount;
  **subsequent** data comes from the same routes via `fetch` (see
  `utils/spa.render_or_json`).
- **Shared code** lives in two places:
  - `frontend/src/components/` — visual + interaction primitives (`ui.jsx`, `Form.jsx`).
  - `frontend/src/lib/` — non-visual hooks/utilities (`section.js`, `api.js`,
    `forms.js`, `hooks.js`, `offline.js`, `format.js`, `draft.js`).

### Layered design

```
┌─────────────────────────────────────────────────────────────┐
│ Section apps        students/, finance/, hr/, results/, …     │  feature logic
├─────────────────────────────────────────────────────────────┤
│ Composite components ImportModal, ExportModal, Customize, …   │  feature UI
├─────────────────────────────────────────────────────────────┤
│ Primitives          components/ui.jsx + components/Form.jsx   │  reusable, themed, a11y
├─────────────────────────────────────────────────────────────┤
│ Hooks & utils       lib/section, lib/api, lib/forms, lib/hooks│  data, nav, offline
├─────────────────────────────────────────────────────────────┤
│ Theme               static/css/style.css (.btn, .badge, .card)│  single source of styling
└─────────────────────────────────────────────────────────────┘
```

**Principle: primitives render the app's existing CSS classes** (`.btn`,
`.form-control`, `.badge`, `.card`) rather than inventing styles. A theme change
in `style.css` flows everywhere; primitives only own *behaviour* (focus,
keyboard, ARIA, state) and a few scoped inline styles where no class exists.

---

## 2. Component catalog & API

All exported from `frontend/src/components/ui.jsx` unless noted.

### Layout & navigation
| Component | Purpose | Key props |
|---|---|---|
| `SectionShell` | Wraps an island; intercepts internal `<a href="/…">` for soft-nav; hosts the `ErrorBoundary` | `go`, `children` |
| `ErrorBoundary` | Catches render crashes → friendly panel + reports to the server error log | `children` |
| `PageHeader` | Standard page title + icon + right-aligned actions | `title`, `icon`, `actions` |
| `SectionTabs` | Sub-navigation tab row (`.fin-tabs`) | `tabs: [[key,icon,label]]`, `urls`, `active`, `go?` |
| `L` / `Nav` | In-section link (no reload, still a real `<a>` for ctrl/middle-click) | `href`, `className`, `children` |
| `Toolbar` | Flex filter/action row that wraps on mobile | `children` |
| `Field` | Label + control wrapper for toolbars | `label`, `htmlFor`, `grow` |
| `TableWrap` | Keyboard-focusable, labelled horizontal-scroll region for wide tables | `label`, `maxHeight`, `children` |

### State feedback (loading / empty / error / offline)
| Component | When to use | Key props |
|---|---|---|
| `Spinner` | While fetching (`role=status aria-live`) | `label` |
| `EmptyState` | Zero rows / nothing selected yet | `icon`, `title`, `hint`, `action` |
| `Empty` | Classic `.empty-state` block variant | `icon`, `title`, `children` |
| `ErrorState` | A fetch failed (`role=alert` + retry) | `title`, `detail`, `onRetry` |
| `OfflineRequired` | Screen needs the network | `what` |
| `Banner` | Inline dismissible status bar | `tone`, `onClose`, `children` |
| `Toast` | Floating auto-dismiss confirmation (no scroll) | `tone`, `duration`, `onClose`, `children` |
| `FailedMarks` | Offline outbox items the server rejected | `items`, `onRetry`, `onDiscard` |

### Inputs & forms (`components/Form.jsx`)
| Component | Purpose | Key props |
|---|---|---|
| `TextField` | Labelled text input, wired `aria-*` | `label`, `value`, `onChange`, `required`, `hint`, `error`, `type` |
| `TextAreaField` | Labelled textarea | same + `rows` |
| `SelectField` | Labelled select; accepts `['a']` or `[{value,label}]` | `label`, `value`, `onChange`, `options`, `placeholder`, `required`, `hint`, `error` |
| `FormCard` | `.card` with icon header | `icon`, `title`, `note`, `children` |
| `Select` (ui.jsx) | Bare select for toolbars (no `.form-group`) | `id`, `value`, `onChange`, `options`, `placeholder`, `disabled` |
| `Autocomplete` (ui.jsx) | Type-ahead picker over a JSON search URL; **full keyboard + listbox ARIA** | `label`, `url`, `onPick(id)`, `initialText`, `required`, `minChars` |

### Actions & overlays
| Component | Purpose | Key props |
|---|---|---|
| `Button` | Themed button (`forwardRef`) | `variant`, `size`, `…buttonProps` |
| `Modal` | **Accessible dialog** (focus trap, Escape, scroll-lock, focus restore, portal) | `title`, `icon`, `onClose`, `footer`, `size`, `closeOnBackdrop`, `initialFocusRef`, `ariaLabel` |
| `confirm()` | Promise-based, themed replacement for `window.confirm` | `(message)` or `({title,message,confirmText,cancelText,tone,icon})` → `Promise<boolean>` |

### Data display
| Component | Purpose | Key props |
|---|---|---|
| `Badge` | Status label mapped to `.badge-*` theme classes | `tone`, `icon`, `children`, `title` |
| `Pill` | Rounded inline tag (inline-styled tones) | `tone`, `children` |
| `StatCards` | Headline metric cards | `items: [{value,label,primary?}]` |
| `InfoGrid` | Compact label/value grid | `items: [{label,value,tone?}]` |
| `PerfBands` | Excellent/Good/Fair/Poor bands | `bands` |
| `SectionTitle` | `h3` with optional icon | `icon`, `children` |
| `AmPm` | AM/PM present/absent ticks | `am`, `pm` |

---

## 3. The flagship primitives (added/upgraded)

### `Modal` — one accessible dialog for everything

Before, three modals (`ImportModal`, `ExportModal`, dashboard `Customize`)
hand-rolled their own backdrop. None trapped focus, restored focus, locked body
scroll, or closed on Escape. `Modal` centralises all of that.

**What it handles for you**
- Renders into a **portal at `<body>`** → never clipped by an ancestor's
  `overflow`/`transform`.
- **Focus moves in** on open (your `initialFocusRef`, else first focusable);
  **restored to the trigger** on close.
- **Focus trap** on Tab / Shift+Tab.
- **Escape** closes; **background scroll locked** while open.
- **Backdrop click** closes — but a drag that *starts inside* the panel does not
  (uses `mousedown` target check, so selecting text and releasing on the
  backdrop won't dismiss a half-filled form).
- `role="dialog"`, `aria-modal`, and `aria-labelledby` wired to the title.

```jsx
import { Modal, Button } from '../components/ui';

function EditClass({ onClose, onSave }) {
  const [name, setName] = useState('');
  return (
    <Modal title="Edit class" icon="fa-pen" size="md" onClose={onClose}
           footer={<>
             <Button variant="secondary" onClick={onClose}>Cancel</Button>
             <Button variant="primary" onClick={() => onSave(name)}>Save</Button>
           </>}>
      <TextField label="Class name" value={name} onChange={setName} />
    </Modal>
  );
}

// render conditionally from the parent:
{editing && <EditClass onClose={() => setEditing(false)} onSave={save} />}
```

Sizes: `sm` 420 · `md` 560 · `lg` 760 · `xl` 960 (px max-width, fluid below).

### `confirm()` — kill `window.confirm`

Native `window.confirm` is blocking, unthemed, and can't be styled or branded.
`confirm()` is a **drop-in promise** that renders an accessible `Modal`.

```jsx
import { confirm } from '../components/ui';

// simplest — same call site shape as window.confirm, just awaited:
onClick={async () => {
  if (await confirm('Delete this student?')) doDelete();
}}

// destructive action with a branded button + danger tone:
if (await confirm({
  title: 'Delete student',
  message: `Permanently delete ${name}? This cannot be undone.`,
  confirmText: 'Delete permanently',
  tone: 'danger',
})) purge();
```

Resolves `true` on confirm, `false` on Cancel / Escape / backdrop. The Confirm
button receives initial focus, so **Enter confirms** and **Escape cancels** —
matching `window.confirm` semantics while being fully themed and accessible.

### `Autocomplete` — now keyboard-operable

The shared type-ahead is reused by student/parent pickers, issue forms, finance,
etc. It now implements the WAI-ARIA combobox/listbox pattern:

- `role="combobox"` input with `aria-expanded`, `aria-controls`,
  `aria-activedescendant`; `role="listbox"` popup with `role="option"` items.
- **↓/↑** move the active option, **Enter** selects it, **Escape** closes.
- Mouse hover and keyboard share one highlight (`aria-selected` + `.active`).

API is unchanged — existing call sites get the keyboard support for free:

```jsx
<Autocomplete label="Student" required url="/api/students/search"
              onPick={(id) => setStudentId(id)} minChars={2} />
```

---

## 4. The standard module recipe

Every section app should follow the same **idle → loading → (data | empty | error)**
shape so behaviour is predictable across the product.

```jsx
import { useSection, NavCtx } from '../lib/section';
import { Spinner, EmptyState, ErrorState, Banner, Button, confirm } from '../components/ui';

export default function App({ initial }) {
  const { data, loading, go, refresh } = useSection(initial);
  const [msg, setMsg] = useState(null);

  if (loading && !data) return <Spinner label="Loading…" />;
  if (data?.error)      return <ErrorState detail={data.error} onRetry={refresh} />;

  const rows = data?.rows || [];
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}

      {rows.length === 0
        ? <EmptyState icon="fa-inbox" title="Nothing here yet"
                      hint="Items you add will show up here." />
        : <List rows={rows} />}
    </NavCtx.Provider>
  );
}
```

Data/mutation helpers (`lib/`):
- `useSection(initial)` → `{ data, loading, go, refresh, setData }` — soft-nav + in-place refresh.
- `submitJson(url, fields)` → normalised `{ ok, status, error, message, … }` — branch on `ok`.
- `apiGet(url)` / `apiPost(url, body)` — JSON fetch with CSRF + offline-aware errors.
- `useOnline()`, `useSync()` — connectivity + offline outbox (attendance).

---

## 5. Best practices

**Reuse before you build.** If a primitive exists, use it. The four most-skipped:
`Button` (not `<button className="btn …">`), `SelectField`/`TextField` (not raw
labelled inputs), `Badge` (not `<span className="badge …">`), and `EmptyState`
(not inline `.empty-state`). Consistency here is what makes a theme change a
one-file change.

**Every async surface needs three states.** Loading (`Spinner`), empty
(`EmptyState`), and error (`ErrorState`/`Banner`). Never render a bare list that
flashes empty then fills, and never swallow a failed fetch.

**Confirm with `confirm()`, never `window.confirm`.** Convert the handler to
`async` and `await` it. Use `tone: 'danger'` + an explicit `confirmText` for
destructive actions.

**Dialogs use `Modal`.** Don't hand-roll a backdrop — you'll forget focus
management. Pass actions via the `footer` slot; pass `initialFocusRef` when a
specific control should receive focus.

**Accessibility checklist (per PR):**
- Decorative `<i className="fas …">` gets `aria-hidden="true"`.
- Icon-only buttons get an `aria-label`.
- Anything clickable is a `<button>` (or has `role`+`tabIndex`+key handler).
- Inputs have an associated `<label>` (use the `Form.jsx` fields) or `aria-label`.
- Async status updates live in a `role="status"`/`role="alert"` region (the
  feedback primitives already do this).

**Responsive by default.** Wrap wide tables in `<TableWrap label="…">` (a
labelled, keyboard-scrollable region) or the `.table-stack` mobile pattern.
Toolbars use `Toolbar`/`flexWrap`. Test at a 375px viewport.

```jsx
<TableWrap label="Class timetable" maxHeight={480}>
  <table className="data-table">…</table>
</TableWrap>
```

**Keep bundles lean.** Primitives are shared source, so esbuild dedupes them per
bundle; prefer them over per-module copies. No new heavy dependencies — the
stack is React + Dexie only.

---

## 6. Migration status

**Done**
- `Modal` added; `ImportModal`, `ExportModal`, dashboard `Customize` refactored onto it.
- `confirm()` added and **rolled out to every module** — all ~50 `window.confirm`
  call sites across the app now use the accessible dialog. (`!await confirm(x)`
  parses as `!(await confirm(x))`, so the conversion needed no rewrapping; the
  DB-restore form keeps a synchronous `preventDefault` and submits natively only
  after the async confirm resolves.)
- `Autocomplete` upgraded to full keyboard + listbox ARIA.
- `Button` converted to `forwardRef`; `Badge` and `TableWrap` primitives added.
- **`aria-hidden="true"` applied to all 671 decorative FontAwesome icons**
  project-wide (two brace-aware passes); nameless icon-only buttons given
  `aria-label`. `TableWrap` applied to the timetable grid as the reference.

- All **truly nameless icon-only** buttons/links now have an `aria-label`
  (icon→label map for plain `<a>`/`<button>`; `title` added to the custom `<A>`
  links, which surfaces as the accessible name). Icon-only elements that already
  had a `title` were left as-is — `title` is the accessible-name fallback.
- Inline `.empty-state` blocks consolidated onto `<Empty>` (students, sales,
  settings, communication). Dashboard now surfaces a refresh failure via `Toast`
  instead of silently keeping stale data.
- **Notifications dropdown is mobile-responsive**: on ≤640px it drops to a
  fixed, near-full-width sheet under the header instead of an absolutely
  positioned 330px box that overflowed the viewport.

**Recommended next (low priority)**
- `<Badge>` exists and renders the same `.badge-*` classes; converting the
  ~100 existing inline `.badge` spans is pure churn (identical output), so it's
  deferred — use `<Badge>` in new/touched code.
- Wrap the remaining wide tables in `<TableWrap>` (most already scroll via
  `.matrix-wrap`/`overflow:auto`, but they aren't keyboard-focusable regions).
