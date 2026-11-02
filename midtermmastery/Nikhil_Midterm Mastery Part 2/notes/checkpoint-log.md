# Checkpoint log (autonomous mode)

The assignment ran in autonomous mode. At each checkpoint the plan and estimate are written here, and work goes ahead as long as the total AWS cost stays under $15 and total experiment runtime stays under 5 h.

---

## CHECKPOINT 1: parameters and experiment plan (2026-11-02, ~02:50 local)

The full parameter table is in [service-overview.md](service-overview.md#tunable-parameters).

### What the code review showed (this drove the design)

1. **Chunks are 64 B.** A 64 KB file is 1,024 datagrams, 1 MB is 16,384, and 4 MB is 65,536 (the client cap `maxChunks`).
2. **Every round ends with a 2 s quiet wait** (`readTimeout`). Even a 12-byte file takes about 2.0 s, which was measured locally.
3. **Every `RETY` re-downloads the whole file from S3** (`handleRetry` → `source.Fetch`), and the backend's job queue holds only `workers*4 = 32` messages. Extra datagrams are dropped as "Overloaded". A round of N `RETY`s can therefore recover only about 40 chunks per backend, whatever N is. A local probe at 10% loss saw 18,210 overload drops against 4,598 `RETY`s served.
4. **The gateway allows `MAX_INFLIGHT = 4` transfers per task**, and each transfer takes at least 2 s. One task's ceiling is therefore about 2 req/s, or ~120 req/min, and the scaling target is 100 req/min/target. Queued requests get a 503 after 5 s.

### Experiments

| | E1: loss × file size | E2: retry budget | E3: scaling under load |
|---|---|---|---|
| Question | Where does the default budget break down, and does file size amplify loss? | Is the default 5 opens / 5 rounds well chosen? | Do gateway (ALB req/target) and backend (CPU) autoscaling react to the real bottleneck? |
| Varied | loss % ∈ {0, 1, 5, 10, 20} (send = recv) × size ∈ {64 KB, 1 MB, 4 MB} | sweep A: retry rounds ∈ {1, 2, 3, 5, 10, 20} at 64 KB and 256 KB; sweep B: open attempts ∈ {1, 2, 5, 10} at 64 KB | load steps of 4 → 8 → 16 → 32 → 64 users (3 min each); config A (defaults, `MAX_INFLIGHT=4`) vs config B (`MAX_INFLIGHT=16`) |
| Fixed | budget 5/5/2 s, 2 Locust users, 2 gateway + 2 backend tasks, `WORKERS=8` | loss 10%, 2 users, `WORKERS=8` | 64 KB file, 1% loss, default thresholds (100 req/min/target, CPU 60%), cooldowns 60 s / 120 s, min 2 / max 4 |
| Trials | 3 × 60 s per cell (15 cells) | 3 × 60 s per cell (15 cells) | 1 run per config (a time series; variance comes from within-step samples) |
| Metrics | success %, p50/p95/p99, `RETY`s, rounds, overload drops | success % vs p95/p99, `RETY`s and datagrams per success | RunningTaskCount, ALB RequestCountPerTarget, 5xx, TargetResponseTime, ECS CPU, EMF in-flight/503 |
| Wall-clock | ~45 min of runs + 4 backend redeploys (~12 min), about 60 min | ~45 min (budget set per request, no redeploys) | 2 × 18 min + resets, about 45 min |

The budget override (`?retry_rounds=&open_attempts=`) lets E2 sweep budgets on the same tasks without redeploying. This saves about 30 min and removes task-to-task variation as a confound.

**Total experiment runtime:** about 2.5 h (under the 5 h cap).

## CHECKPOINT 2: deploy plan and cost (us-east-1)

Resources created by Terraform, all tagged `Project=cs6650-midterm`:
- 2 ECR repos
- 1 ECS cluster with 2 services (gateway and backend, Fargate 0.25 vCPU / 0.5 GB, 2–4 tasks each)
- ALB with target group and listener
- internal UDP NLB with target group and listener
- 3 security groups
- 2 log groups (7-day retention)
- 2 target-tracking policies

The S3 bucket `file-transfer-719602427292-nsk` was created by CLI and tagged. IAM: the tasks reuse `LabRole`, and no roles are created.

| Item | Rate | Est. hours/volume | Est. cost |
|---|---|---|---|
| ALB (hourly + LCU) | ~$0.03/h | 5 h | $0.15 |
| NLB (hourly + NLCU) | ~$0.03/h | 5 h | $0.15 |
| Fargate tasks (0.25 vCPU/0.5 GB = $0.0123/h) | 4–8 tasks | ~5 h × ~5 avg | $0.31 |
| Public IPv4 ($0.005/h): ALB nodes (6 AZs) + tasks | ~11 IPs | 5 h | $0.28 |
| Data transfer out (Locust on laptop) | $0.09/GB | ~3 GB | $0.27 |
| CloudWatch Logs ingest, EMF custom metrics (~25), widget images | – | small | ~$0.20 |
| S3 GETs (each `RETY` = 1 GET) | $0.0004/1k | ~1–2 M | ~$0.80 |
| **Total** | | | **≈ $2–3** (well under $15) |

**Decision:** proceed with the deploy.

---

## Re-scope after the AWS smoke test (2026-11-02, ~03:12 local)

The smoke test found 10–40% datagram loss at 0% simulated loss, so 64 KB and larger mostly fail at the default budget. Diagnosis: [native-loss-diagnosis.md](native-loss-diagnosis.md).

Changes to the plan:

| | Before | After |
|---|---|---|
| E1 sizes | 64 KB, 1 MB, 4 MB | **4 KB, 16 KB, 64 KB, 1 MB** (loss levels unchanged: 0, 1, 5, 10, 20) |
| E2 | 10% loss; 64 KB and 256 KB | **5% loss; 16 KB and 64 KB**; open-attempt sweep at 16 KB |
| E3 | 64 KB | **4 KB** |

Revised runtime: E1 ~90 min (60 runs + 4 rollouts), E2 ~40 min, E3 ~45 min, so ~3 h. The diagnosis added ~20 min of stack time. The cost estimate is unchanged at roughly $2–3, still under the caps.

---

## Time-box changes requested mid-run (2026-11-02, ~05:20 local)

The user asked to speed up the remaining work without hurting validity. Applied:
- E3 runs only config A (stock). Config B is defined in the driver but was not run.
- Scale-in cooldown is 60 s; the E3 low-load tail is 4 min plus 2 min of observation.
- Writeups and slides were drafted in parallel, and figures and CloudWatch data were produced per phase.
- Teardown started immediately after the E3 CloudWatch data and screenshots were saved.

## CHECKPOINT 3: results complete → teardown (2026-11-02, 05:59 local)

Before teardown I confirmed all of the following were saved locally:
- E1 (60 runs), E2 (45 runs) and E3 (1 run) raw data
- CloudWatch CSVs for all three windows
- 18 CloudWatch widget images
- Locust screenshots
- scaling activities and alarm definitions

I then ran teardown with `scripts/destroy.sh --yes`, plus manual removal of the non-Terraform leftovers. Output: [`results/deploy/teardown.log`](../results/deploy/teardown.log) and [`results/deploy/leftover_check.txt`](../results/deploy/leftover_check.txt).

## Actuals

| | Estimate | Actual |
|---|---|---|
| Stack lifetime | ~5 h | ~3.4 h (deploy finished 07:52Z, destroy started 11:00Z) |
| Experiment runtime | ~2.5 h → ~3 h after the re-scope | E1 83 min + E2 54 min (plus ~4 min for the incident) + E3 21 min ≈ **2.7 h** |
| AWS cost | $2–3 | **≈ $1–1.5** (rough, see below) |

Rough cost breakdown:
- ALB + NLB hours: ~$0.20
- Fargate: 4–6 tasks × 3.4 h × $0.0123 ≈ $0.20
- Public IPv4: ~10 addresses × 3.4 h × $0.005 ≈ $0.17
- S3 GETs: ~150k, one per OPEN/RETY, ≈ $0.06
- Data out: under 1 GB, ≈ $0.05
- CloudWatch (logs, ~25 EMF metrics, Container Insights, ~20 widget images): ≈ $0.10–0.30

Learner Lab shows the authoritative number under *AWS Details → Budget*.
