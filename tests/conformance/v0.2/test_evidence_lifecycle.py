import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/support"))
from strict_schema_validation import strict_validator  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/v0.2/evidence-lifecycle"
SCHEMA = json.loads((ROOT / "schemas/v0.2/evidence-lifecycle.schema.json").read_text())
VALIDATOR = strict_validator(SCHEMA)
FORBIDDEN = {"payload", "raw_payload", "content", "body", "secret", "credential", "token", "cookie", "local_path", "email", "account_id", "device_id", "personal_identity", "chat_text"}


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


def semantic_errors(data):
    errors = []
    if FORBIDDEN.intersection(all_keys(data)):
        errors.append("payload_boundary_violation")
    subject = data.get("subject_ref", {}).get("subject_id")
    scoped = data.get("validation_scope", {}).get("subject_identity", {}).get("subject_id")
    if subject and scoped and subject != scoped:
        errors.append("evidence_scope_mismatch")
    if data.get("evidence_state") == "current" and data.get("validation_method", {}).get("result") == "not_run":
        errors.append("not_run_cannot_support_current")
    valid_until = data.get("freshness", {}).get("valid_until")
    evaluated_at = data.get("freshness", {}).get("evaluated_at")
    if data.get("evidence_state") == "current" and valid_until and evaluated_at:
        if datetime.fromisoformat(valid_until.replace("Z", "+00:00")) <= datetime.fromisoformat(evaluated_at.replace("Z", "+00:00")):
            errors.append("evidence_stale")
    relationships = data.get("relationships", {})
    if data.get("evidence_state") == "corrected" and not relationships.get("corrects"):
        errors.append("correction_chain_broken")
    return errors


class EvidenceLifecycleTests(unittest.TestCase):
    def assert_valid(self, name):
        data = load(name)
        self.assertEqual([], list(VALIDATOR.iter_errors(data)), name)
        self.assertEqual([], semantic_errors(data), name)

    def assert_rejected(self, name):
        data = load(name)
        self.assertTrue(list(VALIDATOR.iter_errors(data)) or semantic_errors(data), name)

    def test_valid_lifecycle_records(self):
        for name in ["current-valid.json", "expired-becomes-stale.json", "superseded-historical.json", "correction-chain-valid.json", "synthetic-public-valid.json"]:
            with self.subTest(name=name):
                self.assert_valid(name)

    def test_invalid_lifecycle_records(self):
        for name in ["scope-mismatch-invalid.json", "correction-chain-broken-invalid.json", "not-run-cannot-support-current-invalid.json", "payload-field-forbidden-invalid.json", "payload-in-extension-forbidden-invalid.json"]:
            with self.subTest(name=name):
                self.assert_rejected(name)

    def test_unknown_state_fails_closed(self):
        data = load("current-valid.json")
        data["evidence_state"] = "fresh_enough"
        self.assertTrue(list(VALIDATOR.iter_errors(data)))


if __name__ == "__main__":
    unittest.main()
