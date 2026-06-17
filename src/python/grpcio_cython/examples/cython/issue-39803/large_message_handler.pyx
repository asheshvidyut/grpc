# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# High-performance JIT handler written strictly in clean Cython.
# 100% pure native C++ business logic service class!

# distutils: language = c++

# Dynamic compiled GIL-free business logic C++ class
cdef cppclass LargeMessageService:
    int process_large_message(LargeMessageRequest* req, LargeMessageResponse* resp) nogil:
        cdef int size = req.values_size()
        cdef float total = 0.0
        cdef int i
        for i in range(size):
            total += req.values(i)
            
        resp.set_status("ok")
        return 0
