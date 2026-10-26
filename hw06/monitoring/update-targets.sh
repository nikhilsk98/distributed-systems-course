#!/bin/bash
CLUSTER=CS6650L2-cluster
OUT="$(cd "$(dirname "$0")" && pwd)/targets.json"

while true; do
  TASKS=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns' --output text)
  IPS=""
  if [ -n "$TASKS" ] && [ "$TASKS" != "None" ]; then
    ENIS=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASKS --query "tasks[].attachments[0].details[?name=='networkInterfaceId'].value" --output text)
    IPS=$(aws ec2 describe-network-interfaces --network-interface-ids $ENIS --query 'NetworkInterfaces[].Association.PublicIp' --output text 2>/dev/null)
  fi
  TARGETS=""
  for ip in $IPS; do
    [ "$ip" != "None" ] && TARGETS="$TARGETS\"$ip:8080\","
  done
  TARGETS="${TARGETS%,}"
  echo "[{\"targets\":[${TARGETS}],\"labels\":{\"job\":\"product-api\"}}]" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
  echo "$(date +%T) targets: $IPS"
  sleep 15
done