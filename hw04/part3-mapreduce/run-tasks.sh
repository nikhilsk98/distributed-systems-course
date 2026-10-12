#!/usr/bin/env bash
# Register the mapreduce-worker task definition and launch COUNT Fargate tasks
# (default 5 = 1 splitter + 3 mappers + 1 reducer). Writes their public IPs to ips.txt.
# Usage: bash run-tasks.sh [COUNT]        e.g. bash run-tasks.sh 5
set -euo pipefail
COUNT="${1:-5}"
REGION="us-west-2"
CLUSTER="${CLUSTER:-hello-cluster}"
REPO="mapreduce-worker"
TAG="${TAG:-v1}"
CPU="${CPU:-256}"        # 256 = 0.25 vCPU
MEMORY="${MEMORY:-512}"  # MB
SG_NAME="${SG_NAME:-hello-service-sg}"
DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$COUNT" -lt 3 ] || [ "$COUNT" -gt 10 ]; then
  echo "COUNT must be between 3 and 10"; exit 1
fi

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
IMAGE="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}"
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/LabRole"

# 1. Log group for container logs (ignore error if it already exists)
aws logs create-log-group --log-group-name /ecs/mapreduce-worker --region "$REGION" 2>/dev/null || true

# 2. Task definition (blueprint) - same idea as hello-task in Part II
cat > /tmp/mr-taskdef.json <<JSON
{
  "family": "mapreduce-worker",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "${CPU}",
  "memory": "${MEMORY}",
  "runtimePlatform": {"cpuArchitecture": "X86_64", "operatingSystemFamily": "LINUX"},
  "taskRoleArn": "${ROLE_ARN}",
  "executionRoleArn": "${ROLE_ARN}",
  "containerDefinitions": [{
    "name": "worker",
    "image": "${IMAGE}",
    "essential": true,
    "portMappings": [{"containerPort": 8080, "protocol": "tcp"}],
    "environment": [{"name": "AWS_REGION", "value": "${REGION}"}],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/mapreduce-worker",
        "awslogs-region": "${REGION}",
        "awslogs-stream-prefix": "worker"
      }
    }
  }]
}
JSON
REV=$(aws ecs register-task-definition --cli-input-json file:///tmp/mr-taskdef.json \
  --region "$REGION" --query 'taskDefinition.revision' --output text)
echo "Registered task definition mapreduce-worker:${REV}"

# 3. Networking: default VPC subnets + security group allowing TCP 8080
SUBNETS=$(aws ec2 describe-subnets --region "$REGION" --filters Name=default-for-az,Values=true \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ',')
SG_ID=$(aws ec2 describe-security-groups --region "$REGION" --filters Name=group-name,Values="$SG_NAME" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  echo "Security group $SG_NAME not found - creating it (TCP 8080 from anywhere)..."
  VPC_ID=$(aws ec2 describe-vpcs --region "$REGION" --filters Name=isDefault,Values=true \
    --query 'Vpcs[0].VpcId' --output text)
  SG_ID=$(aws ec2 create-security-group --region "$REGION" --group-name "$SG_NAME" \
    --description "Allow TCP 8080" --vpc-id "$VPC_ID" --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --protocol tcp --port 8080 --cidr 0.0.0.0/0 >/dev/null
fi
echo "Subnets: $SUBNETS   Security group: $SG_ID"

# 4. Launch the tasks
TASK_ARNS=$(aws ecs run-task --region "$REGION" --cluster "$CLUSTER" --launch-type FARGATE \
  --count "$COUNT" --task-definition "mapreduce-worker:${REV}" \
  --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SG_ID}],assignPublicIp=ENABLED}" \
  --query 'tasks[].taskArn' --output text)
if [ -z "$TASK_ARNS" ] || [ "$TASK_ARNS" = "None" ]; then
  echo "No tasks started. Check the ECS console for the failure reason."; exit 1
fi
echo "$TASK_ARNS" | tr '\t' '\n' > "$DIR/tasks.txt"
echo "Started $(wc -l < "$DIR/tasks.txt" | tr -d ' ') tasks. Waiting for RUNNING (about 1 minute)..."

# shellcheck disable=SC2086
if ! aws ecs wait tasks-running --region "$REGION" --cluster "$CLUSTER" --tasks $TASK_ARNS; then
  echo "Some tasks did not reach RUNNING. Open the ECS console -> task -> 'Stopped reason'."; exit 1
fi

# 5. Collect public IPs
# shellcheck disable=SC2086
ENIS=$(aws ecs describe-tasks --region "$REGION" --cluster "$CLUSTER" --tasks $TASK_ARNS \
  --query "tasks[].attachments[].details[?name=='networkInterfaceId'][].value" --output text)
# shellcheck disable=SC2086
aws ec2 describe-network-interfaces --region "$REGION" --network-interface-ids $ENIS \
  --query 'NetworkInterfaces[].Association.PublicIp' --output text | tr '\t' '\n' > "$DIR/ips.txt"

echo "Public IPs (saved to ips.txt):"
cat "$DIR/ips.txt"

# 6. Wait until every worker answers /health
echo "Checking /health on each worker..."
while read -r ip; do
  [ -z "$ip" ] && continue
  for _ in $(seq 1 20); do
    if curl -s --max-time 3 "http://${ip}:8080/health" >/dev/null; then
      echo "  ${ip}  OK"; break
    fi
    sleep 2
  done
done < "$DIR/ips.txt"
echo "Done. Roles used by driver.py: first IP = splitter, last IP = reducer, the rest = mappers."
