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
"""Benchmark: aio server with sub-interpreters under concurrent CPU-bound load.

Sub-interpreters optimize CONCURRENT requests with CPU-bound handlers.
Each sub-interpreter has its own GIL, so multiple handlers can execute
Python code simultaneously across cores.

Compare with benchmark_script_simple_aio.py (no sub-interpreters) to see
the throughput difference under concurrent load.
"""

import asyncio
import sys
import time

import grpc

_METHOD = "/test.Benchmark/CpuWork"


def _cpu_work():
    """Simulate CPU-bound work (e.g. protobuf parsing, validation)."""
    total = 0
    for i in range(200_000):
        total += i * i
    return total


class GenericHandler(grpc.GenericRpcHandler):
    def service(self, handler_call_details):
        if handler_call_details.method == _METHOD:

            async def handler(req, ctx):
                _cpu_work()
                return b"OK"

            return grpc.unary_unary_rpc_method_handler(handler)
        return None


async def run_server(port, use_subinterpreters):
    options = [
        ("grpc.max_send_message_length", 160 * 1024 * 1024),
        ("grpc.max_receive_message_length", 160 * 1024 * 1024),
    ]
    server_kwargs = dict(
        handlers=(GenericHandler(),),
        options=options,
    )
    if use_subinterpreters:
        server_kwargs["experimental_use_subinterpreters"] = True
        server_kwargs["experimental_subinterpreter_count"] = 4

    server = grpc.aio.server(**server_kwargs)
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    return server


async def run_benchmark(port, num_clients, rpcs_per_client):
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    try:
        stub = channel.unary_unary(_METHOD)
        payload = b"x" * 1024  # 1KB — focus on handler time, not I/O

        total_rpcs = num_clients * rpcs_per_client
        print(f"Clients: {num_clients}, RPCs/client: {rpcs_per_client}")
        print(f"Total RPCs: {total_rpcs}")

        # Warmup
        for _ in range(3):
            await stub(payload)

        async def client_worker(count):
            for _ in range(count):
                resp = await stub(payload)
                assert resp == b"OK"

        start_time = time.time()
        tasks = [
            asyncio.create_task(client_worker(rpcs_per_client))
            for _ in range(num_clients)
        ]
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        qps = total_rpcs / total_time
        print(f"Total time: {total_time:.4f} seconds")
        print(f"QPS: {qps:.1f}")
    finally:
        await channel.close()


async def main():
    port_normal = 50070
    port_subinterp = 50071

    print("=" * 50)
    print("Aio Server — CPU-bound handler benchmark")
    print(f"Python {sys.version}")
    print("=" * 50)

    print("\n--- WITHOUT sub-interpreters ---")
    server1 = await run_server(port_normal, use_subinterpreters=False)
    try:
        await run_benchmark(port_normal, num_clients=8, rpcs_per_client=50)
    finally:
        await server1.stop(0)

    print("\n--- WITH sub-interpreters (4 workers) ---")
    server2 = await run_server(port_subinterp, use_subinterpreters=True)
    try:
        await run_benchmark(port_subinterp, num_clients=8, rpcs_per_client=50)
    finally:
        await server2.stop(0)


if __name__ == "__main__":
    asyncio.run(main())
