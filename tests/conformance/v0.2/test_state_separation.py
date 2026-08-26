import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/v0.2/state-separation"
SCHEMA = json.loads((ROOT / "schemas/v0.2/state-separation.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def load(name):
    return json.loads((FIXTURES / name).read_text())


def semantic_errors(record):
    errors = []
    if record.get("record_type") == "state_record":
        kind = record.get("state_kind")
        if kind == "runtime" and record.get("validation_state") in {"verified", "stably_verified"}:
            errors.append("runtime_success_is_not_verified")
        if kind == "observed":
            subject = record.get("subject_ref", {}).get("subject_id", "")
            if any(subject not in ref for ref in record.get("evidence_refs", [])):
                errors.append("evidence_scope_mismatch")
    if record.get("record_type") == "state_transition":
        if record.get("transition_type") == "execute" and not record.get("authorization_refs"):
            errors.append("authorization_missing")
        if any("stale" in ref for ref in record.get("evidence_refs", [])):
            errors.append("evidence_stale")
        if any(item.get("result") != "pass" for item in record.get("condition_results", [])):
            errors.append("transition_condition_not_satisfied")
    return errors


class StateSeparationTests(unittest.TestCase):
    def assert_valid(self, name):
        data = load(name)
        self.assertEqual([], list(VALIDATOR.iter_errors(data)), name)
        self.assertEqual([], semantic_errors(data), name)

    def assert_rejected(self, name):
        data = load(name)
        self.assertTrue(list(VALIDATOR.iter_errors(data)) or semantic_errors(data), name)

    def test_positive_records_and_transitions(self):
        for name in [
            "source-valid.json", "runtime-valid.json", "observed-valid.json", "decision-valid.json",
            "transition-source-runtime-valid.json", "transition-runtime-observed-valid.json",
            "transition-observed-decision-valid.json",
        ]:
            with self.subTest(name=name):
                self.assert_valid(name)

    def test_negative_records_and_transitions(self):
        for name in [
            "source-claims-runtime-invalid.json", "runtime-claims-verified-invalid.json",
            "observed-missing-evidence-invalid.json", "observed-scope-mismatch-invalid.json",
            "decision-missing-basis-invalid.json", "transition-missing-authorization-invalid.json",
            "transition-stale-evidence-invalid.json", "unknown-enum-invalid.json",
        ]:
            with self.subTest(name=name):
                self.assert_rejected(name)

    def test_unknown_schema_version_fails_closed(self):
        data = load("source-valid.json")
        data["schema_version"] = "9.9"
        self.assertTrue(list(VALIDATOR.iter_errors(data)))


if __name__ == "__main__":
    unittest.main()
