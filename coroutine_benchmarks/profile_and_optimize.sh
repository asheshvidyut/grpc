#!/bin/bash
# Complete profiling and optimization workflow for C++ gRPC

# Don't exit on error immediately - let us see what went wrong
set +e

# Unset GRPC_POLL_STRATEGY if set to epoll1 on macOS (epoll is Linux-only)
if [[ "$OSTYPE" == "darwin"* ]] && [[ "$GRPC_POLL_STRATEGY" == "epoll1" ]]; then
    echo "⚠️  Warning: GRPC_POLL_STRATEGY=epoll1 is not supported on macOS (epoll is Linux-only)"
    echo "   Unsetting GRPC_POLL_STRATEGY to use default (poll)"
    unset GRPC_POLL_STRATEGY
fi

# Change to grpc root directory (script should be run from grpc/coroutine_benchmarks/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRPC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$GRPC_ROOT"

echo "=== C++ gRPC Performance Profiling & Optimization ==="
echo ""

# Build
echo "1. Building with optimizations and debug symbols..."
echo "   (This may take a few minutes on first build...)"
echo ""

# Show bazel output - use unbuffered output
bazel build --cxxopt='-std=c++20' --host_cxxopt='-std=c++20' -c opt --copt=-g //test/cpp/qps:inproc_sync_unary_ping_pong_test

BUILD_EXIT=$?
if [ $BUILD_EXIT -ne 0 ]; then
    echo ""
    echo "⚠️  Build failed with exit code $BUILD_EXIT"
    echo "Trying with standalone spawn strategy..."
    echo ""
    bazel build -c opt --copt=-g --spawn_strategy=standalone //test/cpp/qps:inproc_sync_unary_ping_pong_test
    BUILD_EXIT=$?
    if [ $BUILD_EXIT -ne 0 ]; then
        echo ""
        echo "❌ Build still failed. Check the errors above."
        exit 1
    fi
fi

# Re-enable exit on error for rest of script
set -e

# Find binary - Bazel says it's built, so check expected location
BINARY="bazel-bin/test/cpp/qps/inproc_sync_unary_ping_pong_test"

# Verify it exists
if [ ! -f "$BINARY" ]; then
    echo ""
    echo "⚠️  Binary not at expected path: $BINARY"
    echo "   Current directory: $(pwd)"
    echo "   Searching for binary..."
    
    # Try to find it
    FOUND=$(find bazel-bin -name "inproc_sync_unary_ping_pong_test" -type f 2>/dev/null | head -1)
    
    if [ -n "$FOUND" ] && [ -f "$FOUND" ]; then
        BINARY="$FOUND"
        echo "   Found binary at: $BINARY"
    else
        echo "   ❌ Binary not found. Checking bazel-bin structure..."
        ls -la bazel-bin/test/cpp/qps/ 2>/dev/null || echo "   bazel-bin/test/cpp/qps/ doesn't exist"
        exit 1
    fi
fi

# Final check
if [ ! -f "$BINARY" ]; then
    echo ""
    echo "❌ Error: Binary file does not exist: $BINARY"
    exit 1
fi

echo "✅ Build successful!"
echo "   Binary: $BINARY"
echo ""

# Detect OS and choose appropriate profiler
OS_TYPE=$(uname -s)
PROFILE_FILE=""
PROFILE_METHOD=""

if [ "$OS_TYPE" = "Darwin" ]; then
    # macOS - use sample profiler
    echo "✅ Detected macOS - using built-in 'sample' profiler"
    PROFILE_METHOD="sample"
elif [ "$OS_TYPE" = "Linux" ]; then
    # Linux - use perf
    echo "✅ Detected Linux - using 'perf' profiler"
    if ! command -v perf >/dev/null 2>&1; then
        echo "⚠️  Warning: 'perf' not found. Install with:"
        echo "   Ubuntu/Debian: sudo apt-get install linux-perf"
        echo "   RHEL/CentOS: sudo yum install perf"
        echo ""
        echo "   Alternatively, you can use gperftools (see HOW_TO_VIEW_CPU_PROFILE.md)"
        exit 1
    fi
    PROFILE_METHOD="perf"
else
    echo "⚠️  Warning: Unknown OS '$OS_TYPE'"
    echo "   Defaulting to Linux 'perf' profiler..."
    PROFILE_METHOD="perf"
fi

# Start port server if needed
echo ""
echo "2. Setting up environment..."
if ! pgrep -f "start_port_server.py" > /dev/null; then
    echo "   Starting port server (needed for test)..."
    python3 tools/run_tests/start_port_server.py > /tmp/port_server.log 2>&1 &
    PORT_SERVER_PID=$!
    sleep 2
    echo "   Port server started (PID: $PORT_SERVER_PID)"
else
    echo "   Port server already running"
fi

# Profile based on OS
echo ""
echo "3. Running benchmark with CPU profiling..."
if [ -n "${USE_COROUTINES}" ]; then
    echo "   🚀 Using C++20 coroutine-based client (USE_COROUTINES enabled)"
