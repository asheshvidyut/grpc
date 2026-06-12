import grpc

def native_unary_unary_rpc_method_handler(servicer_instance, method_name):
    """
    Creates a gRPC method handler that completely bypasses Python Protobuf deserialization.
    
    This handler instructs the core gRPC C-Extension to pass raw network wire bytes 
    directly to the Cython servicer. The generated Cython class will expose a native 
    dispatcher (e.g. `_native_Dispatch_ComputeMatrix`) which uses the C++ Protobuf 
    arena to parse the bytes without allocating a single Python object or holding the GIL.
    """
    # The protoc cython plugin generates a _native_Dispatch_* method on the servicer
    # that handles raw bytes directly in C++.
    dispatch_fn = getattr(servicer_instance, f"_native_Dispatch_{method_name}", None)
    
    if not dispatch_fn:
        # Fallback to the standard python method if no native dispatcher is found
        dispatch_fn = getattr(servicer_instance, method_name)

    return grpc.unary_unary_rpc_method_handler(
        behavior=dispatch_fn,
        request_deserializer=None,
        response_serializer=None,
    )
