# Copyright 2019 The gRPC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Server-side implementation of gRPC Asyncio Python."""

import asyncio
from concurrent.futures import Executor
from typing import Any, Dict, Optional, Sequence

import grpc
from grpc import _common
from grpc import _compression
from grpc import _observability
from grpc._cython import cygrpc
from grpc._subinterpreter_pool import SubinterpreterPool
from grpc._subinterpreter_pool import _is_supported as _subinterpreters_supported

from . import _base_server
from ._interceptor import ServerInterceptor
from ._typing import ChannelArgumentType


def _augment_channel_arguments(
    base_options: ChannelArgumentType, compression: Optional[grpc.Compression]
):
    compression_option = _compression.create_channel_option(compression)
    maybe_server_call_tracer_factory_option = (
        _observability.create_server_call_tracer_factory_option(xds=False)
    )
    return (
        tuple(base_options)
        + compression_option
        + maybe_server_call_tracer_factory_option
    )


class _SubinterpreterMethodHandler:
    """Wraps a unary-unary handler to dispatch through a sub-interpreter pool.

    The handler runs as a sync function that sends raw bytes to a
    sub-interpreter worker and returns the raw response bytes.
    The aio server's existing sync-handler path
    (loop.run_in_executor) takes care of threading.
    """

    def __init__(
        self,
        original_handler: grpc.RpcMethodHandler,
        method_name: str,
        pool: SubinterpreterPool,
    ):
        self._original = original_handler
        self._method_name = method_name
        self._pool = pool

        # Preserve the handler interface flags.
        self.request_streaming = original_handler.request_streaming
        self.response_streaming = original_handler.response_streaming
        self.request_serializer = getattr(
            original_handler, "request_serializer", None
        )
        self.response_serializer = getattr(
            original_handler, "response_serializer", None
        )
        # Use None for request/response serializers so the aio server
        # passes us raw bytes and accepts raw bytes back.
        self.request_deserializer = None
        self.response_serializer = None

        # The handler itself is a sync function — the Cython aio server
        # will detect this via inspect and route it through
        # loop.run_in_executor().
        self.unary_unary = self._dispatch_handler

    def _dispatch_handler(self, request_bytes, context):
        """Sync handler dispatched to the sub-interpreter pool."""
        # request_bytes is raw bytes (no deserializer set).
        if isinstance(request_bytes, memoryview):
            request_bytes = bytes(request_bytes)
        elif isinstance(request_bytes, list):
            request_bytes = b"".join(request_bytes)

        # Round-robin across pool workers.
        import threading

        worker_id = hash(threading.current_thread().ident) % self._pool.worker_count
        response_bytes, status_code, details = self._pool.dispatch(
            worker_id, self._method_name, request_bytes
        )

        if status_code != 0:
            context.set_code(grpc.StatusCode.UNKNOWN)
            context.set_details(details)
            return b""

        return response_bytes


class _SubinterpreterGenericHandler(grpc.GenericRpcHandler):
    """Wraps an existing GenericRpcHandler to route unary-unary RPCs
    through a sub-interpreter pool."""

    def __init__(
        self,
        inner: grpc.GenericRpcHandler,
        pool: SubinterpreterPool,
    ):
        self._inner = inner
        self._pool = pool

    def service(self, handler_call_details):
        method_handler = self._inner.service(handler_call_details)
        if method_handler is None:
            return None

        # Only intercept unary-unary handlers.
        if (
            not method_handler.request_streaming
            and not method_handler.response_streaming
            and method_handler.unary_unary is not None
        ):
            return _SubinterpreterMethodHandler(
                method_handler,
                handler_call_details.method,
                self._pool,
            )

        # Streaming RPCs pass through unchanged.
        return method_handler


