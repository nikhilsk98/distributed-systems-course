# Service changes (what I edited in the fork and why)

All edits are on branch **`midterm-instrumentation`** of <https://github.com/nikhilsk98/file-transfer-playservice>. Compare against upstream `main` with `git diff main..midterm-instrumentation`. The Go source is not copied here; only small snippets are shown.

**Design rule:** at default settings, the protocol behaviour (chunking, OPEN/RETY logic, timeouts, queue sizes, loss model) is unchanged. The edits only (a) make existing constants configurable, (b) expose what happened, and (c) remove per-datagram log spam.

## 1. Client retry budget made configurable: `transfer-client/udp/udp-client.go`

**What:** `maxRetryRounds` and `maxOpenAttempts` were Go constants, and `readTimeout` was a test-only variable. They are now read from env vars `RETRY_ROUNDS`, `OPEN_ATTEMPTS` and `READ_TIMEOUT_MS`, with the same defaults (5, 5, 2000 ms). A new `FetchWithStats(addr, name, Budget)` accepts a per-call budget, and the old `Fetch` calls it with the defaults.

```go
-const (
-	maxRetryRounds  = 5
-	maxOpenAttempts = 5
-	maxChunks       = 65536
-)
+const maxChunks = 65536
+var (
+	maxRetryRounds  = envInt("RETRY_ROUNDS", 5)
+	maxOpenAttempts = envInt("OPEN_ATTEMPTS", 5)
+	readTimeout = time.Duration(envInt("READ_TIMEOUT_MS", 2000)) * time.Millisecond
+)
```

**Why:** E2 varies the retry budget. Without this change, every budget would need a code change, an image rebuild and a redeploy.

**Effect on measurements:** none at defaults. The control flow of `fetch` is unchanged apart from the loop bounds now coming from `budget`.

## 2. Per-fetch statistics: same file

**What:** a `Stats` struct is filled in during the fetch, even when it fails:
- OPEN attempts
- retry rounds
- RETY datagrams sent
- redials
- NUM_CHUNKS
- datagrams received and duplicates
- chunks missing after OPEN and at the end

```go
+		stats.RetryRounds++
 		for _, id := range missing {
+			stats.RetyRequests++
 			_, err := fmt.Fprintf(conn, "RETY %v %v", filename, id)
```

**Why:** the service had no way to report how many retries a transfer needed. This is the core measurement for E1 and E2.

**Effect:** a few integer increments per datagram, which is negligible.

## 3. Gateway exposes stats: `transfer-frontend/gateway/gateway.go` and `main.go`

**What:**
- **Response headers** on every `/files` response, including 503 and 504: `X-Open-Attempts`, `X-Retry-Rounds`, `X-Rety-Sent`, `X-Missing-After-Open`, `X-Missing-At-End`, `X-Chunks`, `X-Datagrams-Received`, `X-Queue-Wait-Ms`, `X-Fetch-Ms`, `X-Budget`, `X-Task`. Locust records them per request.
- **One JSON log line per request** (`{"evt":"fetch",...}`), queryable with CloudWatch Logs Insights.
- **Budget override:** when `ALLOW_BUDGET_OVERRIDE=1`, the query parameters `open_attempts`, `retry_rounds` and `read_timeout_ms` (bounded to 1–50, 0–50 and 50–10000) override the budget for that request only.
- `gateway.New(...)` keeps its old signature, and `NewInstrumented(...)` adds the stats fetcher. The existing unit tests pass unchanged.

```go
+		file_data, stats, err := fetch(upstream, name, budget)
+		fetchTime := time.Since(started)
+		setStatsHeaders(c, stats, queued, fetchTime)
```

**Why:** the headers let the load generator attribute retries, queueing and latency to each request. The override lets E2 sweep 9 budgets on the same running tasks with **no redeploys**. That saves about 30 minutes and removes "different tasks / different placement" as a confound.

**Effect:** the override is test-only. It is an experiment hook and should be off (`ALLOW_BUDGET_OVERRIDE=0`) in any real deployment, because it lets a client make the gateway try harder. When the override is absent, the defaults apply exactly as before.

## 4. CloudWatch EMF counters: new package `metrics/`, wired into gateway and backend

**What:** every 10 s, each task prints one JSON line in CloudWatch **Embedded Metric Format**. CloudWatch Logs turns it into custom metrics in namespace `FileTransfer` with dimension `Service`.
- **Gateway counters:** `Requests`, `Responses200`, `RejectedBusy503`, `Timeout504`, `OpenAttempts`, `RetryRounds`, `RetyRequestsSent`, plus the gauges `InFlight` and `WaitingForSlot` (max per interval).
- **Backend counters** (`transfer-server/protocol/server.go`, `udp/udp-transport.go`): `OpenRequests`, `RetyRequests`, `OverloadDrops` (job queue full), `MessagesAccepted`, `DatagramsSent`, `SimulatedSendDrops`, `SimulatedRecvDrops`, `SourceFetches`, `SourceFetchMsTotal`, plus the gauges `BusyWorkers` and `QueuedJobs`.

```go
 		select {
 		case jobs <- job{message: message, from: from}:
+			mReceived.Inc()
 		default:
+			mOverload.Inc()
 			printDebugMessage("Overloaded: dropped incoming datagram")
```

