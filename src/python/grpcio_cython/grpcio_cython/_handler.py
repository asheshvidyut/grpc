# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Native handler registration for gRPC Python.

A native handler is a C-linkage function in a user-provided shared library that
implements the business logic for an RPC method. grpcio_cython wraps such a
function in a grpc.RpcMethodHandler that can be registered with a standard
grpc.server() — letting hot RPC paths skip the Python-side protobuf round-trip
and run without the GIL.
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from typing import Dict, Optional

import grpc

from . import _abi

_LOGGER = logging.getLogger(__name__)

# Try to import the Cython fast path. Available when grpcio is built with the
# native_dispatch.pyx.pxi included (this repo's branch onwards). When absent,
# we fall back to a pure-ctypes dispatch which is slower per call but
# functionally equivalent.
try:
    from grpc._cython import cygrpc as _cygrpc  # type: ignore

    _CYTHON_DISPATCH = getattr(_cygrpc, "dispatch_native_unary_unary", None)
    _CYTHON_VALIDATE = getattr(_cygrpc, "validate_native_abi", None)
except ImportError:  # pragma: no cover
    _CYTHON_DISPATCH = None
    _CYTHON_VALIDATE = None


class NativeHandlerError(RuntimeError):
    """Raised when loading or dispatching a native handler fails."""


class NativeModule:
    """A loaded native handler shared library.

    Loading verifies ABI compatibility via the grpcio_cython_abi_version
    symbol. Methods are resolved lazily by name when bound to a service.

    The same NativeModule may be shared across services and method handlers;
    it is thread-safe.
    """

    def __init__(self, path: str):
        self._path = os.path.abspath(path)
        if not os.path.isfile(self._path):
            raise NativeHandlerError(
                f"Native handler library not found: {self._path}"
            )
        try:
            self._lib = ctypes.CDLL(self._path)
            # Automatically execute dynamic JIT service pointer initializations on library load
            if hasattr(self._lib, "grpcio_cython_init"):
                try:
                    init_fn = ctypes.CFUNCTYPE(None)(self._lib.grpcio_cython_init)
                    init_fn()
                except Exception as e:
                    _LOGGER.warning("Dynamic JIT library native initialization failed: %s", e)
        except OSError as e:
            raise NativeHandlerError(
                f"Failed to load native handler library {self._path}: {e}"
            ) from e

        try:
            abi_fn_addr = ctypes.cast(
                self._lib.grpcio_cython_abi_version, _abi.ABI_VERSION_FN
            )
        except AttributeError as e:
            raise NativeHandlerError(
                f"Library {self._path} does not export "
                "grpcio_cython_abi_version; not a grpcio_cython handler."
            ) from e

        version = abi_fn_addr()
        if version != _abi.ABI_VERSION:
            raise NativeHandlerError(
                f"ABI version mismatch loading {self._path}: "
                f"library reports v{version}, runtime expects "
                f"v{_abi.ABI_VERSION}"
            )

        self._lock = threading.Lock()
        self._unary_unary_fns: Dict[str, _abi.UNARY_UNARY_FN] = {}
        self._unary_stream_fns: Dict[str, _abi.UNARY_STREAM_FN] = {}
        self._stream_unary_fns: Dict[str, _abi.STREAM_UNARY_FN] = {}
        self._stream_stream_fns: Dict[str, _abi.STREAM_STREAM_FN] = {}

    @property
    def path(self) -> str:
        return self._path

    def __getattr__(self, name: str):
        if hasattr(self._lib, name):
            return getattr(self._lib, name)
        raise AttributeError(f"'NativeModule' object has no attribute '{name}'")


    def _resolve(self, symbol: str, signature):
        try:
            raw = getattr(self._lib, symbol)
        except AttributeError as e:
            raise NativeHandlerError(
                f"Symbol {symbol!r} not found in {self._path}"
            ) from e
        return ctypes.cast(raw, signature)

    def unary_unary(self, symbol: str) -> "_NativeUnaryUnaryBehavior":
        """Resolve a unary-unary handler symbol into a callable behavior."""
        with self._lock:
            fn = self._unary_unary_fns.get(symbol)
            if fn is None:
                fn = self._resolve(symbol, _abi.UNARY_UNARY_FN)
                self._unary_unary_fns[symbol] = fn
        return _NativeUnaryUnaryBehavior(self, symbol, fn)

    def unary_stream(self, symbol: str) -> "_NativeUnaryStreamBehavior":
        with self._lock:
            fn = self._unary_stream_fns.get(symbol)
            if fn is None:
                fn = self._resolve(symbol, _abi.UNARY_STREAM_FN)
                self._unary_stream_fns[symbol] = fn
        return _NativeUnaryStreamBehavior(self, symbol, fn)

    def stream_unary(self, symbol: str) -> "_NativeStreamUnaryBehavior":
        with self._lock:
            fn = self._stream_unary_fns.get(symbol)
            if fn is None:
                fn = self._resolve(symbol, _abi.STREAM_UNARY_FN)
                self._stream_unary_fns[symbol] = fn
        return _NativeStreamUnaryBehavior(self, symbol, fn)

    def stream_stream(self, symbol: str) -> "_NativeStreamStreamBehavior":
        with self._lock:
            fn = self._stream_stream_fns.get(symbol)
            if fn is None:
                fn = self._resolve(symbol, _abi.STREAM_STREAM_FN)
                self._stream_stream_fns[symbol] = fn
        return _NativeStreamStreamBehavior(self, symbol, fn)


