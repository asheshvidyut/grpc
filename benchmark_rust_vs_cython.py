#!/usr/bin/env python3
"""
Benchmarking script to compare Rust vs Cython gRPC implementations
"""

import os
import sys
import time
import statistics
import subprocess
import threading
from concurrent import futures
import json
from typing import Dict, List, Any
import argparse


class GRPCBenchmark:
    """Benchmarking framework for gRPC implementations"""
    
    def __init__(self):
        self.results = {}
        self.iterations = 100
        self.warmup_iterations = 10
        
    def benchmark_import_time(self):
        """Benchmark import time for different implementations"""
        print("=== Import Time Benchmark ===")
        
        implementations = ['cython', 'rust', 'auto']
        results = {}
        
        for impl in implementations:
            print(f"\nTesting {impl} implementation...")
            
            # Set environment variable
            os.environ['GRPC_PYTHON_IMPLEMENTATION'] = impl
            
            times = []
            for i in range(self.iterations):
                start_time = time.time()
                try:
                    # Clear any cached imports
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
                results[impl] = {
                    'mean': statistics.mean(times),
                    'median': statistics.median(times),
                    'min': min(times),
                    'max': max(times),
                    'std': statistics.stdev(times) if len(times) > 1 else 0
                }
                print(f"  ✓ Mean: {results[impl]['mean']:.6f}s")
                print(f"  ✓ Median: {results[impl]['median']:.6f}s")
                print(f"  ✓ Std Dev: {results[impl]['std']:.6f}s")
        
        self.results['import_time'] = results
        return results
    
    def benchmark_channel_creation(self):
        """Benchmark channel creation time"""
        print("\n=== Channel Creation Benchmark ===")
        
        implementations = ['cython', 'rust', 'auto']
        results = {}
        
        for impl in implementations:
            print(f"\nTesting {impl} implementation...")
            
            # Set environment variable
            os.environ['GRPC_PYTHON_IMPLEMENTATION'] = impl
            
            try:
                import grpc
                times = []
                
                for i in range(self.iterations):
                    start_time = time.time()
                    channel = grpc.insecure_channel('localhost:50051')
                    end_time = time.time()
                    times.append(end_time - start_time)
                
                results[impl] = {
                    'mean': statistics.mean(times),
                    'median': statistics.median(times),
                    'min': min(times),
                    'max': max(times),
                    'std': statistics.stdev(times) if len(times) > 1 else 0
                }
                print(f"  ✓ Mean: {results[impl]['mean']:.6f}s")
                print(f"  ✓ Median: {results[impl]['median']:.6f}s")
                print(f"  ✓ Std Dev: {results[impl]['std']:.6f}s")
                
            except Exception as e:
                print(f"  ✗ Channel creation failed: {e}")
        
        self.results['channel_creation'] = results
        return results
    
    def benchmark_server_creation(self):
        """Benchmark server creation time"""
        print("\n=== Server Creation Benchmark ===")
        
        implementations = ['cython', 'rust', 'auto']
        results = {}
        
        for impl in implementations:
            print(f"\nTesting {impl} implementation...")
            
            # Set environment variable
            os.environ['GRPC_PYTHON_IMPLEMENTATION'] = impl
            
            try:
                import grpc
                from concurrent import futures
                times = []
                
                for i in range(self.iterations):
                    start_time = time.time()
                    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
                    end_time = time.time()
                    times.append(end_time - start_time)
                
                results[impl] = {
                    'mean': statistics.mean(times),
                    'median': statistics.median(times),
                    'min': min(times),
                    'max': max(times),
                    'std': statistics.stdev(times) if len(times) > 1 else 0
                }
                print(f"  ✓ Mean: {results[impl]['mean']:.6f}s")
                print(f"  ✓ Median: {results[impl]['median']:.6f}s")
                print(f"  ✓ Std Dev: {results[impl]['std']:.6f}s")
                
            except Exception as e:
                print(f"  ✗ Server creation failed: {e}")
        
        self.results['server_creation'] = results
        return results
    
    def benchmark_status_codes(self):
        """Benchmark status code operations"""
        print("\n=== Status Code Operations Benchmark ===")
        
        implementations = ['cython', 'rust', 'auto']
        results = {}
        
        for impl in implementations:
            print(f"\nTesting {impl} implementation...")
            
            # Set environment variable
            os.environ['GRPC_PYTHON_IMPLEMENTATION'] = impl
            
            try:
                import grpc
                from grpc import StatusCode
                times = []
                
                for i in range(self.iterations):
                    start_time = time.time()
                    # Test status code operations
                    ok_code = StatusCode.OK
                    cancelled_code = StatusCode.CANCELLED
                    unknown_code = StatusCode.UNKNOWN
                    end_time = time.time()
                    times.append(end_time - start_time)
                
                results[impl] = {
                    'mean': statistics.mean(times),
                    'median': statistics.median(times),
                    'min': min(times),
                    'max': max(times),
                    'std': statistics.stdev(times) if len(times) > 1 else 0
                }
                print(f"  ✓ Mean: {results[impl]['mean']:.6f}s")
                print(f"  ✓ Median: {results[impl]['median']:.6f}s")
                print(f"  ✓ Std Dev: {results[impl]['std']:.6f}s")
                
            except Exception as e:
                print(f"  ✗ Status code operations failed: {e}")
        
        self.results['status_codes'] = results
        return results
    
    def benchmark_memory_usage(self):
        """Benchmark memory usage"""
        print("\n=== Memory Usage Benchmark ===")
        
        try:
            import psutil
            import gc
        except ImportError:
            print("  ℹ psutil not available, skipping memory benchmark")
            return {}
        
        implementations = ['cython', 'rust', 'auto']
        results = {}
        
        process = psutil.Process()
        
        for impl in implementations:
            print(f"\nTesting {impl} implementation...")
            
            # Set environment variable
            os.environ['GRPC_PYTHON_IMPLEMENTATION'] = impl
            
            try:
                # Clear memory
                gc.collect()
                initial_memory = process.memory_info().rss
                
                # Import and create objects
                import grpc
                from grpc import StatusCode
                from concurrent import futures
                
                # Create multiple objects
                channels = []
                servers = []
                
                for i in range(100):
                    channel = grpc.insecure_channel(f'localhost:{50051 + i}')
                    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
                    channels.append(channel)
                    servers.append(server)
                
                # Force garbage collection
                gc.collect()
                final_memory = process.memory_info().rss
                
                memory_used = final_memory - initial_memory
                
                results[impl] = {
                    'memory_used_mb': memory_used / 1024 / 1024,
                    'initial_memory_mb': initial_memory / 1024 / 1024,
                    'final_memory_mb': final_memory / 1024 / 1024
                }
                print(f"  ✓ Memory used: {results[impl]['memory_used_mb']:.2f} MB")
                print(f"  ✓ Initial memory: {results[impl]['initial_memory_mb']:.2f} MB")
                print(f"  ✓ Final memory: {results[impl]['final_memory_mb']:.2f} MB")
                
            except Exception as e:
                print(f"  ✗ Memory benchmark failed: {e}")
        
        self.results['memory_usage'] = results
        return results
    
    def benchmark_concurrent_operations(self):
        """Benchmark concurrent operations"""
        print("\n=== Concurrent Operations Benchmark ===")
        
        implementations = ['cython', 'rust', 'auto']
        results = {}
        
        for impl in implementations:
            print(f"\nTesting {impl} implementation...")
            
            # Set environment variable
            os.environ['GRPC_PYTHON_IMPLEMENTATION'] = impl
            
            try:
                import grpc
                from concurrent import futures
                import threading
                
                def create_channel_and_server():
                    channel = grpc.insecure_channel('localhost:50051')
                    server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
                    return channel, server
                
                times = []
                
                for i in range(self.iterations // 10):  # Fewer iterations for concurrent test
                    start_time = time.time()
                    
                    # Create multiple threads
                    threads = []
                    for j in range(10):
                        thread = threading.Thread(target=create_channel_and_server)
                        threads.append(thread)
                        thread.start()
                    
                    # Wait for all threads to complete
                    for thread in threads:
                        thread.join()
                    
                    end_time = time.time()
                    times.append(end_time - start_time)
                
                results[impl] = {
                    'mean': statistics.mean(times),
                    'median': statistics.median(times),
                    'min': min(times),
                    'max': max(times),
                    'std': statistics.stdev(times) if len(times) > 1 else 0
                }
                print(f"  ✓ Mean: {results[impl]['mean']:.6f}s")
                print(f"  ✓ Median: {results[impl]['median']:.6f}s")
                print(f"  ✓ Std Dev: {results[impl]['std']:.6f}s")
                
            except Exception as e:
                print(f"  ✗ Concurrent operations failed: {e}")
        
        self.results['concurrent_operations'] = results
        return results
    
    def run_all_benchmarks(self):
        """Run all benchmarks"""
        print("gRPC Rust vs Cython Benchmarking")
        print("=" * 50)
        
        # Run all benchmarks
        self.benchmark_import_time()
        self.benchmark_channel_creation()
        self.benchmark_server_creation()
        self.benchmark_status_codes()
        self.benchmark_memory_usage()
        self.benchmark_concurrent_operations()
        
        return self.results
    
    def generate_report(self, output_file=None):
        """Generate a comprehensive benchmark report"""
        print("\n" + "=" * 50)
        print("BENCHMARK REPORT")
        print("=" * 50)
        
        if not self.results:
            print("No benchmark results available. Run benchmarks first.")
            return
        
        report = {
            'summary': {},
            'detailed_results': self.results
        }
        
        # Generate summary
        for benchmark_name, results in self.results.items():
            if not results:
                continue
                
            print(f"\n{benchmark_name.upper().replace('_', ' ')}:")
            
            # Find the fastest implementation
            fastest_impl = None
            fastest_time = float('inf')
            
            for impl, metrics in results.items():
                if 'mean' in metrics:
                    if metrics['mean'] < fastest_time:
                        fastest_time = metrics['mean']
                        fastest_impl = impl
                    print(f"  {impl}: {metrics['mean']:.6f}s (mean)")
                elif 'memory_used_mb' in metrics:
                    print(f"  {impl}: {metrics['memory_used_mb']:.2f} MB")
            
            if fastest_impl:
                report['summary'][benchmark_name] = {
                    'fastest': fastest_impl,
                    'fastest_time': fastest_time
                }
                print(f"  → Fastest: {fastest_impl}")
        
        # Save report to file
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to: {output_file}")
        
        return report


def main():
    parser = argparse.ArgumentParser(description="Benchmark gRPC Rust vs Cython implementations")
    parser.add_argument("--iterations", type=int, default=100, help="Number of iterations per benchmark")
    parser.add_argument("--warmup", type=int, default=10, help="Number of warmup iterations")
    parser.add_argument("--output", type=str, help="Output file for JSON report")
    parser.add_argument("--implementation", choices=['rust', 'cython', 'both'], default='both', 
                       help="Which implementation to benchmark")
    
    args = parser.parse_args()
    
    # Create benchmark instance
    benchmark = GRPCBenchmark()
    benchmark.iterations = args.iterations
    benchmark.warmup_iterations = args.warmup
    
    # Run benchmarks
    results = benchmark.run_all_benchmarks()
    
    # Generate report
    report = benchmark.generate_report(args.output)
    
    print("\n" + "=" * 50)
    print("BENCHMARK COMPLETED")
    print("=" * 50)
    
    if report and 'summary' in report:
        print("\nSummary:")
        for benchmark_name, summary in report['summary'].items():
            print(f"  {benchmark_name}: {summary['fastest']} is fastest")


if __name__ == "__main__":
    main() 