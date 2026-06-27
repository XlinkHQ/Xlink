This is a documentation/report-writing task. I have all the input I need (the JSON digests). No need to explore the codebase since the digests already contain file references. Let me write the report directly as my final response.

# Marzneshin — Full Read: Architecture & Parity Report for the XLink Team

A complete read of Marzneshin (the Marzban successor) — frontend, backend, features, node/protocol layer, and design tokens — with XLink differences called out and a prioritized adoption plan at the end.

---

## 1) What Marzneshin Is (Architecture Overview)

Marzneshin (`github.com/marzneshin/marzneshin`) is a FastAPI backend + a Vite/React 18 SPA dashboard. Its defining conceptual shift from Marzban is the **Service**: instead of wiring users to inbounds directly, a Service bundles a set of inbounds with a set of users (and gates which admins can use them). It dropped Marzban's user-templates feature entirely.

- **Backend (`app/`)**: flat-ish layout — `config/`, `db/` (`base.py` declarative Base, one big `models.py` for all ORM, one `crud.py` for procedural ops, `migrations/`), `models/` (Pydantic), `routes/` (user/admin/service/node/inbounds/subscription/system), `tasks/` (APScheduler jobs), `marznode/` (gRPC node-agent client), `notification/`, `templates/`, `utils/`, plus `dependencies.py`, `webhooks.py`. Integer PKs, offset pagination.
- **Frontend (`dashboard/`)**: domain-modular `src/modules/<entity>/{api/{queries,commands},components/{tables,dialogs,form-fields,pills},contexts,domain}` with cross-cutting `libs/` (entity-table, dialog, stats-charts) and `features/`. Built on shadcn/ui + TanStack (Query/Table/Router) + i18next + Zustand.
- **Control plane**: PUSH-based — the panel holds a persistent gRPC stream to each node's `marznode` agent.

**XLink in one line:** a more decomposed (DDD-layered) FastAPI backend with a Next.js 15 SPA shell, near-complete feature parity, ahead on failover/audit/providers, but everything in the UI is hand-rolled per screen rather than abstracted.

---

## 2) Frontend Design System + Patterns

**Marzneshin:** React 18.3 + Vite 5.4 + TS 5.7, served as static assets (`dashboard/index.html` → `src/app.tsx`). Storybook + Chromatic + Vitest. Real URL routing via TanStack Router (generated `src/routeTree.gen.ts`, per-module router contexts). TanStack Query v5 where each module owns `api/queries/*.query.ts` and `api/commands/*.command.ts` (mutation hooks bundling toast + `invalidateQueries`). The centerpiece is **`libs/entity-table`**: a generic `<EntityTable columns fetchEntity primaryFilter entityKey onCreate onOpen/>` that builds a structured query key `[entityKey,{page,size},primaryFilter,{sortBy,desc},{filters}]`, runs `useQuery`, feeds `useReactTable`, and renders header/rows/skeleton/pagination/search/column-visibility generically. Every screen is just `ColumnDef<T>[]` + a fetcher + create/edit dialogs. Create/edit is standardized via `common/hooks/use-mutation-dialog` (react-hook-form + `zodResolver` + create/update mutation). Full i18next (en/fa/ar/ru/zh + Kurdish, RTL, dayjs sync). Zustand for UI state.

**XLink differs:**
- Next.js 15 App Router used essentially as a **static SPA host** — `web/app/page.tsx` renders one `<ConsoleV2/>`, all screens `"use client"`, no SSR data. Playwright e2e only, no unit tests/Storybook.
- **Hand-rolled router** in `components/console/console.tsx`: `keyFromPath()` maps pathname/hash to a `NAV_ITEMS` key, `history.pushState` + `popstate`. Screens switched by string state, not route files.
- TanStack Query v5 but **no mutation hooks** — components call bare async fns from `lib/api.ts` inside local `act()`/`bulk()` helpers, then manually `qc.invalidateQueries`. Optimistic update is hand-written (`setActiveOptimistic` in `users/index.tsx`).
- **No generic table.** Each screen (`users/index.tsx` ~770 lines, plus nodes/admins/groups/profiles) re-implements list/filter/sort/pagination inline with `warp-*` primitives (`WarpTableCard`, `WarpHead`, `WarpRow`, `WarpBadge`, `WarpTraffic`, `WarpSkeleton`, `WarpEmpty` in `screens/warp-table.tsx`). Filter/sort/search are **in-memory in JS** (so search only filters already-loaded users); pagination is `useInfiniteQuery` + "Load more".
- **No column defs** — cells are inline JSX inside `.map()` (the status-badge ladder + `WarpTraffic` live inline at `users/index.tsx` lines ~417–453). Row menu is an inline `WarpMenu` items array.
- **Bespoke dialogs** (`users/dialogs.tsx` `EditUserDialog`/`UserDialog`): manual `useState` per field, manual `onChange`, manual GiB↔bytes, manual try/catch, **no schema validation**. Built on `components/ui/modal.tsx` + a `Field` helper; `confirmDialog()` for deletes.
- **Minimal 6-file UI kit** (`components/ui`: badge, button, dialog, input, modal, toast) plus `warp-*` primitives. No real select/popover/tabs primitives — selects are native `<select>`; menus are a portal+scrim `WarpMenu`.
- **No i18n** — all strings hardcoded English. No Zustand — UI state is local `useState` + ad-hoc `localStorage` (`readPref`/`writePref`, `xlink.*` keys).
- Flatter structure: `web/{app,components/console/screens/<entity>,components/ui,lib}`, all API in one `lib/api.ts`.

