import os
import sys
import subprocess
import platform
import ctypes
from concurrent import futures
import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
_PROTO_PATH = os.path.join(_GEN_DIR, "echo.proto")

# Add grpcio_native path to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(_GEN_DIR, "..", "..")))
import grpcio_native

def main():
    import argparse
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--pure-python", action="store_true", help="Run pure Python servicer")
    group.add_argument("--ctypes", action="store_true", help="Run standard Python servicer delegating to C via ctypes")
    group.add_argument("--jit", action="store_true", default=True, help="Run high-performance JIT Cython/C++ handler (default)")
    args = parser.parse_args()

    # Determine the running mode
    if args.pure_python:
        mode = "pure-python"
    elif args.ctypes:
        mode = "ctypes"
    else:
        mode = "jit"

    # 1. Dynamically generate Python Protobuf classes for Reflection support
    print("Generating Python Protobuf classes from echo.proto...")
    subprocess.check_call([
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{_GEN_DIR}", f"--python_out={_GEN_DIR}", f"--grpc_python_out={_GEN_DIR}",
        _PROTO_PATH
    ])

    sys.path.insert(0, _GEN_DIR)
    import echo_pb2
    import echo_pb2_grpc

    # 2. Create standard Python gRPC server
    options = [
        ("grpc.max_receive_message_length", 64 * 1024 * 1024),
        ("grpc.max_send_message_length", 64 * 1024 * 1024),
    ]
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8), options=options)

    # 3. Register the selected backend servicer
    if mode == "pure-python":
        print("Registering pure Python Echo servicer...")
        class PurePythonEchoServicer(echo_pb2_grpc.EchoServiceServicer):
            def Echo(self, request, context):
                return echo_pb2.EchoResponse(message=request.message)
        
        echo_pb2_grpc.add_EchoServiceServicer_to_server(PurePythonEchoServicer(), server)

    elif mode == "ctypes":
        print("Building C handler shared library...")
        subprocess.check_call(["make", "-C", _GEN_DIR])

        lib_name = "echo_handler.dylib" if platform.system() == "Darwin" else "echo_handler.so"
        lib_path = os.path.join(_GEN_DIR, lib_name)
        print(f"Loading standard C library via ctypes from: {lib_path}")
        lib = ctypes.CDLL(lib_path)
        lib.echo_c.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        lib.echo_c.restype = None

        class CtypesEchoServicer(echo_pb2_grpc.EchoServiceServicer):
            def Echo(self, request, context):
                in_bytes = request.message.encode('utf-8')
                length = len(in_bytes)
                out_buff = ctypes.create_string_buffer(length + 1)
                lib.echo_c(in_bytes, out_buff, length)
                out_str = out_buff.value.decode('utf-8')
                return echo_pb2.EchoResponse(message=out_str)
        
        echo_pb2_grpc.add_EchoServiceServicer_to_server(CtypesEchoServicer(), server)


    else: # JIT-compiled grpcio_native mode
        print("Generating C++ Protobuf classes from echo.proto...")
        subprocess.check_call([
            "protoc", f"-I{_GEN_DIR}", f"--cpp_out={_GEN_DIR}",
            _PROTO_PATH
        ])
        print("Compiling and registering Cython JIT C++ handlers dynamically...")
        src_path = os.path.join(_GEN_DIR, "handler.pyx")
        grpcio_native.add_native_handlers(
            server=server,
            pyx_file=src_path,
            service_name="echo.EchoService",
            class_name="EchoService"
        )
        print("Cython JIT C++ module compiled and registered successfully!")

    # 4. Enable Server Reflection for all backends
    print("Enabling gRPC Server Reflection...")
    from grpc_reflection.v1alpha import reflection
    SERVICE_NAMES = (
        echo_pb2.DESCRIPTOR.services_by_name['EchoService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    print("gRPC Server Reflection enabled successfully!")

    port = server.add_insecure_port("[::]:50088")
    print(f"Starting standard gRPC server ({mode} mode) on port: {port}")
    server.start()
    print("Server started. Press Ctrl+C to terminate.")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0)

if __name__ == "__main__":
    main()
