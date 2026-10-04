# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] - 2026-10-04

### Added

- **Admin roles (RBAC)**: per-action scopes (none / own users / all users) and
  grant limits (max users, data-limit range, max expiry) for non-sudo admins,
  with a Roles screen and a role picker in the admin dialog.
- **Client templates**: editable base documents for Clash, Mihomo and sing-box;
  generated servers are injected and `{ALL}` expands in groups and selectors.
- **First-run setup wizard**, gated by a one-time token written to the log.
- **REALITY target scanner** (TLS 1.3, h2, X25519, certificate, latency), run
  from the panel or from the node itself.
- **AmneziaWG** (anti-DPI WireGuard) and **MTProto** (Telegram, fake-TLS,
  per-user secrets) cores; opt-in via `xlink core-update amneziawg|mtproto`.
- **AnyTLS** protocol.
- **Per-ISP clean CDN addresses**: inbound hosts map ASNs to addresses, chosen
  per subscriber from a local iptoasn.com dataset (`/asn/*`).
- **Durable job queue** (Redis Streams, dead-letter, retry) and an
  `api` / `worker` process split; multi-panel HA with leader fencing.
- Raw inbound / client-outbound passthrough with deep, case-insensitive
  protection of managed keys.


- Optional PostgreSQL **read replica**: when a replica host is configured, heavy
  lag-tolerant reads (traffic analytics and subscription source listings) are
  routed to it, while writes, enforcement, and auth stay on the primary; a
  replica outage transparently falls back to the primary.
- Opt-in **Prometheus `/metrics`** endpoint (off unless `XLINK_METRICS_TOKEN` is
  set; bearer-authenticated, constant-time compare). Exposes process, HTTP
  request-count/latency, and domain gauges refreshed by a background collector so
  scrapes never trigger database queries.
- Hourly **traffic rollups** (`traffic_hourly` with a watermark): analytics read
  closed-hour rollups unioned with the current raw hour, keeping queries fast as
  data grows; raw records drop after 7 days, rollups keep the 90-day horizon.
- Per-node agent **ingest quota** (Redis fixed-window, fail-open on a Redis
  outage) that authenticates the node token before counting.
- Installer prompts for a **choosable web UI port** (default `3000`) and an
  optional **secret panel path** (`XLINK_WEB_PATH`) that serves the whole panel
  under an unguessable prefix.
- `docs/ARCHITECTURE.md` — system, auth, layering, agent-cycle, subscription and
  data-model diagrams (GitHub-native Mermaid).
- Official Python SDK under `sdk/python/` (`xlink-sdk`): an API-key client for the
  common user / subscription / usage / node workflows.
- Optional standalone **subscription page** service (`subscription-page/`, compose
  profile `subpage`, off by default) that serves `/sub/{token}` on its own domain
  so the panel API can be locked down without breaking subscription links.

### Fixed

- Shadowsocks 2022 multi-user: server PSK, `server:user` client keys and
  correct key lengths (migration 0054 backfills existing profiles).
- REALITY key-pair and shortId validation; sing-box feeds no longer drop nodes
  with an empty shortId. TUIC congestion control, ALPN, stable ShadowTLS detour
  ports, one Hysteria obfs password per node.
- sing-box `geosite:` / `geoip:` rules now map to remote rule-sets instead of
  being dropped.
- TOTP codes cannot be replayed; backup import is capped against gzip bombs;
  explicit `null` can no longer lift users past role limits.
- Node and inbound-host changes invalidate cached subscriptions.
- Dashboard CPU shows real utilisation and a host-wide process count.
- Dependency security updates (pyjwt, anyio, cryptography, urllib3, next).



- **Security (subscription feed)** — a single malformed numeric profile setting
  no longer 500s the entire feed, including the public `/sub/{token}` endpoint;
  the bad config is skipped per-item instead of failing the whole render (fixes a
  persistent denial-of-service vector).
