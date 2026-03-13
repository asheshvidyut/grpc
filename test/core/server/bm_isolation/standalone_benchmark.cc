// Standalone benchmark for Registered Method Lookup.
// This bypasses Bazel and gRPC dependencies to provide results despite toolchain issues.
// Compares:
// 1. absl::flat_hash_map (Baseline)
// 2. BucketedHashLookup (User-proposed, zero-allocation hashing)

#include <iostream>
#include <vector>
#include <string>
#include <chrono>
#include <algorithm>
#include <array>

// Include absl if possible, otherwise fallback to std::unordered_map
// In the run command, we will provide the include path to Abseil.
#include "absl/container/flat_hash_map.h"
#include "absl/hash/hash.h"

// ===================================================================
// Data Structures
// ===================================================================

// 1. Bucketed Hash Implementation (User Proposal)
// Optimized: No string concatenation, hashes components directly.
template <class Value>
class BucketedHashLookup {
 public:
  void Add(const std::string& host, const std::string& path, Value value) {
    if (path.empty()) return;
    uint8_t bucket = static_cast<uint8_t>(path.back());
    size_t h = absl::HashOf(path, host);
    buckets_[bucket][h] = value;
  }

  Value Find(const std::string& host, const std::string& path) const {
    if (path.empty()) return {};
    uint8_t bucket = static_cast<uint8_t>(path.back());
    size_t h = absl::HashOf(path, host);
    auto it = buckets_[bucket].find(h);
    if (it != buckets_[bucket].end()) return it->second;
    return {};
  }

 private:
  std::array<absl::flat_hash_map<size_t, Value>, 256> buckets_;
};

// ===================================================================
// Benchmarking logic
// ===================================================================

struct PathHost {
    std::string path;
    std::string host;

    bool operator==(const PathHost& other) const {
        return path == other.path && host == other.host;
    }

    template <typename H>
    friend H AbslHashValue(H h, const PathHost& ph) {
        return H::combine(std::move(h), ph.path, ph.host);
    }
};

void RunBenchmark(int num_methods) {
  std::cout << "\n--- Scale: " << num_methods << " methods ---\n";

  std::vector<std::string> paths;
  std::vector<std::string> hosts;
  std::vector<PathHost> path_hosts;
  for (int i = 0; i < num_methods; ++i) {
    std::string path = "/pkg.Service" + std::to_string(i / 10) + "/Method" + std::to_string(i % 10);
    std::string host = "host" + std::to_string(i) + ".example.com";
    paths.push_back(path);
    hosts.push_back(host);
    path_hosts.push_back({path, host});
  }

  // Setup
  absl::flat_hash_map<PathHost, int> flat_map;
  BucketedHashLookup<int> bucketed;

  for (int i = 0; i < num_methods; ++i) {
    flat_map[path_hosts[i]] = i + 1;
    bucketed.Add(hosts[i], paths[i], i + 1);
  }

  const int iterations = 1000000;
  const PathHost query_ph = path_hosts.back();
  const std::string query_host = hosts.back();
  const std::string query_path = paths.back();

  // 1. absl::flat_hash_map (Baseline)
  auto start = std::chrono::high_resolution_clock::now();
  volatile int sum = 0;
  for (int i = 0; i < iterations; ++i) {
    sum += flat_map.at(query_ph);
  }
  auto end = std::chrono::high_resolution_clock::now();
  std::cout << "absl::flat_hash_map:      " << std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count() / (double)iterations << " ns/lookup\n";

  // 2. Bucketed Hash (Optimized)
  start = std::chrono::high_resolution_clock::now();
  sum = 0;
  for (int i = 0; i < iterations; ++i) {
    sum += bucketed.Find(query_host, query_path);
  }
  end = std::chrono::high_resolution_clock::now();
  std::cout << "BucketedHash (zero-alloc): " << std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count() / (double)iterations << " ns/lookup\n";
}

int main() {
  RunBenchmark(1);
  RunBenchmark(10);
  RunBenchmark(100);
  RunBenchmark(10000); // 10k methods to really stress probability of collisions
  return 0;
}