else
    echo "   Using standard synchronous client"
    echo "   (Set USE_COROUTINES=1 to use coroutines)"
fi
echo "   ⏱️  This will take ~5 seconds (1s warmup + 3s benchmark + profiling)"
echo ""

if [ "$PROFILE_METHOD" = "sample" ]; then
    # macOS sample profiler
    PROFILE_FILE="/tmp/cpp_perf_sample_$(date +%s).txt"
    
    # Run benchmark in background and profile it
    export USE_COROUTINES=1
    $BINARY > /tmp/benchmark_output.log 2>&1 &
    BENCHMARK_PID=$!
    
    # Wait a bit for it to start
    sleep 1
    
    # Profile for 10 seconds (covers warmup + benchmark)
    echo "   Sampling process $BENCHMARK_PID for 10 seconds..."
    sample $BENCHMARK_PID 10 -f "$PROFILE_FILE" 2>&1 || true
    
    # Wait for benchmark to finish
    wait $BENCHMARK_PID 2>/dev/null || true
    
elif [ "$PROFILE_METHOD" = "perf" ]; then
    # Linux perf profiler
    PROFILE_FILE="/tmp/cpp_perf_$(date +%s).data"
    
    echo "   Profiling benchmark with 'perf record'..."
    export USE_COROUTINES=1
    perf record -g -F 99 --call-graph dwarf -o "$PROFILE_FILE" \
        $BINARY > /tmp/benchmark_output.log 2>&1
    
    PERF_EXIT=$?
    if [ $PERF_EXIT -ne 0 ]; then
        echo "⚠️  perf record failed. Trying without call-graph..."
        perf record -F 99 -o "$PROFILE_FILE" \
            $BINARY > /tmp/benchmark_output.log 2>&1
    fi
fi

echo ""
if [ -f "$PROFILE_FILE" ]; then
    echo "✅ Profile generated successfully!"
    echo "   Profile saved to: $PROFILE_FILE"
    echo ""
else
    echo "⚠️  Profile file not generated."
    echo "   Check benchmark output:"
    cat /tmp/benchmark_output.log | tail -20
    exit 1
fi

# Analysis
echo ""
echo "4. Analysis Results:"
echo "===================="
echo ""

# Use the analyzer script if available
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$PROFILE_METHOD" = "sample" ] && [ -f "$SCRIPT_DIR/analyze_profile.sh" ]; then
    echo "📊 Function-Level CPU Time Breakdown (like Go's 'go tool pprof'):"
    "$SCRIPT_DIR/analyze_profile.sh" "$PROFILE_FILE" 2>&1 | head -50
    echo ""
elif [ "$PROFILE_METHOD" = "perf" ] && [ -f "$SCRIPT_DIR/analyze_perf.sh" ]; then
    echo "📊 Function-Level CPU Time Breakdown (like Go's 'go tool pprof'):"
    "$SCRIPT_DIR/analyze_perf.sh" "$PROFILE_FILE" "$BINARY" 2>&1 | head -50
    echo ""
else
    if [ "$PROFILE_METHOD" = "sample" ]; then
        echo "Top Functions by CPU Time (from sample profiler):"
        echo "────────────────────────────────────────────────────────────────────"
        echo ""
        echo "Heaviest stack traces:"
        grep -A 30 "Heaviest stack" "$PROFILE_FILE" 2>/dev/null | head -50
        echo ""
        
        echo "Call graph (function hierarchy with time %):"
        echo "────────────────────────────────────────────────────────────────────"
        grep -A 100 "Call graph" "$PROFILE_FILE" 2>/dev/null | head -150
    elif [ "$PROFILE_METHOD" = "perf" ]; then
        echo "📊 Top Functions by CPU Time (from perf):"
        echo "────────────────────────────────────────────────────────────────────"
        perf report --stdio --no-children -i "$PROFILE_FILE" 2>&1 | head -80
        echo ""
        echo "💡 For interactive view: perf report -i $PROFILE_FILE"
        echo "💡 For call graph: perf report --stdio -g graph -i $PROFILE_FILE | head -100"
    fi
    echo ""
fi

echo ""
echo "5. Full profile output saved to:"
echo "   $PROFILE_FILE"
echo ""
if [ "$PROFILE_METHOD" = "sample" ]; then
    echo "   To analyze again (like Go's 'go tool pprof'):"
    echo "   ./analyze_profile.sh $PROFILE_FILE"
elif [ "$PROFILE_METHOD" = "perf" ]; then
    echo "   To analyze with perf (like Go's 'go tool pprof'):"
    echo "   ./analyze_perf.sh $PROFILE_FILE $BINARY"
    echo "   perf report -i $PROFILE_FILE"
fi
echo ""

# Cleanup port server if we started it
if [ -n "$PORT_SERVER_PID" ]; then
    kill $PORT_SERVER_PID 2>/dev/null || true
fi

