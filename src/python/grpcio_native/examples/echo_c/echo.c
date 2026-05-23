/*
 * Copyright 2026 gRPC authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Pure-C example of a grpcio_native unary handler.
 *
 * This handler echoes its request payload back as the response — without ever
 * touching protobuf. It demonstrates the raw ABI: wire bytes in, wire bytes
 * out. A realistic handler would parse the request with protobuf-c or upb
 * and produce a real protobuf response.
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "../../include/grpcio_native/handler.h"

GRPCIO_NATIVE_DECLARE_ABI()

GRPCIO_NATIVE_HANDLER int echo_unary(grpc_native_unary_call* call) {
  if (call->req_len == 0) {
    call->resp_data = NULL;
    call->resp_len = 0;
    return 0;
  }
  call->resp_data = (char*)malloc(call->req_len);
  if (call->resp_data == NULL) {
    call->status = GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED;
    const char* msg = "out of memory";
    size_t n = strlen(msg);
    call->err_msg = (char*)malloc(n);
    if (call->err_msg) {
      memcpy(call->err_msg, msg, n);
      call->err_msg_len = n;
    }
    return 0;
  }
  memcpy(call->resp_data, call->req_data, call->req_len);
  call->resp_len = call->req_len;
  return 0;
}

/* A handler that always returns NOT_FOUND, to demonstrate error status. */
GRPCIO_NATIVE_HANDLER int always_not_found(grpc_native_unary_call* call) {
  (void)call;
  call->status = GRPC_NATIVE_STATUS_NOT_FOUND;
  const char* msg = "nothing here";
  size_t n = strlen(msg);
  call->err_msg = (char*)malloc(n);
  if (call->err_msg) {
    memcpy(call->err_msg, msg, n);
    call->err_msg_len = n;
  }
  return 0;
}

/*
 * A "real" handler that reads a 4-byte little-endian uint32 from the request,
 * doubles it, and writes a 4-byte little-endian uint32 response. This is the
 * shape of how a protobuf handler would look — just with a hand-rolled wire
 * format instead of generated protobuf code.
 */
/* A representative "heavy" handler: FNV-1a 64-bit hash over the request,
 * iterated to make the per-call cost meaningful (~10us-100us for typical
 * message sizes). This is the kind of workload where the difference between
 * Python and native shows up — the Python equivalent has to iterate byte by
 * byte through a loop, which is slow. */
/* FNV-1a hash, iterated. Stands in for any per-byte CPU work. The first
 * 4 bytes of the request are interpreted as a little-endian uint32
 * iteration count, the remaining bytes are the data to hash. The Python
 * equivalent in tests/benchmark.py mirrors this layout. */
GRPCIO_NATIVE_HANDLER int fnv1a_hash(grpc_native_unary_call* call) {
  const uint64_t FNV_OFFSET = 14695981039346656037ULL;
  const uint64_t FNV_PRIME = 1099511628211ULL;
  if (call->req_len < 4) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    return 0;
  }
  uint32_t iterations;
  memcpy(&iterations, call->req_data, 4);
  const char* data = call->req_data + 4;
  size_t data_len = call->req_len - 4;
  uint64_t h = FNV_OFFSET;
  for (uint32_t it = 0; it < iterations; ++it) {
    for (size_t i = 0; i < data_len; ++i) {
      h ^= (uint8_t)data[i];
      h *= FNV_PRIME;
    }
  }
  call->resp_data = (char*)malloc(8);
  if (call->resp_data == NULL) {
    call->status = GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED;
    return 0;
  }
  memcpy(call->resp_data, &h, 8);
  call->resp_len = 8;
  return 0;
}

/* A genuinely compute-heavy workload: matrix-multiply two square float
 * matrices encoded in the request. Stands in for ranking, embedding lookup,
 * or any numerical handler. The Python equivalent uses nested loops (no
 * numpy) to make the GIL/interpreter overhead representative of arbitrary
 * Python compute.
 *
 * Request layout: [uint32 n] [n*n float32 A] [n*n float32 B]
 * Response layout: [n*n float32 C]   (C = A @ B)
 *
 * For n=32 this is 32*32*32*2 = 65,536 fmadds, finishes in a few μs in C
 * and ~30 ms in plain Python — a representative ~10000× compute-density gap.
 */
GRPCIO_NATIVE_HANDLER int matmul(grpc_native_unary_call* call) {
  if (call->req_len < 4) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    return 0;
  }
  uint32_t n;
  memcpy(&n, call->req_data, 4);
  if (n == 0 || n > 256) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    return 0;
  }
  size_t mat_bytes = (size_t)n * n * sizeof(float);
  if (call->req_len != 4 + 2 * mat_bytes) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    return 0;
  }
  const float* A = (const float*)(call->req_data + 4);
  const float* B = (const float*)(call->req_data + 4 + mat_bytes);
  float* C = (float*)malloc(mat_bytes);
  if (C == NULL) {
    call->status = GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED;
    return 0;
  }
  for (uint32_t i = 0; i < n; ++i) {
    for (uint32_t j = 0; j < n; ++j) {
      float s = 0.0f;
      for (uint32_t k = 0; k < n; ++k) {
        s += A[i * n + k] * B[k * n + j];
      }
      C[i * n + j] = s;
    }
  }
  call->resp_data = (char*)C;
  call->resp_len = mat_bytes;
  return 0;
}

