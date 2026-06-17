# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Verification tool for MatMul.
# Sequentially launches the server in all three modes (Pure Python, Ctypes,
# JIT C++), calls each one with the exact same random matrices, and verifies
# that their floating-point outputs are mathematically identical.

import os
import sys
import time
import random
import subprocess
import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
_PROTO_PATH = os.path.join(_GEN_DIR, "matmul.proto")

# 1. Dynamically generate Python Protobuf classes at startup
print("Generating Python Protobuf classes from matmul.proto...")
subprocess.check_call([
    sys.executable, "-m", "grpc_tools.protoc",
    f"-I{_GEN_DIR}", f"--python_out={_GEN_DIR}", f"--grpc_python_out={_GEN_DIR}",
    _PROTO_PATH
])

sys.path.insert(0, _GEN_DIR)
import matmul_pb2
import matmul_pb2_grpc


def run_and_call(server_arg: str, n: int, a: list, b: list) -> list:
    """Launches the server with the given mode argument, calls it, and returns the result."""
    print(f"\nStarting MatMul server in [{server_arg}] mode...")
    
    # Ensure port 50089 is clean before starting
    subprocess.run(
        "lsof -t -i :50089 | xargs kill -9 2>/dev/null || true",
        shell=True
    )
    
    # Start server in background
    server_proc = subprocess.Popen([
        sys.executable, "server.py", server_arg
    ])
    
    # JIT mode compilation takes slightly longer
    sleep_time = 12 if server_arg == "--jit" else 6
    time.sleep(sleep_time)
    
    try:
        with grpc.insecure_channel("127.0.0.1:50089") as channel:
            stub = matmul_pb2_grpc.MatMulServiceStub(channel)
            request = matmul_pb2.MatMulRequest(n=n, a=a, b=b)
            response = stub.MatMul(request)
            return list(response.c)
    finally:
        print(f"Stopping server process...")
        server_proc.terminate()
        server_proc.wait()
        subprocess.run(
            "lsof -t -i :50089 | xargs kill -9 2>/dev/null || true",
            shell=True
        )


def main():
    n = 4
    random.seed(42) # Anchored seed for reproducible randoms
    a = [random.randint(1, 10) for _ in range(n * n)]
    b = [random.randint(1, 10) for _ in range(n * n)]

    print("Starting 3-Way Paradigm Verification...")
    print(f"Matrix dimension N = {n} ({n*n} integers per matrix)")
    
    # 1. Run Pure Python
    c_python = run_and_call("--pure-python", n, a, b)
    
    # 2. Run Ctypes
    c_ctypes = run_and_call("--ctypes", n, a, b)
    
    # 3. Run Native JIT C++
    c_jit = run_and_call("--jit", n, a, b)

    # Validate lengths
    assert len(c_python) == n*n
    assert len(c_ctypes) == n*n
    assert len(c_jit) == n*n

    # 4. Print values from all three paradigms
    print("\n--- Result Matrix C Values ---")
    print(f"Pure Python: {c_python}")
    print(f"Ctypes:      {c_ctypes}")
    print(f"Native JIT:  {c_jit}")

    # 5. Perform direct mathematical comparison
    print("\n--- Mathematical Verification ---")
    success = True
    
    for idx in range(n * n):
        v_py = c_python[idx]
        v_ct = c_ctypes[idx]
        v_jt = c_jit[idx]
        
        if v_py != v_ct or v_py != v_jt:
            print(f"Mismatch at index {idx}!")
            print(f"  Pure Python: {v_py}")
            print(f"  Ctypes:      {v_ct}")
            print(f"  Native JIT:  {v_jt}")
            success = False
            break

    if success:
        print("SUCCESS: All 3 server paradigms returned MATHEMATICALLY IDENTICAL outputs!")
    else:
        print("ERROR: Output mismatch between paradigms!")
        sys.exit(1)


if __name__ == "__main__":
    main()