def _raise_for_status(status: int, err_msg: Optional[bytes], context) -> None:
    if status == _abi.STATUS_OK:
        return
    status_name = _abi.status_name(status)
    code = getattr(grpc.StatusCode, status_name, grpc.StatusCode.UNKNOWN)
    detail = err_msg.decode("utf-8", errors="replace") if err_msg else ""
    context.set_code(code)
    if detail:
        context.set_details(detail)


def _copy_and_free_native_buffer(
    ptr: "ctypes._Pointer", length: int
) -> bytes:
    """Copy `length` bytes from a malloc()'d C buffer into Python bytes.

    The C buffer is then released with libc.free(). This is how the dispatcher
    reclaims storage allocated by the native handler.
    """
    if not ptr or length == 0:
        return b""
    
    _ensure_libc_loaded()
    
    # Allocate blank Python bytes object
    resp_bytes = bytes(length)
    
    void_ptr = ctypes.cast(ptr, ctypes.c_void_p)
    # Copy memory using GIL-released libc memcpy (offset 32 for PyBytesObject ob_sval)
    _LIBC.memcpy(id(resp_bytes) + 32, void_ptr, length)
    
    # Free native buffer
    _LIBC.free(void_ptr)
    
    return resp_bytes


_LIBC = None


def _ensure_libc_loaded() -> None:
    global _LIBC
    if _LIBC is None:
        _LIBC = ctypes.CDLL(None)
        _LIBC.free.argtypes = [ctypes.c_void_p]
        _LIBC.free.restype = None
        _LIBC.memcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        _LIBC.memcpy.restype = ctypes.c_void_p


def _libc_free(ptr: ctypes.c_void_p) -> None:
    """Call libc free() on a pointer returned by a handler.

    Loaded lazily and cached.
    """
    _ensure_libc_loaded()
    _LIBC.free(ptr)


