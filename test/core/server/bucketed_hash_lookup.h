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

#ifndef GRPC_TEST_CORE_SERVER_BUCKETED_HASH_LOOKUP_H
#define GRPC_TEST_CORE_SERVER_BUCKETED_HASH_LOOKUP_H

#include <array>
#include <cstdint>
#include <string>
#include <vector>
#include <string_view>
#include <cstring>

#ifdef __ARM_NEON
#include <arm_neon.h>
#endif

namespace grpc_core {
namespace testing {

// SIMD-optimized bucket for registered method lookup.
template <class Value>
struct Bucket {
  uint32_t count{0};
  uint8_t fingerprints[16]{0};
  std::string_view keys[16]{};
  Value values[16]{};
  
  struct OverflowEntry {
    std::string_view key;
    Value value;
  };
  std::vector<OverflowEntry> overflow;

  void Add(std::string_view key, uint8_t fp, Value value) {
    if (count < 16) {
      fingerprints[count] = fp;
      keys[count] = key;
      values[count] = std::move(value);
      count++;
    } else {
      overflow.push_back({key, std::move(value)});
    }
  }

  Value Get(std::string_view sv, uint8_t target_fp) const {
    if (count == 0) return {};

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
                if (sv == keys[i]) return values[i];
            }
        }
        for (uint32_t i = 0; i < 8; ++i) {
            if ((high >> (i * 8)) & 0xFF) {
                if (sv == keys[i + 8]) return values[i + 8];
            }
        }
    }
#else
    for (uint32_t i = 0; i < count; ++i) {
      if (fingerprints[i] == target_fp && sv == keys[i]) {
        return values[i];
      }
    }
#endif

    for (const auto& entry : overflow) {
      if (sv == entry.key) return entry.value;
    }

    return {};
  }
};

template <class Value>
class BucketedRegisteredMethodLookup {
 public:
  // Ultra-fast O(1) hashing for bucket distribution.
  static inline uint64_t FastHash(std::string_view sv) {
    size_t len = sv.size();
    if (len < 12) return len ^ (len > 0 ? static_cast<uint8_t>(sv[0]) : 0);
    uint32_t v1, v2;
    // Use 4 bytes from end and 4 bytes from middle-ish to differentiate
    std::memcpy(&v1, sv.data() + len - 4, 4);
    std::memcpy(&v2, sv.data() + (len - 8), 4);
    return (uint64_t(v1) << 32) | v2;
  }

  void Add(std::string_view host, std::string_view path, Value value) {
    if (path.empty()) return;
    uint64_t h = FastHash(path);
    uint8_t bucket_idx = static_cast<uint8_t>(h & 0xFF);
    uint8_t fp = static_cast<uint8_t>((h >> 8) & 0xFF);
    jump_table_[bucket_idx].Add(path, fp, std::move(value));
  }

  Value Find(std::string_view host, std::string_view path) const {
    if (path.empty()) return {};
    uint64_t h = FastHash(path);
    uint8_t bucket_idx = static_cast<uint8_t>(h & 0xFF);
    uint8_t fp = static_cast<uint8_t>((h >> 8) & 0xFF);
    return jump_table_[bucket_idx].Get(path, fp);
  }

 private:
  std::array<Bucket<Value>, 256> jump_table_;
};

}  // namespace testing
}  // namespace grpc_core

#endif  // GRPC_TEST_CORE_SERVER_BUCKETED_HASH_LOOKUP_H
