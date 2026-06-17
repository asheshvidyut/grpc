# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

import argparse
import os
import sys
import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _GEN_DIR)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="localhost", help="Host of the server")
    parser.add_argument("--port", type=int, default=50099, help="Port of the server")
    parser.add_argument("--message", type=str, default="Hello World from gRPC Native C++ Flow", help="Message to send")
    args = parser.parse_args()

    # Check if generated protobuf modules exist
    try:
        import echo_pb2
        import echo_pb2_grpc
    except ImportError:
        print("Protobuf modules not generated. Please start the server first to generate them.")
        sys.exit(1)

    target = f"{args.host}:{args.port}"
    print(f"Connecting to server at {target}...")
    with grpc.insecure_channel(target) as channel:
        stub = echo_pb2_grpc.EchoServiceStub(channel)

        # 1. Test Unary-Unary Echo with custom metadata
        print("\n--- Testing Unary-Unary Echo ---")
        request = echo_pb2.EchoRequest(message=args.message)
        print(f"Sending Unary Request: '{request.message}'")
        response = stub.Echo(request, metadata=(('client-id', 'test-client-123'),))
        print(f"Received Unary Response: '{response.message}'")

        # 2. Test Unary-Stream EchoStream with custom metadata
        print("\n--- Testing Unary-Stream EchoStream ---")
        print(f"Sending Streaming Request: '{request.message}'")
        responses = stub.EchoStream(request, metadata=(('client-id', 'test-client-123'),))
        print("Received Stream Messages:")
        for i, resp in enumerate(responses):
            print(f"  [{i}] '{resp.message}'")

if __name__ == "__main__":
    main()
