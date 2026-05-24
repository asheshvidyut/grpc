# bench_proto — three-way benchmark with realistic protobuf

This example exists to answer one question: **how much of the grpcio_native
win comes from "calling C" vs from "skipping Python protobuf and the GIL"?**

It runs three servers side by side over the *same* `.proto`:

| Variant | Servicer | Hot loop | Python protobuf parse/serialize | GIL released for handler body |
| ------- | -------- | -------- | ------------------------------- | ----------------------------- |
| `python` | Python class | Python | yes | no |
| `ctypes` | Python class | C via `ctypes` | yes | only for the `ctypes` call |
| `native` | grpcio_native handler | C | **no** | **yes (entire handler)** |

All three share the same compute kernel (FNV-1a hash, n*n matmul) compiled
into `bench_handler.{so,dylib}`. The `python` vs `ctypes` gap shows what a
DIY "just wrap C with ctypes" port buys you. The `ctypes` vs `native` gap
shows what grpcio_native adds on top.

## Build

Requires `protoc`, libprotobuf development headers, and a C++17 compiler.

On macOS:

```bash
brew install protobuf
```

Then:

```bash
make
```

This generates `bench.pb.{h,cc}` and `bench_pb2{,_grpc}.py` from `bench.proto`
and compiles `bench_handler.dylib` (or `.so` on Linux).

## Run

```bash
python benchmark.py
```

For each workload, the output is a table with mean / p50 / p99 latency and
throughput for all three variants, plus a one-line callout for `native vs
ctypes` — the gap that's specifically attributable to grpcio_native.

## Reading the output

- If `ctypes` is close to `python`, the workload is dominated by Python
  protobuf cost — the C kernel barely runs.
- If `ctypes` is between `python` and `native`, the kernel matters but
  framework overhead is also significant — the `native` column shows what
  removing the framework cost looks like.
- If `ctypes` is close to `native`, the workload is so trivial that
  framework overhead dominates. This is the "don't use grpcio_native here"
  signal (ctypes overhead ~5 μs/call, native ~3–5 μs better with the Cython
  fast path).

## What this benchmark does NOT measure

- **AIO server.** grpcio_native MVP is sync-only; the asyncio path is the
  one [grpc/grpc#39803](https://github.com/grpc/grpc/issues/39803) lives in.
- **Cross-machine network latency.** All traffic is over localhost. The
  framework / handler ratio shifts when network dominates.
- **Cold start / library load.** All three servers are warm before timing
  starts; the `ctypes.CDLL` load happens once.
- **Real production payloads.** The synthetic Hash and MatMul are CPU
  shapes, not your actual RPC. Substitute your own workload before making
  capacity decisions.
