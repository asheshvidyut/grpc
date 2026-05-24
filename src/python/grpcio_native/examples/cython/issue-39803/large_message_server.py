# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# JIT Server driver for the C++ Protobuf repeated-float load test.

import os
import sys
from concurrent import futures
import grpc

import asyncio

# Add grpcio_native path
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..", "..", "..")))
import grpcio_native

async def main_async():
    port = 50051
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    src_path = os.path.join(os.path.dirname(__file__), "large_message_handler.pyx")
    out_dir = os.path.dirname(__file__)

    options = [
        ("grpc.max_receive_message_length", 64 * 1024 * 1024),
        ("grpc.max_send_message_length", 64 * 1024 * 1024),
    ]
    server = grpc.aio.server(options=options)

    # Automatically JIT-compile and register the service class! (100% zero-boilerplate!)
    print("Compiling and registering Cython handlers dynamically...")
    grpcio_native.add_native_handlers(
        server=server,
        pyx_file=src_path,
        service_name="large_message.LargeMessageService",
        class_name="LargeMessageService"
    )
    print("Cython JIT module compiled and registered successfully!")
    server.add_insecure_port(f"[::]:{port}")
    print(f"Starting JIT Cython C++ Protobuf AsyncIO server on port: {port}")
    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
