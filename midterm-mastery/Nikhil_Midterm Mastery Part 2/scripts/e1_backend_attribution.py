"""Attribute backend EMF counters (1-min sums) to E1 runs by time window; writes results/E1/backend_counters_by_cell.csv."""
import json
import pandas as pd
from common import RESULTS

cw = pd.read_csv(RESULTS / "E1" / "cloudwatch" / "cloudwatch_metrics.csv", parse_dates=["utc"])
rows = []
for d in sorted((RESULTS / "E1").glob("*/trial*/done.json")):
    m = json.loads(d.read_text())
    s, e = pd.Timestamp(m["start_utc"]), pd.Timestamp(m["end_utc"])
    # weight each 1-minute bucket by the fraction of it that overlaps the run (approximate:
    # runs are ~60-80 s, so neighbouring runs share boundary minutes)
    b0 = cw.utc
    ov = ((b0 + pd.Timedelta(minutes=1)).clip(upper=e) - b0.clip(lower=s)).dt.total_seconds().clip(lower=0) / 60
    rows.append({"file": m["file"], "loss": m["loss"], "trial": m["trial"], "minutes": ov.sum(),
                 **{k: (cw[f"emf_backend_{k}"].fillna(0) * ov).sum() for k in ("OverloadDrops", "RetyRequests", "MessagesAccepted", "DatagramsSent", "SourceFetches", "SourceFetchMsTotal")}})
df = pd.DataFrame(rows)
g = df.groupby(["file", "loss"]).sum(numeric_only=True).reset_index()
g["overload_drop_pct_of_incoming"] = 100 * g.OverloadDrops / (g.OverloadDrops + g.MessagesAccepted)
g["mean_s3_fetch_ms"] = g.SourceFetchMsTotal / g.SourceFetches.where(g.SourceFetches > 0)
g.drop(columns=["trial"]).to_csv(RESULTS / "E1" / "backend_counters_by_cell.csv", index=False)
print(g.drop(columns=["trial"]).round(1).to_string())
