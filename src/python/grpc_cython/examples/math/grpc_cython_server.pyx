# distutils: language = c++

from math_cython_pb2 cimport MathServiceBase, MathRequest, MathResponse
from libc.stdlib cimport malloc

cdef class FastMathService(MathServiceBase):
    cdef int ComputeMatrix(self, MathRequest* req, MathResponse* resp) nogil:
        # === ZERO GIL BUSINESS LOGIC ===
        
        # 1. Get raw C-pointers to the incoming Protobuf data
        cdef float* a_ptr = req.mutable_matrix_a()
        cdef float* b_ptr = req.mutable_matrix_b()
        cdef int size = req.matrix_a_size()
        
        # 2. Get raw C-pointer to the outgoing Protobuf data
        resp.resize_result_matrix(size, 0.0)
        cdef float* out_ptr = resp.mutable_result_matrix()
        
        # 3. Perform compute-heavy math directly in C (e.g. SIMD vector multiplication)
        cdef int i
        for i in range(size):
            out_ptr[i] = a_ptr[i] * b_ptr[i]
            
        return 0 # 0 = OK status
