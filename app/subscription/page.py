from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from urllib.parse import quote

import segno

from app.subscription.formats.base import format_bytes

_IA = 'viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"'
_IC_COPY = f'<svg {_IA}><rect x="7.5" y="7.5" width="9.5" height="9.5" rx="2"/><path d="M13 7.5V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2.5"/></svg>'
_IC_QR = f'<svg {_IA}><rect x="3" y="3" width="5.5" height="5.5" rx="1"/><rect x="11.5" y="3" width="5.5" height="5.5" rx="1"/><rect x="3" y="11.5" width="5.5" height="5.5" rx="1"/><path d="M11.5 11.5h2.5v2.5M17 11.5v.01M14 17h3v-3M11.5 17h.01"/></svg>'
_IC_DOWN = f'<svg {_IA}><path d="M10 3v9M6.2 8.2 10 12l3.8-3.8M4 15.5h12"/></svg>'

_R = 'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"'
_IC_USER = f'<svg viewBox="0 0 20 20" {_R}><circle cx="10" cy="6.5" r="3"/><path d="M4 16.5c0-3.2 2.7-4.8 6-4.8s6 1.6 6 4.8"/></svg>'
_IC_USAGE = f'<svg viewBox="0 0 20 20" {_R}><circle cx="10" cy="10" r="7.3"/><path d="M10 5.6V10l2.8 1.7"/></svg>'
_IC_UP = f'<svg viewBox="0 0 20 20" {_R}><path d="M10 15.5V4.8M5.2 9.6 10 4.8l4.8 4.8"/></svg>'
_IC_DN = f'<svg viewBox="0 0 20 20" {_R}><path d="M10 4.5v10.7M14.8 10.4 10 15.2l-4.8-4.8"/></svg>'
_IC_CAL = f'<svg viewBox="0 0 20 20" {_R}><rect x="3.3" y="4.3" width="13.4" height="12.4" rx="2.2"/><path d="M13.3 2.8v3M6.7 2.8v3M3.3 8h13.4"/></svg>'
_IC_SUN = f'<svg viewBox="0 0 20 20" {_R}><circle cx="10" cy="10" r="3.3"/><path d="M10 2.3v1.6M10 16.1v1.6M3.6 3.6l1.1 1.1M15.3 15.3l1.1 1.1M2.3 10h1.6M16.1 10h1.6M3.6 16.4l1.1-1.1M15.3 4.7l1.1-1.1"/></svg>'
_IC_MOON = f'<svg viewBox="0 0 20 20" {_R}><path d="M17.5 10.6A7.5 7.5 0 1 1 9.4 2.5a5.8 5.8 0 0 0 8.1 8.1z"/></svg>'

_TONES = {
    "ok": ("#15803d", "#dcfce7"),
    "bad": ("#b91c1c", "#fee2e2"),
    "warn": ("#b45309", "#fef3c7"),
    "muted": ("#4b5563", "#f1f3f5"),
}


def _config_label(config: str, proto: str, index: int, is_wg: bool) -> str:
    from urllib.parse import unquote

    if not is_wg and "#" in config:
        tag = unquote(config.rsplit("#", 1)[-1]).strip()
        if tag and "://" not in tag:
            return tag
    if not is_wg and "://" in config:
        host = config.split("://", 1)[1].split("#", 1)[0].split("?", 1)[0]
        host = host.split("@", 1)[-1].split(":", 1)[0].strip()
        if host:
            return host
    return f"{proto.upper()} · {index + 1}"


def _human(num: int | None) -> str:
    if not num or num < 0:
        return "∞"
    return _bytes(num)


def _bytes(num: int | None) -> str:
    if not num or num < 0:
        return "0 B"
    return format_bytes(num, units=("B", "KB", "MB", "GB", "TB"), precision=2, sep=" ")


def _render_inactive_page(*, title: str, username: str, status: str, detail: str) -> str:
    e = html.escape
    sub = f'<p class="ip-date">{e(detail)}</p>' if detail else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{e(title)}</title>
