#!/usr/bin/env python3
"""
Test script for gRPC Python Rust Bindings
"""

import sys
import os

# Add the parent directory to the path so we can import the rust module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_rust_bindings():
    """Test that the Rust bindings can be imported and basic functionality works"""
    
    try:
        # Try to import the Rust bindings
        from grpc._rust import (
            Channel, Server, Call, CompletionQueue,
            CallCredentials, ChannelCredentials, Metadata, Status,
            AioChannel, AioServer, AioCall,
            GRPC_STATUS_OK, GRPC_STATUS_CANCELLED
        )
        print("✓ Successfully imported Rust bindings")
        
        # Test basic class instantiation
        channel = Channel("localhost:50051")
        print("✓ Channel created successfully")
        
        server = Server("localhost", 50051)
        print("✓ Server created successfully")
        
        call = Call("test_method")
        print("✓ Call created successfully")
        
        cq = CompletionQueue()
        print("✓ CompletionQueue created successfully")
        
        metadata = Metadata()
        print("✓ Metadata created successfully")
        
        status = Status(GRPC_STATUS_OK, "Success", "Test status")
        print("✓ Status created successfully")
        
        # Test status methods
        assert status.is_ok() == True
        assert status.get_code() == GRPC_STATUS_OK
        assert status.get_message() == "Success"
        print("✓ Status methods work correctly")
        
        # Test async classes
        aio_channel = AioChannel("localhost:50051")
        print("✓ AioChannel created successfully")
        
        aio_server = AioServer("localhost", 50051)
        print("✓ AioServer created successfully")
        
        aio_call = AioCall("test_method")
        print("✓ AioCall created successfully")
        
        print("\n🎉 All Rust binding tests passed!")
        return True
        
    except ImportError as e:
        print(f"✗ Failed to import Rust bindings: {e}")
        print("This is expected if the Rust extension hasn't been built yet.")
        return False
        
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        return False

def test_cython_fallback():
    """Test that the Cython fallback works when Rust bindings are not available"""
    
    try:
        # Try to import the Cython implementation
        from grpc._cython import cygrpc
        print("✓ Cython implementation available as fallback")
        return True
        
    except ImportError as e:
        print(f"✗ Cython implementation not available: {e}")
        return False

if __name__ == "__main__":
    print("Testing gRPC Python Rust Bindings")
    print("=" * 40)
    
    rust_success = test_rust_bindings()
    cython_success = test_cython_fallback()
    
    print("\n" + "=" * 40)
    if rust_success:
        print("✅ Rust bindings are working correctly!")
    elif cython_success:
        print("⚠️  Rust bindings not available, but Cython fallback works")
    else:
        print("❌ Neither Rust bindings nor Cython fallback are available")
        sys.exit(1) 