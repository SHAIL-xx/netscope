import ssl
import unittest

from netscope import cli


class CertDaysTests(unittest.TestCase):
    def test_days_remaining(self):
        cert = {"notAfter": "Jan  1 00:00:00 2030 GMT"}
        now = ssl.cert_time_to_seconds("Dec 22 00:00:00 2029 GMT")
        self.assertAlmostEqual(cli.cert_days_remaining(cert, now=now), 10.0, places=3)

    def test_already_expired_is_negative(self):
        cert = {"notAfter": "Jan  1 00:00:00 2030 GMT"}
        now = ssl.cert_time_to_seconds("Jan  3 00:00:00 2030 GMT")
        self.assertLess(cli.cert_days_remaining(cert, now=now), 0)


class CertMetricTests(unittest.TestCase):
    URL = "https://x/"

    def setUp(self):
        cli.stats.clear()
        cli.stats[self.URL] = cli.new_stats()

    def tearDown(self):
        cli.stats.clear()

    def test_metric_present_for_https_target(self):
        cli.stats[self.URL]["cert_expiry_days"] = 42.5
        self.assertIn('netscope_cert_expiry_days{url="https://x/"} 42.5',
                      cli.render_metrics())

    def test_no_metric_line_without_cert_data(self):
        out = cli.render_metrics()
        self.assertNotIn('netscope_cert_expiry_days{', out)

    def test_status_json_includes_cert_days(self):
        cli.stats[self.URL]["cert_expiry_days"] = 12.0
        self.assertEqual(cli.render_status()["targets"][0]["cert_days"], 12.0)


if __name__ == "__main__":
    unittest.main()
