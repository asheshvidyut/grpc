# Copyright 2020 The gRPC Authors
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

import socket

cdef gpr_timespec _GPR_INF_FUTURE = gpr_inf_future(GPR_CLOCK_REALTIME)
cdef float _POLL_AWAKE_INTERVAL_S = 0.2

# This bool indicates if the event loop impl can monitor a given fd, or has
# loop.add_reader method.
cdef bint _has_fd_monitoring = True

cdef void _unified_notify_write(int fd, int is_eventfd) noexcept nogil:
    _notify_fd_write_impl(fd, is_eventfd)


def _handle_direct_functor(object wrapper, int success):
    wrapper._on_done(success)



cdef class BaseCompletionQueue:

    cdef grpc_completion_queue* c_ptr(self):
        return self._cq


cdef class _BoundEventLoop:

    def __cinit__(self, object loop, object read_socket, object handler):
        global _has_fd_monitoring
        self.loop = loop
        self.read_socket = read_socket
        reader_function = functools.partial(
            handler,
            loop
        )
        if _has_fd_monitoring:
            try:
                self.loop.add_reader(self.read_socket, reader_function)
                self._has_reader = True
            except NotImplementedError:
                _has_fd_monitoring = False
                self._has_reader = False

    def close(self):
        if self.loop:
            if self._has_reader:
                self.loop.remove_reader(self.read_socket)


cdef class PollerCompletionQueue(BaseCompletionQueue):

    def __cinit__(self):
        self._cq = grpc_completion_queue_create_for_next(NULL)
        self._shutdown = False
        self._poller_thread = threading.Thread(target=self._poll_wrapper, daemon=True)
        self._poller_thread.start()

        cdef int read_fd = -1
        cdef int write_fd = -1
        self._is_eventfd = _create_eventfd_or_socketpair(&read_fd, &write_fd)
        if self._is_eventfd:
            self._read_fd = read_fd
            self._write_fd = write_fd
            self._read_socket = read_fd
            self._write_socket = None
        else:
            self._read_socket, self._write_socket = socket.socketpair()
            self._read_socket.setblocking(False)
            self._read_fd = self._read_socket.fileno()
            self._write_fd = self._write_socket.fileno()

        self._loops = {}
        self._queue = cpp_event_queue()
        self._notified = False

    def bind_loop(self, object loop):
        if loop in self._loops:
            return
        else:
            self._loops[loop] = _BoundEventLoop(loop, self._read_socket, self._handle_events)

    cdef int _poll(self) except -1 nogil:
        cdef grpc_event event
        cdef CallbackContext *context
        cdef bint need_notify

        while not self._shutdown:
            event = grpc_completion_queue_next(self._cq,
                                               _GPR_INF_FUTURE,
                                               NULL)

            if event.type == GRPC_QUEUE_TIMEOUT:
                with gil:
                    raise AssertionError("Core should not return GRPC_QUEUE_TIMEOUT!")
            elif event.type == GRPC_QUEUE_SHUTDOWN:
                self._shutdown = True
            else:
                self._queue_mutex.lock()
                need_notify = not self._notified
                self._notified = True
                self._queue.push(event)
                self._queue_mutex.unlock()
                if _has_fd_monitoring:
                    if need_notify:
                        _unified_notify_write(self._write_fd, self._is_eventfd)
                else:
                    with gil:
                        self._handle_events(None)
        return 0

    def _poll_wrapper(self):
        with nogil:
            self._poll()

    cdef shutdown(self):
        for loop in self._loops:
            self._loops.get(loop).close()

        if self._is_eventfd:
            _close_fd_impl(self._read_fd)
        else:
            self._read_socket.close()

        grpc_completion_queue_shutdown(self._cq)
        while not self._shutdown:
            self._poller_thread.join(timeout=_POLL_AWAKE_INTERVAL_S)
        grpc_completion_queue_destroy(self._cq)

        if not self._is_eventfd and self._write_socket is not None:
            self._write_socket.close()

    def _handle_events(self, object context_loop):
        if _has_fd_monitoring:
            if not self._is_eventfd:
                try:
                    self._read_socket.recv(65536)
                except BlockingIOError:
                    pass
            else:
                _notify_fd_drain_impl(self._read_fd, self._is_eventfd)
        self._queue_mutex.lock()
        self._notified = False
        self._queue_mutex.unlock()
        cdef grpc_event event
        cdef grpc_completion_queue_functor *functor
        cdef _DirectFunctorContext *direct_ctx

        while True:
            self._queue_mutex.lock()
            if self._queue.empty():
                self._queue_mutex.unlock()
                break
            else:
                event = self._queue.front()
                self._queue.pop()
                self._queue_mutex.unlock()

            functor = <grpc_completion_queue_functor *>event.tag
            direct_ctx = <_DirectFunctorContext *>event.tag
            loop = <object>direct_ctx.loop
            if loop is context_loop:
                # Executes callbacks: complete the future directly
                functor.functor_run(
                    functor,
                    event.success
                )
            else:
                loop.call_soon_threadsafe(
                    _handle_direct_functor,
                    <object>direct_ctx.wrapper,
                    event.success
                )

