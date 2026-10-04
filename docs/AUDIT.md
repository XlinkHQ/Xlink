# XLink — Codebase Audit & Cleanup Report

**Date:** 2026-09-12 · **Version:** `xlink` 1.1.0 · **Branch:** `main` @ `8fb83dd`
**Status:** cleanup applied — see §13 for what changed. §4, §5, §6 describe the
findings as they were *before* the fixes; §13 records the resolution of each.

Full read-through of the panel: FastAPI backend (`app/`), Next.js console (`web/`),
node agent (`node-agent/`), and the supporting infrastructure. This document records
what was checked, what is healthy, what is broken, and what should be removed.

---

## 1. Verdict

The codebase is in **good health**. The architecture is deliberate and consistently
applied, the async model is correct, and the test suite is green. There is **no
critical bug** in the backend.

The real findings are concentrated in two places:

1. **`web/app/globals.css`** — 6 undefined CSS custom properties used without a
   fallback (silently dropped declarations) plus ~500 lines of dead rules.
2. **`docs/API.md`** — 32 live endpoints are undocumented; three whole resource
   sections are missing.

| Area | Status |
| --- | --- |
| Async correctness | Clean — no blocking call inside any coroutine |
| Backend tests | 730 passed, 8 skipped (skips need a live Postgres) |
| Web typecheck (`tsc --noEmit`) | Clean — exit 0 |
| Web type escapes (`any`, `@ts-ignore`) | Zero |
| Auth guards on routes | Complete — every route is guarded or deliberately public |
| ORM N+1 risk | Structurally impossible (`lazy="noload"` on every relationship) |
| Dead backend modules | None |
| Dead CSS | ~501 lines / 103 classes |
| API documentation drift | 32 endpoints undocumented |

---

## 2. Repository map

```
Xlink/
├── app/                    FastAPI backend — 359 files, ~38k lines
│   ├── main.py             create_app(): middleware stack + /metrics + ACME challenge
│   ├── core/               config, security, authz, cache, jobs, leader, lifespan
│   ├── api/v1/             router.py aggregates 24 routers → 159 endpoints
│   ├── domain/             SQLAlchemy ORM models (17)
│   ├── repositories/       data access (12)
│   ├── services/           business logic (21)
│   ├── schemas/            Pydantic DTOs (15)
│   ├── dependencies/       DI wiring (auth, core, services)
│   ├── middleware/         request context, audit, rate limit, security headers
│   └── <vertical slices>   agent/ traffic/ subscription/ providers/ failover/
│                           gitops/ backup/ monitoring/ scheduler/ events/
│                           webhooks/ notifications/ observability/
├── web/                    Next.js 15 + React 19 console — 131 TS/TSX files
│   ├── app/                App Router: layout, [[...slug]] catch-all, globals.css
│   ├── components/         console/ (shell, sidebar, topbar, palette) + ui/ (10 primitives)
│   ├── features/           one folder per domain (users, nodes, profiles, routing, …)
│   ├── lib/                api/ clients, i18n/ (en/fa/ru/zh), helpers
│   └── shared/             warp-table, usage-chart, settings-kit, parts
├── node-agent/             single-file sync Python agent + installers + tests
├── alembic/                DB migrations
├── docker/                 Dockerfile, Caddyfile, entrypoint
├── sdk/python/             published client SDK
├── subscription-page/      standalone subscription renderer
├── loadtest/               locust suite
└── docs/                   API.md, ARCHITECTURE.md, BACKEND_REFACTOR_PLAN.md, AUDIT.md
```

### Backend size by package

| Package | Files | Lines |
| --- | ---: | ---: |
| `subscription/` | 43 | 4698 |
| `tests/` | 36 | 4606 |
| `agent/` | 31 | 5156 |
| `api/` | 29 | 4148 |
| `services/` | 21 | 3145 |
| `providers/` | 38 | 2416 |
| `traffic/` | 14 | 2558 |
| `core/` | 12 | 1579 |
| everything else | 135 | ~9700 |

---

## 3. Async review — clean

An AST pass over every non-test backend file checked each `async def` body for
blocking calls (`time.sleep`, `subprocess.*`, `urllib.request.urlopen`,
`requests.*`, bare `open`).

**Result: zero violations.**

Every blocking operation is correctly offloaded:

| Site | Mechanism |
| --- | --- |
| `services/xray_releases.py` GitHub releases fetch | `anyio.to_thread.run_sync(self._fetch)` |
| `webhooks/dispatcher.py` outbound POST | `asyncio.to_thread(_post, …)` |
| `api/v1/routers/monitoring.py` system stats | `anyio.to_thread.run_sync(_collect_system_stats)` |
| `services/outbound_ping.py` temp config write | `anyio.to_thread.run_sync(_write_config)` |
| `services/outbound_ping.py` xray / curl | `asyncio.create_subprocess_exec` |

`node-agent/xlink-agent.py` uses `time.sleep` and `subprocess.run` freely — correct,
it is a deliberately synchronous standalone daemon, not part of the event loop.

### Lifespan symmetry — verified

`app/core/lifespan.py` starts 14 background jobs and stops **all 14** in the `finally`
block, followed by `events.drain()`, `dispatcher.drain()`, `cache.close()`,
`db.dispose()`. No task leak on shutdown.

`WebhookDispatcher` tracks its fire-and-forget tasks in a `set` with
`task.add_done_callback(self._tasks.discard)` and exposes `drain()` — no orphaned
tasks, no unawaited-coroutine warnings.

---

## 4. Bugs

### 4.1 Undefined CSS tokens with no fallback — **real, user-visible**

`web/app/globals.css` references 11 custom properties that are never defined.
Five have a fallback value and are therefore harmless. **Six do not** — the browser
discards those declarations entirely, so the styling silently does not apply.
This is the same defect class as commit `8fb83dd`.

