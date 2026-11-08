#!/usr/bin/env bash
# Build linux/amd64 images and push them to ECR. Usage: scripts/build_push.sh [api|processor|all]
set -euo pipefail
cd "$(dirname "$0")/.."
REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REG="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$REG" >/dev/null
what=${1:-all}
if [[ $what == all || $what == api ]]; then
  docker build --platform linux/amd64 -t "$REG/hw07-order-api:latest" service
  docker push -q "$REG/hw07-order-api:latest"
fi
if [[ $what == all || $what == processor ]]; then
  docker build --platform linux/amd64 -t "$REG/hw07-order-processor:latest" processor
  docker push -q "$REG/hw07-order-processor:latest"
fi
