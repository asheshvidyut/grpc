# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""grpcio_native — register native (C/C++) handlers with a gRPC Python server.

Example:

    import grpc
    from concurrent import futures
    import grpcio_native

    module = grpcio_native.load_native_module("./echo_handler.so")
    handler = grpcio_native.native_unary_unary_rpc_method_handler(
        module, "echo_unary"
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    server.add_generic_rpc_handlers((
        grpc.method_handlers_generic_handler("echo.Echo", {"Echo": handler}),
    ))
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()
"""

from ._handler import (
    NativeHandlerError,
    NativeModule,
    load_native_module,
    native_stream_stream_rpc_method_handler,
    native_stream_unary_rpc_method_handler,
    native_unary_stream_rpc_method_handler,
    native_unary_unary_rpc_method_handler,
)

__all__ = [
    "NativeHandlerError",
    "NativeModule",
    "load_native_module",
    "native_stream_stream_rpc_method_handler",
    "native_stream_unary_rpc_method_handler",
    "native_unary_stream_rpc_method_handler",
    "native_unary_unary_rpc_method_handler",
]

__version__ = "0.1.0"
