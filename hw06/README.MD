# Product API — CS6650

A Go/Gin Product API with in-memory storage, Docker packaging,
Terraform deployment to AWS ECS Fargate, Locust load testing,
and local Prometheus/Grafana monitoring.

## Files

| Location | Purpose |
|---|---|
| `src/product-service.go` | Product schemas, validation, handlers, recovery |
| `src/observability.go` | Prometheus metrics and JSON request logs |
| `src/Dockerfile` | Multi-stage server image |
| `terraform/` | AWS infrastructure and image build/push |
| `docker-compose.yml` | Local application, Prometheus, and Grafana |
| `monitoring/prometheus.yml` | Prometheus scrape configuration |
| `monitoring/dashboard.json` | Exported Grafana dashboard |
| `locust/locustfile.py` | HttpUser and FastHttpUser workloads |
| `locust/results/` | CSV results, HTML reports, and log excerpts |
| `screenshots/` | API, deployment, and test evidence |

## API design

Only the Product endpoints are implemented:

| Method | Path | Responses |
|---|---|---|
| GET | `/products/{productId}` | 200, 404, 500 |
| POST | `/products/{productId}/details` | 204, 400, 404, 500 |

Products are stored in a map protected by `sync.RWMutex`.
GET copies a product under a read lock and releases the lock before
writing the response. POST checks existence and updates under an
exclusive lock.

Product 1 is seeded at startup. The specification provides no separate
catalog-creation endpoint, so this implementation interprets POST as
updating an existing product and returns 404 for an unknown ID.
The body product_id must match the URL ID.

Data is lost on restart. Multiple tasks would have independent maps,
so this assignment uses one ECS task.

The YAML also declares authentication schemes. Authentication is not
implemented in this version.

## Prerequisites

- Git
- Go 1.26 or newer for running directly
- Docker Desktop with Compose, with its engine running
- Terraform compatible with the checked-in configuration
- AWS CLI and valid AWS credentials
- Python 3.11 or newer for the recorded Locust setup

## Run directly with Go

From the repository root:

```bash
cd src
go mod download
go run .
```

The server listens on port 8080.

## Run the local monitoring stack

From the repository root:

```bash
docker compose up -d --build
docker compose ps
```

| Service | Address |
|---|---|
| Product API | http://localhost:8090 |
| Metrics | http://localhost:8090/metrics |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

Grafana initially uses admin/admin on a fresh volume.
Add a Prometheus data source with URL `http://prometheus:9090`,
then import `monitoring/dashboard.json`. Select the local Prometheus
data source if prompted; if panels show a missing data source,
select it in each panel.

Prometheus and Grafana remain local.

## Test every API response

The commands below target the Compose application.
For a direct Go process, change BASE_URL to http://localhost:8080.
For the separately tested Docker container, use port 8081.

```bash
BASE_URL=http://localhost:8090
PRODUCT='{"product_id":1,"sku":"LAPTOP-001","manufacturer":"Dell","category_id":10,"weight":1500,"some_other_id":100}'
```

### GET 200 — existing product

```bash
curl -i "$BASE_URL/products/1"
```

### POST 204 — valid update, empty response body

```bash
curl -i -X POST "$BASE_URL/products/1/details" \
  -H "Content-Type: application/json" \
  -d "$PRODUCT"
```

### GET 404 — unknown product

```bash
curl -i "$BASE_URL/products/999"
```

### POST 400 — negative weight

```bash
curl -i -X POST "$BASE_URL/products/1/details" \
  -H "Content-Type: application/json" \
  -d '{"product_id":1,"sku":"TEST","manufacturer":"Dell","category_id":10,"weight":-1,"some_other_id":100}'
```

### POST 404 — valid body for an unknown product

```bash
curl -i -X POST "$BASE_URL/products/999/details" \
  -H "Content-Type: application/json" \
  -d '{"product_id":999,"sku":"TEST","manufacturer":"Dell","category_id":10,"weight":1500,"some_other_id":100}'
```

### GET and POST 500 — controlled recovery test

From the repository root, build a fresh image and start a temporary
container with failure testing explicitly enabled:

```bash
docker build -t product-api:test ./src

docker run -d --name product-api-failure-test \
  -p 8082:8080 \
  -e ENABLE_FAILURE_TESTS=true \
  product-api:test

curl -i http://localhost:8082/products/1 \
  -H "X-Test-Failure: true"

curl -i -X POST http://localhost:8082/products/1/details \
  -H "X-Test-Failure: true"

docker stop product-api-failure-test
docker rm product-api-failure-test
```

