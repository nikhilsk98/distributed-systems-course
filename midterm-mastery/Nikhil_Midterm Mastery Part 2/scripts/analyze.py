"""Aggregate raw results into summary CSVs and draw the analysis figures.

usage: python analyze.py [E1] [E2] [E3]     (default: all that have data)
Reads results/E*/**/requests.jsonl + done.json; writes results/E*/summary_*.csv and figures/*.png.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import DELIV, RESULTS

FIG = DELIV / "figures"
FIG.mkdir(exist_ok=True)
# Reference palette (dataviz skill), light mode, first three categorical slots (validated all-pairs)
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # slot 4 only on line charts (adjacent-pair validated), with direct labels
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "text.color": INK, "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False, "font.size": 12,
                     "axes.titlesize": 14, "axes.titleweight": "bold", "lines.linewidth": 2, "lines.markersize": 8,
                     "legend.frameon": False, "savefig.dpi": 160, "savefig.bbox": "tight"})
SIZE_LABEL = {"f4k.bin": "4 KB", "f16k.bin": "16 KB", "f64k.bin": "64 KB", "f256k.bin": "256 KB", "f1m.bin": "1 MB", "f4m.bin": "4 MB"}


def load(exp):
    rows = []
    for done in sorted((RESULTS / exp).glob("**/done.json")):
        info = json.loads(done.read_text())
        rl = done.parent / "requests.jsonl"
        if not rl.exists():
            continue
        for line in rl.read_text().splitlines():
            r = json.loads(line)
            r.update({k: info.get(k) for k in ("cell", "trial", "loss") if k in info})
            if "retry_rounds" in info:
                r["budget_rounds"] = info["retry_rounds"]
                r["budget_opens"] = info["open_attempts"]
            rows.append(r)
    return pd.DataFrame(rows)


def pct(s, q):
    return float(np.percentile(s, q)) / 1000 if len(s) else np.nan


def trial_stats(g):
    ok = g[g.ok]
    return pd.Series({
        "n": len(g), "success_rate": g.ok.mean() * 100, "n_504": int((g.status == 504).sum()),
        "n_503": int((g.status == 503).sum()), "n_other_fail": int(((~g.ok) & ~g.status.isin([503, 504])).sum()),
        "p50_s": pct(g.latency_ms, 50), "p95_s": pct(g.latency_ms, 95), "p99_s": pct(g.latency_ms, 99),
        "ok_p50_s": pct(ok.latency_ms, 50), "ok_p95_s": pct(ok.latency_ms, 95),
        "mean_rety_sent": g.rety_sent.mean(), "mean_rounds": g.retry_rounds.mean(),
        "mean_open_attempts": g.open_attempts.mean(), "mean_missing_after_open": g.missing_after_open.mean(),
        "mean_missing_at_end": g.missing_at_end.mean(),
        "rety_per_success": g.rety_sent.sum() / max(g.ok.sum(), 1),
        "datagrams_rx_per_success": g.datagrams_rx.sum() / max(g.ok.sum(), 1),
    })


def cell_table(df, keys):
    tr = df.groupby(keys + ["trial"]).apply(trial_stats, include_groups=False).reset_index()
    agg = tr.groupby(keys).agg(trials=("trial", "count"), n=("n", "sum"), success_mean=("success_rate", "mean"),
                               success_std=("success_rate", "std"), p95_trial_std=("p95_s", "std")).reset_index()
    pooled = df.groupby(keys).apply(trial_stats, include_groups=False).reset_index()
    return tr, agg.merge(pooled.drop(columns=["n"]), on=keys)


def save(fig, name):
    fig.savefig(FIG / name)
    plt.close(fig)
    print("figure", name)


# ---------------- E1 ----------------
def e1():
    df = load("E1")
    if df.empty:
        return
    tr, cells = cell_table(df, ["file", "loss"])
    tr.to_csv(RESULTS / "E1" / "summary_trials.csv", index=False)
    cells.to_csv(RESULTS / "E1" / "summary_cells.csv", index=False)
    files = [f for f in SIZE_LABEL if f in set(df.file)]

    fig, ax = plt.subplots(figsize=(8.5, 5))
    ends = []
    for i, f in enumerate(files):
        c = cells[cells.file == f].sort_values("loss")
        ax.errorbar(c.loss, c.success_mean, yerr=c.success_std.fillna(0), color=C[i], marker="o", capsize=4, label=SIZE_LABEL[f])
        ends.append([c.iloc[-1].success_mean, SIZE_LABEL[f]])
    ends.sort()
    for k in range(1, len(ends)):  # keep direct labels at least 7 points apart
        ends[k][0] = max(ends[k][0], ends[k - 1][0] + 7)
    for y, lab in ends:
        ax.annotate(lab, (20, y), xytext=(10, 0), textcoords="offset points", color=INK2, va="center")
    ax.set(xlabel="Simulated loss % (send = receive)", ylabel="Requests succeeding (%)", ylim=(-5, 105), xlim=(-0.5, 22.5),
           title="E1: success rate vs loss (default budget 5 opens / 5 rounds)")
    ax.legend(title="File size", loc="lower left", bbox_to_anchor=(0.02, 0.12))
    ax.text(0, -0.16, "Mean of 3 × 60 s trials; error bars = std across trials. 2 Locust users.", transform=ax.transAxes, color=INK2, fontsize=10)
    save(fig, "E1_success_rate_vs_loss.png")

    fig, axes = plt.subplots(1, len(files), figsize=(5 * len(files), 4.5), sharey=True)
    for ax, f in zip(np.atleast_1d(axes), files):
        c = cells[cells.file == f].sort_values("loss")
        for j, (col, lab) in enumerate((("p50_s", "p50"), ("p95_s", "p95"), ("p99_s", "p99"))):
            ax.plot(c.loss, c[col], marker="o", color=C[j], label=lab)
        ax.set(title=SIZE_LABEL[f], xlabel="Loss %")
    np.atleast_1d(axes)[0].set_ylabel("Latency (s), all requests")
    np.atleast_1d(axes)[0].legend(loc="upper left")
    fig.suptitle("E1: latency percentiles vs loss (successes and failures pooled)", fontweight="bold")
    save(fig, "E1_latency_percentiles_vs_loss.png")

    chunks = {"f4k.bin": 64, "f16k.bin": 256, "f64k.bin": 1024, "f1m.bin": 16384}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for i, f in enumerate(files):
        c = cells[cells.file == f].sort_values("loss")
        axes[0].plot(c.loss, 100 * c.mean_missing_after_open / chunks[f], marker="o", color=C[i], label=SIZE_LABEL[f])
        axes[1].plot(c.loss, c.mean_rety_sent.where(c.mean_rety_sent > 0), marker="o", color=C[i], label=SIZE_LABEL[f])
    axes[0].plot([0, 20], [0, 20 * 1.0], color=INK2, ls=":", lw=1)
    axes[0].annotate("dotted line = simulated\nsend loss alone", (11.5, 1.0), xytext=(0, 0), textcoords="offset points", fontsize=9, color=INK2)
    axes[0].set(xlabel="Simulated loss %", ylabel="Chunks missing after the OPEN burst (%)", title="Burst loss grows with file size")
    axes[1].set_yscale("log")
    axes[1].set(xlabel="Simulated loss %", ylabel="RETY datagrams sent per request (log)", title="Retry work per request")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, title="File size", loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.1))
    fig.suptitle("E1: where the chunks go (mean per request; 0% simulated loss is NOT 0% real loss)", fontweight="bold", y=1.02)
    save(fig, "E1_retry_work_vs_loss.png")


# ---------------- E2 ----------------
def e2():
    df = load("E2")
    if df.empty:
        return
    tr, cells = cell_table(df, ["file", "budget_opens", "budget_rounds"])
    tr.to_csv(RESULTS / "E2" / "summary_trials.csv", index=False)
    cells.to_csv(RESULTS / "E2" / "summary_cells.csv", index=False)

    fig, ax = plt.subplots(figsize=(8, 5))
    for i, f in enumerate(["f16k.bin", "f64k.bin"]):
        c = cells[(cells.file == f) & (cells.budget_opens == 5)].sort_values("budget_rounds")
        ax.errorbar(c.budget_rounds, c.success_mean, yerr=c.success_std.fillna(0), marker="o", color=C[i], capsize=4, label=SIZE_LABEL[f])
    ax.axvline(5, color=INK2, ls=":", lw=1)
    ax.text(5.2, 3, "default", color=INK2, fontsize=10)
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 3, 5, 10, 20], ["1", "2", "3", "5", "10", "20"])
    ax.set(xlabel="Retry rounds allowed (open attempts = 5)", ylabel="Requests succeeding (%)", ylim=(-5, 105),
           title="E2: success vs retry rounds at 5% loss")
    ax.legend(title="File size")
    save(fig, "E2_success_vs_retry_rounds.png")

    fig, ax = plt.subplots(figsize=(8, 5.5))
    for i, f in enumerate(["f16k.bin", "f64k.bin"]):
        c = cells[(cells.file == f) & (cells.budget_opens == 5)].sort_values("budget_rounds")
        ax.plot(c.p95_s, c.success_mean, marker="o", color=C[i], label=f"{SIZE_LABEL[f]}, rounds sweep")
        groups = []  # merge labels of points that sit within 1.5 s and 4 points of each other
        for _, r in c.iterrows():
            if groups and abs(r.p95_s - groups[-1][0]) < 1.5 and abs(r.success_mean - groups[-1][1]) < 4:
                groups[-1][2].append(int(r.budget_rounds))
            else:
                groups.append([r.p95_s, r.success_mean, [int(r.budget_rounds)]])
        for x, y, rs in groups:
            ax.annotate("R=" + ",".join(map(str, rs)), (x, y), xytext=(6, -14), textcoords="offset points", fontsize=9, color=INK2)
    c = cells[(cells.file == "f16k.bin") & (cells.budget_rounds == 5)].sort_values("budget_opens")
    ax.plot(c.p95_s, c.success_mean, marker="s", ls="--", color=C[2], label="16 KB, open-attempts sweep (R=5)")
    ax.annotate("O=" + ",".join(str(int(o)) for o in c.budget_opens), (c.p95_s.max(), c.success_mean.max()),
                xytext=(8, 4), textcoords="offset points", fontsize=9, color=INK2)
    ax.set(xlabel="p95 latency, all requests (s)", ylabel="Requests succeeding (%)", ylim=(-5, 105),
           title="E2: success vs tail latency per retry budget (5% loss)")
    ax.legend(loc="lower right")
    save(fig, "E2_success_vs_tail_latency.png")

    fig, ax = plt.subplots(figsize=(8, 5))
    for i, f in enumerate(["f16k.bin", "f64k.bin"]):
        c = cells[(cells.file == f) & (cells.budget_opens == 5)].sort_values("budget_rounds")
        ax.plot(c.budget_rounds, c.rety_per_success, marker="o", color=C[i], label=SIZE_LABEL[f])
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 3, 5, 10, 20], ["1", "2", "3", "5", "10", "20"])
    ax.set(xlabel="Retry rounds allowed", ylabel="RETY datagrams sent per successful download",
           title="E2: wasted work per success")
    ax.legend(title="File size")
    save(fig, "E2_rety_per_success.png")


# ---------------- E3 ----------------
def e3():
    for cfgdir in sorted((RESULTS / "E3").glob("config*")):
        if not (cfgdir / "done.json").exists():
            continue
        meta = json.loads((cfgdir / "done.json").read_text())
        t0 = datetime.fromisoformat(meta["start_utc"].replace("Z", "+00:00"))
        req = pd.read_json(cfgdir / "requests.jsonl", lines=True)
        req["t"] = (req.t_start - t0.timestamp()) / 60
        req["bucket"] = (req.t // 0.5) * 0.5
        per = req.groupby("bucket").agg(rps=("ok", "size"), ok=("ok", "sum"), n503=("status", lambda s: (s == 503).sum()),
                                        n504=("status", lambda s: (s == 504).sum()),
                                        p95=("latency_ms", lambda s: np.percentile(s, 95) / 1000)).reset_index()
        per[["rps", "ok", "n503", "n504"]] = per[["rps", "ok", "n503", "n504"]] / 30.0
        hist = pd.read_csv(cfgdir / "locust_stats_history.csv")
        hist = hist[hist.Name == "Aggregated"]
        hist["t"] = (hist.Timestamp - t0.timestamp()) / 60
        tl = pd.read_csv(cfgdir / "ecs_timeline.csv")
        tl["t"] = (pd.to_datetime(tl.utc, utc=True) - pd.Timestamp(t0)).dt.total_seconds() / 60
        acts = json.loads((cfgdir / "scaling_activities.json").read_text()) if (cfgdir / "scaling_activities.json").exists() else []
        end = datetime.fromisoformat(meta.get("observe_end_utc", meta["end_utc"]).replace("Z", "+00:00"))
        events = []
        for a in acts:
            st = datetime.fromisoformat(str(a["StartTime"]))
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            if t0 <= st <= end:
                svc = a["ResourceId"].split("/")[-1]
                events.append(((st - t0).total_seconds() / 60, svc, a.get("Description", "")))
        pd.DataFrame(events, columns=["minute", "service", "description"]).to_csv(cfgdir / "scale_events.csv", index=False)

        fig, axes = plt.subplots(4, 1, figsize=(11, 11), sharex=True)
        axes[0].plot(hist.t, hist["User Count"], color=C[0])
        axes[0].set(ylabel="Locust users", title=f"E3 step load (MAX_INFLIGHT={meta['config'].get('MAX_INFLIGHT')}, 4 KB, 1% loss): load, outcomes, tasks, latency")
        axes[1].plot(per.bucket, per.ok, color=C[2], label="200 OK /s")
        axes[1].plot(per.bucket, per.n503, color=C[1], label="503 busy /s")
        axes[1].plot(per.bucket, per.n504, color=C[0], ls="--", label="504 timeout /s")
        axes[1].set(ylabel="Responses / s")
        axes[1].legend(loc="upper left", ncol=3)
        for i, svc in enumerate(("gateway", "backend")):
            s = tl[tl.service == svc]
            axes[2].step(s.t, s.running, where="post", color=C[i], label=f"{svc} running")
            axes[2].step(s.t, s.desired, where="post", color=C[i], ls=":", label=f"{svc} desired")
        axes[2].set(ylabel="ECS tasks", ylim=(0, 5))
        axes[2].legend(loc="upper left", ncol=2, fontsize=10)
        axes[3].plot(per.bucket, per.p95, color=C[0], label="p95 latency (30 s buckets)")
        axes[3].set(ylabel="p95 latency (s)", xlabel="Minutes since load start")
        for k, (m, svc, desc) in enumerate(sorted(events)):
            for ax in axes:
                ax.axvline(m, color=C[0] if svc == "gateway" else C[1], lw=1, ls="-.", alpha=0.7)
            axes[2].annotate(f"{svc} → {desc.rstrip('.').split()[-1]}", (m, 4.55 - 0.45 * (k % 2)), xytext=(4, 0), textcoords="offset points", fontsize=9, color=INK2, ha="left")
        save(fig, f"E3_timeline_{cfgdir.name}.png")
        req.groupby(pd.cut(req.t, [0, 3, 6, 9, 12, 15, 20])).apply(
            lambda g: trial_stats(g), include_groups=False).to_csv(cfgdir / "summary_by_step.csv")


if __name__ == "__main__":
    which = sys.argv[1:] or ["E1", "E2", "E3"]
    for w in which:
        {"E1": e1, "E2": e2, "E3": e3}[w]()
