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

// A lookup table that uses a 256-element array of flat_hash_maps.
// Dispatch: use the last character of the key as the bucket index.
// Within each bucket, key is the hash of the full string.
//
// This gives O(1) first dispatch (array index, no hashing) and then
// a lookup in a much smaller flat_hash_map (N/K entries where K is
// the number of distinct last characters).

#ifndef GRPC_TEST_CORE_SERVER_BUCKETED_HASH_LOOKUP_H
#define GRPC_TEST_CORE_SERVER_BUCKETED_HASH_LOOKUP_H

#include <array>
#include <cstdint>
#include <string>

#include "absl/container/flat_hash_map.h"
#include "absl/hash/hash.h"
#include "absl/strings/string_view.h"

namespace grpc_core {
namespace testing {

// A lookup table using 256 flat_hash_maps, one per last-character bucket.
// Value must be default-constructible and have an operator bool().
template <class Value>
class BucketedHashLookup {
 public:
  void Add(absl::string_view key, Value value) {
    if (key.empty()) return;
    uint8_t bucket = static_cast<uint8_t>(key.back());
    uint64_t h = absl::HashOf(key);
    buckets_[bucket][h] = std::move(value);
  }

  Value Find(absl::string_view key) const {
    if (key.empty()) return {};
    uint8_t bucket = static_cast<uint8_t>(key.back());
    uint64_t h = absl::HashOf(key);
    auto it = buckets_[bucket].find(h);
    if (it != buckets_[bucket].end()) {
      return it->second;
    }
    return {};
  }

 private:
  std::array<absl::flat_hash_map<uint64_t, Value>, 256> buckets_;
};

// Wraps BucketedHashLookup with the (host, path) semantics matching
// Server::GetRegisteredMethod behavior:
//   1. Try exact match: (host, path)
//   2. Fallback to wildcard: ("", path)
template <class Value>
class BucketedRegisteredMethodLookup {
 public:
  void Add(absl::string_view host, absl::string_view path, Value value) {
    std::string key = MakeKey(host, path);
    lookup_.Add(key, value);
  }

  Value Find(absl::string_view host, absl::string_view path) const {
    if (!host.empty()) {
      std::string exact_key = MakeKey(host, path);
      Value result = lookup_.Find(exact_key);
      if (result) return result;
    }
    std::string wildcard_key = MakeKey("", path);
    return lookup_.Find(wildcard_key);
  }

 private:
  static std::string MakeKey(absl::string_view host,
                             absl::string_view path) {
    std::string key;
    key.reserve(path.size() + 1 + host.size());
    key.append(path.data(), path.size());
    key.push_back('\0');
    key.append(host.data(), host.size());
    return key;
  }

  BucketedHashLookup<Value> lookup_;
};

}  // namespace testing
}  // namespace grpc_core

#endif  // GRPC_TEST_CORE_SERVER_BUCKETED_HASH_LOOKUP_H
