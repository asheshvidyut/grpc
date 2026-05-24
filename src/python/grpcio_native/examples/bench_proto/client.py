# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""MatMul benchmark client.

Drives the BenchService.MatMul RPC at multiple square sizes against one
target. Sends the same wire-format payload regardless of which server
implementation is on the other end — the server's registration decides
whether request bytes are deserialized in Python or handed to a native
handler.

Examples:
  python client.py --target localhost:50051 --sizes 16,32,64,128
  python client.py --target localhost:50052 --sizes 16,32,64,128 --threads 8
  python client.py --target localhost:50051 --sizes 64 --samples 2000
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import threading
import time
from typing import List

import grpc

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    import bench_pb2  # noqa: E402
except ImportError:
    sys.stderr.write(
        "bench_pb2 not generated. Run `make` in this directory first.\n"
    )
    sys.exit(1)


_DEFAULT_OPTIONS = [
    ("grpc.max_receive_message_length", 64 * 1024 * 1024),
    ("grpc.max_send_message_length", 64 * 1024 * 1024),
]


def _build_payload(n: int) -> bytes:
    a = [(i % 7) * 0.13 for i in range(n * n)]
    b = [(i % 11) * 0.07 for i in range(n * n)]
    return bench_pb2.MatMulRequest(n=n, a=a, b=b).SerializeToString()


def _percentile(sorted_samples: List[float], q: float) -> float:
    if not sorted_samples:
        return 0.0
    idx = min(int(len(sorted_samples) * q), len(sorted_samples) - 1)
    return sorted_samples[idx]


def _latency_run(target: str, payload: bytes, samples: int, warmup: int) -> dict:
    with grpc.insecure_channel(target, options=_DEFAULT_OPTIONS) as channel:
        call = channel.unary_unary("/bench.BenchService/MatMul")
        for _ in range(warmup):
            call(payload)
        out = []
        for _ in range(samples):
            t0 = time.perf_counter()
            call(payload)
            out.append(time.perf_counter() - t0)
    out.sort()
    return {
        "n_samples": len(out),
        "mean_us": statistics.mean(out) * 1e6,
        "p50_us": _percentile(out, 0.50) * 1e6,
        "p90_us": _percentile(out, 0.90) * 1e6,
        "p99_us": _percentile(out, 0.99) * 1e6,
    }


def _throughput_run(target: str, payload: bytes, threads: int, duration_s: float) -> float:
    stop_at = time.perf_counter() + duration_s
    counts = [0] * threads

    def worker(idx: int):
        with grpc.insecure_channel(target, options=_DEFAULT_OPTIONS) as channel:
            call = channel.unary_unary("/bench.BenchService/MatMul")
            local = 0
            while time.perf_counter() < stop_at:
                call(payload)
                local += 1
            counts[idx] = local

    workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    start = time.perf_counter()
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    elapsed = time.perf_counter() - start
    return sum(counts) / elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="localhost:50051",
                        help="host:port of the BenchService server")
    parser.add_argument("--sizes", default="16,32,64,128",
                        help="comma-separated list of n for the n*n matmul")
    parser.add_argument("--samples", type=int, default=300,
                        help="latency samples per size (after warmup)")
    parser.add_argument("--warmup", type=int, default=20,
                        help="warmup calls per size before sampling")
    parser.add_argument("--threads", type=int, default=8,
                        help="client threads for the throughput run")
    parser.add_argument("--duration", type=float, default=2.0,
                        help="throughput run length in seconds per size")
    parser.add_argument("--no-throughput", action="store_true",
                        help="skip the multi-threaded throughput run")
    args = parser.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    print(f"target={args.target}")
    print(f"sizes={sizes}  samples={args.samples}  warmup={args.warmup}  "
          f"threads={args.threads}  duration={args.duration}s")
    print()
    header = f"{'n':>5} {'payload B':>10} {'mean μs':>11} {'p50 μs':>10} {'p99 μs':>10}"
    if not args.no_throughput:
        header += f" {'thr (rps)':>11}"
    print(header)
    print("-" * len(header))

    for n in sizes:
        payload = _build_payload(n)
        lat = _latency_run(args.target, payload, args.samples, args.warmup)
        row = (
            f"{n:>5} {len(payload):>10,} "
            f"{lat['mean_us']:>11,.1f} {lat['p50_us']:>10,.1f} {lat['p99_us']:>10,.1f}"
        )
        if not args.no_throughput:
            rps = _throughput_run(args.target, payload, args.threads, args.duration)
            row += f" {rps:>11,.0f}"
        print(row)


if __name__ == "__main__":
    main()
