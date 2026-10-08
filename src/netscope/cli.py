import argparse
import copy
import json
import socket
import ssl
import sys
import time
import threading
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, HTTPServer

BUCKETS_MS = [50, 100, 250, 500, 1000, 5000]
CHECKED_HEADERS = [
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "content-security-policy",
    "cache-control",
]

stats = {}
stats_lock = threading.Lock()


def new_stats():
    return {
        "requests_total": 0,
        "errors_total": 0,
        "status_code": 0,
        "last_timings": {},
        "headers_present": {},
        "last_error": None,
        "last_check": None,
        "bucket_counts": [0] * len(BUCKETS_MS),
        "hist_count": 0,
        "hist_sum": 0.0,
    }


def normalize_url(u):
    return u if "://" in u else "https://" + u


def request(url, timeout):
    parts = urlsplit(url)
    scheme = parts.scheme
    assert scheme in ("http", "https"), "Only http/https supported"
    host = parts.hostname
    port = parts.port or (443 if scheme == "https" else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query

    timings = {}
    t_start = time.perf_counter()

    t0 = time.perf_counter()
    ip = socket.gethostbyname(host)
    timings["dns_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    s = socket.create_connection((ip, port), timeout=timeout)
    timings["connect_ms"] = (time.perf_counter() - t0) * 1000

    try:
        if scheme == "https":
            t0 = time.perf_counter()
            context = ssl.create_default_context()
            s = context.wrap_socket(s, server_hostname=host)
            timings["tls_ms"] = (time.perf_counter() - t0) * 1000

        req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        t0 = time.perf_counter()
        s.sendall(req.encode())

        response = s.makefile("rb")
        first_line = response.readline()
        timings["ttfb_ms"] = (time.perf_counter() - t0) * 1000

        status_line = first_line.decode().strip()
        status_code = int(status_line.split()[1])

        headers = {}
        while True:
            line = response.readline().decode()
            if line in ("\r\n", "\n", ""):
                break
            k, v = line.split(":", 1)
            headers[k.strip().casefold()] = v.strip()

        body = response.read()
    finally:
        s.close()

    timings["total_ms"] = (time.perf_counter() - t_start) * 1000

    return {
        "url": url,
        "ip": ip,
        "status": status_line,
        "status_code": status_code,
        "headers": headers,
        "body_size": len(body),
        "timings": timings,
    }


def print_report(result):
    print(f"URL:         {result['url']}")
    print(f"Resolved IP: {result['ip']}")
    print(f"Status:      {result['status']}")
    print(f"Body size:   {result['body_size']} bytes")
    print("Timing breakdown:")
    for key, val in result["timings"].items():
        print(f"  {key:12s}: {val:.2f} ms")
    if 300 <= result["status_code"] < 400:
        loc = result["headers"].get("location", "?")
        print(f"Note: this is a redirect to {loc} (netscope does not follow redirects),")
        print("      so the header check below describes the redirect, not the final page.")
    print("Header check:")
    is_http = result["url"].startswith("http://")
    for h in CHECKED_HEADERS:
        if h in result["headers"]:
            print(f"  [OK]   {h}: {result['headers'][h]}")
        elif h == "strict-transport-security" and is_http:
            print(f"  [INFO] {h} only applies over HTTPS")
        else:
            print(f"  [WARN] missing {h}")
    if "server" in result["headers"]:
        print(f"  [INFO] server header exposes: {result['headers']['server']}")


def background_checker(target_url, interval_seconds, timeout, stop=None):
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            result = request(target_url, timeout)
            t = result["timings"]
            with stats_lock:
                st = stats[target_url]
                st["requests_total"] += 1
                st["status_code"] = result["status_code"]
                st["last_timings"] = t
                st["headers_present"] = {
                    h: (h in result["headers"]) for h in CHECKED_HEADERS
                }
                st["last_error"] = None
                st["last_check"] = time.time()
                st["hist_count"] += 1
                st["hist_sum"] += t["total_ms"]
                for i, limit in enumerate(BUCKETS_MS):
                    if t["total_ms"] <= limit:
                        st["bucket_counts"][i] += 1
            stages = " ".join(
                f"{k.replace('_ms', '')}={v:.0f}" for k, v in t.items() if k != "total_ms"
            )
            missing = [h for h in CHECKED_HEADERS if h not in result["headers"]]
            print(f"[checked] {target_url} -> {result['status_code']} "
                  f"total={t['total_ms']:.0f}ms | {stages} | missing_headers={len(missing)}")
        except Exception as e:
            with stats_lock:
                st = stats[target_url]
                st["requests_total"] += 1
                st["errors_total"] += 1
                st["last_error"] = f"{type(e).__name__}: {e}"
                st["last_check"] = time.time()
            print(f"[error] {target_url} -> {type(e).__name__}: {e}")
        stop.wait(interval_seconds)


def render_metrics():
    with stats_lock:
        snap = copy.deepcopy(stats)

    lines = []

    def header(name, mtype, help_text):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")

    header("netscope_requests_total", "counter", "Total checks performed")
    for url, st in snap.items():
        lines.append(f'netscope_requests_total{{url="{url}"}} {st["requests_total"]}')

    header("netscope_errors_total", "counter", "Total failed checks")
    for url, st in snap.items():
        lines.append(f'netscope_errors_total{{url="{url}"}} {st["errors_total"]}')

    header("netscope_status_code", "gauge", "HTTP status code of the last successful check")
    for url, st in snap.items():
        lines.append(f'netscope_status_code{{url="{url}"}} {st["status_code"]}')

    header("netscope_stage_ms", "gauge", "Duration of each request stage in the last check")
    for url, st in snap.items():
        for key, val in st["last_timings"].items():
            stage = key.replace("_ms", "")
            lines.append(f'netscope_stage_ms{{url="{url}",stage="{stage}"}} {val:.2f}')

    header("netscope_header_present", "gauge", "1 if the response header was present in the last check, else 0")
    for url, st in snap.items():
        for h, present in st["headers_present"].items():
            lines.append(
                f'netscope_header_present{{url="{url}",header="{h}"}} {1 if present else 0}'
            )

    header("netscope_request_duration_ms", "histogram", "Total request duration in ms")
    for url, st in snap.items():
        for limit, count in zip(BUCKETS_MS, st["bucket_counts"]):
            lines.append(
                f'netscope_request_duration_ms_bucket{{url="{url}",le="{limit}"}} {count}'
            )
        lines.append(
            f'netscope_request_duration_ms_bucket{{url="{url}",le="+Inf"}} {st["hist_count"]}'
        )
        lines.append(f'netscope_request_duration_ms_sum{{url="{url}"}} {st["hist_sum"]:.2f}')
        lines.append(f'netscope_request_duration_ms_count{{url="{url}"}} {st["hist_count"]}')

    return "\n".join(lines) + "\n"


def render_status():
    """Same data as /metrics, shaped as JSON for the dashboard."""
    with stats_lock:
        snap = copy.deepcopy(stats)

    targets = []
    for url, st in snap.items():
        if st["requests_total"] == 0:
            state = "pending"
        elif st["last_error"]:
            state = "down"
        else:
            state = "up"
        targets.append({
            "url": url,
            "state": state,
            "status_code": st["status_code"],
            "requests_total": st["requests_total"],
            "errors_total": st["errors_total"],
            "timings": st["last_timings"],
            "headers": st["headers_present"],
            "last_error": st["last_error"],
            "last_check": st["last_check"],
        })
    return {"generated_at": time.time(), "targets": targets}


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>netscope</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --text:#1c2230; --muted:#6b7385; --line:#e3e6ec;
          --ok:#1a7f4b; --okbg:#e3f5ea; --bad:#b42318; --badbg:#fde8e6; --wait:#8a6100; --waitbg:#fff3d6; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#12151c; --card:#1b2029; --text:#e7eaf0; --muted:#97a0b3; --line:#2a303c;
            --ok:#5fd99a; --okbg:#173326; --bad:#ff8f84; --badbg:#3a1d1a; --wait:#f2c75c; --waitbg:#37300f; }
  }
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background:var(--bg); color:var(--text); }
  header { padding:20px 24px 8px; display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; }
  h1 { margin:0; font-size:20px; }
  #updated { color:var(--muted); font-size:13px; }
  main { padding:8px 24px 32px; }
  .wrap { background:var(--card); border:1px solid var(--line); border-radius:10px; overflow-x:auto; }
  table { border-collapse:collapse; width:100%; font-size:14px; }
  th, td { text-align:left; padding:10px 14px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  tr:last-child td { border-bottom:none; }
  .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:600; margin-right:4px; }
  .up, .on { background:var(--okbg); color:var(--ok); }
  .down, .off { background:var(--badbg); color:var(--bad); }
  .pending { background:var(--waitbg); color:var(--wait); }
  .num { font-variant-numeric: tabular-nums; }
  .err { color:var(--bad); white-space:normal; max-width:320px; }
  .muted { color:var(--muted); }
  .empty { padding:24px; color:var(--muted); }
