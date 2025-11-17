#!/usr/bin/env python3
"""
Find what's referencing leaked Channel objects.
"""

import gc
import sys
import tempfile
import threading
import grpc

ARBITRARY_PORT = 33333
READ_SIZE = 31 * 1024 * 1024

def read_file(file_path: str):
    with open(file_path, 'rb') as fp:
        fp.read(READ_SIZE)

def find_referrers(obj, max_depth=3, visited=None):
    """Find all referrers of an object, with depth limit."""
    if visited is None:
        visited = set()
    
    obj_id = id(obj)
    if obj_id in visited:
        return []
    
    visited.add(obj_id)
    referrers = gc.get_referrers(obj)
    
    result = []
    for ref in referrers:
        if ref is obj:
            continue
        
        ref_type = type(ref).__name__
        ref_module = getattr(type(ref), '__module__', '')
        ref_id = id(ref)
        
        info = {
            'id': ref_id,
            'type': ref_type,
            'module': str(ref_module),
            'repr': repr(ref)[:150]
        }
        
        # Try to get more info about lists/dicts
        if isinstance(ref, (list, tuple)):
            info['length'] = len(ref)
            info['contains'] = [type(item).__name__ for item in ref[:5]]
        elif isinstance(ref, dict):
            info['keys'] = list(ref.keys())[:5]
        
        result.append(info)
        
        # Recursively find referrers of referrers (limited depth)
        if max_depth > 0:
            nested = find_referrers(ref, max_depth - 1, visited)
            for n in nested:
                n['depth'] = n.get('depth', 0) + 1
                result.append(n)
    
    return result

def main():
    print("=" * 80)
    print("Finding Channel Object References")
    print("=" * 80)
    print()
    
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(b'x' * (50 * 1024 * 1024))
        tmp.flush()
        file_path = tmp.name
        
        # Run a few iterations
        channels = []
        for i in range(3):
            print(f"--- Iteration {i + 1} ---")
            
            # Thread
            t = threading.Thread(target=read_file, kwargs=dict(file_path=file_path))
            t.start()
            t.join()
            
            # Create and close channel
            c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
            channel_id = id(c)
            channels.append((i, channel_id, c))
            c.close()
            
            # Force GC
            import gc
            gc.collect()
            
            # Check if channel still exists
            channel_still_exists = any(id(obj) == channel_id for obj in gc.get_objects())
            if channel_still_exists:
                print(f"  ⚠️  Channel {channel_id} still exists after close()")
                
                # Find the actual object
                for obj in gc.get_objects():
                    if id(obj) == channel_id:
                        print(f"  Object: {type(obj).__name__}")
                        print(f"  Refcount: {sys.getrefcount(obj) - 1}")
                        print()
                        
                        # Find referrers
                        print("  Referrers:")
                        referrers = find_referrers(obj, max_depth=2)
                        
                        # Group by type
                        by_type = {}
                        for ref in referrers:
                            ref_type = ref['type']
                            if ref_type not in by_type:
                                by_type[ref_type] = []
                            by_type[ref_type].append(ref)
                        
                        # Show referrers
                        for ref_type, refs in sorted(by_type.items(), key=lambda x: -len(x[1])):
                            print(f"    {ref_type}: {len(refs)} reference(s)")
                            for ref in refs[:3]:  # Show first 3
                                depth_indent = "  " * (ref.get('depth', 0) + 1)
                                print(f"      {depth_indent}id={ref['id']}, module={ref['module']}")
                                if 'length' in ref:
                                    print(f"      {depth_indent}length={ref['length']}, contains={ref.get('contains', [])}")
                                if 'keys' in ref:
                                    print(f"      {depth_indent}keys={ref['keys']}")
                                print(f"      {depth_indent}repr={ref['repr'][:100]}")
            else:
                print(f"  ✅ Channel {channel_id} was freed")
            print()
        
        # Final check
        print("=" * 80)
        print("FINAL STATUS")
        print("=" * 80)
        for i, channel_id, channel_obj in channels:
            still_exists = any(id(obj) == channel_id for obj in gc.get_objects())
            if still_exists:
                print(f"  ⚠️  Channel {i} (id={channel_id}) still exists")
                
                # Find what's holding it
                for obj in gc.get_objects():
                    if id(obj) == channel_id:
                        referrers = gc.get_referrers(obj)
                        print(f"    Referenced by {len(referrers)} objects:")
                        for ref in referrers[:5]:
                            if ref is not obj:
                                print(f"      - {type(ref).__name__}: {repr(ref)[:100]}")
            else:
                print(f"  ✅ Channel {i} (id={channel_id}) was freed")

if __name__ == '__main__':
    main()

