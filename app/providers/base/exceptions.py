from __future__ import annotations

from app.core.exceptions import XLinkError


class ProviderError(XLinkError):
    status_code = 500
    code = "provider_error"
    message = "Provider operation failed."


class ProviderNotFoundError(ProviderError):
    status_code = 404
    code = "provider_not_found"
    message = "Requested provider is not registered."


class ProviderAlreadyRegisteredError(ProviderError):
    status_code = 409
    code = "provider_already_registered"
    message = "A provider with this name is already registered."


class CapabilityNotSupportedError(ProviderError):
    status_code = 422
    code = "capability_not_supported"
    message = "Provider does not support the requested capability."


class ProviderConfigurationError(ProviderError):
    status_code = 422
    code = "provider_configuration_error"
    message = "Provider configuration is invalid."


class ProviderValidationError(ProviderError):
    status_code = 422
    code = "provider_validation_error"
    message = "Provider payload is invalid."


class ClientNotFoundError(ProviderError):
    status_code = 404
    code = "provider_client_not_found"
    message = "Client not found on provider."


class ClientAlreadyExistsError(ProviderError):
    status_code = 409
    code = "provider_client_exists"
    message = "Client already exists on provider."
