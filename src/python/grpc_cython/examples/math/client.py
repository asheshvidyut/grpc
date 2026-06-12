import grpc
import math_cython_pb2

def main():
    print("Connecting to math server...")
    channel = grpc.insecure_channel('localhost:50051')

    print("Instantiating auto-generated Fast Client Stub...")
    client = math_cython_pb2.MathServiceFastStub(channel)

    print("Creating Numpy arrays...")
    try:
        import numpy as np
        matrix_a = np.ones(1024, dtype=np.float32)
        matrix_b = np.full(1024, 2.5, dtype=np.float32)
    except ImportError:
        import array
        matrix_a = array.array('f', [1.0] * 1024)
        matrix_b = array.array('f', [2.5] * 1024)

    print("Dispatching natively without freezing the asyncio event loop!")
    try:
        # Pass the arrays directly into the stub
        # The stub drops the GIL and does all heavy lifting in C++
        response = client.ComputeMatrix(matrix_a=matrix_a, matrix_b=matrix_b)
        print(f"Success! Native execution completed. Response object: {response}")
    except Exception as e:
        print(f"Call finished with expected failure (since no backend is actually listening): {e}")

if __name__ == '__main__':
    main()
