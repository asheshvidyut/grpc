# distutils: language = c++

from libc.stddef cimport size_t

cdef extern from "math.pb.h" namespace "mypackage":
    cdef cppclass MathRequest:
        MathRequest() nogil
        float* mutable_matrix_a "mutable_matrix_a()->mutable_data"() nogil
        int matrix_a_size() nogil
        void resize_matrix_a "mutable_matrix_a()->Resize"(int, float) nogil
        void add_matrix_a(float) nogil
        float* mutable_matrix_b "mutable_matrix_b()->mutable_data"() nogil
        int matrix_b_size() nogil
        void resize_matrix_b "mutable_matrix_b()->Resize"(int, float) nogil
        void add_matrix_b(float) nogil
        size_t ByteSizeLong() nogil
        bint SerializeToArray(void* data, int size) nogil
        bint ParseFromArray(const void* data, int size) nogil

    cdef cppclass MathResponse:
        MathResponse() nogil
        float* mutable_result_matrix "mutable_result_matrix()->mutable_data"() nogil
        int result_matrix_size() nogil
        void resize_result_matrix "mutable_result_matrix()->Resize"(int, float) nogil
        void add_result_matrix(float) nogil
        size_t ByteSizeLong() nogil
        bint SerializeToArray(void* data, int size) nogil
        bint ParseFromArray(const void* data, int size) nogil

cdef class MathServiceBase:
    cdef int ComputeMatrix(self, MathRequest* req, MathResponse* resp) nogil