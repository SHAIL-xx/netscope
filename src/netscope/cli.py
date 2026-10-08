import argparse
import copy
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

    # DNS
    t0 = time.perf_counter()
    ip = socket.gethostbyname(host)
    timings["dns_ms"] = (time.perf_counter() - t0) * 1000

    # TCP connect
    t0 = time.perf_counter()
    s = socket.create_connection((ip, port), timeout=timeout)
    timings["connect_ms"] = (time.perf_counter() - t0) * 1000

    try:
        # TLS handshake (https only)
        if scheme == "https":
            t0 = time.perf_counter()
            context = ssl.create_default_context()
            s = context.wrap_socket(s, server_hostname=host)
            timings["tls_ms"] = (time.perf_counter() - t0) * 1000

        # Send request, wait for first byte
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
    print(f"Body Size:   {result['body_size']} bytes")
    for key, val in result["timings"].items():
        print(f"  {key:12s}: {val: .2f} ms")
    if 300 <= result["status_code"] < 400:
        loc = result["headers"].get("location", "?")
        print(f"Note: this is a redirect to {loc} (netscope does not follow redirects),")
        print("      so the header check below describes the redirect, not the final page.")
    print("Header check:")
    is_http = result["url"].startswith("http://")
    for h in CHECKED_HEADERS:
        if h in result["headers"]:
            print(f"   [OK]  {h}:  {result['headers'][h]}")
        elif h == "strict-transport-security" and is_http:
            print(f"   [INFO] {h} only applies over HTTPS")
        else:
            print(f"   [WARN] missing {h}")
    if "server" in result["headers"]:
        print(f"   [INFO] server header exposes: {result['headers']['server']}")


def background_checker(target_url, interval_seconds, timeout):
    while True:
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
                stats[target_url]["requests_total"] += 1
                stats[target_url]["errors_total"] += 1
            print(f"[error] {target_url} -> {type(e).__name__}: {e}")
        time.sleep(interval_seconds)


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


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        body = render_metrics().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body)

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
                        help="port for /metrics in watch mode (default 8000)")
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

    for url in urls:
        stats[url] = new_stats()
        threading.Thread(
            target=background_checker,
            args=(url, args.interval, args.timeout),
            daemon=True,
        ).start()

    print(f"Checking {len(urls)} target(s) every {args.interval:g}s")
    print(f"Metrics available at http://localhost:{args.port}/metrics (Ctrl+C to stop)")
    try:
        HTTPServer(("localhost", args.port), MetricsHandler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()