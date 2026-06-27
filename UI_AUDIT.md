# XLink Frontend Audit

Prioritized. Severity tags: [CRITICAL] [HIGH] [MED] [LOW]. All paths absolute. Line refs from findings.

---

## 1) UI Bugs

### [CRITICAL]
- **Broken indentation in console screen ternary** — `components/console/console.tsx:139`. Ternary `{active === "Overview" ? (` not aligned to opening `<div>` (138). Fix: prefix line 139 with two spaces to align under the div.

### [HIGH]
- **Stale alerts always in DOM (login)** — `components/console/screens/login.tsx:58-86`. Both success (59-72) and error (73-86) alert containers always render; only `className` is conditional. Screen readers announce hidden alerts; DOM bloat. Fix: gate each alert on `alert` — `{alert ? (<div className="warp-alert ...">…</div>) : null}`. Skip the element entirely when null.
- **Index keys in table header** — `components/console/screens/warp-table.tsx:165-166`. `cols.map((c, i) => <span key={i}…>`. Headers are static so impact is low, but standardize. Fix: pass stable keys alongside cols, or document headers as non-reorderable.
- **Index keys in table row cells** — `components/console/screens/warp-table.tsx:201-204`. `cells.map((c, i) => <span key={i}…>`. On row content change React preserves wrong DOM → stale interactive cell state. Fix: accept `cellKeys[]` or give cells stable `id`; key on that.
- **Fragile keys in subscription QR modal** — `components/console/screens/users/access.tsx:358-359`. Links keyed `${link}-${i}`; QR items keyed `${it.label}-${it.value}` (435) — breaks on special chars/dupes. Fix: assign stable UUIDs at query time, or `key={`${link.split("://")[0]}-${i}`}`.

### [MED]
- **Missing aria-label on table-row button** — `components/console/screens/users/index.tsx:372-383`. Row has `role="button"` + `tabIndex={0}` but no label. Fix: `aria-label={`View details for user ${u.username}`}`.
- **Dialog roles confused** — `components/ui/dialog.tsx:118-126`. Form has `role="dialog"`; overlay has `role="presentation"`. Fix: keep `role="dialog"` + add `aria-modal="true"` on the form; change overlay to `role="none"`.
- **Mobile scrim not Escape-closable** — `components/console/console.tsx:104-110`. Scrim button (`aria-label="Close menu"`) closes on click only. Fix: add `onKeyDown={(e) => e.key === "Escape" && setNavOpen(false)}`.

### [LOW]
- **Scrim not focused on open** — `components/console/console.tsx:104-111`. Conditional render is fine; opened scrim never receives focus. Fix: `autoFocus`, or `useEffect(() => scrimRef.current?.focus(), [navOpen])`.

---

## 2) Icon Unification → lucide-react

Replace string-based `fa-*` + `resolveIcon()` indirection with direct lucide imports.

### [HIGH] — exact swaps
| File:line | Current | Replace with |
|---|---|---|
| `components/console/screens/admins/index.tsx:91` | `icon="fa-user-shield"` (→ via resolver) | `<ShieldCheck size={28} />` |
| `components/console/screens/nodes/index.tsx:119` | `icon="fa-server"` (→ Box) | `<Package size={28} />` |
| `components/console/screens/profiles/index.tsx:101` | `icon="fa-globe"` (→ ServerCog) | `<Globe size={28} />` |
| `components/console/screens/users/index.tsx:221` | `icon="fa-user"` (→ User) | `<User size={28} />` |
| `components/console/screens/groups/index.tsx:101` | `icon="fa-layer-group"` (→ Server) | `<Layers size={28} />` |

### [HIGH] — root cause
- **WarpEmpty takes `icon?: string`** — `components/console/screens/warp-table.tsx:324`. Refactor to `icon?: LucideIcon`, render `<icon size={28} />` directly (warp-table.tsx:328 currently `<Icon name={icon} size={28} />`). Then update the 5 callers above from `icon="fa-*"` to `icon={ShieldCheck}` etc.

