# End-to-End Flow: Math Service (Zero-GIL Handlers)

This example demonstrates the new end-to-end flow for generating, compiling, and running Cython-optimized gRPC handlers. 

Taking reference from the manual ABI bindings required in the previous architecture, this new flow completely eliminates manual `malloc`/`free` and struct-wiring by utilizing the `protoc` compiler.

## Quick Start: Run Benchmark End-to-End

From the repository root, run:

```bash
cd src/python/grpc_cython/examples/math && \
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. math.proto && \
python3 -m grpc_tools.protoc -I. --plugin=protoc-gen-cython=../../grpc_cython/plugin.py --cython_out=. math.proto && \
python3 setup.py build_ext --inplace && \
PYTHONPATH=../../:$PYTHONPATH python3 benchmark.py
```

---

## Step-by-Step Breakdown

### 1. Generate Standard and Cython Protobuf Bindings

Generate the standard Python stubs (needed for standard clients) and the zero-copy Cython `.pxd` / `.pyx` bindings:

```bash
# 1. Standard Python Protobuf stubs
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. math.proto

# 2. Cython zero-GIL bindings
python3 -m grpc_tools.protoc -I. \
    --plugin=protoc-gen-cython=../../grpc_cython/plugin.py \
    --cython_out=. \
    math.proto
```

This automatically generates `MathServiceBase` and the `add_MathServiceServicer_to_server` registration helper.

### 2. Compile the Extensions

Compile both the auto-generated boilerplate (`math_cython_pb2.pyx`) and your native business logic (`grpc_cython_server.pyx`) into shared libraries (`.so`):

```bash
python3 setup.py build_ext --inplace
```

### 3. Execution

Attach the `FastMathService` to your `grpc.Server` using the auto-generated registration function, exactly like standard gRPC:

```python
# Server Bootstrapping Example (grpc_cython_server.py)
import grpc
from concurrent import futures
import grpc_cython_server  # Your compiled grpc_cython_server.so
import math_cython_pb2

grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
math_cython_pb2.add_MathServiceServicer_to_server(grpc_cython_server.FastMathService(), grpc_server)
grpc_server.add_insecure_port("[::]:50051")
grpc_server.start()
grpc_server.wait_for_termination()
```

To run the standalone server:
```bash
PYTHONPATH=../../:$PYTHONPATH python3 grpc_cython_server.py
```

And in another terminal, run the client:
```bash
python3 client.py
```

