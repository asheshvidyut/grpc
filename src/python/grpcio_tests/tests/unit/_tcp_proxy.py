# Copyright 2019 the gRPC authors.
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
"""Proxies a TCP connection between a single client-server pair.

This proxy is not suitable for production, but should work well for cases in
which a test needs to spy on the bytes put on the wire between a server and
a client.
"""

import datetime
import select
import socket
import threading

import time

from tests.unit.framework.common import get_socket

_BUFFER_SIZE = 8192


def _init_proxy_socket(gateway_address, gateway_port, stop_event=None):
    for i in range(10):
        if stop_event is not None and stop_event.is_set():
            return None
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(0.5)
            sock.connect((gateway_address, gateway_port))
            sock.settimeout(None)
            return sock
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
            if stop_event is not None and stop_event.is_set():
                return None
            if i == 9:
                raise
            time.sleep(0.02)


class TcpProxy:
    """Proxies a TCP connection between one client and one server."""

    def __init__(self, bind_address, gateway_address, gateway_port):
        self._bind_address = bind_address
        self._gateway_address = gateway_address
        self._gateway_port = gateway_port

        self._byte_count_lock = threading.RLock()
        self._socket_lock = threading.Lock()
        self._sent_byte_count = 0
        self._received_byte_count = 0

        self._stop_event = threading.Event()

        self._port = None
        self._listen_socket = None
        self._active_sockets = []
        self._threads = []

        self._accept_thread = threading.Thread(target=self._run_accept_loop)

    def start(self):
        _, self._port, self._listen_socket = get_socket(
            bind_address=self._bind_address,
            listen=True,
            sock_options=(socket.SO_REUSEADDR,),
        )
        self._accept_thread.start()

    def get_port(self):
        return self._port

    def _pipe(self, src, dst, is_southbound):
        while not self._stop_event.is_set():
            try:
                data = src.recv(_BUFFER_SIZE)
                if not data:
                    break
                with self._byte_count_lock:
                    if is_southbound:
                        self._sent_byte_count += len(data)
                    else:
                        self._received_byte_count += len(data)
                dst.sendall(data)
            except Exception:
                break
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass

    def _run_accept_loop(self):
        while not self._stop_event.is_set():
            try:
                client_sock, _ = self._listen_socket.accept()
            except Exception:
                break

            if self._stop_event.is_set():
                try:
                    client_sock.close()
                except Exception:
                    pass
                break

            try:
                proxy_sock = _init_proxy_socket(
                    self._gateway_address,
                    self._gateway_port,
                    self._stop_event,
                )
                if proxy_sock is None:
                    try:
                        client_sock.close()
                    except Exception:
                        pass
                    break
            except Exception:
                try:
                    client_sock.close()
                except Exception:
                    pass
                continue

            with self._socket_lock:
                self._active_sockets.extend([client_sock, proxy_sock])

            t1 = threading.Thread(
                target=self._pipe,
                args=(client_sock, proxy_sock, True),
            )
            t2 = threading.Thread(
                target=self._pipe,
                args=(proxy_sock, client_sock, False),
            )
            t1.daemon = True
            t2.daemon = True
            t1.start()
            t2.start()
            with self._socket_lock:
                self._threads.extend([t1, t2])

    def stop(self):
        self._stop_event.set()
        with self._socket_lock:
            for sock in self._active_sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    sock.close()
                except Exception:
                    pass
            self._active_sockets = []
        if self._listen_socket:
            port = self._port
            addr = self._bind_address
            try:
                self._listen_socket.close()
            except Exception:
                pass
            if port and addr:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.1)
                    s.connect((addr, port))
                    s.close()
                except Exception:
                    pass
        if self._accept_thread.is_alive():
            self._accept_thread.join(timeout=1.0)
        with self._socket_lock:
            threads = list(self._threads)
            self._threads = []
        for t in threads:
            if t.is_alive():
                t.join(timeout=0.5)

    def get_byte_count(self):
        with self._byte_count_lock:
            return self._sent_byte_count, self._received_byte_count

    def reset_byte_count(self):
        with self._byte_count_lock:
            self._sent_byte_count = 0
            self._received_byte_count = 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
