#!/bin/bash

echo "=== Benchmarking Coroutine vs Sync at Different Concurrency Levels ==="
echo ""

# Test different concurrency levels
for concurrency in 1 10 50 100 200 500 1000; do
  echo "Testing concurrency level: $concurrency"
  
  # Update the test file
  sed -i '' "s/set_outstanding_rpcs_per_channel([0-9]*);/set_outstanding_rpcs_per_channel($concurrency);/" grpc/test/cpp/qps/inproc_sync_unary_ping_pong_test.cc
  
  # Rebuild
  cd grpc && bazel build --cxxopt='-std=c++20' --host_cxxopt='-std=c++20' -c opt --copt=-g //test/cpp/qps:inproc_sync_unary_ping_pong_test > /dev/null 2>&1 && cd ..
  
  if [ $? -ne 0 ]; then
    echo "Build failed for concurrency $concurrency"
    continue
  fi
  
  # Run coroutine test
  cd grpc
  export USE_COROUTINES=1
  COROUTINE_OUT=$(timeout 30 bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test 2>&1 | grep -E "QPS|Latencies")
  
  # Run sync test
  unset USE_COROUTINES
  SYNC_OUT=$(timeout 30 bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test 2>&1 | grep -E "QPS|Latencies")
  cd ..
  
  # Extract QPS values
  COROUTINE_QPS=$(echo "$COROUTINE_OUT" | grep QPS | sed 's/.*QPS: \([0-9.]*\).*/\1/')
  SYNC_QPS=$(echo "$SYNC_OUT" | grep QPS | sed 's/.*QPS: \([0-9.]*\).*/\1/')
  
  # Extract 50th percentile latency
  COROUTINE_LAT50=$(echo "$COROUTINE_OUT" | grep Latencies | sed 's/.*50\/.*: \([0-9.]*\)\/.*/\1/')
  SYNC_LAT50=$(echo "$SYNC_OUT" | grep Latencies | sed 's/.*50\/.*: \([0-9.]*\)\/.*/\1/')
  
  echo "$concurrency,$COROUTINE_QPS,$SYNC_QPS,$COROUTINE_LAT50,$SYNC_LAT50"
done

