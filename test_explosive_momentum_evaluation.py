import unittest
from datetime import datetime, timedelta, timezone
from explosive_momentum_evaluation import evaluate_replay

NOW = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
EVENTS = {"events": [
    {"symbol": "A", "state": "REVIEW", "observed_at_utc": NOW.isoformat()},
    {"symbol": "B", "state": "WATCH", "observed_at_utc": NOW.isoformat()},
    {"symbol": "C", "state": "REVIEW", "observed_at_utc": NOW.isoformat()},
    {"symbol": "D", "state": "WATCH", "observed_at_utc": NOW.isoformat()},
]}


def labels():
    return [{"symbol": s, "became_leader": s in ("A", "B"),
             "evaluated_after_utc": NOW + timedelta(hours=1)}
            for s in ("A", "B", "C", "D")]


class EvaluationTests(unittest.TestCase):
    def test_complete_confusion_matrix(self):
        result = evaluate_replay(EVENTS, labels(), expected_symbols=("A", "B", "C", "D"))
        self.assertEqual(result["status"], "EVALUATED")
        self.assertEqual([result[k] for k in ("true_positive", "false_positive", "false_negative", "true_negative")], [1, 1, 1, 1])
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 0.5)

    def test_missing_universe_blocks(self):
        self.assertEqual(evaluate_replay(EVENTS, labels())["reason"], "UNIVERSE_COVERAGE_NOT_PROVEN")

    def test_missing_negative_symbol_blocks(self):
        self.assertEqual(evaluate_replay({"events": EVENTS["events"][:3]}, labels(), expected_symbols=("A","B","C","D"))["reason"], "MISSING_SCREENED_SYMBOLS")

    def test_missing_outcome_blocks(self):
        self.assertEqual(evaluate_replay(EVENTS, labels()[:3], expected_symbols=("A","B","C","D"))["reason"], "INCOMPLETE_OUTCOME_LABELS")

    def test_future_leakage_blocks(self):
        future = labels()
        future[0]["evaluated_after_utc"] = NOW
        self.assertEqual(evaluate_replay(EVENTS, future, expected_symbols=("A","B","C","D"))["reason"], "OUTCOME_NOT_AFTER_OBSERVATION")

    def test_duplicate_labels_block(self):
        future = labels() + [labels()[0]]
        self.assertEqual(evaluate_replay(EVENTS, future, expected_symbols=("A","B","C","D"))["reason"], "INVALID_OUTCOME_LABELS")


if __name__ == "__main__":
    unittest.main()
