#!/usr/bin/env python3
"""
Comprehensive build script for gRPC Python with Rust and Cython support
"""

import os
import sys
import subprocess
import argparse
import platform


def check_rust_available():
    """Check if Rust is available"""
    try:
        result = subprocess.run(['cargo', '--version'], 
                              capture_output=True, text=True, check=True)
        print(f"✓ Rust available: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ Rust not available")
        return False


def check_cython_available():
    """Check if Cython is available"""
    try:
        import Cython
        print(f"✓ Cython available: {Cython.__version__}")
        return True
    except ImportError:
        print("✗ Cython not available")
        return False


def build_rust_extension():
    """Build the Rust extension"""
    print("\n=== Building Rust Extension ===")
    
    rust_dir = "src/python/grpcio/grpc/_rust"
    if not os.path.exists(rust_dir):
        print(f"✗ Rust directory not found: {rust_dir}")
        return False
    
    os.chdir(rust_dir)
    try:
        print("Running cargo build...")
        subprocess.run(['cargo', 'build', '--release'], check=True)
        print("✓ Rust extension built successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to build Rust extension: {e}")
        return False
    finally:
        os.chdir("../../../..")


def build_cython_extension():
    """Build the Cython extension"""
    print("\n=== Building Cython Extension ===")
    
    try:
        print("Running setup.py build_ext...")
        subprocess.run([sys.executable, 'setup.py', 'build_ext'], check=True)
        print("✓ Cython extension built successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to build Cython extension: {e}")
        return False


def install_package():
    """Install the package"""
    print("\n=== Installing Package ===")
    
    try:
        print("Running setup.py install...")
        subprocess.run([sys.executable, 'setup.py', 'install'], check=True)
        print("✓ Package installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install package: {e}")
        return False


def test_implementation():
    """Test the implementation"""
    print("\n=== Testing Implementation ===")
    
    try:
        # Test basic import
        import grpc
        print("✓ Basic grpc import successful")
        
        # Test feature flags
        from grpc import _feature_flags
        info = _feature_flags.get_implementation_info()
        print(f"✓ Implementation info: {info}")
        
        # Test core functionality
        from grpc import StatusCode
        print(f"✓ StatusCode import successful: {StatusCode.OK}")
        
        print("✓ All tests passed")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False


def clean_build():
    """Clean build artifacts"""
    print("\n=== Cleaning Build Artifacts ===")
    
    patterns = [
        "build/",
        "dist/",
        "*.egg-info/",
        "src/python/grpcio/grpc/_rust/target/",
        "src/python/grpcio/grpc/_cython/cygrpc.cpp",
        "src/python/grpcio/grpc/_cython/*.so",
        "src/python/grpcio/grpc/_cython/*.dylib",
        "src/python/grpcio/grpc/_cython/*.dll",
    ]
    
    for pattern in patterns:
        if os.path.exists(pattern):
            try:
                if os.path.isdir(pattern):
                    import shutil
                    shutil.rmtree(pattern)
                else:
                    os.remove(pattern)
                print(f"✓ Cleaned: {pattern}")
            except Exception as e:
                print(f"✗ Failed to clean {pattern}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Build gRPC Python with Rust/Cython support")
    parser.add_argument("--implementation", choices=["rust", "cython", "both", "auto"], 
                       default="auto", help="Which implementation to build")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts first")
    parser.add_argument("--install", action="store_true", help="Install the package after building")
    parser.add_argument("--test", action="store_true", help="Test the implementation after building")
    parser.add_argument("--skip-build", action="store_true", help="Skip building, just install/test")
    
    args = parser.parse_args()
    
    print("gRPC Python Build Script")
    print("=" * 40)
    
    # Check available tools
    rust_available = check_rust_available()
    cython_available = check_cython_available()
    
    # Clean if requested
    if args.clean:
        clean_build()
    
    # Determine what to build
    build_rust = False
    build_cython = False
    
    if args.implementation == "rust":
        if rust_available:
            build_rust = True
        else:
            print("✗ Rust implementation requested but Rust not available")
            return 1
    elif args.implementation == "cython":
        if cython_available:
            build_cython = True
        else:
            print("✗ Cython implementation requested but Cython not available")
            return 1
    elif args.implementation == "both":
        build_rust = rust_available
        build_cython = cython_available
    else:  # auto
        if rust_available:
            build_rust = True
        elif cython_available:
            build_cython = True
        else:
            print("✗ Neither Rust nor Cython available")
            return 1
    
    # Build implementations
    if not args.skip_build:
        if build_rust:
            if not build_rust_extension():
                return 1
        
        if build_cython:
            if not build_cython_extension():
                return 1
    
    # Install if requested
    if args.install:
        if not install_package():
            return 1
    
    # Test if requested
    if args.test:
        if not test_implementation():
            return 1
    
    print("\n" + "=" * 40)
    print("Build Summary:")
    print(f"  Rust available: {rust_available}")
    print(f"  Cython available: {cython_available}")
    print(f"  Built Rust: {build_rust}")
    print(f"  Built Cython: {build_cython}")
    print("✓ Build completed successfully!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 