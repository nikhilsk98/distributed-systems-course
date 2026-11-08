#!/usr/bin/env bash
# Async flash test for a given worker count; waits until the queue is empty for 30s.
# Usage: scripts/worker_test.sh <workers>
set -euo pipefail
cd "$(dirname "$0")/.."
W=$1
Q=$(cd terraform && terraform output -raw sqs_queue_url)
scripts/queue_monitor.sh "$Q" "results/queue/async_flash_w$W.csv" 30 &
MON=$!
scripts/run_locust.sh async flash "async_flash_w$W"
wait $MON
echo "queue_empty $(date -u +%Y-%m-%dT%H:%M:%SZ) async_flash_w$W" | tee -a results/test_timeline.txt
