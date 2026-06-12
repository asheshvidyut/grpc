import time
import grpc
import threading
import statistics
import math_cython_pb2

# ==========================================
# 1. Pure Python gRPC Implementation
# ==========================================
import ctypes
import os
import subprocess

# Auto-compile the C kernel for the benchmark
kernel_so = os.path.join(os.path.dirname(__file__), "math_kernel.so")
subprocess.run(["gcc", "-shared", "-O3", "-fPIC", "-o", kernel_so, os.path.join(os.path.dirname(__file__), "math_kernel.c")])

math_lib = ctypes.CDLL(kernel_so)
math_lib.compute_matrix_c.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), ctypes.c_int]

class PurePythonMathService:
    def ComputeMatrix(self, request, context):
        # 1. Python Protobuf Deserialization Tax (Implicitly happened before this method)
        matrix_a = request.matrix_a
        matrix_b = request.matrix_b
        size = len(matrix_a)
        
        # 2. Convert Python Protobuf to C-Arrays for Ctypes (The "Object Tax")
        c_a = (ctypes.c_float * size)(*matrix_a)
        c_b = (ctypes.c_float * size)(*matrix_b)
        c_out = (ctypes.c_float * size)()
        
        # 3. Ctypes Delegation (Fast C execution)
        math_lib.compute_matrix_c(c_a, c_b, c_out, size)
            
        # 4. Serialize back to Python Protobuf
        return math_cython_pb2.MathResponse(result_matrix=list(c_out))

# ==========================================
# 2. Benchmark Harness
# ==========================================
def measure_throughput(target, payload_a, payload_b, threads=8, duration_s=3.0):
    stop_at = time.perf_counter() + duration_s
    counts = [0] * threads

    def worker(idx):
        with grpc.insecure_channel(target) as channel:
            # We use the generated fast stub!
            client = math_cython_pb2.MathServiceFastStub(channel)
            local = 0
            while time.perf_counter() < stop_at:
                try:
                    client.ComputeMatrix(matrix_a=payload_a, matrix_b=payload_b)
                    local += 1
                except:
                    pass # Ignore if server isn't fully booted in this dummy script
            counts[idx] = local

    workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    start = time.perf_counter()
    for w in workers: w.start()
    for w in workers: w.join()
    
    elapsed = time.perf_counter() - start
    return sum(counts) / elapsed

def measure_throughput_pure(target, payload_a, payload_b, threads=8, duration_s=3.0):
    import math_pb2_grpc
    import math_pb2
    stop_at = time.perf_counter() + duration_s
    counts = [0] * threads

    def worker(idx):
        with grpc.insecure_channel(target) as channel:
            client = math_pb2_grpc.MathServiceStub(channel)
            req = math_pb2.MathRequest(matrix_a=payload_a, matrix_b=payload_b)
            local = 0
            while time.perf_counter() < stop_at:
                client.ComputeMatrix(req)
                local += 1
            counts[idx] = local

    workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    start = time.perf_counter()
    for w in workers: w.start()
    for w in workers: w.join()
    
    elapsed = time.perf_counter() - start
    return sum(counts) / elapsed

def main():
    print("=== Zero-GIL Protoc Generation vs Pure Python Benchmark ===")
    
    from concurrent import futures
    import math_pb2_grpc
    
    try:
        from server import FastMathService
        from math_cython_pb2 import add_MathServiceServicer_to_server
    except ImportError:
        print("Please compile the cython extension first: python3 setup.py build_ext --inplace")
        return
        
    # 1. Start Pure Python Server
    py_server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    math_pb2_grpc.add_MathServiceServicer_to_server(PurePythonMathService(), py_server)
    py_server.add_insecure_port("[::]:50051")
    py_server.start()
    
    # 2. Start Cython Fast Server
    cy_server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    add_MathServiceServicer_to_server(FastMathService(), cy_server)
    cy_server.add_insecure_port("[::]:50052")
    cy_server.start()
    
    try:
        import numpy as np
        matrix_a = np.ones(1024, dtype=np.float32)
        matrix_b = np.full(1024, 2.5, dtype=np.float32)
        
        print("Running Pure Python (ctypes delegation) test...")
        py_rps = measure_throughput_pure("localhost:50051", matrix_a, matrix_b)
        
        print("Running Cython Generated Fast-Path test...")
        cy_rps = measure_throughput("localhost:50052", matrix_a, matrix_b)
        
        print("\nResults:")
        print(f"Pure Python (ctypes): {py_rps:,.0f} QPS")
        print(f"Cython Fast-Path:     {cy_rps:,.0f} QPS")
        if py_rps > 0:
            print(f"Speedup:              {cy_rps/py_rps:.2f}x")
    finally:
        py_server.stop(0)
        cy_server.stop(0)

if __name__ == '__main__':
    main()
