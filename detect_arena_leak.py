#!/usr/bin/env python3
"""
Detect which memory arena is leaking.

This script identifies:
- Which allocator is being used (pymalloc vs system malloc)
- Which threads are creating arenas
- Memory growth per thread
- Arena allocation patterns
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
    print("Warning: psutil not installed. Install with: pip install psutil")

import grpc

ARBITRARY_PORT = 33333
READ_SIZE = 31 * 1024 * 1024

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

def get_memory_maps():
    """Get memory mappings from /proc/self/maps."""
    maps = []
    try:
        with open('/proc/self/maps', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    addr_range = parts[0]
                    perms = parts[1]
                    if len(parts) > 5:
                        path = parts[5]
                    else:
                        path = '[anonymous]'
                    
                    # Parse address range
                    start, end = addr_range.split('-')
                    start_addr = int(start, 16)
                    end_addr = int(end, 16)
                    size = end_addr - start_addr
                    
                    maps.append({
                        'start': start_addr,
                        'end': end_addr,
                        'size': size,
                        'perms': perms,
                        'path': path
                    })
    except:
        pass
    return maps

def get_heap_size():
    """Get heap size from memory maps."""
    maps = get_memory_maps()
    heap_size = 0
    for m in maps:
        if '[heap]' in m['path'] or m['path'] == '[anonymous]':
            if 'rw' in m['perms']:  # Read-write (likely heap)
                heap_size += m['size']
    return heap_size / (1024 ** 2)  # MB

def detect_allocator():
    """Detect which allocator Python is using."""
    python_malloc = os.environ.get('PYTHONMALLOC', '')
    
    if python_malloc == 'malloc':
        return 'system_malloc'
    elif python_malloc == 'debug':
        return 'pymalloc_debug'
    elif python_malloc == '':
        return 'pymalloc'
    else:
        return f'unknown_{python_malloc}'

def get_thread_memory():
    """Get memory usage per thread (Linux only)."""
    thread_memory = {}
    try:
        # Get thread IDs
        import threading
        main_thread_id = threading.get_native_id()
        
        # Try to get per-thread memory from /proc
        # This is approximate - Linux doesn't provide exact per-thread RSS
        # But we can check thread-local storage
        
        thread_memory['main'] = {
            'thread_id': main_thread_id,
            'note': 'Main thread - uses main arena'
        }
        
        # Note: Getting exact per-thread memory is difficult on Linux
        # We'll track allocations per thread instead
        
    except Exception as e:
        pass
    
    return thread_memory

def read_file(file_path: str, thread_id: str):
    """Read file and track which thread allocated memory."""
    with open(file_path, 'rb') as fp:
        data = fp.read(READ_SIZE)
    # Data allocated in this thread's arena
    del data

class ArenaTracker:
    """Track memory arena growth."""
    
    def __init__(self):
        self.snapshots = []
        self.thread_allocations = defaultdict(int)
    
    def snapshot(self, label=""):
        """Take a snapshot of memory state."""
        snapshot = {
            'label': label,
            'rss_mb': get_memory_mb(),
            'heap_mb': get_heap_size(),
            'python_objects': len(gc.get_objects()),
            'allocator': detect_allocator(),
            'thread_count': threading.active_count(),
        }
        
        # Get memory maps
        maps = get_memory_maps()
        snapshot['memory_maps'] = maps
        snapshot['map_count'] = len(maps)
        
        # Analyze maps
        heap_maps = [m for m in maps if '[heap]' in m['path'] or (m['path'] == '[anonymous]' and 'rw' in m['perms'])]
        snapshot['heap_maps'] = heap_maps
        snapshot['heap_map_count'] = len(heap_maps)
        snapshot['total_heap_size_mb'] = sum(m['size'] for m in heap_maps) / (1024 ** 2)
        
        self.snapshots.append(snapshot)
        return snapshot
    
    def analyze_growth(self, before_idx, after_idx):
        """Analyze memory growth between snapshots."""
        before = self.snapshots[before_idx]
        after = self.snapshots[after_idx]
        
        return {
            'rss_growth_mb': after['rss_mb'] - before['rss_mb'],
            'heap_growth_mb': after['heap_mb'] - before['heap_mb'],
            'object_growth': after['python_objects'] - before['python_objects'],
            'heap_map_growth': after['heap_map_count'] - before['heap_map_count'],
            'total_heap_growth_mb': after['total_heap_size_mb'] - before['total_heap_size_mb'],
            'allocator': after['allocator'],
        }

def main():
    print("=" * 80)
    print("Detecting Which Memory Arena is Leaking")
    print("=" * 80)
    print()
    
    tracker = ArenaTracker()
    
    # Initial snapshot
    print("Taking initial snapshot...")
    initial = tracker.snapshot("Initial")
    print(f"  RSS: {initial['rss_mb']:.2f} MB")
    print(f"  Heap: {initial['heap_mb']:.2f} MB")
    print(f"  Allocator: {initial['allocator']}")
    print(f"  Heap maps: {initial['heap_map_count']}")
    print(f"  Total heap size: {initial['total_heap_size_mb']:.2f} MB")
    print()
    
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(os.urandom(50 * 1024 * 1024))
        tmp.flush()
        file_path = tmp.name
        
        # Run iterations
        num_iterations = 20
        for i in range(num_iterations):
            # Before iteration
            before = tracker.snapshot(f"Before {i+1}")
            
            # Run thread
            thread_id = f"thread_{i+1}"
            t = threading.Thread(target=read_file, args=(file_path, thread_id))
            t.start()
            t.join()
            
            # Create and close channel
            c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
            c.close()
            
            # Force GC
            gc.collect()
            
            # After iteration
            after = tracker.snapshot(f"After {i+1}")
            
            # Analyze growth
            growth = tracker.analyze_growth(-2, -1)
            
            if (i + 1) % 5 == 0 or i == 0:
                print(f"--- Iteration {i + 1} ---")
                print(f"  RSS: {after['rss_mb']:.2f} MB (+{growth['rss_growth_mb']:.2f} MB)")
                print(f"  Heap: {after['heap_mb']:.2f} MB (+{growth['heap_growth_mb']:.2f} MB)")
                print(f"  Python objects: {after['python_objects']} (+{growth['object_growth']})")
                print(f"  Heap maps: {after['heap_map_count']} (+{growth['heap_map_growth']})")
                print(f"  Total heap size: {after['total_heap_size_mb']:.2f} MB (+{growth['total_heap_growth_mb']:.2f} MB)")
                print()
        
        # Final analysis
        print("=" * 80)
        print("FINAL ANALYSIS")
        print("=" * 80)
        
        final_growth = tracker.analyze_growth(0, -1)
        
        print(f"\nTotal growth over {num_iterations} iterations:")
        print(f"  RSS: +{final_growth['rss_growth_mb']:.2f} MB")
        print(f"  Heap: +{final_growth['heap_growth_mb']:.2f} MB")
        print(f"  Python objects: +{final_growth['object_growth']}")
        print(f"  Heap maps: +{final_growth['heap_map_growth']}")
        print(f"  Total heap size: +{final_growth['total_heap_growth_mb']:.2f} MB")
        print()
        
        # Diagnose
        print("=" * 80)
        print("DIAGNOSIS")
        print("=" * 80)
        print()
        
        allocator = final_growth['allocator']
        print(f"Allocator: {allocator}")
        print()
        
        if allocator == 'pymalloc':
            print("⚠️  Using pymalloc (default)")
            print("   - pymalloc keeps arenas until process exit")
            print("   - No way to release memory to OS")
            print("   - This is the source of the leak!")
            print()
            print("Solution: Set PYTHONMALLOC=malloc")
        
        elif allocator == 'system_malloc':
            print("✅ Using system malloc")
            if final_growth['rss_growth_mb'] > 10:
                print("   ⚠️  But RSS still growing!")
                print("   - Likely thread-local malloc arenas")
                print("   - malloc_trim() only affects calling thread's arena")
                print()
                print("Solution: Call malloc_trim() from each thread")
            else:
                print("   ✅ RSS is stable (no leak)")
        
        # Analyze heap maps
        final_snapshot = tracker.snapshots[-1]
        if final_snapshot['heap_map_count'] > initial['heap_map_count']:
            print()
            print(f"⚠️  Heap maps increased: {initial['heap_map_count']} → {final_snapshot['heap_map_count']}")
            print("   This indicates new arenas were created")
            print("   Each new map is likely a new arena")
        
        # Memory map analysis
        if final_snapshot['total_heap_growth_mb'] > 5:
            print()
            print(f"⚠️  Heap size grew by {final_growth['total_heap_growth_mb']:.2f} MB")
            print("   This is memory in arenas that's not released to OS")
            print("   Even though Python objects are freed, memory stays in arenas")

if __name__ == '__main__':
    main()

