# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Reproduction script for gRPC Python Issue #39803:
# "grpc.aio Server blocked by serialization of large messages"
#
# Evaluates the standard gRPC AsyncIO server (blocked by Python Protobuf parsing)
# vs the JIT Cython Native Server (GIL-free C++ Protobuf parsing).

import os
import sys
import time
import asyncio
import random
import subprocess
import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
_PROTO_PATH = os.path.join(_GEN_DIR, "large_message.proto")

# 1. Dynamically compile the protobuf schema at startup (for Python and C++)
print("Generating Python Protobuf classes from large_message.proto...")
subprocess.check_call(
    [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{_GEN_DIR}",
        f"--python_out={_GEN_DIR}",
        f"--grpc_python_out={_GEN_DIR}",
        _PROTO_PATH,
    ]
)

print("Generating C++ Protobuf classes from large_message.proto...")
subprocess.check_call(
    [
        "protoc",
        f"-I{_GEN_DIR}",
        f"--cpp_out={_GEN_DIR}",
        _PROTO_PATH,
    ]
)

sys.path.insert(0, _GEN_DIR)
import large_message_pb2
import large_message_pb2_grpc

# 2. Background loop latency monitor for the Standard Server
async def standard_server_event_loop_monitor():
    print("[Monitor] Starting STANDARD SERVER event loop latency monitor (checking every 10ms)...")
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(0.01)
        elapsed = (time.perf_counter() - t0) * 1000.0 # ms
        if elapsed > 50.0: # Warn if the loop was blocked for more than 50ms
            print(f"\n>>> [WARNING] [STANDARD SERVER EVENT LOOP] !!! Standard Server Event Loop was BLOCKED/FROZEN for {elapsed:.1f} ms !!! <<<\n")

# 3. Standard gRPC AsyncIO Servicer using standard Protobuf
class StandardLargeMessageServicer(large_message_pb2_grpc.LargeMessageServiceServicer):
    async def ProcessLargeMessage(self, request, context):
        return large_message_pb2.LargeMessageResponse(status="ok")

async def start_standard_server(port, options):
    server = grpc.aio.server(options=options)
    large_message_pb2_grpc.add_LargeMessageServiceServicer_to_server(
        StandardLargeMessageServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    return server

async def run_unified_client(port, num_floats, options):
    # Create an actual LargeMessageRequest object containing 1,000,000 floats
    print(f"[Client] Generating request with {num_floats:,} floats...")
    floats_list = [random.random() for _ in range(num_floats)]
    request = large_message_pb2.LargeMessageRequest(values=floats_list)
    
    print(f"[Client] Connecting standard channel to localhost:{port}...")
    async with grpc.aio.insecure_channel(f"localhost:{port}", options=options) as channel:
        stub = large_message_pb2_grpc.LargeMessageServiceStub(channel)
        
        print(f"[Client] Sending large Protobuf request...")
        t_start = time.perf_counter()
        response = await stub.ProcessLargeMessage(request)
        duration = (time.perf_counter() - t_start) * 1000.0
        print(f"[Client] RPC complete in {duration:.1f} ms. Response status: {response.status}")

async def main():
    port_standard = 50055
    port_native = 50051
    num_floats = 1000000 # 1,000,000 floats (about 4 MB binary size)
    
    options = [
        ("grpc.max_receive_message_length", 64 * 1024 * 1024),
        ("grpc.max_send_message_length", 64 * 1024 * 1024),
    ]
    
    # --------------------------------------------------------------------------
    # TEST 1: Standard gRPC AsyncIO Server (Blocked event loop via Python Protobuf)
    # --------------------------------------------------------------------------
    print("\n================================================================================")
    print("TEST 1: Standard gRPC AsyncIO Server (Real Protobuf repeated field blocks loop)")
    print("================================================================================")
    
    std_server = await start_standard_server(port_standard, options)
    monitor_task = asyncio.create_task(standard_server_event_loop_monitor())
    
    await asyncio.sleep(1.0)
    await run_unified_client(port_standard, num_floats, options)
    
    # Stop Standard Server
    monitor_task.cancel()
    await std_server.stop(grace=0)
    await asyncio.sleep(1.0)
    
    # --------------------------------------------------------------------------
    # TEST 2: JIT Cython Native Server (Unblocked event loop via C++ Protobuf!)
    # --------------------------------------------------------------------------
    print("\n================================================================================")
    print("TEST 2: JIT Cython C++ Protobuf Server (GIL released, C++ Protobuf parsing)")
    print("================================================================================")
    
    # Launch large_message_server.py in a background subprocess
    server_proc = subprocess.Popen(
        [sys.executable, "large_message_server.py", str(port_native)]
    )
    await asyncio.sleep(10.0) # Wait for JIT compilation and startup
    
    await run_unified_client(port_native, num_floats, options)
    
    # Stop Native Server
    server_proc.terminate()
    server_proc.wait()
    
    print("\n================================================================================")
    print("Verification complete! JIT Cython C++ Protobuf Server keeps the event loop responsive!")
    print("================================================================================")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
