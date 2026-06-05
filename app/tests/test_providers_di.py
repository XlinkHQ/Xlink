from __future__ import annotations

from app.core.lifespan import AppState
from app.dependencies.core import get_providers
from app.providers.base.models import ProviderKind
from app.providers.base.registry import ProviderRegistry


async def test_registry_present_in_app_state(app_state: AppState) -> None:
    assert isinstance(app_state.providers, ProviderRegistry)
    assert "xray" in app_state.providers


async def test_get_providers_dependency_returns_registry(app_state: AppState) -> None:
    registry = get_providers(app_state)
    assert registry is app_state.providers
    assert registry.get_by_kind(ProviderKind.XRAY).name == "xray"
