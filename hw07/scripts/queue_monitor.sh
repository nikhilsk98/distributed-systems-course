#!/usr/bin/env bash
# Poll SQS queue depth every 5s and append to a CSV.
# Usage: scripts/queue_monitor.sh <queue-url> <out.csv> [stop-when-empty-after-seconds]
set -uo pipefail
Q=$1; OUT=$2; STOP_AFTER=${3:-0}
echo "epoch,iso_time,visible,in_flight" > "$OUT"
seen_nonzero=0; zero_since=0
while true; do
  read -r v nv < <(aws sqs get-queue-attributes --queue-url "$Q" \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
    --query 'Attributes.[ApproximateNumberOfMessages,ApproximateNumberOfMessagesNotVisible]' --output text 2>/dev/null)
  now=$(date +%s)
  if [[ -n "${v:-}" ]]; then
    echo "$now,$(date -u +%Y-%m-%dT%H:%M:%SZ),$v,$nv" >> "$OUT"
    total=$((v + nv))
    if (( total > 0 )); then seen_nonzero=1; zero_since=0
    elif (( seen_nonzero )) && (( zero_since == 0 )); then zero_since=$now; fi
    if (( STOP_AFTER > 0 && seen_nonzero && zero_since > 0 && now - zero_since >= STOP_AFTER )); then exit 0; fi
  fi
  sleep 5
done
