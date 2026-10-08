import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from unittest import mock

from netscope import cli


class EnvDefaultTests(unittest.TestCase):
    def test_uses_fallback_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(cli.env_default("NETSCOPE_PORT", int, 8000), 8000)

    def test_reads_and_converts_value(self):
        with mock.patch.dict(os.environ, {"NETSCOPE_PORT": "9100"}):
            self.assertEqual(cli.env_default("NETSCOPE_PORT", int, 8000), 9100)

    def test_empty_value_uses_fallback(self):
        with mock.patch.dict(os.environ, {"NETSCOPE_PORT": ""}):
            self.assertEqual(cli.env_default("NETSCOPE_PORT", int, 8000), 8000)

    def test_bad_value_exits_with_message(self):
        with mock.patch.dict(os.environ, {"NETSCOPE_PORT": "abc"}):
            with self.assertRaises(SystemExit):
                cli.env_default("NETSCOPE_PORT", int, 8000)


class HealthEndpointTests(unittest.TestCase):
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

    def status_of(self, path):
        try:
            res = urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5)
            res.close()
            return res.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def test_healthz_is_always_ok(self):
        self.assertEqual(self.status_of("/healthz"), 200)

    def test_readyz_is_503_until_first_check(self):
        self.assertEqual(self.status_of("/readyz"), 503)
        cli.stats["http://x/"]["requests_total"] = 1
        self.assertEqual(self.status_of("/readyz"), 200)

    def test_readyz_needs_every_target_checked(self):
        cli.stats["http://y/"] = cli.new_stats()
        cli.stats["http://x/"]["requests_total"] = 1
        self.assertEqual(self.status_of("/readyz"), 503)


if __name__ == "__main__":
    unittest.main()
