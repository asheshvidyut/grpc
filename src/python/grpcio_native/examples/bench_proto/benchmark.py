# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Three-way benchmark: pure Python vs naive ctypes vs grpcio_native.

All three servers expose the same proto-defined RPCs (Hash, MatMul) and are
driven by the same client. The differences:

  A) Pure Python: standard servicer; framework deserializes request to a
     Python proto, handler runs in Python, framework serializes response.

  B) Naive ctypes: same servicer shape; framework still deserializes request
     to a Python proto, handler reads the parsed fields and invokes the same
     compute kernel from bench_handler.{so,dylib} via ctypes for the heavy
     loop only, then builds a Python proto response.

  C) grpcio_native: handler registered with request_deserializer=None /
     response_serializer=None; raw wire bytes pass through to the native
     handler, which parses with libprotobuf, runs the kernel, and serializes
     back to wire bytes with the GIL released for the entire call.

The output table shows where each layer's cost goes. The (B) vs (C) gap is
specifically the framework / Python-protobuf cost that grpcio_native removes
on top of what a naive "just call C" port would already achieve.
"""

from __future__ import annotations

import ctypes
import os
import platform
import statistics
import sys
import threading
import time
from concurrent import futures
from typing import Callable

import grpc

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))
sys.path.insert(0, _HERE)

import grpcio_native  # noqa: E402

try:
    import bench_pb2  # noqa: E402
    import bench_pb2_grpc  # noqa: E402
except ImportError:
    sys.stderr.write(
        "bench_pb2 not generated. Run `make` in this directory first.\n"
    )
    sys.exit(1)


_LIB_NAME = (
    "bench_handler.dylib"
    if platform.system() == "Darwin"
    else "bench_handler.so"
)
_LIB_PATH = os.path.join(_HERE, _LIB_NAME)

if not os.path.isfile(_LIB_PATH):
    sys.stderr.write(
        f"{_LIB_PATH} not built. Run `make` in this directory first.\n"
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# ctypes bindings to the raw kernels used by the "naive ctypes" servicer.
# ---------------------------------------------------------------------------

_lib = ctypes.CDLL(_LIB_PATH)
_lib.fnv1a_hash_raw.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint32]
_lib.fnv1a_hash_raw.restype = ctypes.c_uint64
_lib.matmul_raw.argtypes = [
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_float),
    ctypes.c_uint32,
]
_lib.matmul_raw.restype = None


# ---------------------------------------------------------------------------
# Variant A: pure Python.
# ---------------------------------------------------------------------------

_FNV_OFFSET = 14695981039346656037
_FNV_PRIME = 1099511628211
_FNV_MASK = (1 << 64) - 1


def _fnv1a_python(data: bytes, iterations: int) -> int:
    h = _FNV_OFFSET
    for _ in range(iterations):
        local = h
        for byte in data:
            local = ((local ^ byte) * _FNV_PRIME) & _FNV_MASK
        h = local
    return h


class PurePythonServicer(bench_pb2_grpc.BenchServiceServicer):
    def Hash(self, request, context):
        h = _fnv1a_python(request.data, request.iterations)
        return bench_pb2.HashResponse(hash=h)

    def MatMul(self, request, context):
        n = request.n
        a = list(request.a)
        b = list(request.b)
        c = [0.0] * (n * n)
        for i in range(n):
            for j in range(n):
                s = 0.0
                for k in range(n):
                    s += a[i * n + k] * b[k * n + j]
                c[i * n + j] = s
        return bench_pb2.MatMulResponse(c=c)


# ---------------------------------------------------------------------------
# Variant B: naive ctypes — Python protobuf in, C kernel for the hot loop,
# Python protobuf out. Represents the "just write a Python servicer that
# calls into a .so via ctypes" approach.
# ---------------------------------------------------------------------------


class NaiveCtypesServicer(bench_pb2_grpc.BenchServiceServicer):
    def Hash(self, request, context):
        h = _lib.fnv1a_hash_raw(
            request.data, len(request.data), request.iterations
        )
        return bench_pb2.HashResponse(hash=h)

    def MatMul(self, request, context):
        n = request.n
        size = n * n
        a_arr = (ctypes.c_float * size)(*request.a)
        b_arr = (ctypes.c_float * size)(*request.b)
        c_arr = (ctypes.c_float * size)()
        _lib.matmul_raw(a_arr, b_arr, c_arr, n)
        return bench_pb2.MatMulResponse(c=list(c_arr))


# ---------------------------------------------------------------------------
# Variant C: grpcio_native — native handler registered directly.
# ---------------------------------------------------------------------------


def _make_native_handlers():
    module = grpcio_native.load_native_module(_LIB_PATH)
    return grpc.method_handlers_generic_handler(
        "bench.BenchService",
        {
            "Hash": grpcio_native.native_unary_unary_rpc_method_handler(
                module, "fnv1a_hash"
            ),
            "MatMul": grpcio_native.native_unary_unary_rpc_method_handler(
                module, "matmul_handler"
            ),
        },
    )


# ---------------------------------------------------------------------------
# Server lifecycle.
# ---------------------------------------------------------------------------


_DEFAULT_OPTIONS = [
    ("grpc.max_receive_message_length", 64 * 1024 * 1024),
    ("grpc.max_send_message_length", 64 * 1024 * 1024),
]


def _start(name: str, register_fn: Callable[[grpc.Server], None]) -> tuple:
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=8),
        options=_DEFAULT_OPTIONS,
    )
    register_fn(server)
    port = server.add_insecure_port("[::]:0")
    server.start()
    return name, server, port


def start_all() -> dict:
    servers = {}

    def reg_python(s):
        bench_pb2_grpc.add_BenchServiceServicer_to_server(
            PurePythonServicer(), s
        )

    def reg_naive(s):
        bench_pb2_grpc.add_BenchServiceServicer_to_server(
            NaiveCtypesServicer(), s
        )

    def reg_native(s):
        s.add_generic_rpc_handlers((_make_native_handlers(),))

    for name, fn in (
        ("python", reg_python),
        ("ctypes", reg_naive),
        ("native", reg_native),
    ):
        n, srv, port = _start(name, fn)
        servers[n] = (srv, port)
    return servers


# ---------------------------------------------------------------------------
# Client driver. We send pre-serialized request bytes via a low-level
# unary_unary so the client cost is identical for every variant; the server
# side still sees its registered (de)serializer (or lack of it, for native).
# ---------------------------------------------------------------------------


def _serialize_hash(data: bytes, iterations: int) -> bytes:
    return bench_pb2.HashRequest(data=data, iterations=iterations).SerializeToString()


def _serialize_matmul(n: int) -> bytes:
    a = [(i % 7) * 0.13 for i in range(n * n)]
    b = [(i % 11) * 0.07 for i in range(n * n)]
    return bench_pb2.MatMulRequest(n=n, a=a, b=b).SerializeToString()


def _measure_latency(
    target: str, method: str, payload: bytes, n: int
) -> dict:
    with grpc.insecure_channel(target, options=_DEFAULT_OPTIONS) as channel:
        call = channel.unary_unary(f"/bench.BenchService/{method}")
        for _ in range(20):  # warmup
            call(payload)
        samples = []
        for _ in range(n):
            t0 = time.perf_counter()
            call(payload)
            samples.append(time.perf_counter() - t0)
    samples.sort()
    return {
        "mean": statistics.mean(samples) * 1e6,
        "p50": samples[len(samples) // 2] * 1e6,
        "p90": samples[int(len(samples) * 0.90)] * 1e6,
        "p99": samples[int(len(samples) * 0.99)] * 1e6,
    }


def _measure_throughput(
    target: str,
    method: str,
    payload: bytes,
    threads: int,
    duration_s: float,
) -> float:
    stop_at = time.perf_counter() + duration_s
    counts = [0] * threads

    def worker(idx: int):
        with grpc.insecure_channel(target, options=_DEFAULT_OPTIONS) as channel:
            call = channel.unary_unary(f"/bench.BenchService/{method}")
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


# ---------------------------------------------------------------------------
# Output.
# ---------------------------------------------------------------------------


def _print_table(label: str, servers: dict, method: str, payload: bytes,
                 latency_n: int, threads: int, duration_s: float):
    print()
    print(f"=== {label} ===")
    rows = {}
    for name, (_srv, port) in servers.items():
        lat = _measure_latency(f"localhost:{port}", method, payload, n=latency_n)
        rps = _measure_throughput(
            f"localhost:{port}", method, payload, threads, duration_s
        )
        rows[name] = (lat, rps)

    py_mean = rows["python"][0]["mean"]
    py_p99 = rows["python"][0]["p99"]
    py_rps = rows["python"][1]

    print(
        f"{'variant':<10} {'mean μs':>10} {'p50 μs':>10} {'p99 μs':>10} "
        f"{'thr (rps)':>11} {'vs python':>10}"
    )
    for name in ("python", "ctypes", "native"):
        lat, rps = rows[name]
        sp_lat = py_mean / lat["mean"] if lat["mean"] > 0 else float("inf")
        sp_rps = rps / py_rps if py_rps > 0 else float("inf")
        speed = f"{sp_lat:.1f}× lat, {sp_rps:.1f}× thr"
        print(
            f"{name:<10} {lat['mean']:>10,.1f} {lat['p50']:>10,.1f} "
            f"{lat['p99']:>10,.1f} {rps:>11,.0f}  {speed:>10}"
        )

    ctypes_mean = rows["ctypes"][0]["mean"]
    native_mean = rows["native"][0]["mean"]
    ctypes_rps = rows["ctypes"][1]
    native_rps = rows["native"][1]
    print(
        f"  native vs ctypes: latency {ctypes_mean/native_mean:.2f}×, "
        f"throughput {native_rps/ctypes_rps:.2f}×  "
        f"  (this is the grpcio_native value over a DIY ctypes port)"
    )


# ---------------------------------------------------------------------------
# Driver.
# ---------------------------------------------------------------------------


def main():
    print(f"loaded {_LIB_PATH}")
    print("starting three servers...")
    servers = start_all()
    for name, (_srv, port) in servers.items():
        print(f"  {name:<8} :{port}")

    workloads = [
        ("Hash light (data=128B, iters=16)",   "Hash",   _serialize_hash(bytes(range(128)) * 1, 16),   500, 8, 2.0),
        ("Hash medium (data=256B, iters=256)", "Hash",   _serialize_hash(bytes((i & 0xFF for i in range(256))), 256), 300, 8, 2.0),
        ("Hash heavy (data=1024B, iters=512)", "Hash",   _serialize_hash(bytes((i & 0xFF for i in range(1024))), 512), 100, 8, 2.0),
        ("MatMul 16x16",                       "MatMul", _serialize_matmul(16),                          300, 8, 2.0),
        ("MatMul 32x32",                       "MatMul", _serialize_matmul(32),                          100, 8, 2.0),
        ("MatMul 64x64 (heavy)",               "MatMul", _serialize_matmul(64),                           50, 8, 2.0),
    ]

    try:
        for label, method, payload, lat_n, threads, dur in workloads:
            _print_table(label, servers, method, payload, lat_n, threads, dur)
    finally:
        for _name, (srv, _port) in servers.items():
            srv.stop(grace=0).wait()


if __name__ == "__main__":
    main()
