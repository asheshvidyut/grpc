# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Standard Protobuf client for verifying the JIT Cython C++ Protobuf server.

import os
import sys
import random
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

def matmul_cpu(n, a, b):
    c = [0.0] * (n * n)
    for i in range(n):
        for j in range(n):
            s = 0.0
            for k in range(n):
                s += a[i * n + k] * b[k * n + j]
            c[i * n + j] = s
    return c

def main():
    port = 50088
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    print(f"Connecting to standard channel on localhost:{port}...")
    with grpc.insecure_channel(f"localhost:{port}") as channel:
        stub = echo_pb2_grpc.EchoServiceStub(channel)

        # ----------------------------------------------------------------------
        # 1. Verify Echo Service RPC
        # ----------------------------------------------------------------------
        print("\n--- Verification 1: Echo RPC ---")
        test_message = "Hello from standard Python Protobuf client!"
        print(f"Sending Echo request: '{test_message}'")
        
        request_echo = echo_pb2.EchoRequest(message=test_message)
        response_echo = stub.Echo(request_echo)
        
        print(f"Received Echo response: '{response_echo.message}'")
        assert response_echo.message == test_message, "Echo message mismatch!"
        print("Echo Verification SUCCESSFUL!")

        # ----------------------------------------------------------------------
        # 2. Verify MatMul Service RPC (Matrix math)
        # ----------------------------------------------------------------------
        print("\n--- Verification 2: MatMul matrix math RPC ---")
        n = 4
        a = [random.random() for _ in range(n * n)]
        b = [random.random() for _ in range(n * n)]
        
        print("Sending MatMul request (4x4 matrices)...")
        request_matmul = echo_pb2.MatMulRequest(n=n, a=a, b=b)
        response_matmul = stub.MatMul(request_matmul)
        
        print(f"Received MatMul response (C size: {len(response_matmul.c)} floats)")
        
        # Verify matrix multiplication results against local CPU implementation
        expected_c = matmul_cpu(n, a, b)
        success = True
        for idx, (v_got, v_exp) in enumerate(zip(response_matmul.c, expected_c)):
            if abs(v_got - v_exp) > 1e-4:
                print(f"Mismatch at index {idx}: got {v_got}, expected {v_exp}")
                success = False
                break
                
        if success:
            print("MatMul Verification SUCCESSFUL! Native JIT C++ Protobuf matched CPU math exactly!")
        else:
            print("MatMul Verification FAILED!")
            sys.exit(1)

if __name__ == "__main__":
    main()
