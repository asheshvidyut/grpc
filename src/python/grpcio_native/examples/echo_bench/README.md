# Unified gRPC Echo Server: Pure Python, ctypes, and JIT C++

This unified example demonstrates and compares three distinct approaches to building gRPC servers in Python:

1. **Pure Python (`--pure-python`):** Standard Python servicer.
2. **Ctypes Delegation (`--ctypes`):** Standard Python servicer that delegates CPU-heavy operations to a C library (`echo_handler.so`) via Python's built-in `ctypes`.
3. **Native JIT (`--jit` / default):** High-performance, zero-copy native JIT-compiled Cython/C++ handler using `grpcio_native`.

All three modes automatically support **gRPC Server Reflection**, allowing you to query schemas and make requests dynamically with tools like `grpcurl`.

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

## Verifying and Querying (grpcurl)

Since reflection is enabled across all modes, you can query the server dynamically:

* **List all registered services:**
  ```bash
  docker run --network host fullstorydev/grpcurl -plaintext localhost:50088 list
  ```

* **Describe the Echo service:**
  ```bash
  docker run --network host fullstorydev/grpcurl -plaintext localhost:50088 describe echo.EchoService
  ```

* **Call the method with JSON payload (Inline):**
  ```bash
  docker run --network host fullstorydev/grpcurl -plaintext -d '{"message": "Hello!"}' localhost:50088 echo.EchoService/Echo
  ```

* **Call the method with JSON payload (Piping from a file):**
  ```bash
  cat data.json | docker run -i --network host fullstorydev/grpcurl -plaintext -d @ localhost:50088 echo.EchoService/Echo
  ```

---

## Benchmarking and Comparing Performance

A unified benchmark client is provided to measure and compare the latency and throughput (QPS) of the three modes under concurrent client load.

Ensure your server is running in the desired mode, then execute the benchmark:
```bash
python benchmark.py
```

### Sample Outputs (e.g., with 100KB payloads):
* **Pure Python:** Slower due to Python protobuf serialization and GIL contention.
* **Ctypes:** Marginally faster but still bottlenecked by Python serialization.
* **Native JIT:** Highest performance; runs completely GIL-free with zero-copy C++ serialization.
