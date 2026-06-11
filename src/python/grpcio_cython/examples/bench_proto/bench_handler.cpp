// Native handlers for the three-way benchmark.
//
// The same .so is loaded two ways from Python:
//
//   1) Through grpcio_cython: the `fnv1a_hash` and `matmul_handler` symbols
//      expose the full ABI-versioned entry point (wire bytes in, wire bytes
//      out, GIL released, libprotobuf for parse/serialize).
//
//   2) Through ctypes: the `fnv1a_hash_raw` and `matmul_raw` symbols expose
//      primitive-typed entry points the "naive ctypes" Python servicer calls
//      after parsing the proto in Python.
//
// The two paths share the compute kernel (`fnv1a` / `matmul_kernel`) so the
// only difference being measured is the framework cost around it.

#include "grpcio_cython/handler.h"
#ifndef NO_PROTO_BINDINGS
#include "bench.pb.h"
#endif

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#ifndef NO_PROTO_BINDINGS
GRPCIO_NATIVE_DECLARE_ABI()
#endif

namespace {

constexpr uint64_t FNV_OFFSET = 14695981039346656037ULL;
constexpr uint64_t FNV_PRIME = 1099511628211ULL;

uint64_t fnv1a(const uint8_t* data, size_t len, uint32_t iterations) {
  uint64_t h = FNV_OFFSET;
  for (uint32_t it = 0; it < iterations; ++it) {
    uint64_t local = h;
    for (size_t i = 0; i < len; ++i) {
      local = (local ^ data[i]) * FNV_PRIME;
    }
    h = local;
  }
  return h;
}

void matmul_kernel(const float* a, const float* b, float* c, uint32_t n) {
  for (uint32_t i = 0; i < n; ++i) {
    for (uint32_t j = 0; j < n; ++j) {
      float s = 0.0f;
      for (uint32_t k = 0; k < n; ++k) {
        s += a[i * n + k] * b[k * n + j];
      }
      c[i * n + j] = s;
    }
  }
}

#ifndef NO_PROTO_BINDINGS
char* malloc_copy(const std::string& s) {
  char* buf = static_cast<char*>(std::malloc(s.size()));
  if (buf && !s.empty()) {
    std::memcpy(buf, s.data(), s.size());
  }
  return buf;
}
#endif

}  // namespace

// ---- ctypes entry points (called from the "naive ctypes" Python servicer) --

extern "C" GRPCIO_NATIVE_EXPORT
uint64_t fnv1a_hash_raw(const uint8_t* data, size_t len, uint32_t iterations) {
  return fnv1a(data, len, iterations);
}

extern "C" GRPCIO_NATIVE_EXPORT
void matmul_raw(const float* a, const float* b, float* c, uint32_t n) {
  matmul_kernel(a, b, c, n);
}

// ---- grpcio_cython entry points -------------------------------------------

#ifndef NO_PROTO_BINDINGS
extern "C" GRPCIO_NATIVE_EXPORT
int fnv1a_hash(grpc_native_unary_call* call) {
  bench::HashRequest req;
  if (!req.ParseFromArray(call->req_data, static_cast<int>(call->req_len))) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    return 0;
  }
  const std::string& data = req.data();
  uint64_t h = fnv1a(reinterpret_cast<const uint8_t*>(data.data()),
                     data.size(), req.iterations());
  bench::HashResponse resp;
  resp.set_hash(h);
  std::string out;
  resp.SerializeToString(&out);
  call->resp_data = malloc_copy(out);
  call->resp_len = out.size();
  return 0;
}

extern "C" GRPCIO_NATIVE_EXPORT
int matmul_handler(grpc_native_unary_call* call) {
  bench::MatMulRequest req;
  if (!req.ParseFromArray(call->req_data, static_cast<int>(call->req_len))) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    return 0;
  }
  uint32_t n = req.n();
  const int expected = static_cast<int>(n) * static_cast<int>(n);
  if (req.a_size() != expected || req.b_size() != expected) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    return 0;
  }
  std::vector<float> c(static_cast<size_t>(expected));
  matmul_kernel(req.a().data(), req.b().data(), c.data(), n);
  bench::MatMulResponse resp;
  resp.mutable_c()->Add(c.begin(), c.end());
  std::string out;
  resp.SerializeToString(&out);
  call->resp_data = malloc_copy(out);
  call->resp_len = out.size();
  return 0;
}
#endif
