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
"""Benchmark for pre-read payload optimization with registered methods.

This benchmarks the GRPC_SRM_PAYLOAD_READ_INITIAL_BYTE_BUFFER optimization
which pre-reads the request payload during the initial call event, avoiding
a separate ReceiveMessage batch + CQ round-trip for unary RPCs.

Usage:
    python benchmark_preread_payload.py [payload_size_bytes] [iterations]
"""

from concurrent import futures
import sys
import time

import grpc

_SERVICE = "test.Benchmark"
_METHOD = f"/{_SERVICE}/PingPong"


class PingPongServicer:
    """A simple servicer that echoes back a fixed response."""

    def PingPong(self, request, context):
        return b"OK"


def run_server(port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))

    # Use add_registered_method_handlers to exercise the registered method
    # path with GRPC_SRM_PAYLOAD_READ_INITIAL_BYTE_BUFFER.
    # Keys must be bare method names — the API internally calls
    # fully_qualified_method(service_name, method) to build "/service/method".
    handler = grpc.unary_unary_rpc_method_handler(
        PingPongServicer().PingPong,
    )
    server.add_registered_method_handlers(_SERVICE, {"PingPong": handler})
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server


def run_benchmark(port, payload_size, iterations):
    channel = grpc.insecure_channel(f"localhost:{port}")
    # Use _registered_method=True to exercise the registered call path.
    stub = channel.unary_unary(_METHOD, _registered_method=True)

    payload = b"x" * payload_size

    print(f"=== Registered Method Benchmark (Pre-read Payload) ===")
    print(f"Payload size: {payload_size} bytes")
    print(f"Iterations: {iterations}")

    # Warmup
    for _ in range(min(50, iterations)):
        stub(payload)

    start_time = time.perf_counter()
    for i in range(iterations):
        response = stub(payload)
        assert response == b"OK", f"Expected b'OK', got {response!r}"

    end_time = time.perf_counter()
    total_time = end_time - start_time
    rps = iterations / total_time
    avg_latency_us = (total_time / iterations) * 1_000_000

    print(f"Total time: {total_time:.4f} seconds")
    print(f"RPC/s: {rps:.0f}")
    print(f"Avg latency: {avg_latency_us:.1f} μs")
    if payload_size > 0:
        throughput_mbps = (
            (payload_size * iterations) / (1024 * 1024) / total_time
        )
        print(f"Throughput: {throughput_mbps:.2f} MB/s")
    print()

    channel.close()


if __name__ == "__main__":
    port = 50053
    payload_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 10000

    server = run_server(port)
    try:
        run_benchmark(port, payload_size, iterations)
    finally:
        server.stop(0)
