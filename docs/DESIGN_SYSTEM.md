# Design System — strict specification

The single source of truth for visual design. **Every value below is a CSS custom
property defined in `static/css/style.css :root`** (with dark overrides under
`[data-theme="dark"]`). Components must consume tokens — never hardcode colours,
sizes, radii, shadows or spacing.

> Golden rule: if you're typing a hex code, a `px`/`rem` literal, or a raw `box-shadow`
> in a component, stop — use a token. The only sanctioned exceptions are listed in
> **§Known exceptions**.

---

## Audit findings (current consistency state)

Measured across the app:
- **CSS is token-clean**: 0 hardcoded `box-shadow` literals; the type/spacing/radius/
  shadow/colour scales are fully tokenised and consumed by `.btn/.card/.form-control/
  .badge/.data-table/.modal`.
- **React**: ~724 inline `style={{…}}` (mostly layout: flex/gap/width — acceptable),
  inline `fontSize` literals **now migrated to `--text-*` tokens** (the lone exception is
  one relative `'.8em'` sort-icon glyph, intentionally size-relative to its row), and
  chart-palette hexes (intended — see exceptions).
- **Jinja**: ~979 inline `style=` — most are layout or live in print/export sheets that
  must keep fixed colours; the themeable greys/borders were already swept to tokens.

**Verdict:** the system is consistent at the token + base-component layer. Residual
drift is limited to (a) chart palette colours and (b) fixed colours in print/export
templates — both sanctioned (see exceptions). The React `fontSize` literals have been
migrated to the `--text-*` scale, so typography is now fully tokenised end to end.

---

## 1. Spacing scale  (`--sp-*`, 4px rhythm)

| Token | Value | px |
|---|---|---|
| `--sp-0` | 0 | 0 |
| `--sp-1` | 0.25rem | 4 |
| `--sp-2` | 0.5rem | 8 |
| `--sp-3` | 0.75rem | 12 |
| `--sp-4` | 1rem | 16 |
| `--sp-5` | 1.25rem | 20 |
| `--sp-6` | 1.5rem | 24 |
| `--sp-8` | 2rem | 32 |
| `--sp-10` | 2.5rem | 40 |
| `--sp-12` | 3rem | 48 |

Rules: card padding `--sp-5`; card-header `--sp-4 --sp-5`; page-content `--sp-4`→`--sp-6`
(≥768)→`--sp-8` (≥1200); gaps between controls `--sp-2`; form-group bottom `--sp-4`.
Utilities: `.m*/.p*/.gap*` (`.gap-1..4`, `.p-0..5`, `.mb-0..6`, `.mt-*`).

## 2. Typography scale  (`--text-*`, `--leading-*`, `--fw-*`)

| Token | Value | px | Use |
|---|---|---|---|
| `--text-xs` | 0.75rem | 12 | badges, captions, table headers |
| `--text-sm` | 0.8125rem | 13 | buttons, labels, table body, secondary |
| `--text-base` | 0.9375rem | 15 | body default |
| `--text-md` | 1rem | 16 | h4, lead inputs |
| `--text-lg` | 1.125rem | 18 | h3 |
| `--text-xl` | 1.375rem | 22 | h1 (mobile), h2 (desktop) |
| `--text-2xl` | 1.75rem | 28 | h1 (desktop) |
| `--text-3xl` | 2.25rem | 36 | hero figures |

Line-height: `--leading-tight 1.25` (headings), `--leading-snug 1.4`, `--leading-normal 1.6` (body).
Weight: `--fw-regular 400`, `--fw-medium 500`, `--fw-semibold 600`, `--fw-bold 700`.
Fonts: body `--font-sans` (DM Sans); headings `--font-display` (Space Grotesk), `letter-spacing:-0.01em`.
Headings use the scale responsively (see `h1..h4` rules). Utilities: `.text-xs/.text-sm/.text-md/.text-lg`, `.fw-medium/-semibold/-bold`.

## 3. Radius scale  (`--radius-*`)

| Token | Value | Use |
|---|---|---|
| `--radius-sm` | 7px | badges' inner bits, small chips, inputs-in-tables |
| `--radius-md` | 10px | **buttons, inputs, dropdowns** (default) |
| `--radius-lg` | 14px | **cards, modals, menus** |
| `--radius-xl` | 20px | large feature panels |
| `--radius-full` | 9999px | pills, badges, avatars, icon buttons |

## 4. Shadow / elevation scale  (`--shadow-*`)

Premium, barely-there; **cards rest on a hairline border + `--shadow-xs`**, elevation comes from the border first.

| Token | Use |
|---|---|
| `--shadow-xs` | resting cards |
| `--shadow-sm` | card/stat-card hover, header underline |
| `--shadow-md` | popovers, raised cards |
| `--shadow-lg` | dropdown menus, modals |
| `--shadow-xl` | rare, top-level overlays |

Focus uses a dedicated ring: `--ring` = `0 0 0 3px var(--primary-alpha)`.

## 5. Colour tokens

Brand: `--primary` `#0d6a4e` (dark `#10b981`), `--primary-hover`, `--primary-light`, `--primary-alpha`; `--accent` `#d4a419` (dark `#fbbf24`).
Status (base + light tint pairs): `--success #198754`/`--success-light`; `--info #0e7490`/`--info-light`; `--warning #e67e22`/`--warning-light`; `--danger #dc2626`/`--danger-light`.
Neutrals — **cool slate** `--gray-50 … --gray-900` (`#f8fafc → #0f172a`).
Surfaces: `--bg-body`, `--bg-card`, `--bg-sidebar`. Text: `--text-primary`, `--text-secondary`, `--text-muted` (all ≥4.5:1 AA on their backgrounds, light + dark). Borders: `--border-color` (hairline), `--border-light`.
Dark mode re-maps these under `[data-theme="dark"]`; never hardcode a colour that won't follow the theme. Utilities: `.text-muted/-secondary/-primary/-success/-danger/-warning/-info`, `.bg-card/-muted`.

