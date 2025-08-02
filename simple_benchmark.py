#!/usr/bin/env python3
"""
Simple benchmarking script for gRPC implementations
"""

import os
import sys
import time
import statistics


def benchmark_implementation(impl_name):
    """Benchmark a specific implementation"""
    print(f"\n=== Benchmarking {impl_name.upper()} ===")
    
    # Set environment variable
    os.environ['GRPC_PYTHON_IMPLEMENTATION'] = impl_name
    
    results = {}
    
    # Test 1: Import time
    print("1. Import time...")
    times = []
    for i in range(50):
        start_time = time.time()
        try:
            # Clear cached imports
            if 'grpc' in sys.modules:
                del sys.modules['grpc']
            if 'grpc._cython' in sys.modules:
                del sys.modules['grpc._cython']
            if 'grpc._rust' in sys.modules:
                del sys.modules['grpc._rust']
            
            import grpc
            end_time = time.time()
            times.append(end_time - start_time)
        except Exception as e:
            print(f"  ✗ Import failed: {e}")
            break
    
    if times:
        results['import_time'] = {
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'min': min(times),
            'max': max(times)
        }
        print(f"  ✓ Mean: {results['import_time']['mean']:.6f}s")
    
    # Test 2: Channel creation
    print("2. Channel creation...")
    try:
        import grpc
        times = []
        for i in range(100):
            start_time = time.time()
            channel = grpc.insecure_channel('localhost:50051')
            end_time = time.time()
            times.append(end_time - start_time)
        
        results['channel_creation'] = {
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'min': min(times),
            'max': max(times)
        }
        print(f"  ✓ Mean: {results['channel_creation']['mean']:.6f}s")
        
    except Exception as e:
        print(f"  ✗ Channel creation failed: {e}")
    
    # Test 3: Server creation
    print("3. Server creation...")
    try:
        import grpc
        from concurrent import futures
        times = []
        for i in range(100):
            start_time = time.time()
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
            end_time = time.time()
            times.append(end_time - start_time)
        
        results['server_creation'] = {
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'min': min(times),
            'max': max(times)
        }
        print(f"  ✓ Mean: {results['server_creation']['mean']:.6f}s")
        
    except Exception as e:
        print(f"  ✗ Server creation failed: {e}")
    
    # Test 4: Status codes
    print("4. Status code operations...")
    try:
        import grpc
        from grpc import StatusCode
        times = []
        for i in range(100):
            start_time = time.time()
            ok_code = StatusCode.OK
            cancelled_code = StatusCode.CANCELLED
            unknown_code = StatusCode.UNKNOWN
            end_time = time.time()
            times.append(end_time - start_time)
        
        results['status_codes'] = {
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'min': min(times),
            'max': max(times)
        }
        print(f"  ✓ Mean: {results['status_codes']['mean']:.6f}s")
        
    except Exception as e:
        print(f"  ✗ Status code operations failed: {e}")
    
    return results


def compare_results(results_dict):
    """Compare results between implementations"""
    print("\n" + "=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)
    
    benchmarks = ['import_time', 'channel_creation', 'server_creation', 'status_codes']
    
    for benchmark in benchmarks:
        print(f"\n{benchmark.upper().replace('_', ' ')}:")
        
        benchmark_results = {}
        for impl, results in results_dict.items():
            if benchmark in results:
                benchmark_results[impl] = results[benchmark]['mean']
                print(f"  {impl}: {results[benchmark]['mean']:.6f}s")
        
        if benchmark_results:
            fastest_impl = min(benchmark_results, key=benchmark_results.get)
            fastest_time = benchmark_results[fastest_impl]
            
            print(f"  → Fastest: {fastest_impl} ({fastest_time:.6f}s)")
            
            # Calculate improvements
            for impl, time_taken in benchmark_results.items():
                if impl != fastest_impl:
                    improvement = ((time_taken - fastest_time) / time_taken) * 100
                    print(f"  → {fastest_impl} is {improvement:.1f}% faster than {impl}")


def main():
    print("gRPC Implementation Benchmarking")
    print("=" * 50)
    
    all_results = {}
    
    # Test Cython implementation
    try:
        cython_results = benchmark_implementation('cython')
        all_results['cython'] = cython_results
    except Exception as e:
        print(f"✗ Cython benchmark failed: {e}")
    
    # Test Rust implementation
    try:
        rust_results = benchmark_implementation('rust')
        all_results['rust'] = rust_results
    except Exception as e:
        print(f"✗ Rust benchmark failed: {e}")
    
    # Test Auto implementation
    try:
        auto_results = benchmark_implementation('auto')
        all_results['auto'] = auto_results
    except Exception as e:
        print(f"✗ Auto benchmark failed: {e}")
    
    # Compare results
    compare_results(all_results)
    
    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main() 