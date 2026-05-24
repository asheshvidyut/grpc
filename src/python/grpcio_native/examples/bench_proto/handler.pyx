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

from libc.stdint cimport uint8_t, uint32_t, uint64_t
from libc.stdint cimport uint32_t as uint32, uint64_t as uint64
from libcpp.string cimport string
from libcpp.string cimport string as bytes

cdef uint64_t FNV_OFFSET = 14695981039346656037ULL
cdef uint64_t FNV_PRIME = 1099511628211ULL

cdef cppclass BenchService:
    int cython_hash(HashRequest* req, HashResponse* resp) nogil:
        cdef uint32_t iterations = req.iterations()
        cdef size_t size = req.data().size()
        cdef const uint8_t* p = <const uint8_t*>req.data().data()
        
        cdef uint64_t h = FNV_OFFSET
        cdef uint32_t it
        cdef size_t i
        cdef uint64_t local
        
        for it in range(iterations):
            local = h
            for i in range(size):
                local = (local ^ p[i]) * FNV_PRIME
            h = local
            
        resp.set_hash(h)
        return 0

    int cython_matmul(MatMulRequest* req, MatMulResponse* resp) nogil:
        cdef uint32_t n = req.n()
        cdef int expected = <int>n * <int>n
        if req.a_size() != expected or req.b_size() != expected:
            return 3 # INVALID_ARGUMENT
            
        cdef int i, j, k
        cdef float sum_val
        for i in range(n):
            for j in range(n):
                sum_val = 0.0
                for k in range(n):
                    sum_val += req.a(i * n + k) * req.b(k * n + j)
                resp.add_c(sum_val)
                
        return 0
