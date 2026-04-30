# gRPC Python Multi-Interpreter Design (PEP 684)

_Status: Draft proposal_
_Authors: gRPC Python team_
_Last updated: 2026-04-30_

## Summary

Python 3.12+ introduces per-interpreter GIL via
[PEP 684](https://peps.python.org/pep-0684/). This enables a new scaling model for
gRPC Python servers: run multiple Python sub-interpreters in one process, each with
its own GIL, while sharing one gRPC C-Core instance.

Today, Python CPU-heavy work (protobuf parse/serialize and user handlers) is
constrained by a single interpreter GIL. The proposed design targets multi-core
parallelism without requiring process-per-core deployments.

## Motivation

### The GIL bottleneck today

A gRPC Python server built on the C-Core can already handle thousands of
concurrent streams at the transport layer. However, every Python-level
operation — protobuf deserialization, servicer logic, response serialization —
is serialized by a single GIL. On a 64-core machine the Python layer becomes
the dominant throughput bottleneck.

### Why sub-interpreters over multiprocessing

| Dimension | multiprocessing | Sub-interpreters (PEP 684) |
|---|---|---|
| Memory overhead | Full process per worker | Shared C-Core, separate Python heaps |
| Data sharing | IPC / shared-memory | Byte-buffer handoff within process |
| Startup cost | Fork + re-init | Lightweight interpreter create |
| Resource sharing | Duplicate C-Core state | Single C-Core instance, shared CQs |
| Failure domain | Process crash is isolated | Interpreter crash may affect process |

Sub-interpreters offer the parallelism of multiprocessing with significantly
lower memory and IPC overhead, at the cost of tighter coupling to a shared
process address space.

## Scope

### In scope

- Experimental opt-in multi-interpreter server mode for Python 3.12+.
- Completion Queue (CQ) sharding: one or more CQs per logical worker shard.
- Shard-aware request routing with pluggable scheduling policies.
- Per-shard concurrency limiting.
- Interpreter-affine request execution in the Python layer.
- C-extension work needed to make `grpcio` sub-interpreter safe.
- Observability: per-shard stats surface for diagnostics.
- Metrics and benchmarks needed to validate scalability.

### Out of scope

- Sharing live Python objects across interpreter boundaries.
- Automatic compatibility for all third-party C extensions.
- Replacing single-interpreter or multi-process deployment models.
- Client-side (Channel) multi-interpreter support.
- Async (`grpc.aio`) multi-interpreter support (deferred to a later phase).

## Design Overview

### Execution model

```
┌──────────────────────────────────────────────────────────┐
│                    OS Process                            │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │              gRPC C-Core (shared)                  │  │
│  │  ┌─────────┐  ┌─────────┐       ┌─────────┐       │  │
│  │  │  CQ[0]  │  │  CQ[1]  │  ...  │  CQ[N]  │       │  │
│  │  └────┬────┘  └────┬────┘       └────┬────┘       │  │
│  └───────┼─────────────┼────────────────┼────────────┘  │
│          │             │                │                │
│          ▼             ▼                ▼                │
│  ┌───────────┐ ┌───────────┐    ┌───────────┐           │
│  │  Shard 0  │ │  Shard 1  │    │  Shard N  │           │
│  │  (GIL-0)  │ │  (GIL-1)  │    │  (GIL-N)  │           │
│  │           │ │           │    │           │           │
│  │ Serve loop│ │ Serve loop│    │ Serve loop│           │
│  │ Thread    │ │ Thread    │    │ Thread    │           │
│  │ pool shard│ │ pool shard│    │ pool shard│           │
│  └───────────┘ └───────────┘    └───────────┘           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

- **One process** hosts one shared gRPC C-Core instance.
- **N shards** are created, each backed by its own Completion Queue.
- In Phase 0–1 (current), shards share the main interpreter's GIL but operate
  on separate CQs with independent serve loops.
- In Phase 2+, each shard runs inside a dedicated Python sub-interpreter with
  its own GIL, enabling true parallelism.
- Each request is routed to a shard and remains shard-local for its lifetime.
  Streaming RPCs are sticky to their originating shard.

### Request lifecycle (sharded model)

```
  Client Request
       │
       ▼
  C-Core accepts connection
       │
       ▼
  Event dispatched to CQ[i]          ◄── Shard assignment at request_call time
       │
       ▼
  Serve thread for CQ[i] wakes
       │
       ▼
  _process_event_and_continue()
       │
       ├── Resolve method handler
       │   (registered method → direct lookup)
       │   (generic → iterate generic_handlers)
       │
       ├── Check concurrency limits
       │   • Global: maximum_concurrent_rpcs
       │   • Per-shard: max_concurrent_rpcs_per_shard
       │
       ├── Submit to thread pool
       │   (same pool today; per-interpreter pool in Phase 2+)
       │
       ├── On completion: _on_call_completed_for_shard(state, shard_index)
       │   • Decrements active_rpc_count and active_rpc_count_by_shard[i]
       │
       └── Re-arm: _select_next_shard_index() → request_call on next shard
```

### Dispatch and scheduling

Two scheduling policies are supported, selectable via the
`experimental_subinterpreter_scheduler` parameter:

- **`round_robin`** (default): Cycles through shards in order. Simple,
  low-overhead, good when handler latencies are uniform.
- **`least_loaded`**: Selects the shard with the lowest
  `active_rpc_count_by_shard` value. Adapts to heterogeneous handler latencies
  at the cost of a linear scan over shard counts.

The scheduler is invoked after each completed event to decide which shard should
receive the next `request_call` / `request_registered_call`.

### Shard tagging scheme

Each outstanding request slot is identified by a tag that encodes its shard
index, enabling the event loop to route completion events back to the correct
shard:

| Tag kind | Format | Example |
|---|---|---|
| Unregistered call | `request_call_{shard_index}` | `request_call_2` |
| Registered call | `{method}#{shard_index}` | `/pkg.Svc/Method#1` |
| Shutdown | `shutdown` (no shard) | `shutdown` |

`_shard_index_from_event_tag()` extracts the shard index from either format.

### Cross-worker handoff contract

- **Allowed**: serialized bytes (`bytes`) and immutable metadata tuples.
- **Disallowed**: Python object/reference transfer across interpreters.
- Add queue bounds and explicit backpressure at handoff points via
  `max_concurrent_rpcs_per_shard`.

## Public API Surface

### `grpc.server()` — new experimental parameters

```python
grpc.server(
    thread_pool,
    # ... existing parameters ...

    # Phase 0-1: CQ sharding + lifecycle scaffolding
    experimental_use_subinterpreters: bool = False,
    experimental_subinterpreter_count: Optional[int] = None,
    experimental_max_concurrent_rpcs_per_shard: Optional[int] = None,
    experimental_subinterpreter_scheduler: str = "round_robin",
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `experimental_use_subinterpreters` | `bool` | `False` | Gate for the entire feature. Must be `True` to use any other subinterpreter parameters. |
| `experimental_subinterpreter_count` | `Optional[int]` | `None` | Number of CQ shards / future sub-interpreter workers. `None` defaults to 1. Must be ≥ 1. |
| `experimental_max_concurrent_rpcs_per_shard` | `Optional[int]` | `None` | Per-shard concurrency cap. `None` means no per-shard limit (global limit still applies). Must be ≥ 1. |
| `experimental_subinterpreter_scheduler` | `str` | `"round_robin"` | Scheduling policy: `"round_robin"` or `"least_loaded"`. |

**Validation rules** (enforced in `_validate_experimental_subinterpreter_config`):

- Subinterpreter-specific params raise `ValueError` if
  `experimental_use_subinterpreters=False`.
- `experimental_use_subinterpreters=True` requires Python 3.12+.
- Invalid scheduler values raise `ValueError`.
- Emits `UserWarning` when enabled, noting experimental status.

### `Server._experimental_get_server_stats()` — diagnostics surface

Returns a dictionary with runtime shard statistics:

```python
{
    "enabled": True,
    "configured_subinterpreter_count": 4,
    "max_concurrent_rpcs_per_shard": 10,
    "scheduler": "least_loaded",
    "completion_queue_count": 4,
    "active_rpc_count": 37,
    "active_rpc_count_by_shard": (12, 10, 8, 7),
    "pending_due_tags_by_shard": (2, 2, 2, 2),
    "pending_due_tags_total": 9,  # includes shutdown tag
    "stage": "started",
}
```

## Internal Architecture Changes

### `_ServerState` extensions

The `_ServerState` class (the central mutable state of a running server) has
been extended with:

| Field | Type | Purpose |
|---|---|---|
| `completion_queues` | `List[cygrpc.CompletionQueue]` | Changed from single CQ to list of N CQs |
| `active_rpc_count_by_shard` | `List[int]` | Per-shard active RPC counters |
| `next_shard_index` | `int` | Round-robin cursor |
| `experimental_subinterpreter_config` | `_ExperimentalSubinterpreterConfig` | Validated configuration |

### Key functions (new and modified)

| Function | Role |
|---|---|
| `_request_call(state, shard_index)` | Arms a CQ slot on a specific shard |
| `_request_registered_call(state, method, shard_index)` | Arms a registered-method CQ slot on a specific shard |
| `_select_next_shard_index(state, current)` | Picks next shard per scheduling policy |
| `_on_call_completed_for_shard(state, shard_index)` | Decrements per-shard counters on RPC completion |
| `_experimental_server_stats(state)` | Collects shard diagnostics |
| `_process_event_and_continue(state, event)` | Modified to extract shard index from tags, enforce per-shard limits |
| `_start(state)` | Modified to arm all shards × all methods and spawn per-CQ serve threads |
| `_Server.__init__` | Modified to create N CQs and register all with C-Core server |

### CQ-per-shard serving model

At `_start()` time, each CQ gets its own daemon serve thread:

```python
for completion_queue in state.completion_queues:
    thread = threading.Thread(target=_serve, args=(state, completion_queue))
    thread.daemon = True
    thread.start()
```

Each serve thread independently polls its CQ. Events are dispatched through the
shared `_process_event_and_continue()` function, which uses `state.lock` for
mutual exclusion on shared state mutations.

## Cython Extension Global State Audit

For full sub-interpreter safety, mutable module-level state in the Cython
extension must be relocated to per-interpreter (module-def) state. The following
is the initial audit of globals in `cygrpc.pyx` and its `.pxi` includes:

### `fork.pyx.pxi`

| Global | Type | Sub-interpreter risk | Migration plan |
|---|---|---|---|
| `_GRPC_ENABLE_FORK_SUPPORT` | `bool` | Low — read-only after init | Move to module state |
| `_fork_handler_failed` | `bool` | **High** — written in prefork handler | Move to per-interpreter flag |
| `_fork_state` | `_ForkState` instance | **High** — mutable condition vars, counters, channel set | One `_ForkState` per interpreter |
| `_AWAIT_THREADS_TIMEOUT_SECONDS` | `int` | None — constant | No action |
| `_TRUE_VALUES` | `list` | None — constant | No action |

### `completion_queue.pyx.pxi`

| Global | Type | Sub-interpreter risk | Migration plan |
|---|---|---|---|
| `g_interrupt_check_period_ms` | `int` | Low — rarely mutated | Move to module state |

### `grpc_gevent.pyx.pxi`

| Global | Type | Sub-interpreter risk | Migration plan |
|---|---|---|---|
| `g_gevent_pool` | `object` | **High** — mutable | Move to module state |
| `g_gevent_threadpool` | `object` | **High** — mutable | Move to module state |
| `g_gevent_activated` | `bool` | **High** — mutable flag | Move to module state |
| `g_greenlets_to_run` | `queue[void*]` | **High** — C++ container | Move to module state |
| `g_greenlets_cv` / `g_greenlets_mu` | C++ sync | **High** — shared lock | Move to module state |
| `g_shutdown_greenlets_to_run_queue` | `bool` | **High** — mutable | Move to module state |
| `g_channel_count` | `int` | **High** — mutable counter | Move to module state |

### `cygrpc.pyx` (top-level)

| Global | Type | Sub-interpreter risk | Migration plan |
|---|---|---|---|
| `_LOGGER` | `Logger` | Medium — per-module logger | Re-create per interpreter |
| `_initialize()` call | one-shot | Medium — must not double-init | Guard with `grpc_is_initialized()` |

### Migration strategy

The recommended approach is Python's
[Module State Access](https://docs.python.org/3/c-api/module.html#c.PyModuleDef)
pattern (`PyModuleDef` with `m_size > 0`). For Cython, this requires:

1. Define a C struct holding all mutable module-level state.
2. Allocate it via `PyModuleDef.m_size`.
3. Access it via `PyModule_GetState(module)` in every function that reads/writes
   global state.
4. Set `Py_mod_multiple_interpreters` slot to
   `Py_MOD_PER_INTERPRETER_GIL_SUPPORTED` to declare sub-interpreter safety.

This is the most invasive part of the project and will be tackled in Phase 0.

## Implementation Plan

### Phase 0: CQ sharding + scaffolding (✅ COMPLETE)

This phase is implemented on the current branch
(`feature/python/optimize-using-subinterpretter`).

- [x] Add `_ExperimentalSubinterpreterConfig` dataclass with validation.
- [x] Add `experimental_use_subinterpreters`, `experimental_subinterpreter_count`,
      `experimental_max_concurrent_rpcs_per_shard`, and
      `experimental_subinterpreter_scheduler` parameters to `grpc.server()`.
- [x] Extend `_ServerState` with per-shard counters and CQ list.
- [x] Implement shard tag encoding/decoding
      (`_request_call_tag_for_shard`, `_registered_method_tag_for_shard`,
      `_shard_index_from_event_tag`).
- [x] Implement scheduling policies (`round_robin`, `least_loaded`) in
      `_select_next_shard_index()`.
- [x] Implement per-shard concurrency limiting in
      `_process_event_and_continue()`.
- [x] Implement per-shard RPC completion tracking via
      `_on_call_completed_for_shard()`.
- [x] Implement diagnostics via `_experimental_server_stats()`.
- [x] Multi-CQ creation and registration in `_Server.__init__`.
- [x] Per-CQ serve thread spawning in `_start()`.
- [x] Add unit tests: config validation, stats surface, scheduler selection.
- [x] Feature is gated behind `experimental_use_subinterpreters=True` with
      `UserWarning`.
- [x] No regression in default single-interpreter / single-CQ behavior.

**Files changed:**
- `src/python/grpcio/grpc/__init__.py` — public API parameters + docstrings
- `src/python/grpcio/grpc/_server.py` — sharding implementation
- `src/python/grpcio_tests/tests/unit/_server_test.py` — new test cases

### Phase 1: Sub-interpreter safety prerequisites

- [ ] Audit mutable global/static state in `grpcio` extension code (see audit
      above).
- [ ] Move state into module/interpreter-local storage using `PyModuleDef`
      with `m_size > 0`.
- [ ] Set `Py_mod_multiple_interpreters = Py_MOD_PER_INTERPRETER_GIL_SUPPORTED`
      in module definition.
- [ ] Verify repeated interpreter init/teardown behavior under stress.
- [ ] Ensure `grpc_init()` / `grpc_shutdown()` reference counting is correct
      across interpreters (C-Core must init once, shutdown when last interpreter
      exits).
- [ ] Handle `_initialize()` SSL roots callback — must only register once
      across all interpreters.

### Phase 2: Per-interpreter request execution

- [ ] Replace per-shard thread pool with per-interpreter thread pool.
- [ ] Create actual `Py_NewInterpreterFromConfig()` sub-interpreters at
      server startup with `PyInterpreterConfig.allow_threads = 1` and
      `PyInterpreterConfig.gil = PyInterpreterConfig_OWN_GIL`.
- [ ] Import servicer modules inside each sub-interpreter.
- [ ] Route deserialization + handler execution to the sub-interpreter's GIL.
- [ ] Implement byte-buffer handoff for request/response data crossing the
      dispatcher → sub-interpreter boundary.
- [ ] Add lifecycle control: startup ordering (main interpreter bootstraps,
      then sub-interpreters) and graceful drain on shutdown
      (`Py_EndInterpreter()` after all in-flight RPCs complete).

### Phase 3: Scheduling and hardening

- [ ] Add adaptive scheduler (queue-depth and tail-latency aware).
- [ ] Add tunables for queue bounds and handoff limits.
- [ ] Harden failure handling (worker failure during in-flight RPCs).
- [ ] Improve saturation signals and operator-facing diagnostics (Prometheus /
      OpenCensus metrics export).
- [ ] Per-interpreter memory usage tracking.
- [ ] Hot-reconfiguration: add/remove interpreters without server restart.

### Phase 4: Production-readiness bar

- [ ] Publish compatibility constraints and unsupported patterns (e.g., which
      C-extensions are known-incompatible).
- [ ] Publish benchmark comparisons against single-interpreter and
      multiprocessing baselines.
- [ ] Define objective promotion criteria for graduating from experimental:
  - ≥ 2× throughput improvement on CPU-bound workloads with 4 interpreters.
  - No p99 latency regression on I/O-bound workloads.
  - Soak test: 24 hours with no memory leak or crash.
- [ ] Documentation: user guide, migration guide, FAQ.

## Test Plan

### Correctness (unit tests — Phase 0 ✅)

- [x] `test_experimental_subinterpreter_count_requires_flag` — params rejected
      without gate.
- [x] `test_experimental_subinterpreter_count_must_be_positive` — zero/negative
      count rejected.
- [x] `test_experimental_subinterpreters_requires_python_3_12` — version gate.
- [x] `test_experimental_subinterpreter_per_shard_limit_must_be_positive` —
      zero/negative per-shard limit rejected.
- [x] `test_experimental_subinterpreter_scheduler_is_validated` — invalid
      scheduler string rejected.
- [x] `test_experimental_subinterpreters_warns` — `UserWarning` emitted.
- [x] `test_experimental_subinterpreter_stats_surface` — stats dict structure
      and CQ count.
- [x] `test_experimental_subinterpreter_stats_include_per_shard_limit` —
      per-shard limit reflected in stats.
- [x] `test_experimental_subinterpreter_stats_include_scheduler` — scheduler
      reflected in stats.

### Correctness (integration tests — Phase 1+)

- [ ] State isolation tests: verify that module-level state in one
      sub-interpreter does not leak to another.
- [ ] Interpreter lifecycle churn tests: create/destroy 1000 interpreters in
      sequence, verify no resource leak.
- [ ] Stress/soak tests with mixed unary and streaming traffic across shards.
- [ ] Fault-injection: kill a sub-interpreter mid-RPC, verify server continues
      serving on remaining shards.
- [ ] Shutdown ordering: verify graceful drain completes all in-flight RPCs
      before interpreter teardown.

### Performance (benchmarks — Phase 2+)

- [ ] **CPU-heavy unary** — protobuf serialize/deserialize-dominated workload,
      measure throughput scaling from 1 to N interpreters.
- [ ] **Mixed I/O + CPU** — simulated database call + protobuf work, measure
      p50/p99 latency and throughput.
- [ ] **Streaming workload** — long-lived bidirectional streams, verify shard
      affinity doesn't cause head-of-line blocking.
- [ ] **Scaling curve** — plot throughput vs. interpreter count (1..N cores) to
      identify the knee.
- [ ] **Comparison matrix**:
  - Single-interpreter baseline
  - Multiprocessing (N workers)
  - Sub-interpreters (N workers)
- [ ] Report: p50/p99 latency, requests/sec, RSS, per-core CPU utilization,
      context switches.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Unsafe mutable global state in Cython extension | Correctness failures, crashes | Systematic audit (see above); move to module state |
| Imbalanced routing hurts p99 | Latency regression | `least_loaded` scheduler; per-shard stats for diagnosis |
| Cross-worker copy overhead for small payloads | Reduced throughput gain | Benchmark to find break-even payload size; document |
| Third-party C-extension incompatibility | Limited adoption | Publish compatibility list; allow per-interpreter module loading |
| `grpc_init`/`grpc_shutdown` ref-count mismatch | C-Core double-free or leak | Single init guard; ref-count in process-global atomic |
| Fork support interaction | Deadlock in prefork handler | Disable fork support when sub-interpreters are enabled |
| gevent incompatibility | Crash or deadlock | Raise `ValueError` if both gevent and sub-interpreters are enabled |

## Alternatives Considered

### 1. Multi-CQ without sub-interpreters

**Status**: This is what Phase 0 implements. Multiple CQs with separate serve
threads can improve event-dispatch throughput but does not bypass the GIL for
Python-level work. It serves as the foundation for the full sub-interpreter
model.

### 2. `multiprocessing` with shared memory

The traditional approach. Higher memory overhead, more complex IPC, but better
failure isolation. Sub-interpreters complement rather than replace this model.

### 3. C++ server with Python callbacks via pybind11

Would bypass the GIL entirely for transport work but requires rewriting the
Python server layer. The sub-interpreter approach preserves the existing Python
API surface.

### 4. Free-threaded Python (PEP 703)

Python 3.13+ experimental `--disable-gil` builds remove the GIL entirely. This
is a longer-term solution that requires all C-extensions to be thread-safe.
Sub-interpreters provide a more controlled isolation model in the interim.

## Initial PR Acceptance Criteria

- [x] Feature is behind explicit experimental opt-in.
- [x] No regression in default single-interpreter behavior.
- [x] Config validation tests are in CI and passing.
- [x] Stats surface is available for diagnostics.
- [ ] At least one CPU-bound benchmark shows measurable multi-core scaling
      (Phase 2 milestone).
- [ ] Interpreter lifecycle safety tests are in CI and passing
      (Phase 1 milestone).

## References

- [PEP 684 — A Per-Interpreter GIL](https://peps.python.org/pep-0684/)
- [PEP 703 — Making the Global Interpreter Lock Optional](https://peps.python.org/pep-0703/)
- [CPython Sub-interpreter C API](https://docs.python.org/3.12/c-api/init.html#sub-interpreter-support)
- [Python Module State Access](https://docs.python.org/3/c-api/module.html#c.PyModuleDef)
- [gRPC C-Core Completion Queue API](https://grpc.github.io/grpc/core/grpc_8h.html)
