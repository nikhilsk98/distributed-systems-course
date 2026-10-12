#!/usr/bin/env python3
"""Run the MapReduce experiments and save results to results/runs.csv and results/mappers.csv.

For each input size it generates a file by repeating data/input.txt, uploads it to S3,
then runs the job with 1, 2, 3 ... mappers, several times each, verifying every run.

Example (5 tasks running = up to 3 mappers):
    python3 experiment.py --bucket MY-BUCKET
    python3 experiment.py --bucket MY-BUCKET --sizes 1,5,10,25,50 --mappers 1,2,3 --repeats 3
"""
import argparse
import csv
import os
import subprocess
import time

from driver import REGION, assign_roles, load_ips, local_count, run_job

RUN_FIELDS = ["size_mb", "input_bytes", "n_mappers", "repeat", "split_ms", "map_ms",
              "reduce_ms", "total_ms", "total_words", "unique_words", "correct",
              "local_python_ms"]
MAPPER_FIELDS = ["size_mb", "n_mappers", "repeat", "mapper_index", "mapper_ip", "chunk_bytes",
                 "words", "download_ms", "compute_ms", "upload_ms", "server_ms", "client_ms"]


def make_input(base_path, size_mb, out_dir="data"):
    """Create data/gen_<size>MB.txt by repeating the base text to exactly size_mb MiB."""
    target = int(size_mb * 1024 * 1024)
    path = os.path.join(out_dir, f"gen_{size_mb:g}MB.txt")
    if os.path.exists(path) and os.path.getsize(path) == target:
        return path
    with open(base_path, "rb") as f:
        base = f.read()
    if not base:
        raise SystemExit(f"{base_path} is empty")
    if not base.endswith(b"\n"):
        base += b"\n"
    with open(path, "wb") as f:
        written = 0
        while written < target:
            piece = base[: target - written]
            f.write(piece)
            written += len(piece)
    return path


def upload(path, bucket):
    url = f"s3://{bucket}/inputs/{os.path.basename(path)}"
    subprocess.run(["aws", "s3", "cp", path, url, "--region", REGION, "--only-show-errors"],
                   check=True)
    return url


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--base", default="data/input.txt", help="base text file to repeat")
    ap.add_argument("--sizes", default="1,5,10,25,50", help="file sizes in MB")
    ap.add_argument("--mappers", default="1,2,3", help="mapper counts to try")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--ips", default="ips.txt")
    args = ap.parse_args()

    sizes = [float(s) for s in args.sizes.split(",")]
    mapper_counts = [int(m) for m in args.mappers.split(",")]
    ips = load_ips(args.ips)
    assign_roles(ips, max(mapper_counts))  # fail early if not enough tasks
    os.makedirs("results", exist_ok=True)

    with open("results/runs.csv", "w", newline="") as rf, \
         open("results/mappers.csv", "w", newline="") as mf:
        runs_w = csv.DictWriter(rf, fieldnames=RUN_FIELDS)
        maps_w = csv.DictWriter(mf, fieldnames=MAPPER_FIELDS)
        runs_w.writeheader()
        maps_w.writeheader()

        for size in sizes:
            path = make_input(args.base, size)
            print(f"\n=== {size:g} MB ({os.path.getsize(path):,} bytes) ===")
            url = upload(path, args.bucket)

            t0 = time.perf_counter()
            expected = local_count(path)
            local_ms = (time.perf_counter() - t0) * 1000
            print(f"local single-process Python count: {local_ms:.0f} ms")

            # Warm-up run (not recorded) so connection setup / first S3 access
            # does not distort the first measurement.
            run_job(ips, url, mapper_counts[0], expected=expected, verify=False)

            for n in mapper_counts:
                for rep in range(1, args.repeats + 1):
                    run, mrows, _ = run_job(ips, url, n, expected=expected)
                    status = "OK" if run["correct"] else "MISMATCH"
                    print(f"  mappers={n} rep={rep}: total {run['total_ms']:7.0f} ms "
                          f"(split {run['split_ms']:.0f} / map {run['map_ms']:.0f} / "
                          f"reduce {run['reduce_ms']:.0f})  {status}")
                    runs_w.writerow({
                        "size_mb": size, "repeat": rep, "local_python_ms": round(local_ms, 2),
                        **{k: run[k] for k in RUN_FIELDS if k in run},
                    })
                    for m in mrows:
                        maps_w.writerow({"size_mb": size, "n_mappers": n, "repeat": rep, **m})
                    rf.flush()
                    mf.flush()

    print("\nDone. Results in results/runs.csv and results/mappers.csv. Next: python3 plot.py")


if __name__ == "__main__":
    main()