class _ContextBridge:
    """Bridges a Python ServicerContext to a grpc_native_context.

    Exposes cancellation, request metadata, response trailers, deadline, and
    peer info to the native handler via C callbacks.

    Thread safety: callbacks are invoked from the C handler's thread (which
    holds the GIL when the callback executes — ctypes manages this). All
    underlying ServicerContext methods are safe to call from any thread.
    """

    def __init__(self, servicer_context):
        self._ctx = servicer_context
        self._current_metadata_value = None  # keep alive between get_metadata calls
        self._peer_bytes = None  # keep alive between peer() calls
        self._trailing_metadata: list = []
        self._metadata_dict = None  # lazily built from invocation_metadata()

        # Strong refs to ctypes callbacks (they MUST outlive the C call).
        self._is_cancelled_cb = _abi._IS_CANCELLED_CB(self._is_cancelled)
        self._get_metadata_cb = _abi._GET_METADATA_CB(self._get_metadata)
        self._set_trailing_cb = _abi._SET_TRAILING_CB(self._set_trailing)
        self._time_remaining_cb = _abi._TIME_REMAINING_CB(
            self._time_remaining_ns
        )
        self._peer_cb = _abi._PEER_CB(self._peer)

        self.context = _abi.GrpcNativeContext()
        self.context.ctx = None
        self.context.is_cancelled = self._is_cancelled_cb
        self.context.get_metadata = self._get_metadata_cb
        self.context.set_trailing_metadata = self._set_trailing_cb
        self.context.time_remaining_ns = self._time_remaining_cb
        self.context.peer = self._peer_cb

    # ---- callback implementations ----

    def _is_cancelled(self, _ctx) -> int:
        try:
            return 0 if self._ctx.is_active() else 1
        except Exception:
            return 0

    def _ensure_metadata_dict(self):
        if self._metadata_dict is None:
            d = {}
            try:
                for k, v in self._ctx.invocation_metadata() or ():
                    # gRPC metadata keys are case-insensitive ASCII.
                    key = k.lower() if isinstance(k, str) else k.decode().lower()
                    val = v if isinstance(v, (bytes, bytearray)) else (
                        v.encode() if isinstance(v, str) else bytes(v)
                    )
                    # First wins (matches gRPC C++ default behavior).
                    d.setdefault(key, val)
            except Exception:  # pragma: no cover
                _LOGGER.exception("error reading invocation_metadata")
            self._metadata_dict = d
        return self._metadata_dict

    def _get_metadata(self, _ctx, key, out_value, out_len) -> int:
        try:
            key_str = key.decode("ascii", errors="replace").lower()
        except Exception:  # pragma: no cover
            return 0
        d = self._ensure_metadata_dict()
        val = d.get(key_str)
        if val is None:
            return 0
        # Keep the bytes alive until the next get_metadata call.
        self._current_metadata_value = val
        # ctypes c_char_p backed by self._current_metadata_value's buffer.
        # The bytes object lives at a stable address while we hold a ref.
        out_value[0] = val
        out_len[0] = len(val)
        return 1

    def _set_trailing(self, _ctx, key, value, length) -> int:
        try:
            key_str = key.decode("ascii", errors="replace")
            val_bytes = ctypes.string_at(value, length)
            self._trailing_metadata.append((key_str, val_bytes))
        except Exception:  # pragma: no cover
            _LOGGER.exception("error in set_trailing_metadata")
            return 1
        return 0

    def _time_remaining_ns(self, _ctx) -> int:
        try:
            seconds = self._ctx.time_remaining()
        except Exception:
            return _abi.INT64_MAX
        if seconds is None:
            return _abi.INT64_MAX
        return int(seconds * 1e9)

    def _peer(self, _ctx):
        try:
            peer = self._ctx.peer()
        except Exception:
            return None
        if not peer:
            return None
        peer_bytes = peer.encode() if isinstance(peer, str) else bytes(peer)
        self._peer_bytes = peer_bytes  # keep alive
        return peer_bytes

    # ---- finalization ----

    def flush_trailing_metadata(self):
        if self._trailing_metadata:
            try:
                # gRPC expects an iterable of (key, value) pairs.
                self._ctx.set_trailing_metadata(self._trailing_metadata)
            except Exception:  # pragma: no cover
                _LOGGER.exception("failed to set trailing metadata")


