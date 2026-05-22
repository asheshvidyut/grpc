// Copyright 2026 gRPC authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

#ifndef GRPC_SRC_CORE_EXT_TRANSPORT_CHTTP2_TRANSPORT_SIMD_DISPATCH_H
#define GRPC_SRC_CORE_EXT_TRANSPORT_CHTTP2_TRANSPORT_SIMD_DISPATCH_H

#include <grpc/support/port_platform.h>

#include "src/core/util/env.h"

// Feature-flagged SIMD acceleration for HPACK base64 and Huffman paths.
//
// Default: disabled. Opt-in via the GRPC_SIMD_ACCELERATION environment
// variable. Runtime CPU feature detection on x86 picks the best path; if
// the CPU lacks the required ISA, the scalar fallback is used unchanged.
//
// The scalar implementations are always present and untouched; the SIMD
// paths are additive and protected by:
//   1. The env-var gate (off by default).
//   2. Runtime CPU feature detection.
//   3. A compile-time guard on x86_64 with SSE4.1+ headers available.

namespace grpc_core {
namespace simd {

// Cached, one-shot env-var check. Reads GRPC_SIMD_ACCELERATION on first call;
// subsequent calls return the cached value. Empty/unset/"0"/"false" -> false;
// any other value -> true.
inline bool IsEnabled() {
  static const bool enabled = [] {
    auto v = GetEnv("GRPC_SIMD_ACCELERATION");
    if (!v.has_value()) return false;
    const std::string& s = *v;
    if (s.empty() || s == "0" || s == "false" || s == "FALSE") return false;
    return true;
  }();
  return enabled;
}

// x86 CPU feature detection. Cached, computed once per process.
// On non-x86 targets these always return false.
#if defined(__x86_64__) || defined(_M_X64)
#if defined(__GNUC__) || defined(__clang__)
inline bool HasSse41() {
  static const bool v = __builtin_cpu_supports("sse4.1");
  return v;
}
inline bool HasAvx2() {
  static const bool v = __builtin_cpu_supports("avx2");
  return v;
}
#else
inline bool HasSse41() { return false; }
inline bool HasAvx2() { return false; }
#endif
#else
inline bool HasSse41() { return false; }
inline bool HasAvx2() { return false; }
#endif

// Composite gates the call sites use. Each is &&-ed with IsEnabled().
inline bool UseSse41() { return IsEnabled() && HasSse41(); }
inline bool UseAvx2() { return IsEnabled() && HasAvx2(); }

}  // namespace simd
}  // namespace grpc_core

#endif  // GRPC_SRC_CORE_EXT_TRANSPORT_CHTTP2_TRANSPORT_SIMD_DISPATCH_H
