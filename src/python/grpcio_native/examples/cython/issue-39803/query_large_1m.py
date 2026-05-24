import os
import sys
import grpc
import random

_GEN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _GEN_DIR)
import large_message_pb2
import large_message_pb2_grpc

def main():
    port = 50051
    print(f"Connecting to large message server on Port {port}...")
    
    options = [
        ("grpc.max_receive_message_length", 64 * 1024 * 1024),
        ("grpc.max_send_message_length", 64 * 1024 * 1024),
    ]
    
    with grpc.insecure_channel(f"localhost:{port}", options=options) as channel:
        stub = large_message_pb2_grpc.LargeMessageServiceStub(channel)
        
        print("Generating 1,000,000 floats payload...")
        floats_list = [random.random() for _ in range(1000000)]
        request = large_message_pb2.LargeMessageRequest(values=floats_list)
        
        print("Sending large request...")
        try:
            response = stub.ProcessLargeMessage(request)
            print(f"Received response status: '{response.status}'")
        except Exception as e:
            print(f"RPC Failed with error: {e}")

if __name__ == "__main__":
    main()