### [MED] — kill the resolver & duplicate SVGs
- **Remove `resolveIcon()` / `Icon()`** — `lib/icons.tsx:56-58`. Indirection makes icons untraceable. Delete after callers migrated.
- **Wrong/confusing ICONS map** — `lib/icons.tsx:26-54`. `'server'→Box`, `'layer-group'→Server`. Replace whole map with top-level lucide imports (`Box, Server, ShieldCheck, User, Users, Globe, Layers, Package`).
- **Duplicate inline `IconCheck` SVG** — `components/console/screens/login.tsx:143-148` and `components/ui/toast.tsx:21-26`. Replace both with `import { Check } from "lucide-react"; <Check size={20} />`.
- **Duplicate inline `IconClose` SVG** — `components/console/screens/login.tsx:150-154` and `components/ui/toast.tsx:28-33`. Replace both with `import { X } from "lucide-react"; <X size={20} />`.

### [LOW] — size standardization
- **Outlier Menu size 20** — `components/console/console.tsx:122`. `size={20}` → `size={16}` (match nav).
- **Odd ChevronDown 15** — `components/console/screens/groups/dialog.tsx:102`. `size={15}` → `size={14}`.
- **Checkbox Check 10** — `components/console/screens/users/dialogs.tsx:118`. `size={10}` → `size={12}`; define checkbox-icon size in design system.
- **Mixed search/row sizes** — `components/console/screens/nodes/index.tsx:79` (search `size={13}`) vs row `size={12}` vs buttons `size={14}`. Document hierarchy: input=13, row=12, CTA=14.
- **Empty-state size 28** — `components/console/screens/warp-table.tsx:328`. Intentional emphasis vs button 14 / nav 16; document as design rule, no code change.

---

## 3) Font Consistency

Canonical: `--font-mono` = `"IBM Plex Mono", ...`; sans = `'Inter Variable', system-ui, sans-serif`.

### [HIGH] — wrong mono stack, force `var(--font-mono)`
- `app/globals.css:1109` — `.terminal` hardcodes `ui-monospace, SFMono-Regular, …`. → `font-family: var(--font-mono);`
- `app/globals.css:1646` — `.output-textarea` uses `monospace;`. → `var(--font-mono)`
- `app/globals.css:1659` — `.output-pre` uses `monospace;`. → `var(--font-mono)`

### [MED] — incomplete fallbacks, drop custom fallback
- `app/globals.css:4465` — `.warp-json-pre/.warp-json-ta` `var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)`. → `var(--font-mono)`
- `app/globals.css:4518` — `.warp-code-pre/.warp-code-ta` `var(--font-mono, ui-monospace, Menlo, monospace)`. → `var(--font-mono)`
- `app/globals.css:4559` — `.warp-code-lines` same incomplete fallback. → `var(--font-mono)`

### [MED] — base/size tokens
- `app/globals.css:453` — `.btn` has no explicit `font-size`. Add `font-size: 14px;` (after font-weight).
- `app/globals.css:206-217` — `.identity` 15px vs `.menu` 12px. Reconcile to a token (`--font-md` 14px) or justify.

### [LOW] — sans stack + hardcoded heading sizes
- `components/console/screens/subscription-settings.tsx:38` — preview HTML `font-family:sans-serif`. → `'Inter Variable',system-ui,sans-serif`.
- `components/console/screens/subscription-settings.tsx:47` — template starter `system-ui,sans-serif`. → `'Inter Variable',system-ui,sans-serif`.
- `app/globals.css:890-895` — `.wndw-titlebar-title` hardcoded `16px`. → token.
- `app/globals.css:1221-1225` — `.breadcrumbs h1` hardcoded `16px`. → token.

---

## 4) Dead Code / Files to Delete

### [MED]
- **Unused export `gibToBytes()`** — `lib/format.ts:15-17`. No importers. Delete (keep `bytes()`).
- **Duplicate `relTime()`** — `components/console/screens/api-keys.tsx:20-28` and `components/console/screens/audit-log.tsx:16-23`. A shared `relativeTime()` exists at `components/console/screens/nodes/util.ts:7`. Consolidate both onto it (minor output diffs — verify after).

### [LOW] — unused CSS
- `app/globals.css:3989` — `.warp-k` (zero refs). Delete.
- `app/globals.css:4928-4940` — `.warp-chips` / `.warp-chip` (+ variants), zero refs. Delete.
- `app/globals.css:5125-5135` — `.warp-online` (+ variants/dark overrides), zero refs (only `.warp-ob*` used). Delete.

