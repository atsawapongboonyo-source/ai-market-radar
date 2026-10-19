"""Run isolated Gunicorn over loopback to verify real HTTP and log lifecycle."""
import os
import socket
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class GunicornSmokeTests(unittest.TestCase):
    def exercise(self, enabled):
        port = free_port()
        env = dict(os.environ, RADAR_REQUEST_DIAGNOSTICS="1" if enabled else "0")
        cmd = [sys.executable, "-m", "gunicorn", "--bind", f"127.0.0.1:{port}",
               "--workers", "1", "--timeout", "8", "--log-level", "info",
               "test_request_diagnostics_gunicorn_app:app"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        responses = []
        try:
            for _ in range(60):
                if proc.poll() is not None:
                    self.fail("Gunicorn exited before serving")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/api/scan", timeout=0.2) as response:
                        self.assertEqual(response.status, 200)
                        responses.append(response.read())
                    break
                except (OSError, TimeoutError):
                    time.sleep(0.05)
            else:
                self.fail("Gunicorn did not become ready")
            with urlopen(f"http://127.0.0.1:{port}/api/catalyst/PRIVATE-SYMBOL?token=SECRET", timeout=2) as response:
                self.assertEqual(response.status, 200)
                responses.append(response.read())
            try:
                urlopen(f"http://127.0.0.1:{port}/private/PRIVATE-PATH?token=SECRET", timeout=2)
            except HTTPError as error:
                self.fail(f"unexpected HTTP error: {error.code}")
            try:
                urlopen(f"http://127.0.0.1:{port}/missing/PRIVATE-PATH?token=SECRET", timeout=2)
            except HTTPError as error:
                self.assertEqual(error.code, 404)
        finally:
            proc.terminate()
            try:
                _, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, stderr = proc.communicate(timeout=5)
        log = stderr.decode("utf-8", errors="replace")
        self.assertNotIn("PRIVATE-SYMBOL", log)
        self.assertNotIn("PRIVATE-PATH", log)
        self.assertNotIn("token=SECRET", log)
        self.assertEqual(len(responses), 2)
        if enabled:
            self.assertIn("REQUEST_START", log)
            self.assertIn("REQUEST_END", log)
            self.assertIn("status=404", log)
            self.assertIn("route=/api/catalyst/<ticker>", log)
        else:
            self.assertNotIn("REQUEST_START", log)
            self.assertNotIn("REQUEST_END", log)

    def test_enabled(self):
        self.exercise(True)

    def test_disabled(self):
        self.exercise(False)


if __name__ == "__main__":
    unittest.main()