class _ReaderBridge:
    """Bridges a Python request iterator to a grpc_native_reader.

    The C handler calls reader.read(ctx, &out_data, &out_len). We pull the
    next message from the iterator, copy its bytes into a stable buffer that
    we own, and write the buffer's address to *out_data. The buffer remains
    valid until the next read() call or until this bridge is destroyed.

    Thread safety: read() is called from the C handler's thread (which may be
    a worker thread we spawned, or the gRPC pool thread for sync stream-unary
    handlers). Python's GIL serializes access; no extra locking needed.
    """

    def __init__(self, request_iterator):
        self._iter = request_iterator
        self._current_buffer = None  # holds the bytes for the *current* read
        # Strong ref to the callback to keep ctypes from GC'ing it.
        read_t = _abi.GrpcNativeReader._fields_[1][1]
        self._read_cb = read_t(self._read)
        self.reader = _abi.GrpcNativeReader()
        self.reader.ctx = None
        self.reader.read = self._read_cb

    def _read(self, _ctx, out_data, out_len):
        try:
            msg = next(self._iter)
        except StopIteration:
            return 0
        except Exception:  # pragma: no cover
            _LOGGER.exception("error advancing request iterator")
            return -1
        if not isinstance(msg, (bytes, bytearray, memoryview)):
            _LOGGER.error(
                "request iterator yielded non-bytes type %s; "
                "RpcMethodHandler must have request_deserializer=None",
                type(msg).__name__,
            )
            return -1
        msg_bytes = bytes(msg)
        # Own a stable buffer; drops the previous one (replaces self._current_buffer).
        buf = ctypes.create_string_buffer(msg_bytes, len(msg_bytes))
        self._current_buffer = buf
        # Write the buffer address into *out_data. We cast via c_void_p to
        # bypass c_char_p's NUL-terminated semantics (our payloads are
        # binary).
        addr = ctypes.addressof(buf)
        ctypes.cast(out_data, ctypes.POINTER(ctypes.c_void_p))[0] = addr
        out_len[0] = len(msg_bytes)
        return 1


