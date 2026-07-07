# Copyright 2022 gRPC authors.
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

import collections
import contextlib
import logging
import os
import subprocess
import sys
import tempfile
import time
from typing import Iterable, List, Mapping, Set, Tuple
import unittest

import grpc.experimental
import xds_interop_client
import xds_interop_server

from src.proto.grpc.testing import empty_pb2
from src.proto.grpc.testing import messages_pb2
from src.proto.grpc.testing import test_pb2
from src.proto.grpc.testing import test_pb2_grpc
import src.python.grpcio_tests.tests.unit.framework.common as framework_common

_CLIENT_PATH = os.path.abspath(os.path.realpath(xds_interop_client.__file__))
_SERVER_PATH = os.path.abspath(os.path.realpath(xds_interop_server.__file__))

_METHODS = (
    (messages_pb2.ClientConfigureRequest.UNARY_CALL, "UNARY_CALL"),
    (messages_pb2.ClientConfigureRequest.EMPTY_CALL, "EMPTY_CALL"),
)

_QPS = 100
_NUM_CHANNELS = 20

_TEST_ITERATIONS = 10
_ITERATION_DURATION_SECONDS = 1
_SUBPROCESS_TIMEOUT_SECONDS = 2

# Maximum number of one-second windows to wait for the client to reach a
# steady state (RPCs flowing with no failures) before asserting on stats.
_WARMUP_MAX_WINDOWS = 30


def _set_union(a: Iterable, b: Iterable) -> Set:
    c = set(a)
    c.update(b)
    return c


@contextlib.contextmanager
def _start_python_with_args(
    file: str, args: List[str]
) -> Tuple[subprocess.Popen, tempfile.TemporaryFile, tempfile.TemporaryFile]:
    with tempfile.TemporaryFile(mode="r") as stdout:
        with tempfile.TemporaryFile(mode="r") as stderr:
            proc = subprocess.Popen(
                (sys.executable, file) + tuple(args),
                stdout=stdout,
                stderr=stderr,
            )
            yield proc, stdout, stderr


def _dump_stream(
    process_name: str, stream_name: str, stream: tempfile.TemporaryFile
):
    sys.stderr.write(f"{process_name} {stream_name}:\n")
    stream.seek(0)
    sys.stderr.write(stream.read())


def _dump_streams(
    process_name: str,
    stdout: tempfile.TemporaryFile,
    stderr: tempfile.TemporaryFile,
):
    _dump_stream(process_name, "stdout", stdout)
    _dump_stream(process_name, "stderr", stderr)
    sys.stderr.write(f"End {process_name} output.\n")


def _index_accumulated_stats(
    response: messages_pb2.LoadBalancerAccumulatedStatsResponse,
) -> Mapping[str, Mapping[int, int]]:
    indexed = collections.defaultdict(lambda: collections.defaultdict(int))
    for _, method_str in _METHODS:
        for status in response.stats_per_method[method_str].result.keys():
            indexed[method_str][status] = response.stats_per_method[
                method_str
            ].result[status]
    return indexed


def _subtract_indexed_stats(
    a: Mapping[str, Mapping[int, int]], b: Mapping[str, Mapping[int, int]]
):
    c = collections.defaultdict(lambda: collections.defaultdict(int))
    all_methods = _set_union(a.keys(), b.keys())
    for method in all_methods:
        all_statuses = _set_union(a[method].keys(), b[method].keys())
        for status in all_statuses:
            c[method][status] = a[method][status] - b[method][status]
    return c


def _collect_stats(
    stats_port: int, duration: int
) -> Mapping[str, Mapping[int, int]]:
    settings = {
        "target": f"127.0.0.1:{stats_port}",
        "insecure": True,
    }
    response = test_pb2_grpc.LoadBalancerStatsService.GetClientAccumulatedStats(
        messages_pb2.LoadBalancerAccumulatedStatsRequest(), **settings
    )
    before = _index_accumulated_stats(response)
    time.sleep(duration)
    response = test_pb2_grpc.LoadBalancerStatsService.GetClientAccumulatedStats(
        messages_pb2.LoadBalancerAccumulatedStatsRequest(), **settings
    )
    after = _index_accumulated_stats(response)
    return _subtract_indexed_stats(after, before)


