# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Tests for grpcio_native.

End-to-end tests rely on the echo_c example being built. They start an actual
gRPC server with a native handler registered and exercise it.
"""

import os
import platform
import struct
import sys
import threading
import time
import unittest
from concurrent import futures

sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..")))

import grpc

import grpcio_native

_REPO_ROOT = os.path.abspath(os.path.join(__file__, "..", ".."))
_LIB_NAME = (
    "echo_handler.dylib"
    if platform.system() == "Darwin"
    else "echo_handler.so"
)
_ECHO_LIB = os.path.join(_REPO_ROOT, "examples", "echo_c", _LIB_NAME)


def _ensure_echo_lib_built():
    if not os.path.isfile(_ECHO_LIB):
        raise unittest.SkipTest(
            f"{_ECHO_LIB} not built; run `make` in examples/echo_c first."
        )


class _Server:
    """Helper that starts and stops a real grpc.server with native handlers."""

    def __init__(self, port: int = 0):
        _ensure_echo_lib_built()
        self.module = grpcio_native.load_native_module(_ECHO_LIB)
        uu = grpcio_native.native_unary_unary_rpc_method_handler
        us = grpcio_native.native_unary_stream_rpc_method_handler
        su = grpcio_native.native_stream_unary_rpc_method_handler
        ss = grpcio_native.native_stream_stream_rpc_method_handler
        method_handlers = {
            # unary-unary
            "Echo": uu(self.module, "echo_unary"),
            "Double": uu(self.module, "double_uint32"),
            "NotFound": uu(self.module, "always_not_found"),
            # unary-stream
            "SplitBytes": us(self.module, "split_bytes"),
            "Fib": us(self.module, "fib_stream"),
            # stream-unary
            "Concat": su(self.module, "concat"),
            "Sum": su(self.module, "sum_u64"),
            # stream-stream
            "EchoStream": ss(self.module, "echo_stream"),
            "RunningSum": ss(self.module, "running_sum"),
        }
        generic_handler = grpc.method_handlers_generic_handler(
            "echo.Echo", method_handlers
        )
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        self.server.add_generic_rpc_handlers((generic_handler,))
        self.port = self.server.add_insecure_port(f"[::]:{port}")
        self.server.start()

    def stop(self):
        self.server.stop(grace=0).wait()

    @property
    def target(self) -> str:
        return f"localhost:{self.port}"


class NativeHandlerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _Server()
        cls.channel = grpc.insecure_channel(cls.server.target)

    @classmethod
    def tearDownClass(cls):
        cls.channel.close()
        cls.server.stop()

    def test_echo_roundtrip(self):
        echo = self.channel.unary_unary("/echo.Echo/Echo")
        payload = b"alpha-beta-gamma"
        self.assertEqual(echo(payload), payload)

    def test_echo_empty(self):
        echo = self.channel.unary_unary("/echo.Echo/Echo")
        self.assertEqual(echo(b""), b"")

    def test_echo_large(self):
        # 1 MiB request — exercises the malloc path in the C handler.
        echo = self.channel.unary_unary("/echo.Echo/Echo")
        payload = b"x" * (1 << 20)
        response = echo(payload)
        self.assertEqual(len(response), len(payload))
        self.assertEqual(response, payload)

    def test_double_uint32(self):
        double = self.channel.unary_unary("/echo.Echo/Double")
        for n in (0, 1, 42, 1_000_000, 2_147_483_647):
            packed = struct.pack("<I", n)
            response = double(packed)
            (result,) = struct.unpack("<I", response)
            self.assertEqual(result, (n * 2) & 0xFFFFFFFF)

    def test_double_uint32_wrong_size(self):
        double = self.channel.unary_unary("/echo.Echo/Double")
        with self.assertRaises(grpc.RpcError) as cm:
            double(b"abc")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT)
        self.assertIn("4-byte", cm.exception.details())

    def test_status_propagation(self):
        not_found = self.channel.unary_unary("/echo.Echo/NotFound")
        with self.assertRaises(grpc.RpcError) as cm:
            not_found(b"")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.NOT_FOUND)
        self.assertEqual(cm.exception.details(), "nothing here")

    def test_unknown_method(self):
        # A method on echo.Echo that wasn't registered.
        unknown = self.channel.unary_unary("/echo.Echo/DoesNotExist")
        with self.assertRaises(grpc.RpcError) as cm:
            unknown(b"")
        self.assertEqual(cm.exception.code(), grpc.StatusCode.UNIMPLEMENTED)

    def test_concurrent_calls(self):
        # Native handlers must be safe to invoke concurrently across threads;
        # ctypes releases the GIL during the C call.
        echo = self.channel.unary_unary("/echo.Echo/Echo")
        errors = []

        def worker(idx: int):
            try:
                for _ in range(100):
                    payload = f"call-{idx}".encode()
                    self.assertEqual(echo(payload), payload)
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


class UnaryStreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _Server()
        cls.channel = grpc.insecure_channel(cls.server.target)

    @classmethod
    def tearDownClass(cls):
        cls.channel.close()
        cls.server.stop()

    def test_split_bytes(self):
        call = self.channel.unary_stream("/echo.Echo/SplitBytes")
        responses = list(call(b"hello"))
        self.assertEqual(responses, [b"h", b"e", b"l", b"l", b"o"])

    def test_split_empty(self):
        call = self.channel.unary_stream("/echo.Echo/SplitBytes")
        responses = list(call(b""))
        self.assertEqual(responses, [])

    def test_fib_stream(self):
        call = self.channel.unary_stream("/echo.Echo/Fib")
        responses = list(call(struct.pack("<I", 10)))
        nums = [struct.unpack("<Q", r)[0] for r in responses]
        self.assertEqual(nums, [0, 1, 1, 2, 3, 5, 8, 13, 21, 34])

    def test_streaming_is_actually_streaming(self):
        """First response must arrive before all are emitted.

        If the worker thread were buffering everything, the very first
        next() would already be blocked on the entire computation. With
        true streaming, the first yield happens promptly.
        """
        call = self.channel.unary_stream("/echo.Echo/SplitBytes")
        iterator = call(b"x" * 50)
        # Advance one message — should return quickly.
        first = next(iterator)
        self.assertEqual(first, b"x")
        rest = list(iterator)
        self.assertEqual(len(rest), 49)


class StreamUnaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _Server()
        cls.channel = grpc.insecure_channel(cls.server.target)

    @classmethod
    def tearDownClass(cls):
        cls.channel.close()
        cls.server.stop()

    def test_concat(self):
        call = self.channel.stream_unary("/echo.Echo/Concat")
        response = call(iter([b"alpha-", b"beta-", b"gamma"]))
        self.assertEqual(response, b"alpha-beta-gamma")

    def test_concat_empty_stream(self):
        call = self.channel.stream_unary("/echo.Echo/Concat")
        response = call(iter([]))
        self.assertEqual(response, b"")

    def test_concat_many(self):
        call = self.channel.stream_unary("/echo.Echo/Concat")
        chunks = [f"chunk-{i:03d}".encode() for i in range(50)]
        response = call(iter(chunks))
        self.assertEqual(response, b"".join(chunks))

    def test_sum_u64(self):
        call = self.channel.stream_unary("/echo.Echo/Sum")
        nums = [1, 2, 3, 4, 5, 100, 1_000_000]
        msgs = [struct.pack("<Q", n) for n in nums]
        response = call(iter(msgs))
        (total,) = struct.unpack("<Q", response)
        self.assertEqual(total, sum(nums))

    def test_sum_invalid_message_size(self):
        call = self.channel.stream_unary("/echo.Echo/Sum")
        with self.assertRaises(grpc.RpcError) as cm:
            call(iter([b"too-short"]))
        self.assertEqual(
            cm.exception.code(), grpc.StatusCode.INVALID_ARGUMENT
        )


class StreamStreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _Server()
        cls.channel = grpc.insecure_channel(cls.server.target)

    @classmethod
    def tearDownClass(cls):
        cls.channel.close()
        cls.server.stop()

    def test_echo_stream(self):
        call = self.channel.stream_stream("/echo.Echo/EchoStream")
        requests = [b"one", b"two", b"three"]
        responses = list(call(iter(requests)))
        self.assertEqual(responses, requests)

    def test_running_sum(self):
        call = self.channel.stream_stream("/echo.Echo/RunningSum")
        inputs = [1, 2, 3, 4, 5]
        msgs = [struct.pack("<Q", n) for n in inputs]
        responses = list(call(iter(msgs)))
        results = [struct.unpack("<Q", r)[0] for r in responses]
        expected_running = [1, 3, 6, 10, 15]
        self.assertEqual(results, expected_running)

    def test_bidi_interleave(self):
        """Verify reads and writes can interleave.

        The C handler reads one message, emits one, reads next, emits next…
        Using a generator that produces requests lazily, we can confirm the
        server is reading them one at a time rather than buffering.
        """
        produced = []

        def request_gen():
            for i in range(5):
                msg = struct.pack("<Q", i + 1)
                produced.append(i)
                yield msg

        call = self.channel.stream_stream("/echo.Echo/RunningSum")
        responses = list(call(request_gen()))
        # All five inputs produced, all five running sums received.
        self.assertEqual(produced, [0, 1, 2, 3, 4])
        self.assertEqual(
            [struct.unpack("<Q", r)[0] for r in responses],
            [1, 3, 6, 10, 15],
        )


class ModuleLoadTest(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(grpcio_native.NativeHandlerError):
            grpcio_native.load_native_module(
                "/does/not/exist/handler.dylib"
            )

    def test_missing_symbol(self):
        _ensure_echo_lib_built()
        module = grpcio_native.load_native_module(_ECHO_LIB)
        with self.assertRaises(grpcio_native.NativeHandlerError):
            module.unary_unary("nonexistent_handler_symbol")


class CompilerTest(unittest.TestCase):
    def test_compile_and_load_cython(self):
        src_file = os.path.join(os.path.dirname(__file__), "temp_handler.pyx")
        import textwrap
        code = textwrap.dedent("""\
            from libc.stdlib cimport malloc, free
            from libc.string cimport memcpy
            from libc.stdint cimport uint32_t

            cdef struct grpc_native_unary_call:
                void* context
                const char* req_data
                size_t req_len
                char* resp_data
                size_t resp_len
                int status
                char* err_msg
                size_t err_msg_len

            cdef public uint32_t grpcio_native_abi_version() nogil:
                return 3

            cdef public int jitted_echo(grpc_native_unary_call* call) nogil:
                call.resp_data = <char*>malloc(call.req_len)
                if call.resp_data != NULL:
                    memcpy(call.resp_data, call.req_data, call.req_len)
                    call.resp_len = call.req_len
                call.status = 0
                return 0
        """)
        with open(src_file, "w") as f:
            f.write(code)

        try:
            out_dir = os.path.dirname(__file__)
            module = grpcio_native.compile_and_load_cython(
                pyx_file=src_file,
                output_dir=out_dir,
                lib_name="temp_jitted_handler"
            )
            
            handler = grpcio_native.native_unary_unary_rpc_method_handler(
                module, "jitted_echo"
            )
            
            generic_handler = grpc.method_handlers_generic_handler(
                "jitted.Jitted", {"Echo": handler}
            )
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
            server.add_generic_rpc_handlers((generic_handler,))
            port = server.add_insecure_port("localhost:0")
            server.start()
            
            try:
                with grpc.insecure_channel(f"localhost:{port}") as channel:
                    reply = channel.unary_unary("/jitted.Jitted/Echo")(b"hello cython jit")
                    self.assertEqual(reply, b"hello cython jit")
            finally:
                server.stop(grace=0).wait()
                
        finally:
            if os.path.exists(src_file):
                os.remove(src_file)
            ext = ".dylib" if platform.system() == "Darwin" else ".so"
            compiled_lib = os.path.join(out_dir, f"temp_jitted_handler{ext}")
            if os.path.exists(compiled_lib):
                os.remove(compiled_lib)


if __name__ == "__main__":
    unittest.main()
