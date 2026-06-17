# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""MatMul server using a naive Python servicer that calls into C via ctypes.

Represents the "just wrap C with ctypes" approach: framework deserializes
the request to a Python proto, handler reads request.a / request.b, marshals
to ctypes arrays, calls matmul_raw in bench_handler.{so,dylib}, then builds
a Python proto response. Framework serializes that back to wire bytes.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import platform
import sys
from concurrent import futures

import grpc

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    import bench_pb2  # noqa: E402
    import bench_pb2_grpc  # noqa: E402
except ImportError:
    sys.stderr.write(
        "bench_pb2 not generated. Run `make` in this directory first.\n"
    )
    sys.exit(1)

_LIB_NAME = (
    "bench_handler.dylib"
    if platform.system() == "Darwin"
    else "bench_handler.so"
)
_LIB_PATH = os.path.join(_HERE, _LIB_NAME)

if not os.path.isfile(_LIB_PATH):
    sys.stderr.write(
        f"{_LIB_PATH} not built. Run `make` in this directory first.\n"
    )
    sys.exit(1)

_lib = ctypes.CDLL(_LIB_PATH)
_lib.matmul_raw.argtypes = [
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_float),
    ctypes.c_uint32,
]
_lib.matmul_raw.restype = None


class CtypesServicer(bench_pb2_grpc.BenchServiceServicer):
    def MatMul(self, request, context):
        n = request.n
        size = n * n
        a_arr = (ctypes.c_float * size)(*request.a)
        b_arr = (ctypes.c_float * size)(*request.b)
        c_arr = (ctypes.c_float * size)()
        _lib.matmul_raw(a_arr, b_arr, c_arr, n)
        return bench_pb2.MatMulResponse(c=list(c_arr))

    def Hash(self, request, context):
        # Out of scope for this server; reject so the proto contract is honest.
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        return bench_pb2.HashResponse()


_DEFAULT_OPTIONS = [
    ("grpc.max_receive_message_length", 64 * 1024 * 1024),
    ("grpc.max_send_message_length", 64 * 1024 * 1024),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=50052)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=args.workers),
        options=_DEFAULT_OPTIONS,
    )
    bench_pb2_grpc.add_BenchServiceServicer_to_server(CtypesServicer(), server)
    server.add_insecure_port(f"[::]:{args.port}")
    server.start()
    print(f"ctypes matmul server listening on :{args.port}")
    print(f"  workers={args.workers}  lib={_LIB_PATH}")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0).wait()


if __name__ == "__main__":
    main()
