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

#ifndef GRPC_SRC_CORE_UTIL_THREAD_ARENA_TRACKER_H
#define GRPC_SRC_CORE_UTIL_THREAD_ARENA_TRACKER_H

#include <grpc/support/port_platform.h>
#include <grpc/support/thd_id.h>

#ifdef GPR_LINUX
#ifdef __GLIBC__

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <map>
#include <mutex>
#include <string>

namespace grpc_core {

// Thread-Arena tracker to identify which threads allocate memory in which
// glibc arenas. This helps debug memory leaks by showing which threads are
// creating memory that accumulates in arenas.
class ThreadArenaTracker {
 public:
  // Get singleton instance
  static ThreadArenaTracker& Instance() {
    static ThreadArenaTracker instance;
    return instance;
  }

  // Record a memory allocation from a specific thread
  // size: size of allocation in bytes
  // source: source of allocation (e.g., "Arena", "MakeSlice", "gpr_malloc")
  void RecordAllocation(size_t size, const char* source);

  // Record a memory deallocation from a specific thread
  void RecordDeallocation(size_t size);

  // Get current thread's arena number (glibc internal)
  // Returns -1 if unable to determine
  int GetCurrentThreadArena();

  // Get statistics for current thread
  struct ThreadStats {
    gpr_thd_id thread_id;
    int arena_number;
    size_t total_allocated;
    size_t total_freed;
    size_t net_allocated;
    std::map<std::string, size_t> allocations_by_source;
  };

  ThreadStats GetThreadStats(gpr_thd_id thread_id);
  std::map<gpr_thd_id, ThreadStats> GetAllThreadStats();

  // Log current state (for debugging)
  void LogState(const char* label);

 private:
  ThreadArenaTracker() = default;
  ~ThreadArenaTracker() = default;
  ThreadArenaTracker(const ThreadArenaTracker&) = delete;
  ThreadArenaTracker& operator=(const ThreadArenaTracker&) = delete;

  struct ThreadData {
    gpr_thd_id thread_id;
    int arena_number;
    std::atomic<size_t> total_allocated{0};
    std::atomic<size_t> total_freed{0};
    std::map<std::string, size_t> allocations_by_source;
    std::mutex mutex;
  };

  ThreadData* GetOrCreateThreadData();
  int GetArenaForThread(gpr_thd_id thread_id);

  std::mutex threads_mutex_;
  std::map<gpr_thd_id, std::unique_ptr<ThreadData>> threads_;
};

}  // namespace grpc_core

#endif  // __GLIBC__
#endif  // GPR_LINUX

#endif  // GRPC_SRC_CORE_UTIL_THREAD_ARENA_TRACKER_H

