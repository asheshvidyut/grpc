import grpc
from concurrent import futures
import time
from server import FastMathService
from math_cython_pb2 import add_MathServiceServicer_to_server

def serve():
    print("Starting Cython Fast-Path Math Server...")
    
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    
    # We use the generated registration function
    add_MathServiceServicer_to_server(FastMathService(), server)
    
    server.add_insecure_port("[::]:50051")
    server.start()
    
    print("Server listening on [::]:50051")
    print("Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve()
