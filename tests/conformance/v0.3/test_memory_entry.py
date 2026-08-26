import json
import unittest
from pathlib import Path

from xingshu_core import Decision, validate_record


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/v0.3/memory-entry"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def evaluate(record):
    return validate_record(record).status


class MemoryEntryTests(unittest.TestCase):
    def test_active_current_record(self):
        result = validate_record(load("active-current-valid.json"))
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual("current_valid", result.status)

    def test_candidate_without_source_is_rejected(self):
        self.assertEqual("rejected", evaluate(load("memory-candidate-without-source-invalid.json")))

    def test_superseded_memory_preserves_history(self):
        record = load("memory-superseded-preserves-history-valid.json")
        self.assertEqual("history_only", evaluate(record))
        self.assertTrue(record["relationships"]["superseded_by"])
        self.assertTrue(record["source_refs"])

    def test_stale_evidence_routes_active_conclusion_to_review(self):
        record = load("stale-evidence-keeps-active-conclusion-needs-review.json")
        result = validate_record(record)
        self.assertEqual(Decision.NEEDS_REVIEW, result.decision)
        self.assertEqual("needs_review", result.status)

    def test_reasoned_inference_requires_promotion_review(self):
        self.assertEqual("rejected", evaluate(load("reasoned-inference-promoted-without-review-invalid.json")))

    def test_low_risk_reasoned_inference_can_use_approved_automated_review(self):
        record = load("reasoned-inference-automated-reviewed-low-risk-valid.json")
        self.assertEqual("automated", record["promotion_review"]["reviewer_type"])
        result = validate_record(record)
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual("current_valid", result.status)

    def test_historical_conclusion_cannot_load_as_current(self):
        self.assertEqual("rejected", evaluate(load("historical-conclusion-loaded-as-current-invalid.json")))

    def test_unknown_states_fail_closed(self):
        record = load("active-current-valid.json")
        record["conclusion_state"] = "probably_active"
        self.assertEqual("rejected", evaluate(record))


if __name__ == "__main__":
    unittest.main()
