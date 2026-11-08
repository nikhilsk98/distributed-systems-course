#!/usr/bin/env python3
"""Plot the 5-second SQS queue-depth samples for each worker-scaling run.
Usage: plot_queue.py results/queue results/graphs/queue_depth_all_workers.png"""
import csv, glob, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

src, out = sys.argv[1], sys.argv[2]
fig, ax = plt.subplots(figsize=(11, 5))
for path in sorted(glob.glob(os.path.join(src, "async_flash_w*.csv")),
                   key=lambda p: int(p.rsplit("_w", 1)[1].split(".")[0])):
    rows = list(csv.DictReader(open(path)))
    if not rows:
        continue
    t0 = int(rows[0]["epoch"])
    xs = [(int(r["epoch"]) - t0) / 60 for r in rows]
    ys = [int(r["visible"]) + int(r["in_flight"]) for r in rows]
    w = path.rsplit("_w", 1)[1].split(".")[0]
    ax.plot(xs, ys, label=(f"{w} worker{'s' if w != '1' else ''}" + (" (queue purged at ~5 min, not drained)" if w == "1" else "")), linewidth=1.8)
ax.set_xlabel("Minutes since flash sale started")
ax.set_ylabel("Messages in queue (visible + in flight)")
ax.set_title("SQS backlog during the 60 s flash sale, by processor goroutine count")
ax.grid(alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(out, dpi=120)
print("saved", out)
