#!/usr/bin/env bash
# Stop all running mapreduce-worker tasks (do this whenever you take a break to save lab budget).
set -euo pipefail
REGION="us-west-2"
CLUSTER="${CLUSTER:-hello-cluster}"
ARNS=$(aws ecs list-tasks --region "$REGION" --cluster "$CLUSTER" --family mapreduce-worker \
  --desired-status RUNNING --query 'taskArns[]' --output text)
if [ -z "$ARNS" ] || [ "$ARNS" = "None" ]; then
  echo "No running mapreduce-worker tasks."; exit 0
fi
for t in $ARNS; do
  aws ecs stop-task --region "$REGION" --cluster "$CLUSTER" --task "$t" --reason "stop-tasks.sh" >/dev/null
  echo "Stopped $t"
done
