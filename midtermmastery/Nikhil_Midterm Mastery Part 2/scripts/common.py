"""Shared helpers for the experiment drivers.

- ECS env-var changes (clone task definition -> update service -> wait stable)
- running Locust headless with exact UTC start/end timestamps
- resumable cells (a cell with done.json is skipped)
- a clear exit (code 3) when Learner Lab credentials expire

Nothing here stores credentials: boto3 reads ~/.aws/credentials at process start, so after a
refresh simply re-run the driver and it resumes from the first unfinished cell.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "us-east-1")
CLUSTER = "file-transfer"
SCRIPTS = Path(__file__).resolve().parent
DELIV = SCRIPTS.parent
RESULTS = DELIV / "results"
FORK = Path(os.environ.get("FORK_DIR", Path.home() / "Documents/Northeastern/Sem 3/file-transfer-playservice"))
LOCUST = os.environ.get("LOCUST_BIN", "locust")

EXPIRED_CODES = {"ExpiredToken", "ExpiredTokenException", "RequestExpired", "InvalidClientTokenId", "UnrecognizedClientException"}


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def log(*a):
    print(f"[{datetime.now().strftime('%H:%M:%S')}]", *a, flush=True)


def client(name):
    return boto3.client(name, region_name=REGION)


def guard(fn):
    """Run fn(); exit with code 3 and a clear message if AWS credentials have expired."""
    try:
        return fn()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in EXPIRED_CODES:
            print("\n*** AWS CREDENTIALS EXPIRED: refresh ~/.aws/credentials and re-run; the driver resumes. ***", flush=True)
            sys.exit(3)
        raise


def alb_dns():
    if os.environ.get("ALB_DNS"):
        return os.environ["ALB_DNS"]
    lb = client("elbv2").describe_load_balancers(Names=["file-transfer-gateway"])["LoadBalancers"][0]
    return lb["DNSName"]


# ---------- ECS env management ----------

def current_env(service):
    ecs = client("ecs")
    svc = ecs.describe_services(cluster=CLUSTER, services=[service])["services"][0]
    td = ecs.describe_task_definition(taskDefinition=svc["taskDefinition"])["taskDefinition"]
    return {e["name"]: e["value"] for e in td["containerDefinitions"][0]["environment"]}, td


def set_service_env(service, updates, cpu=None, memory=None):
    """Register a task definition revision with `updates` applied (and optionally a new task
    cpu/memory size) and roll the service. Skips when the running task definition already
    matches. Waits until stable."""
    updates = {k: str(v) for k, v in updates.items()}
    env, td = current_env(service)
    same_size = (cpu is None or td["cpu"] == str(cpu)) and (memory is None or td["memory"] == str(memory))
    if same_size and all(env.get(k) == v for k, v in updates.items()):
        log(f"{service}: env already {updates}")
        wait_stable(service)
        return td["taskDefinitionArn"]
    env.update(updates)
    cdefs = td["containerDefinitions"]
    cdefs[0]["environment"] = [{"name": k, "value": v} for k, v in sorted(env.items())]
    keep = ["family", "taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions",
            "volumes", "requiresCompatibilities", "cpu", "memory", "runtimePlatform"]
    args = {k: td[k] for k in keep if k in td}
    if cpu:
        args["cpu"] = str(cpu)
    if memory:
        args["memory"] = str(memory)
    args["tags"] = [{"key": "Project", "value": "cs6650-midterm"}]
    ecs = client("ecs")
    new = ecs.register_task_definition(**args)["taskDefinition"]["taskDefinitionArn"]
    ecs.update_service(cluster=CLUSTER, service=service, taskDefinition=new)
    log(f"{service}: rolling to {new.split('/')[-1]} with {updates} cpu={args['cpu']} mem={args['memory']}")
    wait_stable(service)
    return new


def wait_stable(service):
    t0 = time.time()
    client("ecs").get_waiter("services_stable").wait(
        cluster=CLUSTER, services=[service], WaiterConfig={"Delay": 10, "MaxAttempts": 90})
    wait_targets_healthy()
    log(f"{service}: stable after {time.time() - t0:.0f}s")


def wait_targets_healthy(timeout=300):
    elb = client("elbv2")
    t0 = time.time()
    while time.time() - t0 < timeout:
        ok = True
        for name in ("file-transfer-gateway", "file-transfer-backend"):
            arn = elb.describe_target_groups(Names=[name])["TargetGroups"][0]["TargetGroupArn"]
            states = [d["TargetHealth"]["State"] for d in elb.describe_target_health(TargetGroupArn=arn)["TargetHealthDescriptions"]]
            if not states or any(s != "healthy" for s in states):
                ok = False
        if ok:
            return
        time.sleep(5)
    log("warning: targets not all healthy after timeout")


def set_desired(service, n):
    client("ecs").update_service(cluster=CLUSTER, service=service, desiredCount=n)


# ---------- Locust ----------

def run_locust(outdir, users, run_time, file, extra_query="", spawn_rate=None, shape=None, wait="0.5"):
    """Run Locust headless; write CSVs, HTML report, per-request JSONL and meta.json into outdir."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"FT_FILE": file, "FT_EXTRA_QUERY": extra_query, "FT_REQ_LOG": str(outdir / "requests.jsonl"),
                "FT_WAIT": wait})
    if shape:
        env["FT_SHAPE"] = shape
    cmd = [LOCUST, "-f", str(SCRIPTS / "locustfile.py"), "--headless", "--host", f"http://{alb_dns()}",
           "--csv", str(outdir / "locust"), "--csv-full-history", "--html", str(outdir / "report.html"),
           "--only-summary", "--loglevel", "WARNING"]
    if not shape:
        cmd += ["-u", str(users), "-r", str(spawn_rate or users), "-t", f"{run_time}s", "--stop-timeout", "60"]
    else:
        cmd += ["--stop-timeout", "60"]
    start = utcnow()
    log(f"locust -> {outdir.name if RESULTS not in outdir.parents else outdir.relative_to(RESULTS)} users={users} t={run_time}s file={file} q='{extra_query}' shape={shape}")
    with open(outdir / "locust_stdout.txt", "w") as fh:
        rc = subprocess.run(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT).returncode
    end = utcnow()
    meta = {"start_utc": iso(start), "end_utc": iso(end), "users": users, "run_time_s": run_time, "file": file,
            "extra_query": extra_query, "shape": shape, "locust_rc": rc, "cmd": " ".join(cmd)}
    (outdir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def cell_done(outdir):
    return (Path(outdir) / "done.json").exists()


def mark_done(outdir, info):
    (Path(outdir) / "done.json").write_text(json.dumps(info, indent=2))
    with open(RESULTS / "run_ledger.csv", "a") as fh:
        fh.write(",".join(str(info.get(k, "")) for k in ("experiment", "cell", "trial", "start_utc", "end_utc")) + "\n")
