#!/bin/bash

# Detect if we're in grpc root or not, and determine paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../test/cpp/qps/inproc_sync_unary_ping_pong_test.cc" ]; then
  # We're in grpc root (coroutine_benchmarks/ is inside grpc)
  GRPC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  TEST_FILE="$GRPC_ROOT/test/cpp/qps/inproc_sync_unary_ping_pong_test.cc"
elif [ -f "test/cpp/qps/inproc_sync_unary_ping_pong_test.cc" ]; then
  # We're in grpc root already
  GRPC_ROOT="$(pwd)"
  TEST_FILE="$GRPC_ROOT/test/cpp/qps/inproc_sync_unary_ping_pong_test.cc"
else
  echo "Error: Cannot find test file. Run from grpc root or coroutine_benchmarks directory."
  exit 1
fi

cd "$GRPC_ROOT"

echo "=== Benchmarking Coroutine vs Sync at Different Concurrency Levels ==="
echo "GRPC_ROOT: $GRPC_ROOT"
echo "TEST_FILE: $TEST_FILE"
echo ""

# Function to do sed in-place edit (works on both Linux and macOS)
sed_in_place() {
  local file="$1"
  local pattern="$2"
  if [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux"* ]]; then
    sed -i "$pattern" "$file"
  else
    sed -i '' "$pattern" "$file"
  fi
}

# Test different concurrency levels
for concurrency in 1 10 50 100 200 500 1000; do
  echo "Testing concurrency level: $concurrency"
  
  # Update the test file
  sed_in_place "$TEST_FILE" "s/set_outstanding_rpcs_per_channel([0-9]*);/set_outstanding_rpcs_per_channel($concurrency);/"
  
  # Rebuild
  bazel build --cxxopt='-std=c++20' --host_cxxopt='-std=c++20' -c opt --copt=-g //test/cpp/qps:inproc_sync_unary_ping_pong_test > /dev/null 2>&1
  
  if [ $? -ne 0 ]; then
    echo "Build failed for concurrency $concurrency"
    continue
  fi
  
  # Run coroutine test
  export USE_COROUTINES=1
  COROUTINE_OUT=$(timeout 30 bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test 2>&1 | grep -E "QPS|Latencies")
  
  # Run sync test
  unset USE_COROUTINES
  SYNC_OUT=$(timeout 30 bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test 2>&1 | grep -E "QPS|Latencies")
  
  # Extract QPS values
  COROUTINE_QPS=$(echo "$COROUTINE_OUT" | grep QPS | sed 's/.*QPS: \([0-9.]*\).*/\1/')
  SYNC_QPS=$(echo "$SYNC_OUT" | grep QPS | sed 's/.*QPS: \([0-9.]*\).*/\1/')
  
  # Extract 50th percentile latency
  COROUTINE_LAT50=$(echo "$COROUTINE_OUT" | grep Latencies | sed 's/.*50\/.*: \([0-9.]*\)\/.*/\1/')
  SYNC_LAT50=$(echo "$SYNC_OUT" | grep Latencies | sed 's/.*50\/.*: \([0-9.]*\)\/.*/\1/')
  
  echo "$concurrency,$COROUTINE_QPS,$SYNC_QPS,$COROUTINE_LAT50,$SYNC_LAT50"
done