**Why:** the NLB exposes no per-request metric, so the backend tier is otherwise a black box. Overload drops turned out to be the key mechanism behind E1 and E2. EMF needs no CloudWatch agent and no extra IAM permissions, which matters because LabRole is fixed.

**Effect:** atomic counter increments and one log line per 10 s, which is negligible.

## 5. `QUIET=1` mode for per-datagram logs: server, transport and client

**What:**
- With `QUIET=1`, these per-message lines are skipped: `DEBUG: Simulated loss: dropped ...`, `DEBUG: Processing command ...` and `Overloaded: dropped ...`. The counters above replace them.
- "Error fetching file" is always logged (as `ERROR:`).
- The client's per-round "Missing chunks [...]" line logs only the count, and the final error message lists only the first 10 missing IDs.

**Why:** at 20% loss with a 4 MB file the server writes about 26,000 log lines per OPEN. That would cost CloudWatch Logs ingestion fees, slow the 0.25-vCPU tasks, and make the logs unusable.

**Effect on measurements (threat to validity):** upstream code writes one stderr line per dropped or handled datagram. Quiet mode removes that work, so the backend is slightly *faster* than stock under loss. The comparison stays fair because every experiment ran in quiet mode. Absolute CPU numbers would be a bit higher with stock logging.

## 6. Infrastructure (Terraform, `terraform/*.tf`)

| Change | Why |
|---|---|
| Region is now a variable `region` (default `us-east-1`), replacing four hard-coded `us-west-2` (provider, `AWS_REGION`, two `awslogs-region`); `scripts/common.sh` default changed too | The assignment requires us-east-1 |
| `default_tags { Project = "cs6650-midterm" }` on the provider | Tag-based leftover search at teardown |
| New variables passed as env: `open_attempts`, `retry_rounds`, `read_timeout_ms`, `allow_budget_override`, `gateway_queue_wait`, `quiet_logs` | Expose the new knobs |
| `scale_out_cooldown`, `scale_in_cooldown`, `deregistration_delay` made variables (defaults unchanged at 60/120/60). I used `deregistration_delay = 30` | Faster env-change rollouts between cells (old tasks drain in 30 s instead of 60 s). Transfers in these experiments finish in under 30 s |
| Container Insights enabled on the cluster | `RunningTaskCount` / `DesiredTaskCount` per service for E3 |

### Runtime configuration changes made during the experiments (not code)

| When (UTC) | Change | How | Why |
|---|---|---|---|
| 07:56–08:12 | Diagnosis only: gateway set to 1 vCPU / 2 GB, then `UPSTREAM` set to a backend task IP, then restored to stock (revision 5) | `scripts/common.py set_service_env` (new task-definition revisions) | Locate the native datagram loss ([notes/native-loss-diagnosis.md](notes/native-loss-diagnosis.md)). No experiment data was collected on these revisions |
| per E1 level and E2 | Backend `SEND_LOSS`/`RECV_LOSS` | new backend task-definition revision + `update-service` | The experiment variable |
| 10:21, before E3 | **Autoscaling scale-in cooldown 120 s → 60 s** for both policies (scale-out stays 60 s) | `terraform apply -target=aws_appautoscaling_policy.* -var scale_in_cooldown=60` | A time box, so that a scale-in can start within the E3 observation window. Recorded in [`results/E3/scaling_policies_used.txt`](results/E3/scaling_policies_used.txt) |

**Incident:** that targeted `terraform apply` also re-applied the ECS services (dependencies of the policy targets) and rolled them back to task-definition revision 1, which has 0% loss, in the middle of E2. I caught it within a minute. The new tasks started at 10:22:08Z and I stopped the drivers at 10:22:12Z. I re-pointed the services to backend:6 / gateway:5 and waited for stability. I deleted the one interrupted run (`E2/f64k_open05_rounds05/trial3`) and re-ran it. No completed run overlapped the wrong tasks: the previous run ended at 10:22:08Z, before the new tasks could pass health checks. The incident is logged in [`results/run_incidents.txt`](results/run_incidents.txt). **Lesson:** mixing CLI-managed task definitions with Terraform-managed services means any `terraform apply` can silently revert experiment settings.

**IAM:** the stack already used the existing `LabRole` for the task and execution roles (`data "aws_iam_role" "lab"`). No IAM roles are created. Application Auto Scaling worked with its service-linked role in this Learner Lab account.

**S3:** the bucket `file-transfer-719602427292-nsk` was created with the CLI (the voclabs user can create buckets) and tagged `Project=cs6650-midterm`. Terraform only looks it up.

**Images:** built with `--platform linux/amd64` by `scripts/build.sh`, to match the `X86_64` runtime in the task definitions, and pushed to ECR by `scripts/deploy.sh`.

## Validation of the changes

- `gofmt`, `go vet ./...` and `go test ./...` all pass on the branch, including the upstream tests for the client, gateway and protocol.
- Local run at 10% loss: the headers report sensible values. One example: `X-Missing-After-Open: 98`, `X-Retry-Rounds: 3`, `X-Rety-Sent: 136`, `X-Missing-At-End: 0`, with the file byte-identical. The EMF lines parse as JSON with the `_aws` block.
