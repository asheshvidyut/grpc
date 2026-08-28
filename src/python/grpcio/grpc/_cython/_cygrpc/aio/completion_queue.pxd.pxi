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


ctypedef queue[grpc_event] cpp_event_queue


cdef extern from *:
    """
    #ifdef _WIN32
    #include <winsock2.h>
    #else
    #include <unistd.h>
    #if defined(__linux__)
    #include <sys/eventfd.h>
    #include <stdint.h>
    #endif
    #endif

    static int _create_eventfd_or_socketpair(int* read_fd, int* write_fd) {
    #if defined(__linux__)
        int efd = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
        if (efd >= 0) {
            *read_fd = efd;
            *write_fd = efd;
            return 1;
        }
    #endif
        *read_fd = -1;
        *write_fd = -1;
        return 0;
    }

    static void _notify_fd_write_impl(int fd, int is_eventfd) {
    #if defined(__linux__)
        if (is_eventfd) {
            uint64_t val = 1;
            (void)write(fd, &val, sizeof(val));
            return;
        }
    #endif
    #ifdef _WIN32
        send((SOCKET)fd, "1", 1, 0);
    #else
        (void)write(fd, "1", 1);
    #endif
    }

    static void _notify_fd_drain_impl(int fd, int is_eventfd) {
    #if defined(__linux__)
        if (is_eventfd) {
            uint64_t val;
            (void)read(fd, &val, sizeof(val));
            return;
        }
    #endif
    #ifndef _WIN32
        char buf[256];
        (void)read(fd, buf, sizeof(buf));
    #endif
    }

    static void _close_fd_impl(int fd) {
    #ifndef _WIN32
        close(fd);
    #endif
    }
    """
    int _create_eventfd_or_socketpair(int* read_fd, int* write_fd) nogil
    void _notify_fd_write_impl(int fd, int is_eventfd) nogil
    void _notify_fd_drain_impl(int fd, int is_eventfd) nogil
    void _close_fd_impl(int fd) nogil



cdef void _unified_notify_write(int fd, int is_eventfd) noexcept nogil


cdef class BaseCompletionQueue:
    cdef grpc_completion_queue *_cq

    cdef grpc_completion_queue* c_ptr(self)


cdef class _BoundEventLoop:
    cdef readonly object loop
    cdef readonly object read_socket
    cdef bint _has_reader


cdef class PollerCompletionQueue(BaseCompletionQueue):
    cdef bint _shutdown
    cdef cpp_event_queue _queue
    cdef mutex _queue_mutex
    cdef bint _notified
    cdef bint _is_eventfd
    cdef int _read_fd
    cdef int _write_fd
    cdef object _poller_thread  # threading.Thread
    cdef object _read_socket
    cdef object _write_socket
    cdef dict _loops            # Mapping[asyncio.AbstractLoop, _BoundEventLoop]

    cdef int _poll(self) except -1 nogil
    cdef shutdown(self)


