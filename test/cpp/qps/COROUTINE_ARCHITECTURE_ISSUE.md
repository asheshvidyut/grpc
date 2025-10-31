# Coroutine Client Architecture Issue

## Problem
The current coroutine implementation doesn't show benefits vs sync client because:

1. **Same threading model as sync**: Uses `num_threads = outstanding_rpcs_per_channel * client_channels` (one thread per RPC)
2. **Sequential execution**: Each thread does one RPC at a time, waiting for completion before starting the next
3. **No concurrency benefit**: Not leveraging the async nature - should have multiple in-flight coroutines per thread

## Comparison

### Sync Client
- **Threads**: `outstanding_rpcs_per_channel * client_channels` (one per RPC)
- **Execution**: Each thread blocks in kernel waiting for response
- **Overhead**: Thread context switching, but simple model

### Async Client (correct implementation)
- **Threads**: `NumThreads(config)` (typically 1 per CPU core, much fewer)
- **Execution**: All RPCs started upfront, threads process completions as they arrive
- **Concurrency**: Each thread handles multiple in-flight RPCs concurrently
- **Overhead**: Less thread overhead, better CPU utilization

### Our Coroutine Client (current - WRONG)
- **Threads**: `outstanding_rpcs_per_channel * client_channels` (same as sync!)
- **Execution**: One RPC at a time per thread, blocks waiting for completion
- **Concurrency**: NONE - sequential execution
- **Overhead**: Thread overhead + coroutine overhead, but no benefit

## Solution
Refactor to match async client architecture:

1. Use fewer threads: `NumThreads(config)` or `threads_per_cq` logic
2. Start all coroutines upfront: Each coroutine starts its async operation
3. Event loop per thread: Each thread processes CQ completions, resuming coroutines as they complete
4. Multiple concurrent coroutines per thread: Like async client has multiple concurrent RPCs

This way, coroutines provide:
- Less thread overhead (fewer threads)
- Better CPU utilization (multiple concurrent operations per thread)
- Cleaner code (coroutines vs callback/state machine)

