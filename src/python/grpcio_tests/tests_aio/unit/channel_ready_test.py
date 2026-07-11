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
"""Testing the channel_ready function."""

import asyncio
import gc
import logging
import os
import socket
import time
import unittest
import uuid

import grpc
from grpc.experimental import aio

from tests.unit.framework.common import get_socket
from tests.unit.framework.common import test_constants
from tests_aio.unit import _common
from tests_aio.unit._test_base import AioTestBase


class TestChannelReady(AioTestBase):
    async def setUp(self):
        if os.name == "nt":
            address, self._port, self._socket = get_socket(
                listen=False, sock_options=(socket.SO_REUSEADDR,)
            )
            self._address = f"{address}:{self._port}"
            self._socket.close()
        else:
            # Use a Unix domain socket path instead of a reserved-then-
            # released TCP port. channel_ready() only exercises channel
            # state transitions, and a TCP port cannot be made safe here:
            # holding the reservation makes macOS silently drop the
            # channel's SYNs (stalling the TRANSIENT_FAILURE phase), while
            # releasing it lets any concurrent process squat the port
            # (even as an ephemeral source port, which then fails the
            # server's dual-stack bind with EADDRINUSE). A nonexistent UDS
            # path fails connects deterministically and stays exclusively
            # ours to bind later.
            self._address = "unix:/tmp/grpc_channel_ready_%s" % (
                uuid.uuid4().hex
            )
        self._channel = aio.insecure_channel(self._address)

    async def tearDown(self):
        await self._channel.close()

    async def test_channel_ready_success(self):
        # Start `channel_ready` as another Task
        channel_ready_task = self.loop.create_task(
            self._channel.channel_ready()
        )

        # Wait for TRANSIENT_FAILURE
        await _common.block_until_certain_state(
            self._channel, grpc.ChannelConnectivity.TRANSIENT_FAILURE
        )

        server = None
        try:
            # Start a server on the address the channel is dialing.
            server = aio.server()
            server.add_insecure_port(self._address)
            await server.start()

            # The RPC should recover itself
            await channel_ready_task
        finally:
            if server:
                await server.stop(None)

    @unittest.skip(
        "skipping due to flake: https://github.com/grpc/grpc/issues/37949"
    )
    async def test_channel_ready_blocked(self):
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self._channel.channel_ready(), test_constants.SHORT_TIMEOUT
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main(verbosity=2)
