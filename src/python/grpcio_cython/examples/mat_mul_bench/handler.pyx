# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# High-performance JIT handlers written strictly in clean Cython.
# 100% pure native C++ business logic service class!

# distutils: language = c++

# Dynamic compiled GIL-free business logic C++ class
cdef cppclass MatMulService:
    int cython_matmul(MatMulRequest* req, MatMulResponse* resp) nogil:
        cdef int n = req.n()
        cdef const float* a = req.a().data()
        cdef const float* b = req.b().data()
        
        cdef int i, j, k
        cdef float sum_val
        for i in range(n):
            for j in range(n):
                sum_val = 0.0
                for k in range(n):
                    sum_val += a[i * n + k] * b[k * n + j]
                resp.add_c(sum_val)
                
        return 0
