#!/bin/bash
# Build script for gRPC Python Rust Bindings

set -e

echo "Building gRPC Python Rust Bindings..."

# Check if Rust is installed
if ! command -v cargo &> /dev/null; then
    echo "Error: Rust and Cargo are required but not installed."
    echo "Please install Rust from https://rustup.rs/"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "Cargo.toml" ]; then
    echo "Error: Cargo.toml not found. Please run this script from the _rust directory."
    exit 1
fi

# Clean previous builds
echo "Cleaning previous builds..."
cargo clean

# Build in release mode
echo "Building Rust extension..."
cargo build --release

# Check if the library was built successfully
if [ -f "target/release/libgrpc_rust_bindings.dylib" ] || [ -f "target/release/libgrpc_rust_bindings.so" ] || [ -f "target/release/grpc_rust_bindings.dll" ]; then
    echo "✓ Rust extension built successfully!"
else
    echo "✗ Failed to build Rust extension"
    exit 1
fi

# Install the Python package
echo "Installing Python package..."
python setup.py install

echo "✓ Build completed successfully!"
echo ""
echo "You can now test the bindings by running:"
echo "python test_rust_bindings.py" 