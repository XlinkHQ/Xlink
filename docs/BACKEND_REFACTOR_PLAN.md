# Backend Refactor Plan — XLink `app/`

> **Status: PLAN ONLY. No backend code has been changed.** This document describes
> how the FastAPI backend should be reorganized later, mirroring the feature-based
> restructure just done on the web frontend. Nothing here is executed until
> explicitly approved.

## Goal

Make the backend fully **feature-based (vertical slices)**, the same principle
applied to `web/features/*`: every domain owns its models, repository, service,
schemas, and router in one package. No behavior, API, route, or schema change —
this is a **move + import-rewrite** refactor, exactly like the frontend.

## Current state (the "split-brain")

`app/` already has **two coexisting styles**:

**Already clean vertical slices** (models + repo + service + schemas colocated):
`agent/`, `traffic/`, `subscription/`, `failover/`, `gitops/`, `backup/`,
`monitoring/`, `scheduler/`, `providers/`, `events/`, `webhooks/`,
`notifications/`.

**Still scattered across root-level technical-layer folders** — these ~9 domains
live in 5 different places each:
- `app/domain/<x>.py` (ORM model)
- `app/repositories/<x>.py` (data access)
- `app/services/<x>_service.py` (business logic)
- `app/schemas/<x>.py` (Pydantic DTOs)
- `app/api/v1/routers/<x>.py` (HTTP)

The scattered domains: **user, node, profile, client_assignment, group,
certificate, inbound_host, auth, settings** (+ `app_settings`, `routing_rule`,
`outbound`, `api_key`, `audit_log`, `user_template`, `user_device` as related
tables).

A reader cannot predict where a domain lives — half are slices, half are layers.

## Target structure

Fold each scattered domain into its own slice, matching the existing ones:

```
app/
  user/
    __init__.py
    models.py          (from domain/user.py, user_device.py, user_template.py)
    repository.py       (from repositories/user.py)
    service.py          (from services/user_service*.py — already split into 6 this session)
    admin_service.py    (already exists as services/admin_service.py)
    schemas.py          (from schemas/user.py, user_template.py)
    controller.py       (from api/v1/routers/users.py, user_templates.py)
    errors.py           (user-specific typed errors, if any)
  node/                 (node.py + node_service + repositories/node + schemas/node + routers/nodes)
  profile/              (profile + inbound_host folded in, since hosts belong to profiles)
  client_assignment/
  group/
  certificate/          (+ acme_issuer.py, cert_renewal.py already in services/)
  auth/                 (auth_service, token_service, security bits stay in core/, routers/auth)
  settings/             (app_settings model + settings_service + routers/settings + WARP/branding)
  routing/              (routing_rule + outbound models + routers/routing)

  core/                 (unchanged — genuinely cross-cutting: config, security, authz,
                         exceptions, logging, leader, jobs, cache, pagination, totp)
  db/                   (unchanged — engine/session/redis/base)
  dependencies/         (see "DI" below — needs care)
  middleware/           (unchanged)
  api/v1/router.py      (thin aggregator: imports each slice's controller and includes it)
```

After the fold, `app/domain/`, `app/repositories/`, `app/services/`,
`app/schemas/`, and `app/api/v1/routers/` cease to exist as generic layer
buckets — only `app/api/v1/router.py` remains as the aggregator.

## Migration order (one slice per PR, tests green each)

Do the **leaf domains first** (fewest inbound imports), the **hub domains last**
(user/auth/settings are imported everywhere):

1. `routing` (routing_rule + outbound) — small, self-contained.
2. `certificate` — self-contained (+ its acme/renewal services already isolated).
3. `group`
4. `inbound_host` → fold into `profile`
5. `profile`
6. `client_assignment`
7. `node`
8. `settings`
9. `auth`
10. `user` (biggest; already partially prepared — UserService split into 6 files
    this session, which makes the fold easier).

Each step: `git mv` the 5 files into the slice, rewrite imports repo-wide, run
the **full test suite** (must stay green — currently ~780 tests), commit. Same
discipline as the frontend feature moves.

## Blockers to resolve FIRST (from the discovery audit)

These structural hazards must be handled before/at the fold, or the move will
surface latent cycles:

1. **`app/dependencies/services.py` is a god-module (~334 lines)** importing nearly
   every service/repo, and forward-references `SubscriptionServiceDep` before its
   definition (works only via `from __future__ import annotations`). When domains
   become slices, split this into per-slice `dependencies.py` (each slice exposes
   its own `XServiceDep`), leaving `dependencies/core.py` for the shared
   `get_session`/`get_state`.

2. **Latent `core.lifespan` ↔ `dependencies.core` cycle.** `dependencies/core.py`
   imports `AppState` from `core/lifespan.py`, which imports services. Today it
   only works because `lifespan` uses lazy in-function imports. Moving services
   into slices can tighten this — extract `AppState` into its own module
   (`app/core/app_state.py`) that neither imports services nor is imported by
   them, breaking the cycle cleanly before the fold.

3. **`DispatcherDep = Annotated[object, ...]`** (dependencies/core.py) — typed as
   `object` to dodge importing `WebhookDispatcher`. Once webhooks is a proper slice
   with a stable public type, restore the real type.

4. **Duplicated config-building** between `app/agent/config_sync.py` (panel) and
   `node-agent/xlink-agent.py` (standalone agent). This is NOT fixed by the fold —
   it is a separate concern. A protocol-config shared spec (or codegen) would
   remove the hand-sync risk; a mirror test already guards the protocol LIST but
   not the builders. Track separately.

## Non-goals / keep unchanged

- **No route changes** — `api/v1/router.py` keeps the same prefixes/paths; only
  where controllers are imported FROM changes.
- **No schema/DTO changes** — Pydantic models move, their fields do not.
- **No behavior change** — services move verbatim; the UserService split already
  done this session is the template (pure structural, tests green).
- `core/`, `db/`, `middleware/` stay as cross-cutting infrastructure — they are
  legitimately shared, not domains.

## Effort / risk

- **Effort:** ~10 slice-folds × (move 5 files + repo-wide import rewrite + test
  run). Large but mechanical.
- **Risk:** medium. The test suite (~780) is the safety net; the import cycles
  (blockers 1–2) are the only real trap and must be defused first. Every step is
  independently revertable (one commit per slice).
- **Recommendation:** do blockers 1–2 (extract `AppState`, split the DI
  god-module) as their own PRs FIRST, then fold leaf→hub. Do NOT start the fold
  until those two are green, or the moves will fight the cycles.
