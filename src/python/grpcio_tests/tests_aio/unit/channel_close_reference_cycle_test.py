import asyncio
import gc
import weakref
import unittest
from grpc.aio import insecure_channel

class TestStrongReferenceCycle(unittest.IsolatedAsyncioTestCase):
    async def test_call_creates_strong_reference_cycle(self):
        # We disable cyclic garbage collector to observe whether objects 
        # are freed by pure reference counting.
        gc.disable()
        
        channel = insecure_channel('localhost:50051')
        call = channel.unary_unary('/foo/bar')(b'data')
        
        # Keep a weak reference to the call
        call_ref = weakref.ref(call)
        
        # Drop our strong reference
        del call
        
        # The call should ideally be freed instantly by refcounting.
        # But because `channel._register_call` calls `add_done_callback(discard)`,
        # the `_call.py` wrapper does `cb = functools.partial(callback, self)`
        # and passes `cb` to Cython. This creates a cycle:
        # self -> self._cython_call -> _done_callbacks -> cb -> self
        
        self.assertIsNotNone(
            call_ref(), 
            "The Call object leaked! It formed a strong reference cycle and was NOT freed by refcounting!"
        )
        
        # Verify that cyclic GC can eventually clean it up
        gc.collect()
        self.assertIsNone(
            call_ref(),
            "The Call object is permanently leaked!"
        )
        
        gc.enable()

if __name__ == '__main__':
    unittest.main()