| Token | Uses | Location | Effect of the dropped declaration |
| --- | ---: | --- | --- |
| `--warp-radius` | 5 | `globals.css:3740,3741,3746,3747,3780` | login inputs/submit render with square corners |
| `--warp-blue` | 2 | `globals.css:3753,3765` | login input focus ring has no color |
| `--warp-submit` | 1 | `globals.css:3779` | login submit button has no background |
| `--warp-submit-hover` | 1 | `globals.css:3795` | no hover state on submit |
| `--font-xs` | 2 | `globals.css:3205,3578` | `.assignment-context b`, `.feed-summary span` inherit parent size |
| `--shadow-soft` | 1 | `globals.css:790` | toggle knob renders flat |
| `--fg` | 2 | `globals.css:5879,5881` | `.warp-cert-name`, `.warp-cert-meta b` fall back to inherited color |

**Mitigating detail:** the `--warp-*` four sit inside the `.warp-form-signin` block,
which is dead code (see §5.1) — `features/login/LoginScreen.tsx` uses `warp-login-*`
classes instead. Deleting that block fixes four of the six at once.

**Fixes:**

- `--font-xs` → the scale defines `--font-sm` / `--font-md`; add `--font-xs: 11px`
  next to them, or substitute the existing token.
- `--shadow-soft` → substitute the defined `--shadow-xs` or `--shadow-sm`.
- `--fg` → substitute `--fg-default` (`--fg-muted` is already used on the adjacent
  line 5880, so the intent is clearly the default foreground token).
- `--warp-radius` / `--warp-blue` / `--warp-submit` / `--warp-submit-hover` →
  resolved by deleting the dead `.warp-form-signin` block.

Five tokens are used **with** a fallback and are cosmetically fine, but should be
defined or replaced for consistency: `--border-emphasis` (10 uses, falls back to
`#939CA9`), `--form-width`, `--space-xl`, `--surface`, and the `.next/` copies of `--fg`.

### 4.2 Weak production admin password does not block startup — **by design, worth knowing**

`app/core/lifespan.py:250-254`: when `is_production`, a bootstrap admin password that
fails `validate_password_strength` is logged as `admin_bootstrap_weak_password` and
re-raised — but the enclosing `except Exception: logger.exception(...)` at line 271
swallows it. Startup continues without the admin user.

This is *safe* (no weak admin is ever created) and the failure is loud in the logs,
but the operator gets a running panel with no admin rather than a hard stop. If a
hard stop is wanted, re-raise `ValueError` outside the broad handler.

### 4.3 Subscription cache key degrades to a shared bucket on Redis failure — **acceptable**

`app/subscription/service.py:236-239`: if the revision `mget_int` fails, both revisions
become `None` → `g0:r0`. Entries written during an outage land in the same revision
bucket and survive a later `invalidate_*` bump.

**Not a security issue** — `subject_id`, `scope`, `version` and `format` are all still
in the key, so no cross-tenant leak is possible. Worst case is a stale feed for one
subject until the TTL expires. Documented here so it is not rediscovered as a bug.

---

## 5. Dead code to remove

### 5.1 Dead CSS — 103 classes, ~501 lines (7% of `globals.css`)

`web/app/globals.css` is 7031 lines / 210 KB. A block-level scan against every
`.ts`/`.tsx` file (accounting for template-literal class construction — the file
contains no dynamically assembled `warp-` prefixes, so a literal match is sound)
found **171 rule blocks whose every selector class appears nowhere in the app**.

Largest cluster — the superseded login form (`globals.css:3695-3809`, ~90 lines):

```
.warp-form-signin          .warp-form-signin input[type="text"]
.warp-form-signin .warp-logo   .warp-form-signin input[type="password"]
.warp-signin               .warp-form-signin input[type="submit"]
.warp-loader-processor-button  + autofill / placeholder / focus variants
```

`features/login/LoginScreen.tsx` uses `warp-login-page`, `warp-login-form`,
`warp-login-field`, `warp-login-submit` — an entirely separate, live block.
Deleting the old block removes ~90 lines and fixes four undefined tokens.

Other dead clusters: `warp-card-header`/`warp-card-dot`/`warp-card-body`/
`warp-card-collapsed`/`warp-card-head-right`, `warp-chart`/`warp-chart-empty`/
`warp-traffic-legend`, `warp-tab-dark-light` (28 lines), `warp-cfg-*` (12 classes),
`warp-sb-bottom`/`warp-sb-footer`/`warp-sb-active`, `warp-info-row`, `warp-log-row`,
`warp-chip`/`warp-chips`, `warp-btn`, `warp-input`, `warp-logo`, `warp-mstat`,
`warp-drawer-panel`, `warp-kbd-group`, `warp-menu-sep`, `warp-radial-pct`.

Recommendation: delete the login block first (biggest win, fixes bugs), then sweep
the rest. Re-run the scan after each batch.

### 5.2 Unused CSS tokens — 71

Defined in `:root` / `.xlink-dark`, referenced nowhere. Mostly an unused half of the
raw palette and the spacing scale: `--p-accent-50/100/200/300/700/800`,
`--p-neutral-300/400/700/950/975/1000`, `--p-danger-600`, `--p-info-600`,
`--p-success-600`, `--p-warning-600`, `--s-1` through `--s-12`, `--space-16`,
`--space-24`, `--dur-1/3/4`, `--ease-in`, `--ease-out`, `--control-sm`, `--control-md`,
`--radius-xs`, `--radius-2xl`, `--shadow-xs`, `--shadow-sm`, `--skeleton-base`,
`--skeleton-shimmer`, `--st-*-bd` border tokens, `--info-bg/fg/solid`, `--lime`,
`--nav-rail`, `--menu-shadow`, `--scrim`, `--fw-bold`, `--fw-semibold`, `--font-lg`,
`--line-height`, `--bg-subheader`, `--fg-subheader`.

Keep the raw `--p-*` palette (it is the design system's source layer, intentionally
complete). The rest — the `--s-*` scale in particular — is genuinely unused and can go.

### 5.3 Dead TypeScript exports — 3

Confirmed zero call sites anywhere in the app:

- `web/lib/api/subscription.ts:46` — `subscriptionFeed()`
- `web/lib/api/users.ts:85` — `updateUserTemplate()`
- `web/lib/api/users.ts:236` — `promoteUser()`

`promoteUser` is notable: `POST /users/{id}/promote` exists server-side and
`demoteUser` *is* wired into the console — so promote is a half-connected feature, not
just dead code. Decide: wire it into the admins UI, or delete both ends.

