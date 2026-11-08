#!/usr/bin/env bash
# Usage: scripts/run_locust.sh <sync|async> <normal|flash> <label>
set -euo pipefail
cd "$(dirname "$0")/.."
EP=$1; PROFILE=$2; LABEL=$3
HOST=${HOST:-$(cd terraform && terraform output -raw alb_url)}
if [[ $PROFILE == normal ]]; then U=5; R=1; T=30s; else U=20; R=10; T=60s; fi
mkdir -p results/locust
echo "start $(date -u +%Y-%m-%dT%H:%M:%SZ) $LABEL" | tee -a results/test_timeline.txt
ORDER_ENDPOINT=$EP locust -f locust/locustfile.py --headless -u $U -r $R -t $T --host "$HOST" \
  --html "results/locust/$LABEL.html" --csv "results/locust/$LABEL" --only-summary 2>&1 | tail -25 | tee "results/locust/$LABEL.summary.txt"
echo "end   $(date -u +%Y-%m-%dT%H:%M:%SZ) $LABEL" | tee -a results/test_timeline.txt
