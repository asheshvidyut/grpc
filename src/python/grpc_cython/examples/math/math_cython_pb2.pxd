# distutils: language = c++

cdef extern from "math.pb.h" namespace "mypackage":
    cdef cppclass MathRequest:
        MathRequest()
        float* mutable_matrix_a()
        int matrix_a_size()
        float* mutable_matrix_b()
        int matrix_b_size()
        float* mutable_result_matrix()
        int result_matrix_size()
        size_t ByteSizeLong()
        bint SerializeToArray(void* data, int size)
        bint ParseFromArray(const void* data, int size)

    cdef cppclass MathResponse:
        MathResponse()
        float* mutable_matrix_a()
        int matrix_a_size()
        float* mutable_matrix_b()
        int matrix_b_size()
        float* mutable_result_matrix()
        int result_matrix_size()
        size_t ByteSizeLong()
        bint SerializeToArray(void* data, int size)
        bint ParseFromArray(const void* data, int size)

cdef class MathServiceBase:
    cdef int ComputeMatrix(self, MathRequest* req, MathResponse* resp) nogil