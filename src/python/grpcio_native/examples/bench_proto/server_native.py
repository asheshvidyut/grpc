# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""MatMul server using grpcio_native — wire bytes straight to the C handler.

The handler is bench_handler.matmul_handler in bench_handler.{so,dylib};
it parses the protobuf with libprotobuf, runs the kernel, and serializes
the response, all with the GIL released.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from concurrent import futures

import grpc

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

import grpcio_native  # noqa: E402

_LIB_NAME = (
    "bench_handler.dylib"
    if platform.system() == "Darwin"
    else "bench_handler.so"
)
_LIB_PATH = os.path.join(_HERE, _LIB_NAME)

_DEFAULT_OPTIONS = [
    ("grpc.max_receive_message_length", 64 * 1024 * 1024),
    ("grpc.max_send_message_length", 64 * 1024 * 1024),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    if not os.path.isfile(_LIB_PATH):
        sys.stderr.write(
            f"{_LIB_PATH} not built. Run `make` in this directory first.\n"
        )
        sys.exit(1)

    module = grpcio_native.load_native_module(_LIB_PATH)
    handlers = grpc.method_handlers_generic_handler(
        "bench.BenchService",
        {
            "MatMul": grpcio_native.native_unary_unary_rpc_method_handler(
                module, "matmul_handler"
            ),
        },
    )

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=args.workers),
        options=_DEFAULT_OPTIONS,
    )
    server.add_generic_rpc_handlers((handlers,))
    server.add_insecure_port(f"[::]:{args.port}")
    server.start()
    print(f"native matmul server listening on :{args.port}")
    print(f"  workers={args.workers}  lib={_LIB_PATH}")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0).wait()


if __name__ == "__main__":
    main()
