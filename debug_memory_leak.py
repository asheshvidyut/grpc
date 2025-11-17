#!/usr/bin/env python3
"""
Debug script for investigating memory leaks in gRPC with threading.
This script is designed to be run under gdb or with memory profiling tools.
"""

import contextlib
import os
import tempfile
import threading
import time
import sys
import gc
import tracemalloc

import grpc

# --- Configuration Constants ---
ARBITRARY_PORT = 33333
ARBITRARY_FILE_SIZE = 50 * 1024 * 1024 
READ_SIZE = 31 * 1024 * 1024 

# Enable tracemalloc for detailed memory tracking
tracemalloc.start()

def read_file(file_path: str):
    """Reads a large chunk of data from the file."""
    try:
        with open(file_path, 'rb') as fp:
            data = fp.read(READ_SIZE)
            # Keep a reference to see if this is the leak
            _ = data
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)

def trigger_memleak(file_path: str, num_iterations: int = 10):
    """
    Repeatedly runs an IO task in a thread and creates/closes a gRPC channel.
    """
    print(f"Starting {num_iterations} iterations...")
    print("=" * 60)
    
    # Take snapshot before loop
    snapshot_before = tracemalloc.take_snapshot()
    
    for i in range(num_iterations):
        print(f"\n--- Iteration {i + 1}/{num_iterations} ---")
        
        # 1. Run the IO task in a thread
        t = threading.Thread(target=read_file, kwargs=dict(file_path=file_path))
        t.start()
        t.join()
        
        # 2. Create and close gRPC channel
        c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
        c.close()
        
        # Force GC to see what remains
        gc.collect()
        
        # Take snapshot after each iteration
        snapshot_after = tracemalloc.take_snapshot()
        
        # Compare snapshots
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        
        print(f"Top 10 memory allocations since start:")
        for stat in top_stats[:10]:
            print(stat)
        
        # Update baseline for next iteration
        snapshot_before = snapshot_after
        
        # Breakpoint for gdb - set breakpoint here to inspect state
        if i == 0:
            print("\n[DEBUG] First iteration complete. Set breakpoint here to inspect.")
            print("In gdb, you can now inspect:")
            print("  - Python objects: py-list")
            print("  - Memory allocations: info proc mappings")
            print("  - Threads: info threads")
    
    # Final snapshot
    snapshot_final = tracemalloc.take_snapshot()
    top_stats = snapshot_final.compare_to(snapshot_before, 'lineno')
    
    print("\n" + "=" * 60)
    print("FINAL MEMORY STATISTICS:")
    print("=" * 60)
    print("\nTop 20 memory allocations:")
    for stat in top_stats[:20]:
        print(stat)
    
    # Get current memory usage
    current, peak = tracemalloc.get_traced_memory()
    print(f"\nCurrent traced memory: {current / 1024 / 1024:.2f} MB")
    print(f"Peak traced memory: {peak / 1024 / 1024:.2f} MB")

def main():
    """Main function to setup and run the leak test."""
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        print(f"Generating temporary file of size {ARBITRARY_FILE_SIZE / 1024 ** 2:.2f} MB...")
        for _ in range(ARBITRARY_FILE_SIZE // (1024 * 1024)):
            tmp.write(os.urandom(1024 * 1024))
        remaining = ARBITRARY_FILE_SIZE % (1024 * 1024)
        if remaining:
            tmp.write(os.urandom(remaining))
        tmp.flush()
        file_path = tmp.name
        
        print(f"Temporary file created at: {file_path!r}")
        print(f"Data read size per iteration: {READ_SIZE / 1024 ** 2:.2f} MB")
        print("\n" + "=" * 60)
        print("MEMORY LEAK DEBUG SESSION")
        print("=" * 60)
        print("\nRun this script with:")
        print("  gdb --args python3 debug_memory_leak.py")
        print("\nOr with valgrind:")
        print("  valgrind --leak-check=full --show-leak-kinds=all python3 debug_memory_leak.py")
        print("\nOr with Python's tracemalloc (already enabled):")
        print("  python3 debug_memory_leak.py")
        print("=" * 60 + "\n")
        
        # Small delay to allow gdb to attach
        time.sleep(1)
        
        trigger_memleak(file_path, num_iterations=5)

if __name__ == '__main__':
    main()