GRPCIO_NATIVE_HANDLER int double_uint32(grpc_native_unary_call* call) {
  if (call->req_len != 4) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    const char* msg = "expected 4-byte request";
    size_t n = strlen(msg);
    call->err_msg = (char*)malloc(n);
    if (call->err_msg) {
      memcpy(call->err_msg, msg, n);
      call->err_msg_len = n;
    }
    return 0;
  }
  uint32_t v;
  memcpy(&v, call->req_data, 4);
  v = v * 2u;
  call->resp_data = (char*)malloc(4);
  if (call->resp_data == NULL) {
    call->status = GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED;
    return 0;
  }
  memcpy(call->resp_data, &v, 4);
  call->resp_len = 4;
  return 0;
}

/* ===================== Streaming handlers ===================== */

/* Unary -> stream: split the request bytes into single-byte messages. */
GRPCIO_NATIVE_HANDLER int split_bytes(grpc_native_unary_stream_call* call) {
  for (size_t i = 0; i < call->req_len; ++i) {
    char c = call->req_data[i];
    if (call->writer->emit(call->writer->ctx, &c, 1) != 0) {
      /* Stream cancelled by client. */
      return 0;
    }
  }
  return 0;
}

/* Unary -> stream: emit `n` Fibonacci numbers (uint64, little-endian). */
GRPCIO_NATIVE_HANDLER int fib_stream(grpc_native_unary_stream_call* call) {
  if (call->req_len != 4) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    return 0;
  }
  uint32_t n;
  memcpy(&n, call->req_data, 4);
  uint64_t a = 0, b = 1;
  for (uint32_t i = 0; i < n; ++i) {
    if (call->writer->emit(
            call->writer->ctx, (const char*)&a, sizeof(a)) != 0) {
      return 0;
    }
    uint64_t t = a + b;
    a = b;
    b = t;
  }
  return 0;
}

/* Stream -> unary: concatenate all request messages into one response. */
GRPCIO_NATIVE_HANDLER int concat(grpc_native_stream_unary_call* call) {
  size_t capacity = 64;
  size_t used = 0;
  char* buf = (char*)malloc(capacity);
  if (buf == NULL) {
    call->status = GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED;
    return 0;
  }
  while (1) {
    const char* msg = NULL;
    size_t len = 0;
    int rc = call->reader->read(call->reader->ctx, &msg, &len);
    if (rc == 0) break;
    if (rc < 0) {
      free(buf);
      call->status = GRPC_NATIVE_STATUS_CANCELLED;
      return 0;
    }
    if (used + len > capacity) {
      while (capacity < used + len) capacity *= 2;
      char* new_buf = (char*)realloc(buf, capacity);
      if (new_buf == NULL) {
        free(buf);
        call->status = GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED;
        return 0;
      }
      buf = new_buf;
    }
    memcpy(buf + used, msg, len);
    used += len;
  }
  call->resp_data = buf;
  call->resp_len = used;
  return 0;
}

/* Stream -> unary: sum the uint64 LE values in each request message. */
GRPCIO_NATIVE_HANDLER int sum_u64(grpc_native_stream_unary_call* call) {
  uint64_t sum = 0;
  while (1) {
    const char* msg = NULL;
    size_t len = 0;
    int rc = call->reader->read(call->reader->ctx, &msg, &len);
    if (rc == 0) break;
    if (rc < 0) {
      call->status = GRPC_NATIVE_STATUS_CANCELLED;
      return 0;
    }
    if (len != 8) {
      call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
      return 0;
    }
    uint64_t v;
    memcpy(&v, msg, 8);
    sum += v;
  }
  call->resp_data = (char*)malloc(8);
  if (call->resp_data == NULL) {
    call->status = GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED;
    return 0;
  }
  memcpy(call->resp_data, &sum, 8);
  call->resp_len = 8;
  return 0;
}

/* Stream -> stream: echo each request back as a response (per-message). */
GRPCIO_NATIVE_HANDLER int echo_stream(
    grpc_native_stream_stream_call* call) {
  while (1) {
    const char* msg = NULL;
    size_t len = 0;
    int rc = call->reader->read(call->reader->ctx, &msg, &len);
    if (rc == 0) return 0;
    if (rc < 0) {
      call->status = GRPC_NATIVE_STATUS_CANCELLED;
      return 0;
    }
    if (call->writer->emit(call->writer->ctx, msg, len) != 0) {
      /* Stream cancelled. */
      return 0;
    }
  }
}

/* Stream -> stream: running sum over uint64 LE inputs, emit current sum. */
GRPCIO_NATIVE_HANDLER int running_sum(
    grpc_native_stream_stream_call* call) {
  uint64_t sum = 0;
  while (1) {
    const char* msg = NULL;
    size_t len = 0;
    int rc = call->reader->read(call->reader->ctx, &msg, &len);
    if (rc == 0) return 0;
    if (rc < 0) {
      call->status = GRPC_NATIVE_STATUS_CANCELLED;
      return 0;
    }
    if (len != 8) {
      call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
      return 0;
    }
    uint64_t v;
    memcpy(&v, msg, 8);
    sum += v;
    if (call->writer->emit(
            call->writer->ctx, (const char*)&sum, sizeof(sum)) != 0) {
      return 0;
    }
  }
}
