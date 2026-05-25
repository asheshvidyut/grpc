# Unified gRPC MatMul Server: Pure Python, ctypes, and JIT C++

This unified example demonstrates and compares three distinct approaches to building gRPC servers in Python using a heavy CPU-bound **Matrix Multiplication (MatMul)** workload:

1. **Pure Python (`--pure-python`):** Standard Python servicer doing matrix math in pure Python.
2. **Ctypes Delegation (`--ctypes`):** Standard Python servicer that delegates the heavy `O(N^3)` matrix multiplication to a fast C library (`matmul_handler.so`) via Python's built-in `ctypes`.
3. **Native JIT (`--jit` / default):** High-performance, zero-copy native JIT-compiled Cython/C++ handler using `grpcio_native` where both the matrix multiplication and the Protobuf serialization/deserialization are executed entirely in C++.

All three modes automatically support **gRPC Server Reflection**, allowing you to query schemas dynamically with tools like `grpcurl` on port `50089`.

---

## Requirements

Install the required packages:
```bash
pip install grpcio-tools grpcio-reflection
```

---

## Running the Server

Start the server in any of the three modes:

### Mode 1: Native JIT C++ (Default)
```bash
python server.py
```

### Mode 2: Ctypes Delegation
```bash
python server.py --ctypes
```

### Mode 3: Pure Python
```bash
python server.py --pure-python
```

---

## Verifying the Server
In a separate terminal, run the verification client to ensure all three backends calculate the matrix math correctly:

```bash
python client.py
```

---

## Measuring and Comparing Performance

A unified benchmark client is provided to measure and compare the latency and throughput (QPS) of the three modes for various square matrix sizes (e.g., `16x16`, `32x32`, `64x64`, `128x128`).

Ensure your server is running in the desired mode, then execute the benchmark:
```bash
python benchmark.py
```

### Performance Characteristics:
* **Pure Python:** Extremely slow due to Python's slow interpreter execution loops for `O(N^3)` math and GIL blocking.
* **Ctypes:** Significantly faster than pure Python because the expensive `O(N^3)` loops run in compiled C, but still bottlenecked under high concurrency due to Python-bound serialization.
* **Native JIT:** Maximum performance and scalability; runs completely GIL-free, allowing the server to utilize all CPU cores and scale up to 100x+ higher throughput than pure Python under load.
