#!/usr/bin/env bash
# Build the worker image for linux/amd64 and push it to ECR (repo: mapreduce-worker).
# Usage: bash deploy.sh            (tag defaults to v1; TAG=v2 bash deploy.sh to override)
set -euo pipefail
REGION="us-west-2"
REPO="mapreduce-worker"
TAG="${TAG:-v1}"
cd "$(dirname "$0")/worker"

if ! aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1; then
  echo "Creating ECR repository $REPO..."
  aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
fi
ECR_URL=$(aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" \
  --query 'repositories[0].repositoryUri' --output text)
echo "ECR repo: $ECR_URL"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ECR_URL%%/*}"

if ! docker buildx inspect singlearch >/dev/null 2>&1; then
  docker buildx create --name singlearch --bootstrap >/dev/null
fi

docker buildx build --builder singlearch --platform linux/amd64 --push -t "${ECR_URL}:${TAG}" .

echo
echo "Pushed ${ECR_URL}:${TAG}"
aws ecr list-images --repository-name "$REPO" --region "$REGION" --query 'imageIds[*].imageTag' --output table
