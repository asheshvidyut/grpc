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


def get_active_implementation():
    """
    Get the currently active implementation.
    
    Returns:
        str: 'rust' or 'cython'
    """
    preference = get_implementation_preference()
    
    # For testing purposes, if Cython is explicitly requested, use it
    if preference == 'cython':
        return 'cython'
    
    # For auto mode, default to Cython for now to avoid circular import issues
    if preference == 'auto':
        return 'cython'
    
    # For rust preference, try to use rust but fallback to cython
    if preference == 'rust':
        # For now, just return cython to avoid circular import issues
        print("Warning: Rust implementation requested but using Cython to avoid circular import issues.")
        return 'cython'
    
    return 'cython'  # fallback


def get_implementation_info():
    """Get information about available implementations"""
    info = {
        'preference': get_implementation_preference(),
        'active': get_active_implementation(),
    }
    return info


def print_implementation_info():
    """Print information about available implementations"""
    info = get_implementation_info()
    
    print("gRPC Python Implementation Info:")
    print(f"  Preference: {info['preference']}")
    print(f"  Active implementation: {info['active']}")
    
    if info['active'] == 'cython':
        print("  ✓ Using Cython implementation")
    else:
        print("  ✗ No implementation available")


if __name__ == "__main__":
    print_implementation_info() 