Both requests return 500 with a JSON error. The environment flag and
header deliberately trigger a panic to test recovery. Failure testing
is disabled by default and is not enabled in the AWS configuration.

Errors contain `error` and `message`, with optional `details`.
Input validation covers required fields, positive int32 IDs,
string lengths, nonnegative integer weight, and matching URL/body IDs.

## Deploy to AWS

This starter configuration expects an existing IAM role named `LabRole`,
a default VPC, and usable subnets. It is intended for the course lab
account. Another AWS account must provide equivalent networking and
an appropriate ECS task/execution role.

Configure credentials locally. AWS Academy temporary credentials require
all three values: access key, secret key, and session token.
Do not commit credentials.

Verify access:

```bash
aws sts get-caller-identity
aws iam get-role --role-name LabRole --query Role.RoleName --output text
```

Keep Docker Desktop running. From the repository root:

```bash
cd terraform
terraform init
terraform validate
terraform plan
terraform apply
```

Review the plan and enter yes to deploy. The configuration uses
us-east-1, one Fargate task, and container port 8080.

Terraform builds the image for linux/amd64, pushes it to ECR,
and creates the ECS service after the image upload.

Wait for readiness and obtain the public IP in the same terminal:

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
SERVICE=$(terraform output -raw ecs_service_name)

aws ecs wait services-stable \
  --cluster "$CLUSTER" --services "$SERVICE" --region us-east-1

TASK_ARN=$(aws ecs list-tasks \
  --cluster "$CLUSTER" --service-name "$SERVICE" \
  --region us-east-1 --query 'taskArns[0]' --output text)

ENI_ID=$(aws ecs describe-tasks \
  --cluster "$CLUSTER" --tasks "$TASK_ARN" --region us-east-1 \
  --query "tasks[0].attachments[].details[?name=='networkInterfaceId'].value | [0][0]" \
  --output text)

PUBLIC_IP=$(aws ec2 describe-network-interfaces \
  --network-interface-ids "$ENI_ID" --region us-east-1 \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text)

curl -i "http://${PUBLIC_IP}:8080/products/1"
```

Check that TASK_ARN, ENI_ID, and PUBLIC_IP contain actual values before
using them. Public IPs may change when tasks are replaced.

Recorded deployment endpoint: http://3.85.166.240:8080.
This address is temporary.

The recorded AWS tests used the initial Product API image.
The observability screenshots and JSON logs came from the updated
application running locally through Compose.

## Load-test design

The workload selects GET with weight 4 and POST with weight 1:
approximately 80% reads and 20% writes.
Both classes wait 0.1–0.5 seconds between tasks.
Reads are weighted more heavily to model catalog browsing.
Both operations use product 1, making this a small, hot-product workload
rather than a representative large catalog.

Set up Locust from the repository root:

```bash
cd locust
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p results
```

Example AWS baseline:

```bash
locust -f locustfile.py ProductHttpUser \
  --host http://3.85.166.240:8080 \
  --headless -u 50 -r 5 -t 2m \
  --csv results/aws-http-50 \
  --html results/aws-http-50.html
