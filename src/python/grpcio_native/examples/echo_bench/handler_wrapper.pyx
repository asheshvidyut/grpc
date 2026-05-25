# Automatically generated JIT marshalling wrapper by grpcio_native
# distutils: language = c++

from libc.stdlib cimport malloc, free
from libc.stdint cimport uint32_t, uint64_t
from libcpp cimport bool
from libcpp.string cimport string

cdef cppclass EchoService
cdef EchoService* _global_servicer = NULL

cdef extern from "google/protobuf/repeated_field.h" namespace "google::protobuf":
    cdef cppclass RepeatedField[T]:
        const T* data() nogil
        T* mutable_data() nogil
        void Resize(int new_size, T value) nogil

cdef extern from "echo.pb.h" namespace "echo":
    cdef cppclass EchoRequest:
        EchoRequest()
        const string& message() nogil
        void set_message(const string& value) nogil
    cdef cppclass EchoResponse:
        EchoResponse()
        const string& message() nogil
        void set_message(const string& value) nogil

cdef extern from "echo.pb.h":
    cdef cppclass _Wrapper_EchoRequest "echo::EchoRequest":
        _Wrapper_EchoRequest()
        bool ParseFromArray(const void* data, int size) nogil

    cdef cppclass _Wrapper_EchoResponse "echo::EchoResponse":
        _Wrapper_EchoResponse()
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

    static int __pyx_f_15handler_wrapper_cython_echo_wrapper(grpc_native_unary_call*);
    
    int native_cython_echo(grpc_native_unary_call* call) {
        return __pyx_f_15handler_wrapper_cython_echo_wrapper(call);
    }

    #ifdef __cplusplus
    }
    #endif
    """
    pass

cdef int cython_echo_wrapper(grpc_native_unary_call* call) nogil:
    cdef _Wrapper_EchoRequest req
    if not req.ParseFromArray(call.req_data, call.req_len):
        call.status = <grpc_native_status>3 # INVALID_ARGUMENT
        return 0
        
    cdef _Wrapper_EchoResponse resp
    cdef int rc = _global_servicer.cython_echo(<EchoRequest*>&req, <EchoResponse*>&resp)
    
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
        _global_servicer = new EchoService()
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
