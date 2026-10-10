import signal
import socket
import subprocess
import sys
import time
import unittest

from netscope import cli


class DashboardTableTests(unittest.TestCase):
    def test_every_table_column_has_a_cell(self):
        # A header without a matching cell shifts every value one column left.
        columns = cli.DASHBOARD_HTML.count("<th>")
        cells = cli.DASHBOARD_HTML.count("tr.appendChild(")
        self.assertEqual(columns, cells)


class ShutdownTests(unittest.TestCase):
    def test_sigterm_stops_netscope_cleanly(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        proc = subprocess.Popen(
            [sys.executable, "-m", "netscope", "http://127.0.0.1:9/",
             "--port", str(port), "--interval", "60"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                self.fail("netscope never started listening")
            proc.send_signal(signal.SIGTERM)
            self.assertEqual(proc.wait(timeout=5), 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    unittest.main()