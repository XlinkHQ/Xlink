from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from collections.abc import Iterable
from pathlib import Path

from app.core.logging import get_logger
from app.providers.base.provider import Provider
from app.providers.base.registry import ProviderRegistry

logger = get_logger("xlink.providers.plugins")

ENTRYPOINT_GROUP = "xlink.providers"


def _instantiate(obj: object) -> Provider | None:
    if isinstance(obj, Provider):
        return obj
    if inspect.isclass(obj) and issubclass(obj, Provider) and obj is not Provider:
        try:
            return obj()
        except Exception as exc:
            logger.warning("plugin_provider_init_failed", provider=obj.__name__, error=str(exc))
    return None


def _providers_from_module(module: object) -> list[Provider]:
    found: list[Provider] = []
    factory = getattr(module, "register", None)
    if callable(factory):
        try:
            result = factory()
        except Exception as exc:
            logger.warning(
                "plugin_register_failed", module=getattr(module, "__name__", "?"), error=str(exc)
            )
            result = None
        if result is not None:
            items = (
                result
                if isinstance(result, Iterable) and not isinstance(result, Provider)
                else [result]
            )
            for item in items:
                provider = _instantiate(item)
                if provider is not None:
                    found.append(provider)
    if found:
        return found
    for _, obj in inspect.getmembers(module):
        provider = _instantiate(obj) if inspect.isclass(obj) else None
        if provider is not None and type(obj).__module__ == getattr(module, "__name__", ""):
            found.append(provider)
    return found


def load_from_directory(path: str) -> list[Provider]:
    directory = Path(path)
    if not directory.is_dir():
        return []
    providers: list[Provider] = []
    for entry in sorted(directory.iterdir()):
        if entry.name.startswith("_") or entry.name.startswith("."):
            continue
        module_file = entry if entry.suffix == ".py" else entry / "__init__.py"
        if not module_file.is_file():
            continue
        mod_name = f"xlink_plugin_{entry.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, module_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.warning("plugin_load_failed", plugin=entry.name, error=str(exc))
            continue
        for provider in _providers_from_module(module):
            providers.append(provider)
            logger.info("plugin_provider_loaded", plugin=entry.name, provider=provider.name)
    return providers


def load_from_entrypoints() -> list[Provider]:
    providers: list[Provider] = []
    try:
        from importlib.metadata import entry_points

        eps = entry_points()
        selected = (
            eps.select(group=ENTRYPOINT_GROUP)
            if hasattr(eps, "select")
            else eps.get(ENTRYPOINT_GROUP, [])
        )
    except Exception as exc:
        logger.warning("plugin_entrypoints_failed", error=str(exc))
        return providers
    for ep in selected:
        try:
            obj = ep.load()
        except Exception as exc:
            logger.warning("plugin_entrypoint_load_failed", entrypoint=ep.name, error=str(exc))
            continue
        provider = _instantiate(obj() if callable(obj) and not isinstance(obj, Provider) else obj)
        if provider is not None:
            providers.append(provider)
            logger.info("plugin_provider_loaded", entrypoint=ep.name, provider=provider.name)
    return providers


def discover_plugins(directory: str | None = None) -> list[Provider]:
    providers: list[Provider] = []
    providers.extend(load_from_entrypoints())
    if directory:
        providers.extend(load_from_directory(directory))
    return providers


def register_plugins(registry: ProviderRegistry, directory: str | None = None) -> int:
    count = 0
    for provider in discover_plugins(directory):
        try:
            registry.register(provider, replace=True)
            count += 1
        except Exception as exc:
            logger.warning("plugin_register_conflict", provider=provider.name, error=str(exc))
    if count:
        logger.info("plugins_registered", count=count)
    return count
