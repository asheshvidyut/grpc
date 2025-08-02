#!/usr/bin/env python3
"""
Script to run official gRPC benchmarks comparing Cython vs Rust implementations.
This integrates with the official gRPC benchmarking framework.
"""

import os
import sys
import subprocess
import json
import time
import argparse
import logging
from pathlib import Path


class OfficialBenchmarkRunner:
    """Runner for official gRPC benchmarks"""
    
    def __init__(self):
        self.results = {}
        self.benchmark_dir = Path("tools/run_tests/performance")
        self.scenarios_dir = Path("tools/run_tests/performance/scenarios")
        
    def check_prerequisites(self):
        """Check if all prerequisites are available"""
        print("=== Checking Prerequisites ===")
        
        # Check if we're in the gRPC repo
        if not self.benchmark_dir.exists():
            print(f"✗ Benchmark directory not found: {self.benchmark_dir}")
            return False
        
        # Check for scenario files
        if not self.scenarios_dir.exists():
            print(f"✗ Scenarios directory not found: {self.scenarios_dir}")
            return False
        
        # Check for worker scripts
        worker_scripts = [
            "run_worker_python.sh",
            "run_worker_rust.sh"  # We'll create this
        ]
        
        for script in worker_scripts:
            script_path = self.benchmark_dir / script
            if not script_path.exists():
                print(f"⚠ Worker script not found: {script_path}")
        
        print("✓ Prerequisites check completed")
        return True
    
    def create_rust_worker_script(self):
        """Create the Rust worker script"""
        rust_worker_script = self.benchmark_dir / "run_worker_rust.sh"
        
        script_content = f"""#!/bin/bash
# Rust-based gRPC Python worker script
# This script runs the Rust implementation of gRPC Python

set -ex

cd "$(dirname "$0")/../.."

# Set environment to use Rust implementation
export GRPC_PYTHON_IMPLEMENTATION=rust

# Run the Rust worker
python3 src/python/grpcio/grpc/_rust/benchmark_worker.py "$@"
"""
        
        with open(rust_worker_script, 'w') as f:
            f.write(script_content)
        
        # Make executable
        os.chmod(rust_worker_script, 0o755)
        print(f"✓ Created Rust worker script: {rust_worker_script}")
    
    def run_benchmark_scenario(self, scenario_name, implementation):
        """Run a specific benchmark scenario"""
        print(f"\n=== Running {scenario_name} with {implementation} implementation ===")
        
        # Set environment variable
        os.environ['GRPC_PYTHON_IMPLEMENTATION'] = implementation
        
        # Find scenario file
        scenario_file = self.scenarios_dir / f"{scenario_name}.json"
        if not scenario_file.exists():
            print(f"✗ Scenario file not found: {scenario_file}")
            return None
        
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
            "--scenarios_json", str(scenario_file),
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
                "python_protobuf_sync_streaming_ping_pong_1MB_constant",
                "python_protobuf_sync_unary_ping_pong",
                "python_protobuf_sync_unary_ping_pong_1MB_constant"
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
        print("OFFICIAL BENCHMARK REPORT")
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
                'implementations_tested': ['cython', 'rust']
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
    
    def list_available_scenarios(self):
        """List all available benchmark scenarios"""
        print("=== Available Benchmark Scenarios ===")
        
        if not self.scenarios_dir.exists():
            print("No scenarios directory found")
            return []
        
        scenarios = []
        for scenario_file in self.scenarios_dir.glob("*.json"):
            scenario_name = scenario_file.stem
            scenarios.append(scenario_name)
            print(f"  - {scenario_name}")
        
        return scenarios


def main():
    parser = argparse.ArgumentParser(
        description="Run official gRPC benchmarks comparing Cython vs Rust"
    )
    parser.add_argument("--scenarios", nargs="+", 
                       help="Specific scenarios to run")
    parser.add_argument("--list-scenarios", action="store_true",
                       help="List available scenarios")
    parser.add_argument("--output", type=str,
                       help="Output file for JSON report")
    parser.add_argument("--implementation", choices=['cython', 'rust', 'both'],
                       default='both', help="Which implementation to test")
    
    args = parser.parse_args()
    
    runner = OfficialBenchmarkRunner()
    
    # Check prerequisites
    if not runner.check_prerequisites():
        print("Prerequisites check failed. Please ensure you're in the gRPC repo.")
        return
    
    # Create Rust worker script if needed
    runner.create_rust_worker_script()
    
    # List scenarios if requested
    if args.list_scenarios:
        runner.list_available_scenarios()
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
    print("BENCHMARK COMPLETED")
    print("="*60)


if __name__ == "__main__":
    main() 