Files confirmed. Here is the report.

# XLink vs Stripe Design — Compliance Report

Scope: visual-system audit of `web/` against the Stripe design spec. Two themes dominate: (1) shadows/borders use black `rgba(0,0,0,…)` where Stripe mandates navy `rgba(0,55,112,…)` / hairline `#e3e8ee`, and (2) buttons are rounded-rects, not pills. Headings/numerics also deviate from Stripe's light weights + tabular figures.

Out of scope (intentional, not violations): brand blue `#2883de` (Stripe's indigo `#533afd` not adopted) and near-navy ink.

Severity counts: High 30 · Medium 28 · Low 9. Several entries are already-compliant confirmations.

---

## 1. Buttons & Inputs

| Sev | Item | File:line | Current | Stripe | Fix |
|-----|------|-----------|---------|--------|-----|
| High | `.btn` radius is rounded-rect | globals.css:464 (also 457–472) | `border-radius: var(--corner)` = 6px | pill = 9999px | `border-radius: 9999px;` |
| High | `.btn` padding | globals.css:463 | `var(--space-xs) var(--space-sm)` = 6px 8px | 8px 16px | `padding: var(--space-sm) var(--space-md);` |
| High | Tailwind `Button` not pill | components/ui/button.tsx:35 | `rounded-md` (6px) | 9999px | `rounded-full` (or border-radius:9999px) |
| Medium | `.btn` min-height too small | globals.css:462 | `min-height: var(--input-height)` = 28px | ≥36px (pill 8/16 ⇒ ~36–40px) | min-height: 36px (or drop, content-driven) |
| Medium | `.btn-select` padding | globals.css:307–310 | 4px (6+12)px 4px 8px | 8px 12px | `padding: var(--space-xs) var(--space-sm);` |
| Low | `Input` radius | components/ui/input.tsx:5 | `rounded-md` = 8px | 6px (`rounded.sm`) | `rounded-sm` |
| Low | Body text weight | globals.css:134 | 400 | 300 (Söhne) / 400 (Inter) | acceptable for Inter; verify buttons are 400 not 500 |
| Low | Input/select radius | globals.css:1247 | `var(--corner)` = 6px | 6px | none — compliant |
| Low | Status badge radius | globals.css:2885 | 999px | 9999px | none — compliant (pill) |
| Low | `--primary` color | globals.css:52 | `#2883de` | `#533afd` | none — intentional brand deviation |
| Medium | `Button` focus ring | components/ui/button.tsx:35 | `focus-visible:ring-2 ring-primary` | primary focus ring | none — compliant |

Note: two findings flagged `.menu .level-2` shadow at globals.css:790 under this area — see Shadows & Borders (single fix covers all).

---

## 2. Cards & Dialogs

| Sev | Item | File:line | Current | Stripe | Fix |
|-----|------|-----------|---------|--------|-----|
| High | Menu flyout shadow black | globals.css:790 | `0 4px 16px rgba(0,0,0,.1)` | navy `rgba(0,55,112,.08)` | `box-shadow: 0 4px 16px rgba(0,55,112,.08);` |
| High | Top-panel shadow black | globals.css:3330 | `0 -4px 16px rgba(0,0,0,.1)` | navy | `0 -4px 16px rgba(0,55,112,.08);` |
| High | `.warp-card` border black | globals.css:3944 | `1px solid rgba(0,0,0,.1)` | hairline `#e3e8ee` | `border: 1px solid var(--hairline);` |
| High | Table card border black | globals.css:4362 | `1px solid rgba(0,0,0,.1)` | hairline | `var(--hairline)` |
| High | Table search border black | globals.css:4407 | `1px solid rgba(0,0,0,.1)` | hairline | `var(--hairline)` |
| High | Connection pulse shadow black | globals.css:4458 | `0 0 0 3px rgba(0,0,0,.03)` | navy | `0 0 0 3px rgba(0,55,112,.06);` |
| High | Active tab shadow black | globals.css:4620 | `0 1px 2px rgba(0,0,0,.08)` | navy | `0 1px 2px rgba(0,55,112,.08);` |
| High | Command palette shadow black | globals.css:4915 | `0 20px 60px rgba(0,0,0,.25)` | navy L2 | `0 20px 60px rgba(0,55,112,.2);` |
| High | Dropdown menu shadow black | globals.css:4973 | `0 6px 20px rgba(0,0,0,.08), 0 1px 3px rgba(0,0,0,.06)` | navy L2 | `0 6px 20px rgba(0,55,112,.08), 0 1px 3px rgba(0,55,112,.04);` |
| High | Dark toast shadow black | globals.css:4324 | `0 12px 40px rgba(0,0,0,.5)` | navy (softened) | `0 12px 40px rgba(0,55,112,.4);` |
| High | Dark dropdown shadow black | globals.css:4988 | `0 6px 20px rgba(0,0,0,.4)` | navy | `0 6px 20px rgba(0,55,112,.35);` |
| High | Dialog shadow black | globals.css:5308 | `0 10px 40px rgba(0,0,0,.16), 0 1px 2px rgba(0,0,0,.06)` | navy L2 | `0 10px 40px rgba(0,55,112,.16), 0 1px 2px rgba(0,55,112,.06);` |
| High | `.warp-confirm` border black | globals.css:5093 | `1px solid rgba(0,0,0,.08)` | hairline | `var(--hairline)` |
| High | `.btn` not pill (dup) | globals.css:464 | `var(--corner)` 6px | 9999px | `border-radius: 9999px;` |
| Medium | `.warp-card` radius off-scale | globals.css:3943 | 10px | 12px (`rounded.lg`) | `border-radius: 12px;` |
| Medium | Confirm dialog radius off-scale | globals.css:5093 | 16px | 12px | `border-radius: 12px;` |
| Medium | `.btn` padding off-scale (dup) | globals.css:463 | 6px 8px | 8px 16px | `padding: 8px 16px;` |
| Medium | Undefined `--shadow-soft` | globals.css:656 | `var(--shadow-soft)` undefined | define L1 | add `:root { --shadow-soft: 0 1px 3px rgba(0,55,112,.08); }` |
| — | Modal shadow | globals.css:1419 | `var(--shadow-block)` | navy | none — compliant |

---

## 3. Shadows & Borders

Note: `--shadow-block: 0 8px 24px rgba(0,55,112,.08), 0 2px 6px rgba(0,55,112,.04)` (globals.css:69) is the correct navy token — route all shadows through it where possible.

| Sev | Item | File:line | Current | Stripe | Fix |
|-----|------|-----------|---------|--------|-----|
| High | `.menu .level-2` shadow black | globals.css:790 | `0 4px 16px rgba(0,0,0,.1)` | navy L2 | `0 4px 16px rgba(0,55,112,.08);` (single fix; resolves all :790 dups) |
| High | `.shadow-panel-top` black | globals.css:3330 | `0 -4px 16px rgba(0,0,0,.1)` | navy | `0 -4px 16px rgba(0,55,112,.08);` |
| High | `.warp-alert` shadow black | globals.css:3712–3714 | `rgba(0,0,0,.05)…` 3-layer | navy | swap all `0,0,0` → `0,55,112` |
| High | `.warp-toast` shadow black | globals.css:4289–4291 | `rgba(0,0,0,.05)…` 3-layer | navy | swap all `0,0,0` → `0,55,112` |
| High | `.warp-confirm` shadow black | globals.css:5096 | `0 24px 60px rgba(0,0,0,.22)` | navy | `0 24px 60px rgba(0,55,112,.22);` |
| Medium | `.warp-sidebar` border black | globals.css:3818 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `border-right: 1px solid #e3e8ee;` |
| Medium | `.warp-card` border black | globals.css:3944 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-info-row` border black | globals.css:4021 | `1px solid rgba(0,0,0,.06)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-tab-dark-light` border | globals.css:4157 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-si-box` dashed border | globals.css:4193 | `1px dashed rgba(0,0,0,.15)` | `#e3e8ee` | `1px dashed #e3e8ee;` |
| Medium | `.warp-tb-stat` dashed border | globals.css:4350 | `1px dashed rgba(0,0,0,.15)` | `#e3e8ee` | `1px dashed #e3e8ee;` |
| Medium | `.warp-tb-card` border | globals.css:4362 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-tb-search` border | globals.css:4407 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-confirm` border | globals.css:5093 | `1px solid rgba(0,0,0,.08)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-confirm-input` border | globals.css:5112 | `1px solid rgba(0,0,0,.12)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-confirm-select` border | globals.css:5126 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-failover-auto` border | globals.css:5162 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-copyfield-box` border | globals.css:5261 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-copyfield-btn` border | globals.css:5275 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |
| Medium | `.warp-set-card` border | globals.css:5382 | `1px solid rgba(0,0,0,.1)` | `#e3e8ee` | `1px solid #e3e8ee;` |

---

## 4. Typography

| Sev | Item | File:line | Current | Stripe | Fix |
|-----|------|-----------|---------|--------|-----|
| High | `bytes()` 2xl no tabular nums | nodes/detail.tsx:397 | `text-2xl font-medium` | tnum + ls -0.42px | add `.numeric-display { font-variant-numeric: tabular-nums; letter-spacing:-0.14px; }` |
| High | `bytes()` no tabular nums | users/access.tsx:569 | `text-2xl font-medium` | tnum | apply `.numeric-display` |
| High | `bytes()` no tabular nums | profiles/index.tsx:333 | `text-2xl font-medium` | tnum | `font-variant-numeric: tabular-nums;` |
| High | `.warp-confirm-title` too heavy | globals.css:5107 | 600 @16px | 300 (heading-md) | `font-weight: 300;` |
| High | `.warp-ob-sectitle` too heavy | globals.css:4731 | 600 @12px caps | 400 (micro-cap) | `font-weight: 400;` |
| High | `.warp-2fa-h` too heavy | globals.css:4680 | 600 @14px | 300/400 | `font-weight: 400;` |
| Medium | Table numeric cells no tnum | users/access.tsx:609 | `{bytes(r.total_bytes)}` | body-tabular tnum | `.warp-tb-traffic-val { font-variant-numeric: tabular-nums; }` |
| Medium | Heading no neg tracking | users/access.tsx:202 | `text-xl font-medium tracking-tight` (0) | -0.2px, wt 300–400 | `font-normal` + `letter-spacing:-0.2px` |
| Medium | Modal heading too heavy | components/ui/modal.tsx:34 | `text-base font-semibold` (600) | 300–400 | `font-normal` + `letter-spacing:-0.1px` |
| Medium | Table header weight/nums | globals.css:4429 | 500 @13px | 400 (caption) + tnum | `font-weight:400;` + tnum on numeric cols |
| Low | Geist font leftover | globals.css:5–19 | `geistSansFont` @font-face | Inter / Söhne 300–400 | confirm unused; body rule (l.132) already Inter |

---

## 5. Icons & Color

Note: black→navy shadow items at globals.css:790 here are the same defect as §2/§3 — fix once.

| Sev | Item | File:line | Current | Stripe | Fix |
|-----|------|-----------|---------|--------|-----|
| High | `Button` not pill (dup) | components/ui/button.tsx:35 | `rounded-md` | 9999px | `rounded-full` |
| High | Shadows black not navy (dup) | globals.css:790 | `0 4px 16px rgba(0,0,0,.1)` | `rgba(0,55,112,.08)` | navy; also fix 3330, 3712–3714 |
| High | Dark `--shadow-1` black | globals.css:112 | `0 1px 2px rgba(0,0,0,.4)` | navy | `rgba(0,55,112,.08)` (tune for dark) |
| High | `.btn` padding (dup) | globals.css:463 | 6px 8px | 8px 16px | `var(--space-sm) var(--space-md)` |
| Medium | Toast icon stroke width | components/ui/toast.tsx:23,30 | `strokeWidth={2.5}` | 1.75 uniform | global `svg.lucide{stroke-width:1.75}`; drop inline |
| Medium | Hardcoded chart hex | usage-chart.tsx:50 | `["#008ffb","#5564be"]` | tokens | `var(--primary)` / `var(--primary-soft)` |
| Medium | Hardcoded search-icon hex | nodes/index.tsx:79 | `color:"#707070"` | token | `var(--body-muted)` |
| Medium | Status badge radius | globals.css:1300 | 1rem (16px) | 9999px | `border-radius: 9999px;` |
| Medium | Inline SVG hardcoded hex | subscription-settings.tsx:1299 | `#171a23/#cdd3e0/#4f8cff` | tokens | extract to class; `#4f8cff`→`var(--primary)` |
| Medium | Status badge color consistency | globals.css:2902–2935 | mixed token refs | unified pill-tag-soft | use Badge color-mix formula across variants |
| Low | `--corner` 6px input | globals.css:60 | 6px | 6px | none — compliant |

---

## Ordered Action List (highest visual impact first)

1. **Make all buttons pills.** `.btn` radius 6px→9999px (globals.css:464) + `Button` `rounded-md`→`rounded-full` (button.tsx:35). Single most visible deviation, app-wide.
2. **Global black→navy shadow sweep.** Replace every `rgba(0,0,0,…)` box-shadow with `rgba(0,55,112,…)` (or route through `--shadow-block`): globals.css 790, 3330, 3712–3714, 4289–4291, 4324, 4458, 4620, 4915, 4973, 4988, 5096, 5308; dark `--shadow-1` :112. Touches menus, dropdowns, command palette, dialogs, toasts — pervasive.
3. **Global black→hairline border sweep.** Replace `rgba(0,0,0,…)` borders with `var(--hairline)` / `#e3e8ee`: globals.css 3818, 3944, 4021, 4157, 4193, 4350, 4362, 4407, 5093, 5112, 5126, 5162, 5261, 5275, 5382. Cards, tables, inputs, sidebar.
4. **Fix button sizing.** `.btn` padding 6px8px→8px16px (l.463) + min-height 28px→36px (l.462); `.btn-select` padding (l.307–310). Restores Stripe's "short, decisive" pill proportions.
5. **Lighten heavy headings.** 600→300/400: `.warp-confirm-title` (5107), `.warp-ob-sectitle` (4731), `.warp-2fa-h` (4680), modal h3 (modal.tsx:34), access h3 (access.tsx:202) + add negative letter-spacing.
6. **Tabular figures on all numeric/byte displays.** Add `.numeric-display { font-variant-numeric: tabular-nums; letter-spacing:-0.14px; }`: detail.tsx:397, access.tsx:569/609, profiles/index.tsx:333, table headers globals.css:4429.
7. **Card/dialog radii to 8-base scale.** `.warp-card` 10px→12px (3943); `.warp-confirm` 16px→12px (5093). Status badge radius 1rem→9999px (1300).
8. **Define missing token.** Add `--shadow-soft: 0 1px 3px rgba(0,55,112,.08);` (used at 656).
9. **Replace hardcoded hex with tokens.** usage-chart.tsx:50, nodes/index.tsx:79, subscription-settings.tsx:1299.
10. **Normalize icon stroke** to 1.75 globally; drop inline `strokeWidth={2.5}` (toast.tsx:23,30).
11. **Low/cleanup:** `Input` `rounded-md`→`rounded-sm` (input.tsx:5); confirm Geist `@font-face` (globals.css:5–19) is unused.

Already-compliant (no action): `--shadow-block` (69), `--corner` 6px (60), modal `var(--shadow-block)` (1419), status badge 999px (2885), `Button` focus ring (button.tsx:35), input radius (1247). Brand `#2883de` (52) intentional.

Key reference files: `/Users/parsa/Desktop/Xlink/web/app/globals.css`, `/Users/parsa/Desktop/Xlink/web/components/ui/button.tsx`, `/Users/parsa/Desktop/Xlink/web/components/ui/input.tsx`, `/Users/parsa/Desktop/Xlink/web/components/ui/modal.tsx`, `/Users/parsa/Desktop/Xlink/web/components/ui/toast.tsx`.