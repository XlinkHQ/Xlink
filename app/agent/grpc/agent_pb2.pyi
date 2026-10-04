from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ConfigRequest(_message.Message):
    __slots__ = ("node_id", "known_version")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    KNOWN_VERSION_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    known_version: str
    def __init__(self, node_id: _Optional[str] = ..., known_version: _Optional[str] = ...) -> None: ...

class DesiredConfig(_message.Message):
    __slots__ = ("node_id", "config_version", "config_json", "assignment_count")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIG_VERSION_FIELD_NUMBER: _ClassVar[int]
    CONFIG_JSON_FIELD_NUMBER: _ClassVar[int]
    ASSIGNMENT_COUNT_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    config_version: str
    config_json: str
    assignment_count: int
    def __init__(self, node_id: _Optional[str] = ..., config_version: _Optional[str] = ..., config_json: _Optional[str] = ..., assignment_count: _Optional[int] = ...) -> None: ...

class TrafficSample(_message.Message):
    __slots__ = ("assignment_id", "upload_bytes", "download_bytes", "collected_at_unix_ms")
    ASSIGNMENT_ID_FIELD_NUMBER: _ClassVar[int]
    UPLOAD_BYTES_FIELD_NUMBER: _ClassVar[int]
    DOWNLOAD_BYTES_FIELD_NUMBER: _ClassVar[int]
    COLLECTED_AT_UNIX_MS_FIELD_NUMBER: _ClassVar[int]
    assignment_id: str
    upload_bytes: int
    download_bytes: int
    collected_at_unix_ms: int
    def __init__(self, assignment_id: _Optional[str] = ..., upload_bytes: _Optional[int] = ..., download_bytes: _Optional[int] = ..., collected_at_unix_ms: _Optional[int] = ...) -> None: ...

class TrafficBatch(_message.Message):
    __slots__ = ("node_id", "batch_id", "samples")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    BATCH_ID_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    batch_id: str
    samples: _containers.RepeatedCompositeFieldContainer[TrafficSample]
    def __init__(self, node_id: _Optional[str] = ..., batch_id: _Optional[str] = ..., samples: _Optional[_Iterable[_Union[TrafficSample, _Mapping]]] = ...) -> None: ...

class TrafficAck(_message.Message):
    __slots__ = ("batch_id", "received", "inserted", "duplicates", "skipped")
    BATCH_ID_FIELD_NUMBER: _ClassVar[int]
    RECEIVED_FIELD_NUMBER: _ClassVar[int]
    INSERTED_FIELD_NUMBER: _ClassVar[int]
    DUPLICATES_FIELD_NUMBER: _ClassVar[int]
    SKIPPED_FIELD_NUMBER: _ClassVar[int]
    batch_id: str
    received: int
    inserted: int
    duplicates: int
    skipped: int
    def __init__(self, batch_id: _Optional[str] = ..., received: _Optional[int] = ..., inserted: _Optional[int] = ..., duplicates: _Optional[int] = ..., skipped: _Optional[int] = ...) -> None: ...

class MetricSample(_message.Message):
    __slots__ = ("name", "value", "observed_at_unix_ms")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_UNIX_MS_FIELD_NUMBER: _ClassVar[int]
    name: str
    value: float
    observed_at_unix_ms: int
    def __init__(self, name: _Optional[str] = ..., value: _Optional[float] = ..., observed_at_unix_ms: _Optional[int] = ...) -> None: ...

class MetricBatch(_message.Message):
    __slots__ = ("node_id", "samples")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    samples: _containers.RepeatedCompositeFieldContainer[MetricSample]
    def __init__(self, node_id: _Optional[str] = ..., samples: _Optional[_Iterable[_Union[MetricSample, _Mapping]]] = ...) -> None: ...

class LogLine(_message.Message):
    __slots__ = ("level", "message", "observed_at_unix_ms")
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_UNIX_MS_FIELD_NUMBER: _ClassVar[int]
    level: str
    message: str
    observed_at_unix_ms: int
    def __init__(self, level: _Optional[str] = ..., message: _Optional[str] = ..., observed_at_unix_ms: _Optional[int] = ...) -> None: ...

class LogBatch(_message.Message):
    __slots__ = ("node_id", "lines")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    LINES_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    lines: _containers.RepeatedCompositeFieldContainer[LogLine]
    def __init__(self, node_id: _Optional[str] = ..., lines: _Optional[_Iterable[_Union[LogLine, _Mapping]]] = ...) -> None: ...

class ConnectionSample(_message.Message):
    __slots__ = ("assignment_id", "source_ip")
    ASSIGNMENT_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_IP_FIELD_NUMBER: _ClassVar[int]
    assignment_id: str
    source_ip: str
    def __init__(self, assignment_id: _Optional[str] = ..., source_ip: _Optional[str] = ...) -> None: ...

