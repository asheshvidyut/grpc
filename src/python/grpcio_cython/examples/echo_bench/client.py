# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Standard Protobuf client for verifying the C-based JIT gRPC server.

import os
import sys
import subprocess
import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
_PROTO_PATH = os.path.join(_GEN_DIR, "echo.proto")

# 1. Dynamically generate Python Protobuf classes at startup
print("Generating Python Protobuf classes from echo.proto...")
subprocess.check_call([
    sys.executable, "-m", "grpc_tools.protoc",
    f"-I{_GEN_DIR}", f"--python_out={_GEN_DIR}", f"--grpc_python_out={_GEN_DIR}",
    _PROTO_PATH
])

sys.path.insert(0, _GEN_DIR)
import echo_pb2
import echo_pb2_grpc

def main():
    port = 50088
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    print(f"Connecting to standard channel on localhost:{port}...")
    with grpc.insecure_channel(f"localhost:{port}") as channel:
        stub = echo_pb2_grpc.EchoServiceStub(channel)

        # Verify Echo Service RPC
        print("\n--- Verification: Echo RPC ---")
        test_message = "Hello from C-based native gRPC handler!"
        print(f"Sending Echo request: '{test_message}'")
        
        request_echo = echo_pb2.EchoRequest(message=test_message)
        response_echo = stub.Echo(request_echo)
        
        print(f"Received Echo response: '{response_echo.message}'")
        assert response_echo.message == test_message, "Echo message mismatch!"
        print("Verification SUCCESSFUL!")

if __name__ == "__main__":
    main()
