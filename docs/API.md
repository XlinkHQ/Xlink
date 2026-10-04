# XLink API Reference

Complete reference for the XLink panel HTTP API.

- **Base URL:** `https://<panel-host>`
- **API prefix:** `/api/v1` (configurable via `api_v1_prefix`)
- **OpenAPI / Swagger:** `GET /api/v1/openapi.json` and `/docs` — **disabled in production** (`is_production = true`).
- **Content type:** `application/json` for request and response bodies unless noted (CSV, plain text, Prometheus, binary export).
- **Versioning:** single version, mounted under `/api/v1`. App version comes from the `xlink` package metadata.

Every path below is relative to `/api/v1`. Example: `POST /auth/login` → `POST https://panel/api/v1/auth/login`.

---

## 1. Authentication & Authorization

### Auth schemes

| Scheme | Used by | How |
| --- | --- | --- |
| **Bearer JWT** | Admin/console + user endpoints | `Authorization: Bearer <access_token>` |
| **Signed URL token** | Public subscription feed | Token embedded in the URL path (`/subscriptions/sub/{token}`) — no header |
| **API key** | Programmatic/automation access | API key issued via `/api-keys` |
| **Agent token** | Node agents | Per-node token issued via `/nodes/{id}/agent-token`, sent by the agent on `/agent/*` calls |

### Access tiers (dependency guards)

| Tier | Meaning |
| --- | --- |
| **Public** | No auth (health, public subscription feed, agent bootstrap scripts) |
| **CurrentUser** | Any authenticated user (admin or end user) |
| **AdminUser** | Authenticated admin |
| **WriteAdminUser** | Admin with write permission (mutations) |
| **SudoAdminUser** | Super-admin only (sensitive ops) |

> Admins can only manage users within their scope — service/group restrictions are enforced server-side (`assert_can_manage`).

### Token lifecycle

- `POST /auth/login` → returns access + refresh token pair.
- `POST /auth/refresh` → exchange refresh token for a new pair.
- `POST /auth/logout` / `logout-all` → revoke current / all sessions.
- Optional **TOTP 2FA**: `enroll` → `confirm` → enforced on subsequent logins; `disable` to remove.

---

## 2. Conventions

### Error envelope

All handled errors return:

```json
{ "error": { "code": "STRING_CODE", "message": "Human readable", "details": { } } }
```

`details` is omitted when empty. Validation errors return HTTP `422`. DB integrity errors are mapped to friendly codes (duplicate → conflict, foreign key → reference error, not-null → validation).

### Pagination

Two shapes depending on endpoint:

- **Cursor** (`CursorPage[T]`): `{ "items": [...], "next_cursor": "<opaque|null>" }`. Pass `?cursor=<value>` to fetch the next page.
- **Offset** (`Page[T]`): `{ "items": [...], "meta": { ... } }`.

### Common query params

- `cursor`, `limit` — pagination.
- Filtering/search params vary per resource (see notes).

### Status codes

`200` OK · `201` Created · `202` Accepted (async queued) · `204` No Content · `401` Unauthorized · `403` Forbidden · `404` Not Found · `409` Conflict · `422` Validation · `5xx` Server.

### Middleware

- **CORS** — enabled when `cors_origins` is set.
- **Rate limiting** — `rate_limit_per_minute`, toggle `rate_limit_enabled`, `rate_limit_fail_open` (allow on limiter outage).

---

## 3. Endpoints by resource

Legend for **Auth** column: `Public` · `User` (CurrentUser) · `Admin` · `Write` (WriteAdmin) · `Sudo` · `Agent`.

### 3.1 Health — `/health`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/health/live` | Public | Liveness probe |
| GET | `/health/ready` | Public | Readiness probe (DB/Redis reachable) |

### 3.2 Auth — `/auth`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/register` | Public | Register first/admin account → `201` + token pair |
| POST | `/auth/login` | Public | Login → access + refresh tokens |
| POST | `/auth/2fa/enroll` | User | Begin TOTP enrollment (returns secret/QR) |
| POST | `/auth/2fa/confirm` | User | Confirm TOTP code → `204` |
| POST | `/auth/2fa/disable` | User | Disable TOTP → `204` |
| POST | `/auth/refresh` | Public* | Exchange refresh token → new token pair |
| POST | `/auth/logout` | User | Revoke current session → `204` |
| POST | `/auth/logout-all` | User | Revoke all sessions → `204` |
| POST | `/auth/change-password` | User | Change password → `204` |

