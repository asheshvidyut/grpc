#!/usr/bin/env python3
"""
Analyze what's holding Channel objects after close().
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

def find_what_holds_channel(channel_obj):
    """Find what's holding a channel object."""
    channel_id = id(channel_obj)
    referrers = gc.get_referrers(channel_obj)
    
    print(f"Channel {channel_id} is referenced by {len(referrers)} objects:")
    
    for ref in referrers:
        if ref is channel_obj:
            continue
        
        ref_type = type(ref).__name__
        ref_module = getattr(type(ref), '__module__', '')
        ref_id = id(ref)
        
        print(f"\n  Reference {ref_id}:")
        print(f"    Type: {ref_type}")
        print(f"    Module: {ref_module}")
        
        # Special handling for common types
        if isinstance(ref, list):
            print(f"    List length: {len(ref)}")
            print(f"    Contains channel at index: {[i for i, item in enumerate(ref) if id(item) == channel_id]}")
            print(f"    First few items: {[type(item).__name__ for item in ref[:5]]}")
        
        elif isinstance(ref, dict):
            print(f"    Dict size: {len(ref)}")
            # Find which key maps to channel
            for key, value in ref.items():
                if id(value) == channel_id:
                    print(f"    Channel stored at key: {key}")
            print(f"    Keys: {list(ref.keys())[:10]}")
        
        elif isinstance(ref, tuple):
            print(f"    Tuple length: {len(ref)}")
            print(f"    Contains channel at index: {[i for i, item in enumerate(ref) if id(item) == channel_id]}")
        
        elif hasattr(ref, '__dict__'):
            print(f"    Has __dict__: {list(ref.__dict__.keys())[:10]}")
            # Check if channel is in __dict__
            for key, value in ref.__dict__.items():
                if id(value) == channel_id:
                    print(f"    Channel stored in attribute: {key}")
        
        print(f"    Repr: {repr(ref)[:150]}")
        
        # Check if this ref is also referenced (find the chain)
        ref_referrers = gc.get_referrers(ref)
        if ref_referrers:
            print(f"    This reference is held by {len(ref_referrers)} objects:")
            for ref_ref in ref_referrers[:3]:
                if ref_ref is not ref and ref_ref is not channel_obj:
                    print(f"      - {type(ref_ref).__name__}: {repr(ref_ref)[:80]}")

def main():
    print("=" * 80)
    print("Channel Leak Analysis")
    print("=" * 80)
    print()
    
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(b'x' * (50 * 1024 * 1024))
        tmp.flush()
        file_path = tmp.name
        
        channels_created = []
        
        # Run 5 iterations
        for i in range(5):
            print(f"--- Iteration {i + 1} ---")
            
            # Thread
            t = threading.Thread(target=read_file, kwargs=dict(file_path=file_path))
            t.start()
            t.join()
            
            # Create channel
            c = grpc.secure_channel(f"localhost:{ARBITRARY_PORT}", grpc.local_channel_credentials())
            channel_id = id(c)
            channels_created.append((i, channel_id, c))
            print(f"  Created channel: {channel_id}")
            
            # Close channel
            c.close()
            print(f"  Closed channel: {channel_id}")
            
            # Force GC
            gc.collect()
            
            # Check if still exists
            still_exists = any(id(obj) == channel_id for obj in gc.get_objects())
            if still_exists:
                print(f"  ⚠️  Channel {channel_id} still exists!")
                # Find it
                for obj in gc.get_objects():
                    if id(obj) == channel_id:
                        print(f"  Refcount: {sys.getrefcount(obj) - 1}")
                        find_what_holds_channel(obj)
            else:
                print(f"  ✅ Channel {channel_id} was freed")
            print()
        
        # Final check
        print("=" * 80)
        print("FINAL STATUS")
        print("=" * 80)
        
        for i, channel_id, channel_obj in channels_created:
            still_exists = any(id(obj) == channel_id for obj in gc.get_objects())
            if still_exists:
                print(f"\n⚠️  Channel {i} (id={channel_id}) still exists:")
                for obj in gc.get_objects():
                    if id(obj) == channel_id:
                        find_what_holds_channel(obj)
            else:
                print(f"✅ Channel {i} (id={channel_id}) was freed")
        
        # Check for ChannelCache
        print("\n" + "=" * 80)
        print("Checking for ChannelCache")
        print("=" * 80)
        try:
            from grpc import _simple_stubs
            cache = _simple_stubs.ChannelCache.get()
            print(f"ChannelCache exists: {cache}")
            if hasattr(cache, '_mapping'):
                print(f"  Cache size: {len(cache._mapping)}")
                print(f"  Cached channels: {list(cache._mapping.keys())[:5]}")
        except Exception as e:
            print(f"Could not access ChannelCache: {e}")

if __name__ == '__main__':
    main()