class Server(_base_server.Server):
    """Serves RPCs."""

    def __init__(
        self,
        thread_pool: Optional[Executor],
        generic_handlers: Optional[Sequence[grpc.GenericRpcHandler]],
        interceptors: Optional[Sequence[Any]],
        options: ChannelArgumentType,
        maximum_concurrent_rpcs: Optional[int],
        compression: Optional[grpc.Compression],
        subinterpreter_pool: Optional[SubinterpreterPool] = None,
    ):
        self._loop = cygrpc.get_working_loop()
        self._subinterpreter_pool = subinterpreter_pool
        if interceptors:
            invalid_interceptors = [
                interceptor
                for interceptor in interceptors
                if not isinstance(interceptor, ServerInterceptor)
            ]
            if invalid_interceptors:
                error_msg = (
                    "Interceptor must be ServerInterceptor,"
                    "the following are invalid: {invalid_interceptors}"
                )
                # TODO(asheshvidyut): fix the value error below
                # not caught by ruff.
                raise ValueError(error_msg)

        # Wrap generic handlers to dispatch through the pool.
        if subinterpreter_pool is not None:
            generic_handlers = tuple(
                _SubinterpreterGenericHandler(h, subinterpreter_pool)
                for h in (generic_handlers or ())
            )

        self._server = cygrpc.AioServer(
            self._loop,
            thread_pool,
            generic_handlers,
            interceptors,
            _augment_channel_arguments(options, compression),
            maximum_concurrent_rpcs,
        )

    def add_generic_rpc_handlers(
        self, generic_rpc_handlers: Sequence[grpc.GenericRpcHandler]
    ) -> None:
        """Registers GenericRpcHandlers with this Server.

        This method is only safe to call before the server is started.

        Args:
          generic_rpc_handlers: A sequence of GenericRpcHandlers that will be
          used to service RPCs.
        """
        if self._subinterpreter_pool is not None:
            generic_rpc_handlers = [
                _SubinterpreterGenericHandler(h, self._subinterpreter_pool)
                for h in generic_rpc_handlers
            ]
        self._server.add_generic_rpc_handlers(generic_rpc_handlers)

    def add_registered_method_handlers(
        self,
        service_name: str,
        method_handlers: Dict[str, grpc.RpcMethodHandler],
    ) -> None:
        # TODO(xuanwn): Implement this for AsyncIO.
        pass

    def add_insecure_port(self, address: str) -> int:
        """Opens an insecure port for accepting RPCs.

        This method may only be called before starting the server.

        Args:
          address: The address for which to open a port. If the port is 0,
            or not specified in the address, then the gRPC runtime will choose a port.

        Returns:
          An integer port on which the server will accept RPC requests.
        """
        return _common.validate_port_binding_result(
            address, self._server.add_insecure_port(_common.encode(address))
        )

    def add_secure_port(
        self, address: str, server_credentials: grpc.ServerCredentials
    ) -> int:
        """Opens a secure port for accepting RPCs.

        This method may only be called before starting the server.

        Args:
          address: The address for which to open a port.
            if the port is 0, or not specified in the address, then the gRPC
            runtime will choose a port.
          server_credentials: A ServerCredentials object.

        Returns:
          An integer port on which the server will accept RPC requests.
        """
        return _common.validate_port_binding_result(
            address,
            self._server.add_secure_port(
                _common.encode(address), server_credentials
            ),
        )

    async def start(self) -> None:
        """Starts this Server.

        This method may only be called once. (i.e. it is not idempotent).
        """
        if self._subinterpreter_pool is not None:
            self._subinterpreter_pool.start()
        await self._server.start()

    async def stop(self, grace: Optional[float]) -> None:
        """Stops this Server.

        This method immediately stops the server from servicing new RPCs in
        all cases.

        If a grace period is specified, this method waits until all active
        RPCs are finished or until the grace period is reached. RPCs that haven't
        been terminated within the grace period are aborted.
        If a grace period is not specified (by passing None for grace), all
        existing RPCs are aborted immediately and this method blocks until
        the last RPC handler terminates.

        This method is idempotent and may be called at any time. Passing a
        smaller grace value in a subsequent call will have the effect of
        stopping the Server sooner (passing None will have the effect of
        stopping the server immediately). Passing a larger grace value in a
        subsequent call will not have the effect of stopping the server later
        (i.e. the most restrictive grace value is used).

        Args:
          grace: A duration of time in seconds or None.
        """
        await self._server.shutdown(grace)
        if self._subinterpreter_pool is not None:
            self._subinterpreter_pool.shutdown()

    async def wait_for_termination(
        self, timeout: Optional[float] = None
    ) -> bool:
        """Block current coroutine until the server stops.

        This is an EXPERIMENTAL API.

        The wait will not consume computational resources during blocking, and
        it will block until one of the two following conditions are met:

        1) The server is stopped or terminated;
        2) A timeout occurs if timeout is not `None`.

        The timeout argument works in the same way as `threading.Event.wait()`.
        https://docs.python.org/3/library/threading.html#threading.Event.wait

        Args:
          timeout: A floating point number specifying a timeout for the
            operation in seconds.

        Returns:
          A bool indicates if the operation times out.
        """
        return await self._server.wait_for_termination(timeout)

    def __del__(self):
        """Schedules a graceful shutdown in current event loop.

        The Cython AioServer doesn't hold a ref-count to this class. It should
        be safe to slightly extend the underlying Cython object's life span.
        """
        if hasattr(self, "_server") and self._server.is_running():
            cygrpc.schedule_coro_threadsafe(
                self._server.shutdown(None),
                self._loop,
            )


