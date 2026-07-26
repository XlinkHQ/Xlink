from __future__ import annotations

import time
import uuid

import grpc
import structlog

from app.core.logging import get_logger

logger = get_logger("xlink.agent.grpc")


class LoggingInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler

        if handler.unary_unary is not None:
            inner = handler.unary_unary

            async def wrapper(request, context):
                start = time.monotonic()
                structlog.contextvars.bind_contextvars(
                    request_id=uuid.uuid4().hex, transport="grpc"
                )
                try:
                    return await inner(request, context)
                except grpc.RpcError:
                    raise
                except Exception:
                    logger.exception("grpc_unhandled", method=method)
                    await context.abort(grpc.StatusCode.INTERNAL, "internal error")
                finally:
                    dur = (time.monotonic() - start) * 1000
                    logger.info("grpc_call", method=method, duration_ms=round(dur, 2))
                    structlog.contextvars.clear_contextvars()

            return grpc.unary_unary_rpc_method_handler(
                wrapper,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        return handler
