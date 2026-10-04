"""Operator client templates applied to rendered subscription documents.

A template is a complete client config (YAML for Clash/Mihomo, JSON for
sing-box). The renderer keeps everything in it and injects the generated
servers:

* Clash / Mihomo: ``proxies`` is replaced by the generated list. In
  ``proxy-groups``, the token ``{ALL}`` inside a ``proxies`` list expands to
  every generated proxy name. Missing groups/rules fall back to a plain
  ``PROXY`` selector and ``MATCH,PROXY``.
* sing-box: generated outbounds are prepended to the template's own (direct,
  block, dns, selectors...). ``{ALL}`` inside a selector/urltest ``outbounds``
  list expands to every generated tag.

The active templates for a render are provided through a ContextVar, so the
pure ``render(configs)`` signatures of the format modules stay unchanged.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import yaml

from app.core.exceptions import ValidationError

FORMATS = ("clash", "mihomo", "singbox")
ALL_TOKEN = "{ALL}"
MAX_TEMPLATE_BYTES = 256 * 1024

_active: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "xlink_client_templates", default=None
)


@contextmanager
def use(templates: dict[str, dict[str, Any]]) -> Iterator[None]:
    token = _active.set(templates)
    try:
        yield
    finally:
        _active.reset(token)


def active(fmt: str) -> dict[str, Any] | None:
    templates = _active.get()
    if not templates:
        return None
    base = templates.get(fmt)
    return copy.deepcopy(base) if base is not None else None


def parse(fmt: str, content: str) -> dict[str, Any]:
    """Parse and sanity-check a template. Raised errors surface at save time."""
    if fmt not in FORMATS:
        raise ValidationError(f"Unknown template format {fmt!r}.", code="template_invalid")
    if len(content.encode()) > MAX_TEMPLATE_BYTES:
        raise ValidationError("Template is too large.", code="template_invalid")
    try:
        doc = json.loads(content) if fmt == "singbox" else yaml.safe_load(content)
    except (ValueError, yaml.YAMLError) as exc:
        raise ValidationError(f"Template does not parse: {exc}", code="template_invalid") from exc
    if not isinstance(doc, dict):
        raise ValidationError("Template must be a mapping/object.", code="template_invalid")
    if fmt == "singbox" and not isinstance(doc.get("outbounds", []), list):
        raise ValidationError(
            "sing-box template 'outbounds' must be a list.", code="template_invalid"
        )
    if fmt in ("clash", "mihomo") and not isinstance(doc.get("proxy-groups", []), list):
        raise ValidationError("'proxy-groups' must be a list.", code="template_invalid")
    return doc


def _expand(items: list[Any], names: list[str]) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if item == ALL_TOKEN:
            out.extend(n for n in names if n not in out)
        elif item not in out:
            out.append(item)
    return out


def apply_clash(base: dict[str, Any], proxies: list[dict[str, Any]]) -> dict[str, Any]:
    names = [p["name"] for p in proxies]
    base["proxies"] = proxies
    groups = base.get("proxy-groups") or []
    for g in groups:
        if isinstance(g, dict) and isinstance(g.get("proxies"), list):
            g["proxies"] = _expand(g["proxies"], names) or ["DIRECT"]
    if not groups:
        groups = [{"name": "PROXY", "type": "select", "proxies": names or ["DIRECT"]}]
    base["proxy-groups"] = groups
    base.setdefault("rules", ["MATCH,PROXY"])
    return base


def apply_singbox(base: dict[str, Any], outbounds: list[dict[str, Any]]) -> dict[str, Any]:
    tags = [o["tag"] for o in outbounds if "tag" in o]
    own = [o for o in base.get("outbounds", []) if isinstance(o, dict)]
    for o in own:
        if isinstance(o.get("outbounds"), list):
            o["outbounds"] = _expand(o["outbounds"], tags)
    base["outbounds"] = outbounds + own
    return base
