# How to Apply the Patches

The `patches/` folder contains a numbered series of git patches
(`0001-*.patch` through `0012-*.patch`) that fix the macOS Python bazel
test flakes. They were generated with `git format-patch` against
`grpc/grpc` master (commit `b10d7b3`, 2026-07-07) and must be applied in
numeric order, which `git am` does automatically.

## 1. Apply

From the root of a clean `grpc/grpc` checkout on a recent master:

```bash
git checkout master
git pull upstream master
git checkout -b fix/macos-python-bazel-flakes
git am /path/to/patches/*.patch
```

`git am` preserves the original commit messages, which contain the root
cause explanation for each change. After it finishes, `git log --oneline
-12` should show all twelve commits.

## 2. Verify

The quick check (about 10 minutes on an M-series Mac after the first
build):

```bash
bazel test --config=python --runs_per_test=16 --spawn_strategy=local \
  --test_tag_filters=-no_mac --build_tag_filters=-no_mac \
  --test_env=GRPC_VERBOSITY=debug --cache_test_results=no \
  --keep_going --test_summary=terse -- //src/python/...
```

Expected: `Executed 171 out of 171 tests: 171 tests pass.` For a
stronger check, repeat the command in a loop (each repetition needs
`--cache_test_results=no` or bazel will replay cached results). The
series was qualified with 100 repetitions; see `ROOT_CAUSE_ANALYSIS.md`
Section 6 for the results.

## 3. If a patch does not apply

Master may have drifted since `b10d7b3`. In order of preference:

```bash
# Retry the failed patch with 3-way merge (uses the blob info in the patch)
git am --abort
git am --3way /path/to/patches/*.patch

# Resolve any conflict it stops on, then continue
git add -A
git am --continue
```

The patches most likely to drift are `0008` (the 127.0.0.1 sweep, ~54
files) and `0005` (proven-offender pinning), because they touch many test
files. Conflicts there are mechanical: keep the `127.0.0.1` form of
whichever line conflicts.

## 4. What the series contains

| Patch | Subject |
|-------|---------|
| 0001 | Fix macOS flakes in Python bazel tests (leak test UDS, xds reservation + exclusive) |
| 0002 | Fix UDS path collision and tiny listen backlog in test helpers |
| 0003 | Accept CANCELLED in aio server shutdown-during-stream tests |
| 0004 | Isolate _metadata_flags_test from concurrent test servers |
| 0005 | Pin proven cross-talk offenders to 127.0.0.1 |
| 0006 | Harden compression test path against macOS loopback churn |
| 0007 | Pin _reconnect_test and aio server_test to 127.0.0.1 |
| 0008 | Pin Python test binds and dials to 127.0.0.1 across the test tree |
| 0009 | Give _leak_test a moderate timeout |
| 0010 | Run aio channel_ready_test over a Unix domain socket |
| 0011 | Bound and retry the xds interop server startup probe |
| 0012 | Mark aio wait_for_ready_test flaky |

Full root cause analysis, including what is deliberately not fixed and
the recommended upstream issues, is in `ROOT_CAUSE_ANALYSIS.md` next to
this file.

## 5. Regenerating the series

If you rebase or amend the commits, regenerate the folder with:

```bash
git format-patch upstream/master -o /path/to/patches/
```

## 6. Preflight: validate the machine before trusting results

Two machine-level conditions produce flakes that no test fix can remove.
Check both before qualifying the suite; otherwise you will be debugging
your laptop, not the code.

**a. Kernel tuning left over from old workarounds.** Verify stock values:

```bash
sysctl net.inet.tcp.msl net.inet.ip.portrange.first kern.ipc.somaxconn
# stock: 15000 / 49152 / 128. If not, reboot (values do not persist).
```

`net.inet.tcp.msl=10` in particular causes connection resets, RPCs
terminating without trailers, and connect timeouts under load.

**b. Endpoint security filtering loopback.** Corp-managed machines
running network filter agents (CrowdStrike Falcon and similar; check
`sudo pfctl -sr` for anchors) can silently drop a small fraction of
loopback SYNs. Symptom: rare `UNAVAILABLE ... getsockopt(SO_ERROR):
Operation timed out` against `127.0.0.1`. Confirm with a pure-socket
probe (no gRPC involved): open ~20,000 loopback connections in a loop
with a 5s connect timeout. A clean machine shows zero timeouts; any
timeout means the machine adds a failure floor the test suite cannot
control, and qualification should happen on CI or a clean machine
instead. This was measured on a corp laptop at ~1 timeout per 10,000
connections, which matches 1-3 spurious test failures per 16x sweep.
