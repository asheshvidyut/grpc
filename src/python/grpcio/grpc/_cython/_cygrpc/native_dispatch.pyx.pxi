# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Fast path for invoking native (C/C++) RPC handlers.
#
# The grpcio_native Python package exposes the user-facing API; this module is
# the runtime glue. It calls a user-supplied C function pointer with the GIL
# released and copies the response back into a Python bytes object.
#
# Memory ownership matches the C ABI declared in
# include/grpcio_native/handler.h: the dispatcher owns request bytes; the
# native handler malloc()'s response and error buffers; the dispatcher copies
# them into Python and free()'s the originals.

from libc.stdlib cimport free
from libc.string cimport memcpy
cimport cpython

GRPCIO_NATIVE_ABI_VERSION = 1


cdef object dispatch_native_unary_unary(
    object request_bytes, size_t fn_addr, object context) except *:
    """Call a native unary-unary handler.

    Args:
      request_bytes: bytes-like request payload (wire format).
      fn_addr:       address (uintptr_t) of the native function. Obtain via
                     ctypes.cast(lib.symbol, ...).value or similar.
      context:       grpc.ServicerContext for setting status on error.

    Returns:
      bytes: the response payload from the native handler.
    """
    cdef const char* req_data
    cdef Py_ssize_t req_len
    cdef grpc_native_unary_call_c call
    cdef grpc_native_unary_unary_fn fn
    cdef int rc
    cdef bytes response_bytes
    cdef bytes err_bytes

    cpython.PyBytes_AsStringAndSize(
        bytes(request_bytes), <char**>&req_data, &req_len)

    call.req_data = req_data
    call.req_len = <size_t>req_len
    call.resp_data = NULL
    call.resp_len = 0
    call.status = 0
    call.err_msg = NULL
    call.err_msg_len = 0

    fn = <grpc_native_unary_unary_fn><void*>fn_addr
    with nogil:
        rc = fn(&call)

    if rc != 0:
        if call.resp_data != NULL:
            free(call.resp_data)
        if call.err_msg != NULL:
            free(call.err_msg)
        _set_internal_error(context, b"native handler returned non-zero rc")
        return b""

    if call.resp_data != NULL and call.resp_len > 0:
        response_bytes = call.resp_data[:call.resp_len]
        free(call.resp_data)
    else:
        if call.resp_data != NULL:
            free(call.resp_data)
        response_bytes = b""

    if call.err_msg != NULL and call.err_msg_len > 0:
        err_bytes = call.err_msg[:call.err_msg_len]
        free(call.err_msg)
        _apply_status(context, call.status, err_bytes)
    else:
        if call.err_msg != NULL:
            free(call.err_msg)
        if call.status != 0:
            _apply_status(context, call.status, b"")

    return response_bytes


cdef void _set_internal_error(object context, bytes details) except *:
    import grpc
    context.set_code(grpc.StatusCode.INTERNAL)
    context.set_details(details.decode("utf-8", errors="replace"))


cdef void _apply_status(object context, int status, bytes err) except *:
    if status == 0:
        return
    import grpc
    # Map our C-side status int to grpc.StatusCode. Status values mirror the
    # public gRPC status codes; do a name lookup to be robust to ordering.
    cdef dict _by_value = {
        0: grpc.StatusCode.OK,
        1: grpc.StatusCode.CANCELLED,
        2: grpc.StatusCode.UNKNOWN,
        3: grpc.StatusCode.INVALID_ARGUMENT,
        4: grpc.StatusCode.DEADLINE_EXCEEDED,
        5: grpc.StatusCode.NOT_FOUND,
        6: grpc.StatusCode.ALREADY_EXISTS,
        7: grpc.StatusCode.PERMISSION_DENIED,
        8: grpc.StatusCode.RESOURCE_EXHAUSTED,
        9: grpc.StatusCode.FAILED_PRECONDITION,
        10: grpc.StatusCode.ABORTED,
        11: grpc.StatusCode.OUT_OF_RANGE,
        12: grpc.StatusCode.UNIMPLEMENTED,
        13: grpc.StatusCode.INTERNAL,
        14: grpc.StatusCode.UNAVAILABLE,
        15: grpc.StatusCode.DATA_LOSS,
        16: grpc.StatusCode.UNAUTHENTICATED,
    }
    context.set_code(_by_value.get(status, grpc.StatusCode.UNKNOWN))
    if err:
        context.set_details(err.decode("utf-8", errors="replace"))


def validate_native_abi(size_t version_fn_addr):
    """Check that a loaded library's ABI version matches the runtime.

    Called by grpcio_native at .so load time to fail fast on incompatibility.
    """
    cdef grpcio_native_abi_version_fn version_fn = (
        <grpcio_native_abi_version_fn><void*>version_fn_addr)
    cdef uint32_t reported
    with nogil:
        reported = version_fn()
    if reported != GRPCIO_NATIVE_ABI_VERSION:
        raise RuntimeError(
            "grpcio_native ABI version mismatch: library reports v%d, "
            "runtime expects v%d" % (reported, GRPCIO_NATIVE_ABI_VERSION))
    return reported
