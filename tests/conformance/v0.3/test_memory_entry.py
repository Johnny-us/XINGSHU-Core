import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/support"))
from strict_schema_validation import strict_validator  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/v0.3/memory-entry"
SCHEMA = json.loads((ROOT / "schemas/v0.3/memory-entry.schema.json").read_text())
VALIDATOR = strict_validator(SCHEMA)
FORBIDDEN_KEYS = {
    "payload", "raw_payload", "content", "body", "secret", "credential", "token",
    "cookie", "local_path", "absolute_path", "email", "account_id", "device_id",
    "personal_identity", "chat_text",
}


def load(name):
    return json.loads((FIXTURES / name).read_text())


def all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)


def evaluate(record):
    if list(VALIDATOR.iter_errors(record)):
        return "rejected"
    if FORBIDDEN_KEYS.intersection(all_keys(record)):
        return "rejected"
    state = record["conclusion_state"]
    if state == "candidate":
        return "needs_review"
    if state == "active":
        if record["evidence_state"] != "current":
            return "needs_review"
        if not record["current_loading_allowed"]:
            return "needs_review"
        if record["source_verification"]["status"] != "verified":
            return "needs_review"
        if record["dedup_conflict_review"]["status"] not in {"clear", "merged"}:
            return "needs_review"
        if record["promotion_review"]["status"] != "approved":
            return "needs_review"
        return "current_valid"
    if state in {"superseded", "deprecated", "historical"}:
        return "history_only" if not record["current_loading_allowed"] else "rejected"
    return "needs_review"


class MemoryEntryTests(unittest.TestCase):
    def test_active_current_record(self):
        self.assertEqual("current_valid", evaluate(load("active-current-valid.json")))

    def test_candidate_without_source_is_rejected(self):
        self.assertEqual("rejected", evaluate(load("memory-candidate-without-source-invalid.json")))

    def test_superseded_memory_preserves_history(self):
        record = load("memory-superseded-preserves-history-valid.json")
        self.assertEqual("history_only", evaluate(record))
        self.assertTrue(record["relationships"]["superseded_by"])
        self.assertTrue(record["source_refs"])

    def test_stale_evidence_routes_active_conclusion_to_review(self):
        record = load("stale-evidence-keeps-active-conclusion-needs-review.json")
        self.assertEqual([], list(VALIDATOR.iter_errors(record)))
        self.assertEqual("needs_review", evaluate(record))
        self.assertNotEqual("current_valid", evaluate(record))

    def test_reasoned_inference_requires_promotion_review(self):
        self.assertEqual("rejected", evaluate(load("reasoned-inference-promoted-without-review-invalid.json")))

    def test_low_risk_reasoned_inference_can_use_approved_automated_review(self):
        record = load("reasoned-inference-automated-reviewed-low-risk-valid.json")
        self.assertEqual([], list(VALIDATOR.iter_errors(record)))
        self.assertEqual("automated", record["promotion_review"]["reviewer_type"])
        self.assertEqual("current_valid", evaluate(record))

    def test_historical_conclusion_cannot_load_as_current(self):
        self.assertEqual("rejected", evaluate(load("historical-conclusion-loaded-as-current-invalid.json")))

    def test_unknown_states_fail_closed(self):
        record = load("active-current-valid.json")
        record["conclusion_state"] = "probably_active"
        self.assertEqual("rejected", evaluate(record))


if __name__ == "__main__":
    unittest.main()