<style>
:root{{--bg:#F7F8FA;--surface:#fff;--line:#DFE3E9;--fg:#191C23;--muted:#6B7280;--red:#CC3C3C}}
@media(prefers-color-scheme:dark){{:root{{--bg:#141517;--surface:#191A1C;--line:#2E3136;--fg:#E6E9EE;--muted:#8A929E}}}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px}}
.ip-card{{background:var(--surface);border:1px solid var(--line);border-radius:16px;
padding:40px 32px;max-width:360px;width:100%;text-align:center}}
.ip-badge{{width:56px;height:56px;border-radius:999px;margin:0 auto 20px;display:flex;
align-items:center;justify-content:center;background:color-mix(in srgb,var(--red) 12%,transparent);color:var(--red)}}
.ip-badge svg{{width:28px;height:28px}}
.ip-status{{font-size:20px;font-weight:600;letter-spacing:-.02em;margin:0 0 6px}}
.ip-user{{font-size:14px;color:var(--muted);margin:0}}
.ip-date{{font-size:13px;color:var(--muted);margin:16px 0 0;font-variant-numeric:tabular-nums}}
</style></head><body>
<div class="ip-card">
  <div class="ip-badge"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5M12 16h.01"/></svg></div>
  <p class="ip-status">{e(status)}</p>
  <p class="ip-user">{e(username)}</p>
  {sub}
</div>
</body></html>"""


def render_custom_page(
    template: str,
    *,
    title: str,
    username: str,
    status: str,
    used: int,
    total: int | None,
    expire_ts: int | None,
    sub_url: str,
    configs: list[str],
    support: str,
) -> str:
    e = html.escape
    days_left = "never"
    if expire_ts:
        delta = expire_ts - int(datetime.now(UTC).timestamp())
        days_left = f"{max(0, delta // 86400)} days" if delta > 0 else "expired"
    pct = min(100, round(used / total * 100)) if total else 0
    # Copy via an execCommand fallback too: navigator.clipboard is undefined on
    # plain-HTTP origins (non-secure context), which is the common panel setup,
    # so the bare writeText silently does nothing there.
    configs_html = "".join(
        f'<div class="x-config"><code>{e(c)}</code>'
        f"<button onclick=\"(function(v){{if(navigator.clipboard&&window.isSecureContext)"
        f"{{navigator.clipboard.writeText(v)}}else{{var t=document.createElement('textarea');"
        f"t.value=v;t.style.position='fixed';t.style.top='-9999px';document.body.appendChild(t);"
        f"t.select();try{{document.execCommand('copy')}}catch(e){{}}document.body.removeChild(t)}}}})"
        f'({e(json.dumps(c))})">Copy</button></div>'
        for c in configs
    )
    configs_lines = "\n".join(configs)
    repl = {
        "title": e(title),
        "username": e(username),
        "status": e(status),
        "used": _bytes(used),
        "total": _human(total),
        "percent": str(pct),
        "expire": e(days_left),
        "sub_url": e(sub_url),
        "support": e(support),
        "count": str(len(configs)),
        "configs": configs_html,
        "configs_raw": e(configs_lines),
    }
    return re.sub(
        r"\{\{(\w+)\}\}",
        lambda m: repl.get(m.group(1), m.group(0)),
        template,
    )


def render_subscription_page(
    *,
    title: str,
    username: str,
    status: str,
    status_tone: str = "ok",
    used: int,
    total: int | None,
    expire_ts: int | None,
    sub_url: str,
    configs: list[str],
    support: str,
    upload: int = 0,
    download: int = 0,
) -> str:
    pct = min(100, round(used / total * 100)) if total else 0
    days_left = "Never"
    if expire_ts:
        delta = expire_ts - int(datetime.now(UTC).timestamp())
        days_left = f"{max(0, delta // 86400)} days" if delta > 0 else "Expired"
    e = html.escape

    if status_tone in ("bad", "muted", "warn"):
        detail = ""
        if expire_ts:
            detail = datetime.fromtimestamp(expire_ts, UTC).strftime("%Y-%m-%d")
        return _render_inactive_page(
            title=title, username=username, status=status, detail=detail
        )

    if total:
        if pct < 75:
            bar_color = "#038026"
        elif pct < 90:
            bar_color = "#FF9500"
        else:
            bar_color = "#CC3C3C"
        usage_value = (
            f'<span class="uval">{_bytes(used)} <span class="muted">/ {_human(total)}</span></span>'
            f'<span class="ubar"><i style="width:{pct}%;background:{bar_color}"></i></span>'
        )
    else:
        usage_value = f"{_bytes(used)} <span class=\"muted\">used · unlimited</span>"

    _rows = [
        (_IC_USER, "User", e(username)),
        (_IC_USAGE, "Usage", usage_value),
        (_IC_UP, "Upload", _bytes(upload)),
        (_IC_DN, "Download", _bytes(download)),
        (_IC_CAL, "Expire", e(days_left)),
    ]
    info_rows = "".join(
        f'<div class="irow"><span class="ik">{icon}{k}</span><span class="iv">{v}</span></div>'
        for icon, k, v in _rows
    )

    server_rows = ""
    for i, c in enumerate(configs):
        is_wg = "[Interface]" in c
        proto = "wg" if is_wg else (c.split("://")[0] if "://" in c else "cfg")
        label = _config_label(c, proto, i, is_wg)
        # Show the friendly label (server name / host), never the raw URI — the
        # URI is kept only in the title tooltip and copy/QR/download actions.
        link_display = f"WireGuard config {i + 1}" if is_wg else label
        js_val = e(c.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n"))
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)[:32]
        conf_uri = "data:text/plain;charset=utf-8," + quote(c)
        fname = (safe_name or f"config-{i + 1}") + (".conf" if is_wg else ".txt")
        actions = (
            f'<button class="act" type="button" title="Copy" onclick="cp(this,\'{js_val}\')">{_IC_COPY}</button>'
        )
        try:
            q = segno.make(c, error="m" if len(c) < 800 else "l").svg_data_uri(
                scale=5, border=2, dark="#1c1c1c", light="#ffffff"
            )
            js_q = e(q.replace("\\", "\\\\").replace("'", "\\'"))
            actions += (
                f'<button class="act" type="button" title="QR" onclick="qr(\'{js_q}\')">{_IC_QR}</button>'
            )
        except Exception:
            pass
        actions += (
            f'<a class="act" title="Download" download="{e(fname)}" href="{conf_uri}">{_IC_DOWN}</a>'
        )
        server_rows += (
            '<div class="row">'
            f'<span class="rtag">{e(proto)}</span>'
            f'<span class="rlink" title="{e(c)}">{e(link_display)}</span>'
            f'<span class="ractions">{actions}</span>'
            "</div>"
        )

    support_html = (
        f'<a class="support" href="{e(support)}" target="_blank" rel="noopener">Contact support</a>'
        if support
        else ""
    )
    _empty_by_tone = {
        "bad": "This subscription is no longer active. Renew or contact support.",
        "warn": "This subscription is on hold.",
        "muted": "This subscription is disabled.",
    }
    empty_msg = _empty_by_tone.get(status_tone, "No configs yet.")
    empty_html = f'<div class="empty"><p>{e(empty_msg)}</p></div>'
    brand = e(title)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{brand}</title>
<style>
:root{{
  color-scheme:light dark;
  --bg:#F7F8FA; --surface:#ffffff; --line:#DFE3E9; --emphasis:#F0F2F5;
  --fg:#191C23; --muted:#6B7280; --subtle:#9CA3B4;
  --accent:#3961DB; --accent-soft:#EDF1FC;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]){{
    --bg:#141517; --surface:#191A1C; --line:#2E3136; --emphasis:#242629;
    --fg:#F4F5F6; --muted:#8B93A0; --subtle:#6B7280;
    --accent:#5777D9; --accent-soft:#1B2233;
  }}
}}
:root[data-theme="dark"]{{
  --bg:#141517; --surface:#191A1C; --line:#2E3136; --emphasis:#242629;
  --fg:#F4F5F6; --muted:#8B93A0; --subtle:#6B7280;
  --accent:#5777D9; --accent-soft:#1B2233;
}}
*{{box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
body{{margin:0;min-height:100vh;background:var(--bg);color:var(--fg);
font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;
-webkit-font-smoothing:antialiased;font-size:14px;line-height:1.5}}
.wrap{{max-width:640px;margin:0 auto;padding:0 20px 48px}}
.topbar{{display:flex;align-items:center;justify-content:space-between;height:64px;margin-bottom:12px}}
.theme-btn{{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;
border:0;background:none;color:var(--muted);cursor:pointer;transition:.12s}}
.theme-btn:hover{{color:var(--fg)}}
.theme-btn svg{{width:20px;height:20px}}
.theme-btn .moon{{display:none}}
:root[data-theme="dark"] .theme-btn .sun{{display:none}}
:root[data-theme="dark"] .theme-btn .moon{{display:block}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) .theme-btn .sun{{display:none}}
  :root:not([data-theme="light"]) .theme-btn .moon{{display:block}}
}}
.brand{{display:flex;align-items:center}}
.brand img{{height:26px;width:auto;display:block}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:6px 20px}}
.card + .card{{margin-top:14px}}
.chead{{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--subtle);padding:16px 0 10px}}
.muted{{color:var(--muted);font-weight:400}}
button{{cursor:pointer;border:0;font-family:inherit;background:none}}
.irow{{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 0;border-bottom:1px solid var(--line)}}
.irow:last-child{{border-bottom:0}}
.ik{{flex:none;display:flex;align-items:center;gap:10px;font-size:14px;color:var(--muted)}}
.ik svg{{width:17px;height:17px;color:var(--subtle);flex:none}}
.iv{{flex:1;min-width:0;text-align:right;font-size:14px;font-weight:500;color:var(--fg);display:flex;align-items:center;justify-content:flex-end;gap:10px}}
.uval{{flex:none;white-space:nowrap}}
.ubar{{flex:1;max-width:120px;height:6px;border-radius:999px;background:var(--emphasis);overflow:hidden}}
.ubar > i{{display:block;height:100%;border-radius:999px;transition:width .4s ease}}
.row{{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);padding:14px 0}}
.row:last-of-type{{border-bottom:0}}
.rtag{{flex:none;font-size:10.5px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;
color:var(--accent);background:var(--accent-soft);padding:3px 8px;border-radius:6px}}
.rlink{{flex:1;min-width:0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ractions{{flex:none;display:flex;gap:14px;align-items:center}}
.act{{flex:none;color:var(--subtle);display:inline-flex;align-items:center;justify-content:center;
transition:.12s;text-decoration:none;background:none;padding:0}}
.act:hover{{color:var(--accent)}}
.act:active{{transform:scale(.9)}}
.act.ok{{color:#038026}}
.act svg{{width:17px;height:17px;display:block}}
.support{{display:block;width:100%;text-align:center;color:var(--accent);font-size:14px;
text-decoration:none;font-weight:500;margin:32px auto 0}}
.support:hover{{text-decoration:underline}}
.modal{{display:none;position:fixed;inset:0;background:rgba(20,20,25,.5);backdrop-filter:blur(4px);
align-items:center;justify-content:center;padding:20px;z-index:9}}
.modal.show{{display:flex}}
.modal .box{{background:#fff;padding:12px;line-height:0}}
.modal img{{display:block;width:260px;height:260px}}
.empty{{padding:24px 4px;text-align:center}}
.empty p{{margin:12px 0 0;font-size:14px;color:var(--muted);line-height:1.6}}
</style></head><body>
<div class="wrap">
<div class="topbar">
<span class="brand"><img src="/xlink-logo.png" alt="XLink"></span>
<button class="theme-btn" type="button" onclick="tt()" aria-label="Toggle theme"><span class="sun">{_IC_SUN}</span><span class="moon">{_IC_MOON}</span></button>
</div>

<div class="card">
<div class="chead">Account</div>
{info_rows}
{f'<div class="chead">Configs · {len(configs)}</div>{server_rows}' if configs else empty_html}
</div>
{support_html}
</div>
<div class="modal" id="m" onclick="this.classList.remove('show')"><div class="box"><img id="mi" alt="QR"></div></div>
<script>
(function(){{var s=localStorage.getItem('xlink-sub-theme');if(s)document.documentElement.setAttribute('data-theme',s);}})();
function tt(){{var r=document.documentElement;var cur=r.getAttribute('data-theme');
var dark=cur?cur==='dark':matchMedia('(prefers-color-scheme:dark)').matches;
var next=dark?'light':'dark';r.setAttribute('data-theme',next);localStorage.setItem('xlink-sub-theme',next);}}
function cp(b,v){{var done=function(){{b.classList.add('ok');setTimeout(function(){{b.classList.remove('ok')}},1100)}};
if(navigator.clipboard&&window.isSecureContext){{navigator.clipboard.writeText(v).then(done,function(){{fb(v);done()}})}}
else{{fb(v);done()}}}}
function fb(v){{try{{var t=document.createElement('textarea');t.value=v;t.setAttribute('readonly','');
t.style.position='fixed';t.style.top='-9999px';document.body.appendChild(t);t.select();
document.execCommand('copy');document.body.removeChild(t)}}catch(e){{}}}}
function qr(src){{document.getElementById('mi').src=src;document.getElementById('m').classList.add('show')}}
</script></body></html>"""
