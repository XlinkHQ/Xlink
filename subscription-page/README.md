# XLink standalone subscription page

A tiny, optional public-facing service that serves user subscription links
(`/sub/{token}`) **without exposing the panel's domain**. It forwards each
request to the panel's *internal* subscription endpoint over the private
network and streams the response back to the client — the same model as
Remnawave's separate subscription page.

With this in front, you can IP-restrict / firewall the panel API so only this
container can reach it, while subscription links keep resolving on a separate,
throwaway domain. If the sub-page domain gets blocked, you rotate it without
touching the panel.

It is **off by default** and additive: the panel still serves `/sub/{token}`
directly exactly as before.

## What it does

- Accepts `GET /sub/{token}` and `GET /sub/{token}/{format}` (e.g. `/clash`).
- Forwards to `PANEL_INTERNAL_URL` + `/api/v1/subscriptions/sub/{token}`.
- Passes the client's `User-Agent` and `x-hwid` through **unchanged** so the
  panel's client detection, feed-format selection, and HWID device-limit
  tracking all keep working.
- Appends the real client IP to `X-Forwarded-For` (chaining any existing value).
- Sets `X-Forwarded-Host` to the sub-page's **public** host and
  `X-Forwarded-Proto` accordingly, so the panel advertises subscription URLs on
  the sub-page domain (the `profile-web-page-url` header and the status-page
  `sub_url`) instead of its own domain.
- Returns the panel's status code, body, and headers (incl.
  `subscription-userinfo`, `profile-title`, `content-disposition`) verbatim.

## Enable it (docker compose)

```bash
# in .env
SUB_PAGE_PUBLIC_HOST=sub.example.com     # the sub-page domain
SUB_PAGE_PORT=8081                        # host port this service listens on
XLINK_FORWARDED_ALLOW_IPS=10.0.0.0/8      # let the panel trust the proxy (see below)

docker compose --profile subpage up -d --build
```

Then put your sub-page domain in front of port `8081` (a reverse proxy / TLS
edge such as Caddy or Cloudflare terminating HTTPS and forwarding to it). Point
`sub.example.com` at that edge.

Once running, every subscription link the panel generates for a user resolves
on `sub.example.com`, and you can lock the panel's own domain/API down to admin
IPs only.

## The one panel-side setting you must get right: real client IP

The panel's device-limit / HWID tracking and the advertised subscription-URL
host both rely on the request's proxy headers. Uvicorn only honours
`X-Forwarded-*` from proxies it trusts (`FORWARDED_ALLOW_IPS`, default
`127.0.0.1`). Because this service adds a hop, you must tell the panel to trust
it, or:

- **HWID clients** (Happ, v2rayN, …) still work — the HWID device fingerprint is
  IP-independent and `x-hwid` is passed through.
- **Non-HWID clients** would all collapse to this container's IP (the fallback
  `UA + IP` fingerprint), breaking per-device counting, and the panel could
  advertise the wrong host.

Fix: set `XLINK_FORWARDED_ALLOW_IPS` to the sub-page container's network (the
compose bridge CIDR, or `*` if the panel is otherwise firewalled to only this
service). The compose file plumbs it into the panel's `FORWARDED_ALLOW_IPS`.
This is config only — no panel code changes.

## Configuration (env)

| Variable                 | Default            | Purpose                                                        |
| ------------------------ | ------------------ | -------------------------------------------------------------- |
| `PANEL_INTERNAL_URL`     | `http://api:8000`  | Internal panel API base (private network).                     |
| `PANEL_API_V1_PREFIX`    | `/api/v1`          | Panel API prefix (match `XLINK_API_V1_PREFIX`).                |
| `SUB_PAGE_PUBLIC_HOST`   | *(incoming Host)*  | Public sub-page host advertised to the panel.                  |
| `SUB_PAGE_PUBLIC_PROTO`  | `https`            | Public scheme advertised to the panel.                         |
| `PANEL_API_TOKEN`        | *(none)*           | Optional shared secret sent as `X-Sub-Page-Token`.             |
| `SUB_PAGE_TIMEOUT`       | `30`               | Upstream request timeout (seconds).                            |

`PANEL_API_TOKEN` is **not required** by the panel today — the signed URL token
already authenticates each request. It is here so an operator can later add a
panel-side allow rule (e.g. reject direct public hits that lack the header)
without changing this service.

## Run standalone (no compose)

```bash
pip install -r requirements.txt
PANEL_INTERNAL_URL=http://panel-host:8000 SUB_PAGE_PUBLIC_HOST=sub.example.com \
  uvicorn app:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips '*'
```
