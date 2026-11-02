"""E2: retry-budget trade-off. Loss fixed (backend SEND_LOSS=RECV_LOSS=5); the budget is set per
request with the gateway's query override (ALLOW_BUDGET_OVERRIDE=1), so no redeploys are needed.
  sweep A: retry_rounds in {1,2,3,5,10,20}, open_attempts=5, files f16k and f64k
  sweep B: open_attempts in {1,2,10}, retry_rounds=5, file f16k   (5/5 comes from sweep A)
usage: python e2_retry_budget.py [--loss 5] [--trials 3] [--seconds 60] [--users 2]
"""
import argparse
from common import RESULTS, cell_done, guard, log, mark_done, run_locust, set_service_env

ap = argparse.ArgumentParser()
ap.add_argument("--loss", type=int, default=5)
ap.add_argument("--trials", type=int, default=3)
ap.add_argument("--seconds", type=int, default=60)
ap.add_argument("--users", type=int, default=2)
a = ap.parse_args()

cells = [(f, 5, r) for f in ("f16k.bin", "f64k.bin") for r in (1, 2, 3, 5, 10, 20)]
cells += [("f16k.bin", o, 5) for o in (1, 2, 10)]

guard(lambda: set_service_env("backend", {"SEND_LOSS": a.loss, "RECV_LOSS": a.loss}))
for t in range(1, a.trials + 1):
    for f, opens, rounds in cells:
        name = f"{f.split('.')[0]}_open{opens:02d}_rounds{rounds:02d}"
        out = RESULTS / "E2" / name / f"trial{t}"
        if cell_done(out):
            continue
        meta = run_locust(out, a.users, a.seconds, f, f"open_attempts={opens}&retry_rounds={rounds}")
        mark_done(out, {"experiment": "E2", "cell": name, "trial": t, "loss": a.loss, "open_attempts": opens,
                        "retry_rounds": rounds, **meta})
log("E2 complete")
