from __future__ import annotations

from app.providers.base.exceptions import ProviderError, ProviderValidationError


class XrayPayloadError(ProviderValidationError):
    code = "xray_payload_error"
    message = "Xray payload is invalid."


class UnsupportedProtocolError(XrayPayloadError):
    code = "xray_unsupported_protocol"
    message = "Unsupported Xray protocol."


class MissingProtocolError(XrayPayloadError):
    code = "xray_missing_protocol"
    message = "Protocol is required in spec.attributes['protocol']."


class MissingEmailError(XrayPayloadError):
    code = "xray_missing_email"
    message = "Client email is required."


class InvalidClientIdError(XrayPayloadError):
    code = "xray_invalid_client_id"
    message = "Client id must be a valid UUID for this protocol."


class UnsupportedNetworkError(XrayPayloadError):
    code = "xray_unsupported_network"
    message = "Unsupported Xray transport network."


class UnsupportedSecurityError(XrayPayloadError):
    code = "xray_unsupported_security"
    message = "Unsupported Xray security."


class InvalidStreamSettingsError(XrayPayloadError):
    code = "xray_invalid_stream_settings"
    message = "Invalid Xray transport/security combination."


class XrayGatewayError(ProviderError):
    code = "xray_gateway_error"
    message = "Xray gateway operation failed."


class XrayTransportError(XrayGatewayError):
    code = "xray_transport_error"
    message = "Xray transport failure."


class XrayTimeoutError(XrayTransportError):
    status_code = 504
    code = "xray_timeout"
    message = "Xray transport timed out."


class XrayConnectionError(XrayTransportError):
    status_code = 502
    code = "xray_connection_error"
    message = "Could not connect to Xray transport."


class XrayRetryExhaustedError(XrayGatewayError):
    status_code = 502
    code = "xray_retry_exhausted"
    message = "Xray gateway retries exhausted."


class XrayCircuitOpenError(XrayGatewayError):
    status_code = 503
    code = "xray_circuit_open"
    message = "Xray gateway circuit breaker is open."
