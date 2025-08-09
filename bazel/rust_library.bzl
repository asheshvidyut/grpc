# Copyright 2021 The gRPC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Custom rules for gRPC Python Rust bindings"""

def rust_library(name, deps = [], py_deps = [], rust_srcs = [], py_srcs = [], **kwargs):
    """Compiles a Rust library for Python bindings and wraps it in a py_library.

    Builds a Rust library using cargo and creates a Python module that can be imported.
    The library is built as a cdylib that can be loaded by Python. The produced
    shared object is always exposed to Python as `<name>.so` for simplicity, with
    the underlying platform-specific filename copied into that path.

    Args:
        name: Name for the rule.
        deps: Rust dependencies (unused placeholder for future integration).
        py_deps: Pure Python dependencies of the final library.
        rust_srcs: Rust source files to track for rebuilds.
        py_srcs: Python source files for the wrapper package (e.g. __init__.py).
        **kwargs: Extra keyword arguments passed to the py_library.
    """

    native.genrule(
        name = name + "_rust_build",
        srcs = rust_srcs + [
            "//src/python/grpcio/grpc/_rust:Cargo.toml",
            "//src/python/grpcio/grpc/_rust:Cargo.lock",
        ],
        outs = [name + ".so"],
        cmd = """
        set -exuo pipefail
        cargo_toml=$(location //src/python/grpcio/grpc/_rust:Cargo.toml)
        src_dir="$$(dirname $$cargo_toml)"
        build_dir="$$(mktemp -d)"
        cd "$$src_dir"
        CARGO_TARGET_DIR="$$build_dir" cargo build --release --lib
        echo "Build dir: $$build_dir"
        ls -la "$$build_dir/release" || true
        artifact=""
        for f in \
          "$$build_dir/release/libgrpc_rust_bindings.so" \
          "$$build_dir/release/libgrpc_rust_bindings.dylib" \
          "$$build_dir/release/grpc_rust_bindings.dll" \
          "$$build_dir/release/libgrpc_rust_bindings.dll" \
          "$$build_dir/release/grpc_rust_bindings.so" \
          "$$build_dir/release/grpc_rust_bindings.dylib"; do
          if [ -f "$$f" ]; then
            artifact="$$f"
            break
          fi
        done
        if [ -z "$$artifact" ]; then
          echo "Could not find built Rust library in $$build_dir/release" >&2
          ls -la "$$build_dir/release" || true
          exit 1
        fi
        mkdir -p "$(@D)"
        echo "Copying artifact: $$artifact -> $@"
        install -m 0644 "$$artifact" "$@"
        echo "Output created: $@"
        ls -la "$(@D)" || true
        rm -rf "$$build_dir"
        """,
        message = "Building Rust library for " + name,
    )

    data = [name + ".so"]
    data += kwargs.pop("data", [])

    native.py_library(
        name = name,
        srcs = py_srcs,
        deps = py_deps,
        srcs_version = "PY3",
        data = data,
        **kwargs
    )
