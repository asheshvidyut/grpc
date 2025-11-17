#!/usr/bin/env python3
"""
Detect thread-local malloc arenas on Linux.

Uses glibc's mallinfo2() to detect arena usage per thread.
"""

import os
import sys
import tempfile
import threading
import gc
import ctypes
from collections import defaultdict

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

import grpc

ARBITRARY_PORT = 33333
READ_SIZE = 31 * 1024 * 1024

# glibc mallinfo2 structure (simplified)
class MallInfo2(ctypes.Structure):
    _fields_ = [
        ("arena", ctypes.c_size_t),      # Non-mmapped space allocated
        ("ordblks", ctypes.c_size_t),    # Number of free chunks
        ("smblks", ctypes.c_size_t),     # Number of fastbin blocks
        ("hblks", ctypes.c_size_t),      # Number of mmapped regions
        ("hblkhd", ctypes.c_size_t),     # Space allocated in mmapped regions
        ("usmblks", ctypes.c_size_t),    # Maximum total allocated space
        ("fsmblks", ctypes.c_size_t),    # Space in fastbin blocks
        ("uordblks", ctypes.c_size_t),   # Total allocated space
        ("fordblks", ctypes.c_size_t),   # Total free space
        ("keepcost", ctypes.c_size_t),   # Top-most, releasable space
    ]

def get_mallinfo2():
    """Get malloc info from glibc (Linux only)."""
    if sys.platform != 'linux':
        return None
    
    try:
        libc = ctypes.CDLL('libc.so.6')
        if hasattr(libc, 'mallinfo2'):
            libc.mallinfo2.argtypes = []
            libc.mallinfo2.restype = MallInfo2
            info = libc.mallinfo2()
            return {
                'arena': info.arena / (1024 ** 2),  # MB
                'uordblks': info.uordblks / (1024 ** 2),  # MB (used)
                'fordblks': info.fordblks / (1024 ** 2),  # MB (free)
                'keepcost': info.keepcost / (1024 ** 2),  # MB (releasable)
                'hblkhd': info.hblkhd / (1024 ** 2),  # MB (mmapped)
            }
    except:
        pass
    return None

def get_memory_mb():
    """Get current process memory usage in MB."""
    if HAS_PSUTIL:
        return psutil.Process(os.getpid()).memory_info().rss / 1024 ** 2
    else:
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        return int(line.split()[1]) / 1024
        except:
            return 0

def read_file(file_path: str, results_dict: dict, thread_name: str):
    """Read file and capture malloc info for this thread."""
    # Get malloc info before
    before = get_mallinfo2()
    
    with open(file_path, 'rb') as fp:
        data = fp.read(READ_SIZE)
    
    # Get malloc info after
    after = get_mallinfo2()
    
    if before and after:
        results_dict[thread_name] = {
            'before': before,
            'after': after,
            'growth': {
                'arena': after['arena'] - before['arena'],
                'uordblks': after['uordblks'] - before['uordblks'],
                'fordblks': after['fordblks'] - before['fordblks'],
            }
        }
    
    del data

def main():
    print("=" * 80)
    print("Detecting Thread-Local Malloc Arenas")
    print("=" * 80)
    print()
    
    if sys.platform != 'linux':
        print("⚠️  This script only works on Linux with glibc")
        return
    
    # Check if mallinfo2 is available
    mallinfo = get_mallinfo2()
    if not mallinfo:
        print("⚠️  mallinfo2() not available (might not be glibc or too old)")
        print("   This script requires glibc 2.33+")
        return
    
    print("Initial malloc info:")
    print(f"  Arena: {mallinfo['arena']:.2f} MB")
    print(f"  Used: {mallinfo['uordblks']:.2f} MB")
    print(f"  Free: {mallinfo['fordblks']:.2f} MB")
    print(f"  Releasable: {mallinfo['keepcost']:.2f} MB")
    print()
    
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(os.urandom(50 * 1024 * 1024))
        tmp.flush()
        file_path = tmp.name
        
        # Track per-thread allocations
        thread_results = {}
        
        # Run iterations
        num_iterations = 10
        initial_rss = get_memory_mb()
        initial_mallinfo = get_mallinfo2()
        
        for i in range(num_iterations):
            # Create and close channel
            c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
            c.close()
            
            # Run thread
            thread_name = f"thread_{i+1}"
            t = threading.Thread(target=read_file, args=(file_path, thread_results, thread_name))
            t.start()
            t.join()
            
            # Force GC
            gc.collect()
            
            if (i + 1) % 5 == 0:
                current_rss = get_memory_mb()
                current_mallinfo = get_mallinfo2()
                
                if current_mallinfo:
                    print(f"--- After {i+1} iterations ---")
                    print(f"  RSS: {current_rss:.2f} MB (+{current_rss - initial_rss:.2f} MB)")
                    print(f"  Arena: {current_mallinfo['arena']:.2f} MB (+{current_mallinfo['arena'] - initial_mallinfo['arena']:.2f} MB)")
                    print(f"  Used: {current_mallinfo['uordblks']:.2f} MB (+{current_mallinfo['uordblks'] - initial_mallinfo['uordblks']:.2f} MB)")
                    print(f"  Free: {current_mallinfo['fordblks']:.2f} MB (+{current_mallinfo['fordblks'] - initial_mallinfo['fordblks']:.2f} MB)")
                    print(f"  Releasable: {current_mallinfo['keepcost']:.2f} MB")
                    print()
        
        # Final analysis
        print("=" * 80)
        print("FINAL ANALYSIS")
        print("=" * 80)
        
        final_rss = get_memory_mb()
        final_mallinfo = get_mallinfo2()
        
        if final_mallinfo:
            print(f"\nRSS growth: {final_rss - initial_rss:.2f} MB")
            print(f"Arena growth: {final_mallinfo['arena'] - initial_mallinfo['arena']:.2f} MB")
            print(f"Used growth: {final_mallinfo['uordblks'] - initial_mallinfo['uordblks']:.2f} MB")
            print(f"Free growth: {final_mallinfo['fordblks'] - initial_mallinfo['fordblks']:.2f} MB")
            print(f"Releasable: {final_mallinfo['keepcost']:.2f} MB")
            print()
            
            # Diagnose
            if final_mallinfo['keepcost'] > 1:
                print(f"⚠️  {final_mallinfo['keepcost']:.2f} MB is releasable but not released!")
                print("   This is memory that malloc_trim() could release")
                print("   But it's in thread-local arenas, so main thread can't trim it")
            
            if final_mallinfo['fordblks'] > 10:
                print(f"⚠️  {final_mallinfo['fordblks']:.2f} MB is free but not released to OS")
                print("   This is memory in arenas that's not being trimmed")
        
        # Per-thread analysis
        if thread_results:
            print()
            print("Per-thread allocations:")
            for thread_name, result in list(thread_results.items())[:5]:  # Show first 5
                growth = result['growth']
                print(f"  {thread_name}:")
                print(f"    Arena growth: {growth['arena']:.2f} MB")
                print(f"    Used growth: {growth['uordblks']:.2f} MB")
                print(f"    Free growth: {growth['fordblks']:.2f} MB")

if __name__ == '__main__':
    main()

