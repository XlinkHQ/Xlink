# XLink vs Marzban — Improvement Report

Generated 2026-06-27. Findings grouped by area; each section ordered by severity. Every item carries file:line. Ordered action list at the end marks quick UI cleanups vs larger features.

---

## 1) Create-user flow + dialog cleanup

**[HIGH] Create dialog drops `data_reset_strategy` and `device_limit`** — `web/components/console/screens/users/dialogs.tsx:298-327`
The backend `UserCreate` (`app/schemas/user.py:25`) accepts `data_reset_strategy` + `device_limit`, and `EditUserDialog` (`dialogs.tsx:114-130`) shows both ("Auto-reset usage", "Device limit"). The create `UserDialog` omits both, so a new user can never get an auto-reset cycle or device cap until Edit is reopened. More limited than Marzban *and* than XLink's own edit flow.
Fix: add an "Auto-reset usage" Select (`no_reset/day/week/month` → `data_reset_strategy`) and a "Device limit" number Input, mirroring `dialogs.tsx:114-130`; pass both in `createUser()` (`dialogs.tsx:210`).

**[HIGH] `createUser()` never sends `data_reset_strategy`/`device_limit`** — `web/components/console/screens/users/dialogs.tsx:210-224`
Payload only sends username, full_name, data_limit_bytes, expire_strategy, expire_at, on_hold, on_hold_duration_seconds. `data_reset_strategy` defaults server-side to `NO_RESET` (`schemas/user.py:25`); `device_limit` stays null. No path to set either at creation.
Fix: once UI fields exist, include both keys in the `createUser()` object for parity with the schema.

**[MEDIUM] Per-inbound assignment creation is a fragile client-side fan-out** — `web/components/console/screens/users/dialogs.tsx:226-270`
Marzban creates user + proxies + inbounds in one atomic call. XLink POSTs the user, then fires N `createAssignment` calls via `Promise.allSettled`, reporting partial failure ("User created, but N inbound(s) failed") — a half-provisioned user with no rollback. Dedup/group-flattening logic (`226-241`) lives in the React component, not the backend.
Fix: add a backend endpoint (or extend `UserCreate`) accepting chosen `group_ids`/`profile_ids` and create user + all assignments in one transaction; move fan-out/dedup out of the component.

**[MEDIUM] "On first use" UI allows submit with empty usage-duration** — `web/components/console/screens/users/dialogs.tsx:289-296,320-324`
Create button is disabled only by the username regex (`292`). With `expireStrategy='start_on_first_use'`, `usageDays` can be empty and the form still submits → `on_hold_duration_seconds=null`. Marzban blocks this at validation time.
Fix: extend the disabled condition at `292`: also disable when `expireStrategy==='start_on_first_use' && (!usageDays || Number(usageDays) < 1)`, and when `expireStrategy==='fixed_date' && !expire`.

**[MEDIUM] "note" field has no max-length and is overloaded onto `full_name`** — `web/components/console/screens/users/dialogs.tsx:191,325-327`
UI labels the field "Note (optional)" but maps it to `full_name` (`dialogs.tsx:212`), schema-capped at 255 (`schemas/user.py:22`). Label says note, backend treats it as a name, silent 255-char ceiling with no inline feedback or `maxLength`. Marzban has a dedicated `note` (max 500) separate from name.
Fix: either rename the label to "Full name", or add a real note column. Minimum: add `maxLength={255}` + a limit hint, and stop calling a name field a "note".

**[MEDIUM] No inline username validation feedback; only a dead button** — `web/components/console/screens/users/dialogs.tsx:292,299-301`
Validity enforced only by disabling Create via `/^[a-zA-Z0-9_]{3,64}$/`. Invalid username → button just dead, no message. Marzban surfaces the constraint inline; the Field `hint` here is static, not an error state.
Fix: track touched/error state for username; render the rule as red helper text under the Input when invalid instead of relying on a disabled button.

**[LOW] Create dialog has no visual sectioning** — `web/components/console/screens/users/dialogs.tsx:298-365`
Flat vertical list (username, data limit, expiration, conditional date/duration, note, services, inbounds) — identity, limits, and inbound selection visually undifferentiated. Marzban groups into identity / limits-expiry / proxies-inbounds. The Edit dialog at least uses a 2-col grid (`dialogs.tsx:100`).
Fix: put Data limit + Auto-reset + Device limit + Expiration in a 2-col grid block; separate Services/Inbounds with a labeled subsection or divider.

**[LOW] `expire_at` hard-coded to 23:59:59Z; no timezone handling** — `web/components/console/screens/users/dialogs.tsx:215-218`
`new Date(\`${expire}T23:59:59Z\`)` — always end-of-day UTC. An admin in UTC+8 gets an expiry effectively the next morning. Same pattern in `EditUserDialog` (`dialogs.tsx:59`); `dateToIso` is duplicated.
Fix: compute end-of-day in browser-local TZ (drop `Z`, parse local, `toISOString`) or document UTC end-of-day; centralize `dateToIso` into one shared helper.

**[LOW] Username max length differs from Marzban (64 vs 32), no charset parity** — `app/schemas/user.py:11`
XLink `^[a-zA-Z0-9_]{3,64}$`; Marzban uses 3-32 and also allows `-`, `@`, `.`. Not a bug, but if subscription links / external tooling assume Marzban-compatible usernames the divergence matters.
Fix: decide intentionally; keep front-end regex (`dialogs.tsx:292`) and backend pattern in one shared constant to avoid drift.

