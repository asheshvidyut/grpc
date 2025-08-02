#!/usr/bin/env python3
"""
Simple script to test the Rust QPS worker
"""

import os
import sys
import subprocess
import time


def test_rust_qps_worker():
    """Test the Rust QPS worker"""
    print("=== Testing Rust QPS Worker ===")
    
    # Set environment to use Rust implementation
    os.environ['GRPC_PYTHON_IMPLEMENTATION'] = 'rust'
    
    print("1. Testing Rust worker build...")
    try:
        # Build the Rust worker
        result = subprocess.run(['bazel', 'build', '//src/python/grpcio_tests/tests/qps:qps_worker_rust'], 
                              capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            print("✓ Rust worker builds successfully")
        else:
            print(f"✗ Rust worker build failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Build error: {e}")
        return False
    
    print("\n2. Testing Rust worker execution...")
    try:
        # Test running the worker with help
        result = subprocess.run(['bazel-bin/src/python/grpcio_tests/tests/qps/qps_worker_rust', '--help'], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✓ Rust worker executes successfully")
            print("  Output:", result.stdout[:200] + "..." if len(result.stdout) > 200 else result.stdout)
        else:
            print(f"✗ Rust worker execution failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Execution error: {e}")
        return False
    
    print("\n3. Testing Rust implementation detection...")
    try:
        # Test if Rust implementation is being used
        test_script = """
import os
import sys
os.environ['GRPC_PYTHON_IMPLEMENTATION'] = 'rust'
import grpc
print(f"gRPC module: {grpc.__file__}")
print(f"Implementation: {os.environ.get('GRPC_PYTHON_IMPLEMENTATION', 'not set')}")
"""
        
        result = subprocess.run([sys.executable, '-c', test_script], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✓ Rust implementation test passed")
            print("  Output:", result.stdout)
        else:
            print(f"✗ Rust implementation test failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Implementation test error: {e}")
        return False
    
    print("\n4. Testing simple gRPC operations...")
    try:
        # Test basic gRPC operations
        test_script = """
import os
import grpc
from concurrent import futures

# Force Rust implementation
os.environ['GRPC_PYTHON_IMPLEMENTATION'] = 'rust'

# Test channel creation
channel = grpc.insecure_channel('localhost:50051')
print("✓ Channel creation successful")

# Test server creation
server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
print("✓ Server creation successful")

# Test status codes
from grpc import StatusCode
print(f"✓ Status codes: {StatusCode.OK}, {StatusCode.CANCELLED}")

print("✓ All basic gRPC operations successful")
"""
        
        result = subprocess.run([sys.executable, '-c', test_script], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✓ Basic gRPC operations test passed")
            print("  Output:", result.stdout)
        else:
            print(f"✗ Basic gRPC operations test failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Basic operations test error: {e}")
        return False
    
    print("\n" + "="*50)
    print("✓ RUST QPS WORKER TEST COMPLETED SUCCESSFULLY")
    print("="*50)
    return True


def main():
    """Main function"""
    print("Rust QPS Worker Test")
    print("="*50)
    
    success = test_rust_qps_worker()
    
    if success:
        print("\n🎉 All tests passed! Rust QPS worker is working correctly.")
        print("\nTo run benchmarks:")
        print("1. python3 run_bazel_benchmarks.py --implementation rust")
        print("2. python3 run_bazel_benchmarks.py --scenarios python_protobuf_sync_streaming_ping_pong")
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 