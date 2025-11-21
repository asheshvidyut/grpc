import threading
import contextlib
import contextlib
import os
import tempfile
import threading
import time
import psutil
import gc
import sys
import grpc
import tempfile
# --- Configuration Constants ---

ARBITRARY_PORT = 33333
# Total size of the temporary file (50 MB)
ARBITRARY_FILE_SIZE = 50 * 1024 * 1024 
# The amount of data read by read_file (31 MB)
READ_SIZE = 31 * 1024 * 1024 

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

def read_file(file_path: str):
  """Reads a large chunk of data from the file."""
  try:
    with open(file_path, 'rb') as f:
        f.read(READ_SIZE)

    # Fix for issue #40817: Trim this thread's memory arena after I/O
    # This releases memory allocated in this thread's arena back to the OS.
    # Using the new grpc.trim_thread_memory() helper function.
    # grpc.trim_thread_memory()
  except FileNotFoundError:
    print(f"Error: File '{file_path}' not found.", file=sys.stderr)
    sys.exit(1)
def trigger_mem(file_path):
    initial_rss = get_current_rss_mb()
    for _ in range(50):
        t = threading.Thread(target=read_file, kwargs=dict(file_path=file_path))
        t.start()
        t.join()
        c = grpc.secure_channel(f"localhost:{4000}", grpc.local_channel_credentials())
        c.close()
        current_rss = get_current_rss_mb()
        diff_from_start = current_rss - initial_rss
        
        print(
            f"Iteration {_ + 1}/50: "
            f"Current RSS: {current_rss:.2f} MB | "
            f"Total increase: +{diff_from_start:.2f} MB"
        )
        time.sleep(0.1)

if __name__ == "__main__":
    with temporary_urandom_file(ARBITRARY_FILE_SIZE) as file_path:
        trigger_mem(file_path)
