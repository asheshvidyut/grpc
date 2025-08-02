#!/usr/bin/env python3
"""
Demo script showing the Rust integration with gRPC Python
"""

import os
import sys

def demo_feature_flags():
    """Demonstrate the feature flag system"""
    print("=== Feature Flags Demo ===")
    
    # Set environment variable to control implementation
    os.environ['GRPC_PYTHON_IMPLEMENTATION'] = 'auto'
    
    try:
        from grpc import _feature_flags
        info = _feature_flags.get_implementation_info()
        
        print(f"Implementation preference: {info['preference']}")
        print(f"Rust available: {info['rust_available']}")
        print(f"Cython available: {info['cython_available']}")
        print(f"Active implementation: {info['active']}")
        
        # Print detailed info
        _feature_flags.print_implementation_info()
        
    except ImportError as e:
        print(f"Feature flags not available: {e}")


def demo_basic_grpc():
    """Demonstrate basic gRPC functionality"""
    print("\n=== Basic gRPC Demo ===")
    
    try:
        import grpc
        from grpc import StatusCode
        
        print("✓ gRPC import successful")
        print(f"✓ StatusCode.OK: {StatusCode.OK}")
        
        # Test channel creation
        channel = grpc.insecure_channel('localhost:50051')
        print("✓ Channel creation successful")
        
        # Test server creation
        from concurrent import futures
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        print("✓ Server creation successful")
        
    except Exception as e:
        print(f"✗ gRPC functionality failed: {e}")


def demo_implementation_switching():
    """Demonstrate switching between implementations"""
    print("\n=== Implementation Switching Demo ===")
    
    # Test with Rust preference
    os.environ['GRPC_PYTHON_IMPLEMENTATION'] = 'rust'
    try:
        from grpc import _feature_flags
        info = _feature_flags.get_implementation_info()
        print(f"With Rust preference: {info['active']}")
    except Exception as e:
        print(f"Rust preference failed: {e}")
    
    # Test with Cython preference
    os.environ['GRPC_PYTHON_IMPLEMENTATION'] = 'cython'
    try:
        from grpc import _feature_flags
        info = _feature_flags.get_implementation_info()
        print(f"With Cython preference: {info['active']}")
    except Exception as e:
        print(f"Cython preference failed: {e}")
    
    # Test with auto preference
    os.environ['GRPC_PYTHON_IMPLEMENTATION'] = 'auto'
    try:
        from grpc import _feature_flags
        info = _feature_flags.get_implementation_info()
        print(f"With auto preference: {info['active']}")
    except Exception as e:
        print(f"Auto preference failed: {e}")


def demo_build_system():
    """Demonstrate the build system integration"""
    print("\n=== Build System Demo ===")
    
    try:
        # Test if Rust builder is available
        from grpc._rust.rust_builder import should_build_rust, create_rust_extensions
        print("✓ Rust builder available")
        
        # Check if we should build Rust
        should_build = should_build_rust()
        print(f"Should build Rust: {should_build}")
        
        # Create Rust extensions
        extensions = create_rust_extensions()
        print(f"Rust extensions created: {len(extensions)}")
        
    except ImportError as e:
        print(f"✗ Rust builder not available: {e}")


def demo_setup_integration():
    """Demonstrate setup.py integration"""
    print("\n=== Setup Integration Demo ===")
    
    try:
        # Test if the modified setup.py can import the Rust components
        import sys
        sys.path.insert(0, 'src/python/grpcio')
        
        # This would normally be done by setup.py
        try:
            from grpc._rust.rust_builder import create_rust_extensions, should_build_rust, RustBuildExt
            print("✓ Rust builder imports successfully")
            
            should_build = should_build_rust()
            print(f"Should build Rust: {should_build}")
            
            if should_build:
                extensions = create_rust_extensions()
                print(f"✓ Created {len(extensions)} Rust extensions")
            else:
                print("ℹ Rust build not enabled")
                
        except ImportError as e:
            print(f"✗ Rust builder import failed: {e}")
            
    except Exception as e:
        print(f"✗ Setup integration failed: {e}")


def main():
    """Run all demos"""
    print("gRPC Python Rust Integration Demo")
    print("=" * 50)
    
    # Run all demos
    demo_feature_flags()
    demo_basic_grpc()
    demo_implementation_switching()
    demo_build_system()
    demo_setup_integration()
    
    print("\n" + "=" * 50)
    print("Demo completed!")
    print("\nTo use the Rust implementation:")
    print("1. Set environment variable: export GRPC_PYTHON_IMPLEMENTATION=rust")
    print("2. Build with: python build_grpc.py --implementation rust --install")
    print("3. Test with: python -c 'import grpc; print(\"Success!\")'")
    
    print("\nTo use the Cython implementation:")
    print("1. Set environment variable: export GRPC_PYTHON_IMPLEMENTATION=cython")
    print("2. Build with: python build_grpc.py --implementation cython --install")
    print("3. Test with: python -c 'import grpc; print(\"Success!\")'")


if __name__ == "__main__":
    main() 