**Takeaway:** Parity on raw capability and a polished, on-brand `warp-*` design system, but XLink pays a heavy copy-paste tax. The big wins are an EntityTable abstraction, per-entity mutation hooks + a `useMutationDialog` (react-hook-form/zod), and a real router.

---

## 3) Backend Model / Lifecycle

**Marzneshin:** A `User` (subscriber) with a **separate `Admin` table** as owner; a `Service` join-entity bundles inbounds and gates access. User status is a **derived 5-state lifecycle** (active/disabled/limited/expired/on_hold) computed from `enabled` + `activated` + `expired` (hybrid_property over `expire_strategy`+`expire_date`) + `data_limit_reached`; the `status` property collapses to ACTIVE/INACTIVE, full 5-state surfaced in API/UI. Traffic = `used_traffic` + `lifetime_used_traffic` with hourly `NodeUserUsage` rows. Expire strategies: NEVER / FIXED_DATE / START_ON_FIRST_USE (+ `usage_duration`, `activation_deadline`). Reset strategies: no_reset/day/week/month/year via `tasks/reset_user_data_usage.py`. `online_at`, `sub_updated_at`, `sub_last_user_agent` on User; `revoke_user_sub` regenerates `key` + stamps `sub_revoked_at`. Soft delete via `remove_user` (username=None, removed=True). APScheduler `tasks/`: `record_usages`, `review_users`, `expire_days_reached`, `data_usage_percent_reached`, `reset_user_data_usage`, `nodes`.

**XLink differs (meaningfully):**
- **Unified `users` table** — admins are Users with `role=ADMIN` plus `is_sudo`/`all_groups_access`/`modify_users_access`/`subscription_url_prefix`/`users_data_usage` on the same row; `owner_id` self-FK links subscribers to their admin. (Marzneshin keeps Admin and User separate.) Already mirrors the Marzneshin field set.
- **No Service entity** — uses `Group` (admin scoping via `admin_groups`) + `Profile` + per-`(user,profile,node)` `ClientAssignment`. Inbound access is materialized into concrete assignments with credentials rather than a logical bundle.
- **Status is per-assignment, not per-user.** User has only `is_active` + `removed`. `AssignmentStatus` (active/disabled/expired/limited) carries the real lifecycle. The human-facing 5-state is **not persisted** — computed lazily at render in `subscription/generator.py` `_user_status` (on_hold → activation_deadline → is_active → expire_at → data_limit).
- Same expire enum + `on_hold`/`on_hold_duration_seconds`/`activation_deadline`; `activate_on_hold` in `subscription/repository.py` converts on_hold→`expire_at` on first fetch. (parity)
- **No user-level `used_traffic`** — usage lives on `ClientAssignment.used_bytes` + `traffic_limit_bytes`; `traffic/` package aggregates. User has only `users_data_usage` (admin aggregate).
- `DataResetStrategy` enum + `last_reset_at` exist, but **the periodic reset job is missing** (`scheduler/` is failover scoring; `notify_data_reset` exists but no recurring zeroing task).
- **No `online_at`** — presence inferred via `UserDevice.last_seen_at` on subscription fetch.
- `revoke_subscription` increments `sub_revision` (no `sub_revoked_at`, no rotated key). `sub_updated_at` + `sub_last_user_agent` via `touch_subscription` (parity).
- Soft delete is a **superset**: `delete()` sets `removed`+`is_active=False`+disables assignments, plus `restore()` and `purge()`.
- **No central user-lifecycle task package.** Limit enforcement is push-based in `traffic/service.py` (`_enforce_limit`/`_enforce_user_limits` mark `LIMITED` on ingest). Missing: time-based expiry sweeps (`expire_days_reached`) and percent-reached alerts (`data_usage_percent_reached`).
- More decomposed overall: `domain/` (one ORM per file), `repositories/`, `services/`, `schemas/`, `api/v1/routers/`, plus `providers/`, `traffic/`, `failover/`, `gitops/`, `backup/`, `webhooks/`, `monitoring/`, `events/`, `notifications/`. UUID PKs everywhere (`UUIDPrimaryKeyMixin`, `PGUUID`), keyset/cursor pagination, Redis cache. Settings via `AppSettings` singleton (`app/domain/app_settings.py`) — richer than Marzneshin (per-status text, subscription rules JSON, custom HTML, xray core template).

