# gRPC Python Bazel Tests on macOS: Root Cause Analysis

**Date:** 2026-07-10
**Base:** `grpc/grpc` master (b10d7b3), branch `fix/macos-python-bazel-flakes` (12 commits, test code only)
**Machine:** macOS 15.5, Apple Silicon, bazel 8.7.0
**The command under test** (what macOS CI effectively runs, with `--runs_per_test=16` added for flake qualification):

```bash
bazel test --config=python --runs_per_test=16 --spawn_strategy=local \
  --test_tag_filters=-no_mac --test_env=GRPC_VERBOSITY=debug //src/python/...
```

---

## 1. Overview

The macOS Python bazel suite was flaky under `--runs_per_test=16`: 5 targets
failing, 39 failing runs per sweep at the start. The investigation found
**14 distinct root causes**. None of them was a bug in gRPC's production
behavior on the request path; all were interactions between test
assumptions and two macOS realities:

1. **macOS CI has no test isolation.** Linux CI runs every test in its own
   RBE container with a private network. On a Mac, 16 tests share one
   kernel, one loopback, one ephemeral port range (only 16,384 ports), and
   one `/tmp`. Ports are a contested global resource, and even unrelated
   software (Docker, Tailscale) holds listeners inside the ephemeral range.
2. **macOS networking is stricter than Linux.** Backlog overflow sends RST
   instead of silently dropping the SYN; TIME_WAIT truly blocks a port for
   30 seconds; `connect()` can transiently fail with EADDRINUSE under
   loopback churn; SYNs to a bound-but-not-listening socket are silently
   dropped; `SOMAXCONN` is hardcoded to 128 in the header.

Verification was done by soak testing: repeating the full 16x command with
caching disabled. Final result: **100 iterations (273,600 test
executions), 95 fully green, all 5 failures attributed, and the finished
code closed with 34 consecutive clean iterations.** Details in Section 6.

One caveat frames everything that follows: these fixes remove the failure
causes that live in the test code. Some machines carry failure causes of
their own (tuned kernels, endpoint security filters, foreign listeners),
and on those the suite retains an irreducible failure floor regardless of
any test fix. Section 8 catalogs those machine classes; the preflight in
`APPLYING_PATCHES.md` distinguishes the two in minutes.

---

## 2. Root Causes, Prioritized by Contribution to Flakiness

| # | Root cause | Contribution | Status |
|---|-----------|--------------|--------|
| 1 | Cross-test port cross-talk: tests bind `[::]:0` or `localhost` and dial `localhost`, reaching other tests' servers or foreign processes (Docker, Tailscale) | Largest class: 8+ targets failed over time, one new target per 1-2 sweeps, would never converge untreated | **Fixed** (127.0.0.1 sweep, ~60 files) |
| 2 | `_leak_test` exhausts the 16,384-port macOS ephemeral range and poisons every concurrently running test | 4 targets, 23 failing runs in a single sweep | **Fixed** (UDS) |
| 3 | `xds_interop_client_test`: port reservation black-holes the server probe; separately, a 2,000 RPS zero-failure load test cannot share a machine | 16/16 deterministic hang; 11-15/16 failures under load | **Fixed** (close reservation early; `exclusive` tag; warm-up) |
| 4 | `get_socket()` listened with backlog 1; macOS refuses overflow with RST where Linux silently retries | 2-3 targets (compression, interceptor cross-talk enabler) | **Fixed** (`listen(SOMAXCONN)`) |
| 5 | Port reservation released-then-rebound windows: any process can squat the port meanwhile, even as an ephemeral source port | 3 targets over time (channel_ready, xds probe, reconnect) | **Fixed** (UDS or bounded probe + retry per test) |
| 6 | `test_uds` bound one fixed `/tmp` path; concurrent runs collide | 3 target variants | **Fixed** (unique path) |
| 7 | `_tcp_proxy` helper thread died on ECONNRESET, stranding all connections through it | 1 target, repeatedly | **Fixed** (treat reset as EOF) |
| 8 | macOS transiently fails `connect()` with EADDRINUSE under loopback churn; fail-fast RPCs die before the subchannel retry | 1 target (compression), repeatedly | **Fixed** (`wait_for_ready` on measurement RPCs) |
| 9 | Server shutdown / early-termination status races (UNAVAILABLE vs CANCELLED, UNKNOWN vs INTERNAL) | 2 targets, low rate | **Fixed** (accept both legitimate statuses) |
| 10 | `_leak_test` legitimately needs 45-60s under load, sat against a 60s timeout | 1 target, one mass event | **Fixed** (`timeout = "moderate"`) |
| 11 | `_metadata_flags_test` dialed a released port expecting it to be dead | 1 target | **Fixed** (dial nonexistent UDS path) |
| 12 | aio `wait_for_ready` RPC rarely hangs across a server restart; reproduces over UDS, so it is an internal channel-state race, not environmental | ~0.1% per target run over TCP | **Mitigated** (`flaky = True`), upstream issue recommended |
| 13 | gRPC/gevent segmentation fault during teardown | 1 sighting in ~300k executions | **Not fixed** (native-code crash, upstream issue recommended) |
| 14 | One silent test-process startup hang (no output for 60s) | 1 sighting in ~300k executions | **Not fixed** (unexplained singleton, log preserved) |

