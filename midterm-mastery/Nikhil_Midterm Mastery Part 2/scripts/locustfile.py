"""Locust load for the file-transfer gateway.

Configured by environment variables (set by the drivers in common.run_locust):
  FT_FILE         file name to request (e.g. f64k.bin)
  FT_EXTRA_QUERY  extra query string, e.g. "retry_rounds=3&open_attempts=5" (budget override, E2)
  FT_REQ_LOG      path of a JSONL file; one line per request with the gateway's X-* stats headers
  FT_WAIT         seconds each user waits between requests (closed loop), default 0.5
  FT_SHAPE        optional "steps:USERS@SECONDS,USERS@SECONDS,..." load shape (E3)
"""
import json
import os
import threading
import time

from locust import HttpUser, LoadTestShape, constant, events, task

FILE = os.environ.get("FT_FILE", "f64k.bin")
EXTRA = os.environ.get("FT_EXTRA_QUERY", "")
REQ_LOG = os.environ.get("FT_REQ_LOG")
EXPECTED = {"f4k.bin": 4096, "f16k.bin": 16384, "f64k.bin": 65536, "f256k.bin": 262144, "f1m.bin": 1048576, "f4m.bin": 4194304, "hello.txt": 14}

_lock = threading.Lock()
_fh = open(REQ_LOG, "a") if REQ_LOG else None


class FileUser(HttpUser):
    wait_time = constant(float(os.environ.get("FT_WAIT", "0.5")))

    @task
    def get_file(self):
        url = f"/files?name={FILE}" + (f"&{EXTRA}" if EXTRA else "")
        started = time.time()
        with self.client.get(url, name=f"GET {FILE}", catch_response=True, timeout=120) as r:
            ok = r.status_code == 200 and (FILE not in EXPECTED or len(r.content) == EXPECTED[FILE])
            if r.status_code == 200 and not ok:
                r.failure(f"wrong length {len(r.content)}")
            elif not ok:
                r.failure(f"HTTP {r.status_code}")
            else:
                r.success()
            if _fh:
                h = r.headers
                row = {"t_start": round(started, 3), "latency_ms": round((time.time() - started) * 1000, 1),
                       "status": r.status_code, "ok": ok, "bytes": len(r.content or b""), "file": FILE, "query": EXTRA,
                       "task": h.get("X-Task"), "queue_ms": _i(h.get("X-Queue-Wait-Ms")), "fetch_ms": _i(h.get("X-Fetch-Ms")),
                       "open_attempts": _i(h.get("X-Open-Attempts")), "retry_rounds": _i(h.get("X-Retry-Rounds")),
                       "rety_sent": _i(h.get("X-Rety-Sent")), "redials": _i(h.get("X-Redials")),
                       "chunks": _i(h.get("X-Chunks")), "datagrams_rx": _i(h.get("X-Datagrams-Received")),
                       "dup_rx": _i(h.get("X-Duplicate-Datagrams")), "missing_after_open": _i(h.get("X-Missing-After-Open")),
                       "missing_at_end": _i(h.get("X-Missing-At-End")), "budget": h.get("X-Budget")}
                with _lock:
                    _fh.write(json.dumps(row) + "\n")
                    _fh.flush()


def _i(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class Steps(LoadTestShape):
    """Step load from FT_SHAPE="steps:4@180,8@180,..." (users@seconds). Only active when set."""
    spec = os.environ.get("FT_SHAPE", "")
    use_common_options = False

    def __init__(self):
        super().__init__()
        self.steps = []
        if self.spec.startswith("steps:"):
            t = 0
            for part in self.spec[len("steps:"):].split(","):
                users, secs = part.split("@")
                t += int(secs)
                self.steps.append((t, int(users)))

    def tick(self):
        if not self.steps:
            return None
        now = self.get_run_time()
        for end, users in self.steps:
            if now < end:
                return users, max(users, 1)
        return None


if not os.environ.get("FT_SHAPE"):
    # Locust picks up any LoadTestShape subclass in the file; drop it when no shape is wanted.
    del Steps