def server(
    migration_thread_pool: Optional[Executor] = None,
    handlers: Optional[Sequence[grpc.GenericRpcHandler]] = None,
    interceptors: Optional[Sequence[Any]] = None,
    options: Optional[ChannelArgumentType] = None,
    maximum_concurrent_rpcs: Optional[int] = None,
    compression: Optional[grpc.Compression] = None,
    experimental_use_subinterpreters: bool = False,
    experimental_subinterpreter_count: Optional[int] = None,
):
    """Creates a Server with which RPCs can be serviced.

    Args:
      migration_thread_pool: A futures.ThreadPoolExecutor to be used by the
        Server to execute non-AsyncIO RPC handlers for migration purpose.
      handlers: An optional list of GenericRpcHandlers used for executing RPCs.
        More handlers may be added by calling add_generic_rpc_handlers any time
        before the server is started.
      interceptors: An optional list of ServerInterceptor objects that observe
        and optionally manipulate the incoming RPCs before handing them over to
        handlers. The interceptors are given control in the order they are
        specified. This is an EXPERIMENTAL API.
      options: An optional list of key-value pairs (:term:`channel_arguments`
        in gRPC runtime) to configure the channel.
      maximum_concurrent_rpcs: The maximum number of concurrent RPCs this server
        will service before returning RESOURCE_EXHAUSTED status, or None to
        indicate no limit.
      compression: An element of grpc.Compression, e.g.
        grpc.Compression.Gzip. This compression algorithm will be used for the
        lifetime of the server unless overridden by set_compression.
      experimental_use_subinterpreters: EXPERIMENTAL. If True, enables
        sub-interpreter dispatch for unary-unary handlers (Python 3.13+).
      experimental_subinterpreter_count: EXPERIMENTAL. Number of sub-interpreter
        workers. Defaults to 4.

    Returns:
      A Server object.
    """
    pool = None
    if experimental_use_subinterpreters and _subinterpreters_supported():
        count = experimental_subinterpreter_count or 4
        # Build servicer specs from handlers at pool creation time.
        # Workers import servicer modules independently.
        specs = []
        if handlers:
            from grpc._server import _build_servicer_specs

            specs = _build_servicer_specs(handlers)
        pool = SubinterpreterPool(count=count, servicer_specs=specs)

    return Server(
        migration_thread_pool,
        () if handlers is None else handlers,
        () if interceptors is None else interceptors,
        () if options is None else options,
        maximum_concurrent_rpcs,
        compression,
        subinterpreter_pool=pool,
    )
