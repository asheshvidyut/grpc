# grpcio_native

Register native (C/C++) RPC handlers with a gRPC Python server. Hot RPCs run
in compiled code without holding the GIL; everything else (server lifecycle,
non-hot methods, interceptors) stays in Python.

This is an MVP — see [Status](#status) for what's supported.

## Why

A no-op gRPC Python handler costs ~60–100 μs round-trip; almost none of that
is your code. The cost breakdown per request:

  - GIL acquire/release on the polling thread
  - Allocate a Python `bytes` object for the request
  - Parse the request via the Python protobuf module (often the slowest step)
  - Thread-pool hand-off
  - Run handler logic
  - Serialize the response via Python protobuf
  - GIL release back to the polling thread

A native handler skips all of the above except the polling thread and the
thread-pool hand-off. The handler sees the wire-format bytes directly, parses
with `libprotobuf` (or anything else), runs business logic, and returns the
wire-format response — all with the GIL released.

## Benchmark (Apple M1, single process, 8 client threads)

Same workloads implemented in both Python and C, served by `grpc.server`
with no other modifications. Reproduce with `python tests/benchmark.py`
after `make` in `examples/echo_c`.

### Hash (FNV-1a 64-bit, iterated; represents per-byte CPU work)

| Workload                       | Latency p50 speedup | Throughput speedup |
| ------------------------------ | ------------------- | ------------------ |
| 128 B × 16 iters (light)       | 1.8×                | 2.0×               |
| 256 B × 256 iters (medium)     | 17×                 | 22×                |
| 1024 B × 1024 iters (heavy)    | **40×**             | **187×**           |

### MatMul n×n float32 (represents numerical / ranking compute)

| Workload         | Latency p50 speedup | Throughput speedup |
| ---------------- | ------------------- | ------------------ |
| 16 × 16          | 2.3×                | 2.4×               |
| 32 × 32          | 10×                 | 13×                |
| 64 × 64 (heavy)  | **39×**             | **87×**            |

The 100×+ throughput numbers on heavy workloads are mostly the GIL — Python
gets stuck at one effective core under contention; the native handler scales
across all of them. p99 speedups are even larger because Python's tail
balloons under load.

**Trivial handlers (e.g., echo 4 bytes) don't benefit** — ctypes overhead
(~5μs/call) exceeds the savings. Native pays off when the handler does
non-trivial work. If you're framework-bottlenecked, not handler-bottlenecked,
no improvement here will help.

## Quick start

```bash
# Build the example C handler.
cd examples/echo_c
make

# In another terminal:
python echo_server.py

# In another terminal:
python echo_client.py
```

## Writing a native handler

### C++ (recommended): use the helper macros

Include `grpcio_native/handler.hpp` and use one macro per RPC type. The
macro generates the C ABI entry point; you write only typed business logic.

```cpp
#include "grpcio_native/handler.hpp"
#include "ranker.pb.h"

GRPCIO_NATIVE_DECLARE_ABI()

GRPCIO_NATIVE_UNARY(Rank, my_service::RankRequest, my_service::RankResponse) {
  // `req` is const RankRequest&; `resp` is RankResponse*.
  if (req.top_k() <= 0) {
    return grpc::native::InvalidArgument("top_k must be positive");
  }
  // ... ranking logic, all GIL-free ...
  resp->add_ids(42);
  return grpc::native::OK;
}
```

All four RPC types follow the same pattern:

```cpp
GRPCIO_NATIVE_UNARY        (name, ReqT, RespT) { /* req, resp        */ }
GRPCIO_NATIVE_UNARY_STREAM (name, ReqT, RespT) { /* req, writer      */ }
GRPCIO_NATIVE_STREAM_UNARY (name, ReqT, RespT) { /* reader, resp     */ }
GRPCIO_NATIVE_STREAM_STREAM(name, ReqT, RespT) { /* reader, writer   */ }
```

Inside streaming bodies, use `reader.Read(&msg)` / `writer.Write(msg)` — both
parse/serialize the protobuf for you.

### Raw C ABI: for non-C++ languages

If you're writing in plain C or another language that can produce a shared
library with C-linkage exports, include `grpcio_native/handler.h`
and target the raw struct-based ABI. The C++ macros expand to exactly this
shape — see [include/grpcio_native/handler.h](include/grpcio_native/handler.h):

```c
#include "grpcio_native/handler.h"

GRPCIO_NATIVE_DECLARE_ABI()

GRPCIO_NATIVE_HANDLER int my_handler(grpc_native_unary_call* call) {
  // call->req_data / req_len: request wire bytes
  // Allocate response with malloc(); dispatcher will free() after sending.
  call->resp_data = malloc(call->req_len);
  memcpy(call->resp_data, call->req_data, call->req_len);
  call->resp_len = call->req_len;
  return 0;
}
```

Compile to a shared library, then in Python:

```python
import grpc
from concurrent import futures
import grpcio_native

module = grpcio_native.load_native_module("./my_handler.so")
handler = grpcio_native.native_unary_unary_rpc_method_handler(
    module, "my_handler"
)

server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
server.add_generic_rpc_handlers((
    grpc.method_handlers_generic_handler(
        "my.Service", {"MyMethod": handler}
    ),
))
server.add_insecure_port("[::]:50051")
server.start()
server.wait_for_termination()
```

## Examples

### `examples/echo_c/` — bytes-in, bytes-out

Pure C, no protobuf. Three handlers: echo, double-uint32, always-not-found.
Builds with `make`. Demonstrates the raw ABI and that you don't *need*
protobuf for a native handler.

### `examples/echo_pybind11/` — protobuf-aware

C++ handler using `libprotobuf` for parse/serialize. Builds with CMake.
Demonstrates the production shape: real proto messages, generated C++ code,
business logic in idiomatic C++.

> Despite the directory name, the example uses no pybind11. The plain C ABI
> is sufficient — pybind11 only matters if your handler needs Python
> callbacks, which the MVP doesn't expose.

## ABI

The C ABI is in `include/grpcio_native/handler.h`, currently version 2.
Stability rules:

  - `GRPCIO_NATIVE_ABI_VERSION` is bumped on incompatible changes.
  - Every handler library must export `grpcio_native_abi_version()`; the
    loader fails fast on mismatch. The `GRPCIO_NATIVE_DECLARE_ABI()` macro
    emits it.
  - Memory ownership: dispatcher owns request bytes; handler `malloc()`s
    response/error buffers; dispatcher `free()`s them after transmission.
  - On non-glibc platforms (Windows, musl), `free()` may not match the
    `malloc()` the handler used. We currently load `libc` via `CDLL(None)`
    which works on macOS and glibc. A future revision will let handlers
    register a custom free function.

## Architecture

```
                       +---------------------------+
   client RPC -------> | grpc C-core (Cython glue) |
                       +-----------+---------------+
                                   |
                                   v
                       +---------------------------+
                       |  grpc._server dispatcher  |
                       +-----------+---------------+
                                   |
                request_deserializer is None: bytes pass through
                                   |
                                   v
                       +---------------------------+
                       | NativeUnaryUnaryBehavior  |   <-- grpcio_native
                       +-----------+---------------+
                                   |
                  ctypes call (releases GIL)
                                   |
                                   v
                       +---------------------------+
                       |  user's .so handler fn    |   <-- user code (C/C++)
                       +---------------------------+
```

The key design choice: native handlers slot into the existing
`RpcMethodHandler` interface as ordinary `unary_unary` callables, with
`request_deserializer=None` / `response_serializer=None` to pass raw wire
bytes through. No changes required to `grpc._server` or to `cygrpc`.

### Optional Cython fast path

When grpcio is built with the `native_dispatch.pyx.pxi` included in this
branch, `grpcio_native` automatically uses a Cython entry point that skips
ctypes argument marshaling — direct C function pointer call from Cython with
`nogil`. The pure-ctypes path remains as a fallback for users on a stock
grpcio wheel.

The Cython fast path saves ~3–5 μs per call (the ctypes argument-conversion
overhead). It's most visible in throughput benchmarks.

## All four RPC types are supported

| RPC type        | C signature                                           | Tested |
| --------------- | ----------------------------------------------------- | ------ |
| Unary-unary     | `int fn(grpc_native_unary_call*)`                     | ✅      |
| Unary-stream    | `int fn(grpc_native_unary_stream_call*)`              | ✅      |
| Stream-unary    | `int fn(grpc_native_stream_unary_call*)`              | ✅      |
| Stream-stream   | `int fn(grpc_native_stream_stream_call*)`             | ✅      |

Stream-input handlers receive a `grpc_native_reader*` and pull messages by
calling `reader->read(reader->ctx, &out_data, &out_len)`. Stream-output
handlers receive a `grpc_native_writer*` and emit messages by calling
`writer->emit(writer->ctx, data, len)`. Bidi handlers get both — reads and
writes can interleave freely (the Python side runs the C handler on a
dedicated worker thread).

### Streaming example (stream-stream)

```cpp
GRPCIO_NATIVE_STREAM_STREAM(RunningSum, NumberIn, NumberOut) {
  uint64_t sum = 0;
  NumberIn in;
  while (reader.Read(&in)) {
    sum += in.value();
    NumberOut out;
    out.set_total(sum);
    if (!writer.Write(out)) break;  // peer closed
  }
  return grpc::native::OK;
}
```

```python
handler = grpcio_native.native_stream_stream_rpc_method_handler(
    module, "RunningSum"
)
```

## What's not in the MVP

| Feature                    | Status                                  |
| -------------------------- | --------------------------------------- |
| All 4 RPC types            | ✅ Working, tested end-to-end           |
| `grpc.aio` (async server)  | ❌ Not implemented                      |
| Cancellation propagation   | ⚠️  Reader/writer surface it as rc<0; explicit cancel hook missing |
| Metadata access            | ❌ Not surfaced to native handlers      |
| Interceptors               | ⚠️  Python interceptors still run; native handlers can't add new interceptors |
| Cython fast path (streams) | ❌ Only unary-unary has the Cython glue |
| Windows                    | ⚠️  Builds, but malloc/free ABI needs work |

The MVP is built to validate the approach and demonstrate the performance
win. Production use requires the missing pieces above.

## Testing

```bash
cd examples/echo_c && make
cd ../..
python -m unittest tests.test_native_handler -v
python tests/benchmark.py
```

## Status

Experimental. The C ABI may change before any "1.0" release; bump
`GRPCIO_NATIVE_ABI_VERSION` and the loader catches incompatibilities at load
time.
