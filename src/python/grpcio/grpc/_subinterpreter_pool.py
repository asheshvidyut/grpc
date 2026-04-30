# Copyright 2026 gRPC authors.
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
"""EXPERIMENTAL sub-interpreter worker pool for gRPC Python servers.

Provides parallel request processing by running servicer handlers inside
dedicated Python sub-interpreters, each with its own GIL (PEP 684).
Requires Python 3.13+.

Communication between the main interpreter and each worker uses OS-level
pipes with length-prefixed byte framing, which are GIL-independent and
work reliably across interpreter boundaries.

TODO(Python 3.14+): Replace OS pipes with ``concurrent.interpreters.Queue``
and ``memoryview``-based zero-copy handoff once Python 3.14 is the minimum.
The Queue/channel API provides C-level thread safety and supports zero-copy
``memoryview`` transfer, avoiding the copy overhead of pipe I/O for large
gRPC payloads.
"""

from __future__ import annotations

import logging
import os
import struct
import sys
import threading
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
)

_LOGGER = logging.getLogger(__name__)

_SUBINTERPRETER_MIN_VERSION = (3, 13)

# Header format for all pipe messages: 4-byte big-endian length prefix.
_LEN_FMT = "!I"
_LEN_SIZE = struct.calcsize(_LEN_FMT)

# Request wire format:
#   method_len (4B) + request_len (4B) + method_bytes + request_bytes
_REQ_HEADER_FMT = "!II"
_REQ_HEADER_SIZE = struct.calcsize(_REQ_HEADER_FMT)

# Response wire format:
#   status_code (4B) + details_len (4B) + response_len (4B)
#   + details_bytes + response_bytes
_RESP_HEADER_FMT = "!III"
_RESP_HEADER_SIZE = struct.calcsize(_RESP_HEADER_FMT)

# Sentinel length value that tells the worker to exit.
_SHUTDOWN_LENGTH = 0xFFFFFFFF


def _is_supported() -> bool:
    """Return True if the runtime supports per-interpreter GIL."""
    if sys.version_info < _SUBINTERPRETER_MIN_VERSION:
        return False
    try:
        import _interpreters  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Byte-buffer packing helpers (used by both main and worker interpreters).
# ---------------------------------------------------------------------------


def _pack_request(method: str, serialized_request: bytes) -> bytes:
    """Pack method name + serialized request into a single bytes buffer."""
    method_bytes = method.encode("utf-8")
    header = struct.pack(
        _REQ_HEADER_FMT, len(method_bytes), len(serialized_request)
    )
    return header + method_bytes + serialized_request


def _unpack_request(data: bytes) -> Tuple[str, bytes]:
    """Unpack method name + serialized request from a bytes buffer."""
    method_len, request_len = struct.unpack_from(_REQ_HEADER_FMT, data)
    offset = _REQ_HEADER_SIZE
    method = data[offset : offset + method_len].decode("utf-8")
    offset += method_len
    serialized_request = data[offset : offset + request_len]
    return method, serialized_request


def _pack_response(
    serialized_response: Optional[bytes],
    status_code: int,
    details: str,
) -> bytes:
    """Pack response into a bytes buffer."""
    details_bytes = details.encode("utf-8")
    resp_bytes = serialized_response or b""
    header = struct.pack(
        _RESP_HEADER_FMT, status_code, len(details_bytes), len(resp_bytes)
    )
    return header + details_bytes + resp_bytes


def _unpack_response(data: bytes) -> Tuple[Optional[bytes], int, str]:
    """Unpack response from a bytes buffer.

    Returns (serialized_response_or_None, status_code, details).
    """
    status_code, details_len, resp_len = struct.unpack_from(
        _RESP_HEADER_FMT, data
    )
    offset = _RESP_HEADER_SIZE
    details = data[offset : offset + details_len].decode("utf-8")
    offset += details_len
    serialized_response: Optional[bytes] = data[offset : offset + resp_len]
    if resp_len == 0:
        serialized_response = None
    return serialized_response, status_code, details


# ---------------------------------------------------------------------------
# Pipe I/O helpers — length-prefixed messages over OS pipes.
# ---------------------------------------------------------------------------


def _pipe_write_msg(fd: int, data: bytes) -> None:
    """Write a length-prefixed message to a pipe fd."""
    header = struct.pack(_LEN_FMT, len(data))
    os.write(fd, header + data)


