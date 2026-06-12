# distutils: language = c++
import grpc
import grpc_cython
from libc.stdlib cimport malloc, free

# Import C++ Headers from the PXD
from math_cython_pb2 cimport MathServiceBase

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