The 23 "unused exported types" knip reports are **false positives** — they are the
typed API surface (`AuthResponse`, `SystemStatsRead`, `TrafficTotals`, …) and must stay.
The `lib/i18n/index.ts` re-export hits (`translate`, `getLocale`) are also false
positives: `index.ts` deliberately re-exports the `locale.ts` public surface.

### 5.4 Unused devDependencies — 2

`eslint` and `eslint-config-next` are installed and `package.json` declares
`"lint": "next lint"`, but no `eslint.config.*` / `.eslintrc*` exists in `web/`, so
the script cannot run. Either add a config (recommended — it would have caught the
CSS-adjacent issues earlier) or drop both packages and the `lint` script.

### 5.5 No dead backend code

Every module under `app/` is reachable. The scan's apparent hits were all false
positives, each verified:

- all 24 files in `api/v1/routers/` are imported and mounted in `api/v1/router.py`;
- all 9 `subscription/formats/*.py` renderers are registered in `formats/registry.py`;
- `api/v1/outbound_import.py` is a deliberate lazy import at `routers/routing.py:292`;
- `middleware/headers.py` (`find_header`) is used by `request_context.py` and `rate_limit.py`;
- test files are collected by pytest, not imported.

---

## 6. Lint & type status

### Ruff — 90 findings, 0 functional

`app/` (56): 31 × `N802` invalid-function-name (generated gRPC stubs — should be
ignored per-file), 8 × `SIM300` yoda-conditions, 3 × `E402`, 3 × `SIM102`, 2 × `E501`,
2 × `N801`, 2 × `N806`, and single hits of `E731`, `RUF100`, `SIM108`, `SIM115`, `UP009`.

`node-agent/` (34): 14 × `E501`, 9 × `UP031` printf-formatting, 3 × `SIM115`,
3 × `UP032`, 2 × `RUF100`, plus `E741`, `F401`, `SIM105`.

Two worth actually fixing:

- `node-agent/test_wg_builder.py:5` — `F401`, `pytest` imported but unused.
- `node-agent/xlink-agent.py:429` — `E741`, ambiguous variable name `l`.

The one `ASYNC230` (blocking `open` in an async function) is in `loadtest/seed.py:37`
— a load-test script, not shipped code.

`app/services/outbound_ping.py:72` `SIM115` is a **false positive**: the
`NamedTemporaryFile` is closed in a `finally` and the path is passed on deliberately.

`ruff check --fix` clears 17 of the 90 safely.

### Mypy — config drift, not code bugs

- **Missing stubs**: `types-PyYAML`, `types-grpcio-health-checking`,
  `types-grpcio-reflection`. Add them to the dev dependencies.
- **Missing annotations** (`no-untyped-def`, `type-arg`): `traffic/scheduler.py:30,96`,
  `observability/collector.py:27,86`, `subscription/repository.py:48,87,135`,
  `repositories/user.py:112`, `services/acme_issuer.py:37`, `core/authz.py:82`,
  `services/outbound_ping.py:172`.
- **Mypy internal crash** at `app/repositories/user.py:158` (mypy 2.1.0). Upstream bug,
  not a code defect — but it means that file is not fully checked. Try a newer mypy.
- `josepy.JWKRSA` attr-defined at `services/acme_issuer.py:45` — upstream export issue,
  needs a targeted `# type: ignore[attr-defined]`.

### Web

`tsc --noEmit` exits 0. Zero `any`, zero `as any`, zero `@ts-ignore`/`@ts-expect-error`,
zero `eslint-disable`, one intentional `console.warn` (`lib/api/internal.ts:29`).
This is the cleanest part of the codebase.

---

## 7. Documentation drift

`docs/API.md` documents 129 route signatures; the code exposes **159**.

**32 live endpoints have no documentation.** Three whole resources are missing:

| Resource | Missing endpoints |
| --- | --- |
| `/routing` | `GET/POST/PATCH/DELETE /routing/rules`, `GET/POST/PATCH/DELETE /routing/outbounds`, `POST /routing/outbounds/import`, `POST /routing/outbounds/ping`, `POST /routing/outbounds/{id}/ping` |
| `/certificates` | `GET /certificates`, `POST /certificates`, `POST /certificates/acme`, `DELETE /certificates/{id}` |
| `/user-templates` | `GET`, `POST`, `PATCH /{id}`, `DELETE /{id}` |

Plus scattered gaps: `DELETE /nodes/{id}`, `DELETE /profiles/{id}`,
`GET /nodes/{id}/cores`, `GET /traffic/throughput`, `GET /audit/export.csv`,
`GET /gitops/records`, `GET|PATCH /settings/notifications`,
`POST /settings/notifications/test`, `GET|PATCH /settings/warp`,
`GET /users/admins/{id}/usage`, `POST /users/bulk`.

Stale in the other direction: `GET /api/v1/openapi.json` is documented as available,
but `app/main.py:28` sets `openapi_url=None` when `is_production` — the doc says
"disabled in production" in prose, so this is just worth making explicit in the table.

`docs/ARCHITECTURE.md` (16 KB) still matches the code.

`docs/BACKEND_REFACTOR_PLAN.md` is correctly marked **"PLAN ONLY. No backend code has
been changed."** and that is still true — `app/` remains the documented split-brain
(9 domains spread across `domain/` + `repositories/` + `services/` + `schemas/` +
`api/v1/routers/`, the other 12 already vertical slices). The plan is accurate; it is
simply not executed.

---

## 8. Files & directories to remove

### Untracked build artifacts (safe to delete, all regenerate)

| Path | Size | Note |
| --- | ---: | --- |
| `.mypy_cache/` | 33 MB | **not in `.gitignore`** — add it |
| `.VSCodeCounter/` | 832 KB | already gitignored; stale, dated `2026-07-08` |
| `.ruff_cache/` | 352 KB | gitignored |
| `.pytest_cache/` | 84 KB | gitignored |
| `__pycache__/` × 55 | — | gitignored |
| `.DS_Store` × 4 | — | gitignored |
| `web/test-results/` | 4 KB | only a stale `.last-run.json` from 2026-06-24 |

