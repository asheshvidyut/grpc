#!/usr/bin/env python3
"""
Setup script for gRPC benchmarking environment
"""

import os
import sys
import subprocess
import platform


def check_prerequisites():
    """Check if all prerequisites are available"""
    print("=== Checking Prerequisites ===")
    
    # Check Python version
    python_version = sys.version_info
    print(f"✓ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # Check if we're in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✓ Running in virtual environment")
    else:
        print("ℹ Not in virtual environment (recommended)")
    
    # Check Rust
    try:
        result = subprocess.run(['cargo', '--version'], capture_output=True, text=True, check=True)
        print(f"✓ Rust available: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ Rust not available")
    
    # Check Cython
    try:
        import Cython
        print(f"✓ Cython available: {Cython.__version__}")
    except ImportError:
        print("✗ Cython not available")
    
    # Check setuptools
    try:
        import setuptools
        print(f"✓ setuptools available: {setuptools.__version__}")
    except ImportError:
        print("✗ setuptools not available")


def setup_virtual_environment():
    """Set up virtual environment if needed"""
    print("\n=== Setting up Virtual Environment ===")
    
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✓ Already in virtual environment")
        return True
    
    print("Creating virtual environment...")
    try:
        subprocess.run([sys.executable, '-m', 'venv', 'grpc_env'], check=True)
        print("✓ Virtual environment created")
        
        # Activate virtual environment
        if platform.system() == "Windows":
            activate_script = "grpc_env\\Scripts\\activate"
        else:
            activate_script = "source grpc_env/bin/activate"
        
        print(f"To activate: {activate_script}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to create virtual environment: {e}")
        return False


def install_dependencies():
    """Install required dependencies"""
    print("\n=== Installing Dependencies ===")
    
    dependencies = [
        'setuptools',
        'cython==3.1.1',
        'psutil',  # For memory benchmarking
    ]
    
    for dep in dependencies:
        print(f"Installing {dep}...")
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', dep], check=True)
            print(f"✓ {dep} installed")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install {dep}: {e}")


def build_extensions():
    """Build gRPC extensions"""
    print("\n=== Building Extensions ===")
    
    # Try building Cython first
    print("Building Cython extensions...")
    try:
        subprocess.run([sys.executable, 'setup.py', 'build_ext'], check=True)
        print("✓ Cython extensions built")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to build Cython extensions: {e}")
    
    # Try building Rust extensions
    print("Building Rust extensions...")
    try:
        rust_dir = "src/python/grpcio/grpc/_rust"
        if os.path.exists(rust_dir):
            subprocess.run(['cargo', 'build', '--release'], cwd=rust_dir, check=True)
            print("✓ Rust extensions built")
        else:
            print("ℹ Rust directory not found")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to build Rust extensions: {e}")


def test_imports():
    """Test if gRPC can be imported"""
    print("\n=== Testing Imports ===")
    
    implementations = ['cython', 'rust', 'auto']
    
    for impl in implementations:
        print(f"\nTesting {impl} implementation...")
        
        # Set environment variable
        os.environ['GRPC_PYTHON_IMPLEMENTATION'] = impl
        
        try:
            import grpc
            from grpc import StatusCode
            print(f"  ✓ {impl} import successful")
            
            # Test basic functionality
            channel = grpc.insecure_channel('localhost:50051')
            print(f"  ✓ {impl} channel creation successful")
            
        except Exception as e:
            print(f"  ✗ {impl} import failed: {e}")


def main():
    print("gRPC Benchmarking Environment Setup")
    print("=" * 50)
    
    # Check prerequisites
    check_prerequisites()
    
    # Setup virtual environment
    if not setup_virtual_environment():
        print("Warning: Virtual environment setup failed")
    
    # Install dependencies
    install_dependencies()
    
    # Build extensions
    build_extensions()
    
    # Test imports
    test_imports()
    
    print("\n" + "=" * 50)
    print("SETUP COMPLETED")
    print("=" * 50)
    print("\nTo run benchmarks:")
    print("1. Activate virtual environment: source grpc_env/bin/activate")
    print("2. Run simple benchmark: python simple_benchmark.py")
    print("3. Run comprehensive benchmark: python benchmark_rust_vs_cython.py")
    print("4. Run demo: python demo_rust_integration.py")


if __name__ == "__main__":
    main() 