---

## 2) UI sizing / spacing / structure to Marzban standard

**[HIGH] Two competing dialog systems — unify on the Tailwind `<Modal>`** — `nodes/dialog.tsx:80`, `groups/dialog.tsx:59`, `admins/dialog.tsx`, `profiles/dialog.tsx:217`, `profiles/host-dialog.tsx`
Tailwind `<Modal>` (users, subscription-settings) vs raw `.warp-dlg` CSS (nodes, groups, admins, profiles). They differ in width (512px vs 420px), header (left 16px/600 vs centered 15px/500 + a mobile grab bar shown on desktop), input radius (6px vs 10px), border (1px vs 2px), footer (right gap-2 vs space-between). `host-dialog.tsx` mixes both imports.
Fix: port nodes/groups/admins/profiles to `<Modal>` + `<Field>` + `<Input>/<Select>/<Button>`; delete `.warp-dlg-*` CSS (`globals.css 5241-5313, 5446-5508`).

**[HIGH] `warp-dlg` fields are inline label/input (cramped), not stacked** — `app/globals.css:5277`
`.warp-dlg-field` is `flex; justify-content:space-between` with a fixed `flex:0 0 240px; max-width:55%` input → ~240px inputs on the 420px dialog, truncated labels/hints. Marzban stacks label over full-width input (VStack gap=3).
Fix: use the stacked `<Field>` from `parts.tsx`; remove the `flex:0 0 240px; width:240px; max-width:55%` rule (`globals.css 5286-5287`).

**[MEDIUM] Inconsistent field vertical spacing across dialogs** — `app/globals.css:5279`
Three values: Modal body `gap-3` (12px), `.warp-dlg-field` `margin-bottom:16px`, `.warp-dlg-body-flow` `gap:14px` (`profiles/dialog.tsx:225`). Marzban uses one gap (~12px).
Fix: standardize on 12px (`gap-3`); after migration drop the 14px flow gap and 16px field margin.

**[MEDIUM] Dialog input radius/border mismatch** — `app/globals.css:5289`
Shared `<Input>` is 6px/1px (matches Marzban) but `.warp-dlg-field` inputs are 10px/2px and warp buttons 10px (`globals.css 4387`). 2px borders look heavy next to 1px shared inputs.
Fix: standardize 6px/1px; set `.warp-tb-button` radius 10px→6px (`globals.css 4387`).

**[MEDIUM] Profiles dialog too narrow; sections nested oddly** — `web/components/console/screens/profiles/dialog.tsx:284`
Marzban uses ~672px (2xl) + 2-col grid. The most field-heavy dialog renders in 420px `.warp-dlg`, wraps all sections in a bare `<div>` (`284`) with no spacing token; the 2-col grid (`398`) gives ~190px columns — tight for SNI/key fields.
Fix: move to `<Modal width="sm:w-[42rem]">`; remove/`space-y-3` the wrapper `<div>` (`284-335`).

**[MEDIUM] Modal header shows a mobile grab bar on desktop and centers title** — `app/globals.css:5260`
`.warp-dlg-header` centers (`text-align:center`) and always renders `.warp-dlg-grab` (`globals.css 5267`) — a mobile-sheet affordance shown on desktop. Shared `<Modal>` is correctly left-aligned.
Fix: migrate to `<Modal>` (left 16px/600, no bar); short-term set header `text-align:left` and gate `.warp-dlg-grab` behind a mobile breakpoint.

**[MEDIUM] Footer button layout inconsistent (space-between vs right-aligned)** — `app/globals.css:5301`
`<Modal>` footer is `justify-end gap-2` (`modal.tsx:51`); `.warp-dlg-footer` is `space-between` (Cancel far left, Save far right). Padding differs too (`px-6 py-4` vs `0.7rem 1rem`).
Fix: after migration the shared footer applies everywhere; short-term set `.warp-dlg-footer` to `flex-end; gap:8px` + `px-6/py-4`.

**[MEDIUM] Button height inconsistency (warp 38px vs shared 36/40px)** — `web/components/ui/button.tsx:23`
Shared md=40px, sm=36px, `.warp-tb-button`=38px (`globals.css 4385`), inputs=40px. A warp footer button (38px) sits next to a 40px input; toolbar buttons (38px) ≠ dialog buttons (40px).
Fix: pick one height (Marzban=sm); set `.warp-tb-button` to 36px and use `<Button size="sm">` for dialog footers.

**[LOW] Label/hint typography differs between two `<Field>` impls** — `web/components/console/screens/nodes/dialog.tsx:137`
`parts.tsx` Field: label `text-sm/500`, hint `text-[11px]/400` inline-right (matches Marzban). `nodes/dialog.tsx` has its own local Field (`137`) using `.warp-dlg-field` (color `#333`) with a block-level hint below. Two label colors, two hint placements.
Fix: delete the local Field (`137-147`); import shared `Field` from `../parts`.

