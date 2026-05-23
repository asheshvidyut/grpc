# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Server using the protobuf-aware native echo handler.

The C++ handler in echo_handler.cc parses EchoRequest with libprotobuf, runs
the business logic, and serializes EchoResponse with libprotobuf — all
without holding the GIL.
"""

import os
import platform
import sys
from concurrent import futures

import grpc

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))

import grpcio_native  # noqa: E402

# After cmake --build, the .so/.dylib is in build/.
_LIB_NAME = "echo_handler.dylib" if platform.system() == "Darwin" else "echo_handler.so"
_LIB_PATHS = [
    os.path.join(os.path.dirname(__file__), "build", _LIB_NAME),
    os.path.join(os.path.dirname(__file__), _LIB_NAME),
]


def _resolve_lib():
    for path in _LIB_PATHS:
        if os.path.isfile(path):
            return path
    sys.stderr.write(
        "Native library not found in any of:\n  "
        + "\n  ".join(_LIB_PATHS)
        + "\nBuild first:\n"
        "  mkdir -p build && cd build && cmake .. && cmake --build .\n"
    )
    sys.exit(1)


def serve(port: int = 50052) -> None:
    lib_path = _resolve_lib()
    module = grpcio_native.load_native_module(lib_path)
    print(f"loaded {lib_path}", flush=True)

    handler = grpcio_native.native_unary_unary_rpc_method_handler(
        module, "Echo"
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    server.add_generic_rpc_handlers(
        (grpc.method_handlers_generic_handler("echo.Echo", {"Echo": handler}),)
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"native echo server (protobuf) listening on :{port}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