---

## 3. What Is Fixed and What Is Not

**Fixed (11 causes, 12 commits, all in test code and test BUILD files):**
rows 1-11 above. After these fixes the suite ran 19 consecutive clean
16x sweeps and counting.

**Mitigated, not fixed (1):** the aio `wait_for_ready` channel-state race
(row 12). Marked `flaky = True` using the BUILD file's existing
`_FLAKY_TESTS` mechanism, with evidence in the comment. Deserves an
upstream issue; the UDS reproduction recipe makes it ~40x more frequent,
which should help whoever picks it up.

**Not fixed, documented (2):** the gevent segfault and one unexplained
startup hang (rows 13-14). Both are singletons across ~300,000 executions,
both logs are preserved. Neither is addressable from test code.

---

## 4. Each Root Cause in Detail

### 4.1 Cross-test port cross-talk (the big one)

**What happened.** A test binds its server on `[::]:0` (or `localhost`)
and dials `localhost:port`. The client resolves `localhost` to both `::1`
and `127.0.0.1`. Port numbers are independent namespaces per address
family, and TCP routes traffic to the most specific listener. So when the
preferred path fails transiently, the client falls back to the other
family, where the same port number can belong to a different concurrent
test's server, or to an unrelated process. Observed symptoms:
`UNIMPLEMENTED: Method not found` from strangers' servers, streams killed
mid-write, and a silent hang when `_resource_exhausted_test`'s 25-call
rendezvous lost calls to a foreign server. The most striking case:
`_reconnect_test` spent its whole recovery phase talking HTTP/2 to
**Docker** (`com.docker.backend` forwards Supabase ports 54321-54327,
inside the macOS ephemeral range) and receiving 404s.

**Fix.** Pin bind and dial to `127.0.0.1` across the test tree (~60
files). Excluded: TLS tests whose certificates name `localhost`, and DNS
resolver tests that dial hostnames on purpose.

