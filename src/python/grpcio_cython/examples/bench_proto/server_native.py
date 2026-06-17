# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""MatMul server using JIT compiled Cython handlers via grpcio_cython.

Automatically compiles clean Cython handlers and registers them to the server.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent import futures

import grpc

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

import grpcio_cython  # noqa: E402

_DEFAULT_OPTIONS = [
    ("grpc.max_receive_message_length", 64 * 1024 * 1024),
    ("grpc.max_send_message_length", 64 * 1024 * 1024),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    # 1. Dynamically generate Python and C++ protobuf classes at startup
    proto_path = os.path.join(_HERE, "bench.proto")
    print("Generating Python Protobuf classes from bench.proto...")
    subprocess.check_call([
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{_HERE}", f"--python_out={_HERE}", f"--grpc_python_out={_HERE}",
        proto_path
    ])
    print("Generating C++ Protobuf classes from bench.proto...")
    subprocess.check_call([
        "protoc", f"-I{_HERE}", f"--cpp_out={_HERE}",
        proto_path
    ])

    src_path = os.path.join(_HERE, "handler.pyx")

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=args.workers),
        options=_DEFAULT_OPTIONS,
    )

    # Automatically JIT-compile and register the service class!
    print("Compiling and registering Cython handlers dynamically...")
    grpcio_cython.add_native_handlers(
        server=server,
        pyx_file=src_path,
        service_name="bench.BenchService",
        class_name="BenchService"
    )
    print("Cython JIT module compiled and registered successfully!")

    server.add_insecure_port(f"[::]:{args.port}")
    server.start()
    print(f"JIT Cython server listening on :{args.port}")
    print(f"  workers={args.workers}  src={src_path}")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0).wait()


if __name__ == "__main__":
    main()