```

For the comparison, use ProductFastHttpUser with the same settings
and different output filenames. Replace the host if the task IP changes.

## Recorded results

Rates below include ramp-up. Locust request rates count attempts,
including failed requests.

| Target/client | Users | Spawn/sec | Duration | Requests/sec | Failures | p95 |
|---|---:|---:|---:|---:|---:|---:|
| Local HttpUser | 50 | 5 | 2 min | 159.11 | 0% | 5 ms |
| AWS HttpUser | 50 | 5 | 2 min | 145.05 | 0% | 39 ms |
| AWS FastHttpUser | 50 | 5 | 2 min | 145.99 | 0% | 37 ms |
| AWS FastHttpUser | 500 | 25 | 2 min | 1367.13 | 0% | 44 ms |
| AWS FastHttpUser | 1000 | 50 | 2 min | 2714.78 | 0% | 54 ms |
| AWS FastHttpUser | 2000 | 100 | 2 min | 3291.50 | 17.09% | 750 ms |
| AWS FastHttpUser, diagnostic v2 | 2000 | 100 | 1 min | 3183.25 | 15.25% | 610 ms |
| AWS FastHttpUser, Docker generator | 2000 | 100 | 2 min | 3255.15 | 15.88% | 660 ms |

### HttpUser versus FastHttpUser

At 50 users, throughput differed by about 0.65%, which is too small
to establish a meaningful advantage from one run per client.
FastHttpUser uses geventhttpclient rather than the requests-based client
used by HttpUser and can reduce load-generator CPU overhead.

The intentional wait times and network round trips plausibly limited
the difference at this load. This is an interpretation, not a measured
CPU attribution.

Reference: https://docs.locust.io/en/stable/increase-performance.html

### Stress-test interpretation

Performance degraded between the 1000-user and 2000-user runs:
tail latency rose and connection failures appeared.

Diagnostic errors included:
- Native Mac: OSError(49), Can't assign requested address.
- Docker generator: OSError(99), Cannot assign requested address.
- Docker generator: ConnectionRefusedError(111).
- The Docker generator also reported high CPU usage.

These indicate load-generator/network limitations and connection
failures. They do not establish the AWS server's maximum capacity.
The exact cause of the connection refusals was not isolated.

After testing, the API returned 200 and ECS reported one running task,
zero pending tasks, and no restart event in the inspected service events.

A stronger capacity study would use distributed load generators on
separate Linux hosts and correlate results with server CPU, memory,
connection counts, and request logs.

## Observability

The local dashboard tracks each method and endpoint:

- Rate: request counter converted to requests/sec.
- Errors: non-2xx responses as a percentage of requests.
- Duration: histogram-based p50 and p95 processing latency.

Metrics use route templates rather than individual product IDs.
The /metrics endpoint is excluded from the custom API traffic metrics.

### Dashboard evidence

The local 50-user run occurred around 05:44–05:46 America/New_York
on October 19, 2026. The request-rate screenshot shows idle, loaded,
and post-load periods. Error percentage stayed at zero.

![Latency and errors](screenshots/grafana-latency-errors.png)

![Request rate](screenshots/grafana-request-rate.png)

The dashboard measures server processing time. Locust measures
client-observed request latency, including network and client overhead.
Histogram percentiles are estimates based on bucket boundaries.

### Logs from the same local run

Full excerpt: [local request logs](locust/results/local-http-50-logs.jsonl).

```json
{"time":"2026-10-19T09:46:05.803205591Z","level":"INFO","msg":"http_request","method":"POST","endpoint":"/products/:productId/details","status":204,"duration_ms":0.057875}
{"time":"2026-10-19T09:46:05.803300507Z","level":"INFO","msg":"http_request","method":"GET","endpoint":"/products/:productId","status":200,"duration_ms":0.007791}
```

Use the dashboard to spot changes in traffic, errors, and latency.
Use request logs to investigate individual requests and reconstruct
what happened during a particular period.

## Tradeoffs and future design

A map gives average O(1) lookup. RWMutex supports concurrent readers,
but writes require an exclusive lock. Higher write traffic can increase
lock contention. In-memory storage is simple but neither durable nor
shared between replicas.

A scalable store could use a load balancer with stateless Product,
Cart, Inventory, and Payment services backed by durable databases.
Inventory reservations need transactional checks; checkout and payment
operations need idempotency. A queue and outbox/saga workflow could
coordinate order processing and failures. Product reads could use
caching, while inventory correctness requires stronger coordination.
Payment data should be handled through a payment provider/tokenization.

Terraform is declarative: configuration describes the desired resources,
and Terraform plans how to reconcile actual infrastructure with that
configuration. Imperative instructions instead specify each action
in order.

## Evidence and reports

- [All screenshots](screenshots/)
- [Locust results and reports](locust/results/)
- [Grafana dashboard JSON](monitoring/dashboard.json)

HTML reports can be downloaded and opened locally.

## Cleanup

Stop the local monitoring containers:

```bash
docker compose down
```

After the AWS demonstration or grading requirements are satisfied,
remove this project's AWS resources from the terraform directory:

```bash
cd terraform
terraform plan -destroy
terraform destroy
```

Review the destruction plan. Keep Terraform state locally until cleanup
is complete. A populated ECR repository may need its test images removed
before Terraform can delete it.

Terraform state, local variable files, credentials, virtual environments,
and build outputs are excluded through .gitignore.

### Updated Grafana screenshots

The Grafana screenshots were recaptured on October 19, 2026,
around 06:32–06:34 America/New_York, during a separate local
HttpUser test with 50 users, spawn rate 5 users/second, and
a two-minute duration against http://localhost:8090.

These screenshots show the later demonstration run, rather than
the earlier local baseline reported in the results table.
Application logs covering this demonstration are saved in
[local-screenshot-run.log](locust/results/local-screenshot-run.log).

### Idle dashboard

![Grafana dashboard after the load test stopped](screenshots/grafana-idle.png)

After traffic stops, the request rate returns to zero. Latency
estimates may disappear when the query window contains no requests.
Compare this idle period with the loaded screenshots above.
