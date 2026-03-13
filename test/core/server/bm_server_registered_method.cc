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

// Benchmark for Server::GetRegisteredMethod (flat_hash_map) vs a trie-based
// approach (adapted from Envoy's TrieLookupTable) vs a bucketed hash lookup
// (256 buckets dispatched by last character).
//
// This exercises the server hot path that runs on every incoming RPC.

#include <benchmark/benchmark.h>
#include <grpc/grpc.h>

#include <string>
#include <vector>

#include "absl/strings/str_cat.h"
#include "src/core/server/server.h"
#include "test/core/server/bucketed_hash_lookup.h"

namespace grpc_core {
namespace testing {

// Test peer to access private GetRegisteredMethod.
class ServerTestPeer {
 public:
  explicit ServerTestPeer(Server* server) : server_(server) {}

  Server::RegisteredMethod* GetRegisteredMethod(
      const absl::string_view& host, const absl::string_view& path) {
    return server_->GetRegisteredMethod(host, path);
  }

 private:
  Server* server_;
};

}  // namespace testing

namespace {

// ===================================================================
// Common helpers
// ===================================================================

struct ServerSetup {
  grpc_server* c_server;
  Server* server;
  grpc_completion_queue* cq;
};

ServerSetup CreateServerWithMethods(int num_methods, bool with_host) {
  grpc_server* s = grpc_server_create(nullptr, nullptr);
  for (int i = 0; i < num_methods; ++i) {
    std::string method =
        absl::StrCat("/pkg.Service", i / 10, "/Method", i % 10);
    const char* host = with_host ? "host.example.com" : nullptr;
    grpc_server_register_method(s, method.c_str(), host,
                                GRPC_SRM_PAYLOAD_NONE, 0);
  }
  grpc_completion_queue* cq =
      grpc_completion_queue_create_for_next(nullptr);
  grpc_server_register_completion_queue(s, cq, nullptr);
  grpc_server_start(s);
  return {s, Server::FromC(s), cq};
}

void DestroyServer(ServerSetup& setup) {
  grpc_server_shutdown_and_notify(setup.c_server, setup.cq, nullptr);
  grpc_completion_queue_next(setup.cq, gpr_inf_future(GPR_CLOCK_REALTIME),
                             nullptr);
  grpc_server_destroy(setup.c_server);
  grpc_completion_queue_destroy(setup.cq);
}

// Dummy value type for the trie/bucketed lookup — simulates a pointer-like result.
struct MethodEntry {
  void* ptr;
  explicit operator bool() const { return ptr != nullptr; }
};

testing::TrieRegisteredMethodLookup<MethodEntry> BuildTrie(int num_methods,
                                                           bool with_host) {
  testing::TrieRegisteredMethodLookup<MethodEntry> trie;
  for (int i = 0; i < num_methods; ++i) {
    std::string method =
        absl::StrCat("/pkg.Service", i / 10, "/Method", i % 10);
    absl::string_view host = with_host ? "host.example.com" : "";
    trie.Add(host, method, MethodEntry{reinterpret_cast<void*>(i + 1)});
  }
  return trie;
}

testing::BucketedRegisteredMethodLookup<MethodEntry> BuildBucketed(
    int num_methods, bool with_host) {
  testing::BucketedRegisteredMethodLookup<MethodEntry> lookup;
  for (int i = 0; i < num_methods; ++i) {
    std::string method =
        absl::StrCat("/pkg.Service", i / 10, "/Method", i % 10);
    absl::string_view host = with_host ? "host.example.com" : "";
    lookup.Add(host, method, MethodEntry{reinterpret_cast<void*>(i + 1)});
  }
  return lookup;
}

// ===================================================================
// flat_hash_map benchmarks (current implementation)
// ===================================================================

void BM_FlatHashMap_Lookup(benchmark::State& state) {
  ExecCtx exec_ctx;
  const int num_methods = state.range(0);
  const bool with_host = state.range(1);

  auto setup = CreateServerWithMethods(num_methods, with_host);
  testing::ServerTestPeer peer(setup.server);

  std::string path =
      absl::StrCat("/pkg.Service", (num_methods - 1) / 10, "/Method",
                   (num_methods - 1) % 10);
  absl::string_view host = with_host ? "host.example.com" : "";

  for (auto _ : state) {
    auto* rm = peer.GetRegisteredMethod(host, path);
    benchmark::DoNotOptimize(rm);
  }

  DestroyServer(setup);
}

BENCHMARK(BM_FlatHashMap_Lookup)
    ->Args({1, 0})
    ->Args({1, 1})
    ->Args({10, 0})
    ->Args({10, 1})
    ->Args({100, 0})
    ->Args({100, 1})
    ->Args({1000, 0})
    ->Args({1000, 1});

// ===================================================================
// Bucketed Hash benchmarks (User proposed)
// ===================================================================

void BM_BucketedHash_Lookup(benchmark::State& state) {
  const int num_methods = state.range(0);
  const bool with_host = state.range(1);

  auto lookup = BuildBucketed(num_methods, with_host);

  std::string path =
      absl::StrCat("/pkg.Service", (num_methods - 1) / 10, "/Method",
                   (num_methods - 1) % 10);
  absl::string_view host = with_host ? "host.example.com" : "";

  for (auto _ : state) {
    auto result = lookup.Find(host, path);
    benchmark::DoNotOptimize(result);
  }
}

BENCHMARK(BM_BucketedHash_Lookup)
    ->Args({1, 0})
    ->Args({1, 1})
    ->Args({10, 0})
    ->Args({10, 1})
    ->Args({100, 0})
    ->Args({100, 1})
    ->Args({1000, 0})
    ->Args({1000, 1});

}  // namespace
}  // namespace grpc_core

namespace benchmark {
void RunTheBenchmarksNamespaced() { RunSpecifiedBenchmarks(); }
}  // namespace benchmark

int main(int argc, char** argv) {
  ::benchmark::Initialize(&argc, argv);
  grpc_init();
  {
    benchmark::RunTheBenchmarksNamespaced();
  }
  grpc_shutdown();
  return 0;
}
