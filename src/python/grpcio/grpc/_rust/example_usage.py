#!/usr/bin/env python3
"""
Example usage of gRPC Python Rust Bindings

This example demonstrates how to use the Rust bindings to create
a simple gRPC client and server.
"""

import asyncio
import time
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def example_sync_usage():
    """Example of synchronous gRPC usage with Rust bindings"""
    
    try:
        from grpc._rust import Channel, Server, Call, CompletionQueue, Metadata, Status, GRPC_STATUS_OK
        
        print("=== Synchronous gRPC Example ===")
        
        # Create a completion queue
        cq = CompletionQueue()
        cq.start()
        print("✓ Completion queue started")
        
        # Create a server
        server = Server("localhost", 50051, options={"max_concurrent_streams": "10"})
        server.start()
        print("✓ Server started on localhost:50051")
        
        # Create a channel
        channel = Channel("localhost:50051", options={"max_receive_message_length": "4194304"})
        channel.connect()
        print("✓ Channel connected")
        
        # Create a call
        metadata = Metadata()
        metadata.add("user-agent", "rust-grpc-example")
        metadata.add("content-type", "application/grpc")
        
        call = Call("example_method", deadline=30.0, metadata=metadata)
        call.start_call(channel)
        print("✓ Call started")
        
        # Send a message
        message = b"Hello from Rust gRPC!"
        call.send_message(message)
        print(f"✓ Sent message: {message}")
        
        # Receive response
        response = call.recv_message()
        print(f"✓ Received response: {response}")
        
        # Finish the call
        call.finish()
        print("✓ Call finished")
        
        # Cleanup
        channel.disconnect()
        server.shutdown()
        cq.shutdown()
        print("✓ Cleanup completed")
        
    except ImportError as e:
        print(f"✗ Rust bindings not available: {e}")
        print("Please build the Rust extension first using: ./build.sh")
        return False
        
    except Exception as e:
        print(f"✗ Error in sync example: {e}")
        return False
    
    return True

async def example_async_usage():
    """Example of asynchronous gRPC usage with Rust bindings"""
    
    try:
        from grpc._rust import AioChannel, AioServer, AioCall, Metadata
        
        print("\n=== Asynchronous gRPC Example ===")
        
        # Create an async server
        server = AioServer("localhost", 50052, options={"max_concurrent_streams": "10"})
        await server.start()
        print("✓ Async server started on localhost:50052")
        
        # Create an async channel
        channel = AioChannel("localhost:50052", options={"max_receive_message_length": "4194304"})
        await channel.connect()
        print("✓ Async channel connected")
        
        # Create an async call
        metadata = Metadata()
        metadata.add("user-agent", "rust-grpc-async-example")
        metadata.add("content-type", "application/grpc")
        
        call = AioCall("async_example_method", deadline=30.0, metadata=metadata)
        await call.start_call(channel)
        print("✓ Async call started")
        
        # Send a message asynchronously
        message = b"Hello from async Rust gRPC!"
        await call.send_message(message)
        print(f"✓ Sent async message: {message}")
        
        # Receive response asynchronously
        response = await call.recv_message()
        print(f"✓ Received async response: {response}")
        
        # Finish the call
        await call.finish()
        print("✓ Async call finished")
        
        # Cleanup
        await channel.disconnect()
        await server.shutdown()
        print("✓ Async cleanup completed")
        
    except ImportError as e:
        print(f"✗ Rust bindings not available: {e}")
        return False
        
    except Exception as e:
        print(f"✗ Error in async example: {e}")
        return False
    
    return True

def example_status_handling():
    """Example of status code handling"""
    
    try:
        from grpc._rust import Status, GRPC_STATUS_OK, GRPC_STATUS_CANCELLED, GRPC_STATUS_INVALID_ARGUMENT
        
        print("\n=== Status Code Example ===")
        
        # Create different status objects
        ok_status = Status(GRPC_STATUS_OK, "Success", "Operation completed successfully")
        cancelled_status = Status(GRPC_STATUS_CANCELLED, "Cancelled", "Operation was cancelled")
        invalid_status = Status(GRPC_STATUS_INVALID_ARGUMENT, "Invalid Argument", "Invalid parameter provided")
        
        # Test status methods
        print(f"OK status: {ok_status.to_string()}")
        print(f"  is_ok: {ok_status.is_ok()}")
        print(f"  code: {ok_status.get_code()}")
        print(f"  message: {ok_status.get_message()}")
        
        print(f"Cancelled status: {cancelled_status.to_string()}")
        print(f"  is_cancelled: {cancelled_status.is_cancelled()}")
        
        print(f"Invalid status: {invalid_status.to_string()}")
        print(f"  is_invalid_argument: {invalid_status.is_invalid_argument()}")
        
        print("✓ Status handling example completed")
        
    except ImportError as e:
        print(f"✗ Rust bindings not available: {e}")
        return False
        
    except Exception as e:
        print(f"✗ Error in status example: {e}")
        return False
    
    return True

def example_metadata_handling():
    """Example of metadata handling"""
    
    try:
        from grpc._rust import Metadata
        
        print("\n=== Metadata Example ===")
        
        # Create metadata
        metadata = Metadata()
        metadata.add("user-agent", "rust-grpc-client")
        metadata.add("authorization", "Bearer token123")
        metadata.add("content-type", "application/grpc")
        metadata.add("x-custom-header", "custom-value")
        
        # Test metadata operations
        print(f"Metadata length: {metadata.len()}")
        print(f"Is empty: {metadata.is_empty()}")
        
        # Get specific values
        user_agent = metadata.get("user-agent")
        auth = metadata.get("authorization")
        print(f"User-Agent: {user_agent}")
        print(f"Authorization: {auth}")
        
        # Remove a key
        metadata.remove("x-custom-header")
        print(f"After removal, length: {metadata.len()}")
        
        # Clear all metadata
        metadata.clear()
        print(f"After clear, is empty: {metadata.is_empty()}")
        
        print("✓ Metadata handling example completed")
        
    except ImportError as e:
        print(f"✗ Rust bindings not available: {e}")
        return False
        
    except Exception as e:
        print(f"✗ Error in metadata example: {e}")
        return False
    
    return True

async def main():
    """Run all examples"""
    
    print("gRPC Python Rust Bindings - Usage Examples")
    print("=" * 50)
    
    # Run synchronous example
    sync_success = example_sync_usage()
    
    # Run asynchronous example
    async_success = await example_async_usage()
    
    # Run status handling example
    status_success = example_status_handling()
    
    # Run metadata handling example
    metadata_success = example_metadata_handling()
    
    print("\n" + "=" * 50)
    print("Example Results:")
    print(f"  Synchronous: {'✓' if sync_success else '✗'}")
    print(f"  Asynchronous: {'✓' if async_success else '✗'}")
    print(f"  Status Handling: {'✓' if status_success else '✗'}")
    print(f"  Metadata Handling: {'✓' if metadata_success else '✗'}")
    
    if all([sync_success, async_success, status_success, metadata_success]):
        print("\n🎉 All examples completed successfully!")
    else:
        print("\n⚠️  Some examples failed. Check the output above for details.")

if __name__ == "__main__":
    asyncio.run(main()) 