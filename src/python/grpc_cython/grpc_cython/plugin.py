#!/usr/bin/env python3
import sys
from google.protobuf.compiler import plugin_pb2 as plugin

def generate_pxd_content(proto_file, service):
    """Generates the C++ bindings and Server Base interface."""
    content = [
        f"# distutils: language = c++\n",
        f'cdef extern from "{proto_file.name.replace(".proto", ".pb.h")}" namespace "{proto_file.package}":'
    ]
    
    # 1. Map all messages used in the service
    messages_seen = set()
    for method in service.method:
        for msg in (method.input_type, method.output_type):
            msg_name = msg.split('.')[-1]
            if msg_name not in messages_seen:
                messages_seen.add(msg_name)
                content.append(f"    cdef cppclass {msg_name}:")
                content.append(f"        {msg_name}()")
                content.append(f"        size_t ByteSizeLong()")
                content.append(f"        bint SerializeToArray(void* data, int size)")
                content.append(f"        bint ParseFromArray(const void* data, int size)\n")

    # 2. Generate the Server Base Class definition
    content.append(f"cdef class {service.name}Base:")
    for method in service.method:
        in_type = method.input_type.split('.')[-1]
        out_type = method.output_type.split('.')[-1]
        content.append(f"    cdef int {method.name}(self, {in_type}* req, {out_type}* resp) nogil")
        
    return "\n".join(content)

def generate_pyx_content(proto_file, service):
    """Generates the hidden ABI struct wiring and the Client Fast Stub."""
    content = [
        f"# distutils: language = c++",
        f"import grpc",
        f"import grpcio_cython",
        f"from libc.stdlib cimport malloc, free\n",
        f"# Import C++ Headers from the PXD",
        f"from {proto_file.name.replace('.proto', '_cython_pb2')} cimport {service.name}Base"
    ]
    
    # Append the struct ABI
    content.append("""
cdef extern from "grpcio_native/handler.h":
    ctypedef struct grpc_native_client_call:
        const char* method
        const char* req_data
        size_t req_len
        char* resp_data
        size_t resp_len
        int status
    ctypedef int (*grpcio_cython_invoke_fn)(void* c_channel, grpc_native_client_call* call, int timeout) nogil
""")

    # Generate the Client Stub
    content.append(f"cdef class {service.name}FastStub:")
    content.append("    cdef void* c_chan")
    content.append("    cdef grpcio_cython_invoke_fn invoke_fn\n")
    content.append("    def __init__(self, channel):")
    content.append("        self.c_chan = <void*>channel._channel")
    content.append("        self.invoke_fn = <grpcio_cython_invoke_fn>grpcio_cython.get_c_core_invoke_fn_addr()\n")
    
    for method in service.method:
        # Generate the Python-facing method wrapper
        # In a full implementation, we'd introspect the Protobuf descriptor 
        # to generate memoryview mappings, but we use kwargs for the PoC.
        content.append(f"    def {method.name}(self, **kwargs):")
        content.append(f"        cdef grpc_native_client_call call")
        content.append(f'        call.method = b"/{proto_file.package}.{service.name}/{method.name}"')
        content.append(f"        # TODO: Auto-Serialization of kwargs into C++ Protobuf happens here")
        content.append(f"        cdef int rc")
        content.append(f"        with nogil:")
        content.append(f"            rc = self.invoke_fn(self.c_chan, &call, 5000)")
        content.append(f"        if rc != 0: raise RuntimeError('RPC Failed')")
        content.append(f"        # TODO: Auto-Deserialization of call.resp_data happens here")
        content.append(f"        return dict()  # Return the unwrapped output\n")

    return "\n".join(content)

def main():
    # Protoc passes the CodeGeneratorRequest via stdin
    data = sys.stdin.buffer.read()
    request = plugin.CodeGeneratorRequest()
    request.ParseFromString(data)

    response = plugin.CodeGeneratorResponse()

    for proto_file in request.proto_file:
        # Only generate for files explicitly passed to protoc
        if proto_file.name not in request.file_to_generate:
            continue
            
        for service in proto_file.service:
            # 1. Output the .pxd definitions
            f_pxd = response.file.add()
            f_pxd.name = proto_file.name.replace(".proto", "_cython_pb2.pxd")
            f_pxd.content = generate_pxd_content(proto_file, service)
            
            # 2. Output the .pyx implementation
            f_pyx = response.file.add()
            f_pyx.name = proto_file.name.replace(".proto", "_cython_pb2.pyx")
            f_pyx.content = generate_pyx_content(proto_file, service)

    # Protoc expects the CodeGeneratorResponse via stdout
    sys.stdout.buffer.write(response.SerializeToString())

if __name__ == '__main__':
    main()
