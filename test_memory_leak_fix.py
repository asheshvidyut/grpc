import contextlib
import os
import tempfile
import threading
import time
import psutil
import gc
import sys

import grpc

# --- Configuration Constants ---
ARBITRARY_PORT = 33333
# Total size of the temporary file (50 MB)
ARBITRARY_FILE_SIZE = 50 * 1024 * 1024 
# The amount of data read by read_file (31 MB)
READ_SIZE = 31 * 1024 * 1024 

# --- Utility Functions ---

def get_current_rss_mb() -> float:
    """Helper function to return the current process RSS in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 ** 2

@contextlib.contextmanager
def temporary_urandom_file(size: int, chunk_size: int = 1024 * 1024):
    """Creates a temporary file filled with random bytes and yields its path."""
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        print(f"Generating temporary file of size {size / 1024 ** 2:.2f} MB...")
        for _ in range(size // chunk_size):
            tmp.write(os.urandom(chunk_size))
        remaining = size % chunk_size
        if remaining:
            tmp.write(os.urandom(remaining))
        tmp.flush()
        yield tmp.name

@contextlib.contextmanager
def profile_memory(label=""):
    """
    A context manager to measure and report the Resident Set Size (RSS)
    memory usage of the current process before and after the block.
    """
    mem_before = get_current_rss_mb()
    print("---")
    print(f"[MemoryProfile] Starting measurement for: {label}")
    print(f"  Initial RSS: {mem_before:.2f} MB")
    print("---")
    try:
        yield
    finally:
        # Force a garbage collection before final measurement
        gc.collect() 
        
        mem_after = get_current_rss_mb()
        diff = mem_after - mem_before
        sign = "+" if diff >= 0 else "-"
        print("---")
        print(f"[MemoryProfile] **{label}** Summary")
        print(f"  Final RSS: {mem_after:.2f} MB")
        print(f"  Difference: {sign}{abs(diff):.2f} MB")
        print("---")

# --- Leak Demonstration Functions ---

def read_file(file_path: str):
    """Reads a large chunk of data from the file."""
    try:
        with open(file_path, 'rb') as fp:
            fp.read(READ_SIZE)
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)

def trigger_memleak(file_path: str):
    """
    Repeatedly runs an IO task in a thread and creates/closes a gRPC channel,
    now with **per-iteration memory logging**.
    """
    # Get the memory baseline just before the loop starts for cleaner comparison
    initial_rss = get_current_rss_mb()
    print(f"Baseline RSS before loop: {initial_rss:.2f} MB")

    for _ in range(50):
        # 1. Run the IO task in a thread
        t = threading.Thread(target=read_file, kwargs=dict(file_path=file_path))
        t.start()
        t.join()

        # >>>>>>>>>> LEAK CAUSE <<<<<<<<<<<<
        c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
        c.close()
        # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
        
        # --- PER-ITERATION MEMORY LOGGING ---
        current_rss = get_current_rss_mb()
        diff_from_start = current_rss - initial_rss
        
        print(
            f"Iteration {_ + 1}/50: "
            f"Current RSS: {current_rss:.2f} MB | "
            f"Total increase: +{diff_from_start:.2f} MB"
        )
        time.sleep(0.1) 

# --- Main Execution ---

def main():
    """Main function to setup the file, profile memory, and trigger the leak."""
    
    # 1. Create and manage the temporary file
    with temporary_urandom_file(ARBITRARY_FILE_SIZE) as file_path:
        print(f"Temporary file created at: {file_path!r}")
        print(f"Data read size per iteration: {READ_SIZE / 1024 ** 2:.2f} MB")
        print("\nStarting memory leak test (50 iterations)...")

        # 2. Wrap the leak trigger with the memory profiler
        with profile_memory(label="gRPC Channel Leak Test"):
            trigger_memleak(file_path)

        print("\nTemporary file removed.")

if __name__ == '__main__':
    main()
