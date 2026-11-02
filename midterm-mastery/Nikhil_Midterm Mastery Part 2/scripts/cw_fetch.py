"""Fetch CloudWatch metrics for a time window as CSV, and optionally render metric-widget PNGs.

usage:
  python cw_fetch.py --start 2026-11-02T08:00:00Z --end 2026-11-02T08:30:00Z --out results/E3/configA/cloudwatch \
         [--period 60] [--images screenshots/E3_configA] [--title "E3 config A"]

Metrics:
  AWS/ECS               CPUUtilization, MemoryUtilization (gateway, backend)
  ECS/ContainerInsights RunningTaskCount, DesiredTaskCount, PendingTaskCount (gateway, backend)
  AWS/ApplicationELB    RequestCount, RequestCountPerTarget, TargetResponseTime (avg, p95), HTTPCode_ELB_5XX_Count,
                        HTTPCode_Target_5XX_Count, HTTPCode_Target_2XX_Count, HTTPCode_ELB_503_Count, HealthyHostCount
  AWS/NetworkELB        ActiveFlowCount_UDP, NewFlowCount_UDP, ProcessedBytes_UDP, ProcessedBytes, HealthyHostCount
  FileTransfer (EMF)    every metric the instrumented gateway/backend publish (Service dimension)
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from common import CLUSTER, client, guard, log


def ids():
    elb = client("elbv2")
    lbs = {lb["LoadBalancerName"]: lb for lb in elb.describe_load_balancers(Names=["file-transfer-gateway", "file-transfer-backend"])["LoadBalancers"]}
    tgs = {tg["TargetGroupName"]: tg for tg in elb.describe_target_groups(Names=["file-transfer-gateway", "file-transfer-backend"])["TargetGroups"]}
    suffix = lambda arn: arn.split(":loadbalancer/")[-1] if ":loadbalancer/" in arn else arn.split(":")[-1]
    return {
        "alb": suffix(lbs["file-transfer-gateway"]["LoadBalancerArn"]),
        "nlb": suffix(lbs["file-transfer-backend"]["LoadBalancerArn"]),
        "alb_tg": tgs["file-transfer-gateway"]["TargetGroupArn"].split(":")[-1],
        "nlb_tg": tgs["file-transfer-backend"]["TargetGroupArn"].split(":")[-1],
    }


def queries(i):
    q = []
    for svc in ("gateway", "backend"):
        d = [{"Name": "ClusterName", "Value": CLUSTER}, {"Name": "ServiceName", "Value": svc}]
        for m in ("CPUUtilization", "MemoryUtilization"):
            for stat in ("Average", "Maximum"):
                q.append((f"{svc}_{m}_{stat}", "AWS/ECS", m, d, stat))
        for m in ("RunningTaskCount", "DesiredTaskCount", "PendingTaskCount"):
            q.append((f"{svc}_{m}", "ECS/ContainerInsights", m, d, "Average"))
    alb = [{"Name": "LoadBalancer", "Value": i["alb"]}]
    albtg = [{"Name": "TargetGroup", "Value": i["alb_tg"]}, {"Name": "LoadBalancer", "Value": i["alb"]}]
    for m in ("RequestCount", "HTTPCode_ELB_5XX_Count", "HTTPCode_Target_5XX_Count", "HTTPCode_Target_2XX_Count",
              "HTTPCode_Target_4XX_Count", "HTTPCode_ELB_503_Count", "HTTPCode_ELB_504_Count"):
        q.append((f"alb_{m}", "AWS/ApplicationELB", m, alb, "Sum"))
    q.append(("alb_TargetResponseTime_avg", "AWS/ApplicationELB", "TargetResponseTime", alb, "Average"))
    q.append(("alb_TargetResponseTime_p95", "AWS/ApplicationELB", "TargetResponseTime", alb, "p95"))
    q.append(("alb_RequestCountPerTarget", "AWS/ApplicationELB", "RequestCountPerTarget", albtg, "Sum"))
    q.append(("alb_HealthyHostCount", "AWS/ApplicationELB", "HealthyHostCount", albtg, "Average"))
    nlb = [{"Name": "LoadBalancer", "Value": i["nlb"]}]
    nlbtg = [{"Name": "TargetGroup", "Value": i["nlb_tg"]}, {"Name": "LoadBalancer", "Value": i["nlb"]}]
    for m, stat in (("ActiveFlowCount_UDP", "Average"), ("NewFlowCount_UDP", "Sum"), ("ProcessedBytes_UDP", "Sum"),
                    ("ProcessedBytes", "Sum"), ("ActiveFlowCount", "Average"), ("ProcessedPackets", "Sum")):
        q.append((f"nlb_{m}", "AWS/NetworkELB", m, nlb, stat))
    q.append(("nlb_HealthyHostCount", "AWS/NetworkELB", "HealthyHostCount", nlbtg, "Average"))
    # EMF custom metrics from the instrumentation
    cw = client("cloudwatch")
    for page in cw.get_paginator("list_metrics").paginate(Namespace="FileTransfer"):
        for m in page["Metrics"]:
            svc = next((d["Value"] for d in m["Dimensions"] if d["Name"] == "Service"), None)
            if svc and len(m["Dimensions"]) == 1:
                q.append((f"emf_{svc}_{m['MetricName']}", "FileTransfer", m["MetricName"], m["Dimensions"],
                          "Maximum" if m["MetricName"] in ("InFlight", "WaitingForSlot", "BusyWorkers", "QueuedJobs") else "Sum"))
    return q


def fetch(start, end, period, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cw = client("cloudwatch")
    qs = queries(ids())
    series = {}
    for k in range(0, len(qs), 400):
        batch = qs[k:k + 400]
        mdq = [{"Id": f"m{n}", "Label": label, "ReturnData": True,
                "MetricStat": {"Metric": {"Namespace": ns, "MetricName": m, "Dimensions": d}, "Period": period, "Stat": stat}}
               for n, (label, ns, m, d, stat) in enumerate(batch)]
        token = None
        while True:
            kw = dict(MetricDataQueries=mdq, StartTime=start, EndTime=end, ScanBy="TimestampAscending")
            if token:
                kw["NextToken"] = token
            r = cw.get_metric_data(**kw)
            for res in r["MetricDataResults"]:
                s = series.setdefault(res["Label"], {})
                s.update({t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"): v for t, v in zip(res["Timestamps"], res["Values"])})
            token = r.get("NextToken")
            if not token:
                break
    labels = [q[0] for q in qs]
    times = sorted({t for s in series.values() for t in s})
    with open(out / "cloudwatch_metrics.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["utc"] + labels)
        for t in times:
            w.writerow([t] + [series.get(l, {}).get(t, "") for l in labels])
    (out / "window.json").write_text(json.dumps({"start": start.isoformat(), "end": end.isoformat(), "period": period}))
    log(f"cloudwatch: {len(labels)} series x {len(times)} points -> {out}/cloudwatch_metrics.csv")


def widget(metrics, title, start, end, path, period=60, yleft=None, annotations=None):
    spec = {"metrics": metrics, "title": title, "view": "timeSeries", "stacked": False, "period": period,
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "width": 900, "height": 400, "region": "us-east-1"}
    if yleft:
        spec["yAxis"] = {"left": yleft}
    if annotations:
        spec["annotations"] = annotations
    img = client("cloudwatch").get_metric_widget_image(MetricWidget=json.dumps(spec), OutputFormat="png")["MetricWidgetImage"]
    Path(path).write_bytes(img)
    log(f"widget -> {path}")


def images(start, end, prefix, title, period=60):
    i = ids()
    svc = lambda s: ["ClusterName", CLUSTER, "ServiceName", s]
    widget([["AWS/ECS", "CPUUtilization", *svc("gateway"), {"label": "gateway CPU %"}],
            ["AWS/ECS", "CPUUtilization", *svc("backend"), {"label": "backend CPU %"}],
            ["AWS/ECS", "MemoryUtilization", *svc("gateway"), {"label": "gateway mem %"}],
            ["AWS/ECS", "MemoryUtilization", *svc("backend"), {"label": "backend mem %"}]],
           f"{title}: ECS CPU & memory per service", start, end, f"{prefix}_ecs_cpu_memory.png", period)
    widget([["ECS/ContainerInsights", "RunningTaskCount", *svc("gateway"), {"label": "gateway running"}],
            ["ECS/ContainerInsights", "DesiredTaskCount", *svc("gateway"), {"label": "gateway desired"}],
            ["ECS/ContainerInsights", "RunningTaskCount", *svc("backend"), {"label": "backend running"}],
            ["ECS/ContainerInsights", "DesiredTaskCount", *svc("backend"), {"label": "backend desired"}]],
           f"{title}: running vs desired tasks", start, end, f"{prefix}_ecs_running_desired_tasks.png", period)
    alb = ["LoadBalancer", i["alb"]]
    widget([["AWS/ApplicationELB", "RequestCount", *alb, {"stat": "Sum", "label": "RequestCount"}],
            ["AWS/ApplicationELB", "RequestCountPerTarget", "TargetGroup", i["alb_tg"], *alb, {"stat": "Sum", "label": "RequestCountPerTarget"}],
            ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", *alb, {"stat": "Sum", "label": "ELB 5XX"}],
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", *alb, {"stat": "Sum", "label": "Target 5XX"}]],
           f"{title}: ALB requests and 5xx", start, end, f"{prefix}_alb_requests_5xx.png", period)
    widget([["AWS/ApplicationELB", "TargetResponseTime", *alb, {"stat": "Average", "label": "avg"}],
            ["AWS/ApplicationELB", "TargetResponseTime", *alb, {"stat": "p95", "label": "p95"}],
            ["AWS/ApplicationELB", "TargetResponseTime", *alb, {"stat": "p99", "label": "p99"}]],
           f"{title}: ALB TargetResponseTime (s)", start, end, f"{prefix}_alb_target_response_time.png", period)
    nlb = ["LoadBalancer", i["nlb"]]
    widget([["AWS/NetworkELB", "ActiveFlowCount_UDP", *nlb, {"label": "ActiveFlowCount_UDP"}],
            ["AWS/NetworkELB", "NewFlowCount_UDP", *nlb, {"stat": "Sum", "label": "NewFlowCount_UDP"}],
            ["AWS/NetworkELB", "ProcessedBytes_UDP", *nlb, {"stat": "Sum", "label": "ProcessedBytes_UDP", "yAxis": "right"}]],
           f"{title}: NLB UDP flows and bytes", start, end, f"{prefix}_nlb_flows_bytes.png", period)
    widget([["FileTransfer", "OverloadDrops", "Service", "backend", {"stat": "Sum", "label": "backend overload drops"}],
            ["FileTransfer", "RetyRequests", "Service", "backend", {"stat": "Sum", "label": "backend RETYs served"}],
            ["FileTransfer", "SimulatedSendDrops", "Service", "backend", {"stat": "Sum", "label": "simulated send drops"}],
            ["FileTransfer", "RejectedBusy503", "Service", "gateway", {"stat": "Sum", "label": "gateway busy 503s", "yAxis": "right"}]],
           f"{title}: instrumentation (EMF) counters", start, end, f"{prefix}_emf_counters.png", period)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out")
    ap.add_argument("--period", type=int, default=60)
    ap.add_argument("--images")
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    p = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    if a.out:
        guard(lambda: fetch(p(a.start), p(a.end), a.period, a.out))
    if a.images:
        guard(lambda: images(p(a.start), p(a.end), a.images, a.title, a.period))
