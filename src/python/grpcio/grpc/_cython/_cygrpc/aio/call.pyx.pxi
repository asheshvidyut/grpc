# Copyright 2019 gRPC authors.
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

from grpc import _observability
from libc.string cimport memset

_EMPTY_FLAGS = 0
_EMPTY_MASK = 0
_IMMUTABLE_EMPTY_METADATA = tuple()

_UNKNOWN_CANCELLATION_DETAILS = 'RPC cancelled for unknown reason.'
_OK_CALL_REPRESENTATION = ('<{} of RPC that terminated with:\n'
                           '\tstatus = {}\n'
                           '\tdetails = "{}"\n'
                           '>')

_NON_OK_CALL_REPRESENTATION = ('<{} of RPC that terminated with:\n'
                               '\tstatus = {}\n'
                               '\tdetails = "{}"\n'
                               '\tdebug_error_string = "{}"\n'
                               '>')


cdef int _get_send_initial_metadata_flags(object wait_for_ready) except *:
    cdef int flags = 0
    # Wait-for-ready can be None, which means using default value in Core.
    if wait_for_ready is not None:
        flags |= InitialMetadataFlags.wait_for_ready_explicitly_set
        if wait_for_ready:
            flags |= InitialMetadataFlags.wait_for_ready

    flags &= InitialMetadataFlags.used_mask
    return flags


cdef void _py_decref_user_data(void *user_data) noexcept:
    cpython.Py_DECREF(<cpython.PyObject *>user_data)


cdef inline grpc_slice _slice_from_bytes_fast(object py_bytes):
    if py_bytes is None or len(py_bytes) == 0:
        return grpc_empty_slice()
    cdef char* buf = <char*>cpython.PyBytes_AS_STRING(py_bytes)
    cdef size_t length = <size_t>cpython.PyBytes_GET_SIZE(py_bytes)
    cpython.Py_INCREF(py_bytes)
    return grpc_slice_new_with_user_data(buf, length, _py_decref_user_data, <void*>py_bytes)


cdef inline bytes _extract_bytes_from_byte_buffer(grpc_byte_buffer *byte_buffer):
    cdef grpc_byte_buffer_reader message_reader
    cdef bint message_reader_status
    cdef grpc_slice message_slice
    cdef size_t message_slice_length
    cdef list chunks = None
    cdef bytes response_bytes = None

    if byte_buffer != NULL:
        message_reader_status = grpc_byte_buffer_reader_init(
            &message_reader, byte_buffer)
        if message_reader_status:
            if grpc_byte_buffer_reader_next(&message_reader, &message_slice):
                message_slice_length = grpc_slice_length(message_slice)
                if message_slice_length > 0:
                    response_bytes = cpython.PyBytes_FromStringAndSize(
                        <const char *>grpc_slice_start_ptr(message_slice),
                        message_slice_length)
                else:
                    response_bytes = b""
                grpc_slice_unref(message_slice)

                while grpc_byte_buffer_reader_next(&message_reader, &message_slice):
                    if chunks is None:
                        chunks = [response_bytes]
                    message_slice_length = grpc_slice_length(message_slice)
                    if message_slice_length > 0:
                        chunks.append(cpython.PyBytes_FromStringAndSize(
                            <const char *>grpc_slice_start_ptr(message_slice),
                            message_slice_length))
                    grpc_slice_unref(message_slice)

                if chunks is not None:
                    response_bytes = b"".join(chunks)
            else:
                response_bytes = b""
            grpc_byte_buffer_reader_destroy(&message_reader)
        grpc_byte_buffer_destroy(byte_buffer)
    return response_bytes