\* `refresh` is unauthenticated by header but requires a valid refresh token in the body.

### 3.3 Users — `/users`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/users/me` | User | Current profile |
| PATCH | `/users/me` | User | Update own profile |
| GET | `/users` | Admin | List users (cursor or offset page) |
| GET | `/users/export.csv` | Admin | Export users as CSV |
| POST | `/users` | Write | Create user → `201` (`profile_ids` max 100) |
| POST | `/users/bulk` | Write | Bulk action over up to **1000** users (`enable`, `disable`, `delete`, `reset_usage`, `set_data_limit`, `set_expiry`, `extend_expiry`, `set_reset_strategy`) → `{ok, failed}` |
| GET | `/users/{user_id}` | Admin | Get a user |
| GET | `/users/{user_id}/devices` | Admin | List user devices |
| DELETE | `/users/{user_id}/devices` | Write | Clear user devices → `204` |
| POST | `/users/{user_id}/disable` | Write | Disable user |
| POST | `/users/{user_id}/enable` | Write | Enable user |
| DELETE | `/users/{user_id}` | Write | Soft-delete user → `204` |
| POST | `/users/{user_id}/restore` | Write | Restore deleted user |
| PATCH | `/users/{user_id}` | Write | Update user |
| POST | `/users/{user_id}/revoke-subscription` | Write | Rotate subscription token (invalidates old URL) |
| POST | `/users/{user_id}/promote` | Sudo | Promote user to admin |
| POST | `/users/{user_id}/demote` | Sudo | Demote admin to user |
| POST | `/users/admins` | Sudo | Create an admin → `201` |
| PATCH | `/users/admins/{user_id}` | Sudo | Update an admin |
| GET | `/users/admins/{user_id}/usage` | Sudo | Usage totals for an admin's users |
| POST | `/users/admins/{user_id}/enable-users` | Sudo | Bulk-enable an admin's users |
| POST | `/users/admins/{user_id}/disable-users` | Sudo | Bulk-disable an admin's users |

### 3.4 Nodes — `/nodes`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/nodes/xray-versions` | Admin | List installable **stable** Xray-core releases (prereleases/drafts filtered, cached 1h) |
| POST | `/nodes` | Sudo | Create node → `201` |
| GET | `/nodes` | Admin | List nodes (cursor page) |
| GET | `/nodes/{node_id}` | Admin | Get node + metadata (incl. `xray_version`, health) |
| PATCH | `/nodes/{node_id}` | Sudo | Update node |
| POST | `/nodes/{node_id}/status` | Sudo | Set node status |
| POST | `/nodes/{node_id}/disable` | Sudo | Disable node |
| POST | `/nodes/{node_id}/restart-core` | Sudo | Queue a core restart on the node |
| POST | `/nodes/{node_id}/heartbeat` | Sudo | Node heartbeat |
| POST | `/nodes/{node_id}/agent-token` | Sudo | Issue/rotate the node's agent token |
| GET | `/nodes/{node_id}/cores` | Admin | Per-core health/status on the node |
| DELETE | `/nodes/{node_id}` | Sudo | Delete node → `204` |

### 3.5 Profiles — `/profiles`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/profiles/keys` | Write | Generate provider keys for a profile |
| POST | `/profiles` | Sudo | Create profile → `201` |
| GET | `/profiles` | Admin | List profiles (cursor page) |
| GET | `/profiles/{profile_id}` | Admin | Get profile |
| PATCH | `/profiles/{profile_id}` | Sudo | Update profile |
| POST | `/profiles/{profile_id}/disable` | Sudo | Disable profile |
| DELETE | `/profiles/{profile_id}` | Sudo | Delete profile → `204` |

### 3.6 Groups — `/groups`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/groups` | Write | Create group → `201` |
| GET | `/groups` | Admin | List groups |
| GET | `/groups/{group_id}` | Admin | Get group |
| PATCH | `/groups/{group_id}` | Write | Update group |
| DELETE | `/groups/{group_id}` | Write | Delete group → `204` |