```bash
# from the repo root
find . -name __pycache__ -type d -not -path './.venv/*' -not -path './node_modules/*' -exec rm -rf {} +
find . -name '.DS_Store' -not -path './.venv/*' -not -path './node_modules/*' -delete
rm -rf .mypy_cache .ruff_cache .pytest_cache .VSCodeCounter web/test-results
```

Then add to `.gitignore`:

```
.mypy_cache/
web/test-results/
```

### Pending in git

`web/public/favicon.svg` is deleted in the working tree but the deletion is not
committed. No source file references it (`web/public/` holds `xlink-logo.png`,
`login.png`, `fonts/`, `warp/`, `routeros-icons/`, `settings-icons/`). The deletion
is safe — commit it.

### Keep — checked and justified

`sdk/python/` (published client SDK), `subscription-page/` (standalone service with
its own Dockerfile), `loadtest/` (locust suite), `scripts/backfill_wg.py` (one-shot
migration helper, keep for reruns), `docker/`, `alembic/`, `data/providers/`,
`backups/` (gitignored, local only).

---

## 9. Security posture

Audited every route for an auth guard. **All 159 are correctly guarded.**

Deliberately public, and correct:

- `GET /health/live`, `GET /health/ready` — liveness/readiness probes.
- `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` — the auth
  entry points themselves (all rate-limited by `RateLimitMiddleware`).
- `GET /subscriptions/sub/{token}` — signed-URL token in the path is the credential.
- `GET /agent/install.sh`, `GET /agent/xlink-agent.py` — bootstrap scripts, served
  before a node has a token. They expose agent source, not secrets. Acceptable, but
  if node enrollment is ever tightened these are the two to put behind a one-time token.

All 13 `/agent/nodes/{id}/*` routes require the `X-Agent-Token` header and call
`agent.authenticate(node_id, token)`, or require `SudoAdminUser`
(`POST /commands`, `GET /logs/recent`, `GET /metrics/recent`). Verified individually.

Other controls confirmed in place:

- `/metrics` compares the bearer token with `hmac.compare_digest` and 404s when no
  token is configured (`main.py:70-84`) — no timing leak, no accidental exposure.
- CORS sets `allow_credentials=False` whenever origins include `*` — correct, avoids
  the credentialed-wildcard hole.
- `TrustedHostMiddleware`, `SecurityHeadersMiddleware` (production-aware), and
  `RateLimitMiddleware` (with `trusted_proxy_ips`, explicit `fail_open` flag) are all wired.
- Swagger/OpenAPI disabled when `is_production`.
- `webhooks/dispatcher.py` blocks redirects (`_NoRedirect`) and guards against SSRF to
  private addresses (`_assert_public_host`, `_GuardedHTTPHandler`) — matches the
  hardening recorded earlier.
- No secret ever reaches a log call; the grep for token/password/secret in log
  statements returns only counters and metadata.
- `git ls-files` finds no tracked `.env`, `.pem`, `.key`, or `deploy.env.production`.
  `.gitignore` covers them explicitly with a `!.env.example` exception.

---

## 10. What is genuinely good

Worth recording so it is not "cleaned up" by accident:

- **`lazy="noload"` on every ORM relationship** (`domain/user.py`, `node.py`,
  `profile.py`, `client_assignment.py`, `refresh_token.py`, `group.py`). Lazy loading
  cannot silently fire in a request, so the classic async-SQLAlchemy N+1 and
  `MissingGreenlet` failures are structurally impossible. Joins are explicit. This is
  the single best decision in the backend — do not "fix" it by adding lazy loads.
- **Exception handling is honest.** Every broad `except Exception` found is either a
  shutdown-path guard or is paired with a specific `logger.warning`/`logger.exception`
  carrying context. No silent swallowing.
- **Cache degradation is graceful.** Redis failures in `subscription/service.py` and
  `agent/config_sync.py` log and fall through rather than failing the request.
- **The DB layer handles real deployments**: optional read replica with its own pool
  sizing, PgBouncer mode (`NullPool` + `statement_cache_size=0`), `pool_pre_ping`,
  `pool_recycle`, and SQLite branch for tests.
- **Leader election** (`core/leader.py`) gates the background jobs, so a multi-replica
  deployment does not run the schedulers N times.
- **The frontend is disciplined**: no `any`, no `@ts-ignore`, no disabled lint rules,
  a real 4-locale i18n layer, and a consistent `.warp-*` design system.

---

## 11. Recommended order of work

**Fix (correctness):**
1. Delete the dead `.warp-form-signin` block, `globals.css:3695-3809` — removes ~90
   lines and fixes 4 of the 6 dropped declarations at once.
2. Resolve the remaining undefined tokens: `--font-xs` (define as `11px`),
   `--shadow-soft` → `--shadow-xs`, `--fg` → `--fg-default`.
3. Decide on `promoteUser`: wire it to the existing `POST /users/{id}/promote` in the
   admins UI, or delete both it and the dead client function.

**Clean (hygiene):**
4. Delete the build artifacts in §8; add `.mypy_cache/` and `web/test-results/` to `.gitignore`.
5. Commit the pending `web/public/favicon.svg` deletion.
6. `ruff check --fix` (17 safe), then fix `F401` in `node-agent/test_wg_builder.py:5`
   and `E741` in `node-agent/xlink-agent.py:429`.
7. Add `types-PyYAML`, `types-grpcio-health-checking`, `types-grpcio-reflection`;
   add the ~11 missing annotations; per-file-ignore `N802` for `app/agent/grpc/*_pb2*.py`.
8. Sweep the remaining dead CSS (~410 lines) and the unused `--s-*` scale.
9. Either add an ESLint config to `web/` or drop `eslint` + `eslint-config-next` and
   the `lint` script.

**Document:**
10. Add the `/routing`, `/certificates`, and `/user-templates` sections to
    `docs/API.md` plus the 11 scattered missing endpoints.

**Do not do now:**
- The `BACKEND_REFACTOR_PLAN.md` restructure. It is a large move-and-rewrite with no
  behavior change; the current split-brain is ugly but harmless. Nothing in this audit
  depends on it.

---

## 12. How to reproduce this audit

