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
"""Tests for the sub-interpreter pool module."""

import logging
import os
import shutil
import struct
import sys
import tempfile
import threading
import unittest

from grpc._subinterpreter_pool import _is_supported
from grpc._subinterpreter_pool import _pack_request
from grpc._subinterpreter_pool import _pack_response
from grpc._subinterpreter_pool import _unpack_request
from grpc._subinterpreter_pool import _unpack_response


class PackUnpackTest(unittest.TestCase):
    """Tests for byte-buffer packing/unpacking helpers."""

    def test_request_roundtrip(self):
        method = "/pkg.Svc/Method"
        request = b"\x08\x96\x01"
        packed = _pack_request(method, request)
        unpacked_method, unpacked_request = _unpack_request(packed)
        self.assertEqual(method, unpacked_method)
        self.assertEqual(request, unpacked_request)

    def test_request_empty_body(self):
        method = "/test"
        packed = _pack_request(method, b"")
        m, r = _unpack_request(packed)
        self.assertEqual(method, m)
        self.assertEqual(b"", r)

    def test_request_unicode_method(self):
        method = "/unicode.Svc/Method"
        request = b"data"
        packed = _pack_request(method, request)
        m, r = _unpack_request(packed)
        self.assertEqual(method, m)
        self.assertEqual(request, r)

    def test_response_roundtrip_success(self):
        response = b"\x08\x01"
        packed = _pack_response(response, 0, "")
        unpacked_resp, code, details = _unpack_response(packed)
        self.assertEqual(response, unpacked_resp)
        self.assertEqual(0, code)
        self.assertEqual("", details)

    def test_response_roundtrip_error(self):
        packed = _pack_response(None, 2, "something went wrong")
        resp, code, details = _unpack_response(packed)
        self.assertIsNone(resp)
        self.assertEqual(2, code)
        self.assertEqual("something went wrong", details)

    def test_response_with_details_and_body(self):
        response = b"result"
        packed = _pack_response(response, 0, "ok")
        resp, code, details = _unpack_response(packed)
        self.assertEqual(response, resp)
        self.assertEqual(0, code)
        self.assertEqual("ok", details)

    def test_large_payload(self):
        method = "/test/Large"
        request = b"x" * (1024 * 1024)  # 1 MB
        packed = _pack_request(method, request)
        m, r = _unpack_request(packed)
        self.assertEqual(method, m)
        self.assertEqual(request, r)


class SupportDetectionTest(unittest.TestCase):
    """Tests for runtime support detection."""

    def test_is_supported_reflects_runtime(self):
        result = _is_supported()
        if sys.version_info >= (3, 13):
            self.assertIsInstance(result, bool)
        else:
            self.assertFalse(result)


def _make_echo_servicer_dir():
    """Create a temp directory with a pure-Python echo servicer module."""
    tmpdir = tempfile.mkdtemp(prefix="grpc_subinterp_test_")
    module_file = os.path.join(tmpdir, "_test_echo_servicer.py")
    with open(module_file, "w") as f:
        f.write(
            "class EchoServicer:\n"
            "    def Echo(self, request, context):\n"
            "        return request\n"
            "    def Upper(self, request, context):\n"
            "        return request.upper() if isinstance(request, bytes) else request\n"
        )
    return tmpdir


_ECHO_SPECS = [
    [
        "_test_echo_servicer",
        "EchoServicer",
        [
            ("/test/Echo", None, None, "Echo"),
            ("/test/Upper", None, None, "Upper"),
        ],
    ]
]