### 3.7 Inbound Hosts — `/inbound-hosts`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/inbound-hosts` | Write | Create inbound host → `201` |
| GET | `/inbound-hosts` | Admin | List inbound hosts |
| GET | `/inbound-hosts/{host_id}` | Admin | Get inbound host |
| PATCH | `/inbound-hosts/{host_id}` | Write | Update inbound host |
| DELETE | `/inbound-hosts/{host_id}` | Write | Delete → `204` |

### 3.8 Providers — `/providers`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/providers` | Admin | List available provider cores (xray, sing-box, hysteria, wireguard) and their capabilities |

### 3.9 Assignments — `/assignments`

User ↔ inbound/service bindings.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/assignments` | Write | Create assignment → `201` |
| GET | `/assignments` | Admin | List assignments (cursor page) |
| GET | `/assignments/{assignment_id}` | Admin | Get assignment |
| PATCH | `/assignments/{assignment_id}` | Write | Update assignment |
| POST | `/assignments/{assignment_id}/disable` | Write | Disable assignment |
| DELETE | `/assignments/{assignment_id}` | Write | Delete → `204` |

### 3.10 Subscriptions — `/subscriptions`

Generates client configs. Public feed authenticates by **signed token in the URL**, not JWT.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/subscriptions/sub/{token}` | Public (token) | **Public subscription feed** — raw config for VPN clients. Output format negotiated by `User-Agent` / query (base64, clash, mihomo, singbox, xray-json, uri, etc.) |
| GET | `/subscriptions/my/token` | User | Get own subscription URL + token (`?scope=USER\|PROFILE\|ASSIGNMENT`) |
| GET | `/subscriptions/users/{user_id}/token` | Admin | Get subscription URL for a specific user |
| GET | `/subscriptions/assignments/{assignment_id}/config` | Admin | Single-assignment config |
| GET | `/subscriptions/assignments/{assignment_id}/feed` | Admin | Feed scoped to one assignment |
| GET | `/subscriptions/profiles/{profile_id}/feed` | Admin | Feed scoped to a profile |
| GET | `/subscriptions/users/{user_id}/feed` | Admin | Feed scoped to a user |

**Supported output formats** (auto-selected or forced): `base64`, `uri`, `text`, `clash`, `mihomo`, `singbox`, `xray_json`, `shadowsocks`, `trojan`, `vless`, `vmess`, `tuic`, `hysteria2`, `wireguard`, `naive`, `socks`, `http_proxy`.

**Token notes:** signed, carries `user_id` + `scope` + `revision`. `revoke-subscription` / token rotation bumps the revision, instantly invalidating old URLs.

### 3.11 Traffic — `/traffic`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/traffic/summary` | Sudo | Global totals (up/down bytes) — feeds dashboard chart |
| GET | `/traffic/throughput` | Sudo | Up/down throughput over a trailing window (`window_seconds`, 1–3600) |
| GET | `/traffic/online` | Sudo | Currently online users |
| GET | `/traffic/assignments/{assignment_id}` | Admin | Usage for one assignment |
| GET | `/traffic/nodes` | Sudo | Per-node usage |
| GET | `/traffic/nodes/{node_id}/users` | Sudo | Per-user usage on a node |
| GET | `/traffic/users/{user_id}/nodes` | Admin | Per-node usage for a user |
| GET | `/traffic/nodes/{node_id}/usage-series` | Sudo | Time series for a node |
| GET | `/traffic/profiles/{profile_id}/usage-series` | Sudo | Time series for a profile |
| GET | `/traffic/profiles/{profile_id}/usage` | Sudo | Profile usage total |
| GET | `/traffic/users/{user_id}/usage-series` | Admin | Time series for a user |
| POST | `/traffic/users/usage` | Admin | Batch usage for a set of users |
| POST | `/traffic/users/last-seen` | Admin | Batch last-seen for a set of users |
| POST | `/traffic/users/{user_id}/reset` | Write | Reset a user's usage counter |
| GET | `/traffic/retention` | Sudo | Retention policy |
| POST | `/traffic/cleanup` | Sudo | Purge old traffic rows |

