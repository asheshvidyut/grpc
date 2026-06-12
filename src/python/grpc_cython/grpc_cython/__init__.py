from ._handler import native_unary_unary_rpc_method_handler

def get_c_core_invoke_fn_addr() -> int:
    try:
        from grpc._cython import cygrpc
        return cygrpc.get_c_core_invoke_fn_addr()
    except ImportError as e:
        raise RuntimeError("grpcio compiled C-extensions not loaded") from e

__all__ = ["native_unary_unary_rpc_method_handler", "get_c_core_invoke_fn_addr"]