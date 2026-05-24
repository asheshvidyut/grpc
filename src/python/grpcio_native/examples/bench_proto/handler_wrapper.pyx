# Automatically generated JIT marshalling wrapper by grpcio_native
# distutils: language = c++

from libc.stdlib cimport malloc, free
from libc.stdint cimport uint32_t
from libcpp cimport bool
from libcpp.string cimport string

cdef cppclass BenchService
cdef BenchService* _global_servicer = NULL

cdef extern from "google/protobuf/repeated_field.h" namespace "google::protobuf":
    cdef cppclass RepeatedField[T]:
        const T* data() nogil
        T* mutable_data() nogil
        void Resize(int new_size, T value) nogil

cdef extern from "bench.pb.h" namespace "bench":
    cdef cppclass HashRequest:
        HashRequest()
        bytes data() nogil
        void set_data(bytes value) nogil
        uint32 iterations() nogil
        void set_iterations(uint32 value) nogil
    cdef cppclass HashResponse:
        HashResponse()
        uint64 hash() nogil
        void set_hash(uint64 value) nogil
    cdef cppclass MatMulRequest:
        MatMulRequest()
        uint32 n() nogil
        void set_n(uint32 value) nogil
        int a_size() nogil
        float a(int index) nogil
        void add_a(float value) nogil
        const RepeatedField[float]& a() nogil
        RepeatedField[float]* mutable_a() nogil
        int b_size() nogil
        float b(int index) nogil
        void add_b(float value) nogil
        const RepeatedField[float]& b() nogil
        RepeatedField[float]* mutable_b() nogil
    cdef cppclass MatMulResponse:
        MatMulResponse()
        int c_size() nogil
        float c(int index) nogil
        void add_c(float value) nogil
        const RepeatedField[float]& c() nogil
        RepeatedField[float]* mutable_c() nogil

cdef extern from "bench.pb.h":
    cdef cppclass _Wrapper_HashRequest "bench::HashRequest":
        _Wrapper_HashRequest()
        bool ParseFromArray(const void* data, int size) nogil

    cdef cppclass _Wrapper_HashResponse "bench::HashResponse":
        _Wrapper_HashResponse()
        bool SerializeToArray(void* data, int size) nogil
        int ByteSizeLong() nogil

cdef extern from "bench.pb.h":
    cdef cppclass _Wrapper_MatMulRequest "bench::MatMulRequest":
        _Wrapper_MatMulRequest()
        bool ParseFromArray(const void* data, int size) nogil

    cdef cppclass _Wrapper_MatMulResponse "bench::MatMulResponse":
        _Wrapper_MatMulResponse()
        bool SerializeToArray(void* data, int size) nogil
        int ByteSizeLong() nogil

cdef extern from "grpcio_native/handler.h":
    ctypedef enum grpc_native_status:
        pass

    ctypedef struct grpc_native_unary_call:
        void* context
        const char* req_data
        size_t req_len
        char* resp_data
        size_t resp_len
        grpc_native_status status
        char* err_msg
        size_t err_msg_len

include "handler.pyx"

cdef extern from *:
    """
    #ifdef __cplusplus
    extern "C" {
    #endif
    
    uint32_t grpcio_native_abi_version(void) {
        return 3;
    }

    static int __pyx_f_15handler_wrapper_cython_hash_wrapper(grpc_native_unary_call*);
    
    int native_cython_hash(grpc_native_unary_call* call) {
        return __pyx_f_15handler_wrapper_cython_hash_wrapper(call);
    }

    static int __pyx_f_15handler_wrapper_cython_matmul_wrapper(grpc_native_unary_call*);
    
    int native_cython_matmul(grpc_native_unary_call* call) {
        return __pyx_f_15handler_wrapper_cython_matmul_wrapper(call);
    }

    #ifdef __cplusplus
    }
    #endif
    """
    pass

cdef int cython_hash_wrapper(grpc_native_unary_call* call) nogil:
    cdef _Wrapper_HashRequest req
    if not req.ParseFromArray(call.req_data, call.req_len):
        call.status = <grpc_native_status>3 # INVALID_ARGUMENT
        return 0
        
    cdef _Wrapper_HashResponse resp
    cdef int rc = _global_servicer.cython_hash(<HashRequest*>&req, <HashResponse*>&resp)
    
    cdef int resp_size = resp.ByteSizeLong()
    call.resp_data = <char*>malloc(resp_size)
    if call.resp_data != NULL:
        resp.SerializeToArray(call.resp_data, resp_size)
        call.resp_len = resp_size
        
    call.status = <grpc_native_status>rc # OK
    return 0

cdef int cython_matmul_wrapper(grpc_native_unary_call* call) nogil:
    cdef _Wrapper_MatMulRequest req
    if not req.ParseFromArray(call.req_data, call.req_len):
        call.status = <grpc_native_status>3 # INVALID_ARGUMENT
        return 0
        
    cdef _Wrapper_MatMulResponse resp
    cdef int rc = _global_servicer.cython_matmul(<MatMulRequest*>&req, <MatMulResponse*>&resp)
    
    cdef int resp_size = resp.ByteSizeLong()
    call.resp_data = <char*>malloc(resp_size)
    if call.resp_data != NULL:
        resp.SerializeToArray(call.resp_data, resp_size)
        call.resp_len = resp_size
        
    call.status = <grpc_native_status>rc # OK
    return 0

cdef int _cython_init() nogil:
    global _global_servicer
    if _global_servicer == NULL:
        _global_servicer = new BenchService()
    return 0

cdef extern from *:
    """
    #ifdef __cplusplus
    extern "C" {
    #endif
    
    static int __pyx_f_15handler_wrapper__cython_init(void);
    
    void grpcio_native_init(void) {
        __pyx_f_15handler_wrapper__cython_init();
    }
    
    #ifdef __cplusplus
    }
    #endif
    """
    void grpcio_native_init()