cdef class _UnaryCallContext:

    def __cinit__(self, _AioCall call, object future, object loop):
        self.functor_ctx.functor.functor_run = self._static_functor_run
        self.functor_ctx.loop = <cpython.PyObject*>loop
        self.functor_ctx.wrapper = <cpython.PyObject*>self
        self.call = call
        self.future = future
        self._c_send_initial_metadata = NULL
        self._c_send_initial_metadata_count = 0
        self._send_message_buffer = NULL
        self._recv_message_buffer = NULL
        self._status_code = StatusCode.ok
        self._status_details = grpc_empty_slice()
        self._status_error_string = NULL
        grpc_metadata_array_init(&self._recv_initial_metadata)
        grpc_metadata_array_init(&self._recv_trailing_metadata)
        cpython.Py_INCREF(self)

    @staticmethod
    cdef void _static_functor_run(
            grpc_completion_queue_functor* functor,
            int success) noexcept:
        cdef _DirectFunctorContext *ctx = <_DirectFunctorContext *>functor
        cdef _UnaryCallContext self = <_UnaryCallContext>ctx.wrapper
        try:
            self._on_done(success)
        finally:
            cpython.Py_DECREF(self)

    cdef void _on_done(self, int success):
        cdef tuple py_initial_metadata
        if self._recv_initial_metadata.count > 0:
            py_initial_metadata = _metadata(&self._recv_initial_metadata)
        else:
            py_initial_metadata = _IMMUTABLE_EMPTY_METADATA
        self.call._set_initial_metadata(py_initial_metadata)

        cdef tuple py_trailing_metadata
        if self._recv_trailing_metadata.count > 0:
            py_trailing_metadata = _metadata(&self._recv_trailing_metadata)
        else:
            py_trailing_metadata = _IMMUTABLE_EMPTY_METADATA

        cdef str py_details = ""
        if grpc_slice_length(self._status_details) > 0:
            py_details = _decode(_slice_bytes(self._status_details))
        cdef str py_error_string = ""
        if self._status_error_string != NULL:
            py_error_string = _decode(self._status_error_string)
            gpr_free(<void*>self._status_error_string)
            self._status_error_string = NULL

        self.call._set_status(AioRpcStatus(
            self._status_code,
            py_details,
            py_trailing_metadata,
            py_error_string,
        ))

        # Decode received message bytes (fast zero copy path)
        cdef bytes response_bytes = None
        if self._recv_message_buffer != NULL:
            response_bytes = _extract_bytes_from_byte_buffer(self._recv_message_buffer)
            self._recv_message_buffer = NULL

        if self._send_message_buffer != NULL:
            grpc_byte_buffer_destroy(self._send_message_buffer)
            self._send_message_buffer = NULL

        if self._c_send_initial_metadata != NULL:
            _release_c_metadata(self._c_send_initial_metadata, self._c_send_initial_metadata_count)
            self._c_send_initial_metadata = NULL

        grpc_metadata_array_destroy(&self._recv_initial_metadata)
        grpc_metadata_array_destroy(&self._recv_trailing_metadata)
        grpc_slice_unref(self._status_details)

        if not self.future.cancelled():
            if success == 0:
                self.future.set_exception(InternalError("Failed unary_unary batch"))
            elif self._status_code == StatusCode.ok:
                self.future.set_result(response_bytes)
            else:
                self.future.set_result(None)



cdef class _SendMessageContext:

    def __cinit__(self, object future, object loop):
        self.functor_ctx.functor.functor_run = self._static_functor_run
        self.functor_ctx.loop = <cpython.PyObject*>loop
        self.functor_ctx.wrapper = <cpython.PyObject*>self
        self.future = future
        self._message_buffer = NULL
        cpython.Py_INCREF(self)

    @staticmethod
    cdef void _static_functor_run(
            grpc_completion_queue_functor* functor,
            int success) noexcept:
        cdef _DirectFunctorContext *ctx = <_DirectFunctorContext *>functor
        cdef _SendMessageContext self = <_SendMessageContext>ctx.wrapper
        try:
            self._on_done(success)
        finally:
            cpython.Py_DECREF(self)

    cdef void _on_done(self, int success):
        if self._message_buffer != NULL:
            grpc_byte_buffer_destroy(self._message_buffer)
            self._message_buffer = NULL
        if not self.future.cancelled():
            if success == 0:
                self.future.set_exception(InternalError("Failed send_message"))
            else:
                self.future.set_result(None)


cdef class _ReceiveMessageContext:

    def __cinit__(self, object future, object loop):
        self.functor_ctx.functor.functor_run = self._static_functor_run
        self.functor_ctx.loop = <cpython.PyObject*>loop
        self.functor_ctx.wrapper = <cpython.PyObject*>self
        self.future = future
        self._message_buffer = NULL
        cpython.Py_INCREF(self)

    @staticmethod
    cdef void _static_functor_run(
            grpc_completion_queue_functor* functor,
            int success) noexcept:
        cdef _DirectFunctorContext *ctx = <_DirectFunctorContext *>functor
        cdef _ReceiveMessageContext self = <_ReceiveMessageContext>ctx.wrapper
        try:
            self._on_done(success)
        finally:
            cpython.Py_DECREF(self)

    cdef void _on_done(self, int success):
        cdef bytes response_bytes = None
        if self._message_buffer != NULL:
            response_bytes = _extract_bytes_from_byte_buffer(self._message_buffer)
            self._message_buffer = NULL

        if not self.future.cancelled():
            if success == 0:
                self.future.set_result(None)
            else:
                self.future.set_result(response_bytes)