> Note: the `git status` shows a large block of deleted `.VSCodeCounter/**` files — confirm those deletions are intended and commit/clean them.

---

## 5) SaaS Polish / Design-System Consistency

Three competing UI systems (legacy CSS, `warp-*`, React `components/ui`). Unify on tokens.

### [HIGH]
- **Button height fragmented** — `app/globals.css:458` (`.btn` 28px), `:3667` (signin submit 12px pad), `:4386` (`.warp-tb-button` 38px), `:4402` (`.warp-tb-search` 38px); React `button.tsx` h-9/h-10. Fix: define `--button-height-md:40px`, `--button-height-sm:36px`; apply everywhere; align React `h-10`→40px.
- **Padding fragmented** — `app/globals.css:459,3615,3667,4387,4402,4418`. Fix: `--input-px:12px`, `--input-py:8px`; apply to `.btn`, `.warp-tb-button`, signin inputs, table rows.
- **Inputs split 3 ways** — `app/globals.css:1240` (28px), `:1455` (min 28px), `:3606` (~36.8px), `input.tsx:5` (h-10/40px). Fix: unify `--input-height:40px`, `h-10 py-2 px-3`, radius `var(--corner-md)`; remove height/min-height conflicts.
- **Missing focus-visible rings** — `components/ui/button.tsx:35` (none), `components/ui/input.tsx:5` (border/shadow only). Fix: add `focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:[outline-color:var(--focus-ring)]` to Button; ensure 2px ring on all interactives.
- **Ad-hoc hardcoded colors** — `app/globals.css:3573,3610,3653,3674,3702,3742,3751,3766,3770,3813,3843,3864,3867,3878,3889,3938,3959,3965,3968-3973`. `#000/#fff/#a9a9a9/#0e52fd/rgb(254 242 242)…` bypass tokens → dark-mode drift. Fix: map to `var(--body-color)/--white/--body-muted/--primary/--red`; add `--status-success`, `--status-error`.

### [MED]
- **Border-radius mixed** — `app/globals.css:3939,4000,4188,4346,4388,4403,4511` hardcode 10px (+ stray 8/9/11/12px). Fix: standardize `--corner:6px` (controls), `--corner-md:10px` (cards); replace hardcoded values.
- **Gap/spacing off-scale** — `app/globals.css:457,711,906,1543,3929,4385`. Fix: map 6/8/10/12/14/16 → `--space-*` tokens; `.warp-grid-2` 1.4rem → `--space-lg`.
- **Empty states non-uniform** — `app/globals.css:2194-2205,2369-2412,4053-4056` (`.splash` vs `.warp-log-empty`). Fix: one `.empty-state` (icon 56×56 muted bg rounded-lg, 16px heading, 14px message, optional action, `--space-lg` pad).
- **Table row padding off** — `app/globals.css:2146,4418`. Fix: `--table-row-height:40px`; `.table td` → `var(--space-xs) var(--space-sm)`; align `.warp-tb-row`.
- **Badge sizing split 3 ways** — `app/globals.css:60,4445,4446` (+ status-badge h-18, React Badge h-18 px-2). Fix: `--badge-height:24px`, pad 4×8, radius `--corner-md` (pill); unify all three.
- **Page header inconsistent** — `app/globals.css:859-868,1175-1182,3560-3577`, `components/console/screens/settings.tsx:72`. Fix: `--page-header-height:56px`; pad `var(--space-sm) var(--space-md)`; `border-bottom:1px solid var(--hairline)`; h2 16px/1.2.
- **Switch/toggle off-system** — `app/globals.css:633-634` (36×20, thumb 16). Fix: `--toggle-width:44px`, `--toggle-height:24px`, `--toggle-thumb:20px`; thumb `translateX(calc(var(--toggle-width) - var(--toggle-thumb) - 2px))`.
- **Sidebar/menu spacing** — `app/globals.css:713-714,1858,3849-3850`. Fix: `--menu-item-height:40px`; pad `var(--space-xs) var(--space-sm)`; gaps 2px nested / 6px groups.
- **Dark-mode hardcoded in warp-*** — `app/globals.css:3901-3918,4058-4069` (`#0b0b0b/#141414/#000`). Fix: route through root vars (`var(--white)`, `var(--body-color)`).
- **Hover states inconsistent** — `app/globals.css:471,4398,4400,4985-4986` (`var(--bg-light)` vs `#f8f8f8` vs brightness filter). Fix: single hover token (`--bg-medium`, `--primary-hover`); drop brightness filters.
- **No shared Card** — `components/console/screens/dashboard.tsx:48`, `app/globals.css:2637-2763` (`.warp-card/.stat-card/.dashboard-card/.warp-tb-card`). Fix: one `.card` (border `--hairline`, radius `--corner-md`, pad `--space-md`, bg `--white`) + header/body/footer.

