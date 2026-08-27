import copy
import json
import unittest
from pathlib import Path

from xingshu_core import Decision, validate_record


ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads((ROOT / path).read_text())


class ValidatorRuntimeTests(unittest.TestCase):
    def test_valid_memory_passes(self):
        result = validate_record(load("examples/v0.4/memory-valid.json"))
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual("current_valid", result.status)
        self.assertEqual(0, result.exit_code)

    def test_stale_memory_needs_review(self):
        result = validate_record(load("examples/v0.4/memory-needs-review.json"))
        self.assertEqual(Decision.NEEDS_REVIEW, result.decision)
        self.assertEqual("needs_review", result.status)
        self.assertEqual(2, result.exit_code)

    def test_schema_invalid_memory_is_rejected(self):
        result = validate_record(
            load("tests/fixtures/v0.3/memory-entry/memory-candidate-without-source-invalid.json")
        )
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertEqual(3, result.exit_code)
        self.assertTrue(result.errors)

    def test_valid_migration_passes_without_claiming_runtime_verified(self):
        record = load("examples/v0.4/migration-valid.json")
        result = validate_record(record)
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual("accepted", result.status)
        self.assertEqual("pending_verification", record["runtime_validation_state"])

    def test_knowledge_object_semantic_violation_is_rejected(self):
        record = load("tests/fixtures/v0.3/knowledge-object/cross-platform-path-reuse-invalid.json")
        result = validate_record(record)
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertIn("cross_platform_path_reuse", {issue.code for issue in result.errors})

    def test_migration_semantic_violation_is_rejected(self):
        record = load(
            "tests/fixtures/v0.3/migration-provenance/migration-drops-source-without-provenance-invalid.json"
        )
        result = validate_record(record)
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertIn(
            "source_without_mapping_or_omission",
            {issue.code for issue in result.errors},
        )

    def test_unknown_record_type_fails_closed(self):
        result = validate_record({"schema_version": "0.3", "record_type": "unknown_object"})
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertEqual("unknown_record_type", result.errors[0].code)

    def test_validation_does_not_modify_record(self):
        record = load("examples/v0.4/memory-valid.json")
        before = copy.deepcopy(record)
        validate_record(record)
        self.assertEqual(before, record)

    def test_error_output_does_not_echo_private_value(self):
        record = load("examples/v0.4/memory-valid.json")
        record["secret"] = "PRIVATE_VALUE_SENTINEL"
        result = validate_record(record)
        rendered = json.dumps(result.to_dict())
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertEqual("privacy_boundary_violation", result.errors[0].code)
        self.assertNotIn("PRIVATE_VALUE_SENTINEL", rendered)

    def test_timezone_naive_record_is_rejected(self):
        record = load("examples/v0.4/memory-valid.json")
        record["created_at"] = "2026-01-01T00:00:00"
        result = validate_record(record)
        self.assertEqual(Decision.REJECT, result.decision)
        self.assertIn("schema_format", {issue.code for issue in result.errors})


if __name__ == "__main__":
    unittest.main()
