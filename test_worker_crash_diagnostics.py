import unittest
from worker_crash_diagnostics import summarize_worker_logs, assess_memory


class WorkerCrashDiagnosticsTests(unittest.TestCase):
    def test_sigsegv_style_exit_code(self):
        result = summarize_worker_logs(["[40] [ERROR] Worker (pid:18378) was sent code 139!"])
        self.assertEqual(result["crashes"], [{"pid": 18378, "exit_code": 139, "signal": 11}])

    def test_restart_parsing(self):
        result = summarize_worker_logs(["[20086] [INFO] Booting worker with pid: 20086"])
        self.assertEqual(result["boots"], [20086])

    def test_unrelated_http_line_ignored(self):
        result = summarize_worker_logs(['GET /api/scan HTTP/1.1" 200'])
        self.assertEqual(result["crashes"], [])

    def test_memory_is_not_root_cause(self):
        result = assess_memory([208_000_000, 235_000_000], 536_870_912)
        self.assertLess(result["peak_fraction"], .5)
        self.assertIn("Sampling", result["caveat"])

    def test_missing_memory_fails_closed(self):
        self.assertEqual(assess_memory([], 536_870_912)["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
