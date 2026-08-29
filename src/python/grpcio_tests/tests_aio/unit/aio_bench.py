# Copyright 2026 The gRPC Authors
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
"""gRPC Python AsyncIO Performance Benchmark."""

import asyncio
import time

import grpc
from grpc.experimental import aio


class BenchmarkHandler(grpc.GenericRpcHandler):

    def service(self, handler_call_details):
        if handler_call_details.method == "/Benchmark/Unary":
            return grpc.unary_unary_rpc_method_handler(self.unary_handler)
        elif handler_call_details.method == "/Benchmark/Stream":
            return grpc.stream_stream_rpc_method_handler(self.stream_handler)
        return None

    async def unary_handler(self, request, context):
        return request

    async def stream_handler(self, request_iterator, context):
        async for req in request_iterator:
            yield req


async def run_unary_benchmark(target, concurrency=100, duration=3.0):
    channel = aio.insecure_channel(target)
    unary_call = channel.unary_unary("/Benchmark/Unary")

    payload = b"x" * 100
    stop_event = asyncio.Event()
    counts = [0] * concurrency
    latencies = []

    async def worker(worker_id):
        nonlocal counts
        local_count = 0
        local_latencies = []
        while not stop_event.is_set():
            t0 = time.perf_counter()
            await unary_call(payload)
            t1 = time.perf_counter()
            local_latencies.append((t1 - t0) * 1000.0)
            local_count += 1
        counts[worker_id] = local_count
        latencies.extend(local_latencies)

    # Warmup
    for _ in range(50):
        await unary_call(payload)

    start_time = time.perf_counter()
    tasks = [asyncio.create_task(worker(i)) for i in range(concurrency)]

    await asyncio.sleep(duration)
    stop_event.set()
    await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start_time

    total_requests = sum(counts)
    qps = total_requests / total_time
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0
    p90 = latencies[int(len(latencies) * 0.90)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0

    await channel.close()
    return qps, avg_lat, p50, p90, p99, total_requests


async def run_streaming_benchmark(target, count=20000):
    channel = aio.insecure_channel(target)
    stream_call = channel.stream_stream("/Benchmark/Stream")

    payload = b"x" * 100
    call = stream_call()

    start_time = time.perf_counter()

    async def sender():
        for _ in range(count):
            await call.write(payload)
        await call.done_writing()

    async def receiver():
        received = 0
        async for _ in call:
            received += 1
        return received

    _, received = await asyncio.gather(sender(), receiver())
    total_time = time.perf_counter() - start_time
    msg_rate = received / total_time

    await channel.close()
    return msg_rate, received, total_time


async def main():
    server = aio.server()
    server.add_generic_rpc_handlers([BenchmarkHandler()])
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    target = f"127.0.0.1:{port}"

    print(f"\n============================================================")
    print(f"  gRPC Python AsyncIO Performance Benchmark")
    print(f"  Target: {target}")
    print(f"============================================================")

    print("\n--- 1. Unary RPC Benchmark ---")
    for concurrency in [1, 10, 50, 100, 200]:
        qps, avg, p50, p90, p99, total = await run_unary_benchmark(
            target, concurrency=concurrency, duration=3.0
        )
        print(
            f"  Concurrency = {concurrency:3d}: {qps:8.1f} QPS | Latency: avg={avg:5.2f}ms p50={p50:5.2f}ms p90={p90:5.2f}ms p99={p99:5.2f}ms ({total:,} reqs)"
        )

    print("\n--- 2. BiDi Streaming Throughput Benchmark ---")
    msg_rate, count, duration = await run_streaming_benchmark(
        target, count=30000
    )
    print(
        f"  Streaming: {msg_rate:,.1f} msgs/sec ({count:,} msgs in {duration:.2f}s)"
    )
    print(f"============================================================\n")

    await server.stop(None)


if __name__ == "__main__":
    asyncio.run(main())
