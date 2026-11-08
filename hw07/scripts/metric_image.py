#!/usr/bin/env python3
"""Save a CloudWatch metric graph as PNG via `aws cloudwatch get-metric-widget-image`.
Usage: metric_image.py <out.png> <title> <start-iso> <end-iso> <period> <metrics-json> [stat] [yaxis-label]
metrics-json: a JSON list in CloudWatch widget "metrics" format.
"""
import base64, json, subprocess, sys

out, title, start, end, period, metrics = sys.argv[1:7]
stat = sys.argv[7] if len(sys.argv) > 7 else "Maximum"
ylabel = sys.argv[8] if len(sys.argv) > 8 else ""
widget = {
    "title": title, "view": "timeSeries", "stacked": False, "region": "us-east-1",
    "start": start, "end": end, "period": int(period), "stat": stat,
    "metrics": json.loads(metrics), "width": 1000, "height": 450, "timezone": "+0000",
    "yAxis": {"left": {"min": 0, "label": ylabel, "showUnits": False}},
}
res = subprocess.run(["aws", "cloudwatch", "get-metric-widget-image", "--metric-widget", json.dumps(widget),
                      "--output-format", "png", "--query", "MetricWidgetImage", "--output", "text"],
                     check=True, capture_output=True, text=True)
with open(out, "wb") as f:
    f.write(base64.b64decode(res.stdout.strip()))
print("saved", out)
