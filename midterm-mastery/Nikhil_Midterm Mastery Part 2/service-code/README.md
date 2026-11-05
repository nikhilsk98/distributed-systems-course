# Service code changes (patch)

This folder holds **only my changes** to the course's file-transfer play-service, as one patch. It does not contain the service itself.

- **Full runnable code:** <https://github.com/nikhilsk98/file-transfer-playservice/tree/midterm-instrumentation>
- **Origin of the service:** the service is the course's upstream code by its original author (<https://github.com/dnunez02/file-transfer-playservice>). Only the changes in this patch are mine.
- **Why only a patch:** the upstream repository has no licence file, so I did not copy its source files here. The patch contains my added and changed lines, plus the few lines of upstream context that `git diff` needs to apply it.
- **Why each change was made, and its effect on the measurements:** see [`../service-changes.md`](../service-changes.md).

## Contents

| File | What |
|---|---|
| [`service-changes.patch`](service-changes.patch) | Output of `git diff main..midterm-instrumentation` in the fork. 14 files, +583 / −34 lines |

## How to apply the patch

On a checkout of upstream `main`:

```sh
git clone https://github.com/dnunez02/file-transfer-playservice.git
cd file-transfer-playservice
git apply --check /path/to/service-changes.patch   # dry run
git apply /path/to/service-changes.patch
```

The patch was made against upstream `main` at commit `eeeda84`, which is also the fork's `main`.

## Changed files

Section numbers refer to [`../service-changes.md`](../service-changes.md).

| File | Status | Change |
|---|---|---|
| `metrics/metrics.go` | added | New package: process-wide counters and gauges printed every 10 s as CloudWatch Embedded Metric Format, plus the `QUIET` switch (§4, §5) |
| `transfer-client/udp/udp-client.go` | modified | Retry budget read from `RETRY_ROUNDS`, `OPEN_ATTEMPTS` and `READ_TIMEOUT_MS` (same defaults); `FetchWithStats` fills a per-fetch `Stats` struct; quieter missing-chunk logs (§1, §2, §5) |
| `transfer-frontend/gateway/gateway.go` | modified | `X-*` stats response headers, one JSON log line per request, optional per-request budget override, gateway EMF counters; `New` keeps its old signature (§3, §4) |
| `transfer-frontend/main.go` | modified | Wires in the instrumented fetcher and `ALLOW_BUDGET_OVERRIDE`, logs the retry budget at startup, starts the metrics loop (§3, §4) |
| `transfer-server/protocol/server.go` | modified | Backend EMF counters (OPEN/RETY requests, overload drops, S3 fetch count and time, busy workers, queued jobs); `QUIET` mode; errors always logged (§4, §5) |
| `transfer-server/udp/udp-server.go` | modified | Starts the backend metrics loop and logs the loss/worker/queue config as one JSON line (§4) |
| `transfer-server/udp/udp-transport.go` | modified | Counters for simulated send/receive drops, datagrams sent and send errors; skips per-datagram loss logs when quiet (§4, §5) |
| `scripts/common.sh` | modified | Default `AWS_REGION` changed from `us-west-2` to `us-east-1` (§6) |
| `terraform/main.tf` | modified | Provider region from `var.region`; `default_tags { Project = "cs6650-midterm" }` (§6) |
| `terraform/variables.tf` | modified | New variables: `region`, `quiet_logs`, `open_attempts`, `retry_rounds`, `read_timeout_ms`, `allow_budget_override`, `gateway_queue_wait`, `scale_out_cooldown`, `scale_in_cooldown`, `deregistration_delay` (§6) |
| `terraform/ecs.tf` | modified | Container Insights on the cluster; new env vars passed to the tasks; region from `var.region` instead of hard-coded `us-west-2` (§6) |
| `terraform/autoscaling.tf` | modified | Scale-out and scale-in cooldowns from variables (defaults unchanged at 60/120 s) (§6) |
| `terraform/alb.tf` | modified | Gateway target-group deregistration delay from `var.deregistration_delay` (default unchanged at 60 s) (§6) |
| `terraform/nlb.tf` | modified | Backend target-group deregistration delay from `var.deregistration_delay` (default unchanged at 60 s) (§6) |
