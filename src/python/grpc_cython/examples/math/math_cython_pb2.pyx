# distutils: language = c++
import grpc
import grpc_cython
from libc.stdlib cimport malloc, free

cdef class MathServiceBase:
    # Python entry point for the custom gRPC handler (called with raw bytes)
    def _native_Dispatch_ComputeMatrix(self, bytes request_bytes, context):
        # TODO: C++ Protobuf ParseFromArray(request_bytes) -> MathRequest
        # rc = self.ComputeMatrix(&req, &resp)
        # TODO: C++ Protobuf SerializeToArray(&resp) -> bytes
        return b"" # Returns raw serialized bytes to gRPC
        
    cdef int ComputeMatrix(self, MathRequest* req, MathResponse* resp) nogil:
        pass

cdef extern from "grpcio_native/handler.h":
    ctypedef struct grpc_native_client_call:
        const char* method
        const char* req_data
        size_t req_len
        char* resp_data
        size_t resp_len
        int status
    ctypedef int (*grpcio_cython_invoke_fn)(void* c_channel, grpc_native_client_call* call, int timeout) nogil

cdef class MathServiceFastStub:
    cdef void* c_chan
    cdef grpcio_cython_invoke_fn invoke_fn

    def __init__(self, channel):
        self.c_chan = <void*>channel._channel
        self.invoke_fn = <grpcio_cython_invoke_fn>grpc_cython.get_c_core_invoke_fn_addr()

    def ComputeMatrix(self, **kwargs):
        cdef grpc_native_client_call call
        call.method = b"/mypackage.MathService/ComputeMatrix"
        # TODO: Auto-Serialization of kwargs into C++ Protobuf happens here
        cdef int rc
        with nogil:
            rc = self.invoke_fn(self.c_chan, &call, 5000)
        if rc != 0: raise RuntimeError('RPC Failed')
        # TODO: Auto-Deserialization of call.resp_data happens here
        return dict()  # Return the unwrapped output

def add_MathServiceServicer_to_server(servicer, server):
    # This automatically bypasses Python protobuf deserialization
    # and routes raw C-Core bytes directly to your Cython FastMathService
    rpc_method_handlers = {
        "ComputeMatrix": grpc_cython.native_unary_unary_rpc_method_handler(
            servicer_instance=servicer,
            method_name="ComputeMatrix"
        )
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "mypackage.MathService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
