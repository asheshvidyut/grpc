#!/usr/bin/env python3
"""
Detect which Python objects are actually leaking.
This tracks Python objects, not just memory arenas.
"""

import os
import sys
import tempfile
import threading
import gc
import weakref
from collections import defaultdict
import tracemalloc

import grpc

ARBITRARY_PORT = 33333
READ_SIZE = 31 * 1024 * 1024 

class LeakDetector:
    """Detect leaking Python objects."""
    
    def __init__(self):
        self.snapshots = []
        self.tracked_channels = {}  # id -> weakref
    
    def snapshot(self, label=""):
        """Take a snapshot of all objects."""
        snapshot = {
            'label': label,
            'objects_by_type': defaultdict(list),
            'grpc_objects': [],
            'object_ids': set(),
            'refcounts': {}
        }
        
        # Force GC to get accurate counts
        gc.collect()
        
        # Get all objects
        for obj in gc.get_objects():
            obj_id = id(obj)
            obj_type = type(obj)
            type_name = obj_type.__name__
            module = getattr(obj_type, '__module__', '')
            module_str = str(module) if module else ''
            
            snapshot['object_ids'].add(obj_id)
            snapshot['objects_by_type'][type_name].append(obj_id)
            
            # Track gRPC objects specifically
            if 'grpc' in module_str.lower() or 'grpc' in type_name.lower():
                try:
                    refcount = sys.getrefcount(obj) - 1  # -1 for the getrefcount call itself
                    snapshot['grpc_objects'].append({
                        'id': obj_id,
                        'type': type_name,
                        'module': module_str,
                        'refcount': refcount,
                        'repr': repr(obj)[:150]
                    })
                    snapshot['refcounts'][obj_id] = refcount
                except:
                    pass
        
        self.snapshots.append(snapshot)
        return snapshot
    
    def track_channel(self, channel, label=""):
        """Track a specific channel object."""
        channel_id = id(channel)
        self.tracked_channels[channel_id] = {
            'weakref': weakref.ref(channel),
            'label': label,
            'created_at': len(self.snapshots)
        }
    
    def find_leaking_objects(self, before_idx, after_idx):
        """Find objects that leaked between snapshots."""
        before = self.snapshots[before_idx]
        after = self.snapshots[after_idx]
        
        # Objects that exist in 'after' but not in 'before'
        new_object_ids = after['object_ids'] - before['object_ids']
        
        # Find new objects by type
        new_by_type = defaultdict(list)
        for obj_id in new_object_ids:
            # Find which type this object is
            for type_name, obj_ids in after['objects_by_type'].items():
                if obj_id in obj_ids:
                    new_by_type[type_name].append(obj_id)
                    break
        
        # Find new gRPC objects
        before_grpc_ids = {obj['id'] for obj in before['grpc_objects']}
        after_grpc_ids = {obj['id'] for obj in after['grpc_objects']}
        new_grpc_ids = after_grpc_ids - before_grpc_ids
        
        new_grpc_objects = [obj for obj in after['grpc_objects'] 
                           if obj['id'] in new_grpc_ids]
        
        # Check tracked channels
        leaked_channels = []
        for channel_id, info in self.tracked_channels.items():
            weak_ref = info['weakref']
            if weak_ref() is not None:  # Object still exists
                if channel_id in after['object_ids']:
                    leaked_channels.append({
                        'id': channel_id,
                        'label': info['label'],
                        'refcount': after['refcounts'].get(channel_id, 'unknown'),
                        'created_at': info['created_at']
                    })
        
        return {
            'new_objects_by_type': dict(new_by_type),
            'new_grpc_objects': new_grpc_objects,
            'leaked_channels': leaked_channels,
            'total_new_objects': len(new_object_ids)
        }

def read_file(file_path: str):
    """Reads a large chunk of data from the file."""
    with open(file_path, 'rb') as fp:
        data = fp.read(READ_SIZE)
    # Don't keep reference to data
    del data

def analyze_references(obj_id, snapshot):
    """Find what references a specific object."""
    # This is tricky - we need to find the actual object
    for obj in gc.get_objects():
        if id(obj) == obj_id:
            referrers = gc.get_referrers(obj)
            ref_info = []
            for ref in referrers:
                if ref is not obj:  # Don't count self-reference
                    ref_type = type(ref).__name__
                    ref_module = getattr(type(ref), '__module__', '')
                    ref_info.append({
                        'type': ref_type,
                        'module': ref_module,
                        'id': id(ref)
                    })
            return ref_info[:10]  # Limit to first 10
    return []

