//
// Copyright 2024 gRPC authors (Coroutine wrapper implementation)
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

#ifndef GRPC_TEST_CPP_QPS_CLIENT_COROUTINE_H
#define GRPC_TEST_CPP_QPS_CLIENT_COROUTINE_H

#include <atomic>
#include <coroutine>
#include <exception>
#include <memory>
#include <optional>
#include <thread>
#include <utility>

#include <grpcpp/channel.h>
#include <grpcpp/client_context.h>
#include <grpcpp/completion_queue.h>
#include <grpcpp/support/async_stream.h>

#include "src/proto/grpc/testing/benchmark_service.grpc.pb.h"

namespace grpc {
namespace testing {


// Coroutine-aware promise type for gRPC Status results
template <typename T>
class GrpcTask {
 public:
  struct promise_type {
    std::optional<T> value_;
    std::exception_ptr exception_;
    std::atomic<bool> done_{false};

    promise_type();
    GrpcTask get_return_object();
    std::suspend_always initial_suspend();
    std::suspend_always final_suspend() noexcept;
    void return_value(T value);
    void unhandled_exception();
  };

  GrpcTask(std::coroutine_handle<promise_type> handle);
  ~GrpcTask();

  // Non-copyable
  GrpcTask(const GrpcTask&) = delete;
  GrpcTask& operator=(const GrpcTask&) = delete;

  // Movable
  GrpcTask(GrpcTask&& other) noexcept;
  GrpcTask& operator=(GrpcTask&& other) noexcept;

  T get(grpc::CompletionQueue* cq = nullptr);

 private:
  std::coroutine_handle<promise_type> handle_;
};

// Coroutine-aware awaitable for gRPC AsyncUnaryCall
template <typename ResponseType>
class AsyncUnaryCallAwaiter {
 public:
  AsyncUnaryCallAwaiter(
      std::unique_ptr<grpc::ClientAsyncResponseReader<ResponseType>> reader,
      grpc::CompletionQueue* cq);

  bool await_ready() const noexcept;
  void await_suspend(std::coroutine_handle<> h);
  std::pair<grpc::Status, ResponseType*> await_resume();
  
  // Public method to resume coroutine when async operation completes
  void ResumeWithCompletion(bool ok) {
    ok_.store(ok, std::memory_order_release);
    done_.store(true, std::memory_order_release);
    if (handle_) {
      handle_.resume();
    }
  }
  
 private:
  std::unique_ptr<grpc::ClientAsyncResponseReader<ResponseType>> reader_;
  grpc::CompletionQueue* cq_;
  ResponseType response_;
  grpc::Status status_;
  mutable std::atomic<bool> done_{false};
  std::atomic<bool> ok_{false};
  std::coroutine_handle<> handle_;
};

// Helper function to make async call awaitable
template <typename ResponseType>
AsyncUnaryCallAwaiter<ResponseType> MakeAsyncUnaryCall(
    BenchmarkService::Stub* stub, grpc::ClientContext* context,
    const SimpleRequest& request, grpc::CompletionQueue* cq);

// Coroutine-based unary call
GrpcTask<grpc::Status> CoroutineUnaryCall(
    BenchmarkService::Stub* stub, grpc::ClientContext* context,
    const SimpleRequest& request, SimpleResponse* response,
    grpc::CompletionQueue* cq,
    AsyncUnaryCallAwaiter<SimpleResponse>* awaiter_ptr = nullptr);

}  // namespace testing
}  // namespace grpc

#endif  // GRPC_TEST_CPP_QPS_CLIENT_COROUTINE_H

