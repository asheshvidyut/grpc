import contextlib
import gc
import os
import resource
import sys
import tempfile
import threading
import time
import tracemalloc

import grpc

# Try to import psutil for better memory monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not available. Install with: pip install psutil")
    print("Falling back to resource module (Unix only).\n")

ARBITRARY_PORT = 33333
ARBITRARY_FILE_SIZE = 50 * 1024 * 1024


@contextlib.contextmanager
def temporary_urandom_file(size: int, chunk_size: int = 1024 * 1024):
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        for _ in range(size // chunk_size):
            tmp.write(os.urandom(chunk_size))
        remaining = size % chunk_size
        if remaining:
            tmp.write(os.urandom(remaining))
        yield tmp.name


def get_memory_usage():
    """Get current memory usage in MB."""
    if PSUTIL_AVAILABLE:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        return mem_info.rss / (1024 * 1024)  # RSS in MB
    else:
        # Fallback to resource module (Unix only)
        try:
            mem_info = resource.getrusage(resource.RUSAGE_SELF)
            return mem_info.ru_maxrss / 1024  # On Linux, this is in KB
        except (AttributeError, OSError):
            # Windows or other systems
            return 0.0


def format_memory(mb):
    """Format memory value for display."""
    if mb < 1024:
        return f"{mb:.2f} MB"
    else:
        return f"{mb / 1024:.2f} GB"


@contextlib.contextmanager
def profile_memory(label=""):
    """Context manager to profile memory usage."""
    mem_before = get_memory_usage()
    try:
        yield
    finally:
        mem_after = get_memory_usage()
        diff = mem_after - mem_before
        sign = "+" if diff >= 0 else "-"
        print(f"[Memory] {label:20s} "
              f"before: {format_memory(mem_before):>10s}, "
              f"after: {format_memory(mem_after):>10s}, "
              f"diff: {sign}{format_memory(abs(diff)):>10s}")


def read_file(file_path: str):
    """Read a file chunk that triggers the memory leak without the fix."""
    data = None  # Explicitly scope the variable
    with open(file_path, 'rb') as fp:
        # Memory leak occurs only below 32MB (X * 1024 * 1024 where X < 32)
        data = fp.read(31 * 1024 * 1024)
    # Explicitly delete the data to help with garbage collection
    del data


def trigger_memleak(file_path: str, iterations: int = 50):
    """Test function that reproduces the memory leak."""
    print(f"\nStarting {iterations} iterations...")
    print(f"{'Iteration':<10s} {'Memory (MB)':<15s} {'Delta (MB)':<15s}")
    print("-" * 40)
    
    initial_memory = get_memory_usage()
    prev_memory = initial_memory
    
    for i in range(iterations):
        # Take snapshot before iteration
        if i > 0 and i % 10 == 0:  # Every 10 iterations
            snapshot_before = tracemalloc.take_snapshot()
        
        t = threading.Thread(target=read_file, kwargs=dict(file_path=file_path))
        t.start()
        t.join()
        # Ensure thread is fully cleaned up

        # Create and close a gRPC channel
        # With the fix, this should not cause memory to accumulate
        c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
        c.close()
        
        # Small delay to allow gRPC cleanup threads to complete
        # grpc_shutdown() may spawn detached cleanup threads
        time.sleep(0.01)
        
        # Force garbage collection to help release memory
        # This helps identify if the issue is with GC or actual leaks
        collected = gc.collect()
        
        # Additional GC pass to catch objects freed by first pass
        if collected > 0:
            collected += gc.collect()
        
        # Check what was allocated if memory increased significantly
        if i > 0 and i % 10 == 0 and delta > 20:  # Significant increase
            snapshot_after = tracemalloc.take_snapshot()
            top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
            print(f"\n[Iteration {i}] Top allocations since last check:")
            for stat in top_stats[:5]:
                print(f"  {stat}")
        
        current_memory = get_memory_usage()
        delta = current_memory - prev_memory
        total_delta = current_memory - initial_memory
        
        print(f"{i:<10d} {format_memory(current_memory):<15s} "
              f"{'+' if delta >= 0 else ''}{format_memory(delta):<15s} "
              f"(total: {'+' if total_delta >= 0 else ''}{format_memory(total_delta)}, "
              f"GC: {collected})")
        
        prev_memory = current_memory
        time.sleep(0.5)  # Reduced sleep time for faster testing
    
    final_memory = get_memory_usage()
    total_leak = final_memory - initial_memory
    print("-" * 40)
    print(f"Initial memory: {format_memory(initial_memory)}")
    print(f"Final memory:   {format_memory(final_memory)}")
    print(f"Total increase: {format_memory(total_leak)}")
    
    if total_leak > 100:  # More than 100MB increase is suspicious
        print(f"\n⚠️  WARNING: Memory increased by {format_memory(total_leak)}!")
        print("   This might indicate a memory leak.")
    else:
        print(f"\n✓ Memory usage is stable (increase < 100MB)")


def main():
    """Main test function."""
    # Start tracemalloc to track memory allocations
    tracemalloc.start(10)  # Keep 10 frames
    
    print("=" * 60)
    print("Testing memory leak fix for gRPC channel close")
    print("=" * 60)
    print("This test reproduces the scenario from issue #40817")
    print("With the fix, memory usage should remain stable.")
    print()
    
    # Show initial memory
    initial_memory = get_memory_usage()
    print(f"Initial process memory: {format_memory(initial_memory)}")
    print()
    
    with temporary_urandom_file(ARBITRARY_FILE_SIZE) as file_path:
        print(f"Created test file: {file_path!r}")
        print(f"File size: {os.path.getsize(file_path) / (1024*1024):.2f} MB")
        
        # Get iterations from command line or use default
        iterations = 50
        if len(sys.argv) > 1:
            try:
                iterations = int(sys.argv[1])
            except ValueError:
                print(f"Invalid iteration count: {sys.argv[1]}, using default: {iterations}")
        
        trigger_memleak(file_path, iterations)
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
    
    # Show tracemalloc statistics
    print("\nTop 10 memory allocations (tracemalloc):")
    print("-" * 60)
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    for index, stat in enumerate(top_stats[:10], 1):
        print(f"{index}. {stat}")
    
    # Show memory by filename
    print("\nTop 10 memory allocations by filename:")
    print("-" * 60)
    top_stats = snapshot.statistics('filename')
    for index, stat in enumerate(top_stats[:10], 1):
        print(f"{index}. {stat}")
    
    print("\nAdditional monitoring options:")
    print("1. Use 'top' or 'htop' in another terminal:")
    print("   top -p $(pgrep -f test_memory_leak_fix.py)")
    print("\n2. Use 'ps' to check memory:")
    print("   ps aux | grep test_memory_leak_fix.py")


if __name__ == '__main__':
    main()

