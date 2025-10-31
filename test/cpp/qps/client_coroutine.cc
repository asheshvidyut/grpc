//
// Copyright 2024 gRPC authors (Coroutine-based client implementation)
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
#include <coroutine>
#include <exception>
#include <memory>
#include <optional>
#include <thread>

#include <grpc/support/time.h>

#include <grpcpp/channel.h>
#include <grpcpp/client_context.h>
#include <grpcpp/completion_queue.h>
#include <grpcpp/support/async_stream.h>

#include "src/proto/grpc/testing/benchmark_service.grpc.pb.h"
#include "test/cpp/qps/client.h"
#include "test/cpp/qps/interarrival.h"
#include "test/cpp/qps/usage_timer.h"
#include "test/cpp/qps/client_coroutine.h"
#include "absl/log/log.h"

namespace grpc {
namespace testing {

// Coroutine-aware promise type for gRPC Status results
template <typename T>
GrpcTask<T>::promise_type::promise_type() : value_(), exception_() {}

template <typename T>
GrpcTask<T> GrpcTask<T>::promise_type::get_return_object() {
  return GrpcTask<T>{std::coroutine_handle<promise_type>::from_promise(*this)};
}

template <typename T>
std::suspend_always GrpcTask<T>::promise_type::initial_suspend() {
  return {};
}

template <typename T>
std::suspend_always GrpcTask<T>::promise_type::final_suspend() noexcept {
  // Mark as done before suspending
  done_.store(true, std::memory_order_release);
  // Suspend so we can manually destroy the coroutine frame
  return {};
}

template <typename T>
void GrpcTask<T>::promise_type::return_value(T value) {
  value_ = std::move(value);
}

template <typename T>
void GrpcTask<T>::promise_type::unhandled_exception() {
  exception_ = std::current_exception();
}

template <typename T>
GrpcTask<T>::GrpcTask(std::coroutine_handle<promise_type> handle)
    : handle_(handle) {}

template <typename T>
GrpcTask<T>::~GrpcTask() {
  if (handle_) {
    // With suspend_always in final_suspend, we need to manually destroy
    // but only after we've retrieved the result
    if (handle_.done()) {
      handle_.destroy();
    }
  }
}

// Specialization for grpc::Status to access AsyncUnaryCallAwaiter internals
template <>
grpc::Status GrpcTask<grpc::Status>::get(grpc::CompletionQueue* cq) {
  if (!handle_) {
    throw std::runtime_error("Coroutine already destroyed");
  }
  
  // If completion queue provided, poll it directly instead of using separate thread
  // This eliminates thread overhead
  if (cq) {
    // Resume coroutine to start async operation
    handle_.resume();
    
    // Poll completion queue until coroutine completes
    while (!handle_.promise().done_.load(std::memory_order_acquire)) {
      void* tag;
      bool ok;
      // Use zero timeout for non-blocking check
      auto status = cq->AsyncNext(&tag, &ok, gpr_time_0(GPR_CLOCK_REALTIME));
      if (status == CompletionQueue::GOT_EVENT) {
        auto* awaiter = static_cast<AsyncUnaryCallAwaiter<SimpleResponse>*>(tag);
        if (awaiter) {
          // Resume the coroutine when async operation completes
          awaiter->ResumeWithCompletion(ok);
        }
      } else if (status == CompletionQueue::SHUTDOWN) {
        break;
      } else {
        // TIMEOUT - yield and try again
        std::this_thread::yield();
      }
    }
  } else {
    // Fallback: simple spin-wait if no CQ provided
    while (!handle_.promise().done_.load(std::memory_order_acquire)) {
      std::this_thread::yield();
    }
  }
  
  // Now the coroutine is done, we can safely access the result
  if (handle_.promise().exception_) {
    std::rethrow_exception(handle_.promise().exception_);
  }
  if (!handle_.promise().value_.has_value()) {
    throw std::runtime_error("Coroutine did not return a value");
  }
  return std::move(handle_.promise().value_.value());
}

template <typename T>
T GrpcTask<T>::get(grpc::CompletionQueue* cq) {
  if (!handle_) {
    throw std::runtime_error("Coroutine already destroyed");
  }
  
  // Fallback: simple spin-wait
  while (!handle_.promise().done_.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }
  
  // Now the coroutine is done, we can safely access the result
  if (handle_.promise().exception_) {
    std::rethrow_exception(handle_.promise().exception_);
  }
  if (!handle_.promise().value_.has_value()) {
    throw std::runtime_error("Coroutine did not return a value");
  }
  return std::move(handle_.promise().value_.value());
}

// Explicit template instantiation for Status
template class GrpcTask<grpc::Status>;

// Awaitable for AsyncUnaryCall
template <typename ResponseType>
AsyncUnaryCallAwaiter<ResponseType>::AsyncUnaryCallAwaiter(
    std::unique_ptr<grpc::ClientAsyncResponseReader<ResponseType>> reader,
    grpc::CompletionQueue* cq)
    : reader_(std::move(reader)),
      cq_(cq),
      response_(),
      status_() {}

template <typename ResponseType>
bool AsyncUnaryCallAwaiter<ResponseType>::await_ready() const noexcept {
  return done_.load(std::memory_order_acquire);
}

template <typename ResponseType>
void AsyncUnaryCallAwaiter<ResponseType>::await_suspend(
    std::coroutine_handle<> h) {
  handle_ = h;
  // Register completion - tag points to this awaiter so polling can resume us
  reader_->Finish(&response_, &status_, static_cast<void*>(this));
}

template <typename ResponseType>
std::pair<grpc::Status, ResponseType*>
AsyncUnaryCallAwaiter<ResponseType>::await_resume() {
  // This is called after coroutine is resumed
  // The completion queue has already been polled and status/response are set
  // If !ok_, the operation failed and response might not be valid
  if (!ok_.load(std::memory_order_acquire)) {
    // Status should already be set by gRPC to indicate failure
    status_ = grpc::Status(grpc::StatusCode::UNKNOWN, "Async operation failed");
  }
  return {status_, &response_};
}


// Explicit template instantiation
template class AsyncUnaryCallAwaiter<SimpleResponse>;

// Helper function to make async call awaitable
template <typename ResponseType>
AsyncUnaryCallAwaiter<ResponseType> MakeAsyncUnaryCall(
    BenchmarkService::Stub* stub, grpc::ClientContext* context,
    const SimpleRequest& request, grpc::CompletionQueue* cq) {
  auto reader = stub->AsyncUnaryCall(context, request, cq);
  reader->StartCall();
  return AsyncUnaryCallAwaiter<ResponseType>(std::move(reader), cq);
}

// Coroutine-based unary call
GrpcTask<grpc::Status> CoroutineUnaryCall(
    BenchmarkService::Stub* stub, grpc::ClientContext* context,
    const SimpleRequest& request, SimpleResponse* response,
    grpc::CompletionQueue* cq, AsyncUnaryCallAwaiter<SimpleResponse>* /*awaiter_ptr*/) {
  auto awaiter = MakeAsyncUnaryCall<SimpleResponse>(stub, context, request, cq);
  auto [status, result] = co_await awaiter;
  *response = std::move(*result);
  co_return status;
}

}  // namespace testing
}  // namespace grpc