**Takeaway:** XLink's layering and lifecycle (restore/purge, signed commands, UUID+keyset) are ahead. The genuine gaps are: a single shared **computed-status helper at the User level** (today it only exists inside the subscription generator), a denormalized **user-level `used_traffic`** for fast list rendering + user-level "limited", and **periodic review jobs** (expiry sweep, percent-reached alerts, data reset).

---

## 4) Features

**Marzneshin** dashboard has 8 modules (users, services, nodes, hosts, inbounds, admins, settings, auth). Core product features:
- Per-user data limits + 3 expire strategies + data-reset strategies; 5-state status.
- Multi-node with per-node xray "backends", `connection_backend` (grpclib/grpcio), `usage_coefficient` for load distribution/fault tolerance.
- Subscription links: links / base64-links / xray / sing-box / clash / clash-meta / template / block (~8 `ConfigTypes`), selected per-client via `SubscriptionRule` (regex on User-Agent); QR/share generator.
- Multi-admin RBAC: `is_sudo`, `all_services_access`, `modify_users_access`, `enabled`, per-admin `service_ids`, `subscription_url_prefix`.
- Host management (SNI/host/path/ALPN/fingerprint/security overrides per inbound).
- Telegram + webhook notifications on lifecycle events; system/node/traffic stats; integrated CLI.
- **Dropped Marzban's user-templates** — no user-template model.

**XLink differs (near-complete parity, several areas ahead):**
- User model parity in `app/domain/user.py` (`UserExpireStrategy`, `DataResetStrategy`, on_hold, `data_limit_bytes`, `expire_at`, `activation_deadline`); status texts configurable in `app_settings`.
- No user templates either (parity). `app/templates` is Jinja subscription pages. Optional differentiator: quick-create presets (data_limit+expire+group).
- Service ≈ **Group** (`app/domain/group.py`, `profile_ids[]`, `admin_groups` M2M); the web nav even labels Groups as "Services" (`web/components/console/nav.ts`). Profiles/InboundHosts are the inbound equivalent.
- Nodes (`app/domain/node.py`): name/host/port/status/`usage_coefficient`/`max_users`/`current_users`/`last_seen_at`/`node_metadata`/`profiles[]`, plus a **dedicated failover subsystem** (`app/failover/` auto/planner/executor/service) and xray release/version service. Minor gap: no explicit per-node `connection_backend` selector (XLink uses its own agent transport — not parity-critical).
- **20 subscription formats** in `app/subscription/formats/` (base64, clash, mihomo, singbox, xray_json, vmess, vless, trojan, shadowsocks, hysteria2, tuic, naive, wireguard, socks, http_proxy, uri, text, …) vs Marzneshin's ~8. Ensure QR + share-link UI exists to match.
- Subscription rules parity: `app/schemas/settings.py` `SubscriptionRule {pattern, result}` (validated regex, up to 64), persisted as JSON by `settings_service.py`.
- RBAC parity + ahead: same fields in `app/schemas/user.py`, plus `totp_enabled` (2FA), audit log, API keys; promote/demote + enable/disable-an-admin's-users endpoints in `app/api/v1/routers/users.py`.
- **Bulk actions are client-side loops** — `users/index.tsx` iterates selected IDs via `bulk()`; `app/api` lacks `/bulk` routes. Gap: true server-side batch endpoints for atomic/fast large selections.
- Notifications ahead: `app/webhooks/dispatcher.py` (generic webhook + secret, Discord, Telegram) + proactive `app/notifications/job.py` (USER_EXPIRING_SOON / USER_DATA_WARNING) and lifecycle events in `app/webhooks/events.py`.
- Stats: `app/api/v1/routers/monitoring.py` (`/summary`, `/metrics`, `/system`, `/prometheus`); web `usage-chart.tsx` (ApexCharts) + `dashboard.tsx`. Polish: explicit per-node / per-user usage widgets to match Marzneshin's `nodes-usage-widget`.
- Host management ahead: `app/domain/inbound_host.py` adds fragment, noise, mux, chaining (`chain_target_id`), weight, `is_universal`, `is_disabled`. UI `web/.../screens/profiles/host-dialog.tsx`.
- CLI parity: `app/cli/` + `app/api/v1/routers/cli.py`.

