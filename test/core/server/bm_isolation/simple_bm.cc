// Standalone benchmark for SIMD Bucketed Registered Method Lookup.
// Compares:
// 1. std::unordered_map (Baseline)
// 2. SIMD-Optimized Bucketed Lookup (User Proposed)

#include <iostream>
#include <vector>
#include <string>
#include <unordered_map>
#include <chrono>
#include <algorithm>
#include <array>
#include <string_view>

#include "test/core/server/bucketed_hash_lookup.h"

using namespace grpc_core::testing;

void RunBenchmark(int num_methods) {
  std::cout << "\n--- Scale: " << num_methods << " methods ---\n";

  std::vector<std::string> registered_paths;
  for (int i = 0; i < num_methods; ++i) {
    registered_paths.push_back("/pkg.Service" + std::to_string(i / 10) + "/Method" + std::to_string(i % 10));
  }

  // Setup datasets
  std::unordered_map<std::string, int> baseline_map;
  BucketedRegisteredMethodLookup<int> simd_lookup;

  for (int i = 0; i < num_methods; ++i) {
    baseline_map[registered_paths[i]] = i + 1;
    simd_lookup.Add("", registered_paths[i], i + 1);
  }

  const int iterations = 1000000;
  const std::string query_path = registered_paths.back();

  // 1. Baseline: Single Large Map
  auto start = std::chrono::high_resolution_clock::now();
  volatile int sum = 0;
  for (int i = 0; i < iterations; ++i) {
    auto it = baseline_map.find(query_path);
    if (it != baseline_map.end()) sum += it->second;
  }
  auto end = std::chrono::high_resolution_clock::now();
  std::cout << "Baseline (std::unordered_map): " 
            << std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count() / (double)iterations << " ns/lookup\n";

  // 2. SIMD Bucketed Lookup
  start = std::chrono::high_resolution_clock::now();
  sum = 0;
  for (int i = 0; i < iterations; ++i) {
    sum += simd_lookup.Find("", query_path);
  }
  end = std::chrono::high_resolution_clock::now();
  std::cout << "SIMD Bucketed Lookup:         " 
            << std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count() / (double)iterations << " ns/lookup\n";
}

int main() {
  RunBenchmark(1);
  RunBenchmark(10);
  RunBenchmark(100);
  RunBenchmark(1000);
  return 0;
}