class _WriterBridge:
    """Bridges a grpc_native_writer to a thread-safe queue.

    The C handler calls writer.emit(ctx, data, len). The bridge copies the
    bytes (so the handler may reuse its buffer) and pushes onto a deque that
    the iterator on the gRPC side drains.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._queue: list = []
        self._closed = False
        emit_t = _abi.GrpcNativeWriter._fields_[1][1]
        self._emit_cb = emit_t(self._emit)
        self.writer = _abi.GrpcNativeWriter()
        self.writer.ctx = None
        self.writer.emit = self._emit_cb

    def _emit(self, _ctx, data, length):
        msg = ctypes.string_at(data, length)
        with self._cv:
            if self._closed:
                return 1
            self._queue.append(msg)
            self._cv.notify()
        return 0

    def close(self):
        """Mark the writer closed — drain side will see no more messages."""
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    def drain(self):
        """Yield queued messages until close() has been called and queue empty."""
        while True:
            with self._cv:
                while not self._queue and not self._closed:
                    self._cv.wait()
                if self._queue:
                    msg = self._queue.pop(0)
                else:
                    return
            yield msg


class _NativeUnaryUnaryBehavior:
    """A unary-unary handler bound to a native function pointer.

    The grpcio thread pool invokes __call__(request_bytes, context).
    request_deserializer/response_serializer are None on the RpcMethodHandler
    so request_bytes is the raw wire payload and the return value is the raw
    wire payload — no Python protobuf round-trip.

    ctypes releases the GIL for the duration of the foreign function call, so
    the native handler runs in parallel with other Python work.
    """

    def __init__(
        self,
        module: NativeModule,
        symbol: str,
        fn: "ctypes._FuncPointer",
    ):
        self._module = module
        self._symbol = symbol
        self._fn = fn

    def __repr__(self) -> str:
        return (
            f"<NativeUnaryUnary {self._symbol!r} from "
            f"{os.path.basename(self._module.path)}>"
        )

    def __call__(self, request_bytes: bytes, context) -> bytes:
        if not isinstance(request_bytes, (bytes, bytearray, memoryview)):
            raise TypeError(
                "Native handler expected bytes-like request payload; got "
                f"{type(request_bytes).__name__}. The RpcMethodHandler must "
                "be configured with request_deserializer=None."
            )
        payload = bytes(request_bytes)
        # Note: the Cython fast path predates v3 ABI (context). For now it's
        # only used when there's no context to surface — most handlers can
        # ignore context, and the fast path is still ~5μs faster. When the
        # user's handler uses context, we go through ctypes.
        ctx_bridge = _ContextBridge(context)
        call = _abi.GrpcNativeUnaryCall()
        call.context = ctypes.pointer(ctx_bridge.context)
        call.req_data = payload
        call.req_len = len(payload)
        call.resp_data = None
        call.resp_len = 0
        call.status = _abi.STATUS_OK
        call.err_msg = None
        call.err_msg_len = 0

        # ctypes releases the GIL for the duration of this call.
        rc = self._fn(ctypes.byref(call))
        if rc != 0:
            _LOGGER.error(
                "Native handler %s returned non-zero rc=%d", self._symbol, rc
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(
                f"Native handler {self._symbol} returned rc={rc}"
            )
            if call.resp_data:
                _libc_free(ctypes.cast(call.resp_data, ctypes.c_void_p))
            if call.err_msg:
                _libc_free(ctypes.cast(call.err_msg, ctypes.c_void_p))
            return b""

        err_bytes: Optional[bytes] = None
        if call.err_msg and call.err_msg_len:
            err_bytes = _copy_and_free_native_buffer(
                call.err_msg, call.err_msg_len
            )
        elif call.err_msg:
            _libc_free(ctypes.cast(call.err_msg, ctypes.c_void_p))

        response_bytes = _copy_and_free_native_buffer(
            call.resp_data, call.resp_len
        )
        _raise_for_status(call.status, err_bytes, context)
        return response_bytes


def _run_streaming_handler(
    fn, call_struct, writer_bridge: "_WriterBridge", symbol: str
):
    """Run a native streaming handler on a worker thread.

    Returns the (rc, call_struct_with_results) for the caller to inspect after
    the writer bridge is drained.
    """
    result: list = [None, None]  # rc, call

    def runner():
        try:
            result[0] = fn(ctypes.byref(call_struct))
        except Exception:  # pragma: no cover
            _LOGGER.exception(
                "native handler %s raised in ctypes layer", symbol
            )
            result[0] = -1
        finally:
            result[1] = call_struct
            writer_bridge.close()

    t = threading.Thread(target=runner, daemon=True, name=f"native-{symbol}")
    t.start()
    return t, result


class _NativeUnaryStreamBehavior:
    """A unary-stream handler bound to a native function pointer.

    The C handler runs on a dedicated worker thread; the iterator returned
    here drains a queue that the C handler's writer.emit() fills. This gives
    true streaming — messages are forwarded to the client as the C handler
    produces them, not buffered until the handler returns.
    """

    def __init__(
        self,
        module: NativeModule,
        symbol: str,
        fn: "ctypes._FuncPointer",
    ):
        self._module = module
        self._symbol = symbol
        self._fn = fn

    def __repr__(self) -> str:
        return (
            f"<NativeUnaryStream {self._symbol!r} from "
            f"{os.path.basename(self._module.path)}>"
        )

    def __call__(self, request_bytes, context):
        if not isinstance(request_bytes, (bytes, bytearray, memoryview)):
            raise TypeError(
                "Native handler expected bytes-like request payload; got "
                f"{type(request_bytes).__name__}."
            )
        payload = bytes(request_bytes)
        writer_bridge = _WriterBridge()
        ctx_bridge = _ContextBridge(context)

        call = _abi.GrpcNativeUnaryStreamCall()
        call.context = ctypes.pointer(ctx_bridge.context)
        call.req_data = payload
        call.req_len = len(payload)
        call.writer = ctypes.pointer(writer_bridge.writer)
        call.status = _abi.STATUS_OK
        call.err_msg = None
        call.err_msg_len = 0

        worker, result = _run_streaming_handler(
            self._fn, call, writer_bridge, self._symbol
        )

        for msg in writer_bridge.drain():
            yield msg

        worker.join()
        rc, finished_call = result
        ctx_bridge.flush_trailing_metadata()
        _finalize_streaming_status(rc, finished_call, context, self._symbol)


class _NativeStreamUnaryBehavior:
    """A stream-unary handler bound to a native function pointer.

    The C handler runs on the gRPC worker thread (the calling thread). The
    reader bridge pulls messages from the request iterator as the C handler
    calls reader.read(). Single response returned at the end.
    """

    def __init__(
        self,
        module: NativeModule,
        symbol: str,
        fn: "ctypes._FuncPointer",
    ):
        self._module = module
        self._symbol = symbol
        self._fn = fn

    def __repr__(self) -> str:
        return (
            f"<NativeStreamUnary {self._symbol!r} from "
            f"{os.path.basename(self._module.path)}>"
        )

    def __call__(self, request_iterator, context) -> bytes:
        reader_bridge = _ReaderBridge(request_iterator)

        call = _abi.GrpcNativeStreamUnaryCall()
        call.reader = ctypes.pointer(reader_bridge.reader)
        call.resp_data = None
        call.resp_len = 0
        call.status = _abi.STATUS_OK
        call.err_msg = None
        call.err_msg_len = 0

        rc = self._fn(ctypes.byref(call))
        if rc != 0:
            _LOGGER.error(
                "Native handler %s returned non-zero rc=%d", self._symbol, rc
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(
                f"Native handler {self._symbol} returned rc={rc}"
            )
            if call.resp_data:
                _libc_free(ctypes.cast(call.resp_data, ctypes.c_void_p))
            if call.err_msg:
                _libc_free(ctypes.cast(call.err_msg, ctypes.c_void_p))
            return b""

        err_bytes: Optional[bytes] = None
        if call.err_msg and call.err_msg_len:
            err_bytes = _copy_and_free_native_buffer(
                call.err_msg, call.err_msg_len
            )
        elif call.err_msg:
            _libc_free(ctypes.cast(call.err_msg, ctypes.c_void_p))

        response_bytes = _copy_and_free_native_buffer(
            call.resp_data, call.resp_len
        )
        _raise_for_status(call.status, err_bytes, context)
        return response_bytes


class _NativeStreamStreamBehavior:
    """A stream-stream (bidi) handler bound to a native function pointer.

    The C handler runs on a dedicated worker thread so reads from the request
    iterator and writes to the response queue can interleave freely.
    """

    def __init__(
        self,
        module: NativeModule,
        symbol: str,
        fn: "ctypes._FuncPointer",
    ):
        self._module = module
        self._symbol = symbol
        self._fn = fn

    def __repr__(self) -> str:
        return (
            f"<NativeStreamStream {self._symbol!r} from "
            f"{os.path.basename(self._module.path)}>"
        )

    def __call__(self, request_iterator, context):
        reader_bridge = _ReaderBridge(request_iterator)
        writer_bridge = _WriterBridge()

        call = _abi.GrpcNativeStreamStreamCall()
        call.reader = ctypes.pointer(reader_bridge.reader)
        call.writer = ctypes.pointer(writer_bridge.writer)
        call.status = _abi.STATUS_OK
        call.err_msg = None
        call.err_msg_len = 0

        worker, result = _run_streaming_handler(
            self._fn, call, writer_bridge, self._symbol
        )

        for msg in writer_bridge.drain():
            yield msg

        worker.join()
        rc, finished_call = result
        _finalize_streaming_status(rc, finished_call, context, self._symbol)


def _finalize_streaming_status(rc, call, context, symbol: str) -> None:
    """Apply post-handler status to context for stream-out behaviors."""
    if rc != 0:
        _LOGGER.error("native handler %s returned non-zero rc=%d", symbol, rc)
        context.set_code(grpc.StatusCode.INTERNAL)
        context.set_details(f"Native handler {symbol} returned rc={rc}")
        if call is not None:
            if call.err_msg:
                _libc_free(ctypes.cast(call.err_msg, ctypes.c_void_p))
        return

    if call is None:
        return

    err_bytes: Optional[bytes] = None
    if call.err_msg and call.err_msg_len:
        err_bytes = _copy_and_free_native_buffer(
            call.err_msg, call.err_msg_len
        )
    elif call.err_msg:
        _libc_free(ctypes.cast(call.err_msg, ctypes.c_void_p))
    _raise_for_status(call.status, err_bytes, context)


# ---------------------------------------------------------------------------
# Public factory functions — produce grpc.RpcMethodHandler instances that
# slot into a normal grpc.server() registration without modification.
# ---------------------------------------------------------------------------


def native_unary_unary_rpc_method_handler(
    module: Optional[NativeModule] = None,
    symbol: Optional[str] = None,
    *,
    servicer_instance=None,
    method_name: Optional[str] = None
) -> grpc.RpcMethodHandler:
    """Create an RpcMethodHandler backed by a native unary-unary function.

    The returned handler has request_deserializer=None and
    response_serializer=None — the native function sees raw wire bytes and
    returns raw wire bytes. The user .cc/.c file is responsible for protobuf
    encoding/decoding (typically via the protobuf C++ library or upb).

    Args:
      module: A NativeModule produced by load_native_module().
      symbol: The C-linkage symbol name of the unary-unary handler.
      servicer_instance: Compatibility alias for Cython objects containing a _native_module.
      method_name: Compatibility alias for symbol.

    Returns:
      A grpc.RpcMethodHandler that may be registered like any other handler.
    """
    if servicer_instance is not None and method_name is not None and module is None:
        module = getattr(servicer_instance, "_native_module", module)
        symbol = method_name

    if module is None or symbol is None:
        raise ValueError("Either module/symbol or servicer_instance/method_name must be provided")

    behavior = module.unary_unary(symbol)
    from grpc import _utilities

    return _utilities.RpcMethodHandler(
        request_streaming=False,
        response_streaming=False,
        request_deserializer=None,
        response_serializer=None,
        unary_unary=behavior,
        unary_stream=None,
        stream_unary=None,
        stream_stream=None,
    )


def native_unary_stream_rpc_method_handler(
    module: NativeModule,
    symbol: str,
) -> grpc.RpcMethodHandler:
    """Create an RpcMethodHandler backed by a native unary-stream function."""
    behavior = module.unary_stream(symbol)
    from grpc import _utilities

    return _utilities.RpcMethodHandler(
        request_streaming=False,
        response_streaming=True,
        request_deserializer=None,
        response_serializer=None,
        unary_unary=None,
        unary_stream=behavior,
        stream_unary=None,
        stream_stream=None,
    )


def native_stream_unary_rpc_method_handler(
    module: NativeModule,
    symbol: str,
) -> grpc.RpcMethodHandler:
    """Create an RpcMethodHandler backed by a native stream-unary function.

    The native handler pulls request messages via reader.read() and returns
    a single response.
    """
    behavior = module.stream_unary(symbol)
    from grpc import _utilities

    return _utilities.RpcMethodHandler(
        request_streaming=True,
        response_streaming=False,
        request_deserializer=None,
        response_serializer=None,
        unary_unary=None,
        unary_stream=None,
        stream_unary=behavior,
        stream_stream=None,
    )


def native_stream_stream_rpc_method_handler(
    module: NativeModule,
    symbol: str,
) -> grpc.RpcMethodHandler:
    """Create an RpcMethodHandler backed by a native stream-stream function.

    The native handler pulls request messages via reader.read() and emits
    response messages via writer.emit(); both can interleave freely.
    """
    behavior = module.stream_stream(symbol)
    from grpc import _utilities

    return _utilities.RpcMethodHandler(
        request_streaming=True,
        response_streaming=True,
        request_deserializer=None,
        response_serializer=None,
        unary_unary=None,
        unary_stream=None,
        stream_unary=None,
        stream_stream=behavior,
    )


def load_native_module(path: str) -> NativeModule:
    """Load a native handler shared library from disk.

    Validates ABI compatibility. Caches symbol lookups internally.

    Args:
      path: Filesystem path to the .so/.dylib/.dll containing native handlers.

    Returns:
      A NativeModule that can resolve handler symbols.

    Raises:
      NativeHandlerError on load or version-mismatch failure.
    """
    return NativeModule(path)
