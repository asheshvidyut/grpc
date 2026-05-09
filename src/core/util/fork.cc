//
//
// Copyright 2017 gRPC authors.
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
//

#include "src/core/util/fork.h"

#include <grpc/support/atm.h>
#include <grpc/support/port_platform.h>
#include <grpc/support/sync.h>
#include <grpc/support/time.h>

#include <atomic>
#include <utility>

#include "src/core/config/config_vars.h"
#include "src/core/lib/event_engine/thread_local.h"
#include "src/core/util/no_destruct.h"

//
// NOTE: FORKING IS NOT GENERALLY SUPPORTED, THIS IS ONLY INTENDED TO WORK
//       AROUND VERY SPECIFIC USE CASES.
//

namespace grpc_core {
namespace {
// The exec_ctx_count has 2 modes, blocked and unblocked.
// When unblocked, the count is 2-indexed; exec_ctx_count=2 indicates
// 0 active ExecCtxs, exex_ctx_count=3 indicates 1 active ExecCtxs...

// When blocked, the exec_ctx_count is 0-indexed.  Note that ExecCtx
// creation can only be blocked if there is exactly 1 outstanding ExecCtx,
// meaning that BLOCKED and UNBLOCKED counts partition the integers
#define UNBLOCKED(n) ((n) + 2)
#define BLOCKED(n) (n)

class ExecCtxState {
 public:
  ExecCtxState() : fork_complete_(true), blocking_in_progress_(false) {
    gpr_mu_init(&mu_);
    gpr_cv_init(&cv_);
    gpr_atm_no_barrier_store(&count_, UNBLOCKED(0));
  }

  void IncExecCtxCount() {
    // EventEngine is expected to terminate all threads before fork, and so this
    // extra work is unnecessary
    if (grpc_event_engine::experimental::ThreadLocal::IsEventEngineThread()) {
      return;
    }
    gpr_atm count = gpr_atm_no_barrier_load(&count_);
    while (true) {
      // Park if either:
      //   (a) the count has already been transitioned to BLOCKED state, or
      //   (b) BlockExecCtx() has signalled that it is trying to drain ExecCtxs
      //       in preparation for fork. (b) keeps new ExecCtxs from being
      //       created during the drain window so that the BLOCKED(1) CAS in
      //       BlockExecCtx() can actually land — without it, a workload that
      //       continuously creates ExecCtxs (e.g. macOS poll-engine workers
      //       under load, or chatty RPC traffic right up to fork) would
      //       indefinitely keep the count above UNBLOCKED(1) and the prefork
      //       handler would silently bail (see fork_posix.cc).
      if (count <= BLOCKED(1) ||
          blocking_in_progress_.load(std::memory_order_acquire)) {
        // This only occurs if we are trying to fork.  Wait until the fork()
        // operation completes before allowing new ExecCtxs.
        gpr_mu_lock(&mu_);
        if (gpr_atm_no_barrier_load(&count_) <= BLOCKED(1) ||
            blocking_in_progress_.load(std::memory_order_acquire)) {
          while (!fork_complete_) {
            gpr_cv_wait(&cv_, &mu_, gpr_inf_future(GPR_CLOCK_REALTIME));
          }
        }
        gpr_mu_unlock(&mu_);
      } else if (gpr_atm_no_barrier_cas(&count_, count, count + 1)) {
        break;
      }
      count = gpr_atm_no_barrier_load(&count_);
    }
  }

  void DecExecCtxCount() {
    if (grpc_event_engine::experimental::ThreadLocal::IsEventEngineThread()) {
      return;
    }
    gpr_atm_no_barrier_fetch_add(&count_, -1);
  }

  bool BlockExecCtx() {
    // Assumes there is an active ExecCtx when this function is called, so the
    // success state is count_ == UNBLOCKED(1) (only the prefork thread's
    // ExecCtx remains).
    //
    // The CAS UNBLOCKED(1) -> BLOCKED(1) only succeeds if at this instant no
    // other thread holds an ExecCtx. Under realistic workloads — especially
    // macOS, where gRPC falls back to ev_poll_posix because epoll is
    // unavailable, and the poll-engine worker holds an ExecCtx for a
    // significant fraction of wall time — that condition is rarely met,
    // and grpc_prefork() bails silently (see fork_posix.cc). The child then
    // inherits live gRPC threads / unfinished iomgr state and either:
    //   (a) can't shut gRPC down, exiting EX_USAGE (64) from
    //       __postfork_child(), or
    //   (b) crashes inside absl::LowLevelAlloc when a fresh thread starts in
    //       the child and the inherited skiplist is mid-update.
    //
    // To make the drain reliable, set blocking_in_progress_ first: that
    // routes new IncExecCtxCount() callers to the cv-wait path so they can't
    // keep replenishing the count while we wait for in-flight ExecCtxs to
    // finish. Then retry the CAS for up to 5 seconds. If we time out, roll
    // back the gate and broadcast so any parked waiters can proceed (the
    // caller will fall back to the same skipped-handlers behaviour as before
    // — this is a safety net, not a correctness regression).
    blocking_in_progress_.store(true, std::memory_order_release);
    gpr_mu_lock(&mu_);
    fork_complete_ = false;
    gpr_mu_unlock(&mu_);

    // 30s is generous: the drain only blocks the prefork thread, runs at
    // most once per fork(), and we'd rather pay extra latency on a rare
    // path than fall back to the skipped-handlers behavior that previously
    // produced post-fork crashes.
    gpr_timespec deadline = gpr_time_add(
        gpr_now(GPR_CLOCK_MONOTONIC), gpr_time_from_seconds(30, GPR_TIMESPAN));
    while (true) {
      if (gpr_atm_no_barrier_cas(&count_, UNBLOCKED(1), BLOCKED(1))) {
        return true;
      }
      if (gpr_time_cmp(gpr_now(GPR_CLOCK_MONOTONIC), deadline) >= 0) {
        // Roll back: re-open the gate, restore fork_complete_, wake any
        // threads parked in IncExecCtxCount().
        blocking_in_progress_.store(false, std::memory_order_release);
        gpr_mu_lock(&mu_);
        fork_complete_ = true;
        gpr_cv_broadcast(&cv_);
        gpr_mu_unlock(&mu_);
        return false;
      }
      gpr_sleep_until(gpr_time_add(gpr_now(GPR_CLOCK_MONOTONIC),
                                   gpr_time_from_millis(2, GPR_TIMESPAN)));
    }
  }