```bash
# backend: tests, lint, types
.venv/bin/python -m pytest -q
.venv/bin/ruff check app node-agent --statistics
.venv/bin/mypy app

# web: types + dead code
cd web && npx tsc --noEmit && npx knip
```

The CSS-token and dead-CSS scans, the async AST pass, the route-guard sweep, and the
API-drift diff were one-off scripts written for this audit; the checks they perform are
described in §3, §4.1, §5.1, §7 and §9 in enough detail to rebuild them. Wiring the
undefined-token check into CI would prevent recurrences of the §4.1 bug class, which
has now appeared twice.

---

## 13. Cleanup applied (2026-09-12)

Everything below was executed and verified after the audit above was written.

### Bugs fixed

| Bug | Fix |
| --- | --- |
| `--warp-radius`, `--warp-blue`, `--warp-submit`, `--warp-submit-hover` undefined (§4.1) | Removed with the dead `.warp-form-signin` block |
| `--font-xs` undefined, 2 uses | → `var(--font-sm)` (`11px`, the intended value) |
| `--shadow-soft` undefined, 1 use | → `var(--shadow-xs)` |
| `--fg` undefined, 2 uses | → `var(--fg-default)` (matches `--fg-muted` on the adjacent line) |
| 5 `node-agent` test files uncollectable from the repo root | Agent path now resolved via `_HERE`, matching `test_wg_builder.py` |

**Zero `var()` references without a fallback now point at an undefined token.**

The node-agent test bug was not in the original audit — it surfaced during cleanup.
`test_cores.py`, `test_drain.py`, `test_local_enforce.py`, `test_traffic.py` and
`test_wal_and_command.py` loaded the agent via the bare relative path
`"xlink-agent.py"`, so they only collected when pytest ran from inside `node-agent/`.
From the repo root all five died with `FileNotFoundError` at collection.

### Test suite expanded: 730 → 776 passing

Four test directories existed but were absent from `testpaths`, so 46 passing tests
never ran in CI. All added to `pyproject.toml`:

`app/providers/hysteria/tests`, `app/providers/singbox/tests`,
`app/providers/wireguard/tests`, `node-agent`.

### Dead code removed

| Item | Amount |
| --- | ---: |
| Dead CSS rule blocks (158 blocks) | 514 lines |
| Dead `--s-1` … `--s-12` spacing scale (zero uses) | 9 lines |
| **`globals.css` total** | **7031 → 6507 lines (210 KB → 188 KB)** |

Deletion was verified against a pre-edit backup: **no class that was previously
styled lost its styling.** The 12 classes now used in TSX without a CSS rule were
all already unstyled before this cleanup (semantic hooks and prefix matches such as
`warp-font`, `warp-table`, `warp-cli`) — pre-existing and harmless.

`warp-toast-success` / `-error` / `-info` were explicitly protected from deletion:
`components/ui/toast.tsx:43` builds the class dynamically as `warp-toast-${t.type}`,
so a literal-match scan reports them as dead when they are not.

### Lint: 90 → 41 findings

- `ruff check --fix` applied 16 safe fixes.
- `node-agent/test_wg_builder.py:5` — removed the unused `pytest` import (`F401`).
- `node-agent/xlink-agent.py:429` — renamed the ambiguous `l` to `line` and wrapped
  the comprehension (`E741` + `E501`).
- Added per-file ignores for code that must not be renamed:
  `app/agent/grpc/agent_pb2_grpc.py` (protoc-generated) and
  `app/agent/grpc/servicer.py` (method names are fixed by the `.proto` service contract).

The 41 remaining are cosmetic and confined to `node-agent/xlink-agent.py`
(`E501`, `UP031`, `SIM102`, `SIM115`).

### Artifacts deleted

`.mypy_cache/` (33 MB), `.VSCodeCounter/`, `.ruff_cache/`, `.pytest_cache/`,
`web/test-results/`, `web/tsconfig.tsbuildinfo`, 55 × `__pycache__/`, 4 × `.DS_Store`.

`.gitignore` gained `.mypy_cache/`, `web/test-results/`, `*.tsbuildinfo`.

### Checked and NOT removed

- **Images — every one is live.** `web/public/` holds 23 files and all are referenced.
  The 5 `settings-icons/*.png` first appeared dead to a literal path scan; they are
  built dynamically at `features/settings/settings.tsx:32` via ``const IMG =
  "/settings-icons"`` and ```${IMG}/customization.png` ``. `docs/assets/logo.png` is
  used by `README.md`. Only the 2 `.DS_Store` files were junk, and they are gone.
- **71 → 82 unused CSS tokens, kept.** Most sit on packed multi-token lines inside
  coherent scales (`--dur-1/2/3/4`, `--z-*`, `--control-sm/md/lg`, `--space-*`) whose
  siblings are live. Deleting individual members would leave broken half-scales — the
  token layer is the design system's API. Only the fully-dead `--s-*` scale was removed.
  The raw `--p-*` palette is the intentional source layer and stays complete.
- **`xlink` and `xlink.sh`, both kept.** Not duplicates: `xlink` is a thin CLI wrapper
  (`docker compose exec api python -m app.cli.main`), `xlink.sh` is the 14 KB installer.
- **3 unused API client functions — awaiting your decision.** `promoteUser`,
  `updateUserTemplate`, `subscriptionFeed` (§5.3). Each is one member of an otherwise
  complete CRUD set backed by a live endpoint, so removing one leaves the client
  asymmetric. Not touched.

### Still open

Nothing from the original audit — §17 closed the last two items.

### Verification

```
pytest                776 passed, 8 skipped   (was 730 passed, 8 skipped)
ruff check app node-agent    41 findings      (was 90)
tsc --noEmit          exit 0
globals.css           brace balance 0, 6507 lines
```

The 8 skips are unchanged and expected — they need `XLINK_TEST_DATABASE_URL` pointing
at a live PostgreSQL.

---

## 14. Second pass — performance fixes and API docs (2026-09-12)

Found by reading the concurrency-sensitive paths rather than by counting files.

### Unbounded fan-out capped

`UserCreate.profile_ids` and `GroupCreate`/`GroupUpdate.profile_ids` had no
`max_length`, while the sibling bulk endpoint already capped at 1000 — an
oversight, not a decision. A create carrying 500 profile ids issued 500 sequential
round-trips. All three now cap at `MAX_PROFILE_IDS = 100`.