### [LOW]
- **Checkbox size** — `app/globals.css:2314-2322` (14px hardcoded, no focus-visible color). Fix: `--checkbox-size:16px`; apply focus ring.
- **Backdrop not tokenized** — `app/globals.css:1404,1419` `rgba(100,114,114,.5)`. Fix: `--backdrop` token + dark variant; use existing `--bg-dusk`.
- **Typography scale** — `app/globals.css:37-40,894,958,1223,4034` mixed 16/14px headings. Fix: define `--font-xl:18`, `--font-lg:16`, `--font-md:14`, `--font-base:12`; add h1–h5 rules.

---

## Ordered Action List

1. **[CRITICAL]** Fix ternary indentation — `console.tsx:139`.
2. **[HIGH]** Gate login alerts on `alert` (skip DOM when null) — `login.tsx:58-86`.
3. **[HIGH]** Fix React keys: row cells `warp-table.tsx:201-204`, QR/links `access.tsx:358-359,435`, headers `warp-table.tsx:165-166`.
4. **[HIGH]** Add focus-visible rings to Button/Input — `button.tsx:35`, `input.tsx:5`.
5. **[HIGH]** Refactor `WarpEmpty` to `icon?: LucideIcon` (`warp-table.tsx:324,328`); migrate 5 callers (admins:91, nodes:119, profiles:101, users:221, groups:101) to direct lucide.
6. **[HIGH]** Fix mono font stacks → `var(--font-mono)` — `globals.css:1109,1646,1659`.
7. **[HIGH]** Introduce control tokens (`--button-height-*`, `--input-height:40px`, `--input-px/py`) and unify buttons/inputs across legacy/warp/React — `globals.css:458,459,1240,1455,3606,3615,3667,4386,4387,4402,4418`, `input.tsx:5`, `button.tsx`.
8. **[HIGH]** Replace hardcoded colors with tokens (add `--status-success/-error`) — `globals.css:3573…3973`.
9. **[MED]** Remove `resolveIcon()`/`Icon()` + rewrite `ICONS` map — `lib/icons.tsx:26-58`.
10. **[MED]** Replace duplicate inline `IconCheck`/`IconClose` with lucide `Check`/`X` — `login.tsx:143-154`, `toast.tsx:21-33`.
11. **[MED]** A11y: dialog roles `dialog.tsx:118-126`; row aria-label `users/index.tsx:372-383`; scrim Escape `console.tsx:104-110`.
12. **[MED]** Consolidate `relTime()` onto `nodes/util.ts:7` — `api-keys.tsx:20-28`, `audit-log.tsx:16-23`; delete `gibToBytes()` `format.ts:15-17`.
13. **[MED]** Fix incomplete mono fallbacks + `.btn` font-size — `globals.css:4465,4518,4559,453`.
14. **[MED]** Unify radius/spacing/badge/table-row/page-header/toggle/sidebar/card/hover/dark-mode tokens — see Section 5 [MED].
15. **[LOW]** Icon size normalization (`console.tsx:122`, `groups/dialog.tsx:102`, `users/dialogs.tsx:118`, `nodes/index.tsx:79`).
16. **[LOW]** Delete dead CSS (`globals.css:3989,4928-4940,5125-5135`); confirm `.VSCodeCounter/**` deletions.
17. **[LOW]** Remaining font/typography tokens, sans stacks, checkbox, backdrop — `subscription-settings.tsx:38,47`, `globals.css:37-40,890-895,1221-1225,1404,1419,2314-2322`.