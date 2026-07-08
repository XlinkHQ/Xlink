# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `docs/ARCHITECTURE.md` — system, auth, layering, agent-cycle, subscription and
  data-model diagrams (GitHub-native Mermaid).
- Official Python SDK under `sdk/python/` (`xlink-sdk`): an API-key client for the
  common user / subscription / usage / node workflows.
- Optional standalone **subscription page** service (`subscription-page/`, compose
  profile `subpage`, off by default) that serves `/sub/{token}` on its own domain
  so the panel API can be locked down without breaking subscription links.

### Changed

- Gunicorn workers auto-size to the host CPUs, capped by the database connection
  budget (was a fixed 4).

### Fixed

- Database backup downloads are gzipped (SQL compresses ~5–10×), so the download
  is fast; import transparently accepts both `.sql.gz` and older plain `.sql`.

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

[Unreleased]: https://github.com/XlinkHQ/Xlink/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/XlinkHQ/Xlink/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/XlinkHQ/Xlink/releases/tag/v1.0.0
