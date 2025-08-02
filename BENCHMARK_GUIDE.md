# gRPC Rust vs Cython Benchmarking Guide

This guide explains how to run comprehensive benchmarks comparing the Rust and Cython implementations of gRPC Python.

## 🚀 **Quick Start**

### **Step 1: Setup Environment**
```bash
# Run the setup script
python3 setup_benchmark.py

# Activate virtual environment
source grpc_env/bin/activate
```

### **Step 2: Run Simple Benchmark**
```bash
python3 simple_benchmark.py
```

### **Step 3: Run Comprehensive Benchmark**
```bash
python3 benchmark_rust_vs_cython.py --iterations 100 --output results.json
```

## 📊 **Benchmark Types**

### **1. Simple Benchmark (`simple_benchmark.py`)**
- **Import Time**: How fast each implementation imports
- **Channel Creation**: Time to create gRPC channels
- **Server Creation**: Time to create gRPC servers
- **Status Codes**: Performance of status code operations

### **2. Comprehensive Benchmark (`benchmark_rust_vs_cython.py`)**
- **Import Time**: Detailed import performance analysis
- **Channel Creation**: Channel creation performance
- **Server Creation**: Server creation performance
- **Status Codes**: Status code operation performance
- **Memory Usage**: Memory consumption comparison
- **Concurrent Operations**: Multi-threaded performance

## 🔧 **Command Line Options**

### **Simple Benchmark**
```bash
python3 simple_benchmark.py
```

### **Comprehensive Benchmark**
```bash
# Basic run
python3 benchmark_rust_vs_cython.py

# Custom iterations
python3 benchmark_rust_vs_cython.py --iterations 200

# Save results to file
python3 benchmark_rust_vs_cython.py --output results.json

# Test specific implementation
python3 benchmark_rust_vs_cython.py --implementation cython

# All options
python3 benchmark_rust_vs_cython.py --iterations 100 --warmup 20 --output results.json --implementation both
```

## 📈 **Understanding Results**

### **Performance Metrics**
- **Mean**: Average time across all iterations
- **Median**: Middle value (less affected by outliers)
- **Min/Max**: Best and worst case performance
- **Standard Deviation**: Consistency of performance

### **Memory Metrics**
- **Memory Used**: Additional memory consumed
- **Initial Memory**: Memory before operations
- **Final Memory**: Memory after operations

### **Example Output**
```
=== IMPORT TIME ===
  cython: 0.001234s (mean)
  rust: 0.000987s (mean)
  → Fastest: rust (0.000987s)
  → rust is 20.0% faster than cython
```

## 🎯 **Expected Results**

### **Performance Expectations**
1. **Import Time**: Rust should be similar or slightly faster
2. **Channel Creation**: Rust should be 10-20% faster
3. **Server Creation**: Rust should be 10-20% faster
4. **Memory Usage**: Rust should use 20-30% less memory
5. **Concurrent Operations**: Rust should handle concurrency better

### **Factors Affecting Performance**
- **Hardware**: CPU, memory, storage speed
- **Python Version**: Different Python versions may perform differently
- **System Load**: Other processes running
- **Warm-up**: First few iterations may be slower

## 🔍 **Troubleshooting**

### **Common Issues**

#### **1. Import Errors**
```bash
# Check if extensions are built
find src/python/grpcio/grpc/_cython/ -name "*.so" -o -name "*.dylib"
find src/python/grpcio/grpc/_rust/target/release/ -name "*.so" -o -name "*.dylib"
```

#### **2. Build Failures**
```bash
# Rebuild Cython extensions
python3 setup.py build_ext

# Rebuild Rust extensions
cd src/python/grpcio/grpc/_rust
cargo clean && cargo build --release
cd ../../../../..
```

#### **3. Memory Benchmark Issues**
```bash
# Install psutil for memory benchmarking
pip install psutil
```

### **Debug Mode**
```bash
# Run with debug output
python3 -v simple_benchmark.py

# Check implementation selection
python3 -c "from grpc import _feature_flags; _feature_flags.print_implementation_info()"
```

## 📋 **Benchmark Scripts**

### **1. `simple_benchmark.py`**
- Lightweight benchmark
- Quick results
- Good for development testing

### **2. `benchmark_rust_vs_cython.py`**
- Comprehensive benchmark
- Detailed analysis
- JSON report generation
- Memory usage tracking

### **3. `setup_benchmark.py`**
- Environment setup
- Dependency installation
- Extension building
- Import testing

## 📊 **Interpreting Results**

### **Performance Comparison**
```python
# Example results interpretation
results = {
    'cython': {'import_time': 0.001234, 'channel_creation': 0.000567},
    'rust': {'import_time': 0.000987, 'channel_creation': 0.000456}
}

# Calculate improvement
improvement = ((cython_time - rust_time) / cython_time) * 100
print(f"Rust is {improvement:.1f}% faster than Cython")
```

### **Statistical Significance**
- **Standard Deviation**: Lower is better (more consistent)
- **Outliers**: Check min/max values for anomalies
- **Sample Size**: More iterations = more reliable results

## 🎯 **Best Practices**

### **1. Environment Consistency**
- Use the same Python version
- Run on the same hardware
- Minimize system load
- Use virtual environments

### **2. Benchmark Execution**
- Run multiple times
- Use consistent iteration counts
- Include warm-up iterations
- Monitor system resources

### **3. Result Analysis**
- Compare mean and median
- Check for outliers
- Consider standard deviation
- Look for patterns across benchmarks

## 📈 **Advanced Benchmarking**

### **Custom Benchmarks**
```python
def custom_benchmark():
    """Add your own benchmark"""
    start_time = time.time()
    # Your gRPC operations here
    end_time = time.time()
    return end_time - start_time
```

### **Continuous Benchmarking**
```bash
# Run benchmarks periodically
while true; do
    python3 simple_benchmark.py >> benchmark_log.txt
    sleep 3600  # Run every hour
done
```

### **Performance Regression Testing**
```bash
# Compare against baseline
python3 benchmark_rust_vs_cython.py --output baseline.json
# ... make changes ...
python3 benchmark_rust_vs_cython.py --output current.json
python3 compare_results.py baseline.json current.json
```

## 🎉 **Success Metrics**

### **Target Performance Improvements**
- **Import Time**: < 5% difference
- **Channel Creation**: 10-20% improvement
- **Server Creation**: 10-20% improvement
- **Memory Usage**: 20-30% reduction
- **Concurrent Operations**: 15-25% improvement

### **Quality Metrics**
- **Consistency**: Low standard deviation
- **Reliability**: No crashes or errors
- **Compatibility**: Same API behavior
- **Stability**: Consistent results across runs

## 📚 **Additional Resources**

- **gRPC Documentation**: https://grpc.io/docs/
- **Rust Performance**: https://doc.rust-lang.org/book/ch03-00-common-programming-concepts.html
- **Python Profiling**: https://docs.python.org/3/library/profile.html
- **Statistical Analysis**: https://docs.python.org/3/library/statistics.html 