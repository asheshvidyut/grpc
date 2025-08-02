#!/usr/bin/env python3
"""
Feature flags for gRPC Python implementations
"""

import os
import sys


def get_implementation_preference():
    """
    Get the preferred implementation based on environment variables and availability.
    
    Returns:
        str: 'rust', 'cython', or 'auto'
    """
    # Check environment variable
    env_pref = os.environ.get('GRPC_PYTHON_IMPLEMENTATION', 'auto').lower()
    
    if env_pref in ('rust', 'cython', 'auto'):
        return env_pref
    
    # Default to auto
    return 'auto'


def is_rust_available():
    """Check if Rust implementation is available"""
    try:
        from grpc._rust import grpc_rust_bindings
        return True
    except ImportError:
        return False


def is_cython_available():
    """Check if Cython implementation is available"""
    try:
        # Check if the module exists and has the expected attribute
        import grpc._cython
        if hasattr(grpc._cython, 'cygrpc'):
            return True
        return False
    except ImportError:
        return False


def get_active_implementation():
    """
    Get the currently active implementation.
    
    Returns:
        str: 'rust' or 'cython'
    """
    preference = get_implementation_preference()
    
    if preference == 'rust':
        if is_rust_available():
            return 'rust'
        elif is_cython_available():
            print("Warning: Rust implementation requested but not available. Falling back to Cython.")
            return 'cython'
        else:
            raise ImportError("Neither Rust nor Cython implementation is available")
    
    elif preference == 'cython':
        if is_cython_available():
            return 'cython'
        elif is_rust_available():
            print("Warning: Cython implementation requested but not available. Falling back to Rust.")
            return 'rust'
        else:
            raise ImportError("Neither Cython nor Rust implementation is available")
    
    else:  # auto
        if is_rust_available():
            return 'rust'
        elif is_cython_available():
            return 'cython'
        else:
            raise ImportError("No gRPC implementation is available")
    
    return 'cython'  # fallback


def get_implementation_info():
    """Get information about available implementations"""
    info = {
        'preference': get_implementation_preference(),
        'rust_available': is_rust_available(),
        'cython_available': is_cython_available(),
        'active': get_active_implementation(),
    }
    return info


def print_implementation_info():
    """Print information about available implementations"""
    info = get_implementation_info()
    
    print("gRPC Python Implementation Info:")
    print(f"  Preference: {info['preference']}")
    print(f"  Rust available: {info['rust_available']}")
    print(f"  Cython available: {info['cython_available']}")
    print(f"  Active implementation: {info['active']}")
    
    if info['active'] == 'rust':
        print("  ✓ Using Rust implementation")
    elif info['active'] == 'cython':
        print("  ✓ Using Cython implementation")
    else:
        print("  ✗ No implementation available")


if __name__ == "__main__":
    print_implementation_info() 