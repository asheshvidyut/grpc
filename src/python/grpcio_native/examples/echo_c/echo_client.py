# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Client for the native echo example.

Skips protobuf: passes raw bytes through grpc.Channel.unary_unary with
request_serializer=None / response_deserializer=None. The server's native
handler echoes them.
"""

import struct
import sys

import grpc


def main(target: str = "localhost:50051") -> None:
    with grpc.insecure_channel(target) as channel:
        echo = channel.unary_unary("/echo.Echo/Echo")
        double = channel.unary_unary("/echo.Echo/Double")
        not_found = channel.unary_unary("/echo.Echo/NotFound")

        # 1. Echo: raw round-trip.
        payload = b"hello from python, processed in C without the GIL"
        response = echo(payload)
        assert response == payload, (response, payload)
        print("echo ok:", response.decode())

        # 2. Double: 4-byte uint32 wire format encoded in Python, doubled in C.
        for n in (1, 17, 1_000_000):
            response = double(struct.pack("<I", n))
            (result,) = struct.unpack("<I", response)
            assert result == n * 2, (n, result)
            print(f"double({n}) = {result}")

        # 3. Always not-found: status propagation from C.
        try:
            not_found(b"")
        except grpc.RpcError as e:
            print(
                "not_found correctly returned",
                e.code(),  # type: ignore[attr-defined]
                "—",
                e.details(),  # type: ignore[attr-defined]
            )
        else:
            sys.exit("expected RpcError for /NotFound")


if __name__ == "__main__":
    main()