### 3.12 Monitoring — `/monitoring`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/monitoring/summary` | Admin | Metrics snapshot |
| GET | `/monitoring/metrics` | Admin | Raw metric list |
| POST | `/monitoring/restart` | Write | Restart a monitored service → `202` |
| GET | `/monitoring/prometheus` | Admin | Prometheus exposition format |
| GET | `/monitoring/system` | Admin | System stats (CPU/RAM/disk) |

### 3.13 Scheduler — `/scheduler`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/scheduler/policies` | Admin | List scheduling policies |
| POST | `/scheduler/run` | Write | Run a scheduling decision pass |

### 3.14 Failover — `/failover`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/failover/plan` | Admin | Compute a failover plan |
| POST | `/failover/execute` | Write | Execute failover |

### 3.15 Backup — `/backup`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/backup/export` | Sudo | Create a backup record |
| GET | `/backup/export-db` | Sudo | Download a DB dump (binary) |
| POST | `/backup/import-db` | Sudo | Import a DB dump → `204` |
| POST | `/backup/restore` | Sudo | Restore from backup |

### 3.16 GitOps — `/gitops`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/gitops/commit` | Sudo | Commit current config state to git |
| POST | `/gitops/diff` | Admin | Diff current state vs git |
| GET | `/gitops/records` | Admin | List past GitOps commit records |

### 3.17 Settings — `/settings`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/settings/subscription` | Admin | Subscription page/template settings |
| PATCH | `/settings/subscription` | Sudo | Update subscription settings |
| GET | `/settings/notifications` | Sudo | Webhook / Discord / Telegram notification settings |
| PATCH | `/settings/notifications` | Sudo | Update notification settings |
| POST | `/settings/notifications/test` | Sudo | Send a test notification to the configured channels |
| GET | `/settings/warp` | Sudo | WARP integration settings |
| PATCH | `/settings/warp` | Sudo | Update WARP settings |
| GET | `/settings/core` | Admin | Core config templates (xray/sing-box/…) |
| PUT | `/settings/core` | Sudo | Replace core templates |

### 3.18 Audit — `/audit`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/audit` | Sudo | Audit log entries |
| GET | `/audit/export.csv` | Sudo | Export the audit log as CSV |

### 3.19 API Keys — `/api-keys`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api-keys` | Admin | List API keys (page) |
| POST | `/api-keys` | Write | Create API key → `201` (**secret shown once**) |
| DELETE | `/api-keys/{key_id}` | Write | Disable key → `204` |
| POST | `/api-keys/{key_id}/enable` | Write | Re-enable key |
| DELETE | `/api-keys/{key_id}/purge` | Write | Permanently delete key → `204` |

### 3.20 CLI — `/cli`

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/cli` | Admin | Execute a CLI-style command, returns structured result |

### 3.21 Certificates — `/certificates`

TLS certificates used by nodes and the subscription host. ACME issuance is
HTTP-01, served from `/.well-known/acme-challenge/{token}` on the panel itself.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/certificates` | Sudo | List managed certificates (domain, source, validity window) |
| POST | `/certificates` | Sudo | Import a certificate + private key manually → `201` |
| POST | `/certificates/acme` | Sudo | Request/renew a certificate over ACME → `201` |
| DELETE | `/certificates/{cert_id}` | Sudo | Delete a certificate → `204` |

Renewal runs on a scheduled job inside a configurable window; ACME issuance for
due domains is performed concurrently (bounded), while the resulting DB writes
stay sequential.

### 3.22 User Templates — `/user-templates`

Reusable defaults (data limit, expiry, reset strategy, profiles) applied when
creating users.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/user-templates` | Admin | List templates |
| POST | `/user-templates` | Write | Create template → `201` |
| PATCH | `/user-templates/{template_id}` | Write | Update template |
| DELETE | `/user-templates/{template_id}` | Write | Delete template → `204` |

### 3.23 Routing — `/routing`

Routing rules and outbounds for the node cores. Rules are evaluated in priority
order; outbounds are the targets a rule can send matched traffic to.

**Rules**

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/routing/rules` | Admin | List routing rules (priority order) |
| POST | `/routing/rules` | Sudo | Create rule → `201` |
| PATCH | `/routing/rules/{rule_id}` | Sudo | Update rule |
| DELETE | `/routing/rules/{rule_id}` | Sudo | Delete rule → `204` |

