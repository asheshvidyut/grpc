#!/bin/bash

# Script to run gRPC tests with Cython implementation in Docker

set -e

echo "Building and running gRPC tests with Cython implementation in Docker..."

# Build the Docker image
docker build -f Dockerfile.test-simple -t grpc-cython-test .

# Run the tests with more memory and better error handling
docker run --rm \
  --memory=4g \
  --memory-swap=4g \
  --cpus=2 \
  -v "$(pwd):/workspace" \
  -v bazel-cache:/root/.cache/bazel \
  -e GRPC_PYTHON_IMPLEMENTATION=cython \
  -e BAZEL_BUILD_OPTS="--local_test_jobs=1 --test_timeout=300" \
  grpc-cython-test

echo "Tests completed!"
