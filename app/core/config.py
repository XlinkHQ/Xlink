from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Literal

from pydantic import (
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _resolve_version() -> str:
    try:
        return version("xlink")
    except PackageNotFoundError:
        return "0.0.0"


APP_VERSION = _resolve_version()


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


def _split_csv(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("[") and raw.endswith("]"):
            import json

            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except ValueError:
                pass
        return [item.strip() for item in raw.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], Field(default_factory=list)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="XLINK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Environment = Environment.LOCAL
    debug: bool = False
    project_name: str = "XLink"
    app_version: str = APP_VERSION
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    webhook_address: str = ""
    webhook_secret: str = ""
    discord_webhook_url: str = ""

    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""

    notify_expiring_days: int = 3
    notify_usage_percent: int = 80
    notification_interval_seconds: int = 3600

    @property
    def webhook_urls(self) -> list[str]:
        return [u.strip() for u in self.webhook_address.split(",") if u.strip()]

    @property
    def telegram_chats(self) -> list[str]:
        return [c.strip() for c in self.telegram_chat_ids.split(",") if c.strip()]

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "xlink"
    postgres_password: SecretStr = SecretStr("xlink")
    postgres_db: str = "xlink"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_echo: bool = False
    db_pool_mode: Literal["session", "transaction"] = "session"
    db_pool_pre_ping: bool = True
    web_concurrency: int = 1
    db_max_server_connections: int = 100

    database_url_override: str | None = None

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: SecretStr | None = None
    redis_max_connections: int = 50
    cache_ttl_seconds: int = 300

    jwt_secret_key: SecretStr = SecretStr("insecure-dev-key-change-me")
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4
    password_hash_max_workers: int = 8

    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120
    rate_limit_fail_open: bool = True
    trusted_proxy_ips: Annotated[list[str], NoDecode] = Field(default_factory=list)

    default_page_size: int = 20
    max_page_size: int = 100

    token_cleanup_enabled: bool = True
    token_cleanup_interval_seconds: int = 3600

    metrics_summary_enabled: bool = True
    metrics_summary_ttl_seconds: int = 60
    metrics_summary_refresh_seconds: int = 30

    traffic_retention_enabled: bool = True
    traffic_retention_days: int = 90
    traffic_retention_interval_seconds: int = 86400

    assignment_expiration_enabled: bool = True
    assignment_expiration_interval_seconds: int = 30
    # Public self-service registration. Off by default — this is an admin panel;
    # accounts are provisioned by admins, not by anonymous callers.
    registration_enabled: bool = False

    auto_backup_enabled: bool = True
    auto_backup_interval_seconds: int = 86400
    auto_backup_dir: str = "backups"
    auto_backup_keep: int = 7

    admin_username: str | None = None
    admin_password: SecretStr | None = None

    auto_failover_enabled: bool = True

    auto_failover_cooldown_seconds: int = 300

    agent_command_secret: SecretStr | None = None
    agent_reconcile_enabled: bool = True
    agent_reconcile_interval_seconds: int = 60
    agent_self_healing_enabled: bool = True
    agent_target_version: str | None = None
    node_status_interval_seconds: int = 20
    node_offline_after_seconds: int = 120

    provider_plugins_dir: str = ""

    grpc_enabled: bool = True
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    grpc_tls_cert_path: str = ""
    grpc_tls_key_path: str = ""
    grpc_tls_ca_path: str = ""

    _csv_validator = field_validator(
        "cors_origins",
        "trusted_hosts",
        "trusted_proxy_ips",
        mode="before",
    )(_split_csv)

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        secret = self.jwt_secret_key.get_secret_value()
        weak_secrets = {
            "",
            "secret",
            "password",
            "changeme",
            "change_me",
            "change-me",
            "default",
            "insecure-dev-key-change-me",
            "replace_me_with_openssl_rand_hex_32",
            "test-secret-key-not-for-production-use",
            "unit-test-secret-key-with-enough-length-32b",
        }
        if len(secret) < 32:
            raise ValueError("XLINK_JWT_SECRET_KEY must be at least 32 characters")
        if secret.lower() in weak_secrets or len(set(secret)) < 8:
            raise ValueError("XLINK_JWT_SECRET_KEY is too weak")

        if self.is_production:
            default_passwords = {
                "postgres",
                "password",
                "changeme",
                "change_me",
                "change-me",
                "default",
                "xlink",
                "admin",
                "root",
                "test",
                "change_me_in_production",
            }
            if self.postgres_password.get_secret_value().lower() in default_passwords:
                raise ValueError("XLINK_POSTGRES_PASSWORD must not use a default password")
            if not self.db_connection_safe:
                raise ValueError(
                    "Database connection fan-out exceeds XLINK_DB_MAX_SERVER_CONNECTIONS; "
                    "lower XLINK_DB_POOL_SIZE/XLINK_DB_MAX_OVERFLOW, reduce "
                    "XLINK_WEB_CONCURRENCY, or set XLINK_DB_POOL_MODE=transaction (PgBouncer)"
                )
            # Host-header hardening: with a real domain configured, "*" trusted
            # hosts is a poisoning risk. Warn (not fatal — IP-only deployments
            # legitimately run without a domain and rely on "*").
            if ("*" in self.trusted_hosts or not self.trusted_hosts) and self.domain:
                import warnings

                warnings.warn(
                    "XLINK_TRUSTED_HOSTS is '*' but a domain is set; restrict it to "
                    f"'{self.domain}' to prevent Host-header poisoning.",
                    stacklevel=2,
                )
        return self

    @property
    def agent_signing_secret(self) -> str:
        if self.agent_command_secret is not None:
            return self.agent_command_secret.get_secret_value()
        return self.jwt_secret_key.get_secret_value()

    @property
    def db_uses_pgbouncer(self) -> bool:
        return self.db_pool_mode == "transaction"

    @property
    def db_max_total_connections(self) -> int:
        if self.db_uses_pgbouncer:
            return self.web_concurrency
        per_worker = self.db_pool_size + self.db_max_overflow
        return per_worker * max(1, self.web_concurrency)

    @property
    def db_connection_safe(self) -> bool:
        return self.db_max_total_connections <= self.db_max_server_connections

    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.env is Environment.TESTING

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password.get_secret_value(),
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    @property
    def redis_url(self) -> str:
        password = self.redis_password.get_secret_value() if self.redis_password else None
        return str(
            RedisDsn.build(
                scheme="redis",
                username=None,
                password=password,
                host=self.redis_host,
                port=self.redis_port,
                path=str(self.redis_db),
            )
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
