from __future__ import annotations

from datetime import UTC, datetime

from app.core.exceptions import ValidationError
from app.domain.client_assignment import AssignmentStatus
from app.domain.node import NodeStatus
from app.providers.base.exceptions import ProviderNotFoundError
from app.providers.base.models import ProviderKind
from app.providers.base.registry import ProviderRegistry
from app.subscription.models import (
    SUPPORTED_SUBSCRIPTION_PROTOCOLS,
    ProviderConfig,
    SubscriptionSource,
)


class SubscriptionGenerator:
    def __init__(self, providers: ProviderRegistry) -> None:
        self._providers = providers

    async def generate_config(self, source: SubscriptionSource) -> ProviderConfig:
        return self._build_config(source)

    async def generate_feed(
        self, sources: tuple[SubscriptionSource, ...]
    ) -> tuple[ProviderConfig, ...]:
        configs: list[ProviderConfig] = []
        for source in sources:
            try:
                configs.append(self._build_config(source))
            except ValidationError:
                continue
        return tuple(configs)

    def _build_config(self, source: SubscriptionSource) -> ProviderConfig:
        self._validate_source(source)
        provider = self._get_provider(source.assignment.provider_kind)
        settings = {
            **source.profile.settings,
            "assignment_id": str(source.assignment.id),
            "profile_slug": source.profile.slug,
            "node_slug": source.node.slug,
        }
        return ProviderConfig.build(source=source, provider_name=provider.name, settings=settings)

    def _validate_source(self, source: SubscriptionSource) -> None:
        assignment = source.assignment
        profile = source.profile
        node = source.node

        if assignment.provider_kind != profile.provider_kind:
            raise ValidationError(
                "Assignment provider does not match profile provider.",
                code="subscription_provider_mismatch",
            )
        if assignment.status is not AssignmentStatus.ACTIVE:
            raise ValidationError(
                "Assignment is disabled.", code="subscription_assignment_disabled"
            )
        if not profile.is_active:
            raise ValidationError("Profile is disabled.", code="subscription_profile_disabled")
        if node.status is not NodeStatus.ACTIVE:
            raise ValidationError("Node is disabled.", code="subscription_node_disabled")

        expires_at = assignment.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                raise ValidationError(
                    "Assignment is expired.", code="subscription_assignment_expired"
                )

        protocol = profile.protocol.strip().lower()
        if protocol not in SUPPORTED_SUBSCRIPTION_PROTOCOLS:
            raise ValidationError(
                "Profile protocol is not supported for subscriptions.",
                code="subscription_protocol_unsupported",
                details={"protocol": profile.protocol},
            )

        self._get_provider(profile.provider_kind)

    def _get_provider(self, provider_kind: ProviderKind):
        try:
            return self._providers.get_by_kind(provider_kind)
        except ProviderNotFoundError as exc:
            raise ValidationError(
                "Provider is not registered.",
                code="subscription_provider_unavailable",
                details={"provider_kind": provider_kind.value},
            ) from exc
