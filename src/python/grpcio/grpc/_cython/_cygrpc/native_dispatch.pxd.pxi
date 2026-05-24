# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Fast path C-ABI definitions for both server and client JIT fast paths.

from libc.stdint cimport uint32_t, int64_t
from libc.stddef cimport size_t

cdef extern from "src/python/grpcio_native/include/grpcio_native/handler.h":
    # ---- Status Enum ----
    ctypedef enum grpc_native_status "grpc_native_status":
        pass

    # ---- Opaque Contexts ----
    ctypedef struct grpc_native_context_c "grpc_native_context":
        pass

    # ---- Server Fast Path C-ABI ----
    ctypedef struct grpc_native_unary_call_c "grpc_native_unary_call":
        grpc_native_context_c* context
        const char* req_data
        size_t req_len
        char* resp_data
        size_t resp_len
        grpc_native_status status
        char* err_msg
        size_t err_msg_len

    ctypedef int (*grpc_native_unary_unary_fn)(grpc_native_unary_call_c* call) noexcept nogil
    ctypedef uint32_t (*grpcio_native_abi_version_fn)() noexcept nogil

    # ---- Client Fast Path C-ABI ----
    ctypedef struct grpc_native_client_call_c "grpc_native_client_call":
        const char* method
        const char* req_data
        size_t req_len
        char* resp_data
        size_t resp_len
        grpc_native_status status
        char* err_msg
        size_t err_msg_len