def _pipe_read_exact(fd: int, n: int) -> bytes:
    """Read exactly *n* bytes from a pipe fd."""
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            raise EOFError("pipe closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _pipe_read_msg(fd: int) -> Optional[bytes]:
    """Read a length-prefixed message. Returns None on shutdown sentinel."""
    header = _pipe_read_exact(fd, _LEN_SIZE)
    (length,) = struct.unpack(_LEN_FMT, header)
    if length == _SHUTDOWN_LENGTH:
        return None
    return _pipe_read_exact(fd, length)


def _pipe_write_shutdown(fd: int) -> None:
    """Write the shutdown sentinel to a pipe fd."""
    os.write(fd, struct.pack(_LEN_FMT, _SHUTDOWN_LENGTH))


# ---------------------------------------------------------------------------
# Worker code template — runs *inside* a sub-interpreter.
#
# This string is passed to _interpreters.run_string(). It must be
# self-contained — no closures over main-interpreter objects.
# The pipe file descriptors are baked in via format().
# ---------------------------------------------------------------------------
_WORKER_CODE_TEMPLATE = '''
import importlib
import os
import struct
import sys
import traceback

_LEN_FMT = "!I"
_LEN_SIZE = 4
_SHUTDOWN_LENGTH = 0xFFFFFFFF
_REQ_HEADER_FMT = "!II"
_REQ_HEADER_SIZE = 8
_RESP_HEADER_FMT = "!III"
_RESP_HEADER_SIZE = 12

_req_fd = {req_read_fd}
_resp_fd = {resp_write_fd}
_ready_fd = {ready_write_fd}

# Sub-interpreters do NOT inherit sys.path from the parent interpreter.
# Restore it so that importlib.import_module() can find servicer modules.
for _p in {sys_path!r}:
    if _p not in sys.path:
        sys.path.append(_p)


def _read_exact(fd, n):
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            raise EOFError("pipe closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


# Import and instantiate servicers.
_handlers = {{}}
_init_error = None

try:
    for _module_path, _class_name, _bindings in {servicer_specs!r}:
        _mod = importlib.import_module(_module_path)
        _cls = getattr(_mod, _class_name)
        _instance = _cls()
        for _method, _deser_path, _ser_path, _attr in _bindings:
            _deser = None
            _ser = None
            if _deser_path:
                _dmod_path, _dfunc = _deser_path.rsplit(".", 1)
                _dmod = importlib.import_module(_dmod_path)
                _deser = getattr(_dmod, _dfunc)
            if _ser_path:
                _smod_path, _sfunc = _ser_path.rsplit(".", 1)
                _smod = importlib.import_module(_smod_path)
                _ser = getattr(_smod, _sfunc)
            _handlers[_method] = (_deser, _ser, getattr(_instance, _attr))
except Exception:
    _init_error = traceback.format_exc()

# Signal readiness (or failure) to the main interpreter.
if _init_error:
    os.write(_ready_fd, b"E")
    os.close(_ready_fd)
    raise RuntimeError("Worker init failed: " + _init_error)
else:
    os.write(_ready_fd, b"R")
    os.close(_ready_fd)

# Worker loop — runs under this sub-interpreter's own GIL.
while True:
    # Read length header
    hdr = _read_exact(_req_fd, _LEN_SIZE)
    length = struct.unpack(_LEN_FMT, hdr)[0]
    if length == _SHUTDOWN_LENGTH:
        break
    raw = _read_exact(_req_fd, length)

    try:
        method_len, request_len = struct.unpack_from(_REQ_HEADER_FMT, raw)
        offset = _REQ_HEADER_SIZE
        method = raw[offset:offset + method_len].decode("utf-8")
        offset += method_len
        serialized_request = raw[offset:offset + request_len]

        handler_info = _handlers.get(method)
        if handler_info is None:
            details_b = ("Method not found: " + method).encode("utf-8")
            resp_header = struct.pack(_RESP_HEADER_FMT, 12, len(details_b), 0)
            resp = resp_header + details_b
        else:
            deser, ser, func = handler_info
            request = deser(serialized_request) if deser else serialized_request
            response = func(request, None)
            serialized_response = ser(response) if ser else response
            if not isinstance(serialized_response, bytes):
                serialized_response = bytes(serialized_response)
            resp_header = struct.pack(
                _RESP_HEADER_FMT, 0, 0, len(serialized_response)
            )
            resp = resp_header + serialized_response
    except Exception:
        tb = traceback.format_exc()
        details_b = ("Handler exception: " + tb).encode("utf-8")
        resp_header = struct.pack(_RESP_HEADER_FMT, 2, len(details_b), 0)
        resp = resp_header + details_b

    # Write response
    os.write(_resp_fd, struct.pack(_LEN_FMT, len(resp)))
    os.write(_resp_fd, resp)
'''


class _WorkerHandle:
    """Manages one sub-interpreter worker thread with OS pipe communication."""

    def __init__(
        self,
        worker_index: int,
        servicer_specs: list,
    ):
        import _interpreters

        self._interpreters = _interpreters
        self._index = worker_index

        # Create OS pipes: main→worker (requests), worker→main (responses).
        self._req_read_fd, self._req_write_fd = os.pipe()
        self._resp_read_fd, self._resp_write_fd = os.pipe()

        # Create sub-interpreter with its own GIL (PEP 684).
        # Use the default config which allocates a per-interpreter obmalloc
        # (safe for concurrent multi-GIL execution) and has gil='own'.
        # Workers only import pure-Python servicer modules, so the default
        # check_multi_interp_extensions=True is fine.
        config = _interpreters.new_config()
        config.allow_daemon_threads = True
        self._interp_id = _interpreters.create(config)

        self._thread: Optional[threading.Thread] = None
        self._servicer_specs = servicer_specs
        self._started = False
        # Serialize concurrent submit() calls for this worker.
        self._submit_lock = threading.Lock()

    def start(self) -> None:
        """Start the worker thread and wait for it to be ready."""
        if self._started:
            return
        # One-shot pipe: worker writes b"R" when ready, b"E" on error.
        ready_read_fd, ready_write_fd = os.pipe()
        code = _WORKER_CODE_TEMPLATE.format(
            req_read_fd=self._req_read_fd,
            resp_write_fd=self._resp_write_fd,
            ready_write_fd=ready_write_fd,
            servicer_specs=self._servicer_specs,
            sys_path=list(sys.path),
        )
        self._thread = threading.Thread(
            target=self._run,
            args=(code,),
            name=f"grpc-subinterp-worker-{self._index}",
            daemon=True,
        )
        self._started = True
        self._thread.start()
        # Wait for the worker to signal readiness.
        try:
            signal = os.read(ready_read_fd, 1)
            if signal != b"R":
                raise RuntimeError(
                    f"Sub-interpreter worker {self._index} failed to "
                    "initialize (see logs for details)."
                )
        finally:
            os.close(ready_read_fd)
            # ready_write_fd is closed by the worker code.

    def _run(self, code: str) -> None:
        """Thread body — executes worker code inside the sub-interpreter."""
        try:
            self._interpreters.exec(self._interp_id, code)
        except Exception:
            _LOGGER.exception(
                "Sub-interpreter worker %d crashed", self._index
            )

    def submit(self, packed_request: bytes) -> bytes:
        """Send a packed request and block until the response arrives.

        Thread-safe: concurrent calls are serialized via _submit_lock.
        This is called from the main interpreter's serve threads.
        """
        with self._submit_lock:
            _pipe_write_msg(self._req_write_fd, packed_request)
            response = _pipe_read_msg(self._resp_read_fd)
            if response is None:
                raise RuntimeError("Worker shut down during request")
            return response

    def shutdown(self) -> None:
        """Signal the worker to stop and wait for its thread."""
        if not self._started:
            return
        try:
            _pipe_write_shutdown(self._req_write_fd)
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        try:
            self._interpreters.destroy(self._interp_id)
        except Exception:
            pass
        for fd in (
            self._req_read_fd,
            self._req_write_fd,
            self._resp_read_fd,
            self._resp_write_fd,
        ):
            try:
                os.close(fd)
            except OSError:
                pass


class SubinterpreterPool:
    """Pool of sub-interpreter workers for parallel RPC handling.

    Each worker runs inside its own Python sub-interpreter with a dedicated
    GIL, enabling true multi-core parallelism for CPU-bound servicer code.
    Communication uses OS pipes for reliable, GIL-independent data transfer.

    Usage::

        pool = SubinterpreterPool(
            count=4,
            servicer_specs=[
                ("my_service_pb2_grpc", "MyServiceServicer", [
                    ("/pkg.Svc/Method", "my_pb2.Request.FromString",
                     "my_pb2.Response.SerializeToString", "Method"),
                ]),
            ],
        )
        pool.start()
        response_bytes = pool.dispatch(0, "/pkg.Svc/Method", request_bytes)
        pool.shutdown()
    """

    def __init__(
        self,
        count: int,
        servicer_specs: list,
    ):
        if not _is_supported():
            raise RuntimeError(
                "Sub-interpreter pool requires Python "
                f"{_SUBINTERPRETER_MIN_VERSION[0]}."
                f"{_SUBINTERPRETER_MIN_VERSION[1]}+ "
                "with _interpreters module."
            )
        if count < 1:
            raise ValueError("Worker count must be >= 1")
        self._count = count
        self._workers: List[_WorkerHandle] = []
        self._servicer_specs = servicer_specs
        self._started = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Create and start all worker sub-interpreters."""
        with self._lock:
            if self._started:
                return
            for i in range(self._count):
                worker = _WorkerHandle(i, self._servicer_specs)
                worker.start()
                self._workers.append(worker)
            self._started = True
            _LOGGER.info(
                "SubinterpreterPool started with %d workers", self._count
            )

    def dispatch(
        self,
        shard_index: int,
        method: str,
        serialized_request: bytes,
    ) -> Tuple[Optional[bytes], int, str]:
        """Dispatch a unary request to the specified shard's sub-interpreter.

        Args:
            shard_index: Index of the worker to use.
            method: Fully-qualified method name.
            serialized_request: Serialized protobuf request bytes.

        Returns:
            Tuple of (serialized_response, status_code, details).
        """
        worker = self._workers[shard_index % self._count]
        packed = _pack_request(method, serialized_request)
        raw_response = worker.submit(packed)
        return _unpack_response(raw_response)

    @property
    def worker_count(self) -> int:
        return self._count

    def shutdown(self, grace: Optional[float] = None) -> None:
        """Shutdown all workers."""
        with self._lock:
            if not self._started:
                return
            for worker in self._workers:
                worker.shutdown()
            self._workers.clear()
            self._started = False
            _LOGGER.info("SubinterpreterPool shut down")
