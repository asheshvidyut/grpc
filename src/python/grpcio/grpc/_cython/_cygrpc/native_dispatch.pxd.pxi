# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from libc.stdint cimport uint32_t
from libc.stddef cimport size_t


# Mirror of grpc_native_unary_call in include/grpcio_native/handler.h.
cdef extern from *:
    ctypedef struct grpc_native_unary_call_c:
        const char* req_data
        size_t req_len
        char* resp_data
        size_t resp_len
        int status
        char* err_msg
        size_t err_msg_len

# Function pointer type for grpc_native_unary_unary_fn.
ctypedef int (*grpc_native_unary_unary_fn)(grpc_native_unary_call_c* call) noexcept nogil

# Function pointer type for grpcio_native_abi_version.
ctypedef uint32_t (*grpcio_native_abi_version_fn)() noexcept nogil

cdef object dispatch_native_unary_unary(
    object request_bytes, size_t fn_addr, object context) except *
