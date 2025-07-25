# gRPC Bazel BUILD file.
#
# Copyright 2023 gRPC authors.
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

load(
    "//bazel:grpc_build_system.bzl",
    "grpc_cc_library",
)

licenses(["reciprocal"])

package(
    default_visibility = ["//visibility:public"],
    features = [
        "layering_check",
    ],
)

grpc_cc_library(
    name = "csm_observability",
    srcs = [
        "csm_observability.cc",
        "metadata_exchange.cc",
    ],
    hdrs = [
        "csm_observability.h",
        "metadata_exchange.h",
        "//:include/grpcpp/ext/csm_observability.h",
    ],
    external_deps = [
        "absl/functional:any_invocable",
        "absl/log:check",
        "absl/log:log",
        "absl/status:statusor",
        "absl/strings",
        "google_cloud_cpp:opentelemetry",
        "otel/api",
        "otel/sdk/src/metrics",
        "otel/sdk:headers",
        "@com_google_protobuf//upb/base",
        "@com_google_protobuf//upb/mem",
    ],
    tags = [
        # TODO(b/332369798): Remove after fixing bug
        "grpc:otel-namespace-calamity",
    ],
    visibility = ["//:__subpackages__"],
    deps = [
        "//:call_tracer",
        "//:gpr",
        "//:gpr_platform",
        "//:grpc_base",
        "//:protobuf_struct_upb",
        "//:uri",
        "//src/core:channel_args",
        "//src/core:env",
        "//src/core:error",
        "//src/core:metadata_batch",
        "//src/core:slice",
        "//src/core:xds_enabled_server",
        "//src/cpp/ext/otel:otel_plugin",
    ],
)
