# HW7 – Synchronous vs Asynchronous Order Processing (Parts II & III)

Flash-sale order pipeline on AWS: a Go order API behind an ALB, SNS → SQS fan-out,
a Go SQS worker on ECS Fargate, and (Part III) a Go Lambda subscribed directly to SNS.
The write-up and all results are in [REPORT.md](REPORT.md); raw artifacts are in `results/`.

## Layout

```
service/      Go order API  (POST /orders/sync, POST /orders/async, GET /health) + Dockerfile
processor/    Go SQS order processor (long polling, WORKER_COUNT goroutines)     + Dockerfile
lambda/       Go Lambda handler for SNS events (provided.al2)
terraform/    VPC, NAT, ALB, ECR, ECS (2 services), SNS, SQS, Lambda (toggleable)
locust/       locustfile.py (ORDER_ENDPOINT=sync|async)
scripts/      build/push, Lambda build, Locust runner, queue monitor, graph + screenshot export
results/      Locust HTML/CSV, queue-depth CSVs, CloudWatch PNGs, logs, curl output
```

## Prerequisites

Go 1.2x, Docker (buildx), Terraform ≥ 1.5, AWS CLI v2, Locust, Google Chrome (only for
rendering Locust reports to PNG). AWS credentials in `~/.aws/credentials` (Learner Lab; the
existing `LabRole` is used for all task/execution/Lambda roles — no IAM is created).

## Build and test locally (no AWS cost)

```bash
(cd service && go vet ./... && go build ./...)
(cd processor && go vet ./... && go build ./...)
(cd lambda && go vet ./... && go build ./...)

docker build -t hw07-service service
docker run --rm -p 8080:8080 hw07-service          # /orders/sync works without AWS
curl -X POST localhost:8080/orders/sync -d '{"customer_id":1}'

# processor against a local SQS emulator
docker run -d --name emq -p 9324:9324 softwaremill/elasticmq-native
# create a queue with --endpoint-url http://localhost:9324, then run the processor with
# AWS_ENDPOINT_URL=http://<emq-host>:9324 SQS_QUEUE_URL=... WORKER_COUNT=5
```

## Deploy

```bash
cd terraform
terraform init
# 1. ECR repos first, so images exist before the ECS services start
terraform apply -target=aws_ecr_repository.repo -target=aws_ecr_lifecycle_policy.keep3
../scripts/build_push.sh all            # docker build --platform linux/amd64 + push
# 2. Everything else (Lambda + its SNS subscription are OFF by default)
terraform apply
terraform output alb_url
```

Images are multi-stage builds on `distroless/static` (~19 MB). Cost-saving defaults: one shared
NAT gateway, no Container Insights, 1-day log retention, ECR keeps the last 3 images, ALB
deregistration delay 5 s.

## Test

```bash
export HOST=$(terraform -chdir=terraform output -raw alb_url)
scripts/run_locust.sh sync  normal sync_normal     # 5 users, 1/s, 30 s
scripts/run_locust.sh sync  flash  sync_flash      # 20 users, 10/s, 60 s
scripts/run_locust.sh async normal async_normal_w1
scripts/run_locust.sh async flash  async_flash_w1
```

Worker scaling — change only the processor service, then run the flash test and wait for
the queue to drain (the queue monitor polls SQS every 5 s into `results/queue/`):

```bash
terraform -chdir=terraform apply -target=aws_ecs_service.processor -var worker_count=20
aws ecs wait services-stable --cluster hw07-cluster --services order-processor
scripts/worker_test.sh 20
aws sqs purge-queue --queue-url "$(terraform -chdir=terraform output -raw sqs_queue_url)"  # if needed
```

Graphs and screenshots:

```bash
scripts/metric_image.py results/graphs/x.png "title" <start-iso> <end-iso> 60 '[["AWS/SQS","ApproximateNumberOfMessagesVisible","QueueName","order-processing-queue"]]'
scripts/render_locust_png.sh
```

### Part III – Lambda (never load test it)

```bash
scripts/build_lambda.sh                       # GOOS=linux GOARCH=amd64 -> lambda/build/bootstrap
terraform -chdir=terraform apply -var enable_lambda=true -var enable_lambda_subscription=true
# send only a handful of orders with curl
curl -X POST "$HOST/orders/async" -H 'Content-Type: application/json' -d '{"customer_id":1}'
aws logs filter-log-events --log-group-name /aws/lambda/hw07-order-lambda --filter-pattern REPORT
```

Keep `enable_lambda_subscription=false` during every Part II load test.

## Tear down

```bash
terraform -chdir=terraform destroy -var enable_lambda=true
# verify nothing is left
aws ec2 describe-nat-gateways --filter Name=state,Values=available,pending
aws elbv2 describe-load-balancers
aws ecs list-clusters
aws ec2 describe-addresses
aws lambda list-functions
```