**[LOW] Table density heavier than Marzban; min-width forces scroll** — `app/globals.css:4413`
`.warp-tb-head/.warp-tb-row` use `padding:0.7rem 1rem` + hard `min-width:760px` (`globals.css 4416`) → horizontal scroll on narrow panes; cell font 14px vs Marzban's smaller body.
Fix: reduce row padding to ~0.55rem; relax `min-width:760px` or hide low-priority columns under a breakpoint.

**[LOW] Inline checkbox rows use ad-hoc styling, not the Field system** — `web/components/console/screens/users/dialogs.tsx:132`
on-hold/transport bools render as raw `<label className="flex items-center gap-2 text-xs text-fg">` (`dialogs.tsx:132`; profiles bool branch `401`) at `text-xs` while sibling labels are `text-sm`. Breaks vertical rhythm.
Fix: wrap booleans in a checkbox-Field helper at `text-sm` with the same 12px gap.

---

## 3) User table / list improvements

**[HIGH] Sort/filter/search operate only on the loaded page, not the full dataset** — `web/components/console/screens/users/index.tsx:74-80,241-254,466-471`
`listUsers` is cursor-paginated at size 50; `matchStatus` (`225-238`), search (`242`), sort (`244-254`) all run client-side over fetched rows only (UI even warns "Searching loaded users only", `468-470`). "Most traffic"/"Expiring soon"/status chips silently miss users on unloaded pages — wrong for any account with >50 users. Marzban pushes sort + status to the server.
Fix: move sort/status/search into `listUsers` query params and key `useInfiniteQuery` on them; render the server-ordered/filtered page directly. Removes both the caveat and the partial-data bug.

**[HIGH] Data-usage shown as a 24px donut instead of a horizontal bar** — `web/components/console/screens/users/index.tsx:417-423`
`WarpRadial` donut is hard to read and impossible to compare row-to-row. Marzban uses a full-width horizontal Slider with "used / total" beneath and lifetime on the right, colored by status. XLink already ships `WarpTraffic` (`warp-table.tsx:266`) but the table doesn't use it.
Fix: replace `WarpRadial` with `WarpTraffic`: `pct = limit ? (used/limit)*100 : 0`, `tone = reached ? 'danger' : !limit ? 'unlimited' : 'default'`, `label = limit ? \`${bytes(used)} / ${bytes(limit)}\` : \`${bytes(used)} / ∞\``. Widen the column.

**[HIGH] Expiration shows a raw ISO date, not relative time / days-left** — `web/components/console/screens/users/index.tsx:424-426,703-707`
`expireLabel()` returns `u.expire_at.slice(0,10)` in a static orange badge regardless of urgency. Marzban shows "expires in 29 days" / "expired 2 days ago" via a dayjs duration. Badge is always orange even when healthy.
Fix: add `relativeExpiry(expire_at)` (years/months/days → hours/mins, signed for past); render "in 3 days"/"5 days ago". Color by urgency (red/orange if expired or <7 days, neutral otherwise; ∞ for none). Reuse in the detail drawer Expiration row (`index.tsx:650-653`, also `slice(0,10)`).

**[MEDIUM] Online column is a text badge, no last-seen, no live pulse** — `web/components/console/screens/users/index.tsx:398-402`
Full "Online"/"Offline" `WarpBadge` from a 30s-polled `onlineSet`; `last_seen` fetched only in the detail drawer (`552-556`). Marzban uses a compact pulsing dot (green ≤60s, gray offline, hollow ring if never) + relative last-seen.
Fix: render a status dot (green pulse / gray / hollow) and surface last-seen relative text; pull `last_seen` for the visible page via `usersLastSeen(userIds)` at list level.

**[MEDIUM] Sorting hidden in a dropdown; column headers not clickable** — `web/components/console/screens/users/index.tsx:344-354,358`
Sort is a separate `<select>`; `WarpHead` columns are plain labels (`warp-table.tsx:162-173`). Marzban makes Username/Status/Data-usage headers clickable with a rotating chevron.
Fix: give `WarpHead` per-column sort config (key + active dir) + chevron; click toggles sort. Map Username→name, Used Traffic→traffic, Expiration→expiring. Keep the select as fallback or drop it.

**[LOW] Status doesn't distinguish on_hold strategy or show an icon** — `web/components/console/screens/users/index.tsx:403-415`
Icon-less text badges. Marzban pairs each status with a glyph (Wifi/NoSymbol/ExclamationCircle/Clock) + color map; on_hold shows the on-first-use duration, not a date. XLink already knows `expire_strategy === 'start_on_first_use'` (`expireLabel`, `705`) but the status cell ignores it.
Fix: add a leading lucide icon (Wifi/Ban/AlertCircle/Clock) + align tone map (on_hold=purple/blue); for on_hold render the configured duration / "On first use" via `expireLabel`.

---

## 4) Backend user model / lifecycle gaps

