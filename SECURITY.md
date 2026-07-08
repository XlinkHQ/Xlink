# Security Policy

XLink manages VPN infrastructure and user credentials, so security reports are
taken seriously and handled with priority.

## Supported versions

Security fixes are applied to the latest release on the `main` branch. Older
tagged releases are not backported — upgrade to the latest version.

| Version | Supported |
| ------- | --------- |
| `1.x` (latest `main`) | ✅ |
| < `1.0` | ❌ |

## Reporting a vulnerability

**Do not open a public issue for a security vulnerability.**

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/Theok09/Xlink/security/advisories/new)
("Report a vulnerability" on the repository's **Security** tab). This keeps the
details confidential until a fix is released.

Please include:

- the affected component (panel API, web console, node agent, subscription/token
  layer, deploy scripts) and version / commit,
- a description of the issue and its impact,
- steps to reproduce, ideally a minimal proof of concept.

## What to expect

- Acknowledgement of your report within a few days.
- An assessment and, for confirmed issues, a fix on `main` as soon as practical.
- Credit in the release notes if you'd like it (tell us how to attribute you).

## Scope

In scope: authentication/authorization bypasses, subscription-token forgery or
replay, RBAC scope escapes, injection, remote code execution, secret exposure,
and quota/expiry bypasses.

Out of scope: findings that require a compromised host or root on the panel/node,
denial of service from unrealistic traffic volumes, and issues in third-party
dependencies (report those upstream).
