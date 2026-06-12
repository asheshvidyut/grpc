from ._handler import native_unary_unary_rpc_method_handler

def get_c_core_invoke_fn_addr():
    # Placeholder for the raw C-Core cygrpc pointer retrieval
    import grpc._cython.cygrpc as cygrpc
    # In a full implementation, cygrpc would expose an API returning the memory address of the core execution function
    return 0

__all__ = ["native_unary_unary_rpc_method_handler", "get_c_core_invoke_fn_addr"]