**Takeaway:** Feature parity is essentially complete and XLink exceeds on failover, audit, API keys, GitOps, device limits, node pinning, formats, and hosts. The only real gaps are server-side bulk endpoints and (optionally) QR/share + per-node usage widgets.

---

## 5) Node / Protocol Layer

**Marzneshin (PUSH / streaming):** The panel holds a persistent gRPC channel to each node's `marznode` agent. Two interchangeable backends — **grpcio** (`insecure_channel`, no TLS) and **grpclib** (mutual-TLS via a single shared client cert: `ssl.create_default_context()` + `load_cert_chain`, `check_hostname=False`, `CERT_NONE`). On connect, `_sync()` calls `FetchBackends` (learn cores/inbounds), then `RepopulateUsers` (bulk push); thereafter per-user changes stream over a long-lived bidirectional `SyncUsers` fed by an `asyncio.Queue`. **The core config lives on the node** — the panel only stores a template and fetches/restarts via `FetchBackendConfig`/`RestartBackend(BackendConfig{configuration, config_format=PLAIN|JSON|YAML})`; marznode generates the runtime xray/hysteria2/sing-box config from template + synced users. Data model: Node → Backend (per-node core: name/`backend_type`/version/`running`) → Inbound (tag/protocol/config/node_id) → Service (named inbound bundle) → Users (M2M). Health is connection-driven: `_monitor_channel` watches `ChannelConnectivity` (READY → healthy + resync; else unhealthy + cancel). Logs via `StreamBackendLogs` + WebSocket; usage pulled via `FetchUsersStats`; hourly `NodeUsage` / `NodeUserUsage` (unique on created_at+user_id+node_id); `usage_coefficient` multiplier. A module-global `nodes: dict[int, MarzNodeBase]` registry; `operations.add_node/remove_node/update_user` fan out via `asyncio.ensure_future`.

