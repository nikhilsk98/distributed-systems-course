#!/usr/bin/env bash
# FINAL cleanup for all of HW4 (Part II + Part III). Run only after screenshots and plots are done.
# Usage: bash cleanup.sh [bucket-name]   (defaults to the name saved in bucket.txt)
set -uo pipefail
REGION="us-west-2"
CLUSTER="hello-cluster"
DIR="$(cd "$(dirname "$0")" && pwd)"
BUCKET="${1:-$(cat "$DIR/bucket.txt" 2>/dev/null || true)}"

read -r -p "Delete ALL HW4 resources (tasks, task defs, cluster, ECR repos, security group, bucket '${BUCKET:-none}', log groups)? [y/N] " ans
if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then echo "Aborted."; exit 0; fi

echo "1/7 Stopping tasks..."
ARNS=$(aws ecs list-tasks --region "$REGION" --cluster "$CLUSTER" --query 'taskArns[]' --output text 2>/dev/null)
if [ -n "$ARNS" ] && [ "$ARNS" != "None" ]; then
  for t in $ARNS; do aws ecs stop-task --region "$REGION" --cluster "$CLUSTER" --task "$t" >/dev/null; done
  # shellcheck disable=SC2086
  aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks $ARNS
fi

echo "2/7 Deregistering and deleting task definitions..."
for fam in hello-task mapreduce-worker; do
  for td in $(aws ecs list-task-definitions --region "$REGION" --family-prefix "$fam" --query 'taskDefinitionArns[]' --output text); do
    [ "$td" = "None" ] && continue
    aws ecs deregister-task-definition --region "$REGION" --task-definition "$td" >/dev/null
    aws ecs delete-task-definitions --region "$REGION" --task-definitions "$td" >/dev/null 2>&1 || true
    echo "  $td"
  done
done

echo "3/7 Deleting cluster..."
aws ecs delete-cluster --region "$REGION" --cluster "$CLUSTER" >/dev/null 2>&1 && echo "  $CLUSTER"

echo "4/7 Deleting ECR repositories (and their images)..."
for repo in hello-service mapreduce-worker; do
  aws ecr delete-repository --region "$REGION" --repository-name "$repo" --force >/dev/null 2>&1 && echo "  $repo"
done

echo "5/7 Deleting S3 bucket..."
if [ -n "$BUCKET" ]; then
  aws s3 rb "s3://$BUCKET" --force --region "$REGION" >/dev/null 2>&1 && echo "  $BUCKET"
fi

echo "6/7 Deleting log groups..."
for lg in /ecs/mapreduce-worker /ecs/hello-task; do
  aws logs delete-log-group --region "$REGION" --log-group-name "$lg" >/dev/null 2>&1 && echo "  $lg"
done

echo "7/7 Deleting security group (waits for network interfaces to be released)..."
SG_ID=$(aws ec2 describe-security-groups --region "$REGION" --filters Name=group-name,Values=hello-service-sg \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
if [ -n "$SG_ID" ] && [ "$SG_ID" != "None" ]; then
  for _ in $(seq 1 12); do
    if aws ec2 delete-security-group --region "$REGION" --group-id "$SG_ID" >/dev/null 2>&1; then
      echo "  hello-service-sg"; break
    fi
    sleep 15
  done
fi
echo "Cleanup finished. Double-check the console if anything above was not listed."
