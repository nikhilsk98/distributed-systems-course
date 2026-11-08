#!/usr/bin/env python3
"""Peak depth and time-to-zero from the 5 s queue samples, plus ECS CPU/memory per test window."""
import csv, json, subprocess, sys
from datetime import datetime, timezone

def iso(e): return datetime.fromtimestamp(e, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def ecs(service, metric, start, end):
    out = subprocess.run(["aws", "cloudwatch", "get-metric-statistics", "--namespace", "AWS/ECS",
        "--metric-name", metric, "--dimensions", "Name=ClusterName,Value=hw07-cluster", f"Name=ServiceName,Value={service}",
        "--start-time", iso(start - 60), "--end-time", iso(end + 60), "--period", "60",
        "--statistics", "Maximum", "Average", "--output", "json"], capture_output=True, text=True, check=True).stdout
    pts = json.loads(out)["Datapoints"]
    if not pts: return (0, 0)
    return (max(p["Maximum"] for p in pts), sum(p["Average"] for p in pts) / len(pts))

print("label,test_start,peak_queue(visible+inflight),peak_time_s,time_to_zero_s,proc_cpu_max,proc_cpu_avg,proc_mem_max,api_cpu_max,api_mem_max")
for w in sys.argv[1:]:
    rows = [(int(r["epoch"]), int(r["visible"]) + int(r["in_flight"])) for r in csv.DictReader(open(f"results/queue/async_flash_w{w}.csv"))]
    t0 = rows[0][0]
    peak_t, peak = max(rows, key=lambda r: r[1])
    zero = next((t for t, n in rows if t > peak_t and n == 0), None)
    end = zero or rows[-1][0]
    pc = ecs("order-processor", "CPUUtilization", t0, end); pm = ecs("order-processor", "MemoryUtilization", t0, end)
    ac = ecs("order-api", "CPUUtilization", t0, t0 + 60); am = ecs("order-api", "MemoryUtilization", t0, t0 + 60)
    print(f"w{w},{iso(t0)},{peak},{peak_t-t0},{(zero - t0) if zero else 'n/a (purged)'},{pc[0]:.2f},{pc[1]:.2f},{pm[0]:.2f},{ac[0]:.2f},{am[0]:.2f}")
