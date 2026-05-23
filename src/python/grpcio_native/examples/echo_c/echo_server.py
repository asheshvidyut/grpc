# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Example: serve native (C) RPC handlers from a Python gRPC server.

Builds on the grpcio_native package. The hot RPC paths run in C with the
GIL released; everything else (server lifecycle, port binding, registration)
stays in Python.

Run:
    $ make                 # builds echo_handler.dylib / echo_handler.so
    $ python echo_server.py
"""

import os
import platform
import sys
from concurrent import futures

import grpc

# Allow running from the source tree without installing grpcio_native.
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

import grpcio_native  # noqa: E402

_LIB_NAME = "echo_handler.dylib" if platform.system() == "Darwin" else "echo_handler.so"
_LIB_PATH = os.path.join(os.path.dirname(__file__), _LIB_NAME)


def serve(port: int = 50051) -> None:
    if not os.path.isfile(_LIB_PATH):
        sys.stderr.write(
            f"Native library {_LIB_PATH} not found; run `make` first.\n"
        )
        sys.exit(1)

    module = grpcio_native.load_native_module(_LIB_PATH)
    print(f"loaded {_LIB_PATH}", flush=True)

    method_handlers = {
        "Echo": grpcio_native.native_unary_unary_rpc_method_handler(
            module, "echo_unary"
        ),
        "Double": grpcio_native.native_unary_unary_rpc_method_handler(
            module, "double_uint32"
        ),
        "NotFound": grpcio_native.native_unary_unary_rpc_method_handler(
            module, "always_not_found"
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "echo.Echo", method_handlers
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"native echo server listening on :{port}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
