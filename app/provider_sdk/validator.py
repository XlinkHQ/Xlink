from __future__ import annotations

from app.core.exceptions import ValidationError
from app.provider_sdk.manifest import ProviderManifest
from app.providers.base.provider import Provider


class ProviderManifestValidator:
    def __init__(self, *, platform_version: str = "0.1.0") -> None:
        self._platform_version = platform_version

    def validate(self, manifest: ProviderManifest, provider: Provider) -> None:
        metadata = provider.metadata
        if metadata.name != manifest.name:
            raise ValidationError(
                "Provider manifest name does not match provider metadata.",
                code="provider_manifest_mismatch",
                details={"manifest": manifest.name, "provider": metadata.name},
            )
        if metadata.kind is not manifest.kind:
            raise ValidationError(
                "Provider manifest kind does not match provider metadata.",
                code="provider_manifest_mismatch",
                details={"manifest": manifest.kind.value, "provider": metadata.kind.value},
            )
        if not manifest.capabilities.issubset(metadata.capabilities):
            missing = sorted(cap.value for cap in manifest.capabilities - metadata.capabilities)
            raise ValidationError(
                "Provider does not implement requested capabilities.",
                code="provider_capability_mismatch",
                details={"missing": missing},
            )
        if _version_tuple(self._platform_version) < _version_tuple(manifest.min_platform_version):
            raise ValidationError(
                "Provider requires a newer platform version.",
                code="provider_platform_version_unsupported",
                details={
                    "platform_version": self._platform_version,
                    "required": manifest.min_platform_version,
                },
            )


def _version_tuple(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]
