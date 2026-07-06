---
name: marzban-port
description: Replicate a Marzban (Gozargah/Marzban) UI component into XLink exactly — read the real source on GitHub first, extract precise tokens (sizes, colors, text colors, spacing, radius), then rebuild with XLink's .warp-* classes. Use whenever the user says "make it like Marzban", "از مرزبان بردار", "عینه مرزبان", or asks to port/clean a section (nodes, hosts, users, settings, core, header) to match Marzban.
---

# Marzban Port

Goal: XLink section looks/behaves EXACTLY like the real Marzban component — not an approximation.

## Process (always, in order)

1. **Read the real source first.** Never guess Marzban's design from memory. Fetch the actual file(s) from `Gozargah/Marzban@master`:
   `https://raw.githubusercontent.com/Gozargah/Marzban/master/app/dashboard/src/components/<Name>.tsx`
   Component map: NodesModal=`NodesDialog`, HostsDialog, CoreSettingsModal, NodesUsage, Header, Statistics, Filters, UserDialog, `components/NodeModalStatusBadge.tsx`, options in `constants/Proxies.tsx`, status colors in `constants/UserSettings.tsx`. Layout entry: `pages/Dashboard.tsx`, `App.tsx`.
   For big files, spawn a research sub-agent to extract a structured spec (container type, fields, spacing, colors, buttons, states).

2. **Extract EXACT tokens.** Chakra unit = 4px (`p={2}`=8px, `gap={3}`=12px, `px={5}`=20px). Resolve `size` props: modal `2xl`=672px, `3xl`=768px; `size="sm"` button = h32px/14px. Radius: chakra `md`=6px; Marzban items use 4px, buttons 3px, badges/pills `full`. Note exact hex.

3. **Rebuild with XLink conventions:**
   - Keep `.warp-*` class names + plain CSS (no Chakra).
   - Use XLink's data/API logic (XLink endpoints, not Marzban's) — only the *design* is ported.
   - Icons = lucide-react (heroicon-style; Marzban uses heroicons → lucide is the match), `strokeWidth={1.8}` (2.2 for active/bold).
   - Accent = XLink brand blue `#2645d3` (do NOT use Marzban's blue/green).
   - Font = Inter (`--warp-font`), matches Marzban.
   - FLAT, no box-in-box. One border level per surface.

## Real Marzban tokens (verified from source)

**Modal shell (NodesDialog/HostsDialog):** centered `Modal`; overlay `rgba(0,0,0,0.3)` + `backdrop-filter: blur(10px)`; `ModalContent maxW=3xl(768) w=fit-content mx=12px`; **`ModalBody w=440px`** (the real content width), `pt=12 pb=24`; header `pt=24`, icon-only (primary square badge + heroicon, no title text) — but XLink may add a title; close button `mt=12`. Subtitle: `fontSize sm(14) opacity .8 mb=12`.

**Accordion item (per node/inbound):** `border 1px` (light `#e2e8f0`/gray.200, or `#d2d2d4`), `borderRadius 4px`, `p=4px`; button `px=8 radius 3px`; name `fontSize 14 fontWeight medium`, color gray.700 `#374151` light / gray.300 dark; chevron right; VStack gap `8px`.

**Host card:** bg light `#fcfbfb` / dark `#273142`, `1px` border, `p=8 radius 4`. Fields stacked, labels ABOVE (`pb=4 m=0`), inputs `size sm`. Advanced options = inner sub-accordion. Status = Switch `colorScheme primary`, INVERTED (`is_disabled` → on=enabled).

**Status pill (NodeModalStatusBadge):** `rounded full`, `px=12 py=4`, icon+capitalized label, compact: icon 12px text .7rem gap 4. Colors: connected=green, connecting=orange, error=red, disabled=gray (Chakra colorScheme = light tint bg + dark text).

**CoreSettingsModal:** modal 3xl(768); body = JSON editor (`minHeight 300px`, fullscreen toggle top-right ghost) + logs panel (`mt=16`, box border gray.300/`#F9F9F9` light, `#2e3440` dark, radius 5, minH200 maxH250, p=8, log line `fontSize 12 opacity .8`). Footer space-between: left **Restart core** (neutral sm, spinning reload icon), right **Save** (primary sm `px=20`).

**NodesUsage:** modal 2xl(672); body VStack gap16 = time-filter segmented bar (chips, active = `primary.500` bg white text, radius md, `px=12 py=4`) + centered ApexCharts **donut** `maxW=300 height=500`, legend bottom, center title "Total: X".

**Buttons:** `size sm` = h32/14/radius6. Primary = solid accent + white. Secondary = outline `1px gray.300` + white, hover gray.50. Delete = red ghost icon (trash). Apply/Save = ONE global primary, footer right.

**Add affordance:** last accordion item or full-width outline button "Add New …" with `+` (PlusIcon) icon, blue text.

## Verify
After building: run `./node_modules/.bin/tsc --noEmit` (cd web), then a playwright screenshot, then READ the screenshot. Match against the real Marzban layout. Don't claim done until visually verified. Never run `next build` (dev server always running).