  void AllowExecCtx() {
    blocking_in_progress_.store(false, std::memory_order_release);
    gpr_mu_lock(&mu_);
    gpr_atm_no_barrier_store(&count_, UNBLOCKED(0));
    fork_complete_ = true;
    gpr_cv_broadcast(&cv_);
    gpr_mu_unlock(&mu_);
  }

  ~ExecCtxState() {
    gpr_mu_destroy(&mu_);
    gpr_cv_destroy(&cv_);
  }

 private:
  bool fork_complete_;
  // Flag that BlockExecCtx() flips to true while it's draining in-flight
  // ExecCtxs. Read by IncExecCtxCount() to decide whether to park even when
  // the count is in the UNBLOCKED band. Cleared by AllowExecCtx() (success
  // path) or BlockExecCtx() itself on timeout rollback.
  std::atomic<bool> blocking_in_progress_;
  gpr_mu mu_;
  gpr_cv cv_;
  gpr_atm count_;
};

class ThreadState {
 public:
  ThreadState() : awaiting_threads_(false), threads_done_(false), count_(0) {
    gpr_mu_init(&mu_);
    gpr_cv_init(&cv_);
  }

  void IncThreadCount() {
    gpr_mu_lock(&mu_);
    count_++;
    gpr_mu_unlock(&mu_);
  }

  void DecThreadCount() {
    gpr_mu_lock(&mu_);
    count_--;
    if (awaiting_threads_ && count_ == 0) {
      threads_done_ = true;
      gpr_cv_signal(&cv_);
    }
    gpr_mu_unlock(&mu_);
  }
  void AwaitThreads() {
    gpr_mu_lock(&mu_);
    awaiting_threads_ = true;
    threads_done_ = (count_ == 0);
    while (!threads_done_) {
      gpr_cv_wait(&cv_, &mu_, gpr_inf_future(GPR_CLOCK_REALTIME));
    }
    awaiting_threads_ = true;
    gpr_mu_unlock(&mu_);
  }

  ~ThreadState() {
    gpr_mu_destroy(&mu_);
    gpr_cv_destroy(&cv_);
  }

 private:
  bool awaiting_threads_;
  bool threads_done_;
  gpr_mu mu_;
  gpr_cv cv_;
  int count_;
};

}  // namespace

void Fork::GlobalInit() {
  if (!override_enabled_) {
    support_enabled_.store(ConfigVars::Get().EnableForkSupport(),
                           std::memory_order_relaxed);
  }
}

bool Fork::Enabled() {
  return support_enabled_.load(std::memory_order_relaxed);
}

// Testing Only
void Fork::Enable(bool enable) {
  override_enabled_ = true;
  support_enabled_.store(enable, std::memory_order_relaxed);
}

void Fork::DoIncExecCtxCount() {
  NoDestructSingleton<ExecCtxState>::Get()->IncExecCtxCount();
}

void Fork::DoDecExecCtxCount() {
  NoDestructSingleton<ExecCtxState>::Get()->DecExecCtxCount();
}

bool Fork::RegisterResetChildPollingEngineFunc(
    Fork::child_postfork_func reset_child_polling_engine) {
  if (reset_child_polling_engine_ == nullptr) {
    reset_child_polling_engine_ = new std::set<Fork::child_postfork_func>();
  }
  auto ret = reset_child_polling_engine_->insert(reset_child_polling_engine);
  return ret.second;
}

const std::set<Fork::child_postfork_func>&
Fork::GetResetChildPollingEngineFunc() {
  return *reset_child_polling_engine_;
}

bool Fork::BlockExecCtx() {
  if (support_enabled_.load(std::memory_order_relaxed)) {
    return NoDestructSingleton<ExecCtxState>::Get()->BlockExecCtx();
  }
  return false;
}

void Fork::AllowExecCtx() {
  if (support_enabled_.load(std::memory_order_relaxed)) {
    NoDestructSingleton<ExecCtxState>::Get()->AllowExecCtx();
  }
}

void Fork::IncThreadCount() {
  if (support_enabled_.load(std::memory_order_relaxed)) {
    NoDestructSingleton<ThreadState>::Get()->IncThreadCount();
  }
}

void Fork::DecThreadCount() {
  if (support_enabled_.load(std::memory_order_relaxed)) {
    NoDestructSingleton<ThreadState>::Get()->DecThreadCount();
  }
}
void Fork::AwaitThreads() {
  if (support_enabled_.load(std::memory_order_relaxed)) {
    NoDestructSingleton<ThreadState>::Get()->AwaitThreads();
  }
}

std::atomic<bool> Fork::support_enabled_(false);
bool Fork::override_enabled_ = false;
std::set<Fork::child_postfork_func>* Fork::reset_child_polling_engine_ =
    nullptr;
}  // namespace grpc_core
