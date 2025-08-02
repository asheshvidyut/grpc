"""
gRPC Python Rust Bindings

This module provides Rust-based implementations of gRPC functionality
as a replacement for the Cython implementation.
"""

try:
    from .grpc_rust_bindings import (
        Channel,
        Server,
        Call,
        CompletionQueue,
        CallCredentials,
        ChannelCredentials,
        Metadata,
        Status,
        AioChannel,
        AioServer,
        AioCall,
        # Constants
        GRPC_STATUS_OK,
        GRPC_STATUS_CANCELLED,
        GRPC_STATUS_UNKNOWN,
        GRPC_STATUS_INVALID_ARGUMENT,
        GRPC_STATUS_DEADLINE_EXCEEDED,
        GRPC_STATUS_NOT_FOUND,
        GRPC_STATUS_ALREADY_EXISTS,
        GRPC_STATUS_PERMISSION_DENIED,
        GRPC_STATUS_UNAUTHENTICATED,
        GRPC_STATUS_RESOURCE_EXHAUSTED,
        GRPC_STATUS_FAILED_PRECONDITION,
        GRPC_STATUS_ABORTED,
        GRPC_STATUS_OUT_OF_RANGE,
        GRPC_STATUS_UNIMPLEMENTED,
        GRPC_STATUS_INTERNAL,
        GRPC_STATUS_UNAVAILABLE,
        GRPC_STATUS_DATA_LOSS,
    )
except ImportError:
    # Fallback to Cython implementation if Rust bindings are not available
    from .._cython import cygrpc
    
    # Re-export Cython classes
    Channel = cygrpc.Channel
    Server = cygrpc.Server
    Call = cygrpc.Call
    CompletionQueue = cygrpc.CompletionQueue
    CallCredentials = cygrpc.CallCredentials
    ChannelCredentials = cygrpc.ChannelCredentials
    Metadata = cygrpc.Metadata
    Status = cygrpc.Status
    AioChannel = cygrpc.AioChannel
    AioServer = cygrpc.AioServer
    AioCall = cygrpc.AioCall
    
    # Constants
    GRPC_STATUS_OK = cygrpc.GRPC_STATUS_OK
    GRPC_STATUS_CANCELLED = cygrpc.GRPC_STATUS_CANCELLED
    GRPC_STATUS_UNKNOWN = cygrpc.GRPC_STATUS_UNKNOWN
    GRPC_STATUS_INVALID_ARGUMENT = cygrpc.GRPC_STATUS_INVALID_ARGUMENT
    GRPC_STATUS_DEADLINE_EXCEEDED = cygrpc.GRPC_STATUS_DEADLINE_EXCEEDED
    GRPC_STATUS_NOT_FOUND = cygrpc.GRPC_STATUS_NOT_FOUND
    GRPC_STATUS_ALREADY_EXISTS = cygrpc.GRPC_STATUS_ALREADY_EXISTS
    GRPC_STATUS_PERMISSION_DENIED = cygrpc.GRPC_STATUS_PERMISSION_DENIED
    GRPC_STATUS_UNAUTHENTICATED = cygrpc.GRPC_STATUS_UNAUTHENTICATED
    GRPC_STATUS_RESOURCE_EXHAUSTED = cygrpc.GRPC_STATUS_RESOURCE_EXHAUSTED
    GRPC_STATUS_FAILED_PRECONDITION = cygrpc.GRPC_STATUS_FAILED_PRECONDITION
    GRPC_STATUS_ABORTED = cygrpc.GRPC_STATUS_ABORTED
    GRPC_STATUS_OUT_OF_RANGE = cygrpc.GRPC_STATUS_OUT_OF_RANGE
    GRPC_STATUS_UNIMPLEMENTED = cygrpc.GRPC_STATUS_UNIMPLEMENTED
    GRPC_STATUS_INTERNAL = cygrpc.GRPC_STATUS_INTERNAL
    GRPC_STATUS_UNAVAILABLE = cygrpc.GRPC_STATUS_UNAVAILABLE
    GRPC_STATUS_DATA_LOSS = cygrpc.GRPC_STATUS_DATA_LOSS

__all__ = [
    'Channel',
    'Server',
    'Call',
    'CompletionQueue',
    'CallCredentials',
    'ChannelCredentials',
    'Metadata',
    'Status',
    'AioChannel',
    'AioServer',
    'AioCall',
    'GRPC_STATUS_OK',
    'GRPC_STATUS_CANCELLED',
    'GRPC_STATUS_UNKNOWN',
    'GRPC_STATUS_INVALID_ARGUMENT',
    'GRPC_STATUS_DEADLINE_EXCEEDED',
    'GRPC_STATUS_NOT_FOUND',
    'GRPC_STATUS_ALREADY_EXISTS',
    'GRPC_STATUS_PERMISSION_DENIED',
    'GRPC_STATUS_UNAUTHENTICATED',
    'GRPC_STATUS_RESOURCE_EXHAUSTED',
    'GRPC_STATUS_FAILED_PRECONDITION',
    'GRPC_STATUS_ABORTED',
    'GRPC_STATUS_OUT_OF_RANGE',
    'GRPC_STATUS_UNIMPLEMENTED',
    'GRPC_STATUS_INTERNAL',
    'GRPC_STATUS_UNAVAILABLE',
    'GRPC_STATUS_DATA_LOSS',
] 