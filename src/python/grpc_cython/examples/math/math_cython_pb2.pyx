# distutils: language = c++
import grpc
import grpc_cython
from libc.stdlib cimport malloc, free

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
