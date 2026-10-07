import socket
import time

def request(url):
    timings = {}
    t_start = time.perf_counter()

    scheme, rest = url.split("://", 1)
    assert scheme == "http", "Only http supported for now"
    host, path = rest.split("/", 1) if "/" in rest else (rest, "")
    path = "/" + path

    # --- DNS resolution timing ---
    t0 = time.perf_counter()
    ip = socket.gethostbyname(host)
    timings["dns_ms"] = (time.perf_counter() - t0) * 1000

    # --- TCP connect timing ---
    t0 = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, 80))
    timings["connect_ms"] = (time.perf_counter() - t0) * 1000

    # --- Send request ---
    req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
    t0 = time.perf_counter()
    s.send(req.encode())

    # --- Time to first byte ---
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

def print_report(result):
    print(f"URL:     {result['url']}")
    print(f"Resolved IP: {result['ip']}")
    print(f"Status:  {result['status']}")
    print(f"Body size: {result['body_size']} bytes")
    print("Timing breakdown:")
    for key, val in result["timings"].items():
        print(f"  {key:12s}: {val:.2f} ms")
    print("Headers:")
    for k, v in result["headers"].items():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    result = request("http://example.com/")
    print_report(result)