## 6. Z-index & motion

Z-layers: `--z-sticky 100`, `--z-dropdown 1000`, `--z-overlay 1040`, `--z-drawer 1045`, `--z-modal 1050`, `--z-toast 1080`, `--z-progress 2000`. Never use ad-hoc z-index.
Motion: `--transition 140ms` / `--transition-slow 220ms` (`cubic-bezier(0.4,0,0.2,1)`). All animations sit under `@media (prefers-reduced-motion: reduce)`.

---

## Component rules

**Buttons** (`.btn` + one variant). Radius `--radius-md`, weight semibold, `min-height 40px` (`.btn-sm` 32, `.btn-lg` 48), gap `--sp-2`. Variants: `primary, secondary, success, info, warning, danger, light, outline-primary`. Hover = subtle shade (`filter`), active = `scale(0.98)` — **no translateY bounce**. Always `:focus-visible` → `--ring`. Loading: `loading` prop / `.is-loading` shows a spinner. One primary action per view; destructive actions are `danger` and confirmed via the themed modal.

**Inputs** (`.form-control`). Radius `--radius-md`, `min-height 42px`, `--text-sm`, border `--border-color`; hover darkens to `--gray-300`; focus → `--primary` border + `--ring`. Labels via `.form-label` (or `<Form.jsx>` `TextField/SelectField` which wire `htmlFor`/`aria-*`). Inline errors: `.field-error` + `.is-invalid`. Every `<select>` must have an accessible name (auto-applied by `labelSelects()` in `app.js`).

**Cards** (`.card` / `.card-header` / `.card-body`). Radius `--radius-lg`, hairline border + `--shadow-xs`, hover `--shadow-sm` + `--gray-300` border. Header bg `--gray-50`, title `<h3>` with a `--primary` icon. Use `FormCard` (`collapsible`) for optional form sections.

**Tables** (`.data-table` via the React `<Table>`). `--text-sm`; header `--text-xs` uppercase, `--text-muted`, `--gray-50` bg; row hover `--primary-light`; lighter `--border-light` separators. Responsive: `.table-stack` + `data-label` (cards on mobile). Opt-ins: `pageSize` (client pagination), `sticky`+`maxHeight` (frozen header), `sortable` columns. Long lists → `.cap-list` + `[data-cap-toggle]`.

**Badges** (`.badge` + variant). Radius `--radius-full`, `--text-xs`, semibold, hairline definition border, soft tint bg with AA-dark text per status. Use for status only — not as buttons.

**Icons** Font Awesome solid; `aria-hidden="true"` when decorative; `0.85em` inside buttons; `18px` slot in nav/menus. Action icons consistent: view `fa-eye`, edit `fa-edit`, delete `fa-trash`, add `fa-plus`, more `fa-ellipsis-vertical`.

**Overflow / secondary actions** Row-level secondary + destructive actions go in a `.row-menu` (`⋯`) — keep list rows to primary actions only.

**Modals / dialogs** `.modal` (`--z-modal`) + `.modal-content` (radius `--radius-lg`, `--shadow-lg`, fade+scale in). Confirmations use the themed dialog — **never** `window.confirm/alert` (vanilla pages use `window.themedConfirm` / `[data-confirm]`; React uses `confirm()` from `components/ui.jsx`).

**States** Empty → `.empty-state` (icon in a `--gray-100` medallion + title + muted body + optional CTA) or React `<Empty>/<EmptyState>`. Loading → `<Spinner>` / `<Skeleton>` / `#navProgress`; submit buttons show a spinner. Error → `<ErrorState>` / `.alert` with a retry where it makes sense. Disabled → opacity 0.55, `not-allowed`.

**Tap targets / focus / icons** Interactive targets ≥40px (header icon buttons, nav links, inputs); global `:focus-visible` ring; skip-to-content link in the shell.

---

## Enforcement & known exceptions

**Do**: consume tokens; reuse `Form.jsx`, `<Table>/<Pagination>/<FileUpload>/<Modal>/<Empty>` from `components/ui.jsx`; add new shared primitives rather than re-rolling.
**Don't**: hardcode hex/px/shadow/z-index in components; re-implement an existing primitive; use native `alert/confirm/prompt`; put `role="button"` on an `<li>`.

**Sanctioned exceptions (do not "fix"):**
- **Chart palettes** (`#4e73df`, `#11998e`, `#e74a3b`, `#f6c23e`, `#1cc88a`, `#7e6cf0`, `#fd7e14`, `#20c997`, …) — Chart.js renders to `<canvas>`; explicit data colours are required and don't theme.
- **Print / export / PDF-mirror templates** (report cards, broadsheets, timetable sheet, receipts, scratchcards, the JAMB image export) — must use **fixed** colours so the printed artefact looks the same regardless of app theme.
- **Auth / portal standalone pages** keep their own fixed gradients.

**Resolved:** the React inline `fontSize` literals have been migrated to the `--text-*` scale (snapped to the nearest token), so typography is fully tokenised across CSS, Jinja, and React. The only remaining size literal is one relative `'.8em'` sort-icon glyph in the shared `<Table>`, kept relative on purpose.
