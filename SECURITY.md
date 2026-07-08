# Security Policy

XLink sits in front of VPN infrastructure and holds user credentials and
subscription tokens, so a bug in the wrong place has real consequences. Security
reports get handled ahead of everything else — if you've found something, thank
you for taking the time to tell us.

## Which versions get fixes

Fixes land on the latest release on `main`. Older tags aren't backported, so the
answer to "is my version patched" is really "am I on the latest version" —
upgrade if you're behind.

| Version | Supported |
| ------- | --------- |
| `1.x` (latest `main`) | ✅ |
| < `1.0` | ❌ |

## Reporting something

Please **don't open a public issue for a security problem** — that tells everyone
about the hole before there's a fix. Instead, use GitHub's
[private vulnerability reporting](https://github.com/Theok09/Xlink/security/advisories/new)
("Report a vulnerability" on the repo's **Security** tab). It stays private
between us until a fix is out.

The report is most useful if it says:

- which part is affected — the panel API, the web console, the node agent, the
  subscription/token layer, or the deploy scripts — and the version or commit;
- what the issue is and what someone could actually do with it;
- how to reproduce it, ideally with a minimal proof of concept.

## What happens next

You'll hear back within a few days. If it's a real issue, it gets assessed and
fixed on `main` as soon as we reasonably can, and you'll be credited in the
release notes if you want — just tell us how you'd like to be named.

## What counts

The things worth reporting are the ones that break a security boundary:
authentication or authorization bypasses, forging or replaying a subscription
token, a reseller-admin escaping their scope, injection, remote code execution,
leaking secrets, and getting around a quota or expiry.

What isn't in scope: anything that already assumes an attacker has root or a shell
on the panel or a node (at that point it's game over regardless), denial of
service from unrealistic traffic volumes, and bugs in third-party dependencies —
those should go to the upstream project.
