# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Benchmark grpcio-native against pure-Python handlers.

Compares two gRPC servers running the same workloads:

  * Hash:    FNV-1a 64-bit, configurable iteration count over a fixed payload.
             Stands in for per-byte CPU work.
  * MatMul:  n*n float matrix multiplication. Stands in for numerical compute
             (ranking, embedding ops, etc.). Python implementation deliberately
             uses nested loops, not numpy — we want to measure the cost of
             arbitrary Python compute, not a vectorized BLAS call.

Both handlers receive raw wire-format bytes (no protobuf overhead). What we
measure is the cost of running the handler itself.
"""

import os
import platform
import statistics
import struct
import sys
import threading
import time
from concurrent import futures

import grpc

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..")))

import grpcio_native  # noqa: E402

_LIB_NAME = (
    "echo_handler.dylib"
    if platform.system() == "Darwin"
    else "echo_handler.so"
)
_ECHO_LIB = os.path.abspath(
    os.path.join(__file__, "..", "..", "examples", "echo_c", _LIB_NAME)
)


# -- Python handler implementations -----------------------------------------

_FNV_OFFSET = 14695981039346656037
_FNV_PRIME = 1099511628211
_FNV_MASK = (1 << 64) - 1


def python_fnv1a_handler(request_bytes: bytes, context) -> bytes:
    if len(request_bytes) < 4:
        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
        return b""
    (iterations,) = struct.unpack_from("<I", request_bytes, 0)
    data = request_bytes[4:]
    h = _FNV_OFFSET
    for _ in range(iterations):
        for byte in data:
            h = ((h ^ byte) * _FNV_PRIME) & _FNV_MASK
    return struct.pack("<Q", h)


def python_matmul_handler(request_bytes: bytes, context) -> bytes:
    if len(request_bytes) < 4:
        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
        return b""
    (n,) = struct.unpack_from("<I", request_bytes, 0)
    mat_bytes = n * n * 4
    if len(request_bytes) != 4 + 2 * mat_bytes:
        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
        return b""
    a = struct.unpack_from(f"<{n*n}f", request_bytes, 4)
    b = struct.unpack_from(f"<{n*n}f", request_bytes, 4 + mat_bytes)
    c = [0.0] * (n * n)
    for i in range(n):
        for j in range(n):
            s = 0.0
            for k in range(n):
                s += a[i * n + k] * b[k * n + j]
            c[i * n + j] = s
    return struct.pack(f"<{n*n}f", *c)


def make_python_handler(behavior):
    from grpc import _utilities

    return _utilities.RpcMethodHandler(
        request_streaming=False,
        response_streaming=False,
        request_deserializer=None,
        response_serializer=None,
        unary_unary=behavior,
        unary_stream=None,
        stream_unary=None,
        stream_stream=None,
    )


# -- Server lifecycle -------------------------------------------------------


def start_server(handler_map, port=0, max_workers=8):
    generic_handler = grpc.method_handlers_generic_handler(
        "bench.Bench", handler_map
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    server.add_generic_rpc_handlers((generic_handler,))
    actual_port = server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server, actual_port


# -- Payload builders -------------------------------------------------------


def hash_payload(iterations: int, data_size: int) -> bytes:
    return struct.pack("<I", iterations) + bytes(
        (i & 0xFF) for i in range(data_size)
    )


def matmul_payload(n: int) -> bytes:
    a = [(i % 7) * 0.13 for i in range(n * n)]
    b = [(i % 11) * 0.07 for i in range(n * n)]
    return (
        struct.pack("<I", n)
        + struct.pack(f"<{n*n}f", *a)
        + struct.pack(f"<{n*n}f", *b)
    )


# -- Measurement primitives -------------------------------------------------


def measure_latency(target: str, method: str, payload: bytes, n: int = 500):
    with grpc.insecure_channel(target) as channel:
        call = channel.unary_unary(f"/bench.Bench/{method}")
        for _ in range(20):  # warm up
            call(payload)
        samples = []
        for _ in range(n):
            t0 = time.perf_counter()
            call(payload)
            samples.append(time.perf_counter() - t0)
    samples.sort()
    return {
        "p50": samples[len(samples) // 2] * 1e6,
        "p90": samples[int(len(samples) * 0.90)] * 1e6,
        "p99": samples[int(len(samples) * 0.99)] * 1e6,
        "mean": statistics.mean(samples) * 1e6,
    }


def measure_throughput(
    target: str,
    method: str,
    payload: bytes,
    threads: int = 8,
    duration_s: float = 3.0,
):
    stop_at = time.perf_counter() + duration_s
    counts = [0] * threads

    def worker(idx: int):
        with grpc.insecure_channel(target) as channel:
            call = channel.unary_unary(f"/bench.Bench/{method}")
            local = 0
            while time.perf_counter() < stop_at:
                call(payload)
                local += 1
            counts[idx] = local

    workers = [
        threading.Thread(target=worker, args=(i,)) for i in range(threads)
    ]
    start = time.perf_counter()
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    elapsed = time.perf_counter() - start
    return sum(counts) / elapsed


# -- Driver -----------------------------------------------------------------


def run_case(label, method, payload, py_port, nv_port, latency_n=500):
    print()
    print(f"=== {label} ===")
    py_lat = measure_latency(
        f"localhost:{py_port}", method, payload, n=latency_n
    )
    nv_lat = measure_latency(
        f"localhost:{nv_port}", method, payload, n=latency_n
    )
    print(f"{'metric':<8} {'python (μs)':>14} {'native (μs)':>14} {'speedup':>10}")
    for k in ("mean", "p50", "p90", "p99"):
        sp = py_lat[k] / nv_lat[k] if nv_lat[k] > 0 else float("inf")
        print(
            f"{k:<8} {py_lat[k]:>14,.1f} {nv_lat[k]:>14,.1f} {sp:>9.2f}x"
        )
    py_rps = measure_throughput(f"localhost:{py_port}", method, payload)
    nv_rps = measure_throughput(f"localhost:{nv_port}", method, payload)
    print(
        f"throughput (8 client threads): python {py_rps:>10,.0f}  "
        f"native {nv_rps:>10,.0f}  {nv_rps/py_rps:>5.2f}x"
    )


def main():
    if not os.path.isfile(_ECHO_LIB):
        sys.stderr.write(
            f"{_ECHO_LIB} not built; run `make` in examples/echo_c first.\n"
        )
        sys.exit(1)

    module = grpcio_native.load_native_module(_ECHO_LIB)
    native_server, native_port = start_server(
        {
            "Hash": grpcio_native.native_unary_unary_rpc_method_handler(
                module, "fnv1a_hash"
            ),
            "MatMul": grpcio_native.native_unary_unary_rpc_method_handler(
                module, "matmul"
            ),
        }
    )
    python_server, python_port = start_server(
        {
            "Hash": make_python_handler(python_fnv1a_handler),
            "MatMul": make_python_handler(python_matmul_handler),
        }
    )
    print(f"native: :{native_port}   python: :{python_port}")

    run_case(
        "Hash, 128B payload, 16 iterations (light)",
        "Hash",
        hash_payload(16, 128),
        python_port,
        native_port,
    )
    run_case(
        "Hash, 256B payload, 256 iterations (medium)",
        "Hash",
        hash_payload(256, 256),
        python_port,
        native_port,
    )
    run_case(
        "Hash, 1024B payload, 1024 iterations (heavy)",
        "Hash",
        hash_payload(1024, 1024),
        python_port,
        native_port,
        latency_n=100,
    )
    run_case(
        "MatMul 16x16",
        "MatMul",
        matmul_payload(16),
        python_port,
        native_port,
    )
    run_case(
        "MatMul 32x32 (compute heavy)",
        "MatMul",
        matmul_payload(32),
        python_port,
        native_port,
        latency_n=100,
    )
    run_case(
        "MatMul 64x64 (very heavy)",
        "MatMul",
        matmul_payload(64),
        python_port,
        native_port,
        latency_n=50,
    )

    native_server.stop(grace=0).wait()
    python_server.stop(grace=0).wait()


if __name__ == "__main__":
    main()
