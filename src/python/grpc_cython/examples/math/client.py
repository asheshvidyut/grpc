import grpc
import math_pb2
import math_pb2_grpc

def main():
    print("Connecting to math server...")
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = math_pb2_grpc.MathServiceStub(channel)

        print("Creating arrays...")
        matrix_a = [1.0] * 1024
        matrix_b = [2.5] * 1024

        req = math_pb2.MathRequest(matrix_a=matrix_a, matrix_b=matrix_b)
        print("Dispatching request to server...")
        try:
            response = stub.ComputeMatrix(req)
            res_len = len(response.result_matrix)
            print(f"Success! Server execution completed. Received {res_len} elements in response.")
        except Exception as e:
            print(f"Call finished with expected failure (since no backend is actually listening): {e}")

if __name__ == '__main__':
    main()

