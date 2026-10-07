import socket
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

stats = {
    "requests_total": 0,
    "errors_total": 0,
    "total_latency_ms": 0.0,
    "last_status": None,
    "last_url": None,
}
stats_lock = threading.Lock()


def request(url):
    timings = {}
    t_start = time.perf_counter()

    scheme, rest = url.split("://", 1)
    assert scheme == "http", "Only http supported for now"
    host, path = rest.split("/", 1) if "/" in rest else (rest, "")
    path = "/" + path

    t0 = time.perf_counter()
    ip = socket.gethostbyname(host)
    timings["dns_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, 80))
    timings["connect_ms"] = (time.perf_counter() - t0) * 1000

    req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
    t0 = time.perf_counter()
    s.send(req.encode())

    response = s.makefile("rb")
    first_line = response.readline()
    timings["ttfb_ms"] = (time.perf_counter() - t0) * 1000

    status_line = first_line.decode().strip()

    headers = {}
    while True:
        line = response.readline().decode()
        if line in ("\r\n", "\n", ""):
            break
        k, v = line.split(":", 1)
        headers[k.strip().casefold()] = v.strip()

    body = response.read()
    s.close()

    timings["total_ms"] = (time.perf_counter() - t_start) * 1000

    return {
        "url": url,
        "ip": ip,
        "status": status_line,
        "headers": headers,
        "body_size": len(body),
        "timings": timings,
    }


def background_checker(target_url, interval_seconds):
    while True:
        try:
            result = request(target_url)
            with stats_lock:
                stats["requests_total"] += 1
                stats["total_latency_ms"] += result["timings"]["total_ms"]
                stats["last_status"] = result["status"]
                stats["last_url"] = target_url
            print(f"[checked] {target_url} -> {result['status']} "
                  f"({result['timings']['total_ms']:.2f} ms)")
        except Exception as e:
            with stats_lock:
                stats["requests_total"] += 1
                stats["errors_total"] += 1
            print(f"[error] {target_url} -> {e}")
        time.sleep(interval_seconds)


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return

        with stats_lock:
            total = stats["requests_total"]
            errors = stats["errors_total"]
            avg_latency = (stats["total_latency_ms"] / total) if total else 0.0
            last_status = stats["last_status"] or "none"
            last_url = stats["last_url"] or "none"

        body = (
            f"# HELP netscope_requests_total Total requests made by netscope\n"
            f"# TYPE netscope_requests_total counter\n"
            f"netscope_requests_total {total}\n"
            f"# HELP netscope_errors_total Total failed requests\n"
            f"# TYPE netscope_errors_total counter\n"
            f"netscope_errors_total {errors}\n"
            f"# HELP netscope_avg_latency_ms Average request latency in ms\n"
            f"# TYPE netscope_avg_latency_ms gauge\n"
            f"netscope_avg_latency_ms {avg_latency:.2f}\n"
            f"# HELP netscope_last_status_info Last HTTP status seen (as label)\n"
            f"# TYPE netscope_last_status_info gauge\n"
            f'netscope_last_status_info{{status="{last_status}",url="{last_url}"}} 1\n'
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    TARGET_URL = "http://example.com/"
    CHECK_INTERVAL_SECONDS = 10

    checker_thread = threading.Thread(
        target=background_checker,
        args=(TARGET_URL, CHECK_INTERVAL_SECONDS),
        daemon=True,
    )
    checker_thread.start()

    print(f"Checking {TARGET_URL} every {CHECK_INTERVAL_SECONDS}s")
    print("Metrics available at http://localhost:8000/metrics")
    server = HTTPServer(("localhost", 8000), MetricsHandler)
    server.serve_forever()
