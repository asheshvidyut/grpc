#!/bin/bash

# Script to run gRPC tests with Rust implementation in Docker

set -e

echo "Building and running gRPC tests with Rust implementation in Docker..."

# Build the Docker image
docker build -f Dockerfile.test -t grpc-rust-test .

# Run the tests
docker run --rm \
  -v "$(pwd):/workspace" \
  -v bazel-cache:/root/.cache/bazel \
  -e GRPC_PYTHON_IMPLEMENTATION=rust \
  grpc-rust-test \
  bash -c "bazel test --cache_test_results=no '//src/python/...' --test_output=all"

echo "Tests completed!"