@unittest.skipIf(
    not _is_supported(),
    "Sub-interpreter pool requires Python 3.13+ with _interpreters",
)
class SubinterpreterPoolLifecycleTest(unittest.TestCase):
    """Tests for SubinterpreterPool create/start/shutdown."""

    def test_create_and_shutdown_with_handler(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        tmpdir = _make_echo_servicer_dir()
        sys.path.insert(0, tmpdir)
        try:
            pool = SubinterpreterPool(count=1, servicer_specs=_ECHO_SPECS)
            pool.start()
            pool.shutdown()
        finally:
            sys.path.remove(tmpdir)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_worker_count_validation(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        with self.assertRaises(ValueError):
            SubinterpreterPool(count=0, servicer_specs=[])

    def test_double_start_is_idempotent(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        tmpdir = _make_echo_servicer_dir()
        sys.path.insert(0, tmpdir)
        try:
            pool = SubinterpreterPool(count=1, servicer_specs=_ECHO_SPECS)
            pool.start()
            pool.start()  # should not raise
            pool.shutdown()
        finally:
            sys.path.remove(tmpdir)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_double_shutdown_is_idempotent(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        tmpdir = _make_echo_servicer_dir()
        sys.path.insert(0, tmpdir)
        try:
            pool = SubinterpreterPool(count=1, servicer_specs=_ECHO_SPECS)
            pool.start()
            pool.shutdown()
            pool.shutdown()  # should not raise
        finally:
            sys.path.remove(tmpdir)
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_multiple_workers(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        tmpdir = _make_echo_servicer_dir()
        sys.path.insert(0, tmpdir)
        try:
            pool = SubinterpreterPool(count=4, servicer_specs=_ECHO_SPECS)
            pool.start()
            self.assertEqual(4, pool.worker_count)
            pool.shutdown()
        finally:
            sys.path.remove(tmpdir)
            shutil.rmtree(tmpdir, ignore_errors=True)


@unittest.skipIf(
    not _is_supported(),
    "Sub-interpreter pool requires Python 3.13+ with _interpreters",
)
class SubinterpreterPoolDispatchTest(unittest.TestCase):
    """Tests for dispatching work to sub-interpreter workers."""

    def setUp(self):
        self._tmpdir = _make_echo_servicer_dir()
        sys.path.insert(0, self._tmpdir)

    def tearDown(self):
        try:
            sys.path.remove(self._tmpdir)
        except ValueError:
            pass
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_echo_dispatch(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        pool = SubinterpreterPool(count=1, servicer_specs=_ECHO_SPECS)
        pool.start()
        try:
            resp, code, details = pool.dispatch(
                0, "/test/Echo", b"hello world"
            )
            self.assertEqual(0, code)
            self.assertEqual(b"hello world", resp)
            self.assertEqual("", details)
        finally:
            pool.shutdown()

    def test_upper_handler(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        pool = SubinterpreterPool(count=1, servicer_specs=_ECHO_SPECS)
        pool.start()
        try:
            resp, code, _ = pool.dispatch(0, "/test/Upper", b"hello")
            self.assertEqual(0, code)
            self.assertEqual(b"HELLO", resp)
        finally:
            pool.shutdown()

    def test_unknown_method_returns_error(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        pool = SubinterpreterPool(count=1, servicer_specs=_ECHO_SPECS)
        pool.start()
        try:
            resp, code, details = pool.dispatch(
                0, "/test/NonExistent", b"data"
            )
            self.assertEqual(12, code)  # UNIMPLEMENTED
            self.assertIn("not found", details.lower())
        finally:
            pool.shutdown()

    def test_multi_worker_dispatch(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        pool = SubinterpreterPool(count=4, servicer_specs=_ECHO_SPECS)
        pool.start()
        try:
            for shard in range(4):
                data = f"shard-{shard}".encode()
                resp, code, _ = pool.dispatch(
                    shard, "/test/Echo", data
                )
                self.assertEqual(0, code)
                self.assertEqual(data, resp)
        finally:
            pool.shutdown()

    def test_concurrent_dispatch_across_workers(self):
        from grpc._subinterpreter_pool import SubinterpreterPool

        pool = SubinterpreterPool(count=4, servicer_specs=_ECHO_SPECS)
        pool.start()
        try:
            errors = []

            def dispatch_one(idx):
                try:
                    data = f"req-{idx}".encode()
                    resp, code, det = pool.dispatch(
                        idx % 4, "/test/Echo", data
                    )
                    if code != 0 or resp != data:
                        errors.append(
                            f"idx={idx}: code={code} resp={resp} det={det}"
                        )
                except Exception as e:
                    errors.append(f"idx={idx}: {e}")

            threads = [
                threading.Thread(target=dispatch_one, args=(i,))
                for i in range(20)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)
            self.assertEqual([], errors)
        finally:
            pool.shutdown()

    def test_sequential_requests_to_same_worker(self):
        """Multiple sequential requests to the same worker work correctly."""
        from grpc._subinterpreter_pool import SubinterpreterPool

        pool = SubinterpreterPool(count=1, servicer_specs=_ECHO_SPECS)
        pool.start()
        try:
            for i in range(10):
                data = f"seq-{i}".encode()
                resp, code, _ = pool.dispatch(0, "/test/Echo", data)
                self.assertEqual(0, code)
                self.assertEqual(data, resp)
        finally:
            pool.shutdown()


if __name__ == "__main__":
    logging.basicConfig()
    unittest.main(verbosity=2)
