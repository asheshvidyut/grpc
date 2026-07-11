#!/bin/bash
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1

# Refuse to run on a tuned kernel; results would be meaningless.
[ "$(sysctl -n net.inet.tcp.msl)" = "15000" ] || { echo "FATAL: net.inet.tcp.msl != 15000. Reboot first."; exit 1; }
[ "$(sysctl -n net.inet.ip.portrange.first)" = "49152" ] || { echo "FATAL: portrange.first != 49152. Reboot first."; exit 1; }

echo "Tree state:"; git log --oneline -3; git status --short | head -5

mkdir -p /tmp/grpc_soak_logs
for i in $(seq 1 100); do
  echo "===== Run $i of 100 ====="
  bazel test --config=python --runs_per_test=16 --spawn_strategy=local \
    --test_tag_filters=-no_mac --build_tag_filters=-no_mac \
    --test_env=GRPC_VERBOSITY=debug --cache_test_results=no \
    --keep_going --test_summary=terse -- //src/python/... \
    > "/tmp/grpc_soak_logs/run_$i.log" 2>&1
  RC=$?
  tail -3 "/tmp/grpc_soak_logs/run_$i.log"
  if [ $RC -ne 0 ]; then
    echo "Run $i FAILED. Bazel log: /tmp/grpc_soak_logs/run_$i.log"
    grep "^FAIL\|TIMEOUT" "/tmp/grpc_soak_logs/run_$i.log" | head -5
    echo "Copy the referenced test.log files before the next run overwrites them."
    exit 1
  fi
done
echo "All 100 runs green."

