# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""grpcio_cython — register native (C/C++) handlers with a gRPC Python server.

Example:

    import grpc
    from concurrent import futures
    import grpcio_cython

    module = grpcio_cython.load_native_module("./echo_handler.so")
    handler = grpcio_cython.native_unary_unary_rpc_method_handler(
        module, "echo_unary"
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    server.add_generic_rpc_handlers((
        grpc.method_handlers_generic_handler("echo.Echo", {"Echo": handler}),
    ))
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()
"""

import grpc

from ._handler import (
    NativeHandlerError,
    NativeModule,
    load_native_module,
    native_stream_stream_rpc_method_handler,
    native_stream_unary_rpc_method_handler,
    native_unary_stream_rpc_method_handler,
    native_unary_unary_rpc_method_handler,
)
from ._compiler import (
    CompilationError,
    compile_and_load_cython,
)

__all__ = [
    "NativeHandlerError",
    "NativeModule",
    "load_native_module",
    "native_stream_stream_rpc_method_handler",
    "native_stream_unary_rpc_method_handler",
    "native_unary_stream_rpc_method_handler",
    "native_unary_unary_rpc_method_handler",
    "CompilationError",
    "compile_and_load_cython",
    "add_native_handlers",
    "get_c_core_invoke_fn_addr",
]

def get_c_core_invoke_fn_addr() -> int:
    """Retrieve the C function pointer address of the C-Core invoker."""
    try:
        from grpc._cython import cygrpc
        return cygrpc.get_c_core_invoke_fn_addr()
    except ImportError as e:
        raise RuntimeError("grpcio compiled C-extensions not loaded") from e

def add_native_handlers(
    server: grpc.Server,
    pyx_file: str,
    service_name: str,
    methods: list = None,
    output_dir: str = None,
    lib_name: str = None,
    class_name: str = None
):
    """Automatically JIT-compiles clean Cython handlers and registers them to the server in one clean call.

    If methods is not provided and class_name is specified, the compiler will automatically
    autowire all gRPC configurations, namespaces, class interfaces, and symbol linkages
    from the .proto schema and Cython servicer class dynamically at runtime!

    Args:
        server: The standard gRPC Server (or AsyncIO server) to register the JIT handlers on.
        pyx_file: Path to the Cython .pyx source file containing clean business logic.
        service_name: Fully qualified protobuf service name (e.g. 'echo.EchoService').
        methods: Optional list of RPC method names, or dict mapping of custom types.
        output_dir: Optional directory to write JIT compilation cache.
        lib_name: Optional name of JIT compiled shared library.
        class_name: Optional name of JIT compiled Cython service class to instantiate and route calls to.
    """
    import os

    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(pyx_file))

    # 1. Resolve JIT methods, streaming flags, and map class type signatures dynamically
    derived_methods = {}
    package_name = service_name.split(".")[0]

    # Locate the .proto schema file dynamically by matching the service definition
    dir_name = os.path.dirname(os.path.abspath(pyx_file))
    proto_name = None
    service_base = service_name.split(".")[-1]
    import re
    for f in os.listdir(dir_name):
        if f.endswith(".proto"):
            try:
                proto_path = os.path.join(dir_name, f)
                with open(proto_path, "r") as pf:
                    content = pf.read()
                    if re.search(r"\bservice\s+" + re.escape(service_base) + r"\b", content):
                        proto_name = f
                        break
            except Exception:
                pass
    if proto_name is None:
        # Fallback to first proto if no service matches
        for f in os.listdir(dir_name):
            if f.endswith(".proto"):
                proto_name = f
                break
            
    from ._compiler import parse_proto_service_methods
    rpc_methods = {}
    if proto_name:
        proto_path = os.path.join(dir_name, proto_name)
        rpc_methods = parse_proto_service_methods(proto_path, service_name)

    if class_name and methods is None:
        from ._compiler import parse_servicer_methods
        if proto_name:
            methods_info = parse_servicer_methods(pyx_file, class_name)
            
            # Match and align Cython methods to Proto RPC definitions case-insensitively
            for fn_name, req_base, resp_base in methods_info:
                match_name = fn_name.lower().replace("cython_", "").replace("_", "")
                for rpc_name, streaming_flags in rpc_methods.items():
                    if rpc_name.lower().replace("_", "") == match_name:
                        req_t = f"{package_name}::{req_base}"
                        resp_t = f"{package_name}::{resp_base}"
                        # Save type mappings along with request/response streaming flags
                        derived_methods[rpc_name] = (req_t, resp_t, fn_name, streaming_flags[0], streaming_flags[1])
                        break
        else:
            derived_methods = {}
    else:
        # 2. Fallback: Auto-wire dynamically if methods list is passed explicitly
        if methods is None:
            methods = []
            
        if isinstance(methods, (list, tuple)):
            for method_name in methods:
                req_t = f"{package_name}::{method_name}Request"
                resp_t = f"{package_name}::{method_name}Response"
                fn_name = f"cython_{method_name.lower()}"
                streaming_flags = rpc_methods.get(method_name, (False, False))
                derived_methods[method_name] = (req_t, resp_t, fn_name, streaming_flags[0], streaming_flags[1])
        else:
            # If explicit dictionary mappings are provided, default to non-streaming unless specified
            for rpc_name, config in methods.items():
                req_t, resp_t, fn_name = config[:3]
                req_streaming = config[3] if len(config) > 3 else False
                resp_streaming = config[4] if len(config) > 4 else False
                derived_methods[rpc_name] = (req_t, resp_t, fn_name, req_streaming, resp_streaming)

    # Extract lists for dynamic JIT compiler
    request_types = []
    response_types = []
    handler_fns = []
    for rpc_name, config in derived_methods.items():
        req_t, resp_t, fn_name = config[:3]
        request_types.append(req_t)
        response_types.append(resp_t)
        handler_fns.append(fn_name)

    # JIT compile and generate the loop-based wrappers automatically
    module = compile_and_load_cython(
        pyx_file=pyx_file,
        output_dir=output_dir,
        lib_name=lib_name,
        request_type=request_types,
        response_type=response_types,
        handler_fn=handler_fns,
        class_name=class_name
    )

    # Dynamically wrap each JIT handler using the correct standard gRPC method handler factory (supporting all 4 types!)
    rpc_method_handlers = {}
    for rpc_name, config in derived_methods.items():
        req_t, resp_t, fn_name, req_streaming, resp_streaming = config
        c_export_fn = f"native_{fn_name}"
        
        # Select correct method handler factory dynamically
        if not req_streaming and not resp_streaming:
            handler_factory = native_unary_unary_rpc_method_handler
        elif not req_streaming and resp_streaming:
            handler_factory = native_unary_stream_rpc_method_handler
        elif req_streaming and not resp_streaming:
            handler_factory = native_stream_unary_rpc_method_handler
        else:
            handler_factory = native_stream_stream_rpc_method_handler
            
        rpc_method_handlers[rpc_name] = handler_factory(
            module, c_export_fn
        )

    # Create generic handler and add to server
    generic_handler = grpc.method_handlers_generic_handler(
        service_name, rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))

__version__ = "0.1.0"
