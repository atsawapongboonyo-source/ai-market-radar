import unittest
from worker_crash_correlation import correlate_crashes, summarize_timeout_events


class CorrelationTests(unittest.TestCase):
    def setUp(self):
        self.crash = [{"timestamp": "2026-10-16T02:19:06Z",
                       "message": "Worker (pid:19882) was sent code 139!"}]

    def test_nearby_request_not_claimed_as_cause(self):
        requests = [{"timestamp": "2026-10-16T02:19:04Z",
                     "path": "/api/theme-rotation", "statusCode": "200"}]
        result = correlate_crashes(self.crash, requests)
        self.assertEqual(result[0]["root_cause"], "UNDETERMINED")
        self.assertEqual(result[0]["nearby_requests"][0]["offset_seconds"], -2)

    def test_outside_window_excluded(self):
        requests = [{"timestamp": "2026-10-16T02:18:00Z",
                     "path": "/api/scan"}]
        self.assertEqual(correlate_crashes(self.crash, requests)[0]["nearby_requests"], [])

    def test_non_api_request_excluded(self):
        requests = [{"timestamp": "2026-10-16T02:19:06Z", "path": "/"}]
        self.assertEqual(correlate_crashes(self.crash, requests)[0]["nearby_requests"], [])

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            correlate_crashes(self.crash, [{"timestamp": "2026-10-16T02:19:06",
                                           "path": "/api/scan"}])

    def test_timeout_is_separate(self):
        logs = [{"timestamp": "2026-10-16T02:20:00Z",
                 "message": "[CRITICAL] WORKER TIMEOUT (pid:123)"}]
        self.assertEqual(summarize_timeout_events(logs)[0]["pid"], 123)


if __name__ == "__main__":
    unittest.main()
