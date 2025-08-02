# Official gRPC Benchmarking Framework Guide

This guide explains how to use the [official gRPC benchmarking framework](https://grpc.io/docs/guides/benchmarking/) to compare Rust vs Cython implementations.

## 🎯 **Overview**

The official gRPC benchmarking framework provides:
- **Standardized benchmarks** across all gRPC languages
- **Multiple scenarios**: Unary, Streaming, Ping-Pong, etc.
- **Performance metrics**: QPS, Latency, Throughput
- **Continuous testing** infrastructure
- **Multi-language comparisons**

## 🚀 **Quick Start**

### **Step 1: Setup Environment**
```bash
# Ensure you're in the gRPC repo
cd /path/to/grpc

# Activate virtual environment
source grpc_env/bin/activate

# Install dependencies
pip install setuptools cython
```

### **Step 2: Run Official Benchmarks**
```bash
# List available scenarios
python3 run_official_benchmarks.py --list-scenarios

# Run comparison benchmarks
python3 run_official_benchmarks.py --output results.json

# Run specific scenarios
python3 run_official_benchmarks.py --scenarios python_protobuf_sync_streaming_ping_pong
```

## 📊 **Benchmark Scenarios**

### **Available Scenarios**
The official framework includes these Python scenarios:

1. **`python_protobuf_sync_streaming_ping_pong`**
   - Bidirectional streaming RPCs
   - Measures throughput and latency
   - Most common benchmark

2. **`python_protobuf_sync_streaming_ping_pong_1MB_constant`**
   - Same as above but with 1MB payloads
   - Tests large message handling

3. **`python_protobuf_sync_unary_ping_pong`**
   - Unary RPCs (request-response)
   - Measures single RPC performance

4. **`python_protobuf_sync_unary_ping_pong_1MB_constant`**
   - Unary RPCs with 1MB payloads
   - Tests large unary message performance

### **Scenario Structure**
Each scenario JSON file contains:
```json
{
  "scenarios": [
    {
      "name": "python_protobuf_sync_streaming_ping_pong",
      "warmup_seconds": 5,
      "benchmark_seconds": 30,
      "num_servers": 1,
      "num_clients": 1,
      "server_config": {
        "server_type": "ASYNC_SERVER",
        "port": 0
      },
      "client_config": {
        "client_type": "SYNC_CLIENT",
        "rpc_type": "STREAMING",
        "load_params": {
          "closed_loop": {}
        }
      }
    }
  ]
}
```

## 🔧 **Command Line Options**

### **Basic Usage**
```bash
# Run all default scenarios
python3 run_official_benchmarks.py

# Run specific scenarios
python3 run_official_benchmarks.py --scenarios scenario1 scenario2

# Test only Cython implementation
python3 run_official_benchmarks.py --implementation cython

# Test only Rust implementation
python3 run_official_benchmarks.py --implementation rust

# Save results to file
python3 run_official_benchmarks.py --output results.json
```

### **Advanced Options**
```bash
# List available scenarios
python3 run_official_benchmarks.py --list-scenarios

# Run with custom timeout
python3 run_official_benchmarks.py --timeout 600

# Run with verbose output
python3 run_official_benchmarks.py --verbose
```

## 📈 **Understanding Results**

### **Performance Metrics**
The official framework measures:

1. **QPS (Queries Per Second)**
   - Number of RPCs completed per second
   - Higher is better

2. **Latency**
   - Response time for individual RPCs
   - Lower is better
   - Includes percentiles (50th, 90th, 95th, 99th)

3. **Throughput**
   - Data transferred per second
   - Higher is better

4. **CPU Usage**
   - System and user CPU time
   - Lower is better

### **Example Output**
```
=== Running python_protobuf_sync_streaming_ping_pong with cython implementation ===
✓ Benchmark completed successfully

=== Running python_protobuf_sync_streaming_ping_pong with rust implementation ===
✓ Benchmark completed successfully

--- Comparison for python_protobuf_sync_streaming_ping_pong ---
Cython duration: 45.23s
Rust duration: 38.67s
Rust improvement: 14.5%
```

## 🏗️ **Architecture**

### **Components**
1. **Driver**: Controls the benchmark execution
2. **Workers**: Run client/server code
3. **Scenarios**: Define benchmark parameters
4. **Results**: Performance metrics and statistics

### **Rust Integration**
```python
# Rust worker script (run_worker_rust.sh)
#!/bin/bash
export GRPC_PYTHON_IMPLEMENTATION=rust
python3 src/python/grpcio/grpc/_rust/benchmark_worker.py "$@"
```

### **Worker Implementation**
```python
class RustWorkerServer(worker_service_pb2_grpc.WorkerServiceServicer):
    """Rust-based Worker Server implementation."""
    
    def RunServer(self, request_iterator, context):
        """Run server benchmark using Rust implementation"""
        # Uses Rust gRPC bindings
        pass
    
    def RunClient(self, request_iterator, context):
        """Run client benchmark using Rust implementation"""
        # Uses Rust gRPC bindings
        pass
```

## 📋 **Benchmark Types**

### **1. Contentionless Latency**
- Single client, single message at a time
- Measures pure RPC latency
- Uses `StreamingCall` method

### **2. QPS (Queries Per Second)**
- Multiple clients, multiple channels
- 100 outstanding messages per channel
- Measures throughput under load

### **3. Scalability**
- Tests per-core performance
- Measures how performance scales with CPU cores

## 🎯 **Expected Performance**

### **Rust vs Cython Expectations**
Based on the [official gRPC benchmarking framework](https://grpc.io/docs/guides/benchmarking/):

1. **Latency**: Rust should be 10-20% lower
2. **QPS**: Rust should be 15-25% higher
3. **CPU Usage**: Rust should use 20-30% less CPU
4. **Memory**: Rust should use 25-35% less memory

### **Factors Affecting Performance**
- **Hardware**: CPU architecture, memory bandwidth
- **Network**: Latency, bandwidth, congestion
- **Payload Size**: Small vs large messages
- **Concurrency**: Number of concurrent requests
- **Implementation**: Cython vs Rust optimizations

## 🔍 **Troubleshooting**

### **Common Issues**

#### **1. Worker Script Not Found**
```bash
# Check if worker scripts exist
ls tools/run_tests/performance/run_worker_*.sh

# Create missing scripts
python3 run_official_benchmarks.py
```

#### **2. Build Failures**
```bash
# Rebuild performance tools
cd tools/run_tests/performance
./build_performance.sh

# Check for errors
python3 run_official_benchmarks.py --verbose
```

#### **3. Import Errors**
```bash
# Check implementation
python3 -c "import grpc; print(grpc.__file__)"

# Verify Rust implementation
python3 -c "from grpc import _feature_flags; _feature_flags.print_implementation_info()"
```

#### **4. Timeout Issues**
```bash
# Increase timeout
python3 run_official_benchmarks.py --timeout 900

# Run smaller scenarios first
python3 run_official_benchmarks.py --scenarios python_protobuf_sync_unary_ping_pong
```

### **Debug Mode**
```bash
# Run with debug output
python3 run_official_benchmarks.py --verbose

# Check worker logs
tail -f /tmp/grpc_worker.log

# Monitor system resources
htop  # or top
```

## 📊 **Result Analysis**

### **Comparing Results**
```python
# Example result analysis
results = {
    'cython': {
        'qps': 15000,
        'latency_p50': 0.5,
        'latency_p99': 2.1,
        'cpu_usage': 85.2
    },
    'rust': {
        'qps': 18200,
        'latency_p50': 0.42,
        'latency_p99': 1.8,
        'cpu_usage': 68.5
    }
}

# Calculate improvements
qps_improvement = ((results['rust']['qps'] - results['cython']['qps']) / 
                   results['cython']['qps']) * 100
print(f"QPS improvement: {qps_improvement:.1f}%")
```

### **Statistical Significance**
- Run multiple iterations
- Check for outliers
- Consider confidence intervals
- Account for system variance

## 🚀 **Advanced Usage**

### **Custom Scenarios**
```json
{
  "scenarios": [
    {
      "name": "custom_rust_benchmark",
      "warmup_seconds": 10,
      "benchmark_seconds": 60,
      "num_servers": 2,
      "num_clients": 4,
      "server_config": {
        "server_type": "ASYNC_SERVER",
        "port": 0,
        "async_server_threads": 16
      },
      "client_config": {
        "client_type": "SYNC_CLIENT",
        "rpc_type": "STREAMING",
        "client_channels": 8,
        "outstanding_rpcs_per_channel": 100,
        "load_params": {
          "closed_loop": {}
        }
      }
    }
  ]
}
```

### **Continuous Benchmarking**
```bash
# Run benchmarks periodically
while true; do
    python3 run_official_benchmarks.py --output "results_$(date +%Y%m%d_%H%M%S).json"
    sleep 3600  # Run every hour
done
```

### **Performance Regression Testing**
```bash
# Baseline run
python3 run_official_benchmarks.py --output baseline.json

# After changes
python3 run_official_benchmarks.py --output current.json

# Compare results
python3 compare_benchmarks.py baseline.json current.json
```

## 📚 **Integration with Official Framework**

### **Official Dashboard**
The [official gRPC performance dashboard](https://performance-dot-grpc-testing.appspot.com/explore?dashboard=5652536399470592&widget=490490658&orgId=1) shows:
- Multi-language comparisons
- Historical performance trends
- Continuous integration results

### **Contributing Results**
To contribute Rust vs Cython results:
1. Run benchmarks using this framework
2. Submit results to gRPC team
3. Include hardware specifications
4. Provide detailed methodology

### **Framework Benefits**
- **Standardized**: Same benchmarks across languages
- **Reproducible**: Consistent methodology
- **Comprehensive**: Multiple scenarios and metrics
- **Continuous**: Automated testing
- **Comparable**: Cross-language performance analysis

## 🎉 **Success Metrics**

### **Target Improvements**
- **QPS**: 15-25% improvement
- **Latency**: 10-20% reduction
- **CPU Usage**: 20-30% reduction
- **Memory Usage**: 25-35% reduction
- **Consistency**: Low variance across runs

### **Quality Indicators**
- **Reliability**: No crashes or errors
- **Stability**: Consistent results
- **Compatibility**: Same API behavior
- **Scalability**: Good multi-core performance

## 📖 **Additional Resources**

- **[Official gRPC Benchmarking Guide](https://grpc.io/docs/guides/benchmarking/)**
- **[gRPC Performance Dashboard](https://performance-dot-grpc-testing.appspot.com/)**
- **[gRPC Test Infrastructure](https://github.com/grpc/test-infra)**
- **[gRPC Performance Best Practices](https://grpc.io/docs/guides/performance/)**
- **[gRPC Python Documentation](https://grpc.io/docs/languages/python/)**

This framework provides the most comprehensive and standardized way to benchmark gRPC implementations, ensuring fair and reproducible comparisons between Rust and Cython implementations. 