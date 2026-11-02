# Scripts: how to re-run everything

All tooling for the three experiments lives here. The service source is **not** in this repo. Use the fork at <https://github.com/nikhilsk98/file-transfer-playservice>, branch `midterm-instrumentation`.

| File | Purpose |
|---|---|
| `requirements.txt` | Python dependencies (Locust, boto3, pandas, matplotlib, Playwright, python-pptx) |
| `common.py` | Shared helpers: ECS env-var changes (task-definition clone, `update-service`, wait stable), running Locust with exact UTC timestamps, resumable cells, and exit code 3 on expired credentials |
| `locustfile.py` | Locust user. Requests `FT_FILE` with optional budget-override query parameters, logs each request's `X-*` stats headers to `requests.jsonl`, checks body length, and supports an optional step `LoadTestShape` |
| `e1_loss_size.py` | E1 driver: loss {0, 1, 5, 10, 20} × size {4 KB, 16 KB, 64 KB, 1 MB}, 3 × 60 s trials, 2 users |
| `e2_retry_budget.py` | E2 driver: 5% loss. Sweeps retry rounds {1, 2, 3, 5, 10, 20} × {16 KB, 64 KB} and open attempts {1, 2, 10} (16 KB) |
| `e3_scaling.py` | E3 driver: 4 KB, 1% loss, step load of 4 → 8 → 16 → 32 → 64 → 4 users (3 min steps, 4 min tail). Only config A (`MAX_INFLIGHT=4`) was run; B (16) is defined (`--configs A,B`). Polls ECS every 10 s and saves the scaling activities |
| `cw_fetch.py` | Pulls CloudWatch metrics (ECS, Container Insights, ALB, NLB, EMF `FileTransfer`) for a window into a CSV, and renders `get-metric-widget-image` PNGs |
| `analyze.py` | Builds summary CSVs and the matplotlib figures in `../figures/` |
| `screenshot_locust.py` | Takes headless Playwright screenshots of the Locust HTML reports |
| `text_to_png.py` | Renders saved terminal output as a PNG |
| `e1_backend_attribution.py` | Spreads backend EMF counters over E1 cells by time overlap |
| `draw_architecture.py` | Architecture diagram for the slides |
| `presentation_content.json` | Slide text and speaker notes |
| `build_presentation.py` | Builds `../PRESENTATION_Experiment_Presentation.pptx` and `../PRESENTATION_talking_points.md` |

## Re-running

```bash
# 0. tools + credentials (Learner Lab: paste fresh creds into ~/.aws/credentials)
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && playwright install chromium
export AWS_REGION=us-east-1
aws sts get-caller-identity

# 1. bucket + test files (LabRole can't create buckets; the voclabs user can)
aws s3 mb s3://<bucket>; for s in 4096:f4k 16384:f16k 65536:f64k 262144:f256k 1048576:f1m 4194304:f4m; do head -c ${s%%:*} /dev/urandom > ${s#*:}.bin; done
aws s3 cp . s3://<bucket>/tmp/ --recursive --exclude '*' --include 'f*.bin'

# 2. deploy the instrumented fork (builds linux/amd64 images, pushes to ECR, terraform apply)
cd <fork> && git checkout midterm-instrumentation
printf 'files_bucket = "<bucket>"\nfiles_prefix = "tmp/"\nderegistration_delay = 30\n' > terraform/terraform.tfvars
scripts/deploy.sh --yes

# 3. experiments (each is resumable: re-run after an interruption and finished cells are skipped)
python e1_loss_size.py
python e2_retry_budget.py
python e3_scaling.py              # E3 used scale-in cooldown 60 s: terraform -var scale_in_cooldown=60 (see ../service-changes.md for the pitfall)

# 4. CloudWatch data + images for any window (timestamps are in results/**/meta.json and results/run_ledger.csv)
python cw_fetch.py --start <utc> --end <utc> --out ../results/E3/configA/cloudwatch --images ../screenshots/E3_configA --title "E3 config A"

# 5. analysis, screenshots, slides
python analyze.py
python screenshot_locust.py ../results/E3/configA/report.html ../screenshots/E3_configA_locust_report.png
python build_presentation.py

# 6. teardown
cd <fork> && scripts/destroy.sh --yes && aws s3 rb s3://<bucket> --force
```

If credentials expire mid-run, a driver prints `AWS CREDENTIALS EXPIRED` and exits with code 3. Refresh `~/.aws/credentials` and run the same command again. Locust itself talks only to the public ALB and needs no credentials, so a trial in progress still completes.

The Locust HTML reports are stored gzipped (`report.html.gz`). Run `gunzip` on one before passing it to `screenshot_locust.py`.
