# Copyright 2026 gRPC authors.
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

load("//bazel:grpc_build_system.bzl", "grpc_cc_test", "grpc_package")
load("//test/cpp/microbenchmarks:grpc_benchmark_config.bzl", "grpc_cc_benchmark")

licenses(["notice"])

grpc_package(
    name = "test/core/server/bm_isolation",
    features = [
        "layering_check",
        "parse_headers",
    ],
)

grpc_cc_benchmark(
    name = "bm_server_registered_method",
    srcs = [
        "bm_server_registered_method.cc",
        "bucketed_hash_lookup.h",
        "trie_registered_method_lookup.h",
    ],
    external_deps = [
        "absl/strings",
    ],
    deps = [
        "//:gpr",
        "//:grpc",
        "//:server",
    ],
)
