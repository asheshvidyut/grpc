# End-to-End Flow: Math Service (Zero-GIL Handlers)

This example demonstrates the new end-to-end flow for generating, compiling, and running Cython-optimized gRPC handlers. 

Taking reference from the manual ABI bindings required in the previous architecture, this new flow completely eliminates manual `malloc`/`free` and struct-wiring by utilizing the `protoc` compiler.

## 1. Generate the Cython Bindings
Generate the `_cython_pb2.pyx` and `.pxd` bindings from your `.proto` file using the custom plugin:

```bash
python3 -m grpc_tools.protoc -I. \
    --plugin=protoc-gen-cython=../../grpc_cython/plugin.py \
    --cython_out=. \
    math.proto
```

This automatically generates the `MathServiceFastStub` and `MathServiceBase`.

## 2. Compile the Extensions
Compile both the auto-generated boilerplate (`math_cython_pb2.pyx`) and your native business logic (`server.pyx`) into shared libraries (`.so`):

```bash
python3 setup.py build_ext --inplace
```

## 3. Execution
In a production application, you would attach the `FastMathService` to your `grpc.Server` using the auto-generated registration function, exactly like standard gRPC:

```python
# Server Bootstrapping Example
import grpc
from concurrent import futures
import server  # Your compiled server.so
import math_cython_pb2

grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
math_cython_pb2.add_MathServiceServicer_to_server(server.FastMathService(), grpc_server)
grpc_server.add_insecure_port("[::]:50051")
grpc_server.start()
grpc_server.wait_for_termination()
```

Then, you simply execute your client to dispatch the NumPy arrays seamlessly across the network:
```bash
python3 client.py
```
