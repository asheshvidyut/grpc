# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Fast path for invoking native (C/C++) RPC handlers and clients.
# Exposes direct C function pointers to users to bypass Python GIL
# and serialization/deserialization overhead completely.

from libc.stdlib cimport malloc, free
from libc.string cimport memcpy, memset
from libc.stdint cimport uint32_t, int64_t
from libc.stdio cimport printf
from libc.stddef cimport size_t
cimport cpython

GRPCIO_NATIVE_ABI_VERSION = 1


# ===========================================================================
# Server Fast Path Dispatcher
# ===========================================================================

def dispatch_native_unary_unary(
    object request_bytes, size_t fn_addr, size_t context_addr, object context):
    """Call a native unary-unary handler.

    Args:
      request_bytes: bytes-like request payload (wire format).
      fn_addr:       address (uintptr_t) of the native function. Obtain via
                     ctypes.cast(lib.symbol, ...).value or similar.
      context_addr:  address of the native context bridge.
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

    call.context = <grpc_native_context_c*><void*>context_addr
    call.req_data = req_data
    call.req_len = <size_t>req_len
    call.resp_data = NULL
    call.resp_len = 0
    call.status = <grpc_native_status>0
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


cdef void _shutdown_and_destroy_cq(grpc_completion_queue* cq) noexcept nogil:
    grpc_completion_queue_shutdown(cq)
    cdef grpc_event ev
    while True:
        ev = grpc_completion_queue_next(cq, gpr_inf_future(GPR_CLOCK_REALTIME), NULL)
        if ev.type == GRPC_QUEUE_SHUTDOWN:
            break
    grpc_completion_queue_destroy(cq)


# ===========================================================================
# Client Fast Path Dynamic C-Core Invoker
# ===========================================================================

cdef int grpcio_native_invoke(
    void* c_channel, 
    grpc_native_client_call_c* call, 
    int64_t timeout_ms) noexcept nogil:
    
    cdef grpc_completion_queue* cq = grpc_completion_queue_create_for_next(NULL)
    if cq == NULL:
        call.status = <grpc_native_status>13 # INTERNAL
        return -1
        
    cdef gpr_timespec deadline = gpr_time_add(
        gpr_now(GPR_CLOCK_REALTIME),
        gpr_time_from_millis(timeout_ms, GPR_TIMESPAN)
    )
    
    cdef grpc_slice method_slice = grpc_slice_from_copied_string(call.method)
    cdef grpc_call* c_call = grpc_channel_create_call(
        <grpc_channel*>c_channel, NULL, 0, cq, method_slice, NULL, deadline, NULL
    )
    grpc_slice_unref(method_slice)
    
    if c_call == NULL:
        _shutdown_and_destroy_cq(cq)
        call.status = <grpc_native_status>13 # INTERNAL
        return -1
        
    cdef grpc_op[6] ops
    cdef grpc_op* op
    memset(ops, 0, sizeof(ops))
    
    # 1. Send initial metadata
    op = &ops[0]
    op.type = GRPC_OP_SEND_INITIAL_METADATA
    op.data.send_initial_metadata.count = 0
    op.data.send_initial_metadata.metadata = NULL
    
    # 2. Send message (request wire bytes)
    cdef grpc_slice request_slice = grpc_slice_from_copied_buffer(call.req_data, call.req_len)
    cdef grpc_byte_buffer* request_buffer = grpc_raw_byte_buffer_create(&request_slice, 1)
    grpc_slice_unref(request_slice)
    op = &ops[1]
    op.type = GRPC_OP_SEND_MESSAGE
    op.data.send_message.send_message = request_buffer
    
    # 3. Send close from client
    op = &ops[2]
    op.type = GRPC_OP_SEND_CLOSE_FROM_CLIENT
    
    # 4. Receive initial metadata
    cdef grpc_metadata_array recv_initial_metadata
    grpc_metadata_array_init(&recv_initial_metadata)
    op = &ops[3]
    op.type = GRPC_OP_RECV_INITIAL_METADATA
    op.data.receive_initial_metadata.receive_initial_metadata = &recv_initial_metadata
    
    # 5. Receive message (response wire bytes)
    cdef grpc_byte_buffer* recv_message = NULL
    op = &ops[4]
    op.type = GRPC_OP_RECV_MESSAGE
    op.data.receive_message.receive_message = &recv_message
    
    # 6. Receive status on client
    cdef grpc_metadata_array recv_trailing_metadata
    grpc_metadata_array_init(&recv_trailing_metadata)
    cdef grpc_status_code status
    cdef grpc_slice status_details = grpc_empty_slice()
    op = &ops[5]
    op.type = GRPC_OP_RECV_STATUS_ON_CLIENT
    op.data.receive_status_on_client.trailing_metadata = &recv_trailing_metadata
    op.data.receive_status_on_client.status = &status
    op.data.receive_status_on_client.status_details = &status_details
    
    cdef grpc_call_error start_error = grpc_call_start_batch(c_call, ops, 6, <void*>1, NULL)
    if start_error != GRPC_CALL_OK:
        grpc_byte_buffer_destroy(request_buffer)
        grpc_call_unref(c_call)
        _shutdown_and_destroy_cq(cq)
        call.status = <grpc_native_status>13 # INTERNAL
        return -1
        
    cdef grpc_event event = grpc_completion_queue_next(cq, deadline, NULL)
    
    cdef int rc = 0
    cdef grpc_byte_buffer_reader reader
    cdef grpc_slice response_slice
    cdef size_t response_len
    cdef int next_status
    
    if event.type == GRPC_OP_COMPLETE and event.success != 0:
        call.status = <grpc_native_status><int>status
        if status == GRPC_STATUS_OK:
            if recv_message != NULL:
                grpc_byte_buffer_reader_init(&reader, recv_message)
                next_status = grpc_byte_buffer_reader_next(&reader, &response_slice)
                if next_status != 0:
                    response_len = grpc_slice_length(response_slice)
                    call.resp_data = <char*>malloc(response_len)
                    if call.resp_data != NULL:
                        memcpy(call.resp_data, grpc_slice_start_ptr(response_slice), response_len)
                        call.resp_len = response_len
                    grpc_slice_unref(response_slice)
                grpc_byte_buffer_reader_destroy(&reader)
                grpc_byte_buffer_destroy(recv_message)
        else:
            response_len = grpc_slice_length(status_details)
            if response_len > 0:
                call.err_msg = <char*>malloc(response_len)
                if call.err_msg != NULL:
                    memcpy(call.err_msg, grpc_slice_start_ptr(status_details), response_len)
                    call.err_msg_len = response_len
    else:
        call.status = <grpc_native_status>4 # DEADLINE_EXCEEDED
        rc = -1
        
    grpc_slice_unref(status_details)
    grpc_metadata_array_destroy(&recv_initial_metadata)
    grpc_metadata_array_destroy(&recv_trailing_metadata)
    grpc_byte_buffer_destroy(request_buffer)
    grpc_call_unref(c_call)
    _shutdown_and_destroy_cq(cq)
    
    return rc


def get_c_core_invoke_fn_addr():
    """Return the address of the C-Core invocation function pointer."""
    return <size_t><void*>grpcio_native_invoke
