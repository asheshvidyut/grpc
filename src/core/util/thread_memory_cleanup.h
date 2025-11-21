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

#ifndef GRPC_SRC_CORE_UTIL_THREAD_MEMORY_CLEANUP_H
#define GRPC_SRC_CORE_UTIL_THREAD_MEMORY_CLEANUP_H

#include <grpc/support/port_platform.h>
#include <grpc/support/thd_id.h>

#ifdef GPR_LINUX
#ifdef __GLIBC__

#include <malloc.h>
#include <mutex>
#include <set>
#include <vector>

namespace grpc_core {

// Thread memory cleanup utility to clean memory from non-gRPC threads.
// This helps prevent memory accumulation from external threads (e.g., file I/O
// threads) while preserving gRPC's internal thread memory caching.

class ThreadMemoryCleanup {
 public:
  // Mark a thread as a gRPC internal thread (don't clean its memory)
  static void MarkAsGrpcThread(gpr_thd_id thread_id);

  // Mark a thread as external/non-gRPC (can clean its memory)
  static void MarkAsExternalThread(gpr_thd_id thread_id);

  // Check if a thread is a gRPC thread
  static bool IsGrpcThread(gpr_thd_id thread_id);

  // Register automatic cleanup for current thread (if it's not a gRPC thread).
  // The cleanup will happen automatically when the thread exits via pthread
  // thread-local storage destructor. Returns true if registered, false if skipped.
  static bool CleanCurrentThreadIfExternal();

  // Clean memory from a specific thread's arena
  // Note: This can only be called from that thread (malloc_trim limitation)
  static bool CleanThreadArena(gpr_thd_id thread_id);

  // Get list of all external (non-gRPC) threads
  static void GetExternalThreads(std::vector<gpr_thd_id>& external_threads);

  // Automatically register cleanup for current thread if it's external.
  // Call this from gRPC entry points to ensure external threads get automatic cleanup.
  static void AutoRegisterThreadCleanup();

 private:
  ThreadMemoryCleanup() = default;
  ~ThreadMemoryCleanup() = default;
  ThreadMemoryCleanup(const ThreadMemoryCleanup&) = delete;
  ThreadMemoryCleanup& operator=(const ThreadMemoryCleanup&) = delete;

  static std::mutex threads_mutex_;
  static std::set<gpr_thd_id> grpc_threads_;
};

// Helper function to call malloc_trim() from current thread
// This releases memory from the calling thread's glibc arena back to OS
inline void TrimCurrentThreadMemory() {
#ifdef GPR_LINUX
#ifdef __GLIBC__
  malloc_trim(0);
#endif  // __GLIBC__
#endif  // GPR_LINUX
}

}  // namespace grpc_core

#endif  // __GLIBC__
#endif  // GPR_LINUX

#endif  // GRPC_SRC_CORE_UTIL_THREAD_MEMORY_CLEANUP_H

