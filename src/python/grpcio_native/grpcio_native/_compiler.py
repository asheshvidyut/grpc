# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# High-level JIT compiler automation for grpcio_native.
# Automatically compiles and loads C++, Cython, and Rust handlers directly
# from Python code, eliminating manual build steps.

import os
import subprocess
import shutil
import sys
import logging
from typing import List, Sequence

from ._handler import NativeModule, load_native_module

_LOGGER = logging.getLogger(__name__)


class CompilationError(RuntimeError):
    """Raised when automatic compilation of a native handler fails."""








def compile_and_load_cython(
    pyx_file: str,
    output_dir: str = ".",
    lib_name: str = None,
    request_type: str = None,
    response_type: str = None,
    handler_fn: str = None,
    proto_header: str = None,
    class_name: str = None
) -> NativeModule:
    """Automatically compiles a Cython (.pyx) handler file and loads the resulting module.
    
    Supports optional auto-wrapper generation to abstract C++ Protobuf marshalling.
    """
    pyx_path = os.path.abspath(pyx_file)
    if not os.path.isfile(pyx_path):
        raise FileNotFoundError(f"Cython file not found: {pyx_path}")

    if lib_name is None:
        lib_name = os.path.splitext(os.path.basename(pyx_path))[0]

    is_wrapper = False
    original_pyx_path = pyx_path

    # 1. Auto-wire JIT compile parameters dynamically from the Cython class name if provided
    if class_name and request_type is None:
        methods_info = parse_servicer_methods(pyx_path, class_name)
        if methods_info:
            # Auto-resolve the .proto schema inside JIT directory
            import re
            dir_name = os.path.dirname(pyx_path)
            proto_name = None
            proto_files = [f for f in os.listdir(dir_name) if f.endswith(".proto")]
            if len(proto_files) == 1:
                proto_name = proto_files[0]
            else:
                proto_name = "large_message.proto"
                
            proto_path = os.path.join(dir_name, proto_name)
            
            # Extract the protobuf package namespace name dynamically
            ns = None
            try:
                with open(proto_path, "r") as f:
                    for line in f:
                        m = re.match(r"package\s+([\w.]+)", line.strip())
                        if m:
                            ns = m.group(1).replace(".", "::")
                            break
            except Exception:
                pass
            if ns is None:
                ns = "large_message"
                
            request_type = [f"{ns}::{req}" for _, req, _ in methods_info]
            response_type = [f"{ns}::{resp}" for _, _, resp in methods_info]
            handler_fn = [fn for fn, _, _ in methods_info]
            if proto_header is None:
                proto_header = proto_name.replace(".proto", ".pb.h")

    if request_type and response_type and handler_fn:
        # Automatically extract the Protobuf C++ header filename from the developer's pyx source file
        if proto_header is None:
            import re
            try:
                with open(pyx_path, "r") as f:
                    match = re.search(r'cdef\s+extern\s+from\s+["\']([^"\']+\.pb\.h)["\']', f.read())
                    if match:
                        proto_header = match.group(1)
            except Exception:
                pass
                
        # If still not resolved, scan the JIT directory for any .proto files
        if proto_header is None:
            try:
                dir_name = os.path.dirname(pyx_path)
                proto_files = [f for f in os.listdir(dir_name) if f.endswith(".proto")]
                if len(proto_files) == 1:
                    proto_header = proto_files[0].replace(".proto", ".pb.h")
            except Exception:
                pass
        
        # If single values are passed, convert them to lists for unified loop processing
        req_types = [request_type] if isinstance(request_type, str) else list(request_type)
        resp_types = [response_type] if isinstance(response_type, str) else list(response_type)
        fn_names = [handler_fn] if isinstance(handler_fn, str) else list(handler_fn)
        header_name = proto_header if proto_header else "large_message.pb.h"

        is_wrapper = True
        wrapper_lib_name = f"{lib_name}_wrapper"
        wrapper_pyx_path = os.path.join(os.path.dirname(pyx_path), f"{wrapper_lib_name}.pyx")
        
        wrapper_content = f"""# Automatically generated JIT marshalling wrapper by grpcio_native
# distutils: language = c++

from libc.stdlib cimport malloc, free
from libc.stdint cimport uint32_t
from libcpp cimport bool
from libcpp.string cimport string
"""
        if class_name:
            wrapper_content += f"""
cdef cppclass {class_name}
cdef {class_name}* _global_servicer = NULL
"""
        # Resolve the absolute .proto file path dynamically to parse its fields
        proto_name = header_name.replace(".pb.h", ".proto")
        proto_path = os.path.join(os.path.dirname(pyx_path), proto_name)

        # 2. Dynamically generate and append the complete C++ Protobuf class declarations!
        if os.path.exists(proto_path):
            wrapper_content += generate_cppclass_declarations(proto_path, req_types, resp_types)

        # 3. Automatically declare the low-level aliased wrapper classes for memory marshalling
        for req_t, resp_t in zip(req_types, resp_types):
            req_base = req_t.split("::")[-1]
            resp_base = resp_t.split("::")[-1]
            wrapper_content += f"""
cdef extern from "{header_name}":
    cdef cppclass _Wrapper_{req_base} "{req_t}":
        _Wrapper_{req_base}()
        bool ParseFromArray(const void* data, int size) nogil

    cdef cppclass _Wrapper_{resp_base} "{resp_t}":
        _Wrapper_{resp_base}()
        bool SerializeToArray(void* data, int size) nogil
        int ByteSizeLong() nogil
"""

        # Expose standard struct declarations
        wrapper_content += """
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
"""

        # Include the developer's clean business logic file here to inherit all C++ class definitions first
        wrapper_content += f'\ninclude "{os.path.basename(original_pyx_path)}"\n'

        # Expose clean C linkages to prevent name mangling
        if class_name:
            wrapper_content += f"""
cdef extern from *:
    \"\"\"
    #ifdef __cplusplus
    extern "C" {{
    #endif
    
    uint32_t grpcio_native_abi_version(void) {{
        return 3;
    }}
"""
        else:
            wrapper_content += f"""
cdef extern from *:
    \"\"\"
    #ifdef __cplusplus
    extern "C" {{
    #endif
    
    uint32_t grpcio_native_abi_version(void) {{
        return 3;
    }}
"""

        for fn in fn_names:
            wrapper_content += f"""
    static int __pyx_f_{len(wrapper_lib_name)}{wrapper_lib_name}_{fn}_wrapper(grpc_native_unary_call*);
    
    int native_{fn}(grpc_native_unary_call* call) {{
        return __pyx_f_{len(wrapper_lib_name)}{wrapper_lib_name}_{fn}_wrapper(call);
    }}
"""
        wrapper_content += """
    #ifdef __cplusplus
    }
    #endif
    \"\"\"
    pass
"""
        # Generate marshalling wrapper implementations for each handler
        for req_t, resp_t, fn in zip(req_types, resp_types, fn_names):
            req_base = req_t.split("::")[-1]
            resp_base = resp_t.split("::")[-1]
            dispatch_call = f"_global_servicer.{fn}" if class_name else fn
            
            wrapper_content += f"""
cdef int {fn}_wrapper(grpc_native_unary_call* call) nogil:
    cdef _Wrapper_{req_base} req
    if not req.ParseFromArray(call.req_data, call.req_len):
        call.status = <grpc_native_status>3 # INVALID_ARGUMENT
        return 0
        
    cdef _Wrapper_{resp_base} resp
    cdef int rc = {dispatch_call}(<{req_base}*>&req, <{resp_base}*>&resp)
    
    cdef int resp_size = resp.ByteSizeLong()
    call.resp_data = <char*>malloc(resp_size)
    if call.resp_data != NULL:
        resp.SerializeToArray(call.resp_data, resp_size)
        call.resp_len = resp_size
        
    call.status = <grpc_native_status>rc # OK
    return 0
"""
        # Append dynamic C-linkage Cython initializer block at the bottom (fully completed class definitions scope!)
        if class_name:
            wrapper_content += f"""
cdef public void grpcio_native_init() nogil:
    global _global_servicer
    if _global_servicer == NULL:
        _global_servicer = new {class_name}()
"""

        with open(wrapper_pyx_path, "w") as f:
            f.write(wrapper_content)
            
        pyx_path = wrapper_pyx_path
        lib_name = wrapper_lib_name

    if not shutil.which("cython"):
        raise CompilationError("Cython compiler is not installed or not found in PATH")

    package_dir = os.path.dirname(os.path.abspath(__file__))
    native_include_dir = os.path.abspath(os.path.join(package_dir, "../include"))

    # 2. Run Cython to generate C/C++ source
    use_cpp = is_wrapper or "cppclass" in open(original_pyx_path).read()
    c_file = os.path.splitext(pyx_path)[0] + (".cpp" if use_cpp else ".c")
    
    cython_cmd = ["cython"]
    if use_cpp:
        cython_cmd.append("--cplus")
    cython_cmd += ["-I", native_include_dir, pyx_path]
    
    _LOGGER.info("Running Cython: %s", " ".join(cython_cmd))
    try:
        subprocess.run(cython_cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise CompilationError(f"Cython code generation failed:\n{e.stderr}") from e
 
    # 2. Fetch compile and link arguments for the active Python interpreter dynamically
    import sysconfig
    py_includes = [
        f"-I{sysconfig.get_path('include')}",
        f"-I{sysconfig.get_path('platinclude')}"
    ]
    
    # 3. Compile to shared library
    grpc_include_dir = os.path.abspath(os.path.join(package_dir, "../../../../include"))
    ext = ".dylib" if sys.platform == "darwin" else ".so"
    out_path = os.path.abspath(os.path.join(output_dir, f"{lib_name}{ext}"))
    
    # Detect extra C++ sources (like large_message.pb.cc) in output_dir
    extra_sources = []
    extra_libs = []
    compiler = "gcc"
    
    if use_cpp:
        compiler = "g++"
        extra_libs.append("-lprotobuf")
        # Look for any generated C++ Protobuf sources in the same directory as the .pyx file
        pyx_dir = os.path.dirname(pyx_path)
        for f in os.listdir(pyx_dir):
            if f.endswith(".pb.cc") or f.endswith(".pb.cpp") or (f.endswith(".cc") and f != os.path.basename(c_file)):
                extra_sources.append(os.path.join(pyx_dir, f))
 
    cc_cmd = [
        compiler,
        "-shared",
        "-fPIC",
        "-O3",
        f"-I{native_include_dir}",
        f"-I{grpc_include_dir}",
        "-o", out_path,
        c_file
    ] + extra_sources + py_includes + extra_libs
 
    h_file = os.path.splitext(pyx_path)[0] + ".h"
    _LOGGER.info("Compiling Cython C library: %s", " ".join(cc_cmd))
    try:
        subprocess.run(cc_cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise CompilationError(f"Failed to compile Cython handlers:\n{e.stderr}") from e
    finally:
        # Cleanup temporary generated C and H files
        if os.path.exists(c_file):
            os.remove(c_file)
        if os.path.exists(h_file):
            os.remove(h_file)
        # Cleanup dynamically generated JIT wrapper .pyx source file
        if is_wrapper and os.path.exists(pyx_path):
            os.remove(pyx_path)
    return load_native_module(out_path)


def parse_proto_fields(proto_path):
    """Quick and robust regex parser for protobuf message fields."""
    import re
    messages = {}
    current_message = None
    with open(proto_path, "r") as f:
        for line in f:
            line = line.strip()
            m = re.match(r"message\s+(\w+)", line)
            if m:
                current_message = m.group(1)
                messages[current_message] = []
                continue
            if line.startswith("}"):
                current_message = None
                continue
            if current_message and line:
                parts = line.split(";")
                if not parts:
                    continue
                field_line = parts[0].strip()
                m_field = re.match(r"(repeated\s+)?(\w+)\s+(\w+)\s*=", field_line)
                if m_field:
                    is_repeated = bool(m_field.group(1))
                    f_type = m_field.group(2)
                    f_name = m_field.group(3)
                    messages[current_message].append((f_type, f_name, is_repeated))
    return messages


def generate_cppclass_declarations(proto_path, request_types, response_types):
    """Dynamically generates the complete C++ cppclass definition string in Cython."""
    messages = parse_proto_fields(proto_path)
    decl = ""
    header_basename = os.path.basename(proto_path).replace(".proto", ".pb.h")
    
    # Extract the protobuf package name as the C++ namespace name dynamically
    import re
    ns = None
    try:
        with open(proto_path, "r") as f:
            for line in f:
                m = re.match(r"package\s+([\w.]+)", line.strip())
                if m:
                    ns = m.group(1).replace(".", "::")
                    break
    except Exception:
        pass
        
    if ns is None:
        ns = request_types[0].split("::")[0] if isinstance(request_types, list) else request_types.split("::")[0]

    decl += f'\ncdef extern from "{header_basename}" namespace "{ns}":\n'
    for msg_name, fields in messages.items():
        decl += f'    cdef cppclass {msg_name}:\n'
        decl += f'        {msg_name}()\n'
        for f_type, f_name, is_repeated in fields:
            cython_type = f_type
            if f_type == "string":
                cython_type = "string"
            elif f_type in ("int32", "int64"):
                cython_type = "int"
                
            if is_repeated:
                decl += f'        int {f_name}_size() nogil\n'
                decl += f'        {cython_type} {f_name}(int index) nogil\n'
                decl += f'        void add_{f_name}({cython_type} value) nogil\n'
            else:
                if f_type == "string":
                    decl += f'        const string& {f_name}() nogil\n'
                    decl += f'        void set_{f_name}(const string& value) nogil\n'
                else:
                    decl += f'        {cython_type} {f_name}() nogil\n'
                    decl += f'        void set_{f_name}({cython_type} value) nogil\n'
    return decl


def parse_servicer_methods(pyx_path, class_name):
    """Scans the .pyx file to extract all service class method signatures dynamically."""
    import re
    methods = []
    class_found = False
    indent_level = None
    
    with open(pyx_path, "r") as f:
        for line in f:
            if not line.strip() or line.strip().startswith("#"):
                continue
                
            if not class_found:
                m_class = re.match(r"cdef\s+(cpp)?class\s+" + re.escape(class_name), line.strip())
                if m_class:
                    class_found = True
                    continue
            else:
                line_indent = len(line) - len(line.lstrip())
                if indent_level is None:
                    indent_level = line_indent
                elif line_indent < indent_level and line.strip():
                    break
                    
                # Match C++ class method: int fn_name(req_type* req, resp_type* resp) nogil
                m_cpp = re.search(
                    r"int\s+(\w+)\((\w+)\*\s*\w+,\s*(\w+)\*\s*\w+\)\s*nogil",
                    line.strip()
                )
                if m_cpp:
                    fn_name = m_cpp.group(1)
                    req_type = m_cpp.group(2)
                    resp_type = m_cpp.group(3)
                    methods.append((fn_name, req_type, resp_type))
                    continue
                    
                # Fallback: Match Cython extension class method: cdef int fn_name(self, req_type* req, resp_type* resp) nogil
                m_cy = re.search(
                    r"cdef\s+int\s+(\w+)\(self,\s*(\w+)\*\s*\w+,\s*(\w+)\*\s*\w+\)\s*nogil",
                    line.strip()
                )
                if m_cy:
                    fn_name = m_cy.group(1)
                    req_type = m_cy.group(2)
                    resp_type = m_cy.group(3)
                    methods.append((fn_name, req_type, resp_type))
                    
    return methods


def parse_proto_service_methods(proto_path, service_name):
    """Scans the .proto file to extract all RPC methods mapped to their (req_streaming, resp_streaming) flags."""
    import re
    methods = {}
    service_base = service_name.split(".")[-1]
    service_found = False
    
    with open(proto_path, "r") as f:
        for line in f:
            line = line.strip()
            if not service_found:
                m = re.match(r"service\s+" + re.escape(service_base), line)
                if m:
                    service_found = True
                    continue
            else:
                if line.startswith("}"):
                    service_found = False
                    break
                # Match RPC definitions: rpc MethodName (stream RequestType) returns (stream ResponseType)
                m_rpc = re.search(
                    r"rpc\s+(\w+)\s*\(\s*(stream\s+)?(\w+)\s*\)\s*returns\s*\(\s*(stream\s+)?(\w+)\s*\)",
                    line
                )
                if m_rpc:
                    rpc_name = m_rpc.group(1)
                    req_streaming = m_rpc.group(2) is not None
                    resp_streaming = m_rpc.group(4) is not None
                    methods[rpc_name] = (req_streaming, resp_streaming)
    return methods



