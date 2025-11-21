//
//
// Copyright 2024 gRPC authors.
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

#include "src/core/util/thread_memory_cleanup.h"

#ifdef GPR_LINUX
#ifdef __GLIBC__

#include <grpc/support/port_platform.h>
#include <grpc/support/sync.h>
#include <grpc/support/thd_id.h>
#include <pthread.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <mutex>
#include <set>
#include <vector>

#include "absl/log/log.h"

namespace grpc_core {

// pthread key for automatic thread cleanup on exit (file-local)
static pthread_key_t cleanup_key;
static gpr_once cleanup_key_once = GPR_ONCE_INIT;

namespace {

// Destructor called automatically when thread exits
void thread_cleanup_destructor(void* value) {
  if (value == nullptr) return;
  
  gpr_thd_id thread_id = gpr_thd_currentid();
  
  // Only clean if this is NOT a gRPC thread
  if (!ThreadMemoryCleanup::IsGrpcThread(thread_id)) {
    TrimCurrentThreadMemory();
    GRPC_TRACE_LOG(resource_quota, INFO)
        << "Automatically cleaned memory from external thread " << thread_id;
  }
  
  // Free the marker value
  free(value);
}

void init_cleanup_key(void) {
  pthread_key_create(&cleanup_key, thread_cleanup_destructor);
}

}  // namespace

// Initialize thread-local storage for this thread
// This ensures the destructor is called when thread exits
// This function is accessible from ThreadMemoryCleanup methods
static void EnsureThreadCleanupRegistered() {
  gpr_once_init(&cleanup_key_once, init_cleanup_key);
  
  // Check if already registered for this thread
  if (pthread_getspecific(cleanup_key) != nullptr) {
    return;  // Already registered
  }
  
  // Set a marker value so destructor is called when thread exits
  void* marker = malloc(1);
  if (marker != nullptr) {
    pthread_setspecific(cleanup_key, marker);
  }
}

std::mutex ThreadMemoryCleanup::threads_mutex_;
std::set<gpr_thd_id> ThreadMemoryCleanup::grpc_threads_;

void ThreadMemoryCleanup::MarkAsGrpcThread(gpr_thd_id thread_id) {
  std::lock_guard<std::mutex> lock(threads_mutex_);
  grpc_threads_.insert(thread_id);
  GRPC_TRACE_LOG(resource_quota, INFO)
      << "Marked thread " << thread_id << " as gRPC thread";
  // Don't register cleanup for gRPC threads (preserve memory caching)
}

void ThreadMemoryCleanup::MarkAsExternalThread(gpr_thd_id thread_id) {
  std::lock_guard<std::mutex> lock(threads_mutex_);
  grpc_threads_.erase(thread_id);
  GRPC_TRACE_LOG(resource_quota, INFO)
      << "Marked thread " << thread_id << " as external thread";
}

bool ThreadMemoryCleanup::IsGrpcThread(gpr_thd_id thread_id) {
  std::lock_guard<std::mutex> lock(threads_mutex_);
  return grpc_threads_.find(thread_id) != grpc_threads_.end();
}

bool ThreadMemoryCleanup::CleanCurrentThreadIfExternal() {
  gpr_thd_id current_thread = gpr_thd_currentid();
  
  if (IsGrpcThread(current_thread)) {
    // Don't clean gRPC thread memory (preserve caching)
    return false;
  }
  
  // Register automatic cleanup for this external thread
  // The destructor will be called automatically when thread exits
  EnsureThreadCleanupRegistered();
  
  // Also clean immediately (optional - destructor will handle it on exit)
  TrimCurrentThreadMemory();
  GRPC_TRACE_LOG(resource_quota, INFO)
      << "Registered automatic cleanup for external thread " << current_thread;
  return true;
}

bool ThreadMemoryCleanup::CleanThreadArena(gpr_thd_id thread_id) {
  // Note: malloc_trim() can only be called from the thread itself
  // This function is a placeholder - actual cleanup must happen in the thread
  if (IsGrpcThread(thread_id)) {
    return false;
  }
  
  // In practice, the thread must call CleanCurrentThreadIfExternal() itself
  // before exiting. This function just checks if it's safe to clean.
  return true;
}

void ThreadMemoryCleanup::GetExternalThreads(
    std::vector<gpr_thd_id>& external_threads) {
  std::lock_guard<std::mutex> lock(threads_mutex_);
  // Note: This would need a way to enumerate all threads, which is complex
  // For now, we rely on threads calling CleanCurrentThreadIfExternal() themselves
  external_threads.clear();
}

void ThreadMemoryCleanup::AutoRegisterThreadCleanup() {
  gpr_thd_id current_thread = gpr_thd_currentid();
  
  // Only register for non-gRPC threads
  if (!IsGrpcThread(current_thread)) {
    EnsureThreadCleanupRegistered();
  }
}

}  // namespace grpc_core

#endif  // __GLIBC__
#endif  // GPR_LINUX

