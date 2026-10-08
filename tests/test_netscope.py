import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from netscope import cli


class  FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"hello"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, format, *args):
        pass

class NormalizeUrlTets(unittest.TestCase):
    def test_adds_https_when_missing(self):
        self.assertEqual(cli.normalize_url("github.com"), "https://github.com")

    def test_keeps_existing_scheme(self):
        self.assertEqual(cli.normalize_url("http://example.com"), "http://example.com")

class RequestTests(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), FakeHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_parses_status_headers_and_body(self):
        result = cli.request(f"http://127.0.0.1:{self.port}/", timeout=5)
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["body_size"], 5)
        self.assertEqual(result["headers"]["x-frame-options"], "DENY")
        self.assertNotIn("strict-transport-security", result["headers"])

    def test_http_has_no_tls_stage(self):
        result = cli.request(f"http://127.0.0.1:{self.port}/", timeout=5)
        for stage in ("dns_ms", "connect_ms", "ttfb_ms", "total_ms"):
            self.assertIn(stage, result["timings"])
        self.assertNotIn("tls_ms", result["timings"])

    def test_connection_refused_raises(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
        s.close()
        with self.assertRaises(OSError):
            cli.request(f"http://127.0.0.1:{free_port}/", timeout=2)
        

class MetricsTests(unittest.TestCase):
    URL = "http://x/"

    def setUp(self):
        cli.stats.clear()
        cli.stats[self.URL] = cli.new_stats()

    def tearDown(self):
        cli.stats.clear()
    
    def test_counter_is_rendered(self):
        cli.stats[self.URL]["requests_total"] = 3
        self.assertIn('netscope_requests_total{url="http://x/"} 3', cli.render_metrics())
    
    def test_header_presence_is_rendered_as_1_and_0(self):
        cli.stats[self.URL]["headers_present"] = {
            "x-frame-options": True,
            "cache-control": False,
        }
        out = cli.render_metrics()
        self.assertIn('header="x-frame-options"} 1', out)
        self.assertIn('header="cache-control"} 0', out)

    def test_inf_bucket_equals_total_count(self):
        cli.stats[self.URL]["hist_count"] = 4
        self.assertIn('le="+Inf"} 4', cli.render_metrics())


if __name__ == "__main__":
    unittest.main()
    


    