def main():
    """Main analysis."""
    print("=" * 80)
    print("DETECTING LEAKING PYTHON OBJECTS")
    print("=" * 80)
    print()
    print("This will identify which Python objects are actually leaking,")
    print("independent of malloc_trim or PYTHONMALLOC settings.")
    print()
    
    detector = LeakDetector()
    
    # Create temp file
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(os.urandom(50 * 1024 * 1024))
        tmp.flush()
        file_path = tmp.name
        
        # Initial snapshot
        print("Taking initial snapshot...")
        detector.snapshot("Initial")
        initial_grpc_count = len(detector.snapshots[0]['grpc_objects'])
        print(f"  Initial gRPC objects: {initial_grpc_count}")
        print()
        
        # Run iterations
        num_iterations = 50
        for i in range(num_iterations):
            print(f"--- Iteration {i + 1}/{num_iterations} ---")
            
            # Before iteration
            before_snapshot = detector.snapshot(f"Before {i+1}")
            
            # Run thread
            t = threading.Thread(target=read_file, kwargs=dict(file_path=file_path))
            t.start()
            t.join()
            
            # Create channel and track it
            c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
            channel_id = id(c)
            channel_type = type(c).__name__
            detector.track_channel(c, f"Channel iteration {i+1}")
            
            # Close channel
            c.close()
            
            # Force GC
            gc.collect()
            
            # After iteration
            after_snapshot = detector.snapshot(f"After {i+1}")
            
            # Analyze
            leak_info = detector.find_leaking_objects(-2, -1)
            
            # Only print detailed info every 10 iterations or if there's a leak
            should_print_details = (i + 1) % 10 == 0 or leak_info['leaked_channels'] or len(leak_info['new_grpc_objects']) > 0
            
            if should_print_details:
                print(f"  New objects created: {leak_info['total_new_objects']}")
                print(f"  New gRPC objects: {len(leak_info['new_grpc_objects'])}")
            
            if leak_info['new_grpc_objects'] and should_print_details:
                print(f"  New gRPC object types:")
                by_type = defaultdict(list)
                for obj in leak_info['new_grpc_objects']:
                    by_type[obj['type']].append(obj)
                
                for obj_type, objs in sorted(by_type.items(), key=lambda x: -len(x[1])):
                    print(f"    {obj_type}: +{len(objs)} objects")
                    # Show details of first few
                    for obj in objs[:2]:
                        print(f"      - id={obj['id']}, refcount={obj['refcount']}, "
                              f"repr={obj['repr'][:80]}")
            
            # Check if channel leaked (always print if leaked)
            if leak_info['leaked_channels']:
                print(f"  ⚠️  LEAKED CHANNELS:")
                for chan in leak_info['leaked_channels']:
                    print(f"    Channel {chan['id']}: refcount={chan['refcount']}, "
                          f"created at snapshot {chan['created_at']}")
                    # Analyze references
                    refs = analyze_references(chan['id'], after_snapshot)
                    if refs:
                        print(f"      Referenced by {len(refs)} objects:")
                        ref_types = defaultdict(int)
                        for ref in refs:
                            ref_types[ref['type']] += 1
                        for ref_type, count in sorted(ref_types.items(), key=lambda x: -x[1])[:5]:
                            print(f"        {ref_type}: {count}")
            
            # Show top object growth (only every 10 iterations)
            if leak_info['new_objects_by_type'] and should_print_details:
                print(f"  Top object type growth:")
                for obj_type, obj_ids in sorted(leak_info['new_objects_by_type'].items(), 
                                               key=lambda x: -len(x[1]))[:5]:
                    print(f"    {obj_type}: +{len(obj_ids)}")
            
            if should_print_details:
                print()
            elif (i + 1) % 10 == 0:
                print(f"  Progress: {i+1}/{num_iterations} iterations completed")
                print()
        
        # Final analysis
        print("=" * 80)
        print("FINAL ANALYSIS")
        print("=" * 80)
        
        final_leak = detector.find_leaking_objects(0, -1)
        
        print(f"\nTotal new objects: {final_leak['total_new_objects']}")
        print(f"Total new gRPC objects: {len(final_leak['new_grpc_objects'])}")
        
        if final_leak['new_grpc_objects']:
            print(f"\nAll new gRPC objects by type:")
            by_type = defaultdict(list)
            for obj in final_leak['new_grpc_objects']:
                by_type[obj['type']].append(obj)
            
            for obj_type, objs in sorted(by_type.items(), key=lambda x: -len(x[1])):
                print(f"\n  {obj_type}: {len(objs)} objects")
                # Show all instances
                for obj in objs:
                    print(f"    - id={obj['id']}, refcount={obj['refcount']}")
                    print(f"      {obj['repr'][:100]}")
        
        if final_leak['leaked_channels']:
            print(f"\n⚠️  LEAKED CHANNELS (should be freed but aren't):")
            for chan in final_leak['leaked_channels']:
                print(f"  Channel id={chan['id']}, refcount={chan['refcount']}")
                print(f"    Created at: {chan['label']}")
                # This is a REAL leak - object should be freed but isn't!
        
        # Check tracked channels
        print(f"\nTracked channels status:")
        for channel_id, info in detector.tracked_channels.items():
            weak_ref = info['weakref']
            if weak_ref() is not None:
                print(f"  ⚠️  Channel {channel_id} ({info['label']}) still exists!")
            else:
                print(f"  ✅ Channel {channel_id} ({info['label']}) was freed")

if __name__ == '__main__':
    main()

