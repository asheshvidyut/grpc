#!/usr/bin/env python3
"""
Test script to demonstrate the Windows CTRL+C fix for gRPC servers.

This script shows how the enhanced wait_for_termination method now works
better on Windows by using shorter timeouts for improved signal responsiveness.
"""

import grpc
import signal
import sys
import time
from concurrent import futures

# Simple test service
class TestServicer:
    def TestMethod(self, request, context):
        return grpc.StatusCode.OK, b"Hello from test server"

def serve():
    """Start a test gRPC server with improved Windows signal handling."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add a simple test service
    # Note: In a real scenario, you'd add your actual service here
    
    server.add_insecure_port('[::]:50051')
    
    def signal_handler(sig, frame):
        print(f'\nReceived signal {sig}. Shutting down server...')
        server.stop(5)  # 5 second grace period
        sys.exit(0)
    
    # Register signal handler for SIGINT (CTRL+C)
    signal.signal(signal.SIGINT, signal_handler)
    
    server.start()
    print('Test server started on port 50051.')
    print('The server now uses improved Windows signal handling.')
    print('Press Ctrl+C to test the enhanced signal responsiveness...')
    
    try:
        # This will now work better on Windows due to the shorter timeout
        server.wait_for_termination()
    except KeyboardInterrupt:
        print('\nReceived KeyboardInterrupt. Shutting down...')
        server.stop(5)
        sys.exit(0)

if __name__ == '__main__':
    serve()
