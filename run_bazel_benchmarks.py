#!/usr/bin/env python3
"""
Script to run official gRPC benchmarks using Bazel for both Cython and Rust implementations.
This follows the official gRPC performance testing framework.
"""

import os
import sys
import subprocess
import json
import time
import argparse
import logging
from pathlib import Path


class BazelBenchmarkRunner:
    """Runner for official gRPC benchmarks using Bazel"""
    
    def __init__(self):
        self.results = {}
        self.benchmark_dir = Path("tools/run_tests/performance")
        
    def check_prerequisites(self):
        """Check if all prerequisites are available"""
        print("=== Checking Prerequisites ===")
        
        # Check if we're in the gRPC repo
        if not self.benchmark_dir.exists():
            print(f"✗ Benchmark directory not found: {self.benchmark_dir}")
            return False
        
        # Check if Bazel is available
        try:
            subprocess.run(['bazel', '--version'], check=True, capture_output=True)
            print("✓ Bazel available")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("✗ Bazel not available")
            return False
        
        print("✓ Prerequisites check completed")
        return True
    
    def build_workers(self):
        """Build both Cython and Rust workers using Bazel"""
        print("\n=== Building Workers ===")
        
        workers = [
            "//src/python/grpcio_tests/tests/qps:qps_worker",  # Cython
            "//src/python/grpcio_tests/tests/qps:qps_worker_rust",  # Rust
        ]
        
        for worker in workers:
            print(f"Building {worker}...")
            try:
                subprocess.run(['bazel', 'build', worker], check=True)
                print(f"✓ {worker} built successfully")
            except subprocess.CalledProcessError as e:
                print(f"✗ Failed to build {worker}: {e}")
                return False
        
        return True
    
    def run_benchmark_scenario(self, scenario_name, implementation):
        """Run a specific benchmark scenario"""
        print(f"\n=== Running {scenario_name} with {implementation} implementation ===")
        
        # Set environment variable
        os.environ['GRPC_PYTHON_IMPLEMENTATION'] = implementation
        
        # Build performance tools
        print("Building performance tools...")
        try:
            subprocess.run(["./build_performance.sh"], 
                         cwd=self.benchmark_dir, check=True)
            print("✓ Performance tools built")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to build performance tools: {e}")
            return None
        
        # Run the benchmark
        worker_script = f"run_worker_{implementation}.sh"
        if implementation == "rust":
            worker_script = "run_worker_rust.sh"
        
        cmd = [
            "./run_performance_tests.py",
            "--scenarios_json", f'{{"scenarios": [{{"name": "{scenario_name}", "warmup_seconds": 5, "benchmark_seconds": 30, "num_servers": 1, "num_clients": 1, "server_config": {{"server_type": "ASYNC_SERVER", "port": 0}}, "client_config": {{"client_type": "SYNC_CLIENT", "rpc_type": "STREAMING", "load_params": {{"closed_loop": {{}}}}}}}}]}}',
            "--workers", f"python:{worker_script}",
            "--driver_port", "10000"
        ]
        
        print(f"Running: {' '.join(cmd)}")
        
        start_time = time.time()
        try:
            result = subprocess.run(cmd, 
                                  cwd=self.benchmark_dir,
                                  capture_output=True,
                                  text=True,
                                  timeout=300)  # 5 minute timeout
            
            end_time = time.time()
            
            if result.returncode == 0:
                print("✓ Benchmark completed successfully")
                return {
                    'implementation': implementation,
                    'scenario': scenario_name,
                    'duration': end_time - start_time,
                    'output': result.stdout,
                    'error': result.stderr
                }
            else:
                print(f"✗ Benchmark failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("✗ Benchmark timed out")
            return None
        except Exception as e:
            print(f"✗ Benchmark error: {e}")
            return None
    
    def run_comparison_benchmarks(self, scenarios=None):
        """Run benchmarks comparing Cython vs Rust"""
        if scenarios is None:
            scenarios = [
                "python_protobuf_sync_streaming_ping_pong",
                "python_protobuf_sync_unary_ping_pong"
            ]
        
        implementations = ['cython', 'rust']
        
        for scenario in scenarios:
            print(f"\n{'='*60}")
            print(f"BENCHMARKING SCENARIO: {scenario}")
            print(f"{'='*60}")
            
            scenario_results = {}
            
            for impl in implementations:
                result = self.run_benchmark_scenario(scenario, impl)
                if result:
                    scenario_results[impl] = result
                    self.results[scenario] = scenario_results
            
            # Compare results
            if len(scenario_results) == 2:
                self.compare_scenario_results(scenario, scenario_results)
    
    def compare_scenario_results(self, scenario, results):
        """Compare results for a specific scenario"""
        print(f"\n--- Comparison for {scenario} ---")
        
        cython_result = results.get('cython')
        rust_result = results.get('rust')
        
        if cython_result and rust_result:
            print(f"Cython duration: {cython_result['duration']:.2f}s")
            print(f"Rust duration: {rust_result['duration']:.2f}s")
            
            if cython_result['duration'] > 0:
                improvement = ((cython_result['duration'] - rust_result['duration']) / 
                             cython_result['duration']) * 100
                print(f"Rust improvement: {improvement:.1f}%")
    
    def generate_report(self, output_file=None):
        """Generate a comprehensive benchmark report"""
        print("\n" + "="*60)
        print("BAZEL BENCHMARK REPORT")
        print("="*60)
        
        if not self.results:
            print("No benchmark results available.")
            return
        
        report = {
            'summary': {},
            'detailed_results': self.results,
            'metadata': {
                'timestamp': time.time(),
                'scenarios_tested': list(self.results.keys()),
                'implementations_tested': ['cython', 'rust'],
                'build_system': 'bazel'
            }
        }
        
        # Generate summary
        for scenario, results in self.results.items():
            print(f"\n{scenario.upper().replace('_', ' ')}:")
            
            cython_result = results.get('cython')
            rust_result = results.get('rust')
            
            if cython_result and rust_result:
                print(f"  Cython: {cython_result['duration']:.2f}s")
                print(f"  Rust: {rust_result['duration']:.2f}s")
                
                if cython_result['duration'] > 0:
                    improvement = ((cython_result['duration'] - rust_result['duration']) / 
                                 cython_result['duration']) * 100
                    print(f"  → Rust improvement: {improvement:.1f}%")
                    
                    report['summary'][scenario] = {
                        'cython_duration': cython_result['duration'],
                        'rust_duration': rust_result['duration'],
                        'improvement_percent': improvement
                    }
        
        # Save report
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to: {output_file}")
        
        return report
    
    def test_worker_builds(self):
        """Test that both workers can be built successfully"""
        print("\n=== Testing Worker Builds ===")
        
        workers = [
            ("Cython", "//src/python/grpcio_tests/tests/qps:qps_worker"),
            ("Rust", "//src/python/grpcio_tests/tests/qps:qps_worker_rust"),
        ]
        
        for name, target in workers:
            print(f"Testing {name} worker...")
            try:
                result = subprocess.run(['bazel', 'build', target], 
                                      capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    print(f"✓ {name} worker builds successfully")
                else:
                    print(f"✗ {name} worker build failed: {result.stderr}")
            except Exception as e:
                print(f"✗ {name} worker build error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Run official gRPC benchmarks using Bazel for Cython vs Rust"
    )
    parser.add_argument("--scenarios", nargs="+", 
                       help="Specific scenarios to run")
    parser.add_argument("--output", type=str,
                       help="Output file for JSON report")
    parser.add_argument("--implementation", choices=['cython', 'rust', 'both'],
                       default='both', help="Which implementation to test")
    parser.add_argument("--test-builds", action="store_true",
                       help="Test that workers can be built")
    
    args = parser.parse_args()
    
    runner = BazelBenchmarkRunner()
    
    # Check prerequisites
    if not runner.check_prerequisites():
        print("Prerequisites check failed. Please ensure you're in the gRPC repo with Bazel.")
        return
    
    # Test builds if requested
    if args.test_builds:
        runner.test_worker_builds()
        return
    
    # Build workers
    if not runner.build_workers():
        print("Failed to build workers. Please check the build errors above.")
        return
    
    # Run benchmarks
    if args.implementation == 'both':
        runner.run_comparison_benchmarks(args.scenarios)
    else:
        # Run single implementation
        scenarios = args.scenarios or [
            "python_protobuf_sync_streaming_ping_pong"
        ]
        for scenario in scenarios:
            runner.run_benchmark_scenario(scenario, args.implementation)
    
    # Generate report
    report = runner.generate_report(args.output)
    
    print("\n" + "="*60)
    print("BAZEL BENCHMARK COMPLETED")
    print("="*60)


if __name__ == "__main__":
    main() 