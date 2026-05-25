import os
import sys
import subprocess
import platform
import ctypes
from concurrent import futures
import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
_PROTO_PATH = os.path.join(_GEN_DIR, "matmul.proto")

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

    # 1. Dynamically generate Python Protobuf classes
    print("Generating Python Protobuf classes from matmul.proto...")
    subprocess.check_call([
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{_GEN_DIR}", f"--python_out={_GEN_DIR}", f"--grpc_python_out={_GEN_DIR}",
        _PROTO_PATH
    ])

    sys.path.insert(0, _GEN_DIR)
    import matmul_pb2
    import matmul_pb2_grpc

    # 2. Create standard Python gRPC server
    options = [
        ("grpc.max_receive_message_length", 64 * 1024 * 1024),
        ("grpc.max_send_message_length", 64 * 1024 * 1024),
    ]
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8), options=options)

    # 3. Register the selected backend servicer
    if mode == "pure-python":
        print("Registering pure Python MatMul servicer...")
        class PurePythonMatMulServicer(matmul_pb2_grpc.MatMulServiceServicer):
            def MatMul(self, request, context):
                n = request.n
                c = [0.0] * (n * n)
                for i in range(n):
                    for j in range(n):
                        s = 0.0
                        for k in range(n):
                            s += request.a[i * n + k] * request.b[k * n + j]
                        c[i * n + j] = s
                return matmul_pb2.MatMulResponse(c=c)
        
        matmul_pb2_grpc.add_MatMulServiceServicer_to_server(PurePythonMatMulServicer(), server)

    elif mode == "ctypes":
        print("Building C handler shared library...")
        subprocess.check_call(["make", "-C", _GEN_DIR])

        lib_name = "matmul_handler.dylib" if platform.system() == "Darwin" else "matmul_handler.so"
        lib_path = os.path.join(_GEN_DIR, lib_name)
        print(f"Loading standard C library via ctypes from: {lib_path}")
        lib = ctypes.CDLL(lib_path)
        lib.matmul_c.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int
        ]
        lib.matmul_c.restype = None

        class CtypesMatMulServicer(matmul_pb2_grpc.MatMulServiceServicer):
            def MatMul(self, request, context):
                n = request.n
                size = n * n
                
                # Convert python lists to ctypes float arrays
                a_arr = (ctypes.c_float * size)(*request.a)
                b_arr = (ctypes.c_float * size)(*request.b)
                c_arr = (ctypes.c_float * size)()
                
                # Delegate multiplication to C library
                lib.matmul_c(a_arr, b_arr, c_arr, n)
                
                return matmul_pb2.MatMulResponse(c=list(c_arr))
        
        matmul_pb2_grpc.add_MatMulServiceServicer_to_server(CtypesMatMulServicer(), server)

    else: # JIT-compiled grpcio_native mode
        print("Generating C++ Protobuf classes from matmul.proto...")
        subprocess.check_call([
            "protoc", f"-I{_GEN_DIR}", f"--cpp_out={_GEN_DIR}",
            _PROTO_PATH
        ])
        print("Compiling and registering Cython JIT C++ handlers dynamically...")
        src_path = os.path.join(_GEN_DIR, "handler.pyx")
        grpcio_native.add_native_handlers(
            server=server,
            pyx_file=src_path,
            service_name="matmul.MatMulService",
            class_name="MatMulService"
        )
        print("Cython JIT C++ module compiled and registered successfully!")

    # 4. Enable Server Reflection for all backends
    print("Enabling gRPC Server Reflection...")
    from grpc_reflection.v1alpha import reflection
    SERVICE_NAMES = (
        matmul_pb2.DESCRIPTOR.services_by_name['MatMulService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    print("gRPC Server Reflection enabled successfully!")

    port = server.add_insecure_port("[::]:50089")
    print(f"Starting standard gRPC server ({mode} mode) on port: {port}")
    server.start()
    print("Server started. Press Ctrl+C to terminate.")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0)

if __name__ == "__main__":
    main()
