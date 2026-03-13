// Copyright 2026 gRPC authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef GRPC_SRC_CORE_SERVER_METHOD_LOOKUP_H
#define GRPC_SRC_CORE_SERVER_METHOD_LOOKUP_H

#include <grpc/support/port_platform.h>

#include <array>
#include <cstdint>
#include <cstring>
#include <string_view>
#include <vector>

#ifdef __ARM_NEON
#include <arm_neon.h>
#endif

namespace grpc_core {

// SIMD-optimized bucket for registered method lookup.
template <typename T>
class MethodLookupTable {
 public:
  struct Bucket {
    uint32_t count{0};
    uint8_t fingerprints[16]{0};
    const T* methods[16]{nullptr};

    struct OverflowEntry {
      const T* method;
    };
    std::vector<OverflowEntry> overflow;

    void Add(const T* method) {
      if (count < 16) {
        fingerprints[count] = method->path_fingerprint;
        methods[count] = method;
        count++;
      } else {
        overflow.push_back({method});
      }
    }

    const T* Find(std::string_view host, std::string_view path,
                  uint8_t target_fp) const {
      const T* wildcard_match = nullptr;

#ifdef __ARM_NEON
      uint8x16_t target = vdupq_n_u8(target_fp);
      uint8x16_t candidates = vld1q_u8(fingerprints);
      uint8x16_t comparison = vceqq_u8(target, candidates);

      uint64x2_t mask_parts = vreinterpretq_u64_u8(comparison);
      uint64_t low = vgetq_lane_u64(mask_parts, 0);
      uint64_t high = vgetq_lane_u64(mask_parts, 1);

      if (low != 0 || high != 0) {
        for (uint32_t i = 0; i < 8; ++i) {
          if ((low >> (i * 8)) & 0xFF) {
            const T* m = methods[i];
            if (path == m->method) {
              if (host == m->host) return m;
              if (m->host.empty()) wildcard_match = m;
            }
          }
        }
        for (uint32_t i = 0; i < 8; ++i) {
          if ((high >> (i * 8)) & 0xFF) {
            const T* m = methods[i + 8];
            if (path == m->method) {
              if (host == m->host) return m;
              if (m->host.empty()) wildcard_match = m;
            }
          }
        }
      }
#else
      for (uint32_t i = 0; i < count; ++i) {
        if (fingerprints[i] == target_fp && path == methods[i]->method) {
          if (host == methods[i]->host) return methods[i];
          if (methods[i]->host.empty()) wildcard_match = methods[i];
        }
      }
#endif

      for (const auto& entry : overflow) {
        if (path == entry.method->method) {
          if (host == entry.method->host) return entry.method;
          if (entry.method->host.empty()) wildcard_match = entry.method;
        }
      }

      return wildcard_match;
    }
  };

  static inline uint64_t FastHash(std::string_view sv) {
    size_t len = sv.size();
    if (len < 12) return len ^ (len > 0 ? static_cast<uint8_t>(sv[0]) : 0);
    uint32_t v1, v2;
    std::memcpy(&v1, sv.data() + len - 4, 4);
    std::memcpy(&v2, sv.data() + (len - 8), 4);
    return (uint64_t(v1) << 32) | v2;
  }

  void Add(const T* method) {
    uint8_t bucket_idx = static_cast<uint8_t>(method->path_hash & 0xFF);
    buckets_[bucket_idx].Add(method);
  }

  const T* Find(std::string_view host, std::string_view path) const {
    if (path.empty()) return nullptr;
    uint64_t h = FastHash(path);
    uint8_t bucket_idx = static_cast<uint8_t>(h & 0xFF);
    uint8_t fp = static_cast<uint8_t>((h >> 8) & 0xFF);
    return buckets_[bucket_idx].Find(host, path, fp);
  }

 private:
  std::array<Bucket, 256> buckets_;
};

}  // namespace grpc_core

#endif  // GRPC_SRC_CORE_SERVER_METHOD_LOOKUP_H
