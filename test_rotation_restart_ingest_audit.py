import unittest
from scripts.rotation_restart_ingest_audit import audit


def log(time, message):
    return {"timestamp": time, "message": message}


class RestartIngestAuditTests(unittest.TestCase):
    def test_counts_intervals_and_status(self):
        rows = [
            log("2026-11-03T00:51:01Z", "Handling signal: term"),
            log("2026-11-03T00:21:01Z", "Handling signal: term"),
            log("2026-11-03T00:21:43Z", '"POST /api/rotation/ingest HTTP/1.1" 200 33'),
            log("2026-11-03T00:36:01Z", '"POST /api/rotation/ingest HTTP/1.1" 500 33'),
            log("2026-11-03T00:21:34Z", '{"event": "ROTATION_STORAGE_VERIFICATION"}'),
        ]
        result = audit(rows)
        self.assertEqual(result["termination_intervals_seconds"], [1800])
        self.assertEqual(result["ingest_http_200_count"], 1)
        self.assertEqual(result["ingest_other_status_count"], 1)
        self.assertEqual(result["storage_verification_log_count"], 1)

    def test_invalid_timestamp_ignored(self):
        self.assertEqual(audit([log("bad", "Handling signal: term")])["termination_count"], 0)


if __name__ == "__main__":
    unittest.main()
