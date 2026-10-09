"""Smoke test for a running netscope.

Usage: python scripts/smoke_test.py http://127.0.0.1:8000
"""
import json
import sys
import time
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/")


def get(path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as res:
            return res.status, res.read().decode()
    except urllib.error.HTTPError as e:
        e.close()
        return e.code, ""
    except OSError:
        return None, ""


def check(condition, message):
    if not condition:
        sys.exit("FAIL: " + message)


# 1. wait until the server answers and has finished its first checks
deadline = time.time() + 40
while time.time() < deadline:
    status, _ = get("/readyz")
    if status == 200:
        break
    time.sleep(1)
else:
    sys.exit("FAIL: /readyz never returned 200 within 40 seconds")
print("ok: /readyz is 200")

status, _ = get("/healthz")
check(status == 200, f"/healthz returned {status}")
print("ok: /healthz is 200")

status, body = get("/metrics")
check(status == 200 and "netscope_requests_total" in body,
      "/metrics is missing or has no netscope_requests_total")
print("ok: /metrics contains netscope_requests_total")

status, body = get("/api/status")
check(status == 200, f"/api/status returned {status}")
targets = json.loads(body)["targets"]
check(targets and targets[0]["state"] == "up", f"target is not up: {targets}")
print("ok: /api/status reports the target as up")
print("smoke test passed")