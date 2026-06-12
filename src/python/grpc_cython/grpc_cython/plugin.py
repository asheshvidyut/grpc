#!/usr/bin/env python3
import sys
from google.protobuf.compiler import plugin_pb2 as plugin

def generate_pxd_content(proto_file, service):
    """Generates the C++ bindings and Server Base interface."""
    content = [
        f"# distutils: language = c++\n",
        f"from libc.stddef cimport size_t\n",
        f'cdef extern from "{proto_file.name.replace(".proto", ".pb.h")}" namespace "{proto_file.package}":'
    ]
    
    # 1. Map all messages used in the service
    message_dict = {m.name: m for m in proto_file.message_type}
    messages_seen = set()
    for method in service.method:
        for msg in (method.input_type, method.output_type):
            msg_name = msg.split('.')[-1]
            if msg_name not in messages_seen:
                messages_seen.add(msg_name)
                content.append(f"    cdef cppclass {msg_name}:")
                content.append(f'        {msg_name}() nogil')
                
                # Dynamically generate field accessors
                if msg_name in message_dict:
                    msg_desc = message_dict[msg_name]
                    for field in msg_desc.field:
                        # 3 == LABEL_REPEATED
                        if field.label == 3:
                            # Map Protobuf field types to C types (1=double, 2=float, 3=int64, 4=uint64, 5=int32, etc.)
                            c_type = "float"
                            if field.type == 1: c_type = "double"
                            elif field.type == 2: c_type = "float"
                            elif field.type == 5: c_type = "int"
                            elif field.type == 3: c_type = "long"
                            
                            content.append(f'        {c_type}* mutable_{field.name} "mutable_{field.name}()->mutable_data"() nogil')
                            content.append(f'        int {field.name}_size() nogil')
                            content.append(f'        void resize_{field.name} "mutable_{field.name}()->Resize"(int, {c_type}) nogil')
                            content.append(f'        void add_{field.name}({c_type}) nogil')
                        else:
                            # Singular fields (stub implementation)
                            c_type = "float"
                            if field.type == 1: c_type = "double"
                            elif field.type == 2: c_type = "float"
                            elif field.type == 5: c_type = "int"
                            content.append(f'        {c_type} {field.name}() nogil')
                            content.append(f'        void set_{field.name}({c_type} value) nogil')

                content.append(f'        size_t ByteSizeLong() nogil')
                content.append(f'        bint SerializeToArray(void* data, int size) nogil')
                content.append(f'        bint ParseFromArray(const void* data, int size) nogil\n')

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
        f"import grpc_cython",
        f"from libc.stdlib cimport malloc, free",
        f"from libc.stdint cimport uintptr_t\n",
    ]
    
    # Append the struct ABI
    content.append("""
ctypedef struct grpc_native_client_call:
    const char* method
    const char* req_data
    size_t req_len
    char* resp_data
    size_t resp_len
    int status
ctypedef int (*grpcio_cython_invoke_fn)(void* c_channel, grpc_native_client_call* call, int timeout) nogil
""")

    # 2. Provide a dummy implementation for the Base Class
    content.append(f"cdef class {service.name}Base:")
    for method in service.method:
        in_type = method.input_type.split('.')[-1]
        out_type = method.output_type.split('.')[-1]
        content.append(f"    cdef int {method.name}(self, {in_type}* req, {out_type}* resp) nogil:")
        content.append(f"        pass\n")
        
        content.append(f"    def _native_Dispatch_{method.name}(self, bytes req_bytes, object context):")
        content.append(f"        cdef {in_type} req")
        content.append(f"        cdef {out_type} resp")
        content.append(f"        cdef const char* req_data = req_bytes")
        content.append(f"        req.ParseFromArray(req_data, len(req_bytes))")
        content.append(f"        cdef int rc")
        content.append(f"        with nogil:")
        content.append(f"            rc = self.{method.name}(&req, &resp)")
        content.append(f"        cdef int size = resp.ByteSizeLong()")
        content.append(f"        cdef char* out_buf = <char*>malloc(size)")
        content.append(f"        resp.SerializeToArray(out_buf, size)")
        content.append(f"        cdef bytes out_bytes = out_buf[:size]")
        content.append(f"        free(out_buf)")
        content.append(f"        return out_bytes\n")

    # Generate the Client Stub
    content.append(f"cdef class {service.name}FastStub:")
    content.append("    cdef object channel")
    content.append("    cdef void* c_chan")
    content.append("    cdef grpcio_cython_invoke_fn invoke_fn\n")
    content.append("    def __init__(self, channel):")
    content.append("        self.channel = channel")
    content.append("        self.c_chan = <void*>channel._channel")
    content.append("        self.invoke_fn = <grpcio_cython_invoke_fn><uintptr_t>grpc_cython.get_c_core_invoke_fn_addr()\n")
    
    for method in service.method:
        # Generate the Python-facing method wrapper
        # In a full implementation, we'd introspect the Protobuf descriptor 
        # to generate memoryview mappings, but we use kwargs for the PoC.
        content.append(f"    def {method.name}(self, **kwargs):")
        content.append(f"        cdef {in_type} req")
        content.append(f"        cdef {out_type} resp")
        
        # Dynamically map kwargs to the C++ Protobuf request
        in_message = next(m for m in proto_file.message_type if m.name == in_type)
        for field in in_message.field:
            if field.label == 3: # LABEL_REPEATED
                content.append(f"        if '{field.name}' in kwargs:")
                content.append(f"            for item in kwargs['{field.name}']:")
                content.append(f"                req.add_{field.name}(item)")
            else:
                content.append(f"        if '{field.name}' in kwargs:")
                content.append(f"            req.set_{field.name}(kwargs['{field.name}'])")

        content.append(f"        cdef size_t size = req.ByteSizeLong()")
        content.append(f"        cdef char* buf = <char*>malloc(size)")
        content.append(f"        req.SerializeToArray(buf, size)")
        content.append(f"        cdef bytes req_bytes = buf[:size]")
        content.append(f"        free(buf)")
        content.append(f"        cdef object call = self.channel.unary_unary(")
        content.append(f"            '/{proto_file.package}.{service.name}/{method.name}',")
        content.append(f"            request_serializer=None, response_deserializer=None")
        content.append(f"        )")
        content.append(f"        cdef bytes res_bytes = call(req_bytes)")
        content.append(f"        return res_bytes\n")

    content.append(f"def add_{service.name}Servicer_to_server(servicer, server):")
    content.append(f"    rpc_method_handlers = {{")
    for method in service.method:
        content.append(f"        '{method.name}': grpc_cython.native_unary_unary_rpc_method_handler(")
        content.append(f"            servicer_instance=servicer,")
        content.append(f"            method_name='{method.name}'")
        content.append(f"        ),")
    content.append(f"    }}")
    content.append(f"    generic_handler = grpc.method_handlers_generic_handler(")
    content.append(f"        '{proto_file.package}.{service.name}', rpc_method_handlers")
    content.append(f"    )")
    content.append(f"    server.add_generic_rpc_handlers((generic_handler,))")
    content.append(f"")

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
