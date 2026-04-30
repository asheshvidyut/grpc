# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Benchmark: sync server with sub-interpreters under concurrent CPU-bound load.

Sub-interpreters optimize CONCURRENT requests with CPU-bound handlers.
Each sub-interpreter has its own GIL, so multiple handlers can execute
Python code simultaneously across cores.

Compare with benchmark_script_simple.py (no sub-interpreters) to see
the throughput difference under concurrent load.
"""

from concurrent import futures
import sys
import threading
import time

import grpc

_METHOD = "/test.Benchmark/CpuWork"


def _cpu_work():
    """Simulate CPU-bound work (e.g. protobuf parsing, validation)."""
    total = 0
    for i in range(200_000):
        total += i * i
    return total


def run_server(port, use_subinterpreters):
    options = [
        ("grpc.max_send_message_length", 160 * 1024 * 1024),
        ("grpc.max_receive_message_length", 160 * 1024 * 1024),
    ]

    server_kwargs = dict(
        thread_pool=futures.ThreadPoolExecutor(max_workers=8),
        options=options,
    )
    if use_subinterpreters:
        server_kwargs["experimental_use_subinterpreters"] = True
        server_kwargs["experimental_subinterpreter_count"] = 4

    server = grpc.server(**server_kwargs)

    class GenericHandler(grpc.GenericRpcHandler):
        def service(self, handler_call_details):
            if handler_call_details.method == _METHOD:

                def handler(req, ctx):
                    _cpu_work()
                    return b"OK"

                return grpc.unary_unary_rpc_method_handler(handler)
            return None

    server.add_generic_rpc_handlers((GenericHandler(),))
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server


def run_benchmark(port, num_clients, rpcs_per_client):
    channel = grpc.insecure_channel(f"localhost:{port}")
    stub = channel.unary_unary(_METHOD)
    payload = b"x" * 1024  # 1KB — focus on handler time, not I/O

    total_rpcs = num_clients * rpcs_per_client
    print(f"Clients: {num_clients}, RPCs/client: {rpcs_per_client}")
    print(f"Total RPCs: {total_rpcs}")

    # Warmup
    for _ in range(3):
        stub(payload)

    errors = []

    def client_worker(count):
        try:
            for _ in range(count):
                resp = stub(payload)
                assert resp == b"OK"
        except Exception as e:
            errors.append(str(e))

    start_time = time.time()
    threads = [
        threading.Thread(target=client_worker, args=(rpcs_per_client,))
        for _ in range(num_clients)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    total_time = time.time() - start_time
    qps = total_rpcs / total_time

    if errors:
        print(f"Errors: {errors[:3]}")
    print(f"Total time: {total_time:.4f} seconds")
    print(f"QPS: {qps:.1f}")


if __name__ == "__main__":
    port_normal = 50060
    port_subinterp = 50061

    print("=" * 50)
    print("Sync Server — CPU-bound handler benchmark")
    print(f"Python {sys.version}")
    print("=" * 50)

    print("\n--- WITHOUT sub-interpreters ---")
    server1 = run_server(port_normal, use_subinterpreters=False)
    try:
        run_benchmark(port_normal, num_clients=8, rpcs_per_client=50)
    finally:
        server1.stop(0)

    print("\n--- WITH sub-interpreters (4 workers) ---")
    server2 = run_server(port_subinterp, use_subinterpreters=True)
    try:
        run_benchmark(port_subinterp, num_clients=8, rpcs_per_client=50)
    finally:
        server2.stop(0)
