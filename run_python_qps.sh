#!/bin/bash
# Helper script to run Python QPS benchmarks easily
# Usage: ./run_python_qps.sh [scenario_name]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
DRIVER_PORT_START=${DRIVER_PORT_START:-10000}
WARMUP_SECONDS=${WARMUP_SECONDS:-2}
BENCHMARK_SECONDS=${BENCHMARK_SECONDS:-5}
SCENARIO_NAME=${1:-"python_protobuf_sync_unary_ping_pong"}
NUM_WORKERS=${NUM_WORKERS:-2}  # Need at least 1 client + 1 server

echo "========================================="
echo "Python QPS Benchmark Runner"
echo "========================================="
echo "Scenario: $SCENARIO_NAME"
echo "Warmup: ${WARMUP_SECONDS}s, Benchmark: ${BENCHMARK_SECONDS}s"
echo "Workers: $NUM_WORKERS (starting at port $DRIVER_PORT_START)"
echo ""

# Step 1: Build Python worker (if not already built)
echo "Step 1: Building Python QPS worker..."
if ! [ -f "bazel-bin/src/python/grpcio_tests/tests/qps/qps_worker" ]; then
    bazel build -c opt //src/python/grpcio_tests/tests/qps:qps_worker
else
    echo "  ✓ Python worker already built"
fi

# Step 2: Build QPS driver with Bazel
echo ""
echo "Step 2: Building QPS driver with Bazel..."
if ! [ -f "bazel-bin/test/cpp/qps/qps_json_driver" ]; then
    bazel build -c opt //test/cpp/qps:qps_json_driver
else
    echo "  ✓ QPS driver already built"
fi

# Step 3: Generate scenario JSON
echo ""
echo "Step 3: Generating scenario JSON..."
SCENARIO_JSON=$(python3 - "$SCRIPT_DIR" "$SCENARIO_NAME" "$WARMUP_SECONDS" "$BENCHMARK_SECONDS" << 'PYEOF'
import sys
import os
script_dir = sys.argv[1]
scenario_name = sys.argv[2]
warmup_seconds = int(sys.argv[3])
benchmark_seconds = int(sys.argv[4])

sys.path.insert(0, os.path.join(script_dir, 'tools/run_tests/performance'))
import scenario_config
import json

# Find the requested scenario
python_lang = scenario_config.PythonLanguage()
target_scenario = None
for scenario in python_lang.scenarios():
    if scenario['name'] == scenario_name:
        target_scenario = scenario
        break

if not target_scenario:
    # Use a default simple scenario
    print("Warning: Scenario '{}' not found, using default".format(scenario_name), file=sys.stderr)
    target_scenario = {
        "name": "python_simple_unary_test",
        "num_servers": 1,
        "num_clients": 1,
        "warmup_seconds": warmup_seconds,
        "benchmark_seconds": benchmark_seconds,
        "spawn_local_worker_count": -2,
        "client_config": {
            "client_type": "SYNC_CLIENT",
            "security_params": None,
            "outstanding_rpcs_per_channel": 1,
            "client_channels": 1,
            "async_client_threads": 1,
            "rpc_type": "UNARY",
            "histogram_params": {
                "resolution": 0.01,
                "max_possible": 60000000000.0
            },
            "payload_config": {
                "simple_params": {
                    "req_size": 0,
                    "resp_size": 0
                }
            },
            "load_params": {
                "closed_loop": {}
            },
            "channel_args": []
        },
        "server_config": {
            "server_type": "ASYNC_SERVER",
            "security_params": None,
            "async_server_threads": 1,
            "payload_config": {
                "simple_params": {
                    "req_size": 0,
                    "resp_size": 0
                }
            },
            "channel_args": []
        }
    }
else:
    # Update timing if scenario found
    target_scenario["warmup_seconds"] = warmup_seconds
    target_scenario["benchmark_seconds"] = benchmark_seconds

# Remove non-proto fields and convert to JSON
scenario_cleaned = scenario_config.remove_nonproto_fields(target_scenario)

result = {"scenarios": [scenario_cleaned]}
print(json.dumps(result))
PYEOF
)

if [ -z "$SCENARIO_JSON" ]; then
    echo "Error: Failed to generate scenario JSON"
    exit 1
fi

echo "  ✓ Scenario JSON generated"

# Step 4: Start workers in background
echo ""
echo "Step 4: Starting $NUM_WORKERS Python QPS worker(s)..."
WORKER_PIDS=()
WORKER_PORTS=()
for i in $(seq 0 $((NUM_WORKERS - 1))); do
    PORT=$((DRIVER_PORT_START + i))
    WORKER_PORTS+=("localhost:$PORT")
    echo "  Starting worker $((i+1))/$NUM_WORKERS on port $PORT..."
    bazel-bin/src/python/grpcio_tests/tests/qps/qps_worker --driver_port=$PORT > /tmp/qps_worker_${i}.log 2>&1 &
    PID=$!
    WORKER_PIDS+=($PID)
    echo "    Worker PID: $PID"
done

# Wait for workers to be ready
sleep 3

# Check if all workers are still running
FAILED=0
for i in $(seq 0 $((NUM_WORKERS - 1))); do
    PID=${WORKER_PIDS[$i]}
    if ! kill -0 $PID 2>/dev/null; then
        echo "  ✗ Worker $((i+1)) failed to start. Check /tmp/qps_worker_${i}.log"
        FAILED=1
    fi
done

if [ $FAILED -eq 1 ]; then
    # Clean up any running workers
    for PID in "${WORKER_PIDS[@]}"; do
        kill $PID 2>/dev/null || true
    done
    exit 1
fi

echo "  ✓ All $NUM_WORKERS workers are running"
WORKER_LIST=$(IFS=','; echo "${WORKER_PORTS[*]}")

# Step 5: Run the driver
echo ""
echo "Step 5: Running QPS driver with scenario..."
echo "----------------------------------------"
export QPS_WORKERS="$WORKER_LIST"

# Run driver and capture output
bazel-bin/test/cpp/qps/qps_json_driver --scenarios_json="$SCENARIO_JSON" 2>&1 | tee /tmp/qps_results.log || DRIVER_EXIT=$?

# Step 6: Cleanup
echo ""
echo "Step 6: Stopping workers..."
for i in $(seq 0 $((NUM_WORKERS - 1))); do
    PID=${WORKER_PIDS[$i]}
    echo "  Stopping worker $((i+1)) (PID: $PID)..."
    kill $PID 2>/dev/null || true
done
for PID in "${WORKER_PIDS[@]}"; do
    wait $PID 2>/dev/null || true
done

echo ""
echo "========================================="
echo "Benchmark complete!"
echo "========================================="
echo "Full results saved to: /tmp/qps_results.log"
echo "Worker logs saved to: /tmp/qps_worker_*.log"
echo ""

# Extract and display key metrics
if [ -f /tmp/qps_results.log ]; then
    echo "Key Metrics:"
    grep -E "(QPS|Latency|queries_per_second)" /tmp/qps_results.log | head -10 || echo "  (Check /tmp/qps_results.log for full output)"
fi

exit ${DRIVER_EXIT:-0}

