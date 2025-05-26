load("//test/cpp/microbenchmarks:grpc_benchmark_config.bzl", "grpc_cc_benchmark")

package(default_visibility = ["//visibility:public"])

grpc_cc_benchmark(
    name = "xds_routing_benchmark",
    srcs = ["xds_routing_benchmark.cc"],
    deps = [
        "//src/core:grpc_xds_client",
    ],
    # If "benchmark" is still needed explicitly with grpc_cc_benchmark,
    # it would typically go into external_deps:
    # external_deps = ["benchmark"], 
    copts = [
        "-O3",
        "-DNDEBUG",
    ],
)