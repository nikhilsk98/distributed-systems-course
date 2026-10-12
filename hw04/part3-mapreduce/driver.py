#!/usr/bin/env python3
"""Run one MapReduce word-count job against the ECS workers and verify it.

Roles come from ips.txt (written by run-tasks.sh):
    first IP = splitter, last IP = reducer, everything in between = mappers.

Example:
    python3 driver.py --input s3://MY-BUCKET/inputs/input.txt --local data/input.txt
    python3 driver.py --input s3://MY-BUCKET/inputs/input.txt --local data/input.txt --mappers 1

Only the Python standard library is used. Verification downloads the reducer's
final JSON with the AWS CLI (`aws s3 cp`), which you already have configured.
"""
import argparse
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

PORT = 8080
REGION = "us-west-2"
# Same word rule as the Go worker: maximal runs of ASCII letters/digits, lowercased.
WORD_RE = re.compile(rb"[A-Za-z0-9]+")


def http_get(ip, path, params, timeout=900):
    """GET http://ip:8080/path?params and return (json_body, client_ms)."""
    url = f"http://{ip}:{PORT}{path}?" + urllib.parse.urlencode(params)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path} on {ip} failed: HTTP {e.code}: "
                           f"{e.read().decode(errors='replace')}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach {ip}:{PORT} ({e.reason}). Is the task "
                           f"running and is port 8080 open?") from None
    return body, (time.perf_counter() - t0) * 1000


def load_ips(path="ips.txt"):
    with open(path) as f:
        ips = [line.strip() for line in f if line.strip()]
    if len(ips) < 3:
        raise SystemExit(f"{path} needs at least 3 IPs (splitter, >=1 mapper, reducer)")
    return ips


def assign_roles(ips, n_mappers):
    splitter, reducer, mappers = ips[0], ips[-1], ips[1:-1]
    if n_mappers > len(mappers):
        raise SystemExit(f"asked for {n_mappers} mappers but only {len(mappers)} mapper "
                         f"IPs are available; run more tasks (bash run-tasks.sh N)")
    return splitter, mappers[:n_mappers], reducer


def local_count(path):
    """Single-process word count on this laptop (ground truth for verification)."""
    with open(path, "rb") as f:
        data = f.read()
    return dict(Counter(w.lower().decode() for w in WORD_RE.findall(data)))


def fetch_s3_json(s3_url):
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        subprocess.run(["aws", "s3", "cp", s3_url, tmp, "--region", REGION,
                        "--only-show-errors"], check=True)
        with open(tmp) as f:
            return json.load(f)
    finally:
        os.remove(tmp)


def run_job(ips, input_url, n_mappers, local_path=None, expected=None, verify=True):
    """Run split -> parallel map -> reduce. Returns (run_row, mapper_rows, final_or_None)."""
    splitter, mappers, reducer = assign_roles(ips, n_mappers)

    t_start = time.perf_counter()
    split, split_ms = http_get(splitter, "/split", {"url": input_url, "n": n_mappers})
    chunks = split["chunks"]

    # All mappers run at the same time - this is where the parallel speedup comes from.
    t_map = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futures = [pool.submit(http_get, mappers[i % len(mappers)], "/map", {"url": c})
                   for i, c in enumerate(chunks)]
        map_results = [f.result() for f in futures]
    map_ms = (time.perf_counter() - t_map) * 1000

    outputs = ",".join(body["output"] for body, _ in map_results)
    reduce, reduce_ms = http_get(reducer, "/reduce", {"urls": outputs})
    total_ms = (time.perf_counter() - t_start) * 1000

    correct, final = None, None
    if verify and (expected is not None or local_path):
        if expected is None:
            expected = local_count(local_path)
        final = fetch_s3_json(reduce["output"])
        correct = final == expected

    run_row = {
        "input_bytes": split["input_bytes"],
        "n_mappers": n_mappers,
        "split_ms": round(split_ms, 2),
        "map_ms": round(map_ms, 2),
        "reduce_ms": round(reduce_ms, 2),
        "total_ms": round(total_ms, 2),
        "total_words": reduce["total_words"],
        "unique_words": reduce["unique_words"],
        "correct": correct,
        "final_output": reduce["output"],
    }
    mapper_rows = []
    for i, (body, client_ms) in enumerate(map_results):
        t = body["timings"]
        mapper_rows.append({
            "mapper_index": i,
            "mapper_ip": mappers[i % len(mappers)],
            "chunk_bytes": body["chunk_bytes"],
            "words": body["total_words"],
            "download_ms": t["download_ms"],
            "compute_ms": t["compute_ms"],
            "upload_ms": t["upload_ms"],
            "server_ms": t["total_ms"],
            "client_ms": round(client_ms, 2),
        })
    return run_row, mapper_rows, final


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="s3://bucket/key of the text file")
    ap.add_argument("--local", help="local copy of the same file, used to verify the result")
    ap.add_argument("--ips", default="ips.txt", help="file with worker IPs (default ips.txt)")
    ap.add_argument("--mappers", type=int, default=3, help="number of mappers (default 3)")
    args = ap.parse_args()

    ips = load_ips(args.ips)
    splitter, mappers, reducer = assign_roles(ips, args.mappers)
    print(f"splitter: {splitter}\nmappers:  {', '.join(mappers)}\nreducer:  {reducer}\n")

    run, mrows, final = run_job(ips, args.input, args.mappers, local_path=args.local)

    print(f"input size : {run['input_bytes']:,} bytes")
    print(f"split      : {run['split_ms']:.0f} ms")
    print(f"map        : {run['map_ms']:.0f} ms  ({args.mappers} mappers in parallel)")
    print(f"reduce     : {run['reduce_ms']:.0f} ms")
    print(f"TOTAL      : {run['total_ms']:.0f} ms")
    print(f"words      : {run['total_words']:,} total, {run['unique_words']:,} unique")
    print(f"final JSON : {run['final_output']}\n")
    print("per-mapper (load balance):")
    for m in mrows:
        print(f"  mapper {m['mapper_index']} {m['mapper_ip']:>15}: {m['chunk_bytes']:>11,} bytes "
              f"{m['words']:>10,} words  compute {m['compute_ms']:>8.1f} ms  "
              f"total {m['server_ms']:>8.1f} ms")

    if run["correct"] is None:
        print("\n(no --local file given, so the result was not verified)")
    elif run["correct"]:
        print("\nVERIFIED: distributed result matches the local single-process count")
        top = sorted(final.items(), key=lambda kv: -kv[1])[:10]
        print("top 10 words:", ", ".join(f"{w}={c}" for w, c in top))
    else:
        expected = local_count(args.local)
        diff = [w for w in set(expected) | set(final) if expected.get(w) != final.get(w)]
        print(f"\nMISMATCH: {len(diff)} words differ, e.g.:")
        for w in diff[:10]:
            print(f"  {w!r}: expected {expected.get(w)}, got {final.get(w)}")


if __name__ == "__main__":
    main()
