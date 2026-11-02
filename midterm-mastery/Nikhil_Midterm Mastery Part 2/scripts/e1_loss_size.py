"""E1: reliability under loss. Varies backend SEND_LOSS=RECV_LOSS x file size; budget fixed at 5/5/2s.

Resumable: re-run after a crash or expired credentials and finished cells are skipped.
usage: python e1_loss_size.py [--trials 3] [--seconds 60] [--users 2]
"""
import argparse
from common import RESULTS, cell_done, guard, log, mark_done, run_locust, set_service_env

LOSSES = [0, 1, 5, 10, 20]
FILES = ["f4k.bin", "f16k.bin", "f64k.bin", "f1m.bin"]

ap = argparse.ArgumentParser()
ap.add_argument("--trials", type=int, default=3)
ap.add_argument("--seconds", type=int, default=60)
ap.add_argument("--users", type=int, default=2)
a = ap.parse_args()

for loss in LOSSES:
    cells = [(t, f) for t in range(1, a.trials + 1) for f in FILES]
    todo = [(t, f) for t, f in cells if not cell_done(RESULTS / "E1" / f"loss{loss:02d}_{f.split('.')[0]}" / f"trial{t}")]
    if not todo:
        continue
    guard(lambda: set_service_env("backend", {"SEND_LOSS": loss, "RECV_LOSS": loss}))
    for t, f in todo:  # trial-major order interleaves sizes so slow drift does not land on one size
        out = RESULTS / "E1" / f"loss{loss:02d}_{f.split('.')[0]}" / f"trial{t}"
        meta = run_locust(out, a.users, a.seconds, f)
        mark_done(out, {"experiment": "E1", "cell": f"loss{loss}_{f}", "trial": t, "loss": loss, **meta})
log("E1 complete")
