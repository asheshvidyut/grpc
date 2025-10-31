#!/bin/bash
echo "Concurrency | Coroutine QPS | Sync QPS | Coroutine Lat50 (us) | Sync Lat50 (us) | Improvement"
echo "------------|---------------|----------|---------------------|----------------|------------"

for concurrency in 1 10 50 100 200; do
  # Update concurrency in test file
  sed -i '' "s/set_outstanding_rpcs_per_channel([0-9]*);/set_outstanding_rpcs_per_channel($concurrency);/" grpc/test/cpp/qps/inproc_sync_unary_ping_pong_test.cc
  sed -i '' "s/set_threads_per_cq([0-9]*);/set_threads_per_cq(10);/" grpc/test/cpp/qps/inproc_sync_unary_ping_pong_test.cc 2>/dev/null || true
  
  # Build
  cd grpc && bazel build --cxxopt='-std=c++20' --host_cxxopt='-std=c++20' -c opt --copt=-g //test/cpp/qps:inproc_sync_unary_ping_pong_test > /dev/null 2>&1 && cd ..
  
  if [ $? -ne 0 ]; then continue; fi
  
  # Coroutine
  cd grpc
  export USE_COROUTINES=1
  COROUTINE_OUT=$(timeout 25 bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test 2>&1)
  COROUTINE_QPS=$(echo "$COROUTINE_OUT" | grep "QPS:" | sed 's/.*QPS: \([0-9.]*\).*/\1/')
  COROUTINE_LAT=$(echo "$COROUTINE_OUT" | grep "Latencies" | sed 's/.*50\/[0-9.]*\/[0-9.]*\/[0-9.]*\/[0-9.]*-ile): \([0-9.]*\)\/.*/\1/')
  
  # Sync
  unset USE_COROUTINES
  SYNC_OUT=$(timeout 25 bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test 2>&1)
  SYNC_QPS=$(echo "$SYNC_OUT" | grep "QPS:" | sed 's/.*QPS: \([0-9.]*\).*/\1/')
  SYNC_LAT=$(echo "$SYNC_OUT" | grep "Latencies" | sed 's/.*50\/[0-9.]*\/[0-9.]*\/[0-9.]*\/[0-9.]*-ile): \([0-9.]*\)\/.*/\1/')
  cd ..
  
  if [ -n "$COROUTINE_QPS" ] && [ -n "$SYNC_QPS" ]; then
    IMPROVEMENT=$(echo "scale=1; ($COROUTINE_QPS - $SYNC_QPS) * 100 / $SYNC_QPS" | bc)
    printf "%11d | %13s | %8s | %19s | %14s | %+8.1f%%\n" "$concurrency" "$COROUTINE_QPS" "$SYNC_QPS" "$COROUTINE_LAT" "$SYNC_LAT" "$IMPROVEMENT"
  fi
done
