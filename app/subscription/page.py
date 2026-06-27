from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from urllib.parse import quote

import segno

from app.subscription.formats.base import format_bytes

_IC_COPY = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
_IC_QR = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3M21 21v.01M17 21h.01M21 17h.01"/></svg>'
_IC_DOWN = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>'

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
    configs_html = "".join(
        f'<div class="x-config"><code>{e(c)}</code>'
        f"<button onclick=\"navigator.clipboard.writeText('{e(c)}')\">Copy</button></div>"
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
        days_left = f"{max(0, delta // 86400)}d" if delta > 0 else "Expired"
    s_fg, s_bg = _TONES.get(status_tone, _TONES["ok"])
    e = html.escape
    remaining = _human(total - used) if total else "∞"
    total_label = _human(total) if total else "∞"
    if pct < 75:
        grad = "linear-gradient(90deg,#5fc983,#36b37e)"
    elif pct < 90:
        grad = "linear-gradient(90deg,#ffc53d,#fa8c16)"
    else:
        grad = "linear-gradient(90deg,#ff7875,#ff4d4f)"

    if total:
        usage_block = (
            f'<div class="uhead"><span class="ubig">{_bytes(used)}'
            f'<span class="muted"> / {total_label}</span></span>'
            f'<span class="upct">{pct}%</span></div>'
            f'<div class="ubar"><i style="width:{pct}%;background:{grad}"></i></div>'
            f'<div class="ufoot"><span>{remaining} remaining</span></div>'
        )
    else:
        usage_block = (
            f'<div class="uhead"><span class="ubig">{_bytes(used)}'
            '<span class="muted"> used</span></span>'
            '<span class="ulim">∞ Unlimited</span></div>'
        )

    info_rows = "".join(
        f'<div class="ir"><span class="ik">{k}</span><span class="iv">{v}</span></div>'
        for k, v in (
            ("Upload", _bytes(upload)),
            ("Download", _bytes(download)),
            ("Expire", e(days_left)),
        )
    )

    server_rows = ""
    for i, c in enumerate(configs):
        is_wg = "[Interface]" in c
        proto = "wg" if is_wg else (c.split("://")[0] if "://" in c else "cfg")
        label = _config_label(c, proto, i, is_wg)
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
            f'<span class="rtitle">{e(label)}</span>'
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
    empty_html = (
        f'<div class="empty"><span class="badge">{e(status)}</span>'
        f'<p>{e(empty_msg)}</p></div>'
    )
    configs_block = server_rows or empty_html
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{e(title)}</title>
<style>
:root{{
  color-scheme:light;
  --bg:#e6e8ec; --surface:#ffffff; --line:rgba(0,0,0,0.08); --soft:rgba(0,0,0,0.03);
  --fg:#1c1c1c; --muted:#8a8f99;
  --accent:#5472e4; --accent-soft:#eef1fd; --green:#33b074;
}}
*{{box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
body{{margin:0;min-height:100vh;background:var(--bg);color:var(--fg);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,system-ui,sans-serif;
display:flex;justify-content:center;padding:34px 14px 56px;-webkit-font-smoothing:antialiased}}
.card{{width:100%;max-width:420px;background:var(--surface);border:1px solid var(--line);
border-radius:22px;padding:26px 20px;box-shadow:0 8px 30px rgba(20,24,40,.06)}}
.head{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:7px;margin-bottom:22px}}
.head h1{{font-size:21px;font-weight:700;letter-spacing:-.02em;margin:0}}
.head .who{{font-size:12.5px;color:var(--muted);word-break:break-all}}
.badge{{display:inline-flex;align-items:center;gap:6px;flex:none;font-size:11.5px;font-weight:600;
padding:5px 13px;border-radius:999px;color:{s_fg};background:{s_bg};margin-top:2px}}
.badge::before{{content:"";width:6px;height:6px;border-radius:999px;background:{s_fg}}}
.muted{{color:var(--muted)}}
.uhead{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}}
.ubig{{font-size:18px;font-weight:700;letter-spacing:-.01em}}
.ubig .muted{{font-size:14px;font-weight:500}}
.upct{{font-size:14px;font-weight:700;color:var(--muted)}}
.ulim{{font-size:12px;font-weight:600;color:#36b37e;background:rgba(54,179,126,.12);padding:4px 11px;border-radius:999px}}
.ubar{{height:9px;border-radius:999px;background:var(--soft);overflow:hidden}}
.ubar > i{{display:block;height:100%;border-radius:999px;transition:width .4s ease}}
.ufoot{{margin-top:9px;font-size:12.5px;color:var(--muted);text-align:center}}
.itable{{margin-top:14px;background:var(--soft);border-radius:14px;padding:4px 14px}}
.ir{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}}
.ir:last-child{{border-bottom:0}}
.ik{{font-size:13px;color:var(--muted)}}
.iv{{font-size:13.5px;font-weight:600}}
.lbl{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;margin:24px 2px 10px}}
button{{cursor:pointer;border:0;font-family:inherit;background:none}}
.row{{display:flex;align-items:center;gap:10px;background:var(--soft);border-radius:14px;padding:10px 12px;margin-bottom:8px}}
.rtag{{flex:none;font-size:11px;font-weight:600;letter-spacing:.3px;text-transform:uppercase;color:var(--accent);min-width:34px}}
.rtitle{{flex:1;min-width:0;font-size:13.5px;font-weight:600;color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ractions{{flex:none;display:flex;gap:5px}}
.act{{flex:none;width:34px;height:34px;border-radius:10px;color:var(--muted);font-size:15px;
display:inline-flex;align-items:center;justify-content:center;transition:.12s;
border:1px solid var(--line);background:#fff;text-decoration:none}}
.act:hover{{color:var(--accent);border-color:var(--accent)}}
.act:active{{transform:scale(.92)}}
.act.ok{{color:#fff;background:var(--green);border-color:var(--green)}}
.apps{{display:flex;gap:8px;margin-bottom:4px}}
.apps a{{flex:1;text-align:center;color:var(--accent);background:var(--accent-soft);
font-size:13px;font-weight:600;text-decoration:none;padding:11px 0;border-radius:12px}}
.apps a:active{{transform:scale(.97)}}
.support{{display:block;text-align:center;color:#fff;background:var(--accent);font-size:13px;
text-decoration:none;margin-top:22px;font-weight:600;padding:13px 0;border-radius:12px}}
.support:active{{transform:scale(.98)}}
.modal{{display:none;position:fixed;inset:0;background:rgba(20,20,25,.5);backdrop-filter:blur(4px);
align-items:center;justify-content:center;padding:20px;z-index:9}}
.modal.show{{display:flex}}
.modal .box{{background:#fff;border-radius:18px;padding:16px;box-shadow:0 20px 50px rgba(0,0,0,.25);line-height:0}}
.modal img{{display:block;width:240px;height:240px;border-radius:8px}}
.empty{{display:flex;flex-direction:column;align-items:center;gap:14px;padding:28px 8px;text-align:center}}
.empty p{{margin:0;font-size:14px;color:var(--muted);line-height:1.6}}
</style></head><body><div class="card">
<div class="head"><h1>{e(title)}</h1><div class="who">{e(username)}</div><span class="badge">{e(status)}</span></div>
{usage_block if configs else ""}
{f'<div class="itable">{info_rows}</div>' if configs else ""}
{f'<p class="lbl">Configs · {len(configs)}</p>' if configs else ""}
{configs_block}
{support_html}
</div>
<div class="modal" id="m" onclick="this.classList.remove('show')"><div class="box"><img id="mi" alt="QR"></div></div>
<script>
function cp(b,v){{navigator.clipboard&&navigator.clipboard.writeText(v);
b.classList.add('ok');setTimeout(function(){{b.classList.remove('ok')}},1100)}}
function qr(src){{document.getElementById('mi').src=src;document.getElementById('m').classList.add('show')}}
</script></body></html>"""
