# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

import argparse
import os
import platform
import subprocess
import sys
from concurrent import futures
import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
_PROTO_PATH = os.path.join(_GEN_DIR, "echo.proto")

# Resolve path to grpcio_cython
sys.path.insert(0, os.path.abspath(os.path.join(_GEN_DIR, "..", "..")))
import grpcio_cython

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=50099, help="Port to listen on")
    args = parser.parse_args()

    # 1. Dynamically compile protobuf and the C++ shared library at startup
    print("Generating Python Protobuf classes from echo.proto...")
    subprocess.check_call([
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{_GEN_DIR}", f"--python_out={_GEN_DIR}", f"--grpc_python_out={_GEN_DIR}",
        _PROTO_PATH
    ])

    print("Compiling C++ native shared library...")
    subprocess.check_call(["make", "-C", _GEN_DIR])

    lib_ext = "dylib" if platform.system() == "Darwin" else "so"
    lib_path = os.path.join(_GEN_DIR, f"echo_handler.{lib_ext}")

    # 2. Load the C++ shared library via grpcio_cython
    print(f"Loading native module from {lib_path}...")
    module = grpcio_cython.load_native_module(lib_path)

    # 3. Create the native method handlers
    print("Binding native handlers...")
    echo_unary_handler = grpcio_cython.native_unary_unary_rpc_method_handler(
        module, "echo_unary"
    )
    echo_stream_handler = grpcio_cython.native_unary_stream_rpc_method_handler(
        module, "echo_stream"
    )

    # 4. Set up standard Python gRPC server and register generic handlers
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    
    method_handlers = {
        "Echo": echo_unary_handler,
        "EchoStream": echo_stream_handler,
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "echo.EchoService", method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))

    # 5. Enable Server Reflection
    print("Enabling gRPC Server Reflection...")
    from grpc_reflection.v1alpha import reflection
    import echo_pb2
    SERVICE_NAMES = (
        echo_pb2.DESCRIPTOR.services_by_name['EchoService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    # 6. Add insecure port and start
    server.add_insecure_port(f"[::]:{args.port}")
    print(f"Starting gRPC server with C++ native flow on port: {args.port}")
    server.start()
    print("Server started. Press Ctrl+C to terminate.")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0)

if __name__ == "__main__":
    main()
