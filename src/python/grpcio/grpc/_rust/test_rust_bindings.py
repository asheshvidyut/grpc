#!/usr/bin/env python3
"""
Simple test for gRPC Rust bindings stub.
"""

import sys
import os

# Add the current directory to the path so we can import the rust module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from __init__ import (
        Channel, Server, Call, CompletionQueue, CallCredentials,
        Metadata, Status, AioChannel, AioServer, AioCall,
        BaseEvent, CompressionAlgorithm, _cygrpc,
        GRPC_STATUS_OK, GRPC_STATUS_CANCELLED,
        GRPC_COMPRESS_NONE, GRPC_COMPRESS_DEFLATE, GRPC_COMPRESS_GZIP
    )
    print("✅ Successfully imported Rust bindings")
except ImportError as e:
    print(f"❌ Failed to import Rust bindings: {e}")
    sys.exit(1)

def test_basic_classes():
    """Test basic class instantiation."""
    try:
        # Test Channel
        channel = Channel("localhost:50051")
        assert channel.target == "localhost:50051"
        assert not channel.is_closed()
        channel.close()
        assert channel.is_closed()
        print("✅ Channel class works")

        # Test Server
        server = Server()
        assert not server.is_started()
        assert not server.is_stopped()
        server.start()
        assert server.is_started()
        server.stop()
        assert server.is_stopped()
        print("✅ Server class works")

        # Test Call
        call = Call(channel, "/test/method", "localhost")
        assert call.method == "/test/method"
        assert call.host == "localhost"
        assert not call.is_cancelled()
        call.cancel()
        assert call.is_cancelled()
        print("✅ Call class works")

        # Test CompletionQueue
        cq = CompletionQueue()
        assert not cq.is_shutdown()
        cq.shutdown()
        assert cq.is_shutdown()
        print("✅ CompletionQueue class works")

        # Test Metadata
        metadata = Metadata()
        metadata.add("key", "value")
        assert metadata.get("key") == "value"
        assert len(metadata) == 1
        print("✅ Metadata class works")

        # Test Status
        status = Status(GRPC_STATUS_OK, "Success")
        assert status.get_code() == GRPC_STATUS_OK
        assert status.get_message() == "Success"
        assert status.is_ok()
        print("✅ Status class works")

        # Test constants
        assert GRPC_STATUS_OK == 0
        assert GRPC_STATUS_CANCELLED == 1
        assert GRPC_COMPRESS_NONE == 0
        assert GRPC_COMPRESS_DEFLATE == 1
        assert GRPC_COMPRESS_GZIP == 2
        print("✅ Constants are correct")

        # Test _cygrpc module
        assert hasattr(_cygrpc, 'Channel')
        assert hasattr(_cygrpc, 'Server')
        assert hasattr(_cygrpc, 'Call')
        assert hasattr(_cygrpc, 'CompletionQueue')
        assert hasattr(_cygrpc, 'GRPC_STATUS_OK')
        print("✅ _cygrpc module has expected attributes")

        print("✅ All basic class tests passed!")
        return True

    except Exception as e:
        print(f"❌ Basic class test failed: {e}")
        return False

def test_async_classes():
    """Test async class instantiation."""
    try:
        # Test AioChannel
        aio_channel = AioChannel("localhost:50051")
        assert aio_channel.target == "localhost:50051"
        assert not aio_channel.is_closed()
        print("✅ AioChannel class works")

        # Test AioServer
        aio_server = AioServer()
        assert not aio_server.is_started()
        assert not aio_server.is_stopped()
        print("✅ AioServer class works")

        # Test AioCall
        aio_call = AioCall(aio_channel, "/test/method", "localhost")
        assert aio_call.method == "/test/method"
        assert aio_call.host == "localhost"
        assert not aio_call.is_cancelled()
        print("✅ AioCall class works")

        print("✅ All async class tests passed!")
        return True

    except Exception as e:
        print(f"❌ Async class test failed: {e}")
        return False

def test_utility_functions():
    """Test utility functions."""
    try:
        from __init__ import (
            create_insecure_channel, create_server, create_completion_queue,
            create_metadata, create_status, create_deadline,
            create_compression_algorithm, create_write_flags, create_call_flags
        )

        # Test utility functions
        channel = create_insecure_channel("localhost:50051")
        assert isinstance(channel, Channel)

        server = create_server()
        assert isinstance(server, Server)

        cq = create_completion_queue()
        assert isinstance(cq, CompletionQueue)

        metadata = create_metadata()
        assert isinstance(metadata, Metadata)

        status = create_status(GRPC_STATUS_OK, "Success")
        assert isinstance(status, Status)

        deadline = create_deadline(30.0)
        assert deadline.get_timeout_seconds() == 30.0

        comp_algo = create_compression_algorithm("gzip")
        assert comp_algo.get_algorithm() == "gzip"

        write_flags = create_write_flags(0)
        assert isinstance(write_flags, type(create_write_flags(0)))

        call_flags = create_call_flags(0)
        assert isinstance(call_flags, type(create_call_flags(0)))

        print("✅ All utility function tests passed!")
        return True

    except Exception as e:
        print(f"❌ Utility function test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing gRPC Rust bindings stub...")
    print("=" * 50)

    tests = [
        test_basic_classes,
        test_async_classes,
        test_utility_functions,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1
        print()

    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The Rust bindings stub is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 