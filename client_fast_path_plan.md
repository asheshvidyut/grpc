# Implementation Plan: Native Client Fast-Path (`grpcio_native_client`)

This document outlines the architecture and implementation plan to extend `grpcio_native` with client-side fast-path acceleration, bypassing the GIL and Python serialization overhead for outgoing RPCs.

---

## 1. Architectural Blueprint

On the client side, the primary bottlenecks are Python-side Protobuf serialization of outgoing requests and deserialization of incoming responses. To eliminate these, the client fast-path will bypass the Python interpreter entirely during the RPC invocation lifecycle.

```
                   [ Python Client Shell ]
                              │
            Expose raw c_channel pointer address
                              │
                              ▼
               [ Native Client Library (C++/Rust) ]
           (Acquires channel pointer, releases GIL)
                              │
           ┌──────────────────┴──────────────────┐
           ▼                                     ▼
[ Pack Request (C++) ]                 [ Invoke C-Core RPC ]
(Zero Python allocation)              (Direct grpc_channel_create_call)
           │                                     │
           └──────────────────┬──────────────────┘
                              ▼
                      [ Unpack Response ]
                      (C++ Proto parsing)
```

---

## 2. Phase 1: Core C-ABI Extension (`handler.h`)

Extend the C-ABI headers to define the native client invocation structure.

```c
/* include/grpcio_native/client.h */

#ifndef GRPCIO_NATIVE_CLIENT_H
#define GRPCIO_NATIVE_CLIENT_H

#include <stddef.h>
#include <stdint.h>
#include "handler.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Carry raw dynamic inputs and outputs for client invocation */
typedef struct {
  const char* method;
  const char* req_data;
  size_t req_len;
  
  /* Out fields allocated by dispatcher (or C-core) and freed by user */
  char* resp_data;
  size_t resp_len;
  
  grpc_native_status status;
  char* err_msg;
  size_t err_msg_len;
} grpc_native_client_call;

/* 
 * Signature of the C-core invocation function pointer provided by grpcio.
 * Invokes a direct C-core batch call on the raw C-channel pointer.
 */
typedef int (*grpcio_native_invoke_fn)(
    void* c_channel, 
    grpc_native_client_call* call, 
    int64_t timeout_ms
);

#ifdef __cplusplus
}
#endif

#endif /* GRPCIO_NATIVE_CLIENT_H */
```

---

## 3. Phase 2: C-Core Dynamic Invocation Bridge

Extract the raw C-core `grpc_channel` pointer from gRPC Python's internal Cython object and pass it to the native library.

### A. Expose C-Channel Pointer in Cython (`cygrpc.pyx`)
Inside `grpcio`'s `Channel` wrapper, expose the address of the internal `grpc_channel` pointer:
```python
cdef class Channel:
    # ... existing code ...
    @property
    def _c_channel_address(self) -> int:
        return <size_t>self.c_channel
```

### B. Implement Dynamic C-Core Invocation Helper
Inside `cygrpc`, implement a high-performance `invoke_native_client_call` function that accepts the `grpc_channel` address, releases the GIL, and performs a direct, low-level `grpc_call` batch operation:
```python
def invoke_native_client_call(size_t channel_addr, object client_call_addr, int64_t timeout_ms):
    cdef grpc_channel* c_channel = <grpc_channel*>channel_addr
    cdef grpc_native_client_call* call = <grpc_native_client_call*>client_call_addr
    
    with nogil:
        # Perform low-level grpc_channel_create_call and grpc_call_start_batch
        # ... low level C-core call loop ...
```

---

## 4. Phase 3: C++ Helper Library (`client.hpp`)

Provide a premium C++ wrapper on top of the low-level C client API to make writing native client scripts trivial.

```cpp
#include "grpcio_native/client.h"
#include <string>

namespace grpc {
namespace native {

template <typename Req, typename Resp>
class ClientStub {
 public:
  ClientStub(void* c_channel, grpcio_native_invoke_fn invoke_fn, std::string method)
      : c_channel_(c_channel), invoke_fn_(invoke_fn), method_(std::move(method)) {}

  Status Call(const Req& req, Resp* resp, int64_t timeout_ms = 5000) {
    std::string wire_req;
    if (!req.SerializeToString(&wire_req)) {
      return {GRPC_NATIVE_STATUS_INTERNAL, "Serialization failed"};
    }

    grpc_native_client_call call{};
    call.method = method_.c_str();
    call.req_data = wire_req.data();
    call.req_len = wire_req.size();

    int rc = invoke_fn_(c_channel_, &call, timeout_ms);
    if (rc != 0 || call.status != GRPC_NATIVE_STATUS_OK) {
      std::string err = call.err_msg ? call.err_msg : "Unknown error";
      if (call.err_msg) std::free(call.err_msg);
      return {call.status, err};
    }

    if (call.resp_data && call.resp_len > 0) {
      resp->ParseFromArray(call.resp_data, call.resp_len);
      std::free(call.resp_data);
    }

    return OK;
  }

 private:
  void* c_channel_;
  grpcio_native_invoke_fn invoke_fn_;
  std::string method_;
};

} // namespace native
} // namespace grpc
```

---

## 5. Phase 4: The JIT Client Developer Experience

Once completed, the developer experience for JIT compiling and running client-side handlers will look like this:

```python
import grpc
import grpcio_native

# 1. Create standard Python channel
channel = grpc.insecure_channel("localhost:50051")

# 2. JIT compile and load the native client wrapper
module = grpcio_native.compile_and_load_cpp(
    source_files=["client_logic.cc"],
    lib_name="client_fast_stub"
)

# 3. Bind the raw channel address and invoke GIL-free!
c_channel_addr = channel._channel.c_channel_address()
invoke_fn_addr = grpcio_native.get_c_core_invoke_fn_addr()

# Initialize C++ wrapper
fast_stub = module.init_client_stub(c_channel_addr, invoke_fn_addr)

# Invokes the entire serialization, transport, and deserialization loop 100% GIL-free in C++!
result = fast_stub.Predict(my_inputs)
```