**Outbounds**

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/routing/outbounds` | Sudo | List outbounds |
| POST | `/routing/outbounds` | Sudo | Create outbound → `201` |
| PATCH | `/routing/outbounds/{outbound_id}` | Sudo | Update outbound |
| DELETE | `/routing/outbounds/{outbound_id}` | Sudo | Delete outbound → `204` |
| POST | `/routing/outbounds/import` | Sudo | Import an outbound from a share link / JSON blob |
| POST | `/routing/outbounds/ping` | Sudo | Latency-test an arbitrary outbound payload before saving |
| POST | `/routing/outbounds/{outbound_id}/ping` | Sudo | Latency-test a saved outbound |

Ping spins up a throwaway local core instance against the outbound and reports
`{ok, latency_ms, detail}` — it never mutates stored state.

---

## 4. Agent protocol — `/agent`

Node agents authenticate with their per-node **agent token**. Pull-based config + SSE wake.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/agent/install.sh` | Public | Agent installer script (not in schema) |
| GET | `/agent/xlink-agent.py` | Public | Agent source (not in schema) |
| GET | `/agent/nodes/{node_id}/config` | Agent | **Desired config** for the node (pull) |
| GET | `/agent/nodes/{node_id}/events` | Agent | SSE stream — wake signal to re-pull config |
| POST | `/agent/nodes/{node_id}/traffic` | Agent | Report per-client traffic deltas |
| POST | `/agent/nodes/{node_id}/connections` | Agent | Report active connections |
| POST | `/agent/nodes/{node_id}/state` | Agent | Report drift (running vs desired) |
| POST | `/agent/nodes/{node_id}/provider-health` | Agent | Report per-core health |
| POST | `/agent/nodes/{node_id}/metrics` | Agent | Report node metrics |
| POST | `/agent/nodes/{node_id}/logs` | Agent | Ship core logs |
| POST | `/agent/nodes/{node_id}/commands/lease` | Agent | Lease a pending command |
| POST | `/agent/nodes/{node_id}/commands/result` | Agent | Report command result |
| POST | `/agent/nodes/{node_id}/commands` | Write | Enqueue a command for the node → `201` |
| GET | `/agent/nodes/{node_id}/logs/recent` | Admin | Recent shipped logs |
| GET | `/agent/nodes/{node_id}/metrics/recent` | Admin | Recent shipped metrics |

**Command kinds** issued via `/agent/.../commands` (and `issueAgentCommand` in the console): `upgrade` (`payload.target_version`), `update_geo`, restart, etc.

**Config-pull cycle:** agent polls `/config` on interval (default 10s) and on SSE wake; applies per-core with a config hash to avoid reload storms (only the changed core reloads).

---

## 5. Examples

### Login

```bash
curl -X POST https://panel/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"secret"}'
# → { "access_token": "...", "refresh_token": "...", "token_type": "bearer" }
```

### Authenticated request

```bash
curl https://panel/api/v1/users \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Get own subscription URL

```bash
curl https://panel/api/v1/subscriptions/my/token \
  -H "Authorization: Bearer $ACCESS_TOKEN"
# → { "token": "...", "subscription_url": "https://panel/api/v1/subscriptions/sub/<token>" }
```

### Public subscription feed (VPN client)

```bash
curl https://panel/api/v1/subscriptions/sub/<token> \
  -H 'User-Agent: ClashMeta'
# → config in the client's expected format
```

### Create a user

```bash
curl -X POST https://panel/api/v1/users \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"username":"alice","data_limit_bytes":1073741824}'
```

### Error response

```json
{ "error": { "code": "CONFLICT", "message": "username already exists" } }
```

---

## 6. Notes

- **OpenAPI in production:** disabled. To explore the schema, run a non-production instance and open `/docs`.
- **Subscription token rotation:** `POST /users/{id}/revoke-subscription` invalidates all existing subscription URLs for that user.
- **API keys:** the secret is returned **only at creation** — store it immediately.
- **Cursor vs offset:** `/users` supports both shapes; most list endpoints use cursor pages.
- **Soft delete:** users are soft-deleted (`DELETE /users/{id}`) and can be restored (`/restore`).
