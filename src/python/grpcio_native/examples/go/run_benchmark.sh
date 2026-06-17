#!/usr/bin/env bash

# Exit immediately on error
set -e

echo "============================================================="
# Ensure everything is built
echo "Compiling Go server and benchmark tool..."
go build -o server server.go
go build -o benchmark benchmark.go

echo "Compiling C++ native library for Python server..."
(cd ../cpp && make clean && make)

# Cleanup functions
cleanup() {
    echo "Cleaning up background servers..."
    if [ -n "$CPP_PID" ]; then
        kill -9 $CPP_PID 2>/dev/null || true
    fi
    if [ -n "$GO_PID" ]; then
        kill -9 $GO_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT

# 1. Benchmark C++ Server (Native Flow via Python)
echo "============================================================="
echo "Starting C++ Native Flow Server (via Python) on port 50099..."
PYTHONPATH=../../.. python3 ../cpp/server.py --port 50099 > cpp_server.log 2>&1 &
CPP_PID=$!

# Wait for server to start
sleep 3

echo "Running benchmark against C++ Native Flow Server..."
./benchmark -target localhost:50099 -size 1073741824 -samples 5 -warmup 1 > cpp_bench.log 2>&1 || {
    echo "C++ benchmark failed. Server logs:"
    cat cpp_server.log
    exit 1
}
cat cpp_bench.log

# Shutdown C++ server
kill -9 $CPP_PID 2>/dev/null || true
CPP_PID=""

# Wait 2 seconds for port/socket resources to settle
sleep 2

# 2. Benchmark Go Server
echo "============================================================="
echo "Starting Go Server on port 50098..."
./server -port 50098 > go_server.log 2>&1 &
GO_PID=$!

# Wait for server to start
sleep 3

echo "Running benchmark against Go Server..."
./benchmark -target localhost:50098 -size 1073741824 -samples 5 -warmup 1 > go_bench.log 2>&1 || {
    echo "Go benchmark failed. Server logs:"
    cat go_server.log
    exit 1
}
cat go_bench.log

# Shutdown Go server
kill -9 $GO_PID 2>/dev/null || true
GO_PID=""

# 3. Summary Comparison
echo "============================================================="
echo "                    BENCHMARK SUMMARY"
echo "============================================================="
echo "C++ Native Flow Server Results (Port 50099):"
grep -E "Min Latency|Max Latency|Mean Latency|Average Read/Write Speed" cpp_bench.log || true
echo "-------------------------------------------------------------"
echo "Go Server Results (Port 50098):"
grep -E "Min Latency|Max Latency|Mean Latency|Average Read/Write Speed" go_bench.log || true
echo "============================================================="
