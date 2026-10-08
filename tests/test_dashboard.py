import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer

from netscope import cli


class StatusTests(unittest.TestCase):
    def setUp(self):
        cli.stats.clear()

    def tearDown(self):
        cli.stats.clear()

    def test_pending_before_first_check(self):
        cli.stats["http://x/"] = cli.new_stats()
        target = cli.render_status()["targets"][0]
        self.assertEqual(target["state"], "pending")

    def test_up_and_down_states(self):
        cli.stats["http://up/"] = cli.new_stats()
        cli.stats["http://up/"]["requests_total"] = 1
        cli.stats["http://down/"] = cli.new_stats()
        cli.stats["http://down/"]["requests_total"] = 1
        cli.stats["http://down/"]["last_error"] = "TimeoutError: timed out"
        states = {t["url"]: t["state"] for t in cli.render_status()["targets"]}
        self.assertEqual(states["http://up/"], "up")
        self.assertEqual(states["http://down/"], "down")

    def test_failed_check_is_recorded_and_thread_survives(self):
        # Regression test for the bug where the except branch crashed the thread.
        url = "http://nonexistent.invalid/"
        cli.stats[url] = cli.new_stats()
        stop = threading.Event()
        t = threading.Thread(target=cli.background_checker, args=(url, 0.05, 2, stop), daemon=True)
        t.start()
        time.sleep(0.6)
        alive = t.is_alive()
        stop.set()
        t.join(timeout=3)
        self.assertTrue(alive)
        st = cli.stats[url]
        self.assertGreaterEqual(st["errors_total"], 2)
        self.assertIsNotNone(st["last_error"])


class HttpEndpointTests(unittest.TestCase):
    def setUp(self):
        cli.stats.clear()
        cli.stats["http://x/"] = cli.new_stats()
        self.server = HTTPServer(("127.0.0.1", 0), cli.MetricsHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        cli.stats.clear()

    def get(self, path):
        return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5)

    def test_dashboard_page_is_html(self):
        res = self.get("/")
        self.assertEqual(res.status, 200)
        self.assertIn("text/html", res.headers["Content-Type"])
        self.assertIn(b"netscope", res.read())

    def test_api_status_is_json(self):
        res = self.get("/api/status")
        data = json.loads(res.read())
        self.assertEqual(data["targets"][0]["url"], "http://x/")

    def test_metrics_still_works(self):
        self.assertIn(b"netscope_requests_total", self.get("/metrics").read())

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