class ConnectionBatch(_message.Message):
    __slots__ = ("node_id", "samples")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    samples: _containers.RepeatedCompositeFieldContainer[ConnectionSample]
    def __init__(self, node_id: _Optional[str] = ..., samples: _Optional[_Iterable[_Union[ConnectionSample, _Mapping]]] = ...) -> None: ...

class ProviderHealth(_message.Message):
    __slots__ = ("provider_name", "status", "latency_ms", "detail")
    PROVIDER_NAME_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    provider_name: str
    status: str
    latency_ms: float
    detail: str
    def __init__(self, provider_name: _Optional[str] = ..., status: _Optional[str] = ..., latency_ms: _Optional[float] = ..., detail: _Optional[str] = ...) -> None: ...

class ProviderHealthBatch(_message.Message):
    __slots__ = ("node_id", "checks")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    CHECKS_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    checks: _containers.RepeatedCompositeFieldContainer[ProviderHealth]
    def __init__(self, node_id: _Optional[str] = ..., checks: _Optional[_Iterable[_Union[ProviderHealth, _Mapping]]] = ...) -> None: ...

class ReportedState(_message.Message):
    __slots__ = ("node_id", "config_version", "agent_version", "applied_json", "provider_status")
    class ProviderStatusEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIG_VERSION_FIELD_NUMBER: _ClassVar[int]
    AGENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    APPLIED_JSON_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_STATUS_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    config_version: str
    agent_version: str
    applied_json: str
    provider_status: _containers.ScalarMap[str, str]
    def __init__(self, node_id: _Optional[str] = ..., config_version: _Optional[str] = ..., agent_version: _Optional[str] = ..., applied_json: _Optional[str] = ..., provider_status: _Optional[_Mapping[str, str]] = ...) -> None: ...

class DriftReport(_message.Message):
    __slots__ = ("node_id", "severity", "desired_version", "reported_version", "drift_json", "remediated")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    DESIRED_VERSION_FIELD_NUMBER: _ClassVar[int]
    REPORTED_VERSION_FIELD_NUMBER: _ClassVar[int]
    DRIFT_JSON_FIELD_NUMBER: _ClassVar[int]
    REMEDIATED_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    severity: str
    desired_version: str
    reported_version: str
    drift_json: str
    remediated: bool
    def __init__(self, node_id: _Optional[str] = ..., severity: _Optional[str] = ..., desired_version: _Optional[str] = ..., reported_version: _Optional[str] = ..., drift_json: _Optional[str] = ..., remediated: _Optional[bool] = ...) -> None: ...

class CommandLeaseRequest(_message.Message):
    __slots__ = ("node_id",)
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    def __init__(self, node_id: _Optional[str] = ...) -> None: ...

class Command(_message.Message):
    __slots__ = ("command_id", "node_id", "kind", "payload_json", "signature", "origin", "attempts", "max_attempts")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_FIELD_NUMBER: _ClassVar[int]
    ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    MAX_ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    node_id: str
    kind: str
    payload_json: str
    signature: str
    origin: str
    attempts: int
    max_attempts: int
    def __init__(self, command_id: _Optional[str] = ..., node_id: _Optional[str] = ..., kind: _Optional[str] = ..., payload_json: _Optional[str] = ..., signature: _Optional[str] = ..., origin: _Optional[str] = ..., attempts: _Optional[int] = ..., max_attempts: _Optional[int] = ...) -> None: ...

class CommandLease(_message.Message):
    __slots__ = ("lease_token", "commands")
    LEASE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    COMMANDS_FIELD_NUMBER: _ClassVar[int]
    lease_token: str
    commands: _containers.RepeatedCompositeFieldContainer[Command]
    def __init__(self, lease_token: _Optional[str] = ..., commands: _Optional[_Iterable[_Union[Command, _Mapping]]] = ...) -> None: ...

class CommandResult(_message.Message):
    __slots__ = ("node_id", "command_id", "lease_token", "success", "result_json")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    LEASE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_JSON_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    command_id: str
    lease_token: str
    success: bool
    result_json: str
    def __init__(self, node_id: _Optional[str] = ..., command_id: _Optional[str] = ..., lease_token: _Optional[str] = ..., success: _Optional[bool] = ..., result_json: _Optional[str] = ...) -> None: ...

class CommandResultAck(_message.Message):
    __slots__ = ("command_id", "status")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    status: str
    def __init__(self, command_id: _Optional[str] = ..., status: _Optional[str] = ...) -> None: ...

class EventRequest(_message.Message):
    __slots__ = ("node_id",)
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    def __init__(self, node_id: _Optional[str] = ...) -> None: ...

class NodeEvent(_message.Message):
    __slots__ = ("type", "data_json")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    type: str
    data_json: str
    def __init__(self, type: _Optional[str] = ..., data_json: _Optional[str] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ("accepted", "dropped")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    DROPPED_FIELD_NUMBER: _ClassVar[int]
    accepted: int
    dropped: int
    def __init__(self, accepted: _Optional[int] = ..., dropped: _Optional[int] = ...) -> None: ...