class XdsInteropClientTest(unittest.TestCase):
    def _await_client_steady_state(self, stats_port: int) -> None:
        """Waits until the client's RPCs flow with no failures.

        Right after startup, the client fires _QPS RPCs per second from each
        of its _NUM_CHANNELS channels while the channels are still
        connecting and the server process is still warming up. On a loaded
        machine (e.g. --runs_per_test with several copies of this test in
        parallel), RPCs started during this window can fail with transient
        statuses that have nothing to do with the configure-consistency
        property this test asserts on. Wait for a clean one-second window
        before asserting. If the client never stabilizes, proceed and let
        the assertions report the failure with full stats.
        """
        for _ in range(_WARMUP_MAX_WINDOWS):
            try:
                delta = _collect_stats(stats_port, 1)
            except grpc.RpcError:
                # The client's stats server may not be listening yet.
                time.sleep(1)
                continue
            succeeded = sum(
                count
                for method_stats in delta.values()
                for status, count in method_stats.items()
                if status == 0
            )
            failed = sum(
                count
                for method_stats in delta.values()
                for status, count in method_stats.items()
                if status != 0
            )
            if succeeded > 0 and failed == 0:
                return
        logging.warning(
            "Client did not reach a steady state; proceeding anyway."
        )

    def _assert_client_consistent(
        self, server_port: int, stats_port: int, qps: int, num_channels: int
    ):
        settings = {
            "target": f"127.0.0.1:{stats_port}",
            "insecure": True,
        }
        for i in range(_TEST_ITERATIONS):
            target_method, target_method_str = _METHODS[i % len(_METHODS)]
            test_pb2_grpc.XdsUpdateClientConfigureService.Configure(
                messages_pb2.ClientConfigureRequest(types=[target_method]),
                **settings,
            )
            delta = _collect_stats(stats_port, _ITERATION_DURATION_SECONDS)
            logging.info("Delta: %s", delta)
            for _, method_str in _METHODS:
                for status in delta[method_str]:
                    if status == 0 and method_str == target_method_str:
                        self.assertGreater(delta[method_str][status], 0, delta)
                    else:
                        self.assertEqual(delta[method_str][status], 0, delta)

    def test_configure_consistency(self):
        _, server_port, socket = framework_common.get_socket()

        with _start_python_with_args(
            _SERVER_PATH,
            [f"--port={server_port}", f"--maintenance_port={server_port}"],
        ) as (server, server_stdout, server_stderr):
            # Release the port reservation before probing the server. The
            # server binds the wildcard address while the reservation socket
            # listens on 127.0.0.1; TCP routes connections to the most
            # specific listener, so keeping the reservation open would
            # swallow the probe RPC (and every subsequent connection) into a
            # socket that never accepts. wait_for_ready below retries until
            # the server has bound the released port.
            socket.close()
            # Send RPC to server to make sure it's running.
            logging.info("Sending RPC to server.")
            test_pb2_grpc.TestService.EmptyCall(
                empty_pb2.Empty(),
                f"127.0.0.1:{server_port}",
                insecure=True,
                wait_for_ready=True,
            )
            logging.info("Server successfully started.")
            _, stats_port, stats_socket = framework_common.get_socket()
            with _start_python_with_args(
                _CLIENT_PATH,
                [
                    f"--server=127.0.0.1:{server_port}",
                    f"--stats_port={stats_port}",
                    f"--qps={_QPS}",
                    f"--num_channels={_NUM_CHANNELS}",
                ],
            ) as (client, client_stdout, client_stderr):
                stats_socket.close()
                try:
                    self._await_client_steady_state(stats_port)
                    self._assert_client_consistent(
                        server_port, stats_port, _QPS, _NUM_CHANNELS
                    )
                except:
                    _dump_streams("server", server_stdout, server_stderr)
                    _dump_streams("client", client_stdout, client_stderr)
                    raise
                finally:
                    server.kill()
                    client.kill()
                    server.wait(timeout=_SUBPROCESS_TIMEOUT_SECONDS)
                    client.wait(timeout=_SUBPROCESS_TIMEOUT_SECONDS)


if __name__ == "__main__":
    logging.basicConfig()
    unittest.main(verbosity=2)
