#!/usr/bin/env python3
"""
Verify that the leak is in memory arenas, not Python objects.

This script demonstrates that:
1. Python objects ARE freed (GC works)
2. But memory stays in arenas (RSS grows)
"""

import os
import sys
import tempfile
import threading
import gc

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("Warning: psutil not installed. Install with: pip install psutil")
    sys.exit(1)

import grpc

ARBITRARY_PORT = 33333
READ_SIZE = 31 * 1024 * 1024

def get_memory_mb():
    """Get current process memory usage in MB."""
    return psutil.Process(os.getpid()).memory_info().rss / 1024 ** 2

def count_python_objects():
    """Count Python objects in memory."""
    gc.collect()
    return len(gc.get_objects())

def read_file(file_path: str):
    with open(file_path, 'rb') as fp:
        fp.read(READ_SIZE)

def main():
    print("=" * 80)
    print("Verifying: Leak is in Memory Arenas, Not Python Objects")
    print("=" * 80)
    print()
    
    # Check allocator
    python_malloc = os.environ.get('PYTHONMALLOC', 'pymalloc (default)')
    print(f"Python allocator: {python_malloc}")
    print()
    
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(os.urandom(50 * 1024 * 1024))
        tmp.flush()
        file_path = tmp.name
        
        # Initial state
        initial_rss = get_memory_mb()
        initial_objects = count_python_objects()
        
        print(f"Initial state:")
        print(f"  RSS: {initial_rss:.2f} MB")
        print(f"  Python objects: {initial_objects}")
        print()
        
        # Run iterations
        num_iterations = 50
        channels_created = []
        
        for i in range(num_iterations):
            # Thread
            t = threading.Thread(target=read_file, kwargs=dict(file_path=file_path))
            t.start()
            t.join()
            
            # Create and close channel
            c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
            channels_created.append(id(c))
            c.close()
            
            # Force GC every 10 iterations
            if (i + 1) % 10 == 0:
                gc.collect()
                gc.collect()
                gc.collect()
                
                current_rss = get_memory_mb()
                current_objects = count_python_objects()
                rss_growth = current_rss - initial_rss
                object_growth = current_objects - initial_objects
                
                # Check how many channels still exist
                existing_channels = sum(1 for obj_id in channels_created 
                                       if any(id(obj) == obj_id for obj in gc.get_objects()))
                
                print(f"Iteration {i + 1}:")
                print(f"  RSS: {current_rss:.2f} MB (+{rss_growth:.2f} MB)")
                print(f"  Python objects: {current_objects} (+{object_growth})")
                print(f"  Channels created: {len(channels_created)}")
                print(f"  Channels still exist: {existing_channels}")
                print(f"  Channels freed: {len(channels_created) - existing_channels}")
                
                if rss_growth > 10 and object_growth < 100:
                    print(f"  ⚠️  LEAK DETECTED: RSS grew {rss_growth:.2f} MB but only {object_growth} new objects")
                    print(f"      This means memory is in arenas, not Python objects!")
                print()
        
        # Final state
        print("=" * 80)
        print("FINAL STATE (after all iterations)")
        print("=" * 80)
        
        # Aggressive GC
        for _ in range(5):
            gc.collect()
        
        final_rss = get_memory_mb()
        final_objects = count_python_objects()
        rss_growth = final_rss - initial_rss
        object_growth = final_objects - initial_objects
        
        # Check channels
        existing_channels = sum(1 for obj_id in channels_created 
                               if any(id(obj) == obj_id for obj in gc.get_objects()))
        
        print(f"RSS: {final_rss:.2f} MB (+{rss_growth:.2f} MB)")
        print(f"Python objects: {final_objects} (+{object_growth})")
        print(f"Channels created: {len(channels_created)}")
        print(f"Channels still exist: {existing_channels}")
        print(f"Channels freed: {len(channels_created) - existing_channels}")
        print()
        
        # Analysis
        print("=" * 80)
        print("ANALYSIS")
        print("=" * 80)
        
        if rss_growth > 20:
            print(f"⚠️  RSS grew by {rss_growth:.2f} MB")
        else:
            print(f"✅ RSS grew by only {rss_growth:.2f} MB")
        
        if object_growth < 100:
            print(f"✅ Only {object_growth} new Python objects (objects are being freed)")
        else:
            print(f"⚠️  {object_growth} new Python objects (possible object leak)")
        
        if existing_channels < len(channels_created) * 0.1:  # Less than 10% still exist
            print(f"✅ {len(channels_created) - existing_channels}/{len(channels_created)} channels freed")
            print(f"   Python GC is working correctly!")
        else:
            print(f"⚠️  {existing_channels}/{len(channels_created)} channels still exist")
            print(f"   Possible object leak!")
        
        print()
        
        # Conclusion
        if rss_growth > 20 and object_growth < 100 and existing_channels < len(channels_created) * 0.1:
            print("=" * 80)
            print("CONCLUSION: Leak is in Memory Arenas, NOT Python Objects")
            print("=" * 80)
            print()
            print("Evidence:")
            print(f"  ✅ RSS grew {rss_growth:.2f} MB (memory leak exists)")
            print(f"  ✅ Only {object_growth} new Python objects (objects are freed)")
            print(f"  ✅ {len(channels_created) - existing_channels}/{len(channels_created)} channels freed (GC works)")
            print()
            print("This proves:")
            print("  - Python objects ARE being freed")
            print("  - But memory stays in arenas (pymalloc or glibc malloc)")
            print("  - The leak is in memory arenas, not Python objects")
            print()
            print("Solution:")
            print("  - Use PYTHONMALLOC=malloc (bypass pymalloc)")
            print("  - Call malloc_trim() from threads (release glibc arenas)")

if __name__ == '__main__':
    main()

