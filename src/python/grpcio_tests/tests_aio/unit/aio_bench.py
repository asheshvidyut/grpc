#!/usr/bin/env python3
# Copyright 2026 gRPC authors.
import argparse
import asyncio
import statistics
import time
import grpc
from grpc.experimental import aio

from src.proto.grpc.testing import messages_pb2
from src.proto.grpc.testing import test_pb2_grpc


async def run_unary_benchmark(stub, concurrency=100, trials=5, trial_seconds=3):
    request = messages_pb2.SimpleRequest(
        response_size=32,
        payload=messages_pb2.Payload(body=b"x" * 32),
    )

    # Warmup
    for _ in range(50):
        await stub.UnaryCall(request)

    rates = []
    print(f"\n--- 1. Unary Throughput (Concurrency = {concurrency}) ---")
    for t in range(trials):
        count = 0
        deadline = time.perf_counter() + trial_seconds

        async def worker():
            nonlocal count
            while time.perf_counter() < deadline:
                await stub.UnaryCall(request)
                count += 1

        start = time.perf_counter()
        await asyncio.gather(*[worker() for _ in range(concurrency)])
        dur = time.perf_counter() - start
        rate = count / dur
        rates.append(rate)
        print(f"  Trial {t+1}/{trials}: {count:,} requests in {dur:.2f}s -> {rate:,.1f} QPS")

    mean_rate = statistics.mean(rates[1:]) if len(rates) > 1 else rates[0]
    print(f"  Mean Unary QPS: {mean_rate:,.1f} QPS")
    return mean_rate


async def run_streaming_benchmark(stub, concurrency=20, num_messages=2000):
    request = messages_pb2.StreamingOutputCallRequest(
        response_parameters=[
            messages_pb2.ResponseParameters(size=32)
            for _ in range(num_messages)
        ]
    )

    print(f"\n--- 2. Streaming Output Throughput ({concurrency} streams x {num_messages} msgs) ---")

    async def stream_worker():
        call = stub.StreamingOutputCall(request)
        received = 0
        async for _ in call:
            received += 1
        return received

    # Warmup
    await stream_worker()

    start = time.perf_counter()
    results = await asyncio.gather(*[stream_worker() for _ in range(concurrency)])
    dur = time.perf_counter() - start

    total_msgs = sum(results)
    rate = total_msgs / dur
    print(f"  Received {total_msgs:,} streaming messages in {dur:.2f}s -> {rate:,.1f} msg/s")
    return rate


async def main():
    parser = argparse.ArgumentParser(description="gRPC Python AsyncIO Performance Benchmark")
    parser.add_argument("--target", default="127.0.0.1:50051", help="Target gRPC server address (e.g. C++ interop_server)")
    parser.add_argument("--concurrency", type=int, default=100, help="Number of concurrent in-flight RPCs")
    parser.add_argument("--trials", type=int, default=5, help="Number of benchmark trials")
    parser.add_argument("--duration", type=int, default=3, help="Duration of each trial in seconds")
    args = parser.parse_args()

    print(f"============================================================")
    print(f"  gRPC Python AsyncIO Client Benchmark (grpcio={grpc.__version__})")
    print(f"  Target: {args.target}")
    print(f"============================================================")

    channel = aio.insecure_channel(args.target)
    try:
        await asyncio.wait_for(channel.channel_ready(), timeout=10)
    except asyncio.TimeoutError:
        print(f"\n[ERROR] Could not connect to server at {args.target} within 10s.")
        print(f"Make sure the C++ server is running first:")
        print(f"  bazel run //test/cpp/interop:interop_server -- --port=50051\n")
        return

    stub = test_pb2_grpc.TestServiceStub(channel)

    await run_unary_benchmark(stub, concurrency=args.concurrency, trials=args.trials, trial_seconds=args.duration)
    await run_streaming_benchmark(stub, concurrency=20, num_messages=2000)

    await channel.close()
    print(f"\n============================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