</style>
</head>
<body>
<header>
  <h1>netscope</h1>
  <span id="updated">Loading...</span>
</header>
<main>
  <div class="wrap">
    <table>
      <thead>
        <tr><th>Site</th><th>State</th><th>HTTP</th><th>Total</th><th>Stages (ms)</th>
            <th>Headers</th><th>Checks</th><th>Last check</th><th>Last error</th></tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
    <div id="empty" class="empty" hidden>No targets yet.</div>
  </div>
</main>
<script>
const HEADER_LABELS = {
  "strict-transport-security": "HSTS",
  "x-content-type-options": "nosniff",
  "x-frame-options": "XFO",
  "content-security-policy": "CSP",
  "cache-control": "Cache"
};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function td(child, cls) {
  const cell = el("td", cls);
  if (typeof child === "string") cell.textContent = child; else if (child) cell.appendChild(child);
  return cell;
}

function fmt(ms) { return ms === undefined ? "-" : ms.toFixed(0); }

function render(data) {
  const rows = document.getElementById("rows");
  rows.replaceChildren();
  document.getElementById("empty").hidden = data.targets.length > 0;

  for (const t of data.targets) {
    const tr = el("tr");
    tr.appendChild(td(t.url));
    tr.appendChild(td(el("span", "badge " + t.state, t.state.toUpperCase())));
    tr.appendChild(td(t.state === "pending" ? "-" : String(t.status_code || "-"), "num"));
    tr.appendChild(td(t.timings.total_ms === undefined ? "-" : fmt(t.timings.total_ms) + " ms", "num"));

    const parts = [];
    for (const k of ["dns_ms", "connect_ms", "tls_ms", "ttfb_ms"]) {
      if (t.timings[k] !== undefined) parts.push(k.replace("_ms", "") + " " + fmt(t.timings[k]));
    }
    tr.appendChild(td(parts.length ? parts.join(" | ") : "-", "num muted"));

    const hdrs = el("span");
    const names = Object.keys(t.headers);
    if (names.length === 0) hdrs.textContent = "-";
    for (const h of names) {
      const b = el("span", "badge " + (t.headers[h] ? "on" : "off"), HEADER_LABELS[h] || h);
      b.title = h + (t.headers[h] ? ": present" : ": missing");
      hdrs.appendChild(b);
    }
    tr.appendChild(td(hdrs));

    tr.appendChild(td(t.requests_total + " (" + t.errors_total + " errors)", "num"));

    let ago = "-";
    if (t.last_check) ago = Math.max(0, Math.round(data.generated_at - t.last_check)) + " s ago";
    tr.appendChild(td(ago, "muted"));

    tr.appendChild(td(t.last_error || "", "err"));
    rows.appendChild(tr);
  }
}