**XLink (PULL / connectionless — the inverse):**
- No persistent connection, no panel-resident gRPC clients. A stdlib agent **initiates everything**: heartbeat POST, `config_snapshot` GET, command lease/ack. `NodeAgentService` (`app/agent/service.py`) handles per-request. Tradeoff: higher convergence latency (poll interval) vs Marzneshin's near-instant push.
- **Panel computes the full desired config** server-side: `ConfigSyncService.desired_config` → `clients[]` (joined from `ClientAssignment`+`Profile`+`User`) + `core_templates` from `AppSettings.xray_core_template`; provider builders live panel-side (`app/providers/xray/config.py`, `mapper.py`). Hashed to a `config_version`; agent reports applied state; panel diffs desired vs reported → `NodeDriftReport` (severity).
- **Auth is stronger:** per-request HMAC bearer token (`hash_token` at `node.metadata['agent_token_hash']`, `hmac.compare_digest` in `NodeHeartbeatService.authenticate`) + `CommandSigner` signatures on commands. No shared cert with verify disabled.
- **Static `ProviderKind`** {xray, sing-box, hysteria, **wireguard**} via `Provider` ABC + `ProviderRegistry` + capability-based `ProviderCapability`. Adds WireGuard (Marzneshin lacks it) but lacks Marzneshin's **runtime backend discovery** — XLink has `NodeProviderHealth` for status but no versioned per-node backend inventory.
- Flatter inbound mapping: `ClientAssignment(user_id, node_id, profile_id, provider_kind, provider_client_id, credentials, status)` → `Profile(protocol, slug, settings)`. No Service/bundle layer.
- Sync is richer: `assignment_sync` (cursor-paginated keyset on updated_at+id via `NodeSyncService`) **and** full `config_snapshot` with content-hash versioning + drift diff. Verify `SyncCursor` reset falls back to full snapshot when cursor is lost (Marzneshin's implicit "repopulate on reconnect").
- Health finer-grained: `NodeStatus` active/disabled/offline + `mark_stale_offline`, `NodeRecovered`/`NodeOffline` events, plus `NodeProviderHealth` (healthy/degraded/unhealthy/unknown + `latency_ms`).
- Logs/metrics via Redis buffer (`AgentStreamService` push/read) — survives panel restarts; traffic via `TrafficService` batch ingest.
- **Durable signed command queue** (`CommandKind`: apply_config, reload, restart, upgrade, rollback, update_geo, collect_diagnostics, provider_healthcheck) with attempts/lease tokens/expiry; `SelfHealingService` + `AutoUpgradeService` enqueue automatically; `restart_nonce` forces restarts. Strictly better than Marzneshin's fire-and-forget `ensure_future` fan-out.

**Takeaway:** XLink's control plane is more robust (durable signed queue, content-hash drift, per-provider health, rollback/upgrade pinning, stronger auth). Worth borrowing from Marzneshin: (1) **runtime backend discovery** (agent reports which cores/versions it runs → versioned per-node inventory for upgrade targeting + showing `xray_version`); (2) an explicit **`config_format` tag** (plain/json/yaml) on the snapshot so non-xray cores are unambiguous; (3) a per-backend **`running` boolean** in `NodeProviderHealth` (core up-but-not-running); (4) verify traffic-sample dedupe to a `(period,user,node)` grain for idempotent rollups on batch retries.

---

## 6) Design Tokens

**Marzneshin:** standard shadcn/ui — semantic HSL color tokens as bare channel triplets (`--background: 0 0% 100%`) consumed via `hsl(var(--token))`, `.dark` override (`darkMode:["class"]`). Default slate ramp: light = white bg, slate-950 fg (#0a0f1a), slate-100 muted (#f1f5f9), slate-200 borders (#e2e8f0), **dark-navy (not blue) primary**; dark = slate-950 bg, slate-800 (#1e293b) secondary/muted/border, near-white primary, muted-fg #94a3b8. Single `--radius: 0.5rem` → lg(8)/md(6)/sm(4). Fonts: **Lato (body) + Ubuntu (headers)**, default Tailwind sizes, `text-sm`(14) controls, `font-medium`(500) buttons, **`font-semibold`(600) titles/badges**. Roomy: 40px buttons/inputs (h-10), 48px table headers, 24px card/dialog padding (p-6), `shadow-sm` cards, `rounded-full` badges, max-w-lg(512) dialogs with `shadow-lg` + black/80 overlay.

**XLink differs (deliberately denser, true-black, blue, Inter):**
- Hand-rolled hex/rgba vars consumed directly (no `hsl()` wrapper); dark via `.xlink-dark`. Domain-named aliases (surface/canvas/subtle/muted/line) + a `--st-*` status palette. ~5651-line single `app/globals.css`. Theme bus = `lib/theme.ts` (`localStorage xlink-theme` + `CustomEvent('xlink-theme')` + `useTheme()`).
- **Neutrals are essentially identical** to Marzneshin's slate ramp (#0f172a / #64748b / #e2e8f0). Key diff: **primary is blue** (#2563eb light / #0e7ff8 dark) vs Marzneshin's dark navy — keep XLink's blue.
- Dark base diverges: **OLED true-black** (#000 canvas / #141414 surface / #202020 line) vs Marzneshin's blue-tinted slate. Keep XLink's black (WarpProxy match). One nit: XLink's dark secondary text #707070 has less contrast than Marzneshin's #94a3b8 — consider lightening toward ~#8a8a8a.
- **Same 4/6/8 radius scale** (`--corner-sm/--corner/--corner-md`); cards recently unified to 8px. Adopt the split consistently: controls 6px, cards/dialogs 8px.
- Much **denser**: 28px buttons/inputs (`--input-height`) vs 40px; ~8–12px padding vs 24px; flat hairline cards (no default shadow) vs `shadow-sm`; 12px base font vs 14px. All correct for a RouterOS/control-plane UI — keep.
- Fonts: **Inter Variable** (self-hosted) + IBM Plex Mono, single family. Keep — more neutral than Lato/Ubuntu.
- **No-bold rule**: emphasis caps at 500. Do **not** adopt Marzneshin's `font-semibold`(600) titles/badges.
- Badges: pill (1rem), 11px, uppercase, `--st-*` tinted-bg+border (more refined than Marzneshin's solid-fill semantic badges) — keep.
- Modal: `clamp(280,100%,480)` ~ Marzneshin's 512; radius 6px + custom shadow vs 8px + `shadow-lg`; overlay grey-green 50% vs black/80.

**Takeaway:** Parity on neutrals + radius scale; deliberate, correct divergence on density/fonts/dark-base/weights. Small borrowable items: a consistent `focus-visible` ring-2 + offset affordance (XLink uses `--focus-outline` ad hoc), bump modal radius to 8px (`--corner-md`) to match cards, lighten dark secondary text, and consider a slightly stronger modal overlay.

---

## Adopt for XLink — Prioritized

### Quick UI wins (low effort, high leverage)
1. **Factor recurring cell components** (status pill, traffic bar, online dot, expiry value, actions menu) out of the inline `.map()` in `users/index.tsx` (lines ~417–453) into named components reused across screens. No architecture change required.
2. **Consistent focus affordance** — replace ad-hoc `--focus-outline` with a standard `focus-visible` ring-2 + offset across buttons/inputs.
3. **Modal radius → 8px** (`--corner-md`) to match cards; slightly stronger overlay for focus.
4. **Lighten dark secondary text** from #707070 toward ~#8a8a8a for readability.
5. Add **QR + share-link UI** for subscriptions (parity with Marzneshin's auto QR/share) if not already present.

### Bigger frontend features (medium/large)
6. **EntityTable abstraction** (the #1 win) — wrap `warp-*` primitives + TanStack Table into `<EntityTable columns fetchEntity entityKey .../>` with a structured query key. Collapses ~5 near-identical 300–770 line screens, enables real **server-side sort/filter/pagination**, and fixes "search only filters already-loaded users."
7. **Per-entity mutation hooks + `useMutationDialog`** (react-hook-form + zod) — bundle toast + `invalidateQueries`; removes the repeated `act()`/try-catch/invalidate boilerplate and the manual `useState`/`onChange`/GiB↔bytes forms, and adds real client-side validation.
8. **Real router** — give each entity screen its own URL (App Router routes or a small route table), replacing the `keyFromPath`/`pushState`/`popstate` logic in `console.tsx`; enables deep-linking to detail/edit.
9. **Split `lib/api.ts` per entity** into `api/{queries,commands}` colocated with screens (mirrors Marzneshin module layout).
10. **i18next** (en/fa/ar/ru/zh + RTL) — only if the audience needs non-English; even routing strings through `t()` now avoids a painful later refactor. Optionally a tiny **Zustand** store if cross-screen UI state grows.
11. **Component tests / Storybook** for the reusable `warp-*` primitives.

### Backend
12. **Single shared computed-status helper at the User level** — derive the 5-state status (and `expired`/`data_limit_reached` hybrids) in one place so API list/detail, UI, and subscription all agree, instead of only inside `subscription/generator.py._user_status`. Expose 5-state in `UserRead`.
13. **Periodic review jobs** (XLink has the columns/enums but lacks the jobs): time-based **expiry sweep** (`expire_days_reached`), **data-usage-percent-reached** alerts, and the **data-reset job** keyed off `data_reset_strategy` + `last_reset_at`.
14. **Denormalized user-level `used_traffic` + `lifetime_used_traffic`** (summed from assignments) for fast list rendering and user-level "limited" status.
15. **Server-side bulk endpoints** (`/bulk` enable/disable/delete/reset) so large selections are atomic/fast instead of N client-side requests.
16. **Runtime backend discovery** — have the agent report cores/versions it runs (Marzneshin's `FetchBackends`) and persist a versioned per-node inventory for upgrade targeting + `xray_version` display; add a per-backend `running` boolean to `NodeProviderHealth`; add an explicit `config_format` (plain/json/yaml) tag on the snapshot.
17. **Verify** `SyncCursor` reset falls back to full snapshot, and that traffic samples are deduped to a `(period,user,node)` grain (idempotent rollups on batch retries).
18. Optional parity/audit niceties: `User.online_at` (max device last_seen / node activity), `sub_revoked_at` timestamp, `password_reset_at`.

**Net:** XLink already matches or exceeds Marzneshin on backend layering, control-plane robustness, providers, failover, and feature breadth. The highest-ROI work is frontend abstraction (EntityTable + mutation hooks/dialogs + router) to kill per-screen duplication, and a small set of backend review jobs + a unified user-status helper to close the lifecycle gaps.