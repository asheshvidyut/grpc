#!/usr/bin/env python3
"""
Rust extension builder for gRPC Python bindings
"""

import os
import subprocess
import sys
import tempfile
import shutil
from setuptools import Extension
from setuptools.command.build_ext import build_ext


class RustExtension(Extension):
    """Custom Extension class for Rust extensions"""
    
    def __init__(self, name, source_dir):
        super().__init__(name, sources=[])
        self.source_dir = source_dir


class RustBuildExt(build_ext):
    """Custom build_ext command for Rust extensions"""
    
    def build_extension(self, ext):
        if isinstance(ext, RustExtension):
            self.build_rust_extension(ext)
        else:
            super().build_extension(ext)
    
    def build_rust_extension(self, ext):
        """Build the Rust extension using cargo"""
        print(f"Building Rust extension: {ext.name}")
        
        # Change to the source directory
        original_dir = os.getcwd()
        os.chdir(ext.source_dir)
        
        try:
            # Check if Rust is available
            try:
                subprocess.run(['cargo', '--version'], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("Warning: Rust/Cargo not found. Skipping Rust extension build.")
                return
            
            # Build the Rust library
            print(f"Running cargo build in {ext.source_dir}")
            subprocess.check_call([
                'cargo', 'build', '--release'
            ])
            
            # Find the built library
            target_dir = os.path.join('target', 'release')
            if sys.platform == 'win32':
                lib_name = 'grpc_rust_bindings.dll'
            elif sys.platform == 'darwin':
                lib_name = 'libgrpc_rust_bindings.dylib'
            else:
                lib_name = 'libgrpc_rust_bindings.so'
            
            lib_path = os.path.join(target_dir, lib_name)
            
            if not os.path.exists(lib_path):
                raise RuntimeError(f"Built library not found at {lib_path}")
            
            # Copy to the extension directory
            ext_path = self.get_ext_fullpath(ext.name)
            os.makedirs(os.path.dirname(ext_path), exist_ok=True)
            shutil.copy2(lib_path, ext_path)
            
            print(f"✓ Rust extension built successfully: {ext_path}")
            
        except Exception as e:
            print(f"✗ Failed to build Rust extension: {e}")
            # Don't fail the build, just skip the Rust extension
        finally:
            os.chdir(original_dir)


def create_rust_extensions():
    """Create Rust extension definitions"""
    rust_extensions = []
    
    # Define the Rust extension
    rust_ext = RustExtension(
        'grpc._rust.grpc_rust_bindings',
        'src/python/grpcio/grpc/_rust'
    )
    rust_extensions.append(rust_ext)
    
    return rust_extensions


def should_build_rust():
    """Check if we should build Rust extensions"""
    # Check environment variable
    build_rust = os.environ.get('GRPC_PYTHON_BUILD_WITH_RUST', 'False').lower() in ('true', '1', 'yes')
    
    # Check if Rust is available
    try:
        subprocess.run(['cargo', '--version'], check=True, capture_output=True)
        rust_available = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        rust_available = False
    
    return build_rust and rust_available 