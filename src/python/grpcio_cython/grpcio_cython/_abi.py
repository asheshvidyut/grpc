# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""ctypes bindings for the grpcio_cython C ABI.

These mirror the layout declared in include/grpcio_cython/handler.h. Keep in
sync with that header; the ABI_VERSION constant guards against drift.
"""

import ctypes

ABI_VERSION = 3

INT64_MAX = 9223372036854775807

# Mirrors grpc_native_status enum in handler.h.
STATUS_OK = 0
STATUS_CANCELLED = 1
STATUS_UNKNOWN = 2
STATUS_INVALID_ARGUMENT = 3
STATUS_DEADLINE_EXCEEDED = 4
STATUS_NOT_FOUND = 5
STATUS_ALREADY_EXISTS = 6
STATUS_PERMISSION_DENIED = 7
STATUS_RESOURCE_EXHAUSTED = 8
STATUS_FAILED_PRECONDITION = 9
STATUS_ABORTED = 10
STATUS_OUT_OF_RANGE = 11
STATUS_UNIMPLEMENTED = 12
STATUS_INTERNAL = 13
STATUS_UNAVAILABLE = 14
STATUS_DATA_LOSS = 15
STATUS_UNAUTHENTICATED = 16


class GrpcNativeContext(ctypes.Structure):
    """Mirrors grpc_native_context in handler.h."""


# Callback signatures:
#   int is_cancelled(void* ctx)
#   int get_metadata(void* ctx, const char* key,
#                    const char** value, size_t* len)
#   int set_trailing_metadata(void* ctx, const char* key,
#                             const char* value, size_t len)
#   int64_t time_remaining_ns(void* ctx)
#   const char* peer(void* ctx)
_IS_CANCELLED_CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
_GET_METADATA_CB = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_char_p),
    ctypes.POINTER(ctypes.c_size_t),
)
_SET_TRAILING_CB = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_size_t,
)
_TIME_REMAINING_CB = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p)
_PEER_CB = ctypes.CFUNCTYPE(ctypes.c_char_p, ctypes.c_void_p)


GrpcNativeContext._fields_ = [
    ("ctx", ctypes.c_void_p),
    ("is_cancelled", _IS_CANCELLED_CB),
    ("get_metadata", _GET_METADATA_CB),
    ("set_trailing_metadata", _SET_TRAILING_CB),
    ("time_remaining_ns", _TIME_REMAINING_CB),
    ("peer", _PEER_CB),
]


class GrpcNativeUnaryCall(ctypes.Structure):
    """Mirrors grpc_native_unary_call in handler.h."""

    _fields_ = [
        ("context", ctypes.POINTER(GrpcNativeContext)),
        ("req_data", ctypes.c_char_p),
        ("req_len", ctypes.c_size_t),
        ("resp_data", ctypes.POINTER(ctypes.c_char)),
        ("resp_len", ctypes.c_size_t),
        ("status", ctypes.c_int),
        ("err_msg", ctypes.POINTER(ctypes.c_char)),
        ("err_msg_len", ctypes.c_size_t),
    ]


# grpc_native_unary_unary_fn: int (*)(grpc_native_unary_call*)
UNARY_UNARY_FN = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(GrpcNativeUnaryCall)
)

# uint32_t grpcio_cython_abi_version(void)
ABI_VERSION_FN = ctypes.CFUNCTYPE(ctypes.c_uint32)


# Streaming structs mirror the header. Kept here for completeness; the dispatch
# implementation for streaming RPCs is in _handler.py.
class GrpcNativeWriter(ctypes.Structure):
    pass


GrpcNativeWriter._fields_ = [
    ("ctx", ctypes.c_void_p),
    (
        "emit",
        ctypes.CFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t
        ),
    ),
]


class GrpcNativeUnaryStreamCall(ctypes.Structure):
    _fields_ = [
        ("context", ctypes.POINTER(GrpcNativeContext)),
        ("req_data", ctypes.c_char_p),
        ("req_len", ctypes.c_size_t),
        ("writer", ctypes.POINTER(GrpcNativeWriter)),
        ("status", ctypes.c_int),
        ("err_msg", ctypes.POINTER(ctypes.c_char)),
        ("err_msg_len", ctypes.c_size_t),
    ]


UNARY_STREAM_FN = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(GrpcNativeUnaryStreamCall)
)


class GrpcNativeReader(ctypes.Structure):
    pass


# Reader.read signature: int (*)(void* ctx, const char** out_data,
#                                size_t* out_len)
# Returns 1 (got msg), 0 (end-of-stream), -1 (error).
GrpcNativeReader._fields_ = [
    ("ctx", ctypes.c_void_p),
    (
        "read",
        ctypes.CFUNCTYPE(
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_size_t),
        ),
    ),
]


class GrpcNativeStreamUnaryCall(ctypes.Structure):
    _fields_ = [
        ("context", ctypes.POINTER(GrpcNativeContext)),
        ("reader", ctypes.POINTER(GrpcNativeReader)),
        ("resp_data", ctypes.POINTER(ctypes.c_char)),
        ("resp_len", ctypes.c_size_t),
        ("status", ctypes.c_int),
        ("err_msg", ctypes.POINTER(ctypes.c_char)),
        ("err_msg_len", ctypes.c_size_t),
    ]


STREAM_UNARY_FN = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(GrpcNativeStreamUnaryCall)
)


class GrpcNativeStreamStreamCall(ctypes.Structure):
    _fields_ = [
        ("context", ctypes.POINTER(GrpcNativeContext)),
        ("reader", ctypes.POINTER(GrpcNativeReader)),
        ("writer", ctypes.POINTER(GrpcNativeWriter)),
        ("status", ctypes.c_int),
        ("err_msg", ctypes.POINTER(ctypes.c_char)),
        ("err_msg_len", ctypes.c_size_t),
    ]


STREAM_STREAM_FN = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(GrpcNativeStreamStreamCall)
)


# Map our internal status ints to grpc.StatusCode tuples. Imported lazily by
# _handler.py to avoid a hard dependency at module load time.
_STATUS_NAMES = {
    STATUS_OK: "OK",
    STATUS_CANCELLED: "CANCELLED",
    STATUS_UNKNOWN: "UNKNOWN",
    STATUS_INVALID_ARGUMENT: "INVALID_ARGUMENT",
    STATUS_DEADLINE_EXCEEDED: "DEADLINE_EXCEEDED",
    STATUS_NOT_FOUND: "NOT_FOUND",
    STATUS_ALREADY_EXISTS: "ALREADY_EXISTS",
    STATUS_PERMISSION_DENIED: "PERMISSION_DENIED",
    STATUS_RESOURCE_EXHAUSTED: "RESOURCE_EXHAUSTED",
    STATUS_FAILED_PRECONDITION: "FAILED_PRECONDITION",
    STATUS_ABORTED: "ABORTED",
    STATUS_OUT_OF_RANGE: "OUT_OF_RANGE",
    STATUS_UNIMPLEMENTED: "UNIMPLEMENTED",
    STATUS_INTERNAL: "INTERNAL",
    STATUS_UNAVAILABLE: "UNAVAILABLE",
    STATUS_DATA_LOSS: "DATA_LOSS",
    STATUS_UNAUTHENTICATED: "UNAUTHENTICATED",
}


def status_name(code: int) -> str:
    return _STATUS_NAMES.get(code, "UNKNOWN")