### N+1 removed from user creation

`POST /users` called `profiles.get(profile_id)` once per id inside the assignment
loop. Added `ProfileRepository.list_by_ids()` (single `IN` query) and
`ProfileService.list_by_ids()` (same `NotFoundError` semantics as `get()`), and the
router now resolves every profile in one query. The assignment creation itself
stays sequential — each `assignments.create()` reserves a node slot on the shared
session, so parallelising it would corrupt the capacity counter.

### ACME renewal parallelised

`renew_due()` issued certificates one domain at a time, each a full network
round-trip to the ACME server. Issuance now runs concurrently under
`asyncio.Semaphore(_ACME_RENEW_CONCURRENCY = 4)` — bounded to stay within ACME rate
limits — while the DB writes stay sequential because they share one session.
Failures are captured per-domain and still recorded in `cert.last_error`.

### API documentation drift closed

`docs/API.md` went from 32 undocumented endpoints to **0**, verified by
re-running the route-vs-doc diff:

- new §3.21 Certificates, §3.22 User Templates, §3.23 Routing (rules + outbounds)
- added the 11 scattered missing rows (`DELETE /nodes/{id}`, `GET /nodes/{id}/cores`,
  `DELETE /profiles/{id}`, `GET /traffic/throughput`, `GET /audit/export.csv`,
  `GET /gitops/records`, `GET|PATCH /settings/notifications`,
  `POST /settings/notifications/test`, `GET|PATCH /settings/warp`,
  `GET /users/admins/{id}/usage`, `POST /users/bulk`)
- **corrected ~20 wrong auth guards.** Many rows claimed `Write` where the code
  requires `Sudo` (all node mutations, all profile mutations, most of `/traffic`,
  `/audit`, `/gitops/commit`, `PUT /settings/core`). The doc was understating the
  privilege needed, which is the dangerous direction to be wrong in.

### Not changed, and why

- **`bulk_action`'s per-user loop.** It opens a savepoint per user deliberately:
  one bad user must not roll back the other 999. The 1000 cap bounds it. Converting
  to a set-based UPDATE would lose the per-user `assert_can_manage` check and the
  per-user error isolation.
- **Doc/file layout.** Root keeps the GitHub-convention files (README, CONTRIBUTING,
  SECURITY, CODE_OF_CONDUCT, CHANGELOG, DEPLOY) and `docs/` keeps the deep
  references. Moving them would break the README and CHANGELOG links for no gain.
  `docs/AUDIT.md` and `docs/BACKEND_REFACTOR_PLAN.md` were simply missing from
  README's Documentation table; both are now listed.

---

## 15. Third pass — type safety, lint, and tests for the weak spots

### The mypy crash was hiding 411 errors

`app/repositories/user.py:158` unpacked a `dict.get()` result with a default
(`col, desc, _ = self._KEYSET.get(...)`), which trips an internal assertion in
mypy 2.1.0 (`check_multi_assignment_from_tuple`). A crash does not just skip that
line — it aborts analysis of everything downstream.

Measured both ways to be sure the fix was an unmasking, not damage:

| | errors | files with errors | crashes |
| --- | ---: | ---: | ---: |
| crashing `user.py` | 541 | 86 | 1 |
| fixed `user.py` | 952 | 145 | 0 |

So **~59 files were never being type-checked at all**, including the most
important repository in the codebase. Indexed access replaces the unpack; the
comment in the file records why.

### mypy config now reflects real debt

- generated `agent_pb2*.py` excluded (protoc output, 86 errors, not ours);
- test modules relaxed (`disallow_untyped_defs` off, `check_untyped_defs` on) —
  test bodies are assertions, not API surface, and full strictness buried the
  production findings under untyped fixtures;
- `ignore_missing_imports` for `grpc.*`, `josepy.*` (no stubs published).

**Production-code errors: 256**, down from an unmeasurable number (the crash made
the real total unknowable). Worst: `agent/grpc/servicer.py` 39,
`api/v1/outbound_import.py` 18, `agent/service.py` 17, `traffic/repository.py` 15.

### `tuple_()` keyset typing, fixed consistently

Five keyset repositories (`user`, `profile`, `node`, `client_assignment`,
`agent/sync`) pass plain values to SQLAlchemy's `tuple_()`. SQLAlchemy coerces
them to bind params at runtime, but its stubs only declare column expressions.
Each site now carries a scoped `# type: ignore[arg-type]` with the reason rather
than a code contortion. `tuple_` mypy errors: **9 to 0**.

### Tests for the two riskiest untested paths

**`app/tests/test_leader.py` (10 tests) — `core/leader.py` 29% to 92%.**
Leader election is what stops every replica running the background jobs at once;
a silent failure double-counts traffic rollups. Now pinned: acquire on free key,
second elector blocked while held, self-renew via Lua CAS, stand-down when the
key is stolen or expires, `stop()` releases the key (and a successor can take
over), `stop()` does *not* release someone else's key, the run loop sets and
clears `is_leader`, a Redis outage drops leadership rather than leaving a stale
leader, and — the actual point — **a non-leader job does not run its body**.

This needed `fakeredis[lua]`: the stock fake answers `unknown command 'eval'`, so
the Lua CAS paths were untestable. Installed via `uv`; the tests exercise the
real scripts rather than a reimplementation.

**`app/tests/test_cert_renewal.py` (5 tests) — covers the concurrency change
from §14.** Every due certificate renews; each is paired with *its own* issued
material (the cross-pairing bug a careless `gather` would introduce); one
failure records `last_error` without blocking the others; issuance is actually
concurrent (peak in-flight > 1) and bounded by `_ACME_RENEW_CONCURRENCY`; nothing
due is a no-op.

### ESLint: was never running, now runs

`web/` declared `"lint": "next lint"` with `eslint` 9 + `eslint-config-next` 15
installed but **no config file**, so the script did nothing.

