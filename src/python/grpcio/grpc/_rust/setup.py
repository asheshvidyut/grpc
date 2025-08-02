#!/usr/bin/env python3
"""
Setup script for gRPC Python Rust Bindings
"""

import os
import sys
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import subprocess

class RustExtension(Extension):
    def __init__(self, name, source_dir):
        super().__init__(name, sources=[])
        self.source_dir = source_dir

class RustBuildExt(build_ext):
    def build_extension(self, ext):
        if isinstance(ext, RustExtension):
            self.build_rust_extension(ext)
        else:
            super().build_extension(ext)
    
    def build_rust_extension(self, ext):
        """Build the Rust extension using cargo"""
        import subprocess
        import tempfile
        import shutil
        
        # Change to the source directory
        original_dir = os.getcwd()
        os.chdir(ext.source_dir)
        
        try:
            # Build the Rust library
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
            
        finally:
            os.chdir(original_dir)

def main():
    setup(
        name='grpc-rust-bindings',
        version='0.1.0',
        description='gRPC Python Rust Bindings',
        author='gRPC Authors',
        author_email='grpc-io@googlegroups.com',
        url='https://github.com/grpc/grpc',
        ext_modules=[
            RustExtension('grpc_rust_bindings', 'src/python/grpcio/grpc/_rust')
        ],
        cmdclass={
            'build_ext': RustBuildExt,
        },
        install_requires=[
            'pyo3>=0.20',
        ],
        python_requires='>=3.7',
        classifiers=[
            'Development Status :: 3 - Alpha',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: Apache Software License',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.7',
            'Programming Language :: Python :: 3.8',
            'Programming Language :: Python :: 3.9',
            'Programming Language :: Python :: 3.10',
            'Programming Language :: Python :: 3.11',
            'Programming Language :: Rust',
            'Topic :: Software Development :: Libraries :: Python Modules',
        ],
    )

if __name__ == '__main__':
    main() 