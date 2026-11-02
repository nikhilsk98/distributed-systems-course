"""E3: autoscaling under step load. Fixed: f4k.bin, 1% loss, default thresholds.
Config A = defaults (gateway MAX_INFLIGHT=4). Config B (MAX_INFLIGHT=16) is defined but was not run (time box).
Autoscaling cooldowns for this run: scale-out 60 s, scale-in 60 s (set with terraform -var scale_in_cooldown=60).
Each config: reset both services to 2 tasks, run the step shape, poll ECS every 10 s for
desired/running/pending counts, then save the scaling activities.
usage: python e3_scaling.py [--configs A,B]
"""
import argparse
import json
import threading
import time

from common import (CLUSTER, RESULTS, cell_done, client, guard, iso, log, mark_done, run_locust,
                    set_desired, set_service_env, utcnow, wait_stable)

SHAPE = "steps:4@180,8@180,16@180,32@180,64@180,4@240"
CONFIGS = {"A": {"MAX_INFLIGHT": 4}, "B": {"MAX_INFLIGHT": 16}}

ap = argparse.ArgumentParser()
ap.add_argument("--configs", default="A")  # time-boxed: only the default config (B is defined but not run)
ap.add_argument("--loss", type=int, default=1)
a = ap.parse_args()


def poll(out, stop):
    ecs, elb = client("ecs"), client("elbv2")
    tgs = {n: elb.describe_target_groups(Names=[f"file-transfer-{n}"])["TargetGroups"][0]["TargetGroupArn"]
           for n in ("gateway", "backend")}
    with open(out / "ecs_timeline.csv", "w") as fh:
        fh.write("utc,service,desired,running,pending,healthy_targets\n")
        while not stop.is_set():
            try:
                now = iso(utcnow())
                for s in ecs.describe_services(cluster=CLUSTER, services=["gateway", "backend"])["services"]:
                    th = elb.describe_target_health(TargetGroupArn=tgs[s["serviceName"]])["TargetHealthDescriptions"]
                    healthy = sum(d["TargetHealth"]["State"] == "healthy" for d in th)
                    fh.write(f"{now},{s['serviceName']},{s['desiredCount']},{s['runningCount']},{s['pendingCount']},{healthy}\n")
                fh.flush()
            except Exception as e:  # keep polling through transient errors
                log("poll error", e)
            stop.wait(10)


guard(lambda: set_service_env("backend", {"SEND_LOSS": a.loss, "RECV_LOSS": a.loss}))
for cfg in a.configs.split(","):
    out = RESULTS / "E3" / f"config{cfg}"
    if cell_done(out):
        continue
    out.mkdir(parents=True, exist_ok=True)
    guard(lambda: set_service_env("gateway", CONFIGS[cfg]))
    for s in ("gateway", "backend"):
        guard(lambda: set_desired(s, 2))
    guard(lambda: wait_stable("gateway"))
    guard(lambda: wait_stable("backend"))
    log("settling 60 s before load")
    time.sleep(60)
    stop = threading.Event()
    th = threading.Thread(target=poll, args=(out, stop), daemon=True)
    th.start()
    meta = run_locust(out, 0, 0, "f4k.bin", shape=SHAPE)
    log("load done; observing 120 s more")
    time.sleep(120)
    stop.set()
    th.join()
    meta["observe_end_utc"] = iso(utcnow())
    aas = client("application-autoscaling")
    acts = guard(lambda: aas.describe_scaling_activities(ServiceNamespace="ecs", MaxResults=50)["ScalingActivities"])
    (out / "scaling_activities.json").write_text(json.dumps(acts, indent=2, default=str))
    mark_done(out, {"experiment": "E3", "cell": f"config{cfg}", "trial": 1, "config": CONFIGS[cfg], "loss": a.loss, **meta})
log("E3 complete")
