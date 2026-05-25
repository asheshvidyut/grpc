# gRPC Native Echo Server (Pure C++ Flow)

This example demonstrates the high-performance **pure C++ flow** in `grpcio_native`.

Unlike the JIT Cython flow which JIT-compiles `.pyx` files at runtime, this flow allows you to:
1. Write your RPC handlers directly in standard, pure C++ (using standard protobuf libraries for parsing/serialization).
2. Compile the C++ code to a shared library (`.so`/`.dylib`) with standard linkage.
3. Register it with the Python gRPC server using `grpcio_native.load_native_module`.

The hot RPC paths are processed inside C++ without holding Python's GIL.

---

## Requirements

Ensure you have a C++17 compiler, `protoc`, and libprotobuf development headers installed.

---

## Build & Run the Server

To compile the C++ shared library, generate python stub files, and start the server:

```bash
python server.py --port 50099
```

---

## Run the Client

To run the client and send a request to the server:

```bash
python client.py --port 50099 --message "Hello World from gRPC Native C++ Flow"
```