**[HIGH] No single canonical user status enum (Marzban's `UserStatus`)** — `app/domain/user.py:85-132`
Marzban persists one authoritative `status` enum (active/disabled/limited/expired/on_hold) + `last_status_change`. XLink scatters state across `is_active`/`on_hold`/`removed` + derived checks; real status is recomputed ad hoc in `subscription/generator.py:79-97` `_user_status()` for display only. `UserRead` (`schemas/user.py:64-92`) exposes no `status`; `list_users` (`user_service.py:344-360`) can only filter by `is_active`/`removed`.
Fix: add a `UserStatus` StrEnum + persisted indexed `status` column; compute/persist it transactionally on every state change (enable/disable/delete, limit enforcement in `traffic/service.py`, expiry/on-hold in `subscription/repository.py`, reset cron in `agent/reconcile.py`). Expose on `UserRead`; accept as a list filter.

**[HIGH] No persisted `used_traffic`/lifetime; status "limited" never recorded** — `app/traffic/service.py:251-283`
Marzban stores `used_traffic` + `lifetime_used_traffic` and transitions to `limited` over data_limit. XLink has `users_data_usage` (`domain/user.py:150`) but on over-limit `_enforce_user_limits` only flips ClientAssignments to `DISABLED`; the User row keeps `is_active=True`, no "limited" marker. Over-limit is indistinguishable from admin-disabled; resets permanently lose cumulative totals (no reset-log).
Fix: persist `status='limited'` in `_enforce_user_limits`; add a `lifetime_used_traffic` column + usage-reset-log (or accumulate into the column) so `_apply_data_resets` (`agent/reconcile.py:53-59`) adds current usage to lifetime before zeroing.

**[HIGH] Data-reset cron re-enables ALL disabled assignments** — `app/agent/reconcile.py:61-76`
`AssignmentStatus` is only ACTIVE/DISABLED/EXPIRED (`domain/client_assignment.py:34-37`). Limit enforcement (`traffic/service.py:273-281`), admin disable (`user_service.py:425-433`), delete (`user_service.py:516-524`) all collapse into DISABLED. `_apply_data_resets` re-activates every DISABLED assignment when `user.is_active and not user.removed` — silently re-enabling admin-disabled ones. Marzban avoids this because "limited" is distinct.
Fix: add `AssignmentStatus.LIMITED` (or `disabled_reason`); reactivate only LIMITED on reset; set LIMITED in `_enforce_user_limits`/`_enforce_limit`.

**[MEDIUM] No `online_at` / last-seen tracking for users** — `app/domain/user.py:93-94`
Marzban records `online_at` from node usage. XLink tracks only `sub_updated_at`/`sub_last_user_agent` (subscription fetch); `UserDevice.last_seen_at` (`user_service.py:197`) is per-device, not on the user or `UserRead`.
Fix: add `online_at: datetime|None`, update it in `traffic/service.py _bump_user_usage` when deltas>0, expose on `UserRead`; optionally derive an "online" indicator.

**[LOW] on_hold modeled as duration+deadline split, plus redundant boolean** — `app/domain/user.py:113-130`
XLink has `on_hold_duration_seconds` + `activation_deadline` + a redundant `on_hold` bool + `expire_strategy=START_ON_FIRST_USE` all encoding the same fact (`_resolve_expiry`, `user_service.py:28-38` forces sync). Marzban uses 2 explicit columns (`on_hold_expire_duration`, `on_hold_timeout`).
Fix: make `status='on_hold'` the single source of truth; keep the two data columns; drop the bool, treat `expire_strategy` as derived; align naming with Marzban for migration compat.

**[LOW] No `note` / `auto_delete_in_days` / `edit_at` admin fields** — `app/domain/user.py:72-153`
Marzban carries `note` (500), `auto_delete_in_days`, `edit_at`. XLink has none (only TimestampMixin created/updated; manual delete/purge in `user_service.py:510-545`).
Fix: add `note: str|None` (max 500), `auto_delete_in_days: int|None`; surface in Create/Update/Read; add a reconcile purge job; `edit_at` can be `updated_at` if it only bumps on admin edits.

**[LOW] Subscription revoke is well-modeled — keep, don't regress** — `app/services/user_service.py:160-165`
Marzban's JWT validation doesn't actually check `sub_revoked_at`, so old links survive. XLink bumps `sub_revision` and the router enforces it (`api/v1/routers/subscriptions.py:282`, signed at `:432`) — a genuinely stronger revoke.
Fix: none required; documented to avoid regression. Optionally expose `sub_revision`/last-revoked in `UserRead`.

---

## 5) Subscription formats / headers gaps

**[HIGH] `profile-update-interval` is in DAYS, but XLink sends an hours value** — `app/api/v1/routers/subscriptions.py:400`
Clients (Clash Meta, v2rayNG, Karing) read the integer as DAYS. XLink stores `update_interval_hours` (default 12, capped `le=168`, `app/schemas/settings.py:55`, `app/domain/app_settings.py:20`) and emits it raw: `"profile-update-interval": str(cfg.update_interval_hours)`. So "12 hours" is read as "12 days" and the 168 cap would mean 168 days.
Fix: treat the value as days — either rename to `update_interval_days` (e.g. `ge=1,le=30`, default 1) and send directly, or convert on emit: `str(max(1, round(cfg.update_interval_hours / 24)))`. Fix the schema bound at `settings.py:55`.

**[MEDIUM] Modern v2rayN/NG/Streisand/Happ get base64 instead of xray/v2ray-json** — `app/api/v1/routers/subscriptions.py:74`
Marzban version-gates: v2rayN≥6.40, v2rayNG≥1.8.29, Streisand, Happ≥1.63.1 all get `v2ray-json`, falling back to base64 only for old versions. XLink's `_UA_FORMAT_RULES` lumps `v2ray|v2box|streisand|nekoray|nekobox|hiddify` straight into BASE64 with no version parsing, losing the richer config. The `xray_json` renderer already exists (`registry.py:76`).
Fix: version-aware matcher detecting `^v2rayNG/(\d+\.\d+\.\d+)`, `^v2rayN/(\d+\.\d+)`, `^Streisand`, `^Happ/(\d+\.\d+\.\d+)`; return `XRAY_JSON` when ≥ Marzban thresholds, else BASE64 (tuple-of-ints compare).

**[MEDIUM] `content-disposition` filename hardcoded instead of per-user** — `app/api/v1/routers/subscriptions.py:398`
Always `filename="xlink-subscription"`. Marzban uses `filename="{user.username}"`. `owner` (the User) is already in scope here.
Fix: `fname = owner.username if owner else (cfg.profile_title or "xlink")`; `f'attachment; filename="{fname}"'` (sanitize/quote).

**[MEDIUM] `profile-web-page-url` header not emitted** — `app/api/v1/routers/subscriptions.py:396`
Marzban sets `profile-web-page-url: {request.url}`; clients (v2rayTun/Happ/Streisand) use it to open the management page. XLink's header dict (`396-406`) omits it.
Fix: `headers["profile-web-page-url"] = str(request.url).split("?", 1)[0]` (reuse the canonical sub URL computed at `328/341`).

**[MEDIUM] Outline subscription format not supported** — `app/subscription/formats/registry.py:72`
Marzban ships Outline (JSON describing a single SS outbound). XLink has no `OUTLINE` member in `SubscriptionFormat` (`app/subscription/schemas.py:20-36`) and no renderer.
Fix: add `OUTLINE = "outline"`; create `app/subscription/formats/outline.py` rendering the first shadowsocks/2022 config as Outline JSON (`{method,password,server,server_port,tag}`); register in `default_registry()`; add `application/json` to `_FORMAT_CONTENT_TYPES`; add an `outline` alias in `_FORMAT_ALIASES`.

**[LOW] Outline / Shadowsocks-family User-Agents not detected** — `app/api/v1/routers/subscriptions.py:64`
Marzban routes `^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)` to outline. XLink falls through to BASE64 (`subscriptions.py:196`), which Outline can't import.
Fix: after adding Outline, add `(re.compile(r"(?i)^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)"), SubscriptionFormat.OUTLINE)` to `_UA_FORMAT_RULES` + an `outline` mapping in `_RULE_RESULT_FORMATS`.

**[LOW] `subscription-userinfo` splits upload/download instead of upload=0** — `app/api/v1/routers/subscriptions.py:387`
XLink: `up = min(upload_bytes, used_bytes)`, `down = used - up`. Marzban reports all usage as `download` (`upload=0`). Some clients only read `download` or sum both, so Marzban's convention guarantees the full bar.
Fix: optional. If clients under-report, mirror Marzban (`upload=0; download={used_bytes}`). Ensure `total`/`expire` emit `0` (not literal `'None'`) when unset — `stats.traffic_limit_bytes`/`stats.expire_timestamp` could format as `'None'`; coerce to 0.

---

## 6) Validation / UX guardrails

**[HIGH] `on_hold` + `expire_at` accepted simultaneously (silent conflicting state)** — `app/services/user_service.py:28-38`; `app/schemas/user.py:24-29,54-59`
Marzban rejects on_hold-with-expire. XLink's `_resolve_expiry` silently forces START_ON_FIRST_USE and ignores `expire_at`, but Create/Update still accept both with no error. `EditUserDialog` (`web/.../users/dialogs.tsx:61-71`) literally sends both, leaving a stale `expire_at` that no longer matches the strategy, with no feedback.
Fix: add a `model_validator` on Create/Update: if `on_hold` then `expire_at` must be None and `on_hold_duration_seconds` > 0 ('On-hold users use a duration, not a fixed expire date'); if `expire_strategy==START_ON_FIRST_USE` require a duration. Mirror Marzban's explicit messages.

**[HIGH] `on_hold` allowed with no duration → never-expiring user** — `app/services/user_service.py:34-35,91-106`; `app/schemas/user.py:26-27`
Marzban: "User cannot be on hold without a valid on_hold_expire_duration". XLink accepts `on_hold=true` with `on_hold_duration_seconds=None`; `_resolve_expiry` sets START_ON_FIRST_USE with no countdown → never expires after first use. `UserDialog` (`web/.../users/dialogs.tsx:219-223`) sends null when `usageDays` is blank.
Fix: reject `on_hold=true` with missing/zero duration in the schema validator; disable Create / show inline error in `UserDialog` when `expireStrategy=='start_on_first_use'` and `usageDays` is empty.

**[HIGH] No protection against removing/disabling/demoting the last sudo admin (lockout)** — `app/api/v1/routers/users.py:197-209,173-194,290-297`; `app/services/user_service.py:153-158,419,510`
`_guard_not_self` only blocks self-action. Sudo A can delete/disable/demote sudo B and vice versa; `update_admin` (`service:108-128`) can flip the last sudo's `is_sudo`/`is_active` false → full lockout with no in-app recovery. Marzban is anchored by `SUDOERS` config; XLink has no floor.
Fix: before delete/disable/demote/clear-sudo on an ADMIN, count remaining *active sudo* admins (excluding target); raise `ValidationError('Cannot remove the last sudo administrator', code='last_sudo')` if it would reach zero. Apply in `user_service` for delete/disable/set_role/update_admin.

**[MEDIUM] No "expire in the past" guard on `expire_at`/`activation_deadline`** — `app/schemas/user.py:24,29,54,59`
Both accept past datetimes → instantly-dead user, no warning. UI date inputs (`web/.../users/dialogs.tsx:112,150,317`) have no `min`.
Fix: validator rejecting (or warning on) dates earlier than `now()`; set `min={today}` on the `<Input type=date>` fields.

**[MEDIUM] Privilege fields silently ignored when creating a regular user** — `app/schemas/user.py:32-36`; `app/api/v1/routers/users.py:132-140`; `app/services/user_service.py:80-83,130-151`
`UserCreate` exposes `is_active/is_sudo/all_groups_access/modify_users_access/subscription_url_prefix`, but `_create()` never reads them — POST `/users` with `is_sudo=true` returns 201 with the flag dropped. Misleading contract + latent privilege-escalation footgun. Marzban keeps sudo creation on a separate guarded model.
Fix: split schemas — a `UserCreate` without privilege fields for POST `/users`, and `AdminCreate` carrying `is_sudo` etc. Or add `extra='forbid'` + drop admin fields so the API rejects rather than ignores.

**[LOW] `device_limit` and `on_hold_duration_seconds` have no upper bound** — `app/schemas/user.py:30,27,60,57`
Only `ge=0`. A typo (9999999) overflows downstream logic + UI; inputs (`dialogs.tsx:124-129,139-145`) have `min` but no `max`. `data_limit_bytes` likewise only `ge=0`.
Fix: add `le=` bounds (`device_limit le=1000`, `on_hold_duration_seconds le=10*365*86400`) + matching `max=` on inputs with a clear message.

**[LOW] Subscription URL prefix accepted without URL validation** — `app/schemas/user.py:36,48`; `web/.../admins/dialog.tsx:56,128-136`
Only `max_length=512`, no scheme/host check, yet the UI placeholder says `https://sub.example.com` and the value is concatenated into sub URLs → malformed value silently breaks links.
Fix: validate with AnyHttpUrl-style check (must start `http(s)://`, no path beyond host), message 'Subscription URL prefix must be a valid https:// URL'. Mirror client-side in `admins/dialog`.

**[LOW] Username immutable on edit but no normalization / reserved-name guard** — `app/schemas/user.py:11,18`; `app/services/user_service.py:130-151`
Stored as-is (no server-side trim/lowercase; UI trims at `dialogs.tsx:211`, API doesn't). Case-only differing users may collide by collation; no guard against reserved names like `me` (collides with `/users/me`).
Fix: normalize server-side (strip; decide + apply a case policy); reject a small reserved set; keep the regex error message in one place.

**[LOW] Clearing fields on edit is ambiguous (silently wipes limits)** — `web/components/console/screens/users/dialogs.tsx:62-70`
`EditUserDialog` always sends `data_limit_bytes`/`expire_at`/`device_limit` as value-or-null and `update_quota` (`service:258-259`) writes unconditionally. Opening edit just to change `full_name` with a blank "Data limit" wipes an existing limit to unlimited, no warning.
Fix: pre-fill every field and/or send only changed fields in the PATCH; optionally confirm when an edit would remove an existing limit/expiry.

---

## 7) General polish

**[HIGH] Two parallel modal systems (warp-dlg vs `<Modal>`) — pick one** — `nodes/dialog.tsx:81`, `admins/dialog.tsx:77`, `groups/dialog.tsx:60`, `profiles/dialog.tsx:218`, `profiles/host-dialog.tsx:104` vs `users/dialogs.tsx:81,279`
Two incompatible systems side by side. Header `15px/500` (`globals.css:5266`) vs `text-base font-semibold` (`modal.tsx:34`); Modal has `backdrop-blur-sm`, warp-dlg doesn't; mobile bottom-sheet behavior diverges. `host-dialog.tsx` imports Modal (`line 7`) but renders warp-dlg.
Fix: standardize on `<Modal title onClose onSubmit footer>` for Node/Admin/Group/Profile/Host dialogs; delete warp-dlg markup + the dead CSS (`globals.css 5247-5312, 5508-5511`); finish the host-dialog migration. *(Same root cause as §2 item 1 — do once.)*

**[HIGH] Inconsistent footer button styling (warp-tb-button vs `<Button>`)** — `nodes/dialog.tsx:127-130`, `admins/dialog.tsx:178-181`, `groups/dialog.tsx:116-119`, `profiles/dialog.tsx:339-342`, `host-dialog.tsx:226-229` vs `users/dialogs.tsx:87-94,285-296`
warp footers use raw `<button className="warp-tb-button">`; Modal dialogs use `<Button variant>`; drawer Edit (`parts.tsx:77`) uses a third path (`<Button>` default `md`=h-10). Different heights/radii/hover.
Fix: after consolidating on `<Modal>`, render every footer with `<Button variant="outline">Cancel</Button>` + `<Button type="submit" variant="primary" disabled={busy}>`.

**[HIGH] Two `Field` definitions lay out oppositely** — `parts.tsx:87` (vertical) vs `nodes/dialog.tsx:137` (local) + `globals.css:5277-5300` (horizontal); `profiles/dialog.tsx:225` (`warp-dlg-body-flow` hack)
Shared `Field` stacks label-on-top; `.warp-dlg-field` lays label-left/input-right. `profiles/dialog.tsx` adds `warp-dlg-body-flow` (`225`) purely to force the shared vertical Field to behave inside a warp shell — proof the systems fight. `nodes/dialog.tsx` ships a duplicate local Field.
Fix: delete the local Field + the row-layout CSS; use the single vertical `Field` from `parts.tsx` everywhere; removes the `warp-dlg-body-flow` workaround. *(Same root cause as §2 item 2.)*

**[MEDIUM] `Switch` component defined 3 times** — `subscription-settings.tsx:281`, `admins/dialog.tsx:188`, `profiles/host-dialog.tsx:261` (`api-keys.tsx:18` imports the subscription copy)
Same toggle copy-pasted; off-state drifts (`bg-line` in admins `dialog.tsx:198` vs `bg-hairline` in host-dialog `:270`).
Fix: one `<Switch>` in `components/ui/`, single off token (`bg-line`); import in all four; delete the local copies.

**[MEDIUM] Section accordion + Toggle + CheckBox duplicated** — `profiles/dialog.tsx:349`, `profiles/host-dialog.tsx:236` (Section); `host-dialog.tsx:283` (Toggle); `groups/settings.tsx:262` (CheckBox)
Two near-identical collapsible `Section`s with different a11y (`role=button tabIndex=0` vs real `<button>`), plus one-off Toggle/CheckBox.
Fix: promote the profiles `Section` (has `action` slot + keyboard handling) to `parts.tsx`; move Toggle/CheckBox to shared primitives. ~80 lines removed, unified a11y.

**[MEDIUM] Three table implementations — kit vs raw `<table>`** — `warp-table.tsx` kit vs `api-keys.tsx:118-154`, `audit-log.tsx:49-78`, `groups/settings.tsx:225-257`
Index screens use the polished kit; api-keys, audit-log, group members hand-roll `<table>` with repeated literal `<th>` classes (uppercase tracking-widest ≠ `WarpHead`) and ad-hoc hover, plus hand-written `<td colSpan>` loading/empty.
Fix: route the three through `WarpTableCard/WarpHead/WarpRow` (or extract `<DataTable cols rows>`) for identical header style, hover, skeleton, empty state.

**[MEDIUM] Empty states inconsistent (icon+CTA kit vs bare text)** — `warp-table.tsx:318` (WarpEmpty, `cta` unused) vs `api-keys.tsx:132`, `audit-log.tsx:64`, `groups/settings.tsx:251`, `users/dialogs.tsx:159,331,350`, `admins/dialog.tsx:163`, `users/access.tsx:302`
Three tiers: `WarpEmpty` (icon+text), bare `<td>` text, tiny inline muted strings. `WarpEmpty` exposes a `cta` prop (`warp-table.tsx:324`) that no index screen passes — first-run shows "No nodes yet." with no Add button.
Fix: use `WarpEmpty` everywhere a list can be empty; pass `cta={{label:'Add node', onClick}}` on index screens; standardize picker empty strings to one muted size.

**[MEDIUM] Ad-hoc inline styles with hardcoded hex instead of tokens** — `audit-log.tsx:38`, `nodes/index.tsx:79`, `users/access.tsx:604`, `admins/dialog.tsx:161`, `nodes/detail.tsx:201`, `profiles/index.tsx:277`
The search magnifier `style={{position:'absolute',left:14,color:'#707070',pointerEvents:'none'}}` is copy-pasted in `audit-log.tsx:38` + `nodes/index.tsx:79` with hardcoded `#707070` (not `fg-muted`). `access.tsx:604` hardcodes chart color `#008ffb`; several `marginLeft:auto`/`marginTop:0` nudges should be classes.
Fix: extract `<SearchInput>` (icon+input, `text-fg-muted`) used by audit-log + nodes; replace inline margins with Tailwind classes; move chart color to a token.

**[LOW] Drawer header weight differs from Modal/dialog headers** — `parts.tsx:65` (`text-sm font-medium`) vs `ui/modal.tsx:34` (`text-base font-semibold`) vs `globals.css:5266` (15px/500); `security-settings.tsx:127` overrides with `text-lg`
Three title typographies for the same concept; SecuritySettings has to pass `text-lg` to compensate, proving the Drawer default is too small.
Fix: one heading style (`text-base font-semibold`) for Modal, Drawer, and the consolidated dialog; bake into the Drawer so screens stop overriding.

---

## Ordered action list

**Tier 0 — foundational refactor (do first; unblocks many UI items).** *Larger feature.*
1. Consolidate all dialogs onto the shared `<Modal>` + vertical `<Field>` + `<Button>`/`<Input>`/`<Select>`; delete warp-dlg markup/CSS and the local `nodes` Field; remove the `warp-dlg-body-flow` hack. Covers §2 items 1-2,4-8 and §7 items 1-3. — `nodes/dialog.tsx`, `admins/dialog.tsx`, `groups/dialog.tsx`, `profiles/dialog.tsx`, `profiles/host-dialog.tsx`, `globals.css:5241-5313,5446-5508`

**Tier 1 — high-severity backend correctness / data-integrity.** *Larger features.*
2. Add `UserStatus` enum + persisted indexed `status` column; compute/persist on every state change; expose on `UserRead` + list filter. — `app/domain/user.py:85-132`
3. Add `AssignmentStatus.LIMITED` (or `disabled_reason`); reactivate only LIMITED on reset. — `app/agent/reconcile.py:61-76`, `app/domain/client_assignment.py:34-37`
4. Persist `status='limited'` on over-limit + add `lifetime_used_traffic` and reset accumulation. — `app/traffic/service.py:251-283`, `app/agent/reconcile.py:53-59`
5. Server-side sort/status/search params on `listUsers`; key the infinite query on them. — `web/.../users/index.tsx:74-80,241-254`
6. `profile-update-interval` days fix (rename to days or convert hours→days on emit; fix schema bound). — `app/api/v1/routers/subscriptions.py:400`, `app/schemas/settings.py:55`

**Tier 2 — high-severity validation guardrails.** *Quick backend + small UI.*
7. `model_validator` on Create/Update: reject on_hold+expire_at and on_hold-without-duration with Marzban-style messages. — `app/services/user_service.py:28-38`, `app/schemas/user.py:24-29,54-59`
8. Last-sudo-admin lockout guard on delete/disable/demote/clear-sudo. — `app/services/user_service.py`, `app/api/v1/routers/users.py`
9. Disable Create button + inline error for empty on-hold duration / missing fixed date. *(Quick UI.)* — `web/.../users/dialogs.tsx:289-296`

**Tier 3 — create-flow parity.** *Quick UI, then a backend feature.*
10. Add Auto-reset + Device-limit fields to the create dialog and send them in `createUser()`. *(Quick UI.)* — `web/.../users/dialogs.tsx:210-327`
11. Atomic create endpoint accepting group/profile ids (replace the `Promise.allSettled` fan-out). *(Larger feature.)* — `web/.../users/dialogs.tsx:226-270`

**Tier 4 — high-impact user-table UX.** *Quick-to-medium UI.*
12. Replace usage donut with the existing `WarpTraffic` horizontal bar; widen the column. *(Quick UI.)* — `web/.../users/index.tsx:417-423`
13. Relative expiry helper + urgency-colored badge; reuse in detail drawer. *(Quick UI.)* — `web/.../users/index.tsx:424-426,650-653`
14. Online status dot + last-seen relative text via `usersLastSeen`. *(Medium UI.)* — `web/.../users/index.tsx:398-402`
15. Clickable sortable headers with chevron. *(Medium UI.)* — `web/.../users/index.tsx:344-358`, `warp-table.tsx:162-173`

**Tier 5 — subscription format coverage.** *Medium backend.*
16. Version-aware UA matcher → `XRAY_JSON` for modern v2rayN/NG/Streisand/Happ. — `app/api/v1/routers/subscriptions.py:74`
17. Add Outline format + renderer + UA routing. — `app/subscription/formats/registry.py:72`, `schemas.py:20-36`, `subscriptions.py:64`
18. Per-user `content-disposition` filename + `profile-web-page-url` header. *(Quick.)* — `app/api/v1/routers/subscriptions.py:396-398`

**Tier 6 — backend model extras.** *Medium backend.*
19. `online_at` tracking. — `app/domain/user.py:93-94`
20. `note` / `auto_delete_in_days` (+ purge job) / `edit_at`. — `app/domain/user.py:72-153`
21. Collapse on_hold redundancy once `status` exists. — `app/domain/user.py:113-130`

**Tier 7 — shared-component dedup + polish.** *Quick UI cleanups (mostly absorbed once Tier 0 lands).*
22. One `<Switch>` primitive (single off token). — `ui/`, `subscription-settings.tsx:281`, `admins/dialog.tsx:188`, `host-dialog.tsx:261`
23. Shared `Section`/`Toggle`/`CheckBox` in `parts.tsx`. — `profiles/dialog.tsx:349`, `host-dialog.tsx:236,283`, `groups/settings.tsx:262`
24. Route api-keys/audit-log/group-members through the table kit; use `WarpEmpty` + pass `cta` on index screens. — `api-keys.tsx`, `audit-log.tsx`, `groups/settings.tsx`, `warp-table.tsx:318`
25. Extract `<SearchInput>`; replace inline hex/margins with tokens/classes. — `audit-log.tsx:38`, `nodes/index.tsx:79`, `users/access.tsx:604`
26. One heading style for Modal/Drawer/dialog; bake into Drawer. — `parts.tsx:65`, `ui/modal.tsx:34`
27. Remaining low-severity field bounds/normalization/validation: numeric `le=` caps, sub-URL-prefix validation, username normalization + reserved names, past-date guard, edit-clears-limit confirmation, status icons, table density, checkbox-Field rhythm, username inline error, note maxLength, timezone helper, username-length decision. — see §1/§2/§4/§6 LOW items.

**Tier 8 — documented, no action.**
- Subscription revoke (`user_service.py:160-165`) — keep, don't regress; optionally expose `sub_revision` on `UserRead`.
- `subscription-userinfo` upload/download split (`subscriptions.py:387`) — optional; coerce unset `total`/`expire` to `0` not `'None'`.