cdef class _SendCloseContext:

    def __cinit__(self, object future, object loop):
        self.functor_ctx.functor.functor_run = self._static_functor_run
        self.functor_ctx.loop = <cpython.PyObject*>loop
        self.functor_ctx.wrapper = <cpython.PyObject*>self
        self.future = future
        cpython.Py_INCREF(self)

    @staticmethod
    cdef void _static_functor_run(
            grpc_completion_queue_functor* functor,
            int success) noexcept:
        cdef _DirectFunctorContext *ctx = <_DirectFunctorContext *>functor
        cdef _SendCloseContext self = <_SendCloseContext>ctx.wrapper
        try:
            self._on_done(success)
        finally:
            cpython.Py_DECREF(self)

    cdef void _on_done(self, int success):
        if not self.future.cancelled():
            if success == 0:
                self.future.set_exception(InternalError("Failed send_close"))
            else:
                self.future.set_result(None)




cdef class _AioCall(GrpcCallWrapper):

    def __cinit__(self, AioChannel channel, object deadline,
                  bytes method, CallCredentials call_credentials, object wait_for_ready,
                  object registered_call_handle):
        init_grpc_aio()
        self.call = NULL
        self._channel = channel
        self._loop = channel.loop
        self._references = []
        self._status = None
        self._initial_metadata = None
        self._waiters_status = []
        self._waiters_initial_metadata = []
        self._done_callbacks = []
        self._is_locally_cancelled = False
        self._deadline = deadline
        self._send_initial_metadata_flags = _get_send_initial_metadata_flags(wait_for_ready)
        self._call_tracer_capsule = None
        self._create_grpc_call(deadline, method, call_credentials, registered_call_handle)

    def __dealloc__(self):
        if self.call:
            grpc_call_unref(self.call)
        shutdown_grpc_aio()

    def _repr(self) -> str:
        """Assembles the RPC representation string."""
        # This needs to be loaded at run time once everything
        # has been loaded.
        from grpc import _common

        if not self.done():
            return '<{} object>'.format(self.__class__.__name__)

        if self._status.code() is StatusCode.ok:
            return _OK_CALL_REPRESENTATION.format(
                self.__class__.__name__,
                _common.CYGRPC_STATUS_CODE_TO_STATUS_CODE[self._status.code()],
                self._status.details())
        else:
            return _NON_OK_CALL_REPRESENTATION.format(
                self.__class__.__name__,
                self._status.details(),
                _common.CYGRPC_STATUS_CODE_TO_STATUS_CODE[self._status.code()],
                self._status.debug_error_string())

    def __repr__(self) -> str:
        return self._repr()

    def __str__(self) -> str:
        return self._repr()

    cdef void _create_grpc_call(self,
                                object deadline,
                                bytes method,
                                CallCredentials credentials,
                                object registered_call_handle) except *:
        """Creates the corresponding Core object for this RPC.

        For unary calls, the grpc_call lives shortly and can be destroyed after
        invoke start_batch. However, if either side is streaming, the grpc_call
        life span will be longer than one function. So, it would better save it
        as an instance variable than a stack variable, which reflects its
        nature in Core.
        """
        cdef grpc_slice method_slice
        cdef gpr_timespec c_deadline = _timespec_from_time(deadline)
        cdef grpc_call_error set_credentials_error

        if registered_call_handle:
            self.call = grpc_channel_create_registered_call(
                self._channel.channel,
                NULL,
                _EMPTY_MASK,
                global_completion_queue(),
                cpython.PyLong_AsVoidPtr(registered_call_handle),
                c_deadline,
                NULL
            )
            self._maybe_save_registered_method(method)
        else:
            method_slice = grpc_slice_from_copied_buffer(
                <const char *> method,
                <size_t> len(method)
            )
            self.call = grpc_channel_create_call(
                self._channel.channel,
                NULL,
                _EMPTY_MASK,
                global_completion_queue(),
                method_slice,
                NULL,
                c_deadline,
                NULL
            )
            grpc_slice_unref(method_slice)

        if credentials is not None:
            set_credentials_error = grpc_call_set_credentials(self.call, credentials.c())
            if set_credentials_error != GRPC_CALL_OK:
                raise InternalError("Credentials couldn't have been set: {0}".format(set_credentials_error))

        self._maybe_set_client_call_tracer_on_call(method)

    cdef void _maybe_save_registered_method(self, bytes method) except *:
        with _observability.get_plugin() as plugin:
            if plugin and plugin.observability_enabled:
                plugin.save_registered_method(method)

    cdef void _maybe_set_client_call_tracer_on_call(self, bytes method) except *:
        # TODO(zgoda): use channel args to exclude those metrics.
        for exclude_prefix in _observability._SERVICES_TO_EXCLUDE:
            if exclude_prefix in method:
                return
        with _observability.get_plugin() as plugin:
            if not (plugin and plugin.observability_enabled):
                return
            try:
                capsule = plugin.create_client_call_tracer(method, self._channel.target)
                capsule_ptr = cpython.PyCapsule_GetPointer(capsule, CLIENT_CALL_TRACER)
                _set_call_tracer(self.call, capsule_ptr)
                self._call_tracer_capsule = capsule
            except Exception as e:
                _LOGGER.exception(f"Failed to set client call tracer for {method}")


    cdef void _set_status(self, AioRpcStatus status) except *:
        cdef list waiters

        # No more waiters should be expected since status has been set.
        self._status = status

        if self._initial_metadata is None:
            self._set_initial_metadata(_IMMUTABLE_EMPTY_METADATA)

        for waiter in self._waiters_status:
            if not waiter.done():
                waiter.set_result(None)
        self._waiters_status = []

        callbacks = self._done_callbacks
        self._done_callbacks = []
        for callback in callbacks:
            callback()

    cdef void _set_initial_metadata(self, tuple initial_metadata) except *:
        if self._initial_metadata is not None:
            # Some gRPC calls might end before the initial metadata arrived in
            # the Call object. That causes this method to be invoked twice: 1.
            # filled with an empty metadata; 2. updated with the actual user
            # provided metadata.
            return

        cdef list waiters

        # No more waiters should be expected since initial metadata has been
        # set.
        self._initial_metadata = initial_metadata

        for waiter in self._waiters_initial_metadata:
            if not waiter.done():
                waiter.set_result(None)
        self._waiters_initial_metadata = []

    def add_done_callback(self, callback):
        if self.done():
            callback()
        else:
            self._done_callbacks.append(callback)

    def time_remaining(self):
        if self._deadline is None:
            return None
        else:
            return max(0, self._deadline - time.time())

    def cancel(self, str details):
        """Cancels the RPC in Core with given RPC status.

        Above abstractions must invoke this method to set Core objects into
        proper state.
        """
        self._is_locally_cancelled = True

        cdef object details_bytes
        cdef char *c_details
        cdef grpc_call_error error

        self._set_status(AioRpcStatus(
            StatusCode.cancelled,
            details,
            None,
            None,
        ))

        details_bytes = str_to_bytes(details)
        self._references.append(details_bytes)
        c_details = <char *>details_bytes
        # By implementation, grpc_call_cancel_with_status always return OK
        error = grpc_call_cancel_with_status(
            self.call,
            StatusCode.cancelled,
            c_details,
            NULL,
        )
        assert error == GRPC_CALL_OK

    def done(self):
        """Returns if the RPC call has finished.

        Checks if the status has been provided, either
        because the RPC finished or because was cancelled.

        Returns:
            True if the RPC can be considered finished.
        """
        return self._status is not None

    def cancelled(self):
        """Returns if the RPC was cancelled.

        Returns:
            True if the RPC was cancelled.
        """
        if not self.done():
            return False

        return self._status.code() == StatusCode.cancelled

    async def status(self):
        """Returns the status of the RPC call.

        It returns the finished status of the RPC. If the RPC
        has not finished yet this function will wait until the RPC
        gets finished.

        Returns:
            Finished status of the RPC as an AioRpcStatus object.
        """
        if self._status is not None:
            return self._status

        future = self._loop.create_future()
        self._waiters_status.append(future)
        await future

        return self._status

    def is_ok(self):
        """Returns if the RPC is ended with ok."""
        return self.done() and self._status.code() == StatusCode.ok

    async def initial_metadata(self):
        """Returns the initial metadata of the RPC call.

        If the initial metadata has not been received yet this function will
        wait until the RPC gets finished.

        Returns:
            The tuple object with the initial metadata.
        """
        if self._initial_metadata is not None:
            return self._initial_metadata

        future = self._loop.create_future()
        self._waiters_initial_metadata.append(future)
        await future

        return self._initial_metadata

    def is_locally_cancelled(self):
        """Returns if the RPC was cancelled locally.

        Returns:
            True when was cancelled locally, False when was cancelled remotely or
            is still ongoing.
        """
        if self._is_locally_cancelled:
            return True

        return False

    def set_internal_error(self, str error_str):
        self._set_status(AioRpcStatus(
            StatusCode.internal,
            'Internal error from Core',
            (),
            error_str,
        ))

    def start_unary_unary(self,
                          bytes request,
                          tuple outbound_initial_metadata,
                          object context = None):
        """Starts a unary-unary RPC, returning a Future resolving to response bytes."""
        if context is not None:
            set_instrumentation_context_on_call_aio(self, context)

        cdef object future = self._loop.create_future()
        cdef _UnaryCallContext ctx = _UnaryCallContext(self, future, self._loop)

        cdef grpc_op c_ops[6]
        cdef size_t nops = 6
        memset(c_ops, 0, sizeof(c_ops))

        # 0: SEND_INITIAL_METADATA
        c_ops[0].type = GRPC_OP_SEND_INITIAL_METADATA
        c_ops[0].flags = self._send_initial_metadata_flags
        if outbound_initial_metadata:
            _store_c_metadata(
                outbound_initial_metadata,
                &ctx._c_send_initial_metadata,
                &ctx._c_send_initial_metadata_count
            )
            c_ops[0].data.send_initial_metadata.metadata = ctx._c_send_initial_metadata
            c_ops[0].data.send_initial_metadata.count = ctx._c_send_initial_metadata_count
            c_ops[0].data.send_initial_metadata.maybe_compression_level.is_set = 0
        else:
            c_ops[0].data.send_initial_metadata.metadata = NULL
            c_ops[0].data.send_initial_metadata.count = 0
            c_ops[0].data.send_initial_metadata.maybe_compression_level.is_set = 0

        # 1: SEND_MESSAGE
        c_ops[1].type = GRPC_OP_SEND_MESSAGE
        c_ops[1].flags = _EMPTY_FLAGS
        cdef grpc_slice message_slice
        if request is not None:
            message_slice = _slice_from_bytes_fast(request)
            ctx._send_message_buffer = grpc_raw_byte_buffer_create(&message_slice, 1)
            grpc_slice_unref(message_slice)
            c_ops[1].data.send_message.send_message = ctx._send_message_buffer
        else:
            c_ops[1].data.send_message.send_message = NULL

        # 2: SEND_CLOSE_FROM_CLIENT
        c_ops[2].type = GRPC_OP_SEND_CLOSE_FROM_CLIENT
        c_ops[2].flags = _EMPTY_FLAGS

        # 3: RECV_INITIAL_METADATA
        c_ops[3].type = GRPC_OP_RECV_INITIAL_METADATA
        c_ops[3].flags = _EMPTY_FLAGS
        c_ops[3].data.receive_initial_metadata.receive_initial_metadata = &ctx._recv_initial_metadata

        # 4: RECV_MESSAGE
        c_ops[4].type = GRPC_OP_RECV_MESSAGE
        c_ops[4].flags = _EMPTY_FLAGS
        c_ops[4].data.receive_message.receive_message = &ctx._recv_message_buffer

        # 5: RECV_STATUS_ON_CLIENT
        c_ops[5].type = GRPC_OP_RECV_STATUS_ON_CLIENT
        c_ops[5].flags = _EMPTY_FLAGS
        c_ops[5].data.receive_status_on_client.status = &ctx._status_code
        c_ops[5].data.receive_status_on_client.status_details = &ctx._status_details
        c_ops[5].data.receive_status_on_client.trailing_metadata = &ctx._recv_trailing_metadata
        c_ops[5].data.receive_status_on_client.error_string = &ctx._status_error_string

        cdef grpc_call_error error
        with nogil:
            error = grpc_call_start_batch(
                self.call,
                c_ops,
                nops,
                &ctx.functor_ctx.functor,
                NULL
            )
        if error != GRPC_CALL_OK:
            grpc_call_error_string = grpc_call_error_to_string(error).decode()
            raise ExecuteBatchError("Failed grpc_call_start_batch: {} with grpc_call_error value: '{}'".format(error, grpc_call_error_string))

        return future

    async def unary_unary(self,
                          bytes request,
                          tuple outbound_initial_metadata,
                          object context = None):
        """Performs a unary unary RPC.

        Args:
          request: the serialized requests in bytes.
          outbound_initial_metadata: optional outbound metadata.
          context: instrumentation context.
        """
        return await self.start_unary_unary(request, outbound_initial_metadata, context)

    async def _handle_status_once_received(self):
        """Handles the status sent by peer once received."""
        cdef ReceiveStatusOnClientOperation op = ReceiveStatusOnClientOperation(_EMPTY_FLAGS)
        cdef tuple ops = (op,)
        await execute_batch(self, ops, self._loop)

        # Halts if the RPC is locally cancelled
        if self._is_locally_cancelled:
            return

        self._set_status(AioRpcStatus(
            op.code(),
            op.details(),
            op.trailing_metadata(),
            op.error_string(),
        ))

    def send_serialized_message_fast(self, bytes message):
        cdef object future = self._loop.create_future()
        cdef _SendMessageContext ctx = _SendMessageContext(future, self._loop)

        cdef grpc_op c_op
        memset(&c_op, 0, sizeof(c_op))
        c_op.type = GRPC_OP_SEND_MESSAGE
        c_op.flags = _EMPTY_FLAGS
        cdef grpc_slice message_slice
        if message is not None:
            message_slice = _slice_from_bytes_fast(message)
            ctx._message_buffer = grpc_raw_byte_buffer_create(&message_slice, 1)
            grpc_slice_unref(message_slice)
            c_op.data.send_message.send_message = ctx._message_buffer
        else:
            c_op.data.send_message.send_message = NULL


        cdef grpc_call_error error
        with nogil:
            error = grpc_call_start_batch(self.call, &c_op, 1, &ctx.functor_ctx.functor, NULL)
        if error != GRPC_CALL_OK:
            grpc_call_error_string = grpc_call_error_to_string(error).decode()
            raise ExecuteBatchError("Failed send_message: {} with grpc_call_error value: '{}'".format(error, grpc_call_error_string))
        return future

    def receive_serialized_message_fast(self):
        cdef object future = self._loop.create_future()
        cdef _ReceiveMessageContext ctx = _ReceiveMessageContext(future, self._loop)

        cdef grpc_op c_op
        memset(&c_op, 0, sizeof(c_op))
        c_op.type = GRPC_OP_RECV_MESSAGE
        c_op.flags = _EMPTY_FLAGS
        c_op.data.receive_message.receive_message = &ctx._message_buffer

        cdef grpc_call_error error
        with nogil:
            error = grpc_call_start_batch(self.call, &c_op, 1, &ctx.functor_ctx.functor, NULL)
        if error != GRPC_CALL_OK:
            grpc_call_error_string = grpc_call_error_to_string(error).decode()
            raise ExecuteBatchError("Failed receive_message: {} with grpc_call_error value: '{}'".format(error, grpc_call_error_string))
        return future

    async def receive_serialized_message(self):
        """Receives one single raw message in bytes."""
        cdef bytes received_message = await self.receive_serialized_message_fast()
        if received_message is not None:
            return received_message
        else:
            return EOF

    async def send_serialized_message(self, bytes message):
        """Sends one single raw message in bytes."""
        await self.send_serialized_message_fast(message)


    def send_receive_close_fast(self):
        cdef object future = self._loop.create_future()
        cdef _SendCloseContext ctx = _SendCloseContext(future, self._loop)

        cdef grpc_op c_op
        memset(&c_op, 0, sizeof(c_op))
        c_op.type = GRPC_OP_SEND_CLOSE_FROM_CLIENT
        c_op.flags = _EMPTY_FLAGS

        cdef grpc_call_error error
        with nogil:
            error = grpc_call_start_batch(self.call, &c_op, 1, &ctx.functor_ctx.functor, NULL)
        if error != GRPC_CALL_OK:
            grpc_call_error_string = grpc_call_error_to_string(error).decode()
            raise ExecuteBatchError("Failed send_close: {} with grpc_call_error value: '{}'".format(error, grpc_call_error_string))
        return future


    async def send_receive_close(self):
        """Half close the RPC on the client-side."""
        await self.send_receive_close_fast()


    async def initiate_unary_stream(self,
                           bytes request,
                           tuple outbound_initial_metadata,
                           object context = None):
        """Implementation of the start of a unary-stream call."""
        # Peer may prematurely end this RPC at any point. We need a coroutine
        # that watches if the server sends the final status.
        status_task = self._loop.create_task(self._handle_status_once_received())

        cdef tuple outbound_ops
        cdef Operation initial_metadata_op = SendInitialMetadataOperation(
            outbound_initial_metadata,
            self._send_initial_metadata_flags)
        cdef Operation send_message_op = SendMessageOperation(
            request,
            _EMPTY_FLAGS)
        cdef Operation send_close_op = SendCloseFromClientOperation(
            _EMPTY_FLAGS)

        if context is not None:
            set_instrumentation_context_on_call_aio(self, context)
        outbound_ops = (
            initial_metadata_op,
            send_message_op,
            send_close_op,
        )

        try:
            # Sends out the request message.
            await execute_batch(self,
                                outbound_ops,
                                self._loop)

            # Receives initial metadata.
            self._set_initial_metadata(
                await _receive_initial_metadata(self,
                                                self._loop),
            )
        except ExecuteBatchError as batch_error:
            # Core should explain why this batch failed
            await status_task

    async def stream_unary(self,
                           tuple outbound_initial_metadata,
                           object metadata_sent_observer,
                           object context = None):
        """Actual implementation of the complete unary-stream call.

        Needs to pay extra attention to the raise mechanism. If we want to
        propagate the final status exception, then we have to raise it.
        Othersize, it would end normally and raise `StopAsyncIteration()`.
        """
        try:
            # Sends out initial_metadata ASAP.
            await _send_initial_metadata(self,
                                        outbound_initial_metadata,
                                        self._send_initial_metadata_flags,
                                        self._loop)
            # Notify upper level that sending messages are allowed now.
            metadata_sent_observer()

            # Receives initial metadata.
            self._set_initial_metadata(
                await _receive_initial_metadata(self, self._loop)
            )
        except ExecuteBatchError:
            # Core should explain why this batch failed
            await self._handle_status_once_received()

            # Allow upper layer to proceed only if the status is set
            metadata_sent_observer()
            return None

        cdef tuple inbound_ops
        cdef ReceiveMessageOperation receive_message_op = ReceiveMessageOperation(_EMPTY_FLAGS)
        cdef ReceiveStatusOnClientOperation receive_status_on_client_op = ReceiveStatusOnClientOperation(_EMPTY_FLAGS)

        if context is not None:
            set_instrumentation_context_on_call_aio(self, context)
        inbound_ops = (receive_message_op, receive_status_on_client_op)

        # Executes all operations in one batch.
        await execute_batch(self,
                            inbound_ops,
                            self._loop)

        cdef grpc_status_code code
        code = receive_status_on_client_op.code()

        self._set_status(AioRpcStatus(
            code,
            receive_status_on_client_op.details(),
            receive_status_on_client_op.trailing_metadata(),
            receive_status_on_client_op.error_string(),
        ))

        if code == StatusCode.ok:
            return receive_message_op.message()
        else:
            return None

    async def initiate_stream_stream(self,
                           tuple outbound_initial_metadata,
                           object metadata_sent_observer,
                           object context = None):
        """Actual implementation of the complete stream-stream call.

        Needs to pay extra attention to the raise mechanism. If we want to
        propagate the final status exception, then we have to raise it.
        Othersize, it would end normally and raise `StopAsyncIteration()`.
        """
        # Peer may prematurely end this RPC at any point. We need a coroutine
        # that watches if the server sends the final status.
        status_task = self._loop.create_task(self._handle_status_once_received())

        if context is not None:
            set_instrumentation_context_on_call_aio(self, context)

        try:
            # Sends out initial_metadata ASAP.
            await _send_initial_metadata(self,
                                        outbound_initial_metadata,
                                        self._send_initial_metadata_flags,
                                        self._loop)
            # Notify upper level that sending messages are allowed now.
            metadata_sent_observer()

            # Receives initial metadata.
            self._set_initial_metadata(
                await _receive_initial_metadata(self, self._loop)
            )
        except ExecuteBatchError as batch_error:
            # Core should explain why this batch failed
            await status_task

            # Allow upper layer to proceed only if the status is set
            metadata_sent_observer()