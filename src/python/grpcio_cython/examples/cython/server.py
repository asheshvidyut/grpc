import os
import sys
import subprocess
from concurrent import futures
import grpc

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
_PROTO_PATH = os.path.join(_GEN_DIR, "echo.proto")

# Add grpcio_cython path (robust absolute resolution)
sys.path.insert(0, os.path.abspath(os.path.join(_GEN_DIR, "..", "..")))
import grpcio_cython

def main():
    # 1. Dynamically generate Python and C++ protobuf classes at startup
    print("Generating Python Protobuf classes from echo.proto...")
    subprocess.check_call([
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{_GEN_DIR}", f"--python_out={_GEN_DIR}", f"--grpc_python_out={_GEN_DIR}",
        _PROTO_PATH
    ])
    print("Generating C++ Protobuf classes from echo.proto...")
    subprocess.check_call([
        "protoc", f"-I{_GEN_DIR}", f"--cpp_out={_GEN_DIR}",
        _PROTO_PATH
    ])

    src_path = os.path.join(os.path.dirname(__file__), "handler.pyx")

    options = [
        ("grpc.max_receive_message_length", 64 * 1024 * 1024),
        ("grpc.max_send_message_length", 64 * 1024 * 1024),
    ]
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4), options=options)

    # Automatically JIT-compile and register the service class! (100% zero-boilerplate!)
    print("Compiling and registering Cython handlers dynamically...")
    grpcio_cython.add_native_handlers(
        server=server,
        pyx_file=src_path,
        service_name="echo.EchoService",
        class_name="EchoService"
    )
    print("Cython JIT module compiled and registered successfully!")

    port = server.add_insecure_port("[::]:50088")
    print(f"Starting JIT Cython C++ Protobuf server on port: {port}")
    server.start()
    print("Server started. Press Ctrl+C to terminate.")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=0)

if __name__ == "__main__":
    main()
