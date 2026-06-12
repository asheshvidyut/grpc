# distutils: language = c++
import grpc
import grpc_cython
from libc.stdlib cimport malloc, free
from libc.stdint cimport uintptr_t


ctypedef struct grpc_native_client_call:
    const char* method
    const char* req_data
    size_t req_len
    char* resp_data
    size_t resp_len
    int status
ctypedef int (*grpcio_cython_invoke_fn)(void* c_channel, grpc_native_client_call* call, int timeout) nogil

cdef class MathServiceBase:
    cdef int ComputeMatrix(self, MathRequest* req, MathResponse* resp) nogil:
        pass

    def _native_Dispatch_ComputeMatrix(self, bytes req_bytes, object context):
        cdef MathRequest req
        cdef MathResponse resp
        cdef const char* req_data = req_bytes
        req.ParseFromArray(req_data, len(req_bytes))
        cdef int rc
        with nogil:
            rc = self.ComputeMatrix(&req, &resp)
        cdef int size = resp.ByteSizeLong()
        cdef char* out_buf = <char*>malloc(size)
        resp.SerializeToArray(out_buf, size)
        cdef bytes out_bytes = out_buf[:size]
        free(out_buf)
        return out_bytes

cdef class MathServiceFastStub:
    cdef object channel
    cdef void* c_chan
    cdef grpcio_cython_invoke_fn invoke_fn

    def __init__(self, channel):
        self.channel = channel
        self.c_chan = <void*>channel._channel
        self.invoke_fn = <grpcio_cython_invoke_fn><uintptr_t>grpc_cython.get_c_core_invoke_fn_addr()

    def ComputeMatrix(self, **kwargs):
        cdef MathRequest req
        cdef MathResponse resp
        if 'matrix_a' in kwargs:
            for item in kwargs['matrix_a']:
                req.add_matrix_a(item)
        if 'matrix_b' in kwargs:
            for item in kwargs['matrix_b']:
                req.add_matrix_b(item)
        cdef size_t size = req.ByteSizeLong()
        cdef char* buf = <char*>malloc(size)
        req.SerializeToArray(buf, size)
        cdef bytes req_bytes = buf[:size]
        free(buf)
        cdef object call = self.channel.unary_unary(
            '/mypackage.MathService/ComputeMatrix',
            request_serializer=None, response_deserializer=None
        )
        cdef bytes res_bytes = call(req_bytes)
        return res_bytes

def add_MathServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
        'ComputeMatrix': grpc_cython.native_unary_unary_rpc_method_handler(
            servicer_instance=servicer,
            method_name='ComputeMatrix'
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        'mypackage.MathService', rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
