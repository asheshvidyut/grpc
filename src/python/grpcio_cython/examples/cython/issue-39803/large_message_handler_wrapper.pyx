# Automatically generated JIT marshalling wrapper by grpcio_cython
# distutils: language = c++

from libc.stdlib cimport malloc, free
from libc.stdint cimport uint32_t, uint64_t
from libcpp cimport bool
from libcpp.string cimport string

cdef cppclass LargeMessageService
cdef LargeMessageService* _global_servicer = NULL

cdef extern from "google/protobuf/repeated_field.h" namespace "google::protobuf":
    cdef cppclass RepeatedField[T]:
        const T* data() nogil
        T* mutable_data() nogil
        void Resize(int new_size, T value) nogil

cdef extern from "large_message.pb.h" namespace "large_message":
    cdef cppclass LargeMessageRequest:
        LargeMessageRequest()
        int values_size() nogil
        float values(int index) nogil
        void add_values(float value) nogil
        const RepeatedField[float]& values() nogil
        RepeatedField[float]* mutable_values() nogil
    cdef cppclass LargeMessageResponse:
        LargeMessageResponse()
        const string& status() nogil
        void set_status(const string& value) nogil

cdef extern from "large_message.pb.h":
    cdef cppclass _Wrapper_LargeMessageRequest "large_message::LargeMessageRequest":
        _Wrapper_LargeMessageRequest()
        bool ParseFromArray(const void* data, int size) nogil

    cdef cppclass _Wrapper_LargeMessageResponse "large_message::LargeMessageResponse":
        _Wrapper_LargeMessageResponse()
        bool SerializeToArray(void* data, int size) nogil
        int ByteSizeLong() nogil

cdef extern from "grpcio_cython/handler.h":
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

include "large_message_handler.pyx"

cdef extern from *:
    """
    #ifdef __cplusplus
    extern "C" {
    #endif
    
    uint32_t grpcio_cython_abi_version(void) {
        return 3;
    }

    static int __pyx_f_29large_message_handler_wrapper_process_large_message_wrapper(grpc_native_unary_call*);
    
    int native_process_large_message(grpc_native_unary_call* call) {
        return __pyx_f_29large_message_handler_wrapper_process_large_message_wrapper(call);
    }

    #ifdef __cplusplus
    }
    #endif
    """
    pass

cdef int process_large_message_wrapper(grpc_native_unary_call* call) nogil:
    cdef _Wrapper_LargeMessageRequest req
    if not req.ParseFromArray(call.req_data, call.req_len):
        call.status = <grpc_native_status>3 # INVALID_ARGUMENT
        return 0
        
    cdef _Wrapper_LargeMessageResponse resp
    cdef int rc = _global_servicer.process_large_message(<LargeMessageRequest*>&req, <LargeMessageResponse*>&resp)
    
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
        _global_servicer = new LargeMessageService()
    return 0

cdef extern from *:
    """
    #ifdef __cplusplus
    extern "C" {
    #endif
    
    static int __pyx_f_29large_message_handler_wrapper__cython_init(void);
    
    void grpcio_cython_init(void) {
        __pyx_f_29large_message_handler_wrapper__cython_init();
    }
    
    #ifdef __cplusplus
    }
    #endif
    """
    void grpcio_cython_init()
