# gRPC Cython

| \#begin-approvals-addon-section See [go/g3a-approvals](http://goto.google.com/g3a-approvals) for instructions on how to add reviewers. Do not edit this section manually. |
| :---: |

**Self link:** [go/grpc-py-zero-gil](http://goto.google.com/grpc-py-zero-gil), [go/grpc-cython](http://goto.google.com/grpc-cython)  
**Visibility**: Confidential*See [go/data-security-policy](https://goto.google.com/data-security-policy) for definitions if you want to change this.*  
**Status**: Review  
**Authors**: [Ashesh Vidyut](mailto:asheshvidyut@google.com)  
**Contributors**: [Ashesh Vidyut](mailto:asheshvidyut@google.com)  
**Last major revision**: May 25, 2026

---

# Context

This document proposes the design of grpcio-cython (Compute-Optimized Native Dispatch via Zero-GIL Handlers), an opt-in, hybrid execution framework allowing Python developers to write performance-critical RPC handlers in native Cython. These handlers execute entirely GIL-free, while keeping server life-cycle orchestration in high-level Python. By abstracting C++ Protobufs into zero-copy, NumPy-like Memoryviews, this framework brings the high-performance execution model of PyTorch and NumPy directly to gRPC network I/O.

# Objective

The goal of this proposal is to introduce a high-performance execution model for gRPC Python that eliminates Global Interpreter Lock (GIL) contention and Protobuf serialization bottlenecks for compute-heavy RPCs, without requiring a complete C++ server rewrite. We aim to:

* **Bypass the Python Interpreter:** Route raw HTTP/2 frame byte buffers directly from the gRPC Core layer into Cython/C++ business logic, completely avoiding Python object allocation on the hot path.  
* **Provide Zero-Friction Developer Ergonomics:** Use a standard protoc plugin to automatically generate zero-copy Cython wrappers (Memoryviews) so ML/Data developers can write NumPy-style math without touching raw C++ pointers.  
* **Unlock GIL-Free Concurrency:** Release the Python GIL during the entire request deserialization, execution, and response serialization pipeline to enable massive parallel scaling.  
* **Minimize Core Maintainer Burden:** Architect grpcio-cython as a standalone, opt-in package that hooks cleanly into standard grpc.Server APIs.

# Background

## The Event Loop Congestion Problem in grpc.aio

Standard gRPC Python AsyncIO (grpc.aio) servers manage concurrent requests on a single-threaded event loop. While this scales efficiently for I/O-bound services, it suffers from severe degradation when handling compute-bound tasks or large payloads. The "Python object tax"—parsing wire bytes into high-level Python objects—is the true bottleneck.



# Design: The Zero-Copy Architecture

The core philosophy is inspired by PyTorch and NumPy: developers write high-level logic using memory arrays, while the framework handles low-level C++ memory routing.

## The Data Lifecycle (Where Serialization Happens)

* **1\. Ingress (Raw Bytes):** HTTP/2 frame arrives; gRPC Core reads payload into C++ memory buffer. No GIL.  
* **2\. Deserialization (C++):** Routes byte pointer into C++ wrapper, calling libprotobuf's ParseFromArray. Zero Python objects allocated.  
* **3\. The Zero-Copy Bridge (Cython Memoryviews):** Exposes contiguous C++ memory pointer as a Cython Typed Memoryview (const float\[:\]).  
* **4\. Execution (Cython nogil):** User's business logic runs directly inside the C++ Protobuf arena memory space.  
* **5\. Serialization (C++):** Calls SerializeToArray on mutated C++ Protobuf object and hands bytes back to gRPC Core.

# Developer Experience (DevEx) & Integration

Instead of forcing developers to write manual C++ JIT bindings, grpcio-cython utilizes the standard protoc workflow. Developers use a custom plugin that generates Cython bindings (\_cython\_pb2.pxd), making native development feel exactly like standard gRPC.

**Step 1: Generate the Cython Bindings**

Developers run the standard protoc compiler with the new Cython plugin.

```shell
python -m grpc_tools.protoc -I. --cython_out=. math.proto
```

**Step 2: Write the Business Logic (handler.pyx)**

The developer subclasses the generated Cython base class. The framework automatically unwraps the Protobuf fields into safe, NumPy-style Memoryviews, hiding all C++ pointers.

```py
# distutils: language = c++
from math_cython_pb2 cimport MathServiceBase, MathRequest, MathResponse

cdef class FastMathService(MathServiceBase):
    # Executes entirely without the Python GIL!
    cdef int ComputeMatrix(self, MathRequest req, MathResponse resp) nogil:
        # The generated wrapper provides direct Memoryviews (zero-copy)
        cdef const float[:] a = req.matrix_a
        cdef const float[:] b = req.matrix_b
        cdef float[:] out = resp.result_matrix

        # Heavy math directly on C++ memory
        for i in range(a.shape[0]):
            out[i] = a[i] * b[i]
        return 0
```

**Step 3: Register in Python (server.py)**

Registration uses the exact same semantics as standard gRPC Python, ensuring zero friction for enterprise adoption.

```py
import grpc
import handler  # The compiled cython module
from math_cython_pb2 import add_MathServiceServicer_to_server

server = grpc.aio.server()
# Completely familiar API for gRPC users
add_MathServiceServicer_to_server(handler.FastMathService(), server)
server.add_insecure_port("[::]:50089")
server.start()
```

# Quality Attributes & Benchmarks

Benchmarks on CPU-bound Matrix Multiplication (MatMul) show that grpcio-cython scales linearly because the entire data plane remains in compiled C++, unlike ctypes delegation which collapses at scale due to Python-level deserialization.

# Expected Impact

## Benchmark Results

* ### Throughput (QPS / RPS)

| Matrix Size | Pure Python | Ctypes Delegation (Optimized) | `grpcio_cython`  |
| :---- | :---- | :---- | :---- |
| **16x16** | 358 QPS | 2,090 QPS | **2,325 QPS** |
| **32x32** | 53 QPS | 1,550 QPS | **2,298 QPS** |
| **64x64** | 7 QPS | 765 QPS | **2,221 QPS** |
| **128x128** | 1 QPS | 262 QPS | **883 QPS** |

* ### Mean Latency (μs)

| Matrix Size | Pure Python | Ctypes Delegation (Optimized) | `grpcio_cython`  |
| :---- | :---- | :---- | :---- |
| **16x16** | 3,197.5 μs | 804.4 μs | **849.6 μs** |
| **32x32** | 20,184.6 μs | 1,106.3 μs | **903.0 μs** |
| **64x64** | 145,944.3 μs | 1,889.0 μs | **1,063.9 μs** |
| **128x128** | 1,112,943.6 μs | 7,068.0 μs | **4,015.6 μs** |

* ### p99 Latency (μs)

| Matrix Size | Pure Python | Ctypes Delegation (Optimized) | JIT C++ (`grpcio_cython`)  |
| :---- | :---- | :---- | :---- |
| **16x16** | 6,498.3 μs | 1,376.7 μs | **1,496.0 μs** |
| **32x32** | 31,317.8 μs | 1,844.6 μs | **1,584.1 μs** |
| **64x64** | 157,412.4 μs | 2,440.3 μs | **1,512.9 μs** |
| **128x128** | 1,127,750.7 μs | 8,579.7 μs | **4,653.5 μs** |

# Internals

1. **The Standard gRPC Behavior (What normally happens)**  
2. In standard gRPC Python, the generated add\_\*\_to\_server function registers your service by creating a dictionary of method handlers. It binds your Python function to the RPC method name, and crucially, it attaches the Python Protobuf deserializers:

```py
# Standard gRPC behavior (Slow)
"ComputeMatrix": grpc.unary_unary_rpc_method_handler(
    servicer.ComputeMatrix,
    request_deserializer=MathRequest.FromString, # <-- GIL LOCKED HERE
    response_serializer=MathResponse.SerializeToString, # <-- GIL LOCKED HERE
)
```

3. **The Cython Generated Behavior (What your framework does)**  
4. Your custom protoc plugin generates a completely different add\_MathServiceServicer\_to\_server function. Instead of registering Python deserializers, it registers a special Native Method Handler provided by your grpcio\_cython core library.  
5. Here is what the generated code inside math\_cython\_pb2.py will actually look like:

```py
2# math_cython_pb2.py (Generated by your protoc plugin)
import grpc
import grpcio_cython

def add_MathServiceServicer_to_server(servicer, server):
    # 1. Map the RPC method to the native Cython method
    rpc_method_handlers = {
        "ComputeMatrix": grpcio_cython.native_unary_unary_rpc_method_handler(
            servicer_instance=servicer,
            method_name="ComputeMatrix"
        )
    }
    # 2. Create the Generic Handler exactly like standard gRPC
    generic_handler = grpc.method_handlers_generic_handler(
        "mypackage.MathService", rpc_method_handlers
    )
    # 3. Attach it to the standard python grpc.Server
    server.add_generic_rpc_handlers((generic_handler,))
```

**3\. What native\_unary\_unary\_rpc\_method\_handler actually does**

* When the server receives an RPC call for "ComputeMatrix", standard gRPC routes it to `native_unary_unary_rpc_method_handler`. At initialization and runtime, it performs the following critical steps:  
* **Initialization (Symbol Resolution):** During registration, it extracts the `_native_module` from the `servicer_instance`. It then maps the Python `method_name` (`"ComputeMatrix"`) to the exported C-linkage symbol inside the compiled Cython shared library and extracts the raw C function pointer.  
* **Bypasses Python Deserialization:** It returns a standard `grpc.RpcMethodHandler` configured with `request_deserializer=None` and `response_serializer=None`. This tells the standard gRPC layer to completely skip Python protobuf deserialization, passing raw wire bytes directly from the socket buffer to the native handler.  
* **Execution & Context Switching (Releasing the GIL):** Upon receiving a request, the handler invokes the resolved C function pointer natively via `ctypes`. Because it's calling a native C function, Python automatically **drops the GIL**.  
* **Cython Execution:** Control transfers entirely to the C++ wrapper generated by Cython, which calls `ParseFromArray` using the native C++ Protobuf library, populates zero-copy memoryviews, runs your math loop, and serializes the response back to bytes natively.  
* **Returning to Python:** Once the C function returns, the GIL is re-acquired just long enough to hand the raw output bytes back to standard `grpc` for network transmission. The `grpc.aio` event loop remains unblocked during the entire native execution phase.

# Client Fast-Path (Cython Channels)

In addition to server-side optimization, `grpcio-cython` also exposes the raw C-Core `grpc_channel` invocation sequence for building high-performance native clients. This allows users to write handlers in Cython to serialize requests natively and push them directly to the transport layer without contending for the Python GIL or blocking the AsyncIO event loop.

1. **Exposing the C-Core Invoke Function:** 
   The framework provides `grpcio_cython.get_c_core_invoke_fn_addr()`, which retrieves the raw memory address of the Cython C-Core execution function (via `cygrpc.get_c_core_invoke_fn_addr()`).

2. **The Client Fast-Path ABI:**
   Native Cython extensions can cast this integer pointer into the `grpcio_cython_invoke_fn` C signature and pass a constructed `grpc_native_client_call` struct (defined in `grpcio_native/handler.h`). This struct contains the raw serialized bytes, the target method name, and the channel reference.

3. **GIL-Free Client Execution:**
   By pushing data directly into the C-Core using the Cython handler, standard client-side bottlenecks (e.g. creating Python `Operation` batches like `SendMessageOperation` and waiting on thread pools) are completely bypassed. Data goes straight from Cython to the transport queue, yielding massive throughput improvements for compute-heavy clients.

### 4. Zero-Friction Auto-Generation (`protoc --cython_out`)

Writing manual C ABI boilerplate is prone to error. Instead, `grpcio-cython` extends the `protoc` compiler to automatically generate both the **Client Stubs** and **Server Bases** in a single `_cython_pb2.pyx` file. 

By running:
```shell
python -m grpc_tools.protoc -I. --cython_out=. math.proto
```
The generator produces the Cython structures that hide all `malloc`/`free` operations, struct instantiation, and ABI function pointers under the hood:

**The Generated `math_cython_pb2.pyx` Structure:**
```cython
# Auto-generated by protoc --cython_out
cdef class MathServiceBase:
    # Server-side base class to be implemented by users
    cdef int ComputeMatrix(self, MathRequest req, MathResponse resp) nogil:
        pass

cdef class MathServiceFastStub:
    # Auto-wires the client C-Core invoke pointers & serialization
    def __init__(self, channel):
        self._c_chan = <void*>channel._channel
        self._invoke_fn = get_c_core_invoke_fn_addr()
        
    def ComputeMatrix(self, float[:] a, float[:] b):
        # 1. Allocates C++ Request & copies Memoryviews
        # 2. Safely drops GIL, invokes C-Core transport directly
        # 3. Parses C++ Response and returns output
```

**The Clean User API (Client & Server):**

Developers only write pure business logic.

**Server Side (Cython):**
```cython
# user_server.pyx
from math_cython_pb2 cimport MathServiceBase, MathRequest, MathResponse

cdef class FastMathService(MathServiceBase):
    cdef int ComputeMatrix(self, MathRequest req, MathResponse resp) nogil:
        # Business logic strictly in C++ Memoryviews (Zero GIL)
        cdef const float[:] a = req.matrix_a
        cdef const float[:] b = req.matrix_b
        # ... math operations ...
        return 0
```

**Client Side (Python):**
```python
# user_client.py
import grpc
import math_cython_pb2

channel = grpc.insecure_channel('localhost:50051')

# The Fast Stub handles all native dispatch automatically
client = math_cython_pb2.MathServiceFastStub(channel)

# Dispatch natively without freezing the asyncio event loop!
response = client.ComputeMatrix(matrix_a, matrix_b)
```