async function refresh() {
  const label = document.getElementById("updated");
  try {
    const res = await fetch("/api/status", { cache: "no-store" });
    render(await res.json());
    label.textContent = "Updated " + new Date().toLocaleTimeString();
  } catch (e) {
    label.textContent = "Cannot reach netscope";
  }
}

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


class MetricsHandler(BaseHTTPRequestHandler):
    def _send(self, status, content_type, body=b""):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/metrics":
            self._send(200, "text/plain; version=0.0.4", render_metrics().encode())
        elif path == "/api/status":
            self._send(200, "application/json", json.dumps(render_status()).encode())
        elif path == "/":
            self._send(200, "text/html; charset=utf-8", DASHBOARD_HTML.encode())
        else:
            self._send(404, "text/plain", b"not found\n")

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(
        prog="netscope",
        description="HTTP diagnostics: per-stage timings, header checks, Prometheus metrics.",
    )
    parser.add_argument("urls", nargs="+", help="one or more URLs (https:// is assumed if omitted)")
    parser.add_argument("--once", action="store_true",
                        help="check each URL once, print a report, and exit")
    parser.add_argument("--interval", type=float, default=10,
                        help="seconds between checks in watch mode (default 10)")
    parser.add_argument("--port", type=int, default=8000,
                        help="port for the dashboard and /metrics in watch mode (default 8000)")
    parser.add_argument("--timeout", type=float, default=10,
                        help="socket timeout in seconds (default 10)")
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be greater than 0")

    urls = list(dict.fromkeys(normalize_url(u) for u in args.urls))

    if args.once:
        failed = False
        for url in urls:
            try:
                print_report(request(url, args.timeout))
            except Exception as e:
                failed = True
                print(f"[error] {url} -> {type(e).__name__}: {e}")
            print()
        sys.exit(1 if failed else 0)

    # Bind the web server FIRST, so a port problem is reported immediately
    # instead of leaving the checkers running with no dashboard.
    try:
        server = HTTPServer(("127.0.0.1", args.port), MetricsHandler)
    except OSError as e:
        print(f"[fatal] cannot listen on 127.0.0.1:{args.port} -> {e}")
        print("        Is another netscope still running? Try a different --port.")
        sys.exit(1)

    for url in urls:
        stats[url] = new_stats()
        threading.Thread(
            target=background_checker,
            args=(url, args.interval, args.timeout),
            daemon=True,
        ).start()

    print(f"Checking {len(urls)} target(s) every {args.interval:g}s")
    print(f"Dashboard: http://127.0.0.1:{args.port}/")
    print(f"Metrics:   http://127.0.0.1:{args.port}/metrics")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
