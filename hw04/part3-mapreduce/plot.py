#!/usr/bin/env python3
"""Make plots from results/runs.csv and results/mappers.csv (needs matplotlib).

    python3 -m pip install matplotlib
    python3 plot.py

Creates in results/:
    runtime_vs_size.png   total job time vs input size, one line per mapper count
    speedup.png           speedup vs number of mappers (relative to 1 mapper)
    stage_breakdown.png   split / map / reduce time for the largest input
    load_balance.png      per-mapper chunk size and time for the largest input
and prints a summary table you can paste into the writeup.
"""
import csv
import statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def mean(xs):
    return st.mean(xs) if xs else 0.0


def sd(xs):
    return st.stdev(xs) if len(xs) > 1 else 0.0


runs = read("results/runs.csv")
maps = read("results/mappers.csv")

by = defaultdict(list)          # (size, n) -> list of run rows
local = defaultdict(list)       # size -> local python ms
for r in runs:
    size, n = float(r["size_mb"]), int(r["n_mappers"])
    by[(size, n)].append(r)
    local[size].append(float(r["local_python_ms"]))
sizes = sorted({k[0] for k in by})
ns = sorted({k[1] for k in by})
biggest, most = sizes[-1], ns[-1]


def col(rows, name):
    return [float(r[name]) for r in rows]


# 1. Runtime vs input size
plt.figure(figsize=(7, 4.5))
for n in ns:
    ys = [mean(col(by[(s, n)], "total_ms")) / 1000 for s in sizes]
    es = [sd(col(by[(s, n)], "total_ms")) / 1000 for s in sizes]
    plt.errorbar(sizes, ys, yerr=es, marker="o", capsize=3, label=f"{n} mapper{'s' if n > 1 else ''}")
plt.plot(sizes, [mean(local[s]) / 1000 for s in sizes], "k--", alpha=0.6,
         label="local single process (laptop, Python)")
plt.xlabel("input size (MB)")
plt.ylabel("end-to-end job time (s)")
plt.title("MapReduce word count: runtime vs input size")
plt.grid(alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig("results/runtime_vs_size.png", dpi=150)

# 2. Speedup vs number of mappers
if 1 in ns:
    plt.figure(figsize=(7, 4.5))
    for s in sizes:
        base = mean(col(by[(s, 1)], "total_ms"))
        plt.plot(ns, [base / mean(col(by[(s, n)], "total_ms")) for n in ns], marker="o",
                 label=f"{s:g} MB")
    plt.plot(ns, ns, "k--", alpha=0.5, label="ideal (linear)")
    plt.xticks(ns)
    plt.xlabel("number of mappers")
    plt.ylabel("speedup vs 1 mapper")
    plt.title("Speedup from adding mappers")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig("results/speedup.png", dpi=150)

# 3. Stage breakdown for the largest input
plt.figure(figsize=(7, 4.5))
labels = [str(n) for n in ns]
split = [mean(col(by[(biggest, n)], "split_ms")) / 1000 for n in ns]
mapt = [mean(col(by[(biggest, n)], "map_ms")) / 1000 for n in ns]
red = [mean(col(by[(biggest, n)], "reduce_ms")) / 1000 for n in ns]
plt.bar(labels, split, label="split")
plt.bar(labels, mapt, bottom=split, label="map (parallel)")
plt.bar(labels, red, bottom=[a + b for a, b in zip(split, mapt)], label="reduce")
plt.xlabel("number of mappers")
plt.ylabel("time (s)")
plt.title(f"Where the time goes ({biggest:g} MB input)")
plt.legend()
plt.tight_layout()
plt.savefig("results/stage_breakdown.png", dpi=150)

# 4. Load balance across mappers for the largest input / most mappers
sel = [m for m in maps if float(m["size_mb"]) == biggest and int(m["n_mappers"]) == most]
idx = sorted({int(m["mapper_index"]) for m in sel})
per = {i: [m for m in sel if int(m["mapper_index"]) == i] for i in idx}
chunk_mb = [mean(col(per[i], "chunk_bytes")) / 1024 / 1024 for i in idx]
dl = [mean(col(per[i], "download_ms")) for i in idx]
cp = [mean(col(per[i], "compute_ms")) for i in idx]
up = [mean(col(per[i], "upload_ms")) for i in idx]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
names = [f"mapper {i}" for i in idx]
ax1.bar(names, chunk_mb, color="tab:blue")
ax1.set_ylabel("chunk size (MB)")
ax1.set_title("Data given to each mapper")
ax2.bar(names, dl, label="download from S3")
ax2.bar(names, cp, bottom=dl, label="count words")
ax2.bar(names, up, bottom=[a + b for a, b in zip(dl, cp)], label="upload to S3")
ax2.set_ylabel("time (ms)")
ax2.set_title("Time spent by each mapper")
ax2.legend()
totals = [a + b + c for a, b, c in zip(dl, cp, up)]
cv_size = sd(chunk_mb) / mean(chunk_mb) * 100 if mean(chunk_mb) else 0
cv_time = sd(totals) / mean(totals) * 100 if mean(totals) else 0
fig.suptitle(f"Load balance: {biggest:g} MB, {most} mappers "
             f"(size spread CV {cv_size:.2f}%, time spread CV {cv_time:.1f}%)")
fig.tight_layout()
fig.savefig("results/load_balance.png", dpi=150)

# Summary table for the writeup
print(f"{'size MB':>8} {'mappers':>8} {'mean total s':>13} {'std s':>7} {'speedup':>8} {'correct':>8}")
for s in sizes:
    base = mean(col(by[(s, 1)], "total_ms")) if 1 in ns else None
    for n in ns:
        rows = by[(s, n)]
        t = mean(col(rows, "total_ms"))
        ok = sum(r["correct"] == "True" for r in rows)
        spd = f"{base / t:.2f}x" if base else "-"
        print(f"{s:>8g} {n:>8} {t / 1000:>13.2f} {sd(col(rows, 'total_ms')) / 1000:>7.2f} "
              f"{spd:>8} {ok:>4}/{len(rows)}")
print(f"\nLoad balance ({biggest:g} MB, {most} mappers): chunk size CV {cv_size:.2f}%, "
      f"mapper time CV {cv_time:.1f}%")
print("Saved: results/runtime_vs_size.png, speedup.png, stage_breakdown.png, load_balance.png")