- **Failover** — a user with a historical assignment on the only viable target
  node is no longer stranded (the stale row is cleared before re-insert), and
  both nodes' user counts are recomputed from the live count; the auto-failover
  cooldown map now prunes expired entries.
- **Security (webhooks)** — the dispatcher no longer sends the raw secret as a
  header (which defeated the HMAC signature); GitOps audit redaction covers more
  secret key names.
- Database backup downloads are gzipped (SQL compresses ~5–10×), so the download
  is fast; import transparently accepts both `.sql.gz` and older plain `.sql`.

### Changed

- Gunicorn workers auto-size to the host CPUs, capped by the database connection
  budget (was a fixed 4).
- Protocol definitions and the protocol×format capability matrix now come from a
  single source of truth instead of allow-sets duplicated across renderers;
  format-incompatible protocols are logged once per feed rather than dropped
  silently.

## [1.1.0] - 2026-07-08

### Added

- Automatic detection of the server's real public IP for the dashboard: when the
  local egress address is private (the Docker case) the panel resolves the real
  public IP externally, with optional `XLINK_PUBLIC_IP` / `XLINK_PUBLIC_MAC`
  overrides; the installer also writes the detected IP into `.env`.
- Plaintext SOCKS5 inbound support (sing-box).
- Community & docs: `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, GitHub
  issue/PR templates, and a full HTTP API reference (`docs/API.md`).

### Fixed

- **Node agent** — corrected per-protocol auth mapping so hysteria, naive, SOCKS,
  shadowtls, tuic and wireguard clients authenticate and are counted correctly;
  keyed hysteria/traffic stats by assignment id; WireGuard restarts no longer
  re-count an interface's whole lifetime; capped the traffic WAL below the panel's
  batch limit; drop non-UUID samples so one bad row can't reject a whole batch.
- **Subscriptions** — shadowtls now renders in sing-box/clash feeds instead of
  being silently dropped; an admin/panel preview no longer consumes a
  START_ON_FIRST_USE user's expiry window.
- **Quotas & admin state** — a reseller at their user cap can now set a data limit
  on an existing unlimited user; suspending then restoring an owner no longer
  clobbers users an admin disabled individually; profile disable→enable restores
  the affected assignments; bulk quota/expiry edits invalidate the feed cache.
- **Security** — closed a device-limit bypass via a forged browser user-agent on
  the subscription status page.
- **Web console** — metrics screen reads the correct endpoint; token refresh now
  covers CSV/backup downloads and survives a network blip without logging out;
  full pagination for group membership/counts; soft-deleted users can be shown
  and restored; detail views have working back/edit controls; usage/metrics
  charts are theme-aware (were invisible grid lines + a white tooltip on dark);
  branding preview stays legible in dark mode; the bulk-action bar fits one row
  without overflowing; several date and form-reset fixes.

### Changed

- Removed the redundant `deploy.sh` wrapper; `xlink.sh` is the single install /
  update entrypoint (with `scripts/install.sh` as the curl bootstrap).
- Relicensed to Apache-2.0 (patent grant, trademark clause, `NOTICE`).

## [1.0.0] - 2026-07

Initial release.

### Added

- Multi-node VPN management panel: FastAPI + PostgreSQL + Redis backend, Next.js
  admin console, and a pull-based node agent.
- Cores: **xray, sing-box, hysteria, wireguard** (vless / vmess / trojan /
  shadowsocks / shadowtls / hysteria2 / tuic / naive / socks / wireguard).
- Per-user data, expiry, on-hold and device limits; HMAC subscription tokens with
  per-user scope and revocation.
- Multi-node load-balancing and failover, traffic accounting, and database
  backups.
- Role-based access control with sudo admins and scoped reseller-admins.
- One-command installer and containerized deployment.

[Unreleased]: https://github.com/XlinkHQ/Xlink/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/XlinkHQ/Xlink/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/XlinkHQ/Xlink/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/XlinkHQ/Xlink/releases/tag/v1.0.0
