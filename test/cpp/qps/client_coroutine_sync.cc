//
// Copyright 2024 gRPC authors (Coroutine-based synchronous-style client)
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
//

#include "test/cpp/qps/client_coroutine.h"

#include <atomic>
#include <chrono>
#include <grpc/grpc.h>
#include <grpc/support/time.h>
#include <grpcpp/channel.h>
#include <grpcpp/client_context.h>
#include <grpcpp/completion_queue.h>

#include <memory>
#include <thread>
#include <vector>

#include "src/core/util/crash.h"
#include "src/core/util/grpc_check.h"
#include "src/proto/grpc/testing/benchmark_service.grpc.pb.h"
#include "test/cpp/qps/client.h"
#include "test/cpp/qps/interarrival.h"
#include "test/cpp/qps/usage_timer.h"

// Include AsyncUnaryCallAwaiter forward declaration needed
#include "test/cpp/qps/client_coroutine.h"
#include "absl/log/log.h"

namespace grpc {
namespace testing {

static std::unique_ptr<BenchmarkService::Stub> BenchmarkStubCreator(
    const std::shared_ptr<Channel>& ch) {
  return BenchmarkService::NewStub(ch);
}

// Coroutine-based client that mimics synchronous API but uses coroutines
class CoroutineClient
    : public ClientImpl<BenchmarkService::Stub, SimpleRequest> {
 public:
  using Client::closed_loop_;
  using Client::thread_pool_done_;
  using Client::NextIssueTime;
  using Client::ThreadCompleted;
  using ClientImpl<BenchmarkService::Stub, SimpleRequest>::channels_;
  using ClientImpl<BenchmarkService::Stub, SimpleRequest>::request_;
  
  explicit CoroutineClient(const ClientConfig& config)
      : ClientImpl<BenchmarkService::Stub, SimpleRequest>(
            config, BenchmarkStubCreator) {
    num_threads_ =
        config.outstanding_rpcs_per_channel() * config.client_channels();
    responses_.resize(num_threads_);
    
    // Create completion queues (one per thread or shared)
    int threads_per_cq = std::max(1, config.threads_per_cq());
    int num_cqs = (num_threads_ + threads_per_cq - 1) / threads_per_cq;
    for (int i = 0; i < num_cqs; i++) {
      cqs_.emplace_back(std::make_unique<CompletionQueue>());
    }
    
    SetupLoadTest(config, num_threads_);
  }

  ~CoroutineClient() override {
    // Drain completion queues (they should already be shut down by DestroyMultithreading)
    for (auto& cq : cqs_) {
      void* tag;
      bool ok;
      while (cq->Next(&tag, &ok)) {
        // Clean up any remaining operations
      }
    }
  }

  void ThreadFunc(size_t thread_idx, Thread* t) override {
    // Run coroutine-based RPC loop
    // Poll completion queue in same thread to eliminate thread overhead
    CompletionQueue* cq = cqs_[thread_idx % cqs_.size()].get();
    
    for (;;) {
      // Check if we should stop BEFORE starting new RPCs
      if (ThreadCompleted()) {
        return;
      }
      
      if (!WaitToIssue(thread_idx)) {
        return;
      }
      
      HistogramEntry entry;
      bool thread_still_ok = CoroutineThreadFuncImpl(&entry, thread_idx, cq);
      t->UpdateHistogram(&entry);
      
      if (!thread_still_ok) {
        return;
      }
    }
  }

 protected:
  bool WaitToIssue(int thread_idx) {
    if (!closed_loop_) {
      const gpr_timespec next_issue_time = NextIssueTime(thread_idx);
      while (true) {
        const gpr_timespec one_sec_delay =
            gpr_time_add(gpr_now(GPR_CLOCK_MONOTONIC),
                         gpr_time_from_seconds(1, GPR_TIMESPAN));
        if (gpr_time_cmp(next_issue_time, one_sec_delay) <= 0) {
          gpr_sleep_until(next_issue_time);
          return true;
        } else {
          gpr_sleep_until(one_sec_delay);
          if (gpr_atm_acq_load(&thread_pool_done_) != gpr_atm{0}) {
            return false;
          }
        }
      }
    }
    return true;
  }

  // Coroutine-based thread function
  bool CoroutineThreadFuncImpl(HistogramEntry* entry, size_t thread_idx,
                               CompletionQueue* cq) {
    responses_[thread_idx].Clear();
    auto* stub = channels_[thread_idx % channels_.size()].get_stub();
    double start = UsageTimer::Now();
    
    grpc::ClientContext context;
    
    // Use coroutine-based async call - pass CQ for in-thread polling
    auto task = CoroutineUnaryCall(stub, &context, request_,
                                   &responses_[thread_idx], cq, nullptr);
    // Pass completion queue to get() so it can poll directly in this thread
    grpc::Status s = task.get(cq);
    
    if (s.ok()) {
      entry->set_value((UsageTimer::Now() - start) * 1e9);
    }
    entry->set_status(s.error_code());
    return true;
  }

  size_t num_threads_;
  std::vector<SimpleResponse> responses_;
  std::vector<std::unique_ptr<CompletionQueue>> cqs_;
};

class CoroutineUnaryClient final : public CoroutineClient {
 public:
  explicit CoroutineUnaryClient(const ClientConfig& config)
      : CoroutineClient(config) {
    StartThreads(num_threads_);
  }
  ~CoroutineUnaryClient() override {}

 private:
  void DestroyMultithreading() final {
    // Shutdown completion queues before ending threads
    // This ensures all threads stop using the queues before they're shut down
    for (auto& cq : cqs_) {
      cq->Shutdown();
    }
    EndThreads();
  }
};

std::unique_ptr<Client> CreateCoroutineClient(const ClientConfig& config) {
  GRPC_CHECK(!config.use_coalesce_api());  // not supported yet.
  switch (config.rpc_type()) {
    case UNARY:
      return std::unique_ptr<Client>(new CoroutineUnaryClient(config));
    default:
      LOG(ERROR) << "Coroutine client only supports UNARY RPC type";
      return nullptr;
  }
}

}  // namespace testing
}  // namespace grpc

