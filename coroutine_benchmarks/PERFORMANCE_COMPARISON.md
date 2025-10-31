# Performance Comparison: Coroutine vs Sync gRPC Client

## Benchmark Results

| Concurrency | Coroutine QPS | Sync QPS   | Improvement | Coroutine Lat50 | Sync Lat50 |
|-------------|---------------|------------|-------------|-----------------|------------|
| 1           | 80,127        | 72,647     | **+10.3%**  | 11.2 µs         | 12.2 µs    |
| 10          | 120,896       | 110,661    | **+9.2%**   | 64.5 µs         | 73.4 µs    |
| 50          | 144,557       | 108,928    | **+32.7%**  | 90.3 µs         | 96.7 µs    |
| 200         | 108,788       | 116,381    | -6.5%       | 250.0 µs        | 140.7 µs   |
| 500         | 59,088        | 108,226    | -45.4%      | 299.6 µs        | 142.4 µs   |

## Key Observations

### ✅ **Coroutines Excel at Moderate Concurrency (10-100 RPCs)**
- **Peak performance**: **32.7% improvement** at 50 concurrent RPCs
- Better CPU utilization without blocking threads
- Lower median latency compared to sync client

### ⚠️ **Performance Degrades at Very High Concurrency (>200)**
- Polling overhead becomes significant with many threads
- Each thread polls its completion queue independently
- Sync client's blocking model becomes more efficient

### 📊 **Optimal Configuration**
- **Recommended range**: 10-100 concurrent RPCs per channel
- **Threads per CQ**: 10 (sharing completion queues reduces overhead)
- **Best performance**: ~50 concurrent RPCs shows maximum benefit

## Performance Analysis

### Why Coroutines Win at Moderate Concurrency:
1. **No thread blocking**: Coroutines yield control instead of blocking threads
2. **Better CPU utilization**: Multiple operations can progress on fewer threads
3. **Lower overhead**: Coroutine frames are lighter than full thread contexts
4. **Efficient polling**: In-thread polling eliminates thread wake-up costs

### Why Sync Client Wins at Very High Concurrency:
1. **Native blocking**: Kernel-level blocking is more efficient than user-space polling
2. **Less CPU spinning**: Sync client doesn't consume CPU cycles while waiting
3. **Kernel scheduling**: OS scheduler handles thread management more efficiently
4. **Lower contention**: No polling overhead when many threads are waiting

## Recommendations

- **Use coroutines for**: 10-100 concurrent RPCs per channel
- **Use sync client for**: >200 concurrent RPCs per channel
- **Hybrid approach**: Consider sharing completion queues more aggressively at high concurrency

## Test Configuration

- **Server**: Synchronous server (in-process)
- **RPC Type**: Unary
- **Benchmark Duration**: 3 seconds (after 1 second warmup)
- **Platform**: macOS (Darwin)
- **Build**: Optimized (-O2) with debug symbols (-g)

