# gRPC Python Rust Bindings

This directory contains Rust-based implementations of gRPC functionality as a replacement for the Cython implementation.

## Overview

The Rust bindings provide the same API as the Cython implementation but with improved performance, memory safety, and concurrency handling. The implementation uses PyO3 for Python bindings and the official gRPC Rust crate.

## Features

- **Channel Management**: Create and manage gRPC channels
- **Server Implementation**: Build gRPC servers with async support
- **Call Handling**: Manage individual gRPC calls with cancellation support
- **Completion Queue**: Handle completion events
- **Credentials**: Support for SSL/TLS and call credentials
- **Metadata**: Request/response metadata handling
- **Status Codes**: Comprehensive status code support
- **Async/Await**: Full async/await support for modern Python

## Architecture

The implementation is structured as follows:

```
src/
├── lib.rs              # Main module entry point
├── channel.rs          # Channel implementation
├── server.rs           # Server implementation
├── call.rs             # Call implementation
├── completion_queue.rs  # Completion queue
├── credentials.rs      # Credentials handling
├── metadata.rs         # Metadata management
├── status.rs           # Status codes and error handling
└── aio.rs              # Async/await implementations
```

## Building

### Prerequisites

- Rust 1.70+ with Cargo
- Python 3.7+
- gRPC Rust dependencies

### Build Commands

```bash
# Build the Rust extension
cd src/python/grpcio/grpc/_rust
cargo build --release

# Install the Python package
python setup.py install
```

## Usage

The Rust bindings provide a drop-in replacement for the Cython implementation:

```python
# Import the Rust bindings
from grpc._rust import Channel, Server, Call, CompletionQueue

# Create a channel
channel = Channel("localhost:50051", options={"max_receive_message_length": "4194304"})
channel.connect()

# Create a server
server = Server("localhost", 50051, options={"max_concurrent_streams": "100"})
server.start()

# Create a call
call = Call("my_method", deadline=30.0, metadata={"user-agent": "rust-grpc"})
call.start_call(channel)

# Send and receive messages
call.send_message(b"Hello, gRPC!")
response = call.recv_message()
call.finish()
```

## Async/Await Support

The Rust implementation provides full async/await support:

```python
import asyncio
from grpc._rust import AioChannel, AioServer, AioCall

async def main():
    # Async channel
    channel = AioChannel("localhost:50051")
    await channel.connect()
    
    # Async server
    server = AioServer("localhost", 50051)
    await server.start()
    
    # Async call
    call = AioCall("my_method")
    await call.start_call(channel)
    
    await call.send_message(b"Hello, async gRPC!")
    response = await call.recv_message()
    await call.finish()

asyncio.run(main())
```

## Performance Benefits

The Rust implementation offers several performance advantages:

1. **Memory Safety**: Rust's ownership system prevents memory leaks and data races
2. **Zero-Cost Abstractions**: High-level abstractions without runtime overhead
3. **Concurrent Safety**: Thread-safe by design with async/await support
4. **Native Performance**: Direct access to gRPC C++ core without Python GIL limitations

## Migration from Cython

The Rust bindings are designed to be a drop-in replacement for the Cython implementation. The API is identical, so existing code should work without modification.

To use the Rust bindings instead of Cython:

```python
# Instead of:
from grpc._cython import cygrpc

# Use:
from grpc._rust import Channel, Server, Call
```

## Error Handling

The Rust implementation provides comprehensive error handling with proper Python exceptions:

```python
try:
    call = Call("invalid_method")
    call.start_call(channel)
except ValueError as e:
    print(f"Call error: {e}")
```

## Status Codes

All gRPC status codes are supported:

```python
from grpc._rust import Status, GRPC_STATUS_OK, GRPC_STATUS_CANCELLED

status = Status(GRPC_STATUS_OK, "Success", "Operation completed successfully")
print(status.is_ok())  # True
```

## Development

### Adding New Features

1. Add the Rust implementation in the appropriate module
2. Add Python bindings using PyO3
3. Update the main `lib.rs` to register the new class
4. Add tests and documentation

### Testing

```bash
# Run Rust tests
cargo test

# Run Python tests
python -m pytest tests/
```

## Contributing

1. Follow Rust coding standards
2. Add comprehensive tests
3. Update documentation
4. Ensure backward compatibility with Cython API

## License

This implementation is licensed under the Apache License 2.0, same as the main gRPC project. 