from __future__ import annotations

import grpc

from app.agent.grpc import agent_pb2_grpc as pb_grpc
from app.agent.grpc.servicer import NodeAgentServicer
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.redis import RedisCache
from app.db.session import Database
from app.events.bus import EventBus

logger = get_logger("xlink.agent.grpc")


class GrpcServer:
    def __init__(
        self,
        db: Database,
        cache: RedisCache,
        events: EventBus,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._servicer = NodeAgentServicer(db, cache, events, settings)
        self._server: grpc.aio.Server | None = None

    async def start(self) -> None:
        if not self._settings.grpc_enabled:
            return
        from app.agent.grpc.interceptors import LoggingInterceptor

        server = grpc.aio.server(
            interceptors=[LoggingInterceptor()],
            options=[
                ("grpc.max_receive_message_length", 16 * 1024 * 1024),
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_permit_without_calls", 1),
                ("grpc.so_reuseport", 1),
            ],
        )
        pb_grpc.add_NodeAgentServicer_to_server(self._servicer, server)
        service_names = self._register_health_and_reflection(server)

        bind = f"{self._settings.grpc_host}:{self._settings.grpc_port}"

        creds = self._server_credentials()
        if creds is not None:
            server.add_secure_port(bind, creds)
            mode = "mTLS"
        else:
            server.add_insecure_port(bind)
            mode = "insecure"

        await server.start()
        self._server = server
        logger.info("grpc_started", bind=bind, mode=mode, services=len(service_names))

    def _register_health_and_reflection(self, server: grpc.aio.Server) -> list[str]:
        from app.agent.grpc import agent_pb2

        full_name = agent_pb2.DESCRIPTOR.services_by_name["NodeAgent"].full_name
        service_names = [full_name]
        try:
            from grpc_health.v1 import health, health_pb2, health_pb2_grpc

            health_servicer = health.aio.HealthServicer()
            health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
            service_names.append(health_pb2.DESCRIPTOR.services_by_name["Health"].full_name)
        except Exception as exc:
            logger.warning("grpc_health_unavailable", error=str(exc))
        try:
            from grpc_reflection.v1alpha import reflection

            reflection.enable_server_reflection(
                (*service_names, reflection.SERVICE_NAME), server
            )
        except Exception as exc:
            logger.warning("grpc_reflection_unavailable", error=str(exc))
        return service_names

    def _server_credentials(self) -> grpc.ServerCredentials | None:
        cert = self._settings.grpc_tls_cert_path
        key = self._settings.grpc_tls_key_path
        ca = self._settings.grpc_tls_ca_path
        if not (cert and key):
            return None
        with open(cert, "rb") as fh:
            cert_chain = fh.read()
        with open(key, "rb") as fh:
            private_key = fh.read()
        root_certs = None
        require_client_auth = False
        if ca:
            with open(ca, "rb") as fh:
                root_certs = fh.read()
            require_client_auth = True
        return grpc.ssl_server_credentials(
            [(private_key, cert_chain)],
            root_certificates=root_certs,
            require_client_auth=require_client_auth,
        )

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.stop(grace=5.0)
            self._server = None
            logger.info("grpc_stopped")
