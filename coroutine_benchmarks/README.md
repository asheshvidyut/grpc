# C++20 Coroutine gRPC Client Benchmarks

This directory contains benchmarks and scripts for testing the C++20 coroutine-based gRPC client implementation.

## Files

- **`PERFORMANCE_COMPARISON.md`** - Detailed performance comparison table showing coroutine vs sync client at different concurrency levels
- **`profile_and_optimize.sh`** - Main script to build, profile, and benchmark the coroutine implementation
- **`benchmark_concurrency.sh`** - Script to benchmark multiple concurrency levels
- **`create_comparison_table.sh`** - Script to generate performance comparison tables
- **`run_quick_bench.sh`** - Quick benchmark script for rapid testing

## Prerequisites

- Bazel installed and configured
- C++20 compatible compiler (GCC 10+, Clang 11+)
- Linux or macOS system
- gRPC repository built

## Usage

### Running Benchmarks

From the `grpc` root directory:

```bash
# Run the main profiling and optimization script
./coroutine_benchmarks/profile_and_optimize.sh

# Or from within the coroutine_benchmarks directory:
cd coroutine_benchmarks
bash profile_and_optimize.sh
```

### Testing Coroutine Client

The coroutine client is enabled via the `USE_COROUTINES` environment variable:

```bash
# Test with coroutines
export USE_COROUTINES=1
bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test

# Test without coroutines (baseline sync client)
unset USE_COROUTINES
bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test
```

### Benchmarking Multiple Concurrency Levels

```bash
./coroutine_benchmarks/benchmark_concurrency.sh
```

This will test concurrency levels from 1 to 1000 and generate a comparison table.

## Implementation Details

The coroutine implementation consists of:

- **`test/cpp/qps/client_coroutine.h`** - Coroutine promise types and awaitable types
- **`test/cpp/qps/client_coroutine.cc`** - Implementation of coroutine machinery
- **`test/cpp/qps/client_coroutine_sync.cc`** - Coroutine-based client that mimics sync API

## Performance Results

Based on benchmarks, the coroutine implementation shows:

- **Best performance**: 32.7% improvement at 50 concurrent RPCs
- **Optimal range**: 10-100 concurrent RPCs per channel
- **Performance degrades** at very high concurrency (>200) due to polling overhead

See `PERFORMANCE_COMPARISON.md` for detailed results.

## Linux Notes

On Linux, you may need to:

1. Ensure epoll is available (default on modern Linux)
2. Use appropriate polling strategy:
   ```bash
   export GRPC_POLL_STRATEGY=poll  # or epoll1, epollex
   ```
3. Check file descriptor limits:
   ```bash
   ulimit -n 65536  # Increase if needed for high concurrency
   ```

## Building

```bash
# From grpc root directory
bazel build --cxxopt='-std=c++20' --host_cxxopt='-std=c++20' -c opt --copt=-g \
  //test/cpp/qps:inproc_sync_unary_ping_pong_test
```