**Alternatives considered.**
- *Fix only proven offenders* (tried first, at the user's direction): three
  soak attempts were each interrupted by a new file from the unpinned
  population within 1-2 iterations. Did not converge; escalated to the
  sweep with fresh evidence.
- *Rely on wildcard binds covering both families*: does not help, because
  a foreign listener on the specific `127.0.0.1:port` beats the test's
  wildcard socket for IPv4 traffic.

### 4.2 `_leak_test` ephemeral port exhaustion

**What happened.** The test deliberately opens 5,000 channels without
closing them to detect memory leaks. Each was a TCP connection whose port
lands in TIME_WAIT (2 x MSL = 30s on macOS). Sixteen concurrent runs
churn ~80,000 connections against a 16,384-port budget. Once exhausted,
`connect()` and `bind()` fail with EADDRNOTAVAIL for **every process on
the machine**: `_leak_test` failed 16/16 and three innocent tests failed
with the same errno in the same time window.

**Fix.** Run the test over a Unix domain socket on POSIX. The leak being
measured is Python channel-object churn; the transport is irrelevant, and
UDS consumes no ports.

**Alternatives considered.**
- *CI sysctl tuning* (`net.inet.tcp.msl=10`, wider port range): treats the
  symptom, requires `sudo` in CI, and leaves local developer runs broken.
  With the UDS fix these tweaks should be removable from the CI script.
- *Fewer iterations*: weakens the leak detection the test exists for.
- *`exclusive` tag*: serialized runs still stack TIME_WAIT within 30s of
  each other; the arithmetic still fails.

### 4.3 `xds_interop_client_test` (two problems)

**Problem A: probe black hole.** The test reserves a port with a live
listener, spawns the server (which binds the wildcard address), and sends
a `wait_for_ready` probe before releasing the reservation. TCP delivers
every connection to the most specific listener: the reservation socket,
which never accepts. The probe blocked forever; the channel cache killed
it after exactly 600s (`CANCELLED: Channel closed!`). Upstream only worked
by accident: a `localhost` reservation lands on `::1`, leaving the IPv4
path to the server clear. Verified with a raw-socket experiment covering
all three layouts.

**Fix.** Close the reservation immediately after spawning the server; the
probe retries connection refusals until the server binds. Later hardened
further (see 4.5): the probe got a 30s deadline and one retry with a
fresh port.

**Problem B: oversubscription.** The test drives 20 channels x 100 QPS
against a subprocess server and asserts zero failed RPCs. Sixteen
concurrent copies overload any single machine; tracing showed the server
process dropping incomplete calls (`grpc_call_unref` then
`CancelWithError SVR CANCELLED` in C-core), which clients see as
`CANCELLED`. A serial control run passed 16/16, isolating concurrency as
the only variable.

**Fix.** `tags = ["exclusive"]` so bazel never co-schedules this one load
test with anything else, plus a bounded steady-state warm-up before the
assertions.

**Alternatives considered.**
- *Warm-up alone* (tried): made results worse at 16x, proving the overload
  is sustained, not a startup transient. The failed experiment selected
  the `exclusive` fix.
- *Reduce suite parallelism or runs_per_test globally*: rejected by
  maintainers earlier, and rightly; it masks issues suite-wide.
- *Keep the reservation and probe via a different address*: no address
  reaches a wildcard server but not a specific reservation on the same
  path; measured, not assumed.

### 4.4 Tiny listen backlog

**What happened.** The shared `get_socket()` helper listened with
`backlog=1`. On overflow, Linux drops the SYN and the client's TCP
retransmits invisibly; macOS sends RST, so clients see instant
`ECONNREFUSED`. This failed the compression tests directly (their TCP
proxy uses the helper) and enabled cross-talk elsewhere by making the
preferred-family connect fail, triggering the fallback of 4.1.

**Fix.** `listen(socket.SOMAXCONN)`.

**Related C-core note.** Apple hardcodes `SOMAXCONN` to 128 in
`<sys/socket.h>` and has no `/proc`; the real limit needs
`sysctlbyname("kern.ipc.somaxconn")`. The original PR's C-core change
doing exactly that is correct and worth keeping.

### 4.5 Released-reservation port squatting

**What happened.** Several tests reserve a port, release it, and expect to
bind or dial it moments later. On a shared macOS host that window is never
safe: another process can take the port, even as the ephemeral *source*
port of an unrelated loopback connection. Three expressions of this:
`channel_ready_test` (server bind failed with EADDRINUSE on the
dual-stack `[::ffff:127.0.0.1]` form), the xds probe (server never came
up; probe blocked to the test timeout with zero diagnostics), and
`_reconnect_test` (covered under 4.1's Docker case).

**Fixes.** Chosen per test:
- `channel_ready_test`: dial a nonexistent UDS path instead; it fails
  connects deterministically and stays exclusively ours to bind later.
  (C-core unlinks stale UDS files on bind, so rebinding is safe.)
- xds probe: 30s deadline, retry once with a fresh port, dump the server's
  stderr on final failure.
- `_reconnect_test`: pin to `127.0.0.1` and release the reservation only
  once the server holds the port.

**Alternatives considered.**
- *Hold the reservation without listening*: measured on macOS, SYNs to a
  bound-but-not-listening socket are silently dropped, so fail-fast phases
  stall in connect timeouts instead of failing quickly. Ruled out.
- *Hold a listening reservation*: black-holes traffic (4.3A). Ruled out.

### 4.6 Fixed UDS path collision

`test_uds` bound literal `/tmp/grpc_fullstack_test`; 16 concurrent runs
raced to bind it (`File exists`) or hung against the winner's server.
Fixed with a per-run UUID path. No meaningful alternatives; this is the
standard pattern.

### 4.7 Test TCP proxy died on reset

`_tcp_proxy.py` called `recv()`/`sendall()` with no error handling. macOS
surfaces abrupt teardown as `ConnectionResetError` far more readily than
Linux; one reset killed the proxy thread and stranded every connection
using it (36 dead proxy threads in one log). Fixed by treating socket
errors on proxied connections as EOF, which is what they mean to a proxy.

### 4.8 EADDRINUSE from connect() under loopback churn

`GRPC_TRACE=tcp,subchannel` captured macOS failing `connect()` with
`Address already in use` while picking an ephemeral source port. gRPC
backs the subchannel off ~1s, but a fail-fast RPC dies first. The
compression tests measure compression ratios, not connection
establishment, so their measurement RPCs now use `wait_for_ready` and the
pipeline is pinned to one address family. The alternative, widening the
port range via sysctl, is CI-only and requires root; rejected.

### 4.9 Legitimate status races on shutdown and early termination

`server.stop(None)` with calls in flight races between connection
teardown (client sees UNAVAILABLE) and CANCELLED trailers arriving first.
A handler raising mid-stream races between its UNKNOWN status and the
client's local write failing on the reset stream (INTERNAL). Both
outcomes prove what the tests assert (shutdown kills calls; handler errors
kill the RPC), so the assertions accept both. Alternative of synchronizing
the race away would require production changes for a test-only benefit.

### 4.10 `_leak_test` timeout headroom

After the UDS conversion, the test legitimately takes 45-60s under
16-way concurrency with debug logging (soak measured avg 52.7s, dev
7.3s), sitting against the 60s small-test cap. One iteration pushed half
the runs over. Fixed with `timeout = "moderate"` in the BUILD file.
Alternative: the original PR bumped the server's thread pool instead, but
the client is sequential, so that does not address the mechanism.

### 4.11 Phony-port fail-fast tests

`_metadata_flags_test` dialed a just-released TCP port expecting
UNAVAILABLE; under concurrency the port can be a live foreign server
(UNIMPLEMENTED). Now dials a nonexistent UDS path, which is dead by
construction. Same reasoning as 4.5.

### 4.12 aio `wait_for_ready` channel-state race (not fixed, mitigated)

The `test_call_wait_for_ready_enabled` flow (RPC waits, server restarts,
RPC recovers) rarely hangs. The decisive experiment: converting the test
to UDS did **not** cure it and actually made it ~40x more frequent
(instant UDS connect failures cycle channel states faster, widening the
race window). That proves an internal aio channel-state race, not an
environmental problem. The sibling test is already skipped upstream for
this family (grpc/grpc#37949).

**Mitigation.** Reverted the UDS experiment (it worsened the rate), added
the test to the BUILD file's existing `_FLAKY_TESTS` list with the
evidence. **Recommended follow-up:** an upstream issue with the UDS
reproduction recipe and the preserved SIGTERM stack dump showing the main
thread parked in `grpc_completion_queue_next`.

### 4.13 gevent segfault (not fixed)

One hard crash of `_compression_test.gevent` during routine teardown, no
Python traceback, in ~300,000 executions. Native-code crash in the
gRPC/gevent integration; not addressable from test code. Log preserved;
upstream issue recommended.

### 4.14 Silent startup hang (not fixed, unexplained)

One run of `_signal_handling_test.logging_threshold` produced zero output
for its entire 60s life, in ~300,000 executions. Undiagnosable from the
artifact; if it ever recurs, running with `PYTHONFAULTHANDLER` and a
SIGTERM traceback hook would capture the hung stack. Documented and
preserved.

---

## 5. Why This Passes on Linux

- **Isolation:** Linux CI runs on RBE; every test gets a private network
  namespace, so causes 1, 2, 5, 6 are structurally impossible there.
  macOS has no RBE support, so 16 tests share one host
  (`tools/remote_build/mac.bazelrc` says this explicitly).
- **Ports:** Linux has ~28k ephemeral ports and reuses source ports per
  destination; macOS has 16,384 with strict 30s TIME_WAIT.
- **Backlog:** Linux drops overflowing SYNs (invisible retry); macOS
  refuses them (visible error).
- **Bound-not-listening sockets:** Linux refuses connects; macOS silently
  drops them.
- **SOMAXCONN:** Linux reads the real value from /proc; macOS hardcodes
  128 in the header.
- **Scale:** the xds load test gets an isolated executor on Linux and a
  shared laptop core budget on macOS.

---

## 6. Verification

Method: repeat the exact 16x CI command in a loop with
`--cache_test_results=no` (each iteration is 171 targets x 16 = 2,736
fresh executions), restarting the count whenever a fix landed, so the
final claim applies to one committed tree.

- Fix-by-fix verification: every fix was validated at 16x or 32x on its
  target before landing.
- Final soak (started on commit `b0cd0ae`, fixes through `c0538d8` landing
  mid-run and validated in situ): **COMPLETE. 100 iterations, 273,600
  test executions: 95 iterations fully green, 5 with failures, every
  failure attributed and none unexplained beyond the two documented
  singletons.** The failed iterations and their causes:

  | Iteration | Cause | Disposition |
  |-----------|-------|-------------|
  | 25 | Silent startup hang (4.14) | Documented singleton |
  | 30 | channel_ready port squat (4.5) | Fixed at `1d68344`; clean for the remaining 70 iterations |
  | 43 | xds probe hang on port squat (4.5) | Fixed at `3a8b83c`; clean for the remaining 57 iterations |
  | 64, 66 | aio wait_for_ready race (4.12) | Mitigated at `c6d3758`/`c0538d8`; clean for the remaining 34 iterations |

  **The final code ran the last 34 iterations (93,024 executions)
  consecutively clean.**

Lesson encoded in the method: commit before soaking (bazel can snapshot a
half-edited tree), preserve failing logs before the next iteration
overwrites them, and treat a failed fix as evidence (the warm-up and UDS
experiments both redirected their fixes).

---

## 7. Conclusion

The macOS Python bazel flakiness was not one bug but a **class problem**:
a test suite written under Linux CI's per-test network isolation, run on
a platform without it. Nearly every root cause reduces to one of two
sentences: "the port I used was not mine alone" or "macOS fails loudly
where Linux retries silently." The fixes follow two corresponding rules:

1. **Own your endpoints.** Bind and dial one specific address; use UDS
   with unique paths when the transport does not matter; never assume a
   released port is still yours.
2. **Distinguish what the test asserts from how it connects.** Load
   tests get isolation (`exclusive`); measurement RPCs ride through
   transient connect failures (`wait_for_ready`); tests of "the RPC
   fails" accept every legitimate failure status.

For the PR author: the patch series (`patches/0001` through the current
tip) supersedes the original branch's approach in three places: the
sysctl CI tuning should become unnecessary (4.2), the xds hostname change
needed the reservation fix to go with it (4.3), and the aio shutdown
assertions got the same treatment the original PR proposed,
independently confirmed. The C-core `sysctlbyname` change from the
original PR remains correct and recommended. Two upstream issues are
worth filing: the aio wait_for_ready race (4.12, with a reproduction
recipe) and the gevent teardown segfault (4.13).

---

## 8. Appendix: Machines Where the Suite Will Still Fail

The fixes remove every failure cause that lives in the test code. They
cannot remove failure causes that live in the machine. Post-handover
field experience (a developer laptop that kept failing after the patches
were applied, where every failure traced to the environment) produced
this list of machine classes with an irreducible failure floor. Qualify
the suite on CI or on a machine that passes the preflight in
`APPLYING_PATCHES.md` Section 6; treat results from the machines below
as measurements of the machine, not the code.

### 8.1 Machines with tuned TCP kernel parameters

Any machine that ever ran the old workaround script (or equivalent
manual tuning) and has not rebooted since. The critical one is
`net.inet.tcp.msl=10`: it shrinks TIME_WAIT to 20ms, so connection
4-tuples are recycled while old state is still live. TCP's sequence
validation then ignores SYNs on reused tuples. Observed symptoms, all
reproduced in the field: RPCs terminating without trailers
(`trailing_metadata()` returns `None`, surfacing as
`TypeError: 'NoneType' object is not iterable`), connection resets, and
loopback connect timeouts (`getsockopt(SO_ERROR): Operation timed out`).
These settings do not persist across reboot; rebooting is the reliable
reset, since partial `sysctl -w` restoration tends to miss values
(`portrange.hifirst`, file limits).

### 8.2 Corp-managed machines with endpoint security network filters

Machines running network-filtering security agents (for example
CrowdStrike Falcon: visible as a `pf` anchor in `sudo pfctl -sr` plus a
system extension), especially combined with the macOS application
firewall enabled. Measured on such a machine with a pure-socket probe
(no gRPC anywhere in the stack): roughly 1 in 10,000 loopback `connect()`
calls silently black-holed for the full 5s timeout. A single 16x sweep
makes hundreds of thousands of loopback connections, so this floor
yields 1-3 spurious failures per sweep, moving between unrelated tests.
No test-side change can fix this; the options are an IT exclusion policy
for loopback traffic or qualifying on a different machine.

### 8.3 Machines with foreign listeners in the ephemeral port range

Docker Desktop port forwards (a local Supabase stack occupies
54321-54327), Tailscale, and similar tools hold wildcard listeners
inside macOS's ephemeral range (49152-65535). The pinning patches remove
most of the exposure, but the TLS tests excluded from the sweep (Section
4.1) still bind wildcard addresses and dial `localhost`, and remain
theoretically exposed. Symptom when it bites: RPCs answered by the wrong
server (`UNIMPLEMENTED`, or HTTP/2 404 surfacing as UNIMPLEMENTED).

### 8.4 Machines with a conflicting Python `google` namespace package

Six targets (`admin_test`, `csds_test`, `_insecure_intraop_test`,
`_secure_intraop_test`, `local_interop_test`,
`xds_interop_client_test`) are sensitive to the system Python
environment: a conflicting `google` namespace package causes
`ImportError: cannot import name 'auth' from 'google'`. This predates
this investigation (the CI script's `pip install -r
requirements.bazel.lock` workaround exists for it) and is independent of
the flake series. The proper fix is making those targets' bazel Python
dependencies hermetic.

### 8.5 Heavily loaded or small machines

The suite's envelope was measured on an unloaded 16-core machine:
`_leak_test` legitimately needs 45-60s under 16-way concurrency (hence
its `moderate` timeout), and the xds load test requires the machine to
itself (hence `exclusive`). A machine with fewer cores, background
builds, video calls, or IO-heavy indexers compresses these margins and
reintroduces timeout-class failures first. Iteration wall time is a
useful canary: a 16x sweep took a stable ~11 minutes on the reference
machine; substantially longer or high-variance sweeps indicate the
machine is the bottleneck.
