# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Client for the protobuf-aware native echo example.

The client uses generated Python protobuf code; the server-side parses with
libprotobuf in C++.
"""

import os
import subprocess
import sys

import grpc

# Generate echo_pb2 on the fly so the example is self-contained.
_PB2_PATH = os.path.join(os.path.dirname(__file__), "echo_pb2.py")
if not os.path.isfile(_PB2_PATH):
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            "-I",
            os.path.dirname(__file__),
            f"--python_out={os.path.dirname(__file__)}",
            os.path.join(os.path.dirname(__file__), "echo.proto"),
        ]
    )

sys.path.insert(0, os.path.dirname(__file__))
import echo_pb2  # noqa: E402


def main(target: str = "localhost:50052") -> None:
    with grpc.insecure_channel(target) as channel:
        # Note: request_serializer / response_deserializer are protobuf here
        # because the client uses generated python proto; the server-side
        # native handler also uses protobuf wire format.
        echo = channel.unary_unary(
            "/echo.Echo/Echo",
            request_serializer=echo_pb2.EchoRequest.SerializeToString,
            response_deserializer=echo_pb2.EchoResponse.FromString,
        )

        req = echo_pb2.EchoRequest(message="hi-", repeat=3)
        resp = echo(req)
        assert resp.message == "hi-hi-hi-", resp.message
        print("echo ok:", resp.message)

        # Invalid: repeat out of range
        try:
            echo(echo_pb2.EchoRequest(message="x", repeat=999999))
        except grpc.RpcError as e:
            print(
                "invalid-arg correctly returned",
                e.code(),  # type: ignore[attr-defined]
                "—",
                e.details(),  # type: ignore[attr-defined]
            )


if __name__ == "__main__":
    main()
