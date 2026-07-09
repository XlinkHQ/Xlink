# Security Policy

## Reporting a Vulnerability

XLink manages VPN infrastructure, user credentials, and subscription tokens, so
security reports are handled with priority. If you believe you have found a
security issue, please disclose it responsibly by opening a private
[GitHub Security Advisory](https://github.com/XlinkHQ/Xlink/security/advisories/new).

Please do not report vulnerabilities through public GitHub issues, discussions,
or pull requests, and do not include live secrets, tokens, or personal data in
your report.

A good report identifies the affected component (panel API, web console, node
agent, subscription/token layer, or deploy scripts), the version or commit, the
impact, and steps to reproduce.

## Supported Versions

Fixes are applied to the latest release on `main`. Older tags are not
backported — upgrade to the current version.

| Version | Supported |
| ------- | --------- |
| `1.x` (latest `main`) | ✅ |
| `< 1.0` | ❌ |

## What to Expect

You will receive an acknowledgement within a few days. Confirmed issues are
assessed and fixed on `main` as soon as practical, and you will be credited in
the release notes if you wish.