A first attempt with `.eslintrc.json` looked like it passed — it did not. ESLint 9
defaults to flat config and ignores `.eslintrc.*`, exiting **2** ("couldn't find
eslint.config.js"); the earlier "OK" was a shell echo after a piped command.
Replaced with `eslint.config.mjs` using `FlatCompat` (eslint-config-next still
ships legacy-shaped config), and `@eslint/eslintrc` added.

The script also moved from `next lint` to `eslint .` — `next lint` is deprecated
and removed in Next 16.

Real findings fixed:
- `console.tsx` — `useEffect` missing `qc`; the React Query client is
  render-stable, so listing it is safe and removes a genuine staleness warning.
- `sidebar.tsx` — `<img>` for the branding logo annotated with the reason
  (user-supplied URL; `next/image` would need arbitrary hosts whitelisted).

**`react/jsx-key` (43 errors) turned out to be false positives** and is disabled
with that reasoning written into the config: `WarpHead` and `WarpRow` take
`cols`/`cells` as `ReactNode[]` and attach `key={i}` themselves when mapping
them (`shared/warp-table.tsx:168,204`). The rule cannot follow JSX across a prop
boundary. Adding 43 keys at call sites would have been cargo-culting.

ESLint now exits **0** (14 advisory warnings: `exhaustive-deps` hints about
`x || []` literals recreating per render, and `no-img-element` on dynamic URLs).

### Verification

```
pytest        791 passed, 8 skipped   (was 776)
coverage      77%   leader.py 29% -> 92%
mypy          0 internal crashes; 256 production-code errors
ruff          41 (unchanged; all style, in node-agent)
tsc           exit 0
eslint        exit 0
```

### Housekeeping

`.coverage` removed and gitignored (with `coverage.xml`, `htmlcov/`).
`web/package-lock.json` was auto-patched by `next lint` with optional
`@next/swc-darwin-x64` binaries; reverted, since it was unrelated to this work.

---

## 16. Fourth pass — the three highest-value gaps

### `outbound_import.py`: 0% → 96% coverage

The worst risk profile in the repo: a hand-written parser for operator-pasted
share links (`vless://`, `vmess://`, `trojan://`, `ss://`) and Xray config JSON,
with **197 statements, zero tests and 18 type errors**.

`app/tests/test_outbound_import.py` — 32 tests covering:

- **vless/trojan**: plain, REALITY (`pbk`/`sid`/`sni`/`fp`), gRPC `serviceName`,
  ws `path` URL-decoding, IPv6 bracket hosts, percent-encoded credentials,
  `tcp` correctly *not* emitted as a network, unknown `security` dropped.
- **vmess**: base64 JSON body, ws+tls, **unpadded base64** (real share links strip
  `=`), non-JSON body rejected, missing `id` rejected.
- **shadowsocks** — the format with two encodings in the wild: fully-base64 body,
  base64 userinfo only, plain userinfo, passwords containing `:`, `#fragment`
  stripping, missing method separator rejected.
- **Xray JSON**: built-in outbounds (`freedom`/`blackhole`/`dns`) skipped, bare
  outbound objects, shadowsocks server entries, configs with only built-ins,
  vless without a user id.
- **Malformed input must return `None`, never raise**: empty, whitespace, unknown
  scheme, broken JSON, top-level array, missing host/port, `vmess://` with no
  body, `ss://@@@`, non-numeric port, case-insensitive schemes, and a 500 KB paste.

That last one matters because `OutboundImportRequest.text` has `min_length=1` and
**no maximum** — the parser has to stay well-behaved on an arbitrarily large paste.

Worth recording for severity: `POST /routing/outbounds/import` is `SudoAdminUser`
gated and its result is returned for review rather than passed to
`_validate_outbound`, so a bad parse is a correctness bug, not an injection path.

### `user_bulk_service.py`: 19% → 99% coverage

Lines 29-100 — the entire action loop that mutates **up to 1000 users per call** —
had no coverage at all.

`app/tests/test_user_bulk.py` — 13 tests. Beyond the happy paths for all eight
actions, the two that encode the design:

- **one missing user does not stop the others** → `{ok: 2, failed: 1}`, proving the
  per-user savepoint actually isolates failures;
- **an out-of-scope user is skipped, not fatal** — a non-sudo admin bulk-disabling
  its own user plus someone else's gets `{ok: 1, failed: 1}` and the other admin's
  user is verifiably untouched.

Also pinned: soft-delete semantics (`removed` + `is_active` both set), unknown
actions failing every user rather than raising, upfront validation of a bad reset
strategy and of `extend_expiry` without `extend_days`, and an empty id list as a
no-op.

### `traffic/repository.py`: 15 type errors → 0

The heart of traffic accounting is now fully typed:

- five untyped helpers annotated (`_hour_bucket_expr`, `_as_hour_datetime`,
  `_weighted_totals_stmt` → `Select[Any]`, `_unified_usage_cte` and
  `_unified_usage_ts_cte` → `Subquery`);
- `Sequence[dict]` → `Sequence[dict[str, Any]]`;
- the three dialect-branch `stmt` variables annotated `Any` — the sqlite and
  postgres `Insert` types genuinely differ and mypy otherwise narrows to whichever
  branch it sees first;
- the three `result.rowcount` accesses carry a scoped ignore with the reason
  (`execute()` is typed as returning `Result`; it is a `CursorResult` at runtime).

No behaviour changed — these are annotations and two scoped ignores.

### Verification

```
pytest      836 passed, 8 skipped   (was 791)
coverage    78%
            outbound_import.py     0%  -> 96%
            user_bulk_service.py  19%  -> 99%
mypy        241 production-code errors (was 256); traffic/repository.py 15 -> 0
ruff        41 (unchanged)
```

### Not done, and why

`agent/grpc/servicer.py` (0%, 39 type errors), `lifespan.py` (28%) and the 26
node-agent ruff findings were left alone — agreed as lower value. The servicer is
thin gRPC plumbing over already-tested services, `lifespan.py` is wiring that the
integration tests exercise end-to-end, and the node-agent findings are all style
(`E501`, `UP031`).

---

## 17. Fifth pass — dead exports removed, images right-sized

### The 3 unused API client functions are gone

Re-verified as unreferenced immediately before deleting (0 non-definition call
sites each), then removed:

- `lib/api/subscription.ts` — `subscriptionFeed()`
- `lib/api/users.ts` — `updateUserTemplate()`, `promoteUser()`

Deleting `subscriptionFeed` orphaned the `query` import in `subscription.ts`
(0 remaining uses), so that came out too. `users.ts` was left intact —
`UserTemplateRead` (4 refs), `UserRead` (13 refs) and `query` are all still used
there.

`knip` now reports only the i18n re-export false positives
(`translate`/`getLocale`, which `index.ts` deliberately re-exports) and
`eslint-config-next`, which is a false positive of its own: the flat config
consumes it through `FlatCompat`, which knip cannot follow.

### Images: 2276 KB → 604 KB (73% smaller)

Every target was chosen from the **measured rendered size**, not a guess:

| File | Rendered at | Before | After | New dims |
| --- | --- | ---: | ---: | --- |
| `web/public/xlink-logo.png` | 22px, 26px, 128px | 792 KB | **24 KB** | 512×170 |
| `docs/assets/logo.png` | 420px (README) | 792 KB | **60 KB** | 1024×341 |
| `web/public/login.png` | aside, `max-width:84%` | 548 KB | **500 KB** | 1014×1200 |
| `warp/os/ubuntu.png` | 16×16 (`.warp-si-badge img`) | 112 KB | **12 KB** | 128×128 |
| `warp/os/debian.png` | 16×16 | 32 KB | **8 KB** | 128×72 |

Each keeps generous headroom (the logo is still 4× its largest use; the OS icons
8×), and alpha is preserved everywhere — verified with `sips -g hasAlpha`.

The two logos were previously **byte-identical duplicates** at 2172×724; they now
differ because their consumers need different sizes (README at 420px, the console
and subscription page at ≤128px).

**`login.png` was deliberately left nearly as-is.** Colour quantisation would have
taken it to 128 KB, but measuring the distortion honestly (after flattening the
33%-transparent layer, since the first PSNR reading was an alpha artifact) gave
~21 dB — and it barely improved from 256 to 512 colours, meaning the loss was not
colour-count driven. That is not a number worth shipping on a user-facing hero
image sight-unseen, so it got the plain resize only. Converting it to WebP would
save far more and is the right follow-up, but that changes the `<img src>` and is
a call for you to make.

Originals are backed up outside the repo for this session; `git` holds them
regardless.

### Verification

```
pytest    836 passed, 8 skipped
tsc       exit 0
eslint    exit 0 (14 advisory warnings)
knip      3 unused exports -> 0 real ones
images    web/public 1.8M -> 888K
```

---

## 18. Sixth pass — gRPC servicer, traffic scheduler, parser types

### A real bug found by writing the tests

`agent/grpc/servicer.py` had **four RPCs that never mapped `AuthenticationError`
to a gRPC status**: `ReportProviderHealth`, `ReportState`, `LeaseCommands`,
`SubmitCommandResult`. They passed the agent token down to the service layer but,
unlike `GetConfig` (which catches) and the streaming RPCs (which call `_auth`),
they let the exception escape raw — so an agent presenting a bad token got an
opaque `UNKNOWN` instead of `UNAUTHENTICATED`. The HTTP equivalents return a clean
401. All four now catch and abort with `UNAUTHENTICATED`, each guarded by a
regression test.

### `servicer.py`: 0% → 93% coverage, 39 → 0 type errors

`app/agent/tests/test_grpc_servicer.py` — 32 tests driving the servicer directly
through a fake `ServicerContext` (which raises on `abort`, as real gRPC does), so
no channel is needed. Covers every RPC: config pull with/without `known_version`,
traffic ingest and its cross-RPC batch idempotency, the **stream node_id pinning
rule** (a stream authenticates once, so a later batch must not smuggle in another
node's id), sample-level rejection of unparseable assignment ids, malformed
`applied_json` / `result_json` / `command_id`, command lease round-trip, and
`WatchEvents` cancellation.

The type story was a config bug of my own from §15: excluding `agent_pb2.py` from
mypy made every `pb.Message` reference a `name-defined` error in the modules that
*use* it. The real cause is that protoc's output builds message classes at runtime
(`AddSerializedFile`), so there is nothing static to read. Fixed properly by
generating `agent_pb2.pyi` with `protoc --pyi_out` (26 errors gone), swapping the
exclusion for an `ignore_errors` override, annotating the `context` parameters and
the four streaming return types, and declaring `node_channel` on `CacheProtocol` —
a genuine protocol gap, since `WatchEvents` calls it but only the concrete
`RedisCache` had it.

`grpcio-tools` is now a dev dependency, and the generated `.pyi` is checked in and
excluded from ruff.

### `traffic/scheduler.py`: 22% → 90%

12 tests. The work functions (retention purges only rows past the cutoff; rollup
is idempotent), and the loop contract that makes these safe on multiple replicas:
**a non-leader job does not run its body**, a leader does, `leader=None` still
works for single-replica deployments, `start()` is idempotent, `stop()` without
`start()` is safe, and **one failing pass is logged and retried rather than
killing the loop**.

### `outbound_import.py`: 18 type errors → 0

All eighteen were one root cause — an untyped `g = lambda k: ...` helper made
every call to it an untyped-call-in-typed-context. Replaced with a typed nested
`def`.

### `ruff --fix` silently stripped three deliberate suppressions

Twice in this session now. It removed `# noqa: S310` (audited `urlopen`) from
`monitoring.py` and both `# noqa: BLE001` from `xlink-agent.py`, because those
rules are not in `select` so it judged them "unused". They are deliberate
pre-suppressions: if S-rules are ever enabled, `S310` should already be marked as
reviewed rather than surfacing as a new finding.

All three restored, and `RUF100` is now in the ignore list so `--fix` cannot strip
them again.

### Verification

```
pytest    880 passed, 8 skipped   (was 836)
coverage  80%
          agent/grpc/servicer.py    0% -> 93%
          traffic/scheduler.py     22% -> 90%
          api/v1/outbound_import.py      96% (held)
mypy      184 production-code errors (was 241); 0 crashes
ruff      39
```

### Still outstanding

The two architectural items — splitting the worker/scheduler out of the API
process, and the 9-domain split-brain refactor. Both are multi-module structural
changes, not bounded fixes.
