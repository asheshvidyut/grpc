# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# MatMul server benchmark client.
# Measures latency (mean, p50, p99) and multi-threaded throughput (QPS).

from __future__ import annotations

import argparse
import os
import sys
import time
import statistics
import threading
from typing import List

import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _GEN_DIR)

try:
    import matmul_pb2
    import matmul_pb2_grpc
except ImportError:
    sys.stderr.write(
        "matmul_pb2 not generated. Run the server first to compile the proto.\n"
    )
    sys.exit(1)


_DEFAULT_OPTIONS = [
    ("grpc.max_receive_message_length", 64 * 1024 * 1024),
    ("grpc.max_send_message_length", 64 * 1024 * 1024),
]


def _build_request(n: int) -> matmul_pb2.MatMulRequest:
    a = [(i % 7) * 0.13 for i in range(n * n)]
    b = [(i % 11) * 0.07 for i in range(n * n)]
    return matmul_pb2.MatMulRequest(n=n, a=a, b=b)


def _percentile(sorted_samples: List[float], q: float) -> float:
    if not sorted_samples:
        return 0.0
    idx = min(int(len(sorted_samples) * q), len(sorted_samples) - 1)
    return sorted_samples[idx]


def _latency_run(target: str, req: matmul_pb2.MatMulRequest, samples: int, warmup: int) -> dict:
    with grpc.insecure_channel(target, options=_DEFAULT_OPTIONS) as channel:
        stub = matmul_pb2_grpc.MatMulServiceStub(channel)
        
        # Warmup
        for _ in range(warmup):
            stub.MatMul(req)
            
        # Sampling
        out = []
        for _ in range(samples):
            t0 = time.perf_counter()
            stub.MatMul(req)
            out.append(time.perf_counter() - t0)
            
    out.sort()
    return {
        "n_samples": len(out),
        "mean_us": statistics.mean(out) * 1e6,
        "p50_us": _percentile(out, 0.50) * 1e6,
        "p90_us": _percentile(out, 0.90) * 1e6,
        "p99_us": _percentile(out, 0.99) * 1e6,
    }


def _throughput_run(target: str, req: matmul_pb2.MatMulRequest, threads: int, duration_s: float) -> float:
    stop_at = time.perf_counter() + duration_s
    counts = [0] * threads

    def worker(idx: int):
        with grpc.insecure_channel(target, options=_DEFAULT_OPTIONS) as channel:
            stub = matmul_pb2_grpc.MatMulServiceStub(channel)
            local = 0
            while time.perf_counter() < stop_at:
                stub.MatMul(req)
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
    parser.add_argument("--target", default="localhost:50089",
                        help="host:port of the MatMulService server")
    parser.add_argument("--sizes", default="16,32,64,128",
                        help="comma-separated list of square matrix sizes (N x N)")
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

    print(f"Benchmarking target: {args.target}")
    print(f"Config: samples={args.samples}, warmup={args.warmup}, threads={args.threads}, duration={args.duration}s")
    print()
    
    header = f"{'N (matrix)':>11} {'payload B':>12} {'mean μs':>12} {'p50 μs':>11} {'p99 μs':>11}"
    if not args.no_throughput:
        header += f" {'throughput (qps)':>18}"
    print(header)
    print("-" * len(header))

    for n in sizes:
        req = _build_request(n)
        size_bytes = req.ByteSize()
        lat = _latency_run(args.target, req, args.samples, args.warmup)
        row = (
            f"{f'{n}x{n}':>11} "
            f"{size_bytes:>12,} "
            f"{lat['mean_us']:>12,.1f} {lat['p50_us']:>11,.1f} {lat['p99_us']:>11,.1f}"
        )
        if not args.no_throughput:
            qps = _throughput_run(args.target, req, args.threads, args.duration)
            row += f" {qps:>18,.0f}"
        print(row)


if __name__ == "__main__